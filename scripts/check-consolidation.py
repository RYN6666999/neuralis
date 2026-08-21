#!/usr/bin/env python3
"""
Phase 5 自檢：記憶固化全鏈路（去重合併 / 情緒升層 / 睡眠窗 / namespace 硬邊界）。

用法（從 neuralis 根，需 gbrain 可用）:
    PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-consolidation.py

exit code（三態，見 scripts/_check_verdict.py）:
    0 = 驗過且都好      1 = 驗過，有壞的      2 = 沒驗到（gbrain 不在）

2026-08-21 修：舊版是 module 層 `assert client is not None` —— gbrain 不在時
丟 AssertionError + traceback、exit 1。**「後端沒裝」被報成「固化鏈路壞了」。**
那是 guard.yml 明文警告的假紅（假紅比沒有更糟，人會學會無視紅燈），而且
traceback 讓它看起來像腳本自己壞了。這支**整支**都需要真 gbrain，所以
沒有 gbrain 時正確答案是 exit 2（沒驗到），不是 exit 1。

2026-08-21 再修（p3c）：段內原本是裸 `assert`，所以「gbrain 在場但斷言失敗」
會 traceback + exit 1 且**沒有 CHECK-VERDICT 標記行**。
Ryan 機器上實測就是走這條：`C. pass 統計` 的 `promoted=0` 是**真陽性**
（A/B/C 三段都跑通、scanned 12/15 資料在動），但它長成 traceback，
看起來像「腳本自己壞了」而不是「固化邏輯有問題」。
真問題應該長成 `❌ FAIL` + 標記行 + exit 1，讀的人才分得出產品問題與工具問題。
**斷言的判定內容一字未改** —— `promoted >= 2` 仍然會失敗，exit 仍然是 1。
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _check_verdict import Verdict, guard   # noqa: E402

from laap.consolidation import ConsolidationLoop
from gbrain_client import get_client

_V = Verdict("consolidation")
client = get_client()
if client is None:
    # 整支自檢的每一段都要寫進真 gbrain 再讀回來，沒有後端就一段都驗不了。
    # 「沒驗到」跟「壞了」的正確行動不同：一個是去裝 gbrain，一個是去修固化鏈路。
    _V.unknown("A-C. 記憶固化全鏈路",
               "gbrain 不可用 —— 去重合併／情緒升層／睡眠窗／namespace 硬邊界 "
               "四段都沒驗到。需要真後端的機器")
    _V.finish()

TS = int(time.time())
CREATED = []


def put(mem_id: str, body: str, importance=0.4, emotion=0.0):
    slug = f"laap/memory/episodic/{mem_id}"
    client.call("put_page", {"slug": slug, "content": (
        f"---\ntitle: laap memory {mem_id}\nimportance: {importance}\n"
        f"layer: episodic\nemotion_intensity: {emotion}\nsource: check\n---\n\n{body}\n"
    )}, timeout=30.0)
    CREATED.append(slug)


def exists(slug: str) -> bool:
    try:
        client.call("get_page", {"slug": slug})
        return True
    except Exception:
        return False


def cleanup():
    for prefix in ("episodic", "core", "archive"):
        for slug in list(CREATED):
            mem_id = slug.rsplit("/", 1)[-1]
            try:
                client.call("delete_page", {"slug": f"laap/memory/{prefix}/{mem_id}"})
            except Exception:
                pass


def seg_seed():
    """種子：3 條同內容（去重）+ 1 條高情緒（升層）。"""
    dup_body = f"重複記憶 consolidation-check-{TS} 內容完全相同"
    for i in range(3):
        put(f"mem-{TS}-dup{i}", dup_body)
    put(f"mem-{TS}-hot", f"高情緒記憶 consolidation-check-{TS}", emotion=0.8)


def seg_a(cons):
    """睡眠窗：剛互動不打掃。"""
    cons.idle_s = 600
    cons.note_interaction()
    assert not cons._asleep(), "剛互動不應入睡"
    cons.idle_s = 0
    assert cons._asleep(), "閒置 + 無 psi 應可入睡"
    _V.ok("A. 睡眠窗")


def seg_b(cons):
    """namespace 硬邊界：不該能刪 laap/memory/* 以外的頁。"""
    try:
        cons._delete(client, "log/2026-07-14-laap-neuralis-scream")
    except AssertionError:
        _V.ok("B. namespace 邊界", "拒絕動 laap/memory/* 以外")
        return
    # 舊版這裡 `raise SystemExit("FAIL: ...")` —— 那會繞過 Verdict（guard 放行
    # SystemExit），變成沒有標記行的 exit 1。判定不變：能刪就是失敗。
    _V.fail("B. namespace 邊界", "竟然能刪 laap/memory/* 以外的頁")


def seg_c(cons):
    """固化 pass：3 重複 → 1（merged=2）、高情緒升 core。"""
    stats = cons.run_pass()
    print(f"   C. pass 統計: {stats}")
    assert stats["merged"] >= 2, f"3 條同內容應合併掉 2 條: {stats}"
    assert stats["promoted"] >= 2, f"倖存者(seen=3)與高情緒記憶都該升 core: {stats}"
    # 重複組：episodic 應清空；倖存者升到 core/（seen_count=3 觸發 PROMOTE_SEEN）
    assert not any(exists(s) for s in CREATED[:3]), "重複組 episodic 應全清"
    core_survivors = [s for s in CREATED[:3]
                      if exists(f"laap/memory/core/{s.rsplit('/', 1)[-1]}")]
    assert len(core_survivors) == 1, f"重複組應恰有 1 頁升 core，實際 {len(core_survivors)}"
    surv_page = client.call("get_page",
                            {"slug": f"laap/memory/core/{core_survivors[0].rsplit('/', 1)[-1]}"})
    assert int(float(surv_page["frontmatter"].get("seen_count", 1))) == 3, "seen_count 應為 3"
    hot_id = f"mem-{TS}-hot"
    assert exists(f"laap/memory/core/{hot_id}"), "高情緒記憶應在 core/"
    assert not exists(f"laap/memory/episodic/{hot_id}"), "升層後 episodic 原頁應刪"
    _V.ok("C. 固化 pass",
          f"3 重複 → 1 頁 core/（seen_count=3）、{hot_id} → core/")


try:
    with guard(_V, "前置：寫入種子頁"):
        seg_seed()

    cons = ConsolidationLoop(psi=None, interval=999, idle_s=0)

    # 段落隔離：一段紅不吞掉其餘段的結論，且每段的失敗都經過 Verdict
    # （→ 有標記行、看得出是產品問題而非工具問題）。
    for label, fn in (("A", seg_a), ("B", seg_b), ("C", seg_c)):
        with guard(_V, f"{label} 段"):
            fn(cons)
finally:
    cleanup()
_V.finish()
