#!/usr/bin/env python3
"""Phase 5 補完自檢：檢索端情緒加權（emotion re-rank）。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-emotion-recall.py"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory_store import _emotion_rerank, _emotion_intensity_for, _emotion_cache
from gbrain_client import get_client

client = get_client()
assert client is not None, "此自檢需要 gbrain"

TS = int(time.time())
LO = f"laap/memory/episodic/emo-lo-{TS}"
HI = f"laap/memory/episodic/emo-hi-{TS}"


def put(slug, emo):
    mid = slug.rsplit("/", 1)[-1]
    client.call("put_page", {"slug": slug, "content": (
        f"---\ntitle: laap memory {mid}\nimportance: 0.5\nlayer: episodic\n"
        f"emotion_intensity: {emo}\nsource: check\n---\n\nemotion recall check {TS}\n"
    )}, timeout=30.0)


try:
    put(LO, 0.0)
    put(HI, 0.9)
    _emotion_cache.clear()

    # A. 情緒讀取：laap 頁抓得到、非 laap 頁回 0
    assert _emotion_intensity_for(client, HI) == 0.9, "應讀到 emotion_intensity"
    assert _emotion_intensity_for(client, "log/2026-07-14-laap-neuralis-scream") == 0.0, \
        "非 laap slug 應回 0（不查 frontmatter）"
    print("A. emotion 讀取 + namespace 隔離: OK")

    # B. re-rank：base 較低的高情緒頁應翻到前面
    #    lo: 0.80×(1+0.3×0)=0.80 ; hi: 0.75×(1+0.3×0.9)=0.9525 → hi 勝
    hits = [{"slug": LO, "score": 0.80}, {"slug": HI, "score": 0.75}]
    ranked = _emotion_rerank(client, hits)
    assert ranked[0]["slug"] == HI, f"高情緒應排前，實際 {[h['slug'] for h in ranked]}"
    print(f"B. 情緒加權翻轉排序: OK — hi adj={ranked[0]['_score_adj']:.3f} "
          f"> lo adj={ranked[1]['_score_adj']:.3f}")

    # C. 穩定性：emotion 全 0 時順序不變（全腦頁不受影響）
    flat = [{"slug": "wiki/a", "score": 0.9}, {"slug": "wiki/b", "score": 0.8}]
    assert [h["slug"] for h in _emotion_rerank(client, flat)] == ["wiki/a", "wiki/b"], \
        "emotion=0 應保持原序"
    print("C. 全腦頁（emotion=0）排序不變: OK")

    # D. 端到端：recall 走 re-rank 不炸、回結果
    from memory_store import MemoryStore
    frags = MemoryStore().recall(f"emotion recall check {TS}", top_k=5)
    assert frags, "recall 應回結果"
    print(f"D. recall 端到端: OK — {len(frags)} 條")

    print("ALL EMOTION-RECALL CHECKS PASSED")
finally:
    for slug in (LO, HI):
        try:
            client.call("delete_page", {"slug": slug})
        except Exception:
            pass
