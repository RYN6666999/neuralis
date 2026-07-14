#!/usr/bin/env python3
"""
Phase 5 自檢：記憶固化全鏈路（去重合併 / 情緒升層 / 睡眠窗 / namespace 硬邊界）。

用法（從 neuralis 根，需 gbrain 可用）:
    PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-consolidation.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.consolidation import ConsolidationLoop
from gbrain_client import get_client

client = get_client()
assert client is not None, "gbrain 不可用，此自檢需要真後端"

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


try:
    # 種子：3 條同內容（去重）+ 1 條高情緒（升層）
    dup_body = f"重複記憶 consolidation-check-{TS} 內容完全相同"
    for i in range(3):
        put(f"mem-{TS}-dup{i}", dup_body)
    put(f"mem-{TS}-hot", f"高情緒記憶 consolidation-check-{TS}", emotion=0.8)

    cons = ConsolidationLoop(psi=None, interval=999, idle_s=0)

    # A. 睡眠窗：剛互動不打掃
    cons.idle_s = 600
    cons.note_interaction()
    assert not cons._asleep(), "剛互動不應入睡"
    cons.idle_s = 0
    assert cons._asleep(), "閒置 + 無 psi 應可入睡"
    print("A. 睡眠窗: OK")

    # B. namespace 硬邊界
    try:
        cons._delete(client, "log/2026-07-14-laap-neuralis-scream")
        raise SystemExit("FAIL: 不該能刪 namespace 外的頁")
    except AssertionError:
        print("B. namespace 邊界: OK（拒絕動 laap/memory/* 以外）")

    # C. 固化 pass：3 重複 → 1（merged=2）、高情緒升 core
    stats = cons.run_pass()
    print(f"C. pass 統計: {stats}")
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
    print(f"   3 重複 → 1 頁 core/（seen_count=3）✓、{hot_id} → core/ ✓")

    print("ALL CONSOLIDATION CHECKS PASSED")
finally:
    cleanup()
