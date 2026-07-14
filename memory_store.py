"""
memory_store — top-level module for laap-AGI's bare import.

aris_cognitive_bridge.py / laap_integrator.py / state_snapshot.py do:
    from memory_store import MemoryStore, MemoryFragment

作者在 MemoryStore 實例上呼叫的方法（實測掃描）:
    store(fragment) / get(id) / get_stats() -> {'core','episodic',...}
    get_memory_embedding(query=, layer=, top_k=) -> 384-dim float32

Phase 1（gbrain 記憶後端）:
  - backend 由 NEURALIS_MEMORY_BACKEND 控制: auto（預設）| gbrain | local
  - auto/gbrain: store→gbrain put_page（laap/memory/<layer>/<id> 頁）、
    recall→gbrain search（全腦 1868+ 頁語意檢索）、get_stats→gbrain page_count、
    get_memory_embedding→檢索結果的 deterministic hash embedding（384-dim）
  - gbrain 不可用（binary 缺 / 呼叫失敗）→ 每次呼叫自動 fallback 到 in-process，
    作者端介面與行為不變。local 強制純 in-process（Phase 0 行為）。
"""
import hashlib
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("memory_store")

EMBED_DIM = 384  # 作者 get_memory_embedding 契約：384-dim float32

_GBRAIN_NS = "laap/memory"          # gbrain 頁面命名空間: laap/memory/<layer>/<id>
_STATS_TTL = 60.0                   # gbrain get_stats 快取（desire engine 每輪都問）


def _backend_mode() -> str:
    mode = os.environ.get("NEURALIS_MEMORY_BACKEND", "auto").lower()
    return mode if mode in ("auto", "gbrain", "local") else "auto"


def _gbrain():
    """回 gbrain client 或 None（不可用 / 強制 local）。import 放函式內避免循環。"""
    if _backend_mode() == "local":
        return None
    try:
        from gbrain_client import get_client
        return get_client()
    except Exception as e:
        logger.debug(f"[memory_store] gbrain client unavailable: {e}")
        return None


def emotion_intensity() -> float:
    """寫入當下的情緒強度 |valence|×arousal（Damasio somatic marker：情緒強的記憶
    該被記得更牢）。PsiCore 沒起就 0.0。固化循環用它做升層/保留判斷。
    ponytail: 檢索端 re-rank 未做（search hit 不帶 frontmatter，逐頁抓太慢）—
    目前情緒只影響寫入 importance 與固化決策。"""
    try:
        from laap.startup import get_psi_core
        psi = get_psi_core()
        if psi is not None:
            e = psi.emotion.to_dict()
            return round(abs(e["valence"]) * e["arousal"], 3)
    except Exception:
        pass
    return 0.0


