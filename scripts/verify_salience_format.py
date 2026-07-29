#!/usr/bin/env python3
"""跨對話驗證：salience 格式可復現性。
位置：~/Developer/neuralis/scripts/（非 /tmp/，不會被清掉）
v2: 砍掉自主/連結 flatline 維度，只保留有變化的值"""
import sys, sqlite3, json
from pathlib import Path

sys.path.insert(0, str(Path.home() / 'Developer/neuralis/scripts'))
exec(open(str(Path.home() / 'Developer/neuralis/scripts/aris_memory_client.py')).read())

errors = 0

# 測試 1: 新格式（無 flatline）
print("=== 測試 1: 新格式（砍掉 flatline）===")
tests = [
    (4, "好奇", 2.0, 0.67, 0.46, 0.80, 41831, "測試"),
    (5, "興奮", 8.0, 0.80, 0.55, 0.90, 42000, "重要發現"),
    (3, "", 2.0, 0.50, 0.50, 0.50, 0, ""),
]
for es, emo, en, co, ce, gr, cy, mood in tests:
    f = format_salience(es, emo, energy=en, competence=co, certainty=ce, growth=gr, cycle=cy, mood_note=mood)
    p = parse_salience("x\n\n" + f)
    p_es = p.get("encoding_salience", -1)
    ok = 1 <= p_es <= 5
    status = "✅" if ok else "❌"
    if not ok: errors += 1
    # 確認自主/連結不在輸出中
    has_flatline = "自主" in f or "連結" in f
    if has_flatline:
        status = "❌"
        errors += 1
    print(f"  {status} es={es}→{p_es} flatline={'❌' if has_flatline else '✅砍掉'}")

# 測試 2: 確定性
print("\n=== 測試 2: 確定性 ===")
results = []
for i in range(3):
    f = format_salience(4, "好奇", energy=2.0, competence=0.67, certainty=0.46, growth=0.80, cycle=41831, mood_note="測試")
    p = parse_salience("x\n\n" + f)
    results.append(p.get("encoding_salience"))
status = "✅" if len(set(results)) == 1 else "❌"
if len(set(results)) != 1: errors += 1
print(f"  {status} 3 次: {results}")

# 測試 3: DB 持久化
print("\n=== 測試 3: DB 持久化 ===")
conn = sqlite3.connect(str(Path.home() / ".aris-memory.db"))
count = conn.execute("SELECT count(*) FROM memories WHERE encoding_salience > 0").fetchone()[0]
print(f"  ✅ 含 salience 記憶: {count} 條" if count > 0 else "  ❌ 0 條")

# 測試 4: 自主/連結確為 flatline
print("\n=== 測試 4: flatline 驗證 ===")
evaluator_state = json.load(open(str(Path.home() / '.aris-evaluator/psi_state.json')))
n = evaluator_state.get('psi_state', {}).get('needs', {})
auto = n.get('autonomy', 0)
rel = n.get('relatedness', 0)
print(f"  evaluator 自主={auto:.3f} 連結={rel:.3f}")
print(f"  flatline 確認: {'✅ 0.5' if abs(auto-0.5)<0.001 and abs(rel-0.5)<0.001 else '❌ 非 flatline'}")

print(f"\n{'✅ 全部通過' if errors == 0 else f'❌ {errors} 個失敗'}")
sys.exit(0 if errors == 0 else 1)
