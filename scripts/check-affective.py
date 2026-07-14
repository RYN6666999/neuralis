#!/usr/bin/env python3
"""5 維情緒引擎自檢：事件動力學/損失趨避/耦合/偏差/agency 探索率調變。

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-affective.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from laap.affective import AffectiveState, EmotionDimension, PersonalityProfile

QUIET = PersonalityProfile(noise_amplitude=0.0)  # 測試關噪聲，斷言才穩定
P = EmotionDimension.PLEASURE.value
S = EmotionDimension.STRESS.value


def fresh():
    return AffectiveState(profile=PersonalityProfile(noise_amplitude=0.0))


# A. 事件方向：task_success 拉高 pleasure、壓低 stress
a = fresh()
p0, s0 = a.state_vector[P], a.state_vector[S]
a.post_event("task_success", 1.0)
a.update(dt=1.0)
assert a.state_vector[P] > p0, "task_success 應拉高 pleasure"
assert a.state_vector[S] < s0 + 0.01, "task_success 不應推高 stress"
print(f"A. 事件方向: OK — pleasure {p0:.2f}→{a.state_vector[P]:.2f}")

# B. 損失趨避：等強度負刺激的 |Δpleasure| > 正刺激（×1.5 tanh 夾後仍應成立）
pos, neg = fresh(), fresh()
pos.post_event("task_success", 0.5)
pos.update(dt=0.3)
neg.post_event("task_failure", 0.5)
neg.update(dt=0.3)
dp = abs(pos.state_vector[P] - 0.0)
dn = abs(neg.state_vector[P] - 0.0)
assert dn > dp, f"損失趨避失效: +Δ{dp:.3f} vs -Δ{dn:.3f}"
print(f"B. 損失趨避 ×1.5: OK — 正Δ{dp:.3f} < 負Δ{dn:.3f}")

# C. 維度耦合（矩陣語義 raw[target] = C[target,source]×state[source]）：
#    C[AROUSAL,STRESS]=0.2 → 壓力抬升喚起；C[STRESS,PLEASURE]=-0.4 → 愉悅洩壓
A = EmotionDimension.AROUSAL.value
c = fresh()
c.state_vector[S] = 0.8
a0 = c.state_vector[A]
for _ in range(3):
    c.update(dt=1.0)
assert c.state_vector[A] > a0 + 0.05, f"stress 應抬升 arousal: {c.state_vector[A]:.3f}"
happy, flat = fresh(), fresh()
happy.state_vector[:] = [0.8, 0.0, 0.3, 0.0, 0.5]
flat.state_vector[:] = [0.0, 0.0, 0.3, 0.0, 0.5]
for _ in range(3):
    happy.update(dt=1.0)
    flat.update(dt=1.0)
assert happy.state_vector[S] < flat.state_vector[S] - 0.02, \
    f"pleasure 應加速洩壓: {happy.state_vector[S]:.3f} vs {flat.state_vector[S]:.3f}"
print(f"C. 耦合矩陣: OK — stress→arousal {a0:.2f}→{c.state_vector[A]:.2f}；"
      f"愉悅洩壓 {happy.state_vector[S]:.3f} < {flat.state_vector[S]:.3f}")

# D. 情緒標籤象限
d = fresh()
d.state_vector[:] = [0.6, 0.4, 0.3, 0.0, 0.0]
assert d.compute_mood() == "joyful"
d.state_vector[:] = [-0.6, 0.5, 0.0, 0.0, 0.5]
assert d.compute_mood() == "angry"
d.state_vector[:] = [0.0, -0.5, 0.3, 0.0, 0.0]
assert d.compute_mood() == "calm"
print("D. mood 象限標籤: OK")

# E. 偏差公式符號：高 arousal 升 risk_seeking；高 stress 反壓 + 升窄化
e = fresh()
e.state_vector[:] = [0.0, 0.8, 0.0, 0.0, 0.0]
b1 = e.compute_cognitive_bias()
assert b1["risk_seeking"] > 0.1 and b1["attention_narrowing"] > 0.2
e.state_vector[:] = [0.0, 0.0, 0.0, 0.0, 0.9]
b2 = e.compute_cognitive_bias()
assert b2["risk_seeking"] < 0 and b2["attention_narrowing"] > 0.2
print("E. 認知偏差公式: OK")

# F. agency 探索率被偏差真調變（功能性驗證核心）
from laap.agency import AgencyLoop


class FakePsi:
    def __init__(self, av):
        self.affective = av


base = fresh()                       # 中性 → eff ≈ 底值
hot = fresh()
hot.state_vector[:] = [0.0, 0.9, 0.0, 0.0, 0.8]   # 高喚起+高壓力 → 窄化主導
calm_risk = fresh()
calm_risk.state_vector[:] = [0.0, 0.6, 0.0, 0.0, -0.5]  # 高喚起低壓力 → 探索升

ag = AgencyLoop.__new__(AgencyLoop)   # 不跑 __init__ 的迴路，只測純函式
ag._exploration_rate = 0.15
ag.psi = FakePsi(base)
e_base = ag._effective_exploration()
ag.psi = FakePsi(hot)
e_hot = ag._effective_exploration()
ag.psi = FakePsi(calm_risk)
e_risk = ag._effective_exploration()
assert e_hot < e_base, f"窄化應降探索: {e_hot:.3f} vs {e_base:.3f}"
assert e_risk > e_base, f"risk_seeking 應升探索: {e_risk:.3f} vs {e_base:.3f}"
print(f"F. 探索率調變: OK — 底 {e_base:.3f} | 壓力窄化 {e_hot:.3f} | 冒險 {e_risk:.3f}")

# G. psi_core 整合：affective 進 get_state、心跳可跑
from laap.agi.cognitive_bus import CognitiveBus
from laap.psi_core import PsiCore
psi = PsiCore(bus=CognitiveBus(agent_name="check"))
psi.process_input("謝謝你，做得很好")
psi.affective.update(dt=1.0)
st = psi.get_state()
assert "affective" in st and "mood" in st["affective"] and "biases" in st["affective"]
assert st["affective"]["events_total"] >= 1   # user_engagement 有進
print(f"G. psi_core 整合: OK — mood={st['affective']['mood']} "
      f"events={st['affective']['events_total']}")

print("ALL AFFECTIVE CHECKS PASSED")
