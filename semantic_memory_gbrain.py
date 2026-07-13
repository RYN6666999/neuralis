"""
semantic_memory_gbrain — 把 laap_semantic_memory 的後端換成 gbrain。

背景：`/v1/recall_memory`（= scream-code 的 laap_recall_memory tool）與 reflect
的記憶持久化走的是作者的 `laap_semantic_memory`（JSON/Chroma 後端），不是
memory_store。作者模組有 lazy singleton（`get_memory()` / `_MEMORY`），
這裡提供 duck-typed 替身 + `install()` 換掉 singleton — 作者檔零改動。

觸發點：memory_store.py 檔尾（boot 時必被 import）。
NEURALIS_MEMORY_BACKEND=local 時不安裝，保留 Phase 0 行為。
gbrain 呼叫失敗時，逐呼叫 fallback 到作者原版 LaapSemanticMemory（lazy 建立，
避免 boot 時就做 embedding provider 探測）。
"""
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("semantic_memory_gbrain")

_NS = "laap/memory/episodic"  # semantic memory 全存情景層（作者無 layer 概念）


class GbrainSemanticMemory:
    """LaapSemanticMemory 的 duck-typed 替身：add / recall / list_all。"""

    def __init__(self, original_factory):
        self._original_factory = original_factory  # () -> LaapSemanticMemory
        self._original = None

    def _fallback(self):
        if self._original is None:
            self._original = self._original_factory()
        return self._original

    def _client(self):
        from gbrain_client import get_client
        return get_client()

    # ── LaapSemanticMemory 介面 ────────────────────────────────

    def add(self, text: str, meta: Optional[Dict] = None) -> str:
        client = self._client()
        if client is None:
            return self._fallback().add(text, meta)
        ts = time.time()
        mem_id = f"mem-{int(ts)}-{hashlib.md5(f'{text}:{ts}'.encode()).hexdigest()[:6]}"
        meta_type = (meta or {}).get("type", "")
        content = (
            f"---\n"
            f"title: laap memory {mem_id}\n"
            f"layer: episodic\n"
            f"source: laap-semantic\n"
            f"meta_type: {meta_type}\n"
            f"---\n\n"
            f"{text}\n"
        )
        try:
            client.call("put_page", {"slug": f"{_NS}/{mem_id}", "content": content}, timeout=30.0)
            return mem_id
        except Exception as e:
            logger.warning(f"[semantic_gbrain] add 失敗，退作者原版: {e}")
            return self._fallback().add(text, meta)

    def recall(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict]:
        client = self._client()
        if client is None:
            return self._fallback().recall(query, top_k, min_score)
        try:
            from gbrain_client import hybrid_hits
            hits = hybrid_hits(client, query, max(top_k * 2, 10))
        except Exception as e:
            logger.warning(f"[semantic_gbrain] recall 失敗，退作者原版: {e}")
            return self._fallback().recall(query, top_k, min_score)
        results = []
        for h in hits:
            score = round(float(h.get("score", 0.0)), 4)
            if score < min_score:
                continue
            results.append({
                "id": h.get("slug", ""),
                "text": h.get("chunk_text", "") or h.get("title", ""),
                "timestamp": "",  # gbrain search hit 不帶時間; 要精確時間得另 get_page
                "score": score,
                "meta": {"source": "gbrain"},
            })
        return results[:top_k]

    def list_all(self, limit: int = 100) -> List[Dict]:
        client = self._client()
        if client is None:
            return self._fallback().list_all(limit)
        try:
            pages = client.call("list_pages", {"limit": 100})
        except Exception as e:
            logger.warning(f"[semantic_gbrain] list_all 失敗，退作者原版: {e}")
            return self._fallback().list_all(limit)
        items = [
            {"id": p["slug"], "text": p.get("title", ""), "timestamp": p.get("updated_at", "")}
            for p in pages if p.get("slug", "").startswith("laap/memory/")
        ]
        return items[:limit]


def install() -> bool:
    """把 laap_semantic_memory 的 singleton 換成 gbrain 替身。回傳是否安裝成功。"""
    try:
        import laap_semantic_memory as sem
    except ImportError:
        return False  # 不在 laap-AGI 環境（例如單獨跑 neuralis 測試），沒東西可換
    if isinstance(getattr(sem, "_MEMORY", None), GbrainSemanticMemory):
        return True  # 已安裝，冪等
    original_cls = sem.LaapSemanticMemory
    sem._MEMORY = GbrainSemanticMemory(original_factory=lambda: original_cls())
    logger.info("[semantic_gbrain] laap_semantic_memory singleton → gbrain 後端")
    return True
