"""
memory_store — top-level module for laap-AGI's bare import.

aris_cognitive_bridge.py / laap_integrator.py / state_snapshot.py do:
    from memory_store import MemoryStore, MemoryFragment

作者在 MemoryStore 實例上呼叫的方法（實測掃描）:
    store(fragment) / get(id) / get_stats() -> {'core','episodic',...}
    get_memory_embedding(query=, layer=, top_k=) -> 384-dim float32

這裡提供一個「同一 process 內真的存得回」的最小實作（非 stub），
分核心(core)/情景(episodic)兩層，足以讓認知橋接的記憶行為真的動起來。

gbrain seam: 把 MemoryStore 換成 gbrain 後端只需改 store/recall/get_stats/
get_memory_embedding 四個方法，介面不變。見檔尾 GBRAIN_BACKEND 說明。
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("memory_store")

EMBED_DIM = 384  # 作者 get_memory_embedding 契約：384-dim float32


@dataclass
class MemoryFragment:
    """記憶片段。作者以 r.content[:50] 取用，故 content 必為 str。"""
    id: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5
    layer: str = "episodic"  # 'core' | 'episodic'
    ts: float = field(default_factory=time.time)


class MemoryStore:
    """階層記憶儲存（core / episodic），in-process，可被 gbrain 後端替換。"""

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._items: List[MemoryFragment] = []
        logger.info(f"[memory_store] 初始化 capacity={capacity}")

    def store(self, fragment: MemoryFragment) -> str:
        if not fragment.id:
            fragment.id = f"mem_{len(self._items)}_{int(fragment.ts)}"
        # importance >= 0.7 視為核心記憶
        if fragment.layer == "episodic" and fragment.importance >= 0.7:
            fragment.layer = "core"
        self._items.append(fragment)
        if len(self._items) > self.capacity:
            # 丟最舊的 episodic，保留 core
            for i, m in enumerate(self._items):
                if m.layer == "episodic":
                    self._items.pop(i)
                    break
        return fragment.id

    def get(self, mem_id: str) -> Optional[MemoryFragment]:
        return next((m for m in self._items if m.id == mem_id), None)

    def recall(self, query: str = "", top_k: int = 5, layer: Optional[str] = None) -> List[MemoryFragment]:
        pool = [m for m in self._items if layer is None or m.layer == layer]
        if query:
            q = query.lower()
            pool.sort(key=lambda m: (q in m.content.lower(), m.importance, m.ts), reverse=True)
        else:
            pool.sort(key=lambda m: (m.importance, m.ts), reverse=True)
        return pool[:top_k]

    def get_stats(self) -> Dict[str, int]:
        core = sum(1 for m in self._items if m.layer == "core")
        episodic = sum(1 for m in self._items if m.layer == "episodic")
        return {"core": core, "episodic": episodic, "working": 0, "total": len(self._items)}

    def get_memory_embedding(self, query: str = "", layer: str = "core", top_k: int = 3) -> "np.ndarray":
        # 無真實向量後端時回傳零向量（作者端 np.linalg.norm<0.01 會自動降級到情景層）。
        # gbrain 後端接上後，這裡改為對 query 做 embed + 檢索平均。
        return np.zeros(EMBED_DIM, dtype=np.float32)


# ── GBRAIN_BACKEND 說明 ─────────────────────────────────────────────
# 要把記憶換成 gbrain（Postgres+pgvector，真正持久化 + 語意檢索）：
#   1. store()  -> mcp__gbrain__put_page / put_raw_data
#   2. recall() -> mcp__gbrain__search / query（回傳轉成 MemoryFragment）
#   3. get_memory_embedding() -> gbrain 的向量檢索平均
# 介面不變，作者端零改動。see docs/specs 的 gbrain 整合章節。
