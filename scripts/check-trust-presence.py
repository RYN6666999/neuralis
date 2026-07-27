#!/usr/bin/env python3
"""
check-trust-presence.py — 自檢登場感（presence）感測器。

背景：trust 舊設計單調飽和到 1.0（+0.03/msg vs -0.0005/cycle），且接的
relatedness 增益早已接空鉤（relatedness 07-15 退出 _ANGLE）。改為登場感：
遞增上升 + 閒置均值回歸，接活槓桿 _effective_exploration。

測試 4 段：
A. 無飽和 — 連續互動遞增上升、停在 1.0 以下、增量遞減
B. 閒置回歸 — _evaluate 空轉時 presence 向 baseline 降（不再卡住）
C. 活槓桿 — presence 高 → 探索率低；presence 低 → 探索率高（單調）
D. 死鉤移除 — 舊 relatedness×trust 增益碼已不存在（結構守衛）

用法:
    cd ~/Developer/neuralis
    PYTHONPATH=".:../laap-AGI" ../laapenv/bin/python scripts/check-trust-presence.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from laap.agency import AgencyLoop

errors = 0


def section(name):
    print(f"\n─── {name} ───")


def check(cond, label):
    global errors
    print(f"  {'✅' if cond else '❌'} {label}")
    if not cond:
        errors += 1


class MockPsi:
    def __init__(self):
        self._drives = {"competence": 0.0, "growth": 0.0, "certainty": 0.0,
                        "relatedness": 0.0, "autonomy": 0.0}
        self._last = ""
    def get_drives(self):
        return dict(self._drives)
    def get_last_input(self):
        return self._last
    def get_cognitive_bias(self):
        return {"risk_seeking": 0.0, "attention_narrowing": 0.0}


class MockTools:
    def execute(self, *a, **kw):
        return ""


def fresh():
    return AgencyLoop(psi=MockPsi(), tools=MockTools())


# ── A: 無飽和 + 遞增 ──
section("A — 無飽和，遞增式上升")
a = fresh()
start = a._trust_scores["user"]
inc_prev = None
diminishing = True
for i in range(100):
    before = a._trust_scores["user"]
    a.note_interaction("user")
    inc = a._trust_scores["user"] - before
    if inc_prev is not None and inc > inc_prev + 1e-9:
        diminishing = False
    inc_prev = inc
check(start == a._TRUST_BASELINE, f"初始 = baseline {a._TRUST_BASELINE} (實 {start:.3f})")
check(diminishing, "增量遞增式遞減（越高越難推）")

# 生產等效：每週期 1 互動 + 1 decay，看平衡點（這才是「會不會再飽和」的真問題）
e = fresh()
for _ in range(200):
    e.note_interaction("user")   # 每週期一次密集互動
    e._evaluate()                # 同週期跑 decay
eq_dense = e._trust_scores["user"]
check(eq_dense < 0.9, f"最密集互動（每週期）平衡點仍 < 0.9 (實 {eq_dense:.4f})  ← 舊設計卡 1.0")
check(abs(eq_dense - 0.8) < 0.03, f"平衡點 ≈ 0.8（rise/decay 解析解）(實 {eq_dense:.4f})")


# ── B: 閒置向 baseline 回歸 ──
section("B — 閒置均值回歸（presence 會降下來）")
b = fresh()
for _ in range(30):
    b.note_interaction("user")   # 先推高
high = b._trust_scores["user"]
for _ in range(60):              # 模擬 60 個評估週期無互動
    b._evaluate()                # 走真實 decay 路徑（drives 全 0 → 不觸發行動）
low = b._trust_scores["user"]
check(high > 0.8, f"互動後高登場感 (實 {high:.3f})")
check(low < high - 0.2, f"閒置後明顯下降 {high:.3f} → {low:.3f}  ← 舊設計 -0.0005 幾乎不動")
check(abs(low - b._TRUST_BASELINE) < 0.05, f"回歸到 baseline 附近 (實 {low:.3f} vs {b._TRUST_BASELINE})")


# ── C: 活槓桿（presence → 探索率） ──
section("C — 登場感調變探索率（在場少探索、離開多探索）")
c = fresh()
c._exploration_rate = 0.15
c._trust_scores["user"] = 0.9    # 在場
eff_high = c._effective_exploration()
c._trust_scores["user"] = 0.2    # 離開久
eff_low = c._effective_exploration()
check(eff_high < eff_low, f"presence 高 → 探索低 ({eff_high:.4f}) vs presence 低 → 探索高 ({eff_low:.4f})")
check(0.02 <= eff_high <= 0.5 and 0.02 <= eff_low <= 0.5, "兩者都在 clamp [0.02, 0.5] 內")
# 中性參考點附近應接近底值
c._trust_scores["user"] = c._TRUST_MID
eff_mid = c._effective_exploration()
check(abs(eff_mid - 0.15) < 1e-6, f"presence = _TRUST_MID 時無調變 (實 {eff_mid:.4f} = 底值 0.15)")


# ── D: 死鉤移除（結構守衛） ──
section("D — 舊 relatedness×trust 增益已移除")
src = open(os.path.join(os.path.dirname(__file__), "..", "laap", "agency.py"),
           encoding="utf-8").read()
check("1.0 + trust * 0.5" not in src, "舊 `1.0 + trust * 0.5` 增益碼不存在")
check('drives["relatedness"] =' not in src, "不再改寫 drives[relatedness]")
check("_TRUST_DECAY_PULL" in src and "_trust_decay_rate" not in src,
      "舊 _trust_decay_rate 已換成 _TRUST_DECAY_PULL")


print(f"\n{'='*40}")
print(f"{'✅ 全部通過' if errors == 0 else f'❌ {errors} 項失敗'}")
sys.exit(1 if errors else 0)
