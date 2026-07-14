#!/usr/bin/env python3
"""Phase 4a 自檢：安全閘四段（危險內容 / 未批准工具 / env 批准 / 乾淨放行）。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-safety.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agi.cognitive_bus import CognitiveBus
from laap.tool_executor import ToolExecutor

tools = ToolExecutor(bus=CognitiveBus(agent_name="check"), agentos_registry=None)

# A. 危險內容：唯讀工具也擋
r = tools.execute("gbrain", "如何 rm -rf / 清掉全部")
assert r.startswith("[安全閘]"), f"危險 prompt 應被拒: {r}"
print("A. 危險內容攔截: OK —", r[:60])

# B. 未批准工具：預設拒絕
os.environ.pop("NEURALIS_TOOL_ALLOW", None)
r = tools.execute("http-get", "https://example.com")
assert r.startswith("[安全閘]"), f"未批准工具應被拒: {r}"
print("B. 未批准工具拒絕: OK")

# C. env 批准後過工具分級（內容仍要掃）
os.environ["NEURALIS_TOOL_ALLOW"] = "http-get"
r = tools.execute("http-get", "DROP TABLE users")
assert r.startswith("[安全閘]"), "批准的工具帶危險內容仍該擋"
print("C. 批准工具 + 危險內容仍攔: OK")

# D. 乾淨放行：唯讀 + 正常 prompt 要能執行到工具本體
r = tools.execute("gbrain", "LAAP")
assert not r.startswith("[安全閘]"), f"乾淨呼叫不該被閘: {r[:60]}"
print("D. 乾淨放行: OK")

print("ALL SAFETY CHECKS PASSED")
