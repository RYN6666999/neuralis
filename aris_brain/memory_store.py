"""
Stub: MemoryStore — 階層式記憶儲存（neuralis 擴充）
被 aris_brain 的記憶系統使用
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aris_brain.memory_store")


@dataclass
class MemoryFragment:
    """記憶片段 — 最小的可召回單元"""
    id: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5
    timestamp: float = 0.0
    source: str = ""


class MemoryStore:
    """階層記憶儲存 — 工作記憶 / 最近記憶 / 長期記憶三層

    這是 neuralis 對 laap-AGI 記憶系統的擴充實作。
    """

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._working: List[MemoryFragment] = []
        self._recent: List[MemoryFragment] = []
        self._long_term: List[MemoryFragment] = []
        logger.info(f"[MemoryStore] stub 初始化, capacity={capacity}")

    def store(self, fragment: MemoryFragment) -> str:
        self._working.append(fragment)
        if len(self._working) > self.capacity // 10:
            self._consolidate()
        return fragment.id or f"mem_{len(self._working)}"

    def recall(self, query: str, top_k: int = 5) -> List[MemoryFragment]:
        return self._working[:top_k] + self._recent[:top_k]

    def _consolidate(self) -> None:
        """工作記憶 → 最近記憶的壓縮"""
        self._recent.extend(self._working[-10:])
        self._working.clear()

    def clear(self) -> None:
        self._working.clear()
        self._recent.clear()
        self._long_term.clear()