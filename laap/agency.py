"""
AgencyLoop — Phase 6：閉合「需求 → 行動 → 結果 → 記憶」迴路（v0）。

誠實標註：v0 的「意圖形成」是規則表（drive 超閾值 → 查詢），不是認知。
迴路是骨架；推理器官（Phase 3 過 benchmark 後）是可替換件。

煞車（先行，不是事後補）：
  - 唯讀白名單：只准 gbrain / qmd / file-search（不含寫入、不含任意 HTTP）
  - rate cap：每小時 ≤ NEURALIS_AGENCY_MAX_PER_HOUR（預設 6）
  - 每需求 cooldown 30 min（competence 在靜息值 drive 恆 0.75，沒 cooldown 會壟斷配額）
  - 審計：每次行動一行 JSONL → neuralis/agency-audit.jsonl（不進版控）
  - 總開關：NEURALIS_AGENCY=off

回寫：行動結果 → memory_bridge.store_important（→ gbrain laap/memory/*），
importance 上限 0.5（自主寫入防污染，見 handoff retention 原則）+ 情緒加權。
成功行動 satisfy 對應需求 → drive 回落 → 迴路自然靜下來，直到鬆弛再拉高。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

logger = logging.getLogger("laap.agency")

READONLY_WHITELIST = frozenset({"gbrain", "qmd", "file-search"})
NEED_COOLDOWN_S = 1800.0
AUDIT_PATH = Path(__file__).resolve().parents[1] / "agency-audit.jsonl"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


class AgencyLoop:
    """背景執行緒：定期評估 PsiCore drives，超閾值就形成意圖並行動。"""

    def __init__(self, psi, tools, bus=None,
                 interval: Optional[float] = None,
                 max_per_hour: Optional[float] = None,
                 drive_threshold: Optional[float] = None):
        self.psi = psi
        self.tools = tools
        self.bus = bus
        self.interval = interval if interval is not None else _env_float("NEURALIS_AGENCY_INTERVAL", 60.0)
        self.max_per_hour = int(max_per_hour if max_per_hour is not None
                                else _env_float("NEURALIS_AGENCY_MAX_PER_HOUR", 6))
        self.drive_threshold = (drive_threshold if drive_threshold is not None
                                else _env_float("NEURALIS_AGENCY_DRIVE_THRESHOLD", 0.45))
        self._action_ts: deque = deque()          # 最近一小時行動時間戳
        self._need_last_action: dict = {}          # need name → ts
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.actions_total = 0

    # ── 生命週期 ──

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"[Agency] 迴路啟動 interval={self.interval}s cap={self.max_per_hour}/h "
                    f"threshold={self.drive_threshold}")

    def stop(self) -> None:
        self._running = False

    # ── 主迴路 ──

    def _loop(self) -> None:
        while self._running:
            time.sleep(self.interval)
            try:
                self._evaluate()
            except Exception as e:
                # 同心跳原則：單次評估失敗不停迴路
                logger.warning(f"[Agency] 評估失敗: {e}")

    def _evaluate(self) -> None:
        now = time.time()
        while self._action_ts and now - self._action_ts[0] > 3600:
            self._action_ts.popleft()
        if len(self._action_ts) >= self.max_per_hour:
            return  # rate cap

        drives = self.psi.needs.get_drives()
        # 依 drive 高→低找第一個「超閾值 + 不在 cooldown + 規則表有招」的需求
        for need, drive in sorted(drives.items(), key=lambda kv: kv[1], reverse=True):
            if drive < self.drive_threshold:
                break
            if now - self._need_last_action.get(need, 0.0) < NEED_COOLDOWN_S:
                continue
            intent = self._form_intent(need)
            if intent is None:
                continue
            tool, prompt = intent
            self._act(need, drive, tool, prompt)
            return  # 每次評估最多一個行動

    # ── 意圖形成（v0 = 規則表，不是認知） ──

    def _form_intent(self, need: str):
        topic = (getattr(self.psi, "last_input", "") or "").strip()[:80]
        if need == "certainty":
            # 不確定感高 → 對最近話題查證；沒話題就盤點自身狀態脈絡
            return ("gbrain", topic or "LAAP neuralis 最近進度")
        if need == "growth":
            return ("gbrain", f"{topic} 延伸 新方向".strip() if topic else "新想法 探索 學習")
        if need == "competence":
            return ("gbrain", f"{topic} 作法 經驗".strip() if topic else "專案 進行中 任務 作法")
        return None  # relatedness / autonomy：v0 無唯讀動作可做

    # ── 行動 + 回寫 + 審計 ──

    def _act(self, need: str, drive: float, tool: str, prompt: str) -> None:
        if tool not in READONLY_WHITELIST:
            logger.warning(f"[Agency] 拒絕非白名單工具: {tool}")
            return
        now = time.time()
        result = self.tools.execute(tool, prompt, timeout=30)
        ok = bool(result) and not result.startswith(("[錯誤]", "[未知工具]", "[AgentOS 錯誤]")) \
            and result != "無結果"

        mem_id = ""
        if ok:
            try:
                import memory_bridge
                emo = self.psi.emotion.to_dict()
                importance = min(0.5, 0.25 + 0.25 * emo["arousal"])  # 自主寫入上限 0.5
                mem_id = memory_bridge.store_important(
                    f"[自主行動:{need}] 查詢「{prompt}」→\n{result[:500]}",
                    tags=["agency", need], importance=importance)
                self.psi.needs.satisfy_all({self._need_type(need): 0.2})
            except Exception as e:
                logger.warning(f"[Agency] 回寫失敗: {e}")

        self._action_ts.append(now)
        self._need_last_action[need] = now
        self.actions_total += 1
        self._audit({"ts": now, "need": need, "drive": round(drive, 3), "tool": tool,
                     "prompt": prompt, "ok": ok, "result_len": len(result or ""),
                     "mem_id": mem_id})
        logger.info(f"[Agency] 行動#{self.actions_total} {need}(drive={drive:.2f}) "
                    f"{tool}({prompt[:40]}) ok={ok} → mem={mem_id or '-'}")

    @staticmethod
    def _need_type(name: str):
        from laap.psi_core import NeedType
        return NeedType(name)

    @staticmethod
    def _audit(entry: dict) -> None:
        try:
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Agency] 審計寫入失敗: {e}")
