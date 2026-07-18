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
from laap.s_span_bench import behavior_entropy, learning_correlation

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

# 判決
print("\n=== 判決 ===")
learned = corr is not None and corr > 0.2
diverse = learned_ent > baseline_ent + 0.1
if learned and diverse:
    print(f"✅ S_span 有效 — 選擇正相關 outcome（{corr:.2f}，學了不是隨機）"
          f"且比規則表多樣。分工/學習投資值得。")
elif learned:
    print(f"🟡 部分 — 有學習跡象（corr {corr:.2f}）但多樣度未明顯超規則表。續觀察。")
else:
    c = "算不了（樣本太少/單一選擇）" if corr is None else f"{corr:.2f}"
    print(f"❌ 未證實 — 選擇與 outcome 相關 {c}，看不到『學了』的證據。"
          f"⚠️ 樣本可能太小（{len(recs)} 筆）；讓 Aris 多跑再驗，或前面投資要回頭。")
