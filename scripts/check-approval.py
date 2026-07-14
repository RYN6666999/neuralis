#!/usr/bin/env python3
"""Phase 4b 自檢：檔案式人工批准閘（排隊 / 批准生效 / 內容掃描不繞過 / 撤銷）。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-approval.py"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.pop("NEURALIS_TOOL_ALLOW", None)

from laap.agi.cognitive_bus import CognitiveBus
from laap.safety_gate import check, APPROVED_PATH, PENDING_PATH
from laap.tool_executor import ToolExecutor

APPROVE = os.path.join(os.path.dirname(__file__), "approve-tool.sh")


def _run(*args):
    r = subprocess.run(["bash", APPROVE, *args],
                       capture_output=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"approve-tool.sh {args} exit={r.returncode} {r.stderr}"


def _cleanup():
    for p in (APPROVED_PATH, PENDING_PATH):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


_cleanup()
try:
    tools = ToolExecutor(bus=CognitiveBus(agent_name="check"), agentos_registry=None)

    # A. 未批准 → 拒 + 排入待批
    r = tools.execute("http-get", "https://example.com")
    assert r.startswith("[安全閘]") and "待批" in r, r
    assert PENDING_PATH.exists(), "應寫入待批清單"
    print("A. 拒絕 + 排隊: OK")

    # B. 人工批准 → 免重啟生效 + 出隊
    _run("http-get")
    allowed, _ = check("http-get", "https://example.com")
    assert allowed, "批准後應放行"
    pending = PENDING_PATH.read_text() if PENDING_PATH.exists() else ""
    assert '"http-get"' not in pending, "批准後應移出待批"
    print("B. 檔案批准即時生效 + 出隊: OK")

    # C. 批准工具帶危險內容仍攔（兩層獨立）
    allowed, _ = check("http-get", "rm -rf /")
    assert not allowed, "內容掃描不受工具批准影響"
    print("C. 批准後內容掃描仍在: OK")

    # D. 撤銷 → 再拒
    _run("-r", "http-get")
    allowed, _ = check("http-get", "https://example.com")
    assert not allowed, "撤銷後應再拒"
    print("D. 撤銷: OK")

    print("ALL 4B APPROVAL CHECKS PASSED")
finally:
    _cleanup()
