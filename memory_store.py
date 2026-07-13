"""
memory_store — top-level stub for laap-AGI's bare import

aris_cognitive_bridge.py does:
    from memory_store import MemoryStore, MemoryFragment

This module provides those classes as stubs.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, List

logger = logging.getLogger("memory_store")


@dataclass
class MemoryFragment:
    """記憶片段"""
    id: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5


class MemoryStore:
    """記憶儲存"""

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        logger.info(f"[memory_store] stub 初始化, capacity={capacity}")

    def store(self, fragment: MemoryFragment) -> str:
        return fragment.id or "stub_id"

    def recall(self, tags: List[str], top_k: int = 5) -> List[MemoryFragment]:
        return []