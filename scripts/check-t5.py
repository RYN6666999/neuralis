#!/usr/bin/env python3
"""
T5 自檢：AgencyLoop AgentOS 工具擴展 — 驗證 agency 能使用 web-search 等 AgentOS 工具。

6 段：
  A. 白名單含 AgentOS 唯讀工具
  B. Intent 形成使用 AgentOS 工具 (high exploration → web-search)
  C. Intent 仍退 gbrain (low exploration → gbrain)
  D. Write 工具不被 hard-block (pass-through to safety_gate)
  E. 現有 gbrain 路徑正常
  F. Rate cap 和 cycle guard 仍在

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-t5.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agency import AgencyLoop, READONLY_WHITELIST, AUDIT_PATH
from laap.psi_core import PsiCore, NeedType
from laap.psi_backend import PythonPsiBackend
from laap.agi.cognitive_bus import CognitiveBus
from laap.tool_executor import ToolExecutor


def main():
    bus = CognitiveBus(agent_name="check-t5")
    raw = PsiCore(bus=bus, interval=0.5)
    psi = PythonPsiBackend(raw)
    tools = ToolExecutor(bus=bus, agentos_registry=None)
    agency = AgencyLoop(psi=psi, tools=tools, bus=bus,
                        interval=0.5, max_per_hour=2, drive_threshold=0.45)

    # A. 白名單含 AgentOS 唯讀工具
    assert "web-search" in READONLY_WHITELIST, f"web-search 應在 READONLY_WHITELIST: {READONLY_WHITELIST}"
    assert "gbrain" in READONLY_WHITELIST
    print("A. 白名單含 AgentOS 唯讀工具: OK")

    # B. Intent 形成使用 AgentOS 工具 (high exploration → web-search)
    for nt in NeedType:
        raw.needs.values[nt] = raw.needs.targets[nt]  # drive→0
    raw.needs.values[NeedType.GROWTH] = 0.2            # drive ≈ 0.72
    raw.last_input = "未來趨勢"
    agency._exploration_rate = 1.0  # 強制探索
    # 多次嘗試確保有機率觸發 web-search path
    found_agentos = False
    for _ in range(20):
        intent = agency._form_intent("growth")
        if intent and intent[0] == "web-search":
            found_agentos = True
            break
    assert found_agentos, "exploration=1.0 時應至少一次回 web-search"
    print(f"B. Intent 使用 AgentOS 工具: OK ({intent})")

    # C. Intent 仍退 gbrain (low exploration)
    agency._exploration_rate = 0.0
    agency._recent_queries.clear()  # 清空 B 段收集的查詢，避免 _too_similar 干擾 gbrain 路由測試
    found_gbrain = False
    for _ in range(10):
        intent = agency._form_intent("growth")
        if intent and intent[0] == "gbrain":
            found_gbrain = True
            break
    assert found_gbrain, "exploration=0 時應回 gbrain"
    print("C. Intent 退 gbrain: OK")

    # D. Write 工具不被 hard-block
    before = agency.actions_total
    agency._act("growth", 0.9, "claude-code", "echo test")
    # 不應被 hard-block → 應執行到 tools.execute (結果是錯誤字串，但走完了流程)
    # 重點：actions_total 應增加（_act 沒提前 return）
    assert agency.actions_total == before + 1, \
        f"write tool 不該被 hard-block: before={before} after={agency.actions_total}"
    print("D. Write 工具 pass-through: OK")

    # E. 現有 gbrain 路徑正常
    for nt in NeedType:
        raw.needs.values[nt] = raw.needs.targets[nt]  # drive→0，清空先前段的殘留
    raw.needs.values[NeedType.CERTAINTY] = 0.2  # drive ≈ 0.72
    raw.last_input = "gbrain 記憶"
    agency._need_last_action.clear()
    cert_before = agency.actions_total
    agency._evaluate()
    assert agency.actions_total >= cert_before, "gbrain 路徑應有行動"
    last_need = json.loads(AUDIT_PATH.read_text().splitlines()[-1])["need"]
    assert last_need == "certainty", f"certainty 需求應走 gbrain: {last_need}"
    print("E. 現有 gbrain 路徑正常: OK")

    # F. Rate cap 和 cycle guard 仍在
    agency._need_last_action.clear()
    n0 = agency.actions_total
    agency._evaluate()
    agency._need_last_action.clear()
    agency._evaluate()
    assert agency.actions_total - n0 <= 1, f"cap=2 應最多再 1 次，實際 {agency.actions_total - n0}"
    print("F. Rate cap 和 cycle guard: OK")

    # 清理本次自檢的審計
    try:
        from gbrain_client import get_client
        client = get_client()
        if client is not None and AUDIT_PATH.exists():
            for line in AUDIT_PATH.read_text().splitlines():
                mem_id = json.loads(line).get("mem_id")
                if mem_id:
                    client.call("delete_page", {"slug": f"laap/memory/episodic/{mem_id}"})
    except Exception:
        pass
    print("ALL T5 CHECKS PASSED")


if __name__ == "__main__":
    import json
    main()
