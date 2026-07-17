#!/usr/bin/env python3
"""
T5 整合自檢：AgentOS registry 整合測試 — 驗證 agency 可透過 ToolExecutor 使用 AgentOS 工具。

3 段：
  A. Mock registry 測試 web-search 可執行 → 審計有記錄
  B. 寫入工具走 Phase 4b → safety_gate 拒 + pending queue
  C. 審計日誌含 grade

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-agency-agentos.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agency import AgencyLoop, AUDIT_PATH
from laap.psi_core import PsiCore, NeedType
from laap.psi_backend import PythonPsiBackend
from laap.agi.cognitive_bus import CognitiveBus
from laap.tool_executor import ToolExecutor
from laap.safety_gate import PENDING_PATH, APPROVED_PATH, AUDIT_PATH as SAFETY_AUDIT


def _cleanup():
    for p in (PENDING_PATH, APPROVED_PATH):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def main():
    _cleanup()

    # 建立 mock AgentOS registry
    class MockRegistry:
        def run(self, tool, prompt, timeout=30):
            if tool == "web-search":
                return '{"query": "AI trends", "results": [{"title": "AI in 2026"}]}'
            raise KeyError(f"unknown tool: {tool}")

        def list_all(self):
            return [{"name": "web-search", "source": "agentos"}]

    bus = CognitiveBus(agent_name="check-agentos")
    raw = PsiCore(bus=bus, interval=0.5)
    psi = PythonPsiBackend(raw)
    tools = ToolExecutor(bus=bus, agentos_registry=MockRegistry())
    agency = AgencyLoop(psi=psi, tools=tools, bus=bus,
                        interval=0.5, max_per_hour=5, drive_threshold=0.45)

    # A. Mock registry 測試 web-search 可執行
    audit_before = len(AUDIT_PATH.read_text().splitlines()) if AUDIT_PATH.exists() else 0
    for nt in NeedType:
        raw.needs.values[nt] = raw.needs.targets[nt]
    raw.needs.values[NeedType.GROWTH] = 0.2
    raw.last_input = "AI 趨勢"
    agency._exploration_rate = 1.0
    agency._need_last_action.clear()
    agency._evaluate()
    audit_after = len(AUDIT_PATH.read_text().splitlines()) if AUDIT_PATH.exists() else 0
    assert audit_after > audit_before, "應有審計記錄"
    last = json.loads(AUDIT_PATH.read_text().splitlines()[-1])
    assert last.get("tool") in ("web-search", "gbrain"), f"工具應為 web-search 或 gbrain: {last}"
    assert last.get("ok") is not None, "應有 ok 欄位"
    print(f"A. AgentOS 工具執行: OK (tool={last['tool']} ok={last['ok']})")

    # B. 寫入工具走 Phase 4b → safety_gate 拒 + pending queue
    agency._act("competence", 0.9, "claude-code", "write test file")
    assert PENDING_PATH.exists(), "claude-code 被拒應進 pending queue"
    pending = PENDING_PATH.read_text(encoding="utf-8")
    assert "claude-code" in pending, f"pending 應含 claude-code: {pending}"
    print("B. 寫入工具 Phase 4b 拒 + pending: OK")

    # C. 審計日誌含 grade
    if SAFETY_AUDIT.exists():
        for line in SAFETY_AUDIT.read_text().splitlines():
            entry = json.loads(line)
            if entry.get("tool") == "claude-code":
                assert "grade" in entry, f"審計應含 grade: {entry}"
                assert entry["grade"] == "write", f"claude-code grade 應為 write: {entry}"
                print(f"C. 審計日誌含 grade: OK (grade={entry['grade']})")
                break

    _cleanup()
    print("ALL AGENCY-AGENTOS CHECKS PASSED")


if __name__ == "__main__":
    main()