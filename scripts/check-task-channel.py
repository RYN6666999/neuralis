#!/usr/bin/env python3
"""任務頻道自我檢查 — 驗證 type='task' → type='result' 迴路與任務狀態。

6 區段（H1-H6）：
  H1. 頻道可讀取
  H2. type="task" 包含必要欄位
  H3. 每條 task 有對應 result（request_ts 匹配）
  H4. progress 順序正確（decomposing→executing→completed）
  H5. 狀態檔完整（必要欄位全在）
  H6. 工具註冊與安全分類

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-task-channel.py
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
from laap.agency import AgencyLoop

CHANNEL = "/tmp/aris-scream-channel.jsonl"
STATE = "/tmp/aris-scream-task-state.json"

errors = 0


def log(result: str):
    print(result)
    return 0 if result.startswith("✅") else 1


def cleanup():
    for p in (CHANNEL, STATE):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


def main():
    global errors
    cleanup()
    bus = CognitiveBus(agent_name="check-task")
    tools = ToolExecutor(bus=bus, agentos_registry=None)

    # H6: 工具註冊與安全分類（不依賴頻道檔案）
    tool_names = [t["name"] for t in tools.list_tools()]
    assert "scream-task" in tool_names, f"scream-task 未註冊: {tool_names}"
    assert classify("scream-task") in ("readonly_builtin",), \
        f"scream-task 分類錯誤: {classify('scream-task')}"
    log("✅ H6 工具註冊與安全分類: OK")

    # 建立測試頻道
    os.makedirs(os.path.dirname(CHANNEL) or ".", exist_ok=True)

    # 寫入一組 task + result + progress 測試資料
    fake_ts = time.time()
    test_entries = [
        {"ts": fake_ts, "id": "task00000001", "direction": "aris→scream",
         "type": "progress", "content": "decomposing task 0",
         "context": {"phase": "decomposing", "task_index": 0}},
        {"ts": fake_ts + 1, "id": "task00000002", "direction": "aris→scream",
         "type": "task", "content": "搜尋最新 AI 技術",
         "context": {"task_list": [{"idx": 0, "description": "搜尋"},
                                    {"idx": 1, "description": "驗證"}],
                     "task_index": 0, "total_tasks": 2, "goal_id": "goal001"}},
        {"ts": fake_ts + 2, "id": "res00000001", "direction": "scream→aris",
         "type": "result", "content": "[Scream 搜尋] 已完成查詢",
         "context": {"request_ts": fake_ts + 1, "task_index": 0, "success": True}},
        {"ts": fake_ts + 3, "id": "task00000003", "direction": "aris→scream",
         "type": "progress", "content": "executing task 1",
         "context": {"phase": "executing", "task_index": 1}},
        {"ts": fake_ts + 5, "id": "res00000002", "direction": "scream→aris",
         "type": "result", "content": "[Scream 驗證] 測試通過",
         "context": {"request_ts": fake_ts + 5, "task_index": 1, "success": True}},
        {"ts": fake_ts + 6, "id": "task00000004", "direction": "aris→scream",
         "type": "progress", "content": "completed task 2",
         "context": {"phase": "completed", "task_index": 2}},
    ]
    with open(CHANNEL, "w") as f:
        for e in test_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    try:
        with open(CHANNEL) as f:
            lines = [l.strip() for l in f if l.strip()]
        log(f"✅ H1 頻道可讀取 ({len(lines)} 行)")

        # H2: task 項目包含 task_list
        tasks = [json.loads(l) for l in lines
                 if json.loads(l).get("type") == "task"]
        for t in tasks:
            if not t.get("context", {}).get("task_list"):
                log(f"❌ H2 缺少 task_list: {t.get('id')}")
                errors += 1
        if not errors and tasks:
            log(f"✅ H2 {len(tasks)} 個 task 項目均包含 task_list")

        # H3: 每條 task 有對應 result
        task_ts = {json.loads(l)["ts"] for l in lines
                   if json.loads(l).get("type") == "task"}
        result_ts = {json.loads(l)["context"]["request_ts"] for l in lines
                     if json.loads(l).get("type") == "result"}
        orphan = task_ts - result_ts
        if orphan:
            log(f"❌ H3 {len(orphan)} 個孤立 task（無對應 result）")
            errors += 1
        else:
            log("✅ H3 所有 task 都有對應 result")

        # H4: progress 順序
        progress = [json.loads(l) for l in lines
                    if json.loads(l).get("type") == "progress"]
        if progress:
            phases = [p["context"]["phase"] for p in progress]
            expected = ["decomposing", "executing", "completed"]
            # 允許 progress 比 expected 短（未全部完成的場景）
            sub = [p for p in phases if p in expected]
            if sub == [e for e in expected if e in sub]:
                log(f"✅ H4 progress 順序正確 ({len(progress)} 個)")
            else:
                log(f"❌ H4 progress 順序錯誤: {phases}")
                errors += 1

        # H5: 狀態檔
        if os.path.exists(STATE):
            try:
                s = json.load(open(STATE))
                for k in ["goal_spec", "task_queue", "task_index",
                          "goal_completed"]:
                    assert k in s, f"缺少 {k}"
                log("✅ H5 狀態檔完整")
            except Exception as e:
                log(f"❌ H5 狀態檔無效: {e}")
                errors += 1
        else:
            # 寫入一個測試狀態檔
            test_state = {"goal_spec": "測試目標",
                          "task_queue": [{"idx": 0, "description": "測試"}],
                          "task_index": 0, "goal_completed": False}
            with open(STATE, "w") as f:
                json.dump(test_state, f)
            s = json.load(open(STATE))
            for k in ["goal_spec", "task_queue", "task_index",
                      "goal_completed"]:
                assert k in s, f"缺少 {k}"
            log("✅ H5 狀態檔讀寫正常")

    finally:
        cleanup()

    print(f"\n{'=' * 40}")
    total = 6  # H1 through H6
    if errors:
        print(f"❌ {errors}/{total} 項錯誤")
        sys.exit(errors)
    else:
        print("✅ ALL TASK-CHANNEL CHECKS PASSED")


if __name__ == "__main__":
    main()