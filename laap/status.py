"""
StatusWriter — 產品向可觀測層：把三迴路即時狀態寫成 status.json。

系統自己在跑（心跳/agency/consolidation），狀態全在 API process 記憶體裡，
外部看不見。這個模組定期把快照寫檔（同作者 state/latest.json 的 overlay 模式），
`scripts/aris-status.py` 讀它 → 人類可讀狀態。不碰作者碼。

snapshot() 是純函式（收集各迴路 getter），可單獨測。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("laap.status")

STATUS_PATH = Path(__file__).resolve().parents[1] / "status.json"


def snapshot() -> dict:
    """收集三迴路 + 記憶分層的即時狀態。任一迴路沒起 → 該段回 None，不炸。"""
    from laap.startup import get_psi_core, get_agency, get_consolidation

    out: dict = {"ts": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S")}

    psi = get_psi_core()
    if psi is not None:
        try:
            st = psi.get_state()
            out["psi"] = {
                "tick": st["tick"],
                "dominant_need": st["dominant_need"],
                "dominant_drive": st["dominant_drive"],
                "emotion": st["emotion"],
                "attention": st["attention"],
                "last_input": (getattr(psi, "last_input", "") or "")[:80],
            }
        except Exception as e:
            out["psi"] = {"error": str(e)}

    agency = get_agency()
    if agency is not None:
        out["agency"] = {
            "actions_total": agency.actions_total,
            "interval_s": agency.interval,
            "max_per_hour": agency.max_per_hour,
            "drive_threshold": agency.drive_threshold,
            "actions_last_hour": len(getattr(agency, "_action_ts", [])),
        }

    cons = get_consolidation()
    if cons is not None:
        out["consolidation"] = {
            "passes_total": cons.passes_total,
            "interval_s": cons.interval,
            "idle_s": cons.idle_s,
            "seconds_since_interaction": round(time.time() - cons._last_interaction, 1),
            "asleep": cons._asleep(),
        }

    out["memory"] = _memory_breakdown()
    return out


def _memory_breakdown() -> dict:
    """gbrain 記憶分層頁數（laap/memory/{episodic,core,archive}）+ 全腦總數。"""
    try:
        from gbrain_client import get_client
        client = get_client()
        if client is None:
            return {"error": "gbrain 不可用"}
        stats = client.call("get_stats", {}, timeout=10.0)
        pages = client.call("list_pages", {"limit": 100})
        layers = {"episodic": 0, "core": 0, "archive": 0}
        for p in pages:
            slug = p.get("slug", "")
            for layer in layers:
                if slug.startswith(f"laap/memory/{layer}/"):
                    layers[layer] += 1
        return {"gbrain_total": stats.get("page_count", 0), "laap_layers": layers}
    except Exception as e:
        return {"error": str(e)}


class StatusWriter:
    """背景執行緒：每 interval 秒寫一次 status.json。"""

    def __init__(self, interval: float = 30.0):
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._write_once()  # boot 即寫一次，別讓首個 30s 空窗
        logger.info(f"[Status] writer 啟動 → {STATUS_PATH.name} (每 {self.interval}s)")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            time.sleep(self.interval)
            self._write_once()

    def _write_once(self) -> None:
        try:
            STATUS_PATH.write_text(
                json.dumps(snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[Status] 寫入失敗: {e}")
