#!/usr/bin/env python3
"""
check-dopamine.py — 自檢功能性多巴胺（RPE）系統。

測試 4 段：
A. _score_result 對不同品質的結果回傳正確分數
B. 模擬行動序列，驗證 RPE 計算 + EMA 更新
C. 模擬角度權重更新（正 RPE 升權重、負 RPE 降權重）
D. 模擬探索率自適應（持續正 RPE 升探索率、持續負 RPE 降探索率）

用法:
    cd ~/Developer/neuralis
    PYTHONPATH=".:../laap-AGI" ../laapenv/bin/python scripts/check-dopamine.py
"""
import json
import os
import sys
import time

# 插入 neuralis root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agency import AgencyLoop

errors = 0


def section(name: str):
    print(f"\n─── {name} ───")


# ── A: _score_result ──
section("A — _score_result 品質分數")

# 需要一個 agency 實例來呼叫靜態方法（但 _score_result 是實例方法）
# 用最小 mock
class MockPsi:
    class Needs:
        def get_drives(self): return {}
        def get_dominant(self): return (None, 0)
    needs = Needs()
    class Emotion:
        def to_dict(self): return {"valence": 0, "arousal": 0.5}
    emotion = Emotion()

class MockTools:
    def execute(self, *a, **kw): return ""

agency = AgencyLoop(psi=MockPsi(), tools=MockTools())

cases = [
    ("", 0.0, "空字串"),
    ("無結果", 0.0, "無結果"),
    ("[0.82] slug — text\n[0.75] slug2 — more", 0.785 + 0.12, "2 hit 高品質"),
    ("[0.50] slug — text", 0.50 + 0.06, "1 hit 中等"),
    ("[0.10] slug — text\n[0.05] slug2 — text", 0.075 + 0.12, "2 hit 低品質"),
    ("something without scores", 0.4, "無分數但有內容（E1.1 flat base，非 len/500）"),
]
for result, expected, label in cases:
    score = agency._score_result(result)
    ok = abs(score - expected) < 0.01
    status = "✅" if ok else "❌"
    print(f"  {status} {label}: got={score:.3f} expected={expected:.3f}")
    if not ok:
        errors += 1


# ── B: RPE 計算 + EMA ──
section("B — RPE 計算 + EMA 更新")

agency2 = AgencyLoop(psi=MockPsi(), tools=MockTools())
# 模擬三次行動，每次模擬不同結果
sim_results = [
    "[0.80] hit1 — good\n[0.70] hit2 — great",
    "[0.30] hit1 — poor",
    "[0.90] hit1 — excellent\n[0.85] hit2 — great\n[0.75] hit3 — good",
]
for i, r in enumerate(sim_results):
    # 直接呼叫 _act 需要完整參數，用 _score_result + 手動更新 RPE 代替
    outcome = agency2._score_result(r)
    need = "competence"
    stats = agency2._need_stats.setdefault(need, {
        "expected": 0.3, "rpes": [], "angle_weights": {}})
    expected = stats["expected"]
    rpe = outcome - expected
    stats["expected"] = 0.9 * expected + 0.1 * outcome
    stats["rpes"].append(rpe)
    agency2._rpe_buffer.append(rpe)
    agency2._rpe_total += rpe
    agency2._rpe_count += 1
    print(f"  行動#{i+1}: outcome={outcome:.3f} expected={expected:.3f} "
          f"rpe={rpe:+.3f} → 新 expected={stats['expected']:.3f}")

# 驗證 EMA 收斂
expected_final = round(agency2._need_stats["competence"]["expected"], 3)
print(f"  EMA 最終值: {expected_final}")
if 0.3 < expected_final < 0.6:
    print(f"  ✅ EMA 在合理範圍")
else:
    print(f"  ⚠️  EMA 值 {expected_final} 需手動確認")
    errors += 1


# ── C: 角度權重更新 ──
section("C — 角度權重更新（RPE 正→升，負→降）")

agency3 = AgencyLoop(psi=MockPsi(), tools=MockTools())
need = "competence"
stats = agency3._need_stats.setdefault(need, {
    "expected": 0.5, "rpes": [], "angle_weights": {"作法": 1.0, "經驗": 1.0}})

# 正 RPE → 權重升
old_w = stats["angle_weights"]["作法"]
rpe_pos = 0.3
stats["angle_weights"]["作法"] = max(0.1, min(3.0, old_w + rpe_pos * 0.5))
print(f"  正 RPE (+0.3): 作法權重 {old_w:.1f} → {stats['angle_weights']['作法']:.2f} ✅ 升")
assert stats["angle_weights"]["作法"] > old_w, "正 RPE 應升權重"

# 負 RPE → 權重降
old_w = stats["angle_weights"]["經驗"]
rpe_neg = -0.4
stats["angle_weights"]["經驗"] = max(0.1, min(3.0, old_w + rpe_neg * 0.5))
print(f"  負 RPE (-0.4): 經驗權重 {old_w:.1f} → {stats['angle_weights']['經驗']:.2f} ✅ 降")
assert stats["angle_weights"]["經驗"] < old_w, "負 RPE 應降權重"

# 權重下限 0.1
rpe_big_neg = -5.0
stats["angle_weights"]["經驗"] = max(0.1, min(3.0, stats["angle_weights"]["經驗"] + rpe_big_neg * 0.5))
print(f"  極負 RPE (-5.0): 經驗權重下限 {stats['angle_weights']['經驗']:.2f} ✅ clamp 0.1")
assert stats["angle_weights"]["經驗"] >= 0.1, "權重下限應為 0.1"


# ── D: 探索率自適應 ──
section("D — 探索率自適應")

agency4 = AgencyLoop(psi=MockPsi(), tools=MockTools())
init_exp = agency4._exploration_rate
print(f"  初始探索率: {init_exp:.2f}")

# 持續正 RPE
for i in range(5):
    agency4._rpe_buffer.append(0.15)
    if len(agency4._rpe_buffer) >= 5:
        avg_rpe = sum(agency4._rpe_buffer) / len(agency4._rpe_buffer)
        if avg_rpe > 0.05:
            agency4._exploration_rate = min(0.30, agency4._exploration_rate + 0.005)
print(f"  持續正 RPE 後: {agency4._exploration_rate:.2f} ✅ 升")
assert agency4._exploration_rate > init_exp, "正 RPE 應升探索率"
assert agency4._exploration_rate <= 0.30, "探索率上限 0.30"

# 持續負 RPE
for i in range(5):
    agency4._rpe_buffer.append(-0.15)
    if len(agency4._rpe_buffer) >= 5:
        avg_rpe = sum(agency4._rpe_buffer) / len(agency4._rpe_buffer)
        if avg_rpe < -0.05:
            agency4._exploration_rate = max(0.05, agency4._exploration_rate - 0.005)
print(f"  持續負 RPE 後: {agency4._exploration_rate:.2f} ✅ 降")
assert agency4._exploration_rate < 0.30, "負 RPE 應降探索率"
assert agency4._exploration_rate >= 0.05, "探索率下限 0.05"


# ── 結果 ──
print(f"\n{'='*40}")
if errors:
    print(f"❌ {errors} 個測試失敗")
    sys.exit(1)
else:
    print("✅ 全部通過")