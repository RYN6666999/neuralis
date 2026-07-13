"""
Stub: MemoryBridge — 記憶橋接（連接 laap-AGI 記憶系統與 neuralis MemoryStore）
被 aris_brain 模組使用
"""
import logging
from typing import Any, Dict, List, Optional

from aris_brain.memory_store import MemoryFragment, MemoryStore

logger = logging.getLogger("aris_brain.memory_bridge")


class MemoryBridge:
    """記憶橋接 — 從 CognitiveBus 事件自動存入重要記憶"""

    def __init__(self, store: Optional[MemoryStore] = None):
        self.store = store or MemoryStore()
        logger.info("[MemoryBridge] stub 初始化")

    def on_conscious_frame(self, source: str, data: dict) -> None:
        """CognitiveBus CONSCIOUS_FRAME 回呼 — 自動記憶"""
        snapshot = data.get("snapshot", {})
        narrative = snapshot.get("narrative", "")
        if narrative:
            fragment = MemoryFragment(
                content=narrative[:200],
                tags=["conscious_frame", source],
                importance=0.5,
            )
            self.store.store(fragment)

    def get_context(self, query: str, limit: int = 5) -> List[MemoryFragment]:
        return self.store.recall(query, top_k=limit)