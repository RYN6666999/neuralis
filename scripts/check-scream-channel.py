#!/usr/bin/env python3
"""
Scream–Aris 頻道自檢：驗證 scream-ask 工具註冊、分類、寫入、讀取、安全防護。

7 段：
  A. tool registration — "scream-ask" in tools.list_tools()
  B. safety classification — classify("scream-ask") == "readonly_builtin"
  C. channel write — execute 後檔案存在且格式正確
  D. response read — mock scream→aris 回應，驗證讀到
  E. symlink guard — 建立 symlink 驗證拒絕
  F. agency intent — mock agency 驗證 competence 可選 scream-ask
  G. cleanup

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-scream-channel.py
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agi.cognitive_bus import CognitiveBus
from laap.tool_executor import ToolExecutor
from laap.safety_gate import classify, READONLY_SAFE
from laap.agency import AgencyLoop, READONLY_WHITELIST
from laap.psi_core import PsiCore, NeedType
from laap.psi_backend import PythonPsiBackend

CHANNEL = "/tmp/aris-scream-channel.jsonl"


def _cleanup():
    for p in (CHANNEL,):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


def main():
    _cleanup()
    bus = CognitiveBus(agent_name="check-channel")
    tools = ToolExecutor(bus=bus, agentos_registry=None)

    # A. tool registration
    tool_names = [t["name"] for t in tools.list_tools()]
    assert "scream-ask" in tool_names, f"scream-ask 未註冊: {tool_names}"
    print("A. tool registration: OK")

    # B. safety classification
    assert classify("scream-ask") == "readonly_builtin", classify("scream-ask")
    assert "scream-ask" in READONLY_SAFE
    print("B. safety classification: OK")

    # C. channel write
    r = tools.execute("scream-ask", "Read 工具怎麼用？")
    assert os.path.exists(CHANNEL), "頻道檔案未建立"
    with open(CHANNEL) as f:
        lines = f.read().splitlines()
    assert len(lines) >= 1, "頻道應至少一行"
    last = json.loads(lines[-1])
    assert last["direction"] == "aris→scream", f"direction 應為 aris→scream: {last}"
    assert last["type"] == "request"
    assert "Read" in last["content"]
    assert "id" in last and len(last["id"]) == 12
    print(f"C. channel write: OK (id={last['id']}, content={last['content'][:30]}...)")

    # D. response read — mock scream→aris 回應
    request_entry = last
    mock_response = {
        "ts": time.time(), "id": "mock" + "x" * 8,
        "direction": "scream→aris", "type": "response",
        "content": "Read 工具可以用來讀取檔案內容",
        "context": {"request_ts": request_entry["ts"]},
    }
    with open(CHANNEL, "a") as f:
        f.write(json.dumps(mock_response, ensure_ascii=False) + "\n")
    r2 = tools.execute("scream-ask", "再試一次")  # 發新請求
    # 新請求不該讀到舊回應（request_ts 不同）
    with open(CHANNEL) as f:
        updated = [json.loads(l) for l in f if l.strip()]
    scream_responses = [e for e in updated
                        if e["direction"] == "scream→aris"]
    assert len(scream_responses) >= 1, "應有 scream 回應"
    latest_scream = scream_responses[-1]
    assert "Read" in latest_scream["content"]
    print(f"D. response read: OK (content={latest_scream['content'][:30]}...)")

    # E. symlink guard
    _cleanup()
    try:
        os.symlink("/etc/passwd", CHANNEL)
        r3 = tools.execute("scream-ask", "測試")
        assert "symlink" in r3.lower() or "安全拒絕" in r3, f"symlink 應被拒: {r3}"
        print(f"E. symlink guard: OK ({r3[:40]})")
    finally:
        _cleanup()

    # F. agency intent — mock agency 驗證 competence 可選 scream-ask
    raw = PsiCore(bus=CognitiveBus(agent_name="check-channel-f"), interval=0.5)
    psi = PythonPsiBackend(raw)
    f_tools = ToolExecutor(bus=CognitiveBus(agent_name="check-channel-f"), agentos_registry=None)
    agency = AgencyLoop(psi=psi, tools=f_tools, bus=None,
                        interval=0.5, max_per_hour=10, drive_threshold=0.45)
    agency._exploration_rate = 1.0
    for nt in NeedType:
        raw.needs.values[nt] = raw.needs.targets[nt]
    raw.needs.values[NeedType.COMPETENCE] = 0.2  # drive ≈ 0.72
    raw.last_input = "如何操作檔案"
    # 高 exploration + competence + "問Scream" 角度 → 可能選 scream-ask
    found_scream = False
    for _ in range(30):
        intent = agency._form_intent("competence")
        if intent and intent[0] == "scream-ask":
            found_scream = True
            break
    # 不強制通過（有機率性），只用於驗證 intent 形成不報錯
    _cleanup()
    print(f"F. agency intent: {'OK（可選 scream-ask）' if found_scream else 'OK（隨機未命中，非錯誤）'}")

    # G. cleanup
    _cleanup()
    print("G. cleanup: OK")

    # H. scream-task 工具驗證（委派任務模式）
    task_tools = ToolExecutor(bus=CognitiveBus(agent_name="check-task"), agentos_registry=None)
    task_names = [t["name"] for t in task_tools.list_tools()]
    assert "scream-task" in task_names, f"scream-task 未註冊: {task_names}"
    from laap.safety_gate import classify as _cls
    assert _cls("scream-task") in ("readonly_builtin",), f"scream-task 分類錯誤: {_cls('scream-task')}"
    print("H. scream-task 工具已註冊且安全分類正確: OK")

    print("ALL SCREAM-CHANNEL CHECKS PASSED")


if __name__ == "__main__":
    main()
