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

exit code（三態，見 scripts/_check_verdict.py）:
    0 = 驗過且都好          1 = 驗過，有壞的          2 = 沒驗到（gbrain 不在）

2026-08-21 修：舊版在 gbrain binary 不存在時印一行 `SKIP` 然後照樣印
`ALL CHECKS PASSED` exit 0 —— 本檔 docstring 自稱驗證「gbrain 後端 store →
新實例 recall」，而那段一行都沒跑。同一個病 `brain/drift.py` 修過一次
（上游 404 印成「✅ 全部同步」）。B/C 段是這支存在的主要理由，它沒驗到時
對外訊號不能跟「驗過而且好」一樣。
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from _check_verdict import Verdict, guard


def check_local(v: Verdict):
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
    v.ok("A. local backend")


def check_gbrain(v: Verdict):
    """B/C 段。gbrain 不在 = **沒驗到**（exit 2），不是通過。

    在時則必須真的驗：store → 新實例 recall。gbrain 存在但呼叫失敗是
    `fail`（真問題），不是 unknown —— 「它壞了」跟「它不在」的正確行動不同。
    """
    os.environ["NEURALIS_MEMORY_BACKEND"] = "auto"
    import importlib
    import memory_store
    importlib.reload(memory_store)
    from memory_store import MemoryStore, MemoryFragment
    from gbrain_client import get_client, GbrainError

    client = get_client()
    if client is None:
        v.unknown("B/C. gbrain 後端 round-trip",
                  "gbrain binary 不存在 —— 本檔 docstring 承諾的「store → 新實例 "
                  "recall」這段一行都沒跑。需要有 gbrain 的機器才驗得到")
        return

    # binary 在 → 這段必須真的通。以下任一步失敗都是 fail（不是 unknown）：
    # 依賴在場而行為錯誤，就是這支腳本要抓的東西。
    token = f"phase1-check-{int(time.time())}"
    try:
        s1 = MemoryStore()
        mid = s1.store(MemoryFragment(content=f"gbrain round-trip 記憶 {token}",
                                      importance=0.6))
        # 新實例 = 模擬重啟後的 process：in-process 快取為空，只能從 gbrain 撈回
        s2 = MemoryStore()
        hits = s2.recall(token, top_k=3)
    except GbrainError as e:
        v.fail("B/C. gbrain 後端 round-trip",
               f"binary 在但呼叫失敗 —— 後端壞了，不是「沒裝」: {e}")
        return

    if not hits:
        v.fail("B/C. gbrain 後端 round-trip",
               f"新實例 recall 找不到 {token} —— 跨 process 持久性沒成立")
        return
    if token not in hits[0].content:
        v.fail("B/C. gbrain 後端 round-trip", f"recall 回了別的東西: {hits[0].content[:80]!r}")
        return
    if hits[0].layer != "episodic":
        v.fail("B/C. gbrain 後端 round-trip", f"layer 應為 episodic，得到 {hits[0].layer}")
        return

    st = s2.get_stats()
    if st.get("gbrain_pages", 0) <= 1000:
        v.fail("B/C. gbrain 全腦頁數", f"應看到全腦頁數，得到 {st}")
        return

    emb = s2.get_memory_embedding(query=token, layer="episodic")
    if np.linalg.norm(emb) <= 0.01:
        v.fail("B/C. gbrain 召回後 embedding", "召回有內容卻拿到零向量")
        return

    try:
        client.call("delete_page", {"slug": f"{'laap/memory/episodic'}/{mid}"})
    except GbrainError as e:
        v.warn("B/C. 自檢頁清理失敗（不影響結論）", str(e))
    v.ok("B/C. gbrain 後端 round-trip",
         f"新實例 recall 得回, stats={st['gbrain_pages']} pages")


def check_bridge(v: Verdict):
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
    v.ok("D. memory_bridge")


def main() -> None:
    forced_local = os.environ.get("NEURALIS_MEMORY_BACKEND", "auto") == "local"
    v = Verdict("memory-gbrain")

    with guard(v, "A. local backend"):
        check_local(v)

    if forced_local:
        # 明示 local 模式：gbrain 段是**刻意**沒驗，但仍然是沒驗。
        # 不算失敗（使用者自己選的），但不准讓摘要看起來像 gbrain 驗過了。
        v.unknown("B/C. gbrain 後端 round-trip",
                  "NEURALIS_MEMORY_BACKEND=local —— 刻意只驗 local，"
                  "gbrain 後端這次沒驗")
    else:
        with guard(v, "B/C. gbrain 後端"):
            check_gbrain(v)

    with guard(v, "D. memory_bridge"):
        check_bridge(v)

    v.finish()


if __name__ == "__main__":
    main()
