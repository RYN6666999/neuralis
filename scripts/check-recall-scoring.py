#!/usr/bin/env python3
"""
check-recall-scoring.py — 自檢 outcome-tied recall 記分（第2條）。

背景：discovered_salience 曾是死欄位（recall_hit 沒人叫）。修法 = wake 曝露被撈
記憶 id，由 chatflow 在互動結果正向時回頭 credit（不在撈取當下記分，否則 wake 依
τ 選、τ 含 discovered_salience → 自我墊高，違反 recall_not_selfinflated 契約）。

測試 4 段（aris-memory 側）：
A. wake_context 回 (text, ids)，ids = 被選進暖啟動塊的記憶 id
B. recall_hit credit discovered_salience +0.1、total_recalls +1
C. 無自賺分 — 重複呼叫 wake_context 100 次，discovered_salience 完全不動
   （只有顯式 recall_hit 才加分）
D. τ 對 discovered_salience 有反應（credit 過的記憶衰減慢）

用法:
    cd ~/Developer/neuralis
    ../laapenv/bin/python scripts/check-recall-scoring.py
"""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location("aris_memory_srv",
                                              os.path.join(HERE, "aris-memory.py"))
am = importlib.util.module_from_spec(spec)
spec.loader.exec_module(am)

errors = 0


def check(cond, label):
    global errors
    print(f"  {'✅' if cond else '❌'} {label}")
    if not cond:
        errors += 1


tmp = tempfile.mktemp(suffix=".db")
mem = am.ArisMemory(db_path=tmp)

# 種三筆帶 attention_line 的記憶
ids = []
for i in range(3):
    r = mem.store("aris-self", f"內容{i}", attention_line=f"下一步{i}",
                  encoding_salience=3, source_id=f"t-{i}")
    ids.append(r["id"])

print("─── A: wake_context 回 (text, ids) ───")
text, recalled = mem.wake_context(limit=3)
check(isinstance(text, str) and isinstance(recalled, list), "回傳 (str, list)")
check(len(recalled) == 3 and set(recalled) == set(ids), f"ids = 被撈記憶 (實 {recalled})")
check("下一步" in text, "text 含注意力線")

print("\n─── B: recall_hit credit ───")
mid = ids[0]
before = mem.query("", "", 10)
ds_before = next(m["discovered_salience"] for m in before if m["id"] == mid)
r = mem.recall_hit(mid)
after = mem.query("", "", 10)
ds_after = next(m["discovered_salience"] for m in after if m["id"] == mid)
tr_after = next(m["total_recalls"] for m in after if m["id"] == mid)
check(abs(ds_after - (ds_before + 0.1)) < 1e-9, f"discovered_salience +0.1 ({ds_before}→{ds_after})")
check(tr_after == 1, f"total_recalls +1 (實 {tr_after})")

print("\n─── C: 無自賺分（wake 不記分）───")
snap = {m["id"]: m["discovered_salience"] for m in mem.query("", "", 10)}
for _ in range(100):
    mem.wake_context(limit=3)   # 重複撈取
after2 = {m["id"]: m["discovered_salience"] for m in mem.query("", "", 10)}
unchanged = all(abs(after2[i] - snap[i]) < 1e-9 for i in snap)
check(unchanged, "撈取 100 次後 discovered_salience 完全不動（選擇≠獎勵，不自我墊高）")

print("\n─── D: τ 對 discovered_salience 有反應 ───")
tau_lo = am._tau_score(2, 0.0, 5.0)   # 沒被 recall
tau_hi = am._tau_score(2, 1.0, 5.0)   # discovered 滿
check(tau_hi > tau_lo, f"credit 過的記憶衰減慢 (τ_hi {tau_hi:.3f} > τ_lo {tau_lo:.3f})")

os.unlink(tmp)
print(f"\n{'='*40}")
print(f"{'✅ 全部通過' if errors == 0 else f'❌ {errors} 項失敗'}")
sys.exit(1 if errors else 0)
