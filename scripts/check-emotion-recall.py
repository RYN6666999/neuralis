#!/usr/bin/env python3
"""Phase 5 補完自檢：檢索端情緒加權（emotion re-rank）。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-emotion-recall.py

exit code（三態，見 scripts/_check_verdict.py）:
    0 = 驗過且都好      1 = 驗過，有壞的      2 = 沒驗到（gbrain 不在）

2026-08-21 修：舊版 module 層 `assert client is not None` → gbrain 不在時
AssertionError + traceback + exit 1。「後端沒裝」被報成「情緒加權壞了」，
那是假紅（guard.yml：假紅比沒有更糟）。四段都要寫真頁再讀回，
所以沒有 gbrain 時正確答案是 exit 2。

2026-08-21 再修（p3c）：段內原本是裸 `assert`，所以「gbrain 在場但斷言失敗」
會 traceback + exit 1 且**沒有 CHECK-VERDICT 標記行** —— 繞過 Verdict。
那讓一個**真陽性**看起來像「腳本自己壞了」，跟本檔上一輪修掉的假紅同型，
只是換到斷言失敗這條路上。真問題應該長成 `❌ FAIL` + 標記行 + exit 1，
讀的人才分得出「產品有問題」與「工具有問題」。
**斷言的判定內容一字未改，只改它失敗時的呈現方式。**"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _check_verdict import Verdict, guard   # noqa: E402

from memory_store import _emotion_rerank, _emotion_intensity_for, _emotion_cache
from gbrain_client import get_client

_V = Verdict("emotion-recall")
client = get_client()
if client is None:
    _V.unknown("A-D. 檢索端情緒加權",
               "gbrain 不可用 —— 情緒強度讀取／re-rank 排序／快取／recall 端到端 "
               "四段都沒驗到。需要真後端的機器")
    _V.finish()

TS = int(time.time())
LO = f"laap/memory/episodic/emo-lo-{TS}"
HI = f"laap/memory/episodic/emo-hi-{TS}"


def put(slug, emo):
    mid = slug.rsplit("/", 1)[-1]
    client.call("put_page", {"slug": slug, "content": (
        f"---\ntitle: laap memory {mid}\nimportance: 0.5\nlayer: episodic\n"
        f"emotion_intensity: {emo}\nsource: check\n---\n\nemotion recall check {TS}\n"
    )}, timeout=30.0)


def seg_a():
    """情緒讀取：laap 頁抓得到、非 laap 頁回 0。"""
    assert _emotion_intensity_for(client, HI) == 0.9, "應讀到 emotion_intensity"
    assert _emotion_intensity_for(client, "log/2026-07-14-laap-neuralis-scream") == 0.0, \
        "非 laap slug 應回 0（不查 frontmatter）"
    _V.ok("A. emotion 讀取 + namespace 隔離")


def seg_b():
    """re-rank：base 較低的高情緒頁應翻到前面。
    lo: 0.80×(1+0.3×0)=0.80 ; hi: 0.75×(1+0.3×0.9)=0.9525 → hi 勝"""
    hits = [{"slug": LO, "score": 0.80}, {"slug": HI, "score": 0.75}]
    ranked = _emotion_rerank(client, hits)
    assert ranked[0]["slug"] == HI, f"高情緒應排前，實際 {[h['slug'] for h in ranked]}"
    _V.ok("B. 情緒加權翻轉排序",
          f"hi adj={ranked[0]['_score_adj']:.3f} > lo adj={ranked[1]['_score_adj']:.3f}")


def seg_c():
    """穩定性：emotion 全 0 時順序不變（全腦頁不受影響）。"""
    flat = [{"slug": "wiki/a", "score": 0.9}, {"slug": "wiki/b", "score": 0.8}]
    assert [h["slug"] for h in _emotion_rerank(client, flat)] == ["wiki/a", "wiki/b"], \
        "emotion=0 應保持原序"
    _V.ok("C. 全腦頁（emotion=0）排序不變")


def seg_d():
    """端到端：recall 走 re-rank 不炸、回結果。"""
    from memory_store import MemoryStore
    frags = MemoryStore().recall(f"emotion recall check {TS}", top_k=5)
    assert frags, "recall 應回結果"
    _V.ok("D. recall 端到端", f"{len(frags)} 條")


try:
    # 寫入自檢頁本身失敗 = gbrain 在場但不能用 → 那是真問題（fail），
    # 不是「沒驗到」：binary 在、呼叫卻壞，正是這支要抓的東西。
    with guard(_V, "前置：寫入自檢頁"):
        put(LO, 0.0)
        put(HI, 0.9)
        _emotion_cache.clear()

    # 段落隔離：一段失敗只讓那段紅，其餘照跑（舊版是一個大 try，
    # 第一個 assert 就帶走後面全部，而且沒有標記行）。
    for label, fn in (("A", seg_a), ("B", seg_b), ("C", seg_c), ("D", seg_d)):
        with guard(_V, f"{label} 段"):
            fn()
finally:
    for slug in (LO, HI):
        try:
            client.call("delete_page", {"slug": slug})
        except Exception:
            pass
_V.finish()
