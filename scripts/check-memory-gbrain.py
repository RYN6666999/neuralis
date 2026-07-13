#!/usr/bin/env python3
"""
Phase 1 自檢：memory_store 雙後端行為。

用法（從 neuralis 根）:
    python3 scripts/check-memory-gbrain.py            # 兩種後端都測
    NEURALIS_MEMORY_BACKEND=local python3 scripts/check-memory-gbrain.py   # 只測 local

驗證點:
  A. local 後端 = Phase 0 行為（store/recall/stats/零向量）
  B. gbrain 後端: store → 新實例 recall 得回（跨 process 持久的等價證明）
  C. get_memory_embedding: 有召回 → 非零向量; 空召回 → 零向量（降級契約）
  D. memory_bridge: store_important → recall_related 回 .content
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np


def check_local():
    os.environ["NEURALIS_MEMORY_BACKEND"] = "local"
    import importlib
    import memory_store
    importlib.reload(memory_store)
    from memory_store import MemoryStore, MemoryFragment, EMBED_DIM

    s = MemoryStore(capacity=10)
    mid = s.store(MemoryFragment(content="local check alpha", importance=0.8))
    assert s.get(mid) is not None
    assert s.get(mid).layer == "core", "importance>=0.7 應升 core"
    hits = s.recall("alpha", top_k=3)
    assert hits and hits[0].content == "local check alpha"
    st = s.get_stats()
    assert st["core"] == 1 and st["total"] == 1 and "gbrain_pages" not in st
    emb = s.get_memory_embedding(query="alpha", layer="core")
    assert emb.shape == (EMBED_DIM,) and np.linalg.norm(emb) > 0.01, "有召回應非零"
    emb2 = s.get_memory_embedding(query="zzz-no-match", layer="episodic")
    assert np.linalg.norm(emb2) < 0.01, "空召回應零向量（降級契約）"
    print("A. local backend: OK")


def check_gbrain():
    os.environ["NEURALIS_MEMORY_BACKEND"] = "auto"
    import importlib
    import memory_store
    importlib.reload(memory_store)
    from memory_store import MemoryStore, MemoryFragment
    from gbrain_client import get_client

    client = get_client()
    if client is None:
        print("B/C. gbrain backend: SKIP（binary 不存在）")
        return

    token = f"phase1-check-{int(time.time())}"
    s1 = MemoryStore()
    mid = s1.store(MemoryFragment(content=f"gbrain round-trip 記憶 {token}", importance=0.6))

    # 新實例 = 模擬重啟後的 process：in-process 快取為空，只能從 gbrain 撈回
    s2 = MemoryStore()
    hits = s2.recall(token, top_k=3)
    assert hits, f"gbrain recall 應找到 {token}"
    assert token in hits[0].content
    assert hits[0].layer == "episodic"

    st = s2.get_stats()
    assert st.get("gbrain_pages", 0) > 1000, f"應看到全腦頁數: {st}"

    emb = s2.get_memory_embedding(query=token, layer="episodic")
    assert np.linalg.norm(emb) > 0.01, "gbrain 召回後 embedding 應非零"

    client.call("delete_page", {"slug": f"laap/memory/episodic/{mid}"})
    print(f"B/C. gbrain backend: OK（round-trip via 新實例, stats={st['gbrain_pages']} pages）")


def check_bridge():
    import memory_bridge
    mid = memory_bridge.store_important("bridge check gamma", tags=["check"], importance=0.4)
    rel = memory_bridge.recall_related("gamma", top_k=2)
    assert rel and hasattr(rel[0], "content"), "recall_related 必須回有 .content 的物件"
    ctx = memory_bridge.get_memory_context()
    assert isinstance(ctx, str)
    # 清掉自檢寫進 gbrain 的頁（local 模式下 client=None，no-op）
    from gbrain_client import get_client
    client = get_client()
    if client is not None and os.environ.get("NEURALIS_MEMORY_BACKEND", "auto") != "local":
        try:
            client.call("delete_page", {"slug": f"laap/memory/episodic/{mid}"})
        except Exception:
            pass
    print("D. memory_bridge: OK")


if __name__ == "__main__":
    forced_local = os.environ.get("NEURALIS_MEMORY_BACKEND", "auto") == "local"
    check_local()
    if not forced_local:
        check_gbrain()
    check_bridge()
    print("ALL CHECKS PASSED")
