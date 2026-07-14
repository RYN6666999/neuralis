#!/usr/bin/env python3
"""Phase 6 補強自檢：agency 意圖品質（種子優先序 + 去重 + 聯想鏈）。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-agency-intent.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agency import AgencyLoop
from laap.agi.cognitive_bus import CognitiveBus
from laap.psi_core import PsiCore

psi = PsiCore(bus=CognitiveBus(agent_name="check"), interval=0.5)
ag = AgencyLoop(psi=psi, tools=None, bus=None)

# A. 真對話優先：last_input 當種子
psi.last_input = "gbrain 記憶架構"
intent = ag._form_intent("certainty")
assert intent and "gbrain 記憶架構" in intent[1], intent
print(f"A. 真對話當種子: OK — {intent[1]!r}")

# B. 去重：同種子第二次被擋（Jaccard ≥ 0.7）
again = ag._form_intent("certainty")
assert again is None, f"重複查詢應被擋: {again}"
assert ag.skipped_stale == 1
print("B. 查詢去重: OK — 第二次同種子被跳過")

# C. 無種子不硬查（舊版會退固定模板刷垃圾）
psi.last_input = ""
ag._seed_snippet = ""
assert ag._form_intent("growth") is None, "無種子應不行動"
assert ag.skipped_stale == 2
print("C. 無新鮮種子不硬查: OK")

# D. 聯想鏈：上次結果摘要 → 下次種子
ag._seed_snippet = ag._extract_seed("[0.85] wiki/x -- Clifford 幾何代數 是符號推理的基礎工具")
assert "Clifford" in ag._seed_snippet, ag._seed_snippet
intent = ag._form_intent("growth")
assert intent and "Clifford" in intent[1], intent
print(f"D. 聯想鏈（無對話時從記憶延伸）: OK — 種子={ag._seed_snippet!r}")

# E. _extract_seed 剝前綴（多層：分數 + slug）
assert ag._extract_seed("[0.72] a/b -- 真實內容片段測試") == "真實內容片段測試"
assert ag._extract_seed("## 標題\n實際內容在這行") == "實際內容在這行"  # 標題 2 字太短跳過
print("E. seed 抽取剝 slug/分數/標題前綴（多層）: OK")

print("ALL AGENCY-INTENT CHECKS PASSED")
