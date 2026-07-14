"""
constitution — 需求憲法：需求值與 RPE 權重的邊界、變速、來源預算治理。

概念採自作者開源的 need_constitution.json + governor（Apache 2.0, by Lorry）：
per-need 硬邊界、按來源分小時預算、超速凍結。直接回答「RPE 品質綁死 gbrain
分數線 → 垃圾訊號被永久累積」的安全網待辦。

治理對象（只管外部調變，不管恆定回歸）：
  - 需求值變化：psi_core satisfy/satisfy_all（source="user" 對話 / "agency" 自主行動）
  - RPE 角度權重變化：agency 的 angle_weights 更新
tick 的 decay-to-baseline 不受管 — 那是憲法自己的 drift_back 機制。

規則：range 硬夾 → 單次 delta 上限 → 小時預算（按來源）。超預算 = 凍結
（delta 歸零 + 審計），視窗滾動自動解凍。NEURALIS_CONSTITUTION=off 全放行。
審計：constitution-audit.jsonl（clamp / freeze 才記，正常放行不刷）。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

logger = logging.getLogger("laap.constitution")

_RULES_PATH = Path(__file__).resolve().parent / "need_constitution.json"
_AUDIT_PATH = Path(__file__).resolve().parents[1] / "constitution-audit.jsonl"


def _enabled() -> bool:
    return os.environ.get("NEURALIS_CONSTITUTION", "on").lower() not in ("off", "0", "false")


class Constitution:
    def __init__(self, rules_path: Path = _RULES_PATH):
        try:
            self.rules = json.loads(rules_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[憲法] 規則載入失敗，全放行: {e}")
            self.rules = {"needs": {}, "weights": {}}
        self._lock = threading.Lock()
        self._need_spend: dict = {}    # (need, source) → deque[(ts, amount)]
        self._weight_spend: dict = {}  # need → deque[(ts, amount)]
        self.clamps_total = 0
        self.freezes_total = 0

    # ── 需求值治理 ──

    def guard_need(self, need: str, current: float, delta: float, source: str) -> float:
        """回准許的 delta。range 硬夾 → 單次上限 → 小時預算（超支凍結）。"""
        if not _enabled() or delta == 0.0:
            return delta
        rule = self.rules.get("needs", {}).get(need)
        if not rule:
            return delta
        with self._lock:
            allowed = delta
            # 1. 單次上限
            cap = rule.get("max_delta_per_call", 1.0)
            if abs(allowed) > cap:
                allowed = cap if allowed > 0 else -cap
            # 2. range 硬夾（以結果值算）
            lo, hi = rule.get("range", [0.0, 1.0])
            allowed = max(lo, min(hi, current + allowed)) - current
            # 3. 小時預算（按來源，計絕對值）
            budget = rule.get("budget_per_hour", {}).get(source)
            if budget is not None:
                spent = self._spend_window(self._need_spend, (need, source))
                remaining = budget - spent
                if remaining <= 0:
                    self._audit("freeze_need", need=need, source=source,
                                delta=delta, budget=budget)
                    self.freezes_total += 1
                    return 0.0
                if abs(allowed) > remaining:
                    allowed = remaining if allowed > 0 else -remaining
                self._need_spend[(need, source)].append((time.time(), abs(allowed)))
            if abs(allowed - delta) > 1e-9:
                self._audit("clamp_need", need=need, source=source,
                            delta=delta, allowed=round(allowed, 4))
                self.clamps_total += 1
            return allowed

    # ── RPE 權重治理 ──

    def guard_weight(self, need: str, angle: str, delta: float) -> float:
        """RPE 角度權重變速上限 + 小時預算凍結。"""
        if not _enabled() or delta == 0.0:
            return delta
        rule = self.rules.get("weights", {})
        if not rule:
            return delta
        with self._lock:
            allowed = delta
            cap = rule.get("max_delta_per_update", 1.0)
            if abs(allowed) > cap:
                allowed = cap if allowed > 0 else -cap
            budget = rule.get("budget_per_hour_per_need")
            if budget is not None:
                spent = self._spend_window(self._weight_spend, need)
                remaining = budget - spent
                if remaining <= 0:
                    self._audit("freeze_weight", need=need, angle=angle,
                                delta=round(delta, 4), budget=budget)
                    self.freezes_total += 1
                    return 0.0
                if abs(allowed) > remaining:
                    allowed = remaining if allowed > 0 else -remaining
                self._weight_spend[need].append((time.time(), abs(allowed)))
            if abs(allowed - delta) > 1e-9:
                self._audit("clamp_weight", need=need, angle=angle,
                            delta=round(delta, 4), allowed=round(allowed, 4))
                self.clamps_total += 1
            return allowed

    # ── 內部 ──

    def _spend_window(self, store: dict, key) -> float:
        """滾動一小時視窗內已花費量（順手清過期）。呼叫方須持鎖。"""
        q = store.setdefault(key, deque())
        cutoff = time.time() - 3600
        while q and q[0][0] < cutoff:
            q.popleft()
        return sum(a for _, a in q)

    @staticmethod
    def _audit(event: str, **fields) -> None:
        try:
            entry = {"ts": time.time(), "event": event, **fields}
            with _AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[憲法] 審計寫入失敗: {e}")


_instance: Constitution | None = None
_instance_lock = threading.Lock()


def get_constitution() -> Constitution:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = Constitution()
    return _instance