def _hash_embed(text: str) -> np.ndarray:
    """Deterministic feature-hashing embedding（384-dim，L2 normalized）。
    中英混排：CJK 逐字 + 英數 token。同文字同向量；相近文字向量相近（詞袋級）。
    ponytail: 天花板是詞袋語意。升級路徑=gbrain 曝露原生向量後做 3072→384 投影。"""
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for tok in re.findall(r"[一-鿿]|[a-z0-9]+", text.lower()):
        idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % EMBED_DIM
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


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
    """階層記憶儲存（core / episodic）。gbrain 為真後端，in-process 為快取 + fallback。"""

    _stats_cache: Optional[Dict[str, int]] = None   # class-level：作者會 new 多個實例
    _stats_cache_at: float = 0.0
    _stats_lock = threading.Lock()

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._items: List[MemoryFragment] = []
        logger.info(f"[memory_store] 初始化 capacity={capacity} backend={_backend_mode()}")

    # ── store ──────────────────────────────────────────────────

    def store(self, fragment: MemoryFragment) -> str:
        if not fragment.id:
            digest = hashlib.md5(f"{fragment.content}:{fragment.ts}".encode()).hexdigest()[:6]
            fragment.id = f"mem-{int(fragment.ts)}-{digest}"
        # importance >= 0.7 視為核心記憶
        if fragment.layer == "episodic" and fragment.importance >= 0.7:
            fragment.layer = "core"
        self._store_local(fragment)
        client = _gbrain()
        if client is not None:
            try:
                client.call("put_page", {
                    "slug": f"{_GBRAIN_NS}/{fragment.layer}/{fragment.id}",
                    "content": self._to_markdown(fragment),
                }, timeout=30.0)
            except Exception as e:
                logger.warning(f"[memory_store] gbrain store 失敗（已存 in-process）: {e}")
        return fragment.id

    def _store_local(self, fragment: MemoryFragment) -> None:
        self._items.append(fragment)
        if len(self._items) > self.capacity:
            # 丟最舊的 episodic，保留 core
            for i, m in enumerate(self._items):
                if m.layer == "episodic":
                    self._items.pop(i)
                    break

    @staticmethod
    def _to_markdown(f: MemoryFragment) -> str:
        tags = ", ".join(f.tags) if f.tags else ""
        return (
            f"---\n"
            f"title: laap memory {f.id}\n"
            f"tags: [{tags}]\n"
            f"importance: {f.importance}\n"
            f"layer: {f.layer}\n"
            f"emotion_intensity: {emotion_intensity()}\n"
            f"source: laap-runtime\n"
            f"---\n\n"
            f"{f.content}\n"
        )

    # ── get / recall ───────────────────────────────────────────

    def get(self, mem_id: str) -> Optional[MemoryFragment]:
        return next((m for m in self._items if m.id == mem_id), None)

    def recall(self, query: str = "", top_k: int = 5, layer: Optional[str] = None) -> List[MemoryFragment]:
        local = self._recall_local(query, top_k, layer)
        if not query:
            # 無 query = 「最近/最重要」語意，本 session 的 in-process 快取就是對的來源
            return local
        client = _gbrain()
        if client is None:
            return local
        try:
            # hybrid（vec+lex→lex）降級檢索; 無 OPENAI_API_KEY 時 vec 退化只剩 lex
            from gbrain_client import hybrid_hits
            hits = hybrid_hits(client, query, max(top_k * 2, 10))
        except Exception as e:
            logger.warning(f"[memory_store] gbrain recall 失敗，用 in-process: {e}")
            return local
        remote = [self._hit_to_fragment(h) for h in hits]
        if layer is not None:
            remote = [f for f in remote if f.layer == layer]
        # 本 session 剛存的可能還沒進索引 → local 優先，slug/id 去重
        seen = {f.id for f in local}
        merged = local + [f for f in remote if f.id not in seen]
        return merged[:top_k]

    def _recall_local(self, query: str, top_k: int, layer: Optional[str]) -> List[MemoryFragment]:
        pool = [m for m in self._items if layer is None or m.layer == layer]
        if query:
            q = query.lower()
            pool = [m for m in pool if q in m.content.lower()]
            pool.sort(key=lambda m: (m.importance, m.ts), reverse=True)
        else:
            pool.sort(key=lambda m: (m.importance, m.ts), reverse=True)
        return pool[:top_k]

    @staticmethod
    def _hit_to_fragment(hit: Dict) -> MemoryFragment:
        slug = hit.get("slug", "")
        if slug.startswith(f"{_GBRAIN_NS}/"):
            mem_id = slug.rsplit("/", 1)[-1]
            layer = "core" if slug.startswith(f"{_GBRAIN_NS}/core/") else "episodic"
        else:
            # 腦庫既有知識頁 = 長期記憶 → core
            mem_id, layer = slug, "core"
        return MemoryFragment(
            id=mem_id,
            content=hit.get("chunk_text", "") or hit.get("title", ""),
            importance=min(1.0, float(hit.get("score", 0.5))),
            layer=layer,
        )

    # ── stats ──────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, int]:
        core = sum(1 for m in self._items if m.layer == "core")
        episodic = sum(1 for m in self._items if m.layer == "episodic")
        stats = {"core": core, "episodic": episodic, "working": 0, "total": len(self._items)}
        gbrain_pages = self._gbrain_page_count()
        if gbrain_pages is not None:
            stats["gbrain_pages"] = gbrain_pages
            stats["total"] += gbrain_pages
        return stats

    @classmethod
    def _gbrain_page_count(cls) -> Optional[int]:
        client = _gbrain()
        if client is None:
            return None
        with cls._stats_lock:
            now = time.time()
            if cls._stats_cache is not None and now - cls._stats_cache_at < _STATS_TTL:
                return cls._stats_cache
            try:
                stats = client.call("get_stats", {}, timeout=10.0)
                cls._stats_cache = int(stats.get("page_count", 0))
                cls._stats_cache_at = now
                return cls._stats_cache
            except Exception as e:
                logger.warning(f"[memory_store] gbrain get_stats 失敗: {e}")
                return cls._stats_cache  # 過期快取也比 None 好

    # ── embedding ──────────────────────────────────────────────

    def get_memory_embedding(self, query: str = "", layer: str = "core", top_k: int = 3) -> "np.ndarray":
        """檢索該層記憶 → deterministic hash embedding 加權平均（384-dim）。
        召回為空 → 零向量（作者端 np.linalg.norm<0.01 會自動降級到情景層，契約保留）。"""
        frags = self.recall(query=query, top_k=top_k, layer=layer)
        if not frags:
            return np.zeros(EMBED_DIM, dtype=np.float32)
        acc = np.zeros(EMBED_DIM, dtype=np.float32)
        for f in frags:
            acc += _hash_embed(f.content) * max(0.1, f.importance)
        norm = float(np.linalg.norm(acc))
        return acc / norm if norm > 0 else acc


# ── GBRAIN_BACKEND ─────────────────────────────────────────────
# Phase 1 已接上（見模組 docstring）。強制舊行為: NEURALIS_MEMORY_BACKEND=local

# /v1/recall_memory（laap_recall_memory tool）走作者的 laap_semantic_memory，
# 不走本模組 — 在這裡掛替身是因為 memory_store 是 boot 必經的 neuralis 模組。
if _backend_mode() != "local":
    try:
        from semantic_memory_gbrain import install as _install_semantic
        _install_semantic()
    except Exception as _e:  # 安裝失敗不影響 memory_store 本體
        logger.debug(f"[memory_store] semantic gbrain 掛載跳過: {_e}")
