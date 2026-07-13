"""
memory_bridge — top-level stub for laap-AGI's bare import

aris_cognitive_bridge.py does:
    from memory_bridge import get_memory_context, recall_related, store_important

This module provides those functions as stubs.
"""
import logging
from typing import Any, List

logger = logging.getLogger("memory_bridge")


def get_memory_context(query: str, limit: int = 5) -> List[dict]:
    """獲取與查詢相關的記憶上下文"""
    logger.debug(f"[memory_bridge] get_memory_context stub: query={query[:40]}")
    return []


def recall_related(tags: List[str], top_k: int = 5) -> List[dict]:
    """回憶相關記憶片段"""
    logger.debug(f"[memory_bridge] recall_related stub: tags={tags}")
    return []


def store_important(content: str, tags: List[str], importance: float = 0.5) -> str:
    """儲存重要記憶"""
    logger.debug(f"[memory_bridge] store_important stub: content={content[:40]}")
    return "stub_memory_id"