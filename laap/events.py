"""
events — Agency loop 事件基礎設施（Phase 1 里程碑）。

event-driven agent loop 的地基。所有外掛（gbrain 固化、affective 訂閱、
三繩 advisor、stream rule）都透過 subscribe/emit 掛進來。

核心設計原則：
  1. emit() 永遠不拋例外 — 訂閱者壞了不影響 agency 主迴路
  2. 模組不存在時 emit() 自動 no-op — 改造一回退時刪 events.py 即安全
  3. 執行緒安全 — LockGuard 保護訂閱者列表
  4. zero 外部依賴 — 不 import agency/affective 等（防循環 import）
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger("laap.events")

# ── 事件類型常數 ──

AGENCY_TURN_START = "agency_turn_start"       # _act 進入時
AGENCY_TOOL_RESULT = "agency_tool_result"      # tools.execute 返回後
AGENCY_TURN_END = "agency_turn_end"            # _act 結束時（含完整 entry dict）

# ── 內部狀態 ──

_subscribers: dict[str, list[Callable]] = {}
_lock = threading.Lock()
_disabled = False  # 關閉開關（用於回退 / 測試）


# ── 公開 API ──


def emit(event_type: str, source: str = "agency", **data: Any) -> None:
    """發射事件給所有訂閱者。永遠安全 — 訂閱者壞了不影響呼叫端。"""
    if _disabled:
        return
    subs = _subscribers.get(event_type, ())
    if not subs:
        return
    payload = {"type": event_type, "source": source, "data": data}
    for cb in list(subs):
        try:
            cb(payload)
        except Exception:
            logger.debug(f"[events] 訂閱者失敗 {event_type}:", exc_info=True)


def subscribe(event_type: str, callback: Callable) -> Callable:
    """訂閱事件。回傳可呼叫的 unsubscribe。"""
    with _lock:
        _subscribers.setdefault(event_type, []).append(callback)
    logger.debug(f"[events] 訂閱 {event_type}")
    return lambda: _unsubscribe_one(event_type, callback)


def unsubscribe(event_type: str, callback: Callable) -> None:
    _unsubscribe_one(event_type, callback)


def _unsubscribe_one(event_type: str, callback: Callable) -> None:
    with _lock:
        subs = _subscribers.get(event_type)
        if subs:
            try:
                subs.remove(callback)
            except ValueError:
                pass


def disable() -> None:
    """關閉事件系統（回退模式 / 測試用）。emit() 變 no-op。"""
    global _disabled
    _disabled = True


def enable() -> None:
    global _disabled
    _disabled = False


def list_subscribers() -> dict[str, int]:
    """回 {事件類型: 訂閱者數}，供 debug 用。"""
    with _lock:
        return {k: len(v) for k, v in _subscribers.items()}


def _reset() -> None:
    """測試用：清除所有訂閱者 + 啟用。"""
    global _disabled
    with _lock:
        _subscribers.clear()
    _disabled = False