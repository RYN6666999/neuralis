"""
memory_bridge — top-level module for laap-AGI's bare import.

aris_cognitive_bridge.py does:
    from memory_bridge import get_memory_context, recall_related, store_important

作者的實際呼叫方式（實測）:
    recall_related(user_message: str, top_k=2)        -> 物件序列，取 r.content
    get_memory_context(max_core=3, max_recent=3, max_working=2) -> str/序列
    store_important(content, tags, importance)         -> id

三個函式共用 memory_store 的單例，讓「存進去 → 之後召回」在同一 process 內真的成立。
"""
import logging
from typing import List, Union

from memory_store import MemoryStore, MemoryFragment

logger = logging.getLogger("memory_bridge")

# 共用單例：store_important 寫進去的東西，recall_related / get_memory_context 讀得到
_STORE = MemoryStore(capacity=1000)


def store_important(content: str, tags: Union[List[str], None] = None, importance: float = 0.5) -> str:
    frag = MemoryFragment(content=content, tags=list(tags or []), importance=importance)
    mem_id = _STORE.store(frag)
    logger.debug(f"[memory_bridge] store_important -> {mem_id}")
    return mem_id


def recall_related(query: str, top_k: int = 5) -> List[MemoryFragment]:
    """作者做 r.content[:50]，故回傳有 .content 的 MemoryFragment 序列。"""
    _feed_psi(query)
    return _STORE.recall(query=query, top_k=top_k)


def _feed_psi(user_message: str) -> None:
    """把使用者輸入餵進 PsiCore 需求偵測。作者的 _perceive 每輪呼叫 recall_related，
    這裡是 overlay 能掛到「每輪對話」的最近點。PsiCore 沒起（get 回 None）就 no-op —
    絕不因心臟缺席擋記憶召回。"""
    try:
        from laap.startup import get_psi_core
        psi = get_psi_core()
        if psi is not None:
            psi.process_input(user_message)
    except Exception as e:
        logger.debug(f"[memory_bridge] psi feed 跳過: {e}")


def get_memory_context(max_core: int = 3, max_recent: int = 3, max_working: int = 2) -> str:
    """作者以 max_core/max_recent/max_working kwargs 呼叫；回傳可拼進 prompt 的字串。"""
    core = _STORE.recall(top_k=max_core, layer="core")
    recent = _STORE.recall(top_k=max_recent, layer="episodic")
    parts = [f"[核心] {m.content}" for m in core] + [f"[近期] {m.content}" for m in recent]
    return "\n".join(parts)
