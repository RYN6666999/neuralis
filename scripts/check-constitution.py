#!/usr/bin/env python3
"""需求憲法自檢：邊界/單次上限/來源預算/凍結/權重治理/off 開關。

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-constitution.py
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["NEURALIS_CONSTITUTION"] = "on"

from laap.constitution import Constitution, _AUDIT_PATH

c = Constitution()

# A. 單次上限：user 對 competence 單次 max 0.15
allowed = c.guard_need("competence", 0.5, 0.4, "user")
assert abs(allowed - 0.15) < 1e-9, allowed
print("A. 單次上限 0.4→0.15: OK")

# B. range 硬夾：current 0.9 + 0.15 會破 0.95 上界 → 只准 +0.05
allowed = c.guard_need("competence", 0.9, 0.15, "user")
assert abs(allowed - 0.05) < 1e-9, allowed
print("B. range 硬夾 [0.05,0.95]: OK")

# C. 小時預算 + 凍結：agency 對 competence 預算 0.5/h
#    連打 5 次 0.15 → 0.15+0.15+0.15+0.05(補滿預算)+0.0(凍結)
c2 = Constitution()
got = [c2.guard_need("competence", 0.5, 0.15, "agency") for _ in range(5)]
assert abs(sum(got) - 0.5) < 1e-9, got          # 總放行量 = 預算
assert got[4] == 0.0, got                        # 預算耗盡後凍結
assert c2.freezes_total >= 1
print(f"C. 小時預算凍結: OK — 放行序列 {[round(g,3) for g in got]}")

# D. 預算按來源獨立：agency 凍結後 user 仍可過
allowed = c2.guard_need("competence", 0.5, 0.1, "user")
assert allowed > 0, allowed
print("D. 來源預算獨立: OK")

# E. 權重治理：單次 cap 0.30 + 預算 1.2/h/need 凍結
c3 = Constitution()
assert abs(c3.guard_weight("competence", "作法", 0.5) - 0.30) < 1e-9
got = [c3.guard_weight("competence", "作法", 0.5) for _ in range(4)]
assert got[-1] == 0.0, got                       # 預算耗盡凍結
print(f"E. 權重變速上限+凍結: OK — {[round(g,3) for g in got]}")

# F. 視窗滾動解凍（把花費戳記改成 1h 前）
key = ("competence", "agency")
c2._need_spend[key] = type(c2._need_spend[key])(
    (ts - 3700, a) for ts, a in c2._need_spend[key])
allowed = c2.guard_need("competence", 0.5, 0.1, "agency")
assert allowed > 0, allowed
print("F. 視窗滾動自動解凍: OK")

# G. off 開關全放行
os.environ["NEURALIS_CONSTITUTION"] = "off"
assert c.guard_need("competence", 0.9, 0.4, "user") == 0.4
assert c.guard_weight("competence", "作法", 0.9) == 0.9
os.environ["NEURALIS_CONSTITUTION"] = "on"
print("G. off 開關: OK")

# H. 審計檔有 freeze 事件
if _AUDIT_PATH.exists():
    events = [json.loads(l)["event"] for l in
              _AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-20:]]
    assert any("freeze" in e for e in events), events
    print("H. 審計檔 freeze 事件: OK")

# I. 整合：psi_core.satisfy 真的過憲法（超額被夾）
from laap.agi.cognitive_bus import CognitiveBus
from laap.psi_core import PsiCore, NeedType
psi = PsiCore(bus=CognitiveBus(agent_name="check"))
v0 = psi.needs.values[NeedType.COMPETENCE]
psi.needs.satisfy(NeedType.COMPETENCE, 0.4)      # 應被夾到 0.15
v1 = psi.needs.values[NeedType.COMPETENCE]
assert abs((v1 - v0) - 0.15) < 1e-9, (v0, v1)
print("I. psi_core.satisfy 走憲法: OK")

print("ALL CONSTITUTION CHECKS PASSED")
