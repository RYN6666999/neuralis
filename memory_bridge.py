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


def store_important(content: str, tags: Union[List[str], None] = None, importance: float = 0.5,
                    mem_type: str = "episodic", provenance: str = "", status: str = "provisional") -> str:
    """儲存重要記憶。新參數向後相容：不傳 = 預設 episodic/provisional。

    OpenSpace-inspired:
      mem_type  — user/feedback/project/reference/episodic
      status    — provisional（新記憶預設）/ trusted（寫入閘自動升）
      provenance— 來源標記：chatflow / agency / scream-bridge
    """
    frag = MemoryFragment(content=content, tags=list(tags or []), importance=importance,
                          mem_type=mem_type, provenance=provenance, status=status)
    mem_id = _STORE.store(frag)
    logger.debug(f"[memory_bridge] store_important -> {mem_id} type={mem_type} status={status}")
    return mem_id


def recall_related(query: str, top_k: int = 5, mem_type: Optional[str] = None,
                   status: Optional[str] = None) -> List[MemoryFragment]:
    """作者做 r.content[:50]，故回傳有 .content 的 MemoryFragment 序列。

    OpenSpace-inspired 新參數：
        mem_type — user/feedback/project/reference 過濾
        status   — provisional/trusted 過濾
    """
    _feed_psi(query)
    if mem_type or status:
        return _STORE.structured_recall(query=query, top_k=top_k,
                                        include_types={mem_type} if mem_type else None,
                                        status_filter=status)
    return _STORE.recall(query=query, top_k=top_k)


def _feed_psi(user_message: str) -> None:
    """把使用者輸入餵進 PsiCore 需求偵測。作者的 _perceive 每輪呼叫 recall_related，
    這裡是 overlay 能掛到「每輪對話」的最近點。PsiCore 沒起（get 回 None）就 no-op —
    絕不因心臟缺席擋記憶召回。"""
    try:
        from laap.startup import get_psi_core, get_consolidation
        psi = get_psi_core()
        if psi is not None:
            psi.process_input(user_message)
        cons = get_consolidation()
        if cons is not None:
            cons.note_interaction()  # 有互動 → 重置睡眠窗（不在對話中打掃）
    except Exception as e:
        logger.debug(f"[memory_bridge] psi feed 跳過: {e}")


def get_memory_context(max_core: int = 3, max_recent: int = 3, max_working: int = 2) -> str:
    """作者以 max_core/max_recent/max_working kwargs 呼叫；回傳可拼進 prompt 的字串。

    OpenSpace-inspired：輸出依類型分組，讓 LLM 能區分不同種類的記憶。
    """
    core = _STORE.recall(top_k=max_core, layer="core")
    recent = _STORE.recall(top_k=max_recent, layer="episodic")
    # 依類型分組
    by_type: dict = {}
    for m in core + recent:
        t = m.mem_type if hasattr(m, 'mem_type') else "episodic"
        by_type.setdefault(t, []).append(m.content)
    parts = []
    for t in ["user", "feedback", "project", "reference", "episodic"]:
        if t in by_type:
            for c in by_type[t]:
                parts.append(f"[{t}] {c}")
    return "\n".join(parts)
