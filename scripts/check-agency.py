#!/usr/bin/env python3
"""
Phase 6 自檢：AgencyLoop 需求→行動→結果→記憶 全鏈路。

用法（從 neuralis 根，需 laap-AGI 同層）:
    PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-agency.py

驗證點:
  A. 白名單：非白名單工具被拒（不執行、不記帳）
  B. 迴路：certainty 壓低 → 自主行動 → 審計 JSONL + 記憶回寫 + certainty 回升
  C. rate cap：超額後不再行動
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agency import AgencyLoop, AUDIT_PATH, READONLY_WHITELIST
from laap.psi_core import PsiCore, NeedType
from laap.psi_backend import PythonPsiBackend
from laap.agi.cognitive_bus import CognitiveBus
from laap.tool_executor import ToolExecutor


def main():
    bus = CognitiveBus(agent_name="check")
    raw = PsiCore(bus=bus, interval=0.5)   # 不 start 心跳，手動控狀態
    psi = PythonPsiBackend(raw)            # M2 compat: AgencyLoop needs v1 API
    tools = ToolExecutor(bus=bus, agentos_registry=None)
    agency = AgencyLoop(psi=psi, tools=tools, bus=bus,
                        interval=0.5, max_per_hour=2, drive_threshold=0.45)

    # A. 白名單
    before = agency.actions_total
    agency._act("certainty", 0.9, "http-get", "https://example.com")
    assert agency.actions_total == before, "非白名單工具不應記入行動"
    print("A. 白名單拒絕: OK")

    # B. 迴路（手動壓低 certainty，其餘壓到閾值下避免搶跑）
    audit_before = AUDIT_PATH.read_text().count("\n") if AUDIT_PATH.exists() else 0
    for nt in NeedType:
        raw.needs.values[nt] = raw.needs.targets[nt]  # drive→0
    raw.needs.values[NeedType.CERTAINTY] = 0.2        # drive = 0.6*1.2 = 0.72
    raw.last_input = "gbrain 記憶"
    cert_before = raw.needs.values[NeedType.CERTAINTY]
    agency._evaluate()
    audit_after = AUDIT_PATH.read_text().count("\n") if AUDIT_PATH.exists() else 0
    assert audit_after == audit_before + 1, "應寫入一行審計"
    last = json.loads(AUDIT_PATH.read_text().splitlines()[-1])
    assert last["need"] == "certainty" and last["tool"] in READONLY_WHITELIST
    print(f"B. 迴路: OK — 行動 {last['tool']}({last['prompt'][:30]}) ok={last['ok']} "
          f"mem={last['mem_id'] or '-'}")
    if last["ok"]:
        assert raw.needs.values[NeedType.CERTAINTY] > cert_before, "成功行動應回升需求"
        assert last["mem_id"], "成功行動應有記憶 id"
        print(f"   certainty {cert_before:.2f} → {raw.needs.values[NeedType.CERTAINTY]:.2f}, "
              f"記憶已回寫")

    # C. rate cap（cap=2；B 已用 1 次 → 再 2 次只該成 1 次）
    raw.needs.values[NeedType.GROWTH] = 0.1
    agency._need_last_action.clear()
    n0 = agency.actions_total
    agency._evaluate()
    agency._need_last_action.clear()
    agency._evaluate()
    assert agency.actions_total - n0 <= 1, f"cap=2 應最多再 1 次，實際 {agency.actions_total - n0}"
    print("C. rate cap: OK")

    # 清掉本次自檢回寫進 gbrain 的所有記憶（B + C 的行動都會寫）
    try:
        from gbrain_client import get_client
        client = get_client()
        if client is not None and AUDIT_PATH.exists():
            for line in AUDIT_PATH.read_text().splitlines()[audit_before:]:
                mem_id = json.loads(line).get("mem_id")
                if mem_id:
                    client.call("delete_page", {"slug": f"laap/memory/episodic/{mem_id}"})
    except Exception:
        pass
    print("ALL AGENCY CHECKS PASSED")


if __name__ == "__main__":
    main()
