"""結案審計閘。

與舊版的差異
------------
1. **不用 signal。** 舊版 `with timeout(1.5)` → `signal.alarm(1.5)`，而
   `alarm()` 只接受 int，每次呼叫都在檢查開始前就 TypeError，再被寬 except
   吞成「Manifest 處理錯誤」。而且 signal 只能在主執行緒用，Hermes 的
   worker thread 一律 ValueError。逾時改由 `subprocess.run(timeout=)` 與
   urllib 各自處理。
2. **回傳值是主角。** `audit_text()` 回傳 Report，呼叫端必須用它。
   同時無論結果如何都先寫 ledger，不依賴呼叫端有沒有接住。
3. **解析失敗是 INVALID 不是靜默放行。**
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from laap.audit import ledger
from laap.audit.manifest import Manifest, extract
from laap.audit.verifiers import VERIFIERS, Evidence, known_types

PASS = "PASS"
FAIL = "FAIL"
INVALID = "INVALID"

MAX_MANIFESTS_PER_TURN = 5

# 呼叫端（hook）自己的時間預算必須小於 Hermes 給 hook 的 timeout，否則
# Hermes 會 SIGKILL 我們 —— 那會讓整筆稽核靜默消失，連 ledger 都沒有。
# 寧可自己回「預算耗盡」也不要被砍。
MIN_VERIFIER_TIMEOUT_S = 2


@dataclass
class Verdict:
    status: str
    task_id: str
    reason: str
    evidence_type: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == PASS


@dataclass
class Report:
    verdicts: List[Verdict] = field(default_factory=list)

    @property
    def had_claims(self) -> bool:
        return bool(self.verdicts)

    @property
    def all_passed(self) -> bool:
        return bool(self.verdicts) and all(v.ok for v in self.verdicts)

    @property
    def failures(self) -> List[Verdict]:
        return [v for v in self.verdicts if not v.ok]

    def render(self) -> str:
        """給人看的一段文字。沒有宣告就回空字串（不吵）。"""
        if not self.verdicts:
            return ""
        lines = []
        for v in self.verdicts:
            icon = "✅" if v.status == PASS else ("⚠️" if v.status == INVALID else "❌")
            lines.append(f"{icon} {v.status} [{v.task_id}] {v.reason}")
        head = "【結案審計】" if self.all_passed else "【結案審計 · 未通過】"
        return head + "\n" + "\n".join(lines)


def run_gate(m: Manifest, *, remaining_s: Optional[float] = None) -> Verdict:
    """驗一筆 manifest。永遠回 Verdict，不丟例外。

    `remaining_s` 是這筆還剩多少秒可用。給了就把 evidence 裡的 timeout 夾到
    這個上限（複製 spec，不改原物件）；剩餘時間不夠就直接判 INVALID，不要
    開始一個注定會被外部砍掉的驗證。
    """
    if not m.ok:
        return Verdict(INVALID, m.task_id, m.error or "manifest 無法解析")

    data = m.data or {}
    task_id = str(data.get("task_id") or "<no-task-id>")
    etype = data.get("evidence_type") or data.get("audit_type")

    if not isinstance(etype, str) or etype not in VERIFIERS:
        return Verdict(
            INVALID,
            task_id,
            f"evidence_type 必須是 {known_types()} 之一，收到 {etype!r}",
        )

    spec = data.get("evidence")
    if not isinstance(spec, dict):
        return Verdict(INVALID, task_id, "evidence 必須是物件，內容依 evidence_type 而定", etype)

    if remaining_s is not None:
        if remaining_s < MIN_VERIFIER_TIMEOUT_S:
            return Verdict(
                INVALID,
                task_id,
                f"稽核預算耗盡（剩 {remaining_s:.1f}s），這筆未經驗證",
                etype,
            )
        # 不可變：夾 timeout 用複製，不動呼叫端的 dict
        capped = int(remaining_s)
        declared = spec.get("timeout")
        if not isinstance(declared, (int, float)) or declared > capped:
            spec = {**spec, "timeout": capped}

    try:
        ev: Evidence = VERIFIERS[etype](spec)
    except Exception as exc:  # noqa: BLE001 - 驗證器崩潰算 FAIL，不算通過
        return Verdict(FAIL, task_id, f"驗證器崩潰: {type(exc).__name__}: {exc}", etype)

    return Verdict(PASS if ev.passed else FAIL, task_id, ev.reason, etype, ev.detail)


def audit_text(
    text: str,
    *,
    source: str = "unknown",
    session_id: str = "",
    budget_s: Optional[float] = None,
) -> Report:
    """從一段文字抽出所有結案宣告並逐一實際驗證，結果寫入 ledger。

    `budget_s` 是整批驗證的總時間上限。呼叫端（hook）必須給一個小於外部
    timeout 的值，否則被 SIGKILL 時整筆稽核會靜默消失 —— 連 ledger 都不會有，
    而那等於「看起來有閘、實際放行」。
    """
    manifests = extract(text)
    report = Report()

    if not manifests:
        return report

    overflow = 0
    if len(manifests) > MAX_MANIFESTS_PER_TURN:
        overflow = len(manifests) - MAX_MANIFESTS_PER_TURN
        manifests = manifests[:MAX_MANIFESTS_PER_TURN]

    started = time.monotonic()
    for m in manifests:
        remaining = None
        if budget_s is not None:
            remaining = budget_s - (time.monotonic() - started)
        verdict = run_gate(m, remaining_s=remaining)
        report.verdicts.append(verdict)
        ledger.append(
            {
                "source": source,
                "session_id": session_id,
                "status": verdict.status,
                "task_id": verdict.task_id,
                "evidence_type": verdict.evidence_type,
                "reason": verdict.reason,
                "detail": verdict.detail,
                "manifest_raw": m.raw,
            }
        )

    if overflow:
        v = Verdict(
            INVALID,
            "<overflow>",
            f"本輪還有 {overflow} 筆宣告未驗（單輪上限 {MAX_MANIFESTS_PER_TURN}）",
        )
        report.verdicts.append(v)
        ledger.append(
            {
                "source": source,
                "session_id": session_id,
                "status": v.status,
                "task_id": v.task_id,
                "reason": v.reason,
            }
        )

    return report
