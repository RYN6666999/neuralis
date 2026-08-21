#!/usr/bin/env python3
"""E3 runner — S_span 誠實驗收：學習/分工 vs 純規則表 baseline。

用 agency-audit.jsonl（真實決策）算：
  1. 選擇非隨機性（(need,tool) 頻率 vs 平均 outcome 相關）— 學了 vs 規則表
  2. 動作多樣性熵 vs 規則表 baseline（固定 = 只有 need 那層熵）
  3. gbrain 快取真實命中率（C-a）
用法: PYTHONPATH=.:../laap-AGI python scripts/benchmark-s-span.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from laap.s_span_bench import (behavior_entropy, learning_correlation,
                               learning_verdict, realized_advantage)

AUDIT = ROOT / "agency-audit.jsonl"

recs = []
for line in AUDIT.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    if d.get("need") and d.get("tool"):
        recs.append(d)

print(f"E3 S_span 驗收 — {len(recs)} 筆真實決策\n")

# 1. 選擇非隨機性：(need,tool) 頻率 vs 平均 outcome
lc = learning_correlation([{"choice": (r["need"], r["tool"]),
                            "outcome": r.get("outcome", 0)} for r in recs])
corr = lc["corr"]
print(f"1. 選擇非隨機性（學了 vs 規則表）")
print(f"   (need,tool) 選擇頻率 vs 平均 outcome 相關: "
      f"{corr if corr is None else round(corr, 3)}  "
      f"（{lc['n_choices']} 種選擇）")

# 2. 動作多樣性熵 vs 規則表 baseline
learned_ent = behavior_entropy([(r["need"], r["tool"]) for r in recs])
baseline_ent = behavior_entropy([r["need"] for r in recs])   # 規則表 = 固定 tool/need
print(f"\n2. 動作多樣性熵")
print(f"   學習系統 (need,tool): {learned_ent:.2f} bits")
print(f"   規則表 baseline (need only): {baseline_ent:.2f} bits")

# 3. C-a 快取真實命中率
try:
    from laap.experience_cache import hit_rate
    hr = hit_rate()
    print(f"\n3. gbrain 快取真實命中率（C-a）: "
          f"{hr['rate']:.0%} ({hr['hits']}/{hr['total']})"
          + ("" if hr['total'] else "  ← 還沒累積，讓 Aris 多跑一陣"))
except Exception:
    hr = {"total": 0}

# 1b. E3.2 可信度校準判準（corr 的誤判率約 40% 且不隨樣本量下降，見 s_span_bench 註解）
verdict = learning_verdict([{"choice": (r["need"], r["tool"]),
                             "outcome": r.get("outcome", 0)} for r in recs])
print(f"\n1b. 實現優勢（realized_advantage）")
print(f"   實際選擇的平均 outcome − 均勻亂選期望: {verdict['advantage']:+.4f}")
if verdict["null_p95"] is not None:
    print(f"   虛無分佈 95 百分位（亂選能拿到的上限）: {verdict['null_p95']:+.4f}")

# 判決
print("\n=== 判決 ===")
if verdict["underpowered"]:
    print(f"⚪ 樣本不足，不下結論 — {verdict['n_records']} 筆 / "
          f"{verdict['n_choices']} 種選擇。")
    print(f"   蒙地卡羅顯示 n<100 時連真的有學也只有 ~50% 檢出率，")
    print(f"   所以這裡的「未證實」不等於「沒學」，是「測不出來」。")
    print(f"   需要 ≥100 筆（建議 300 筆）真實決策才能判。")
elif verdict["learned"]:
    diverse = learned_ent > baseline_ent + 0.1
    print(f"✅ 學了 — 實現優勢 {verdict['advantage']:+.4f} 超過亂選上限 "
          f"{verdict['null_p95']:+.4f}（{verdict['n_records']} 筆）")
    print(f"   {'且比規則表多樣。分工/學習投資值得。' if diverse else '但多樣度未明顯超規則表，續觀察廣度軸。'}")
else:
    print(f"❌ 未證實 — 實現優勢 {verdict['advantage']:+.4f} 未超過亂選上限 "
          f"{verdict['null_p95']:+.4f}（{verdict['n_records']} 筆，樣本量足夠）")
    print(f"   樣本夠而測不出優勢 = 選擇與品質無關的證據，前面的投資要回頭檢視。")

# 舊判準並列（保留可比性，但標明不可信）
learned_old = corr is not None and corr > 0.2
print(f"\n   [舊判準 corr>0.2: {'通過' if learned_old else '未通過'}"
      f" — 誤判率約 40%，僅供對照，不作結論依據]")
