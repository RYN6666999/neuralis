#!/usr/bin/env python3
"""任務通道監聽器（Scream 端背景精靈）— 偵測 type='task' → 執行 → 寫回 type='result'。

啟動：python3 ~/Developer/neuralis/scripts/scream-task-executor.py &
或由 scream-monitor.sh 自動 spawn。

v0：執行階段為模擬結果（標記 TODO 處）。v1：改為實際呼叫 Scream 工具。
"""
from __future__ import annotations

import json
import os
import time
import uuid

CHANNEL = "/tmp/aris-scream-channel.jsonl"
PROCESSED = "/tmp/aris-scream-processed-ids.json"
LOCK = "/tmp/aris-scream-task-lock"
API_URL = "http://localhost:11546/v1/chat/completions"
POLL_INTERVAL = 1.0


def acquire_lock() -> bool:
    if os.path.exists(LOCK):
        age = time.time() - os.path.getmtime(LOCK)
        if age < 30:  # 30s stale timeout
            return False
    with open(LOCK, "w") as f:
        f.write(str(time.time()))
    return True


def release_lock():
    try:
        os.remove(LOCK)
    except FileNotFoundError:
        pass


def load_processed() -> set:
    try:
        with open(PROCESSED) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_processed(ids: set):
    with open(PROCESSED, "w") as f:
        json.dump(list(ids), f)


def execute_task(entry: dict) -> dict:
    """根據任務描述執行 Scream 動作。回傳結果 dict。

    TODO v1: 改為實際呼叫 Scream 工具（Read/Write/Bash/WebSearch）。
    目前 v0 為模擬結果，讓 Aris 端的端到端流程能驗證。
    """
    desc = entry.get("content", "")
    # 簡單路由：根據內容關鍵字決定回應
    if any(kw in desc for kw in ("搜尋", "search", "查詢", "查")):
        summary = f"[Scream 搜尋] 已完成查詢: {desc[:80]}"
    elif any(kw in desc for kw in ("寫入", "write", "存檔", "建立")):
        summary = f"[Scream 寫入] 已建立/更新: {desc[:80]}"
    elif any(kw in desc for kw in ("讀取", "read", "檢查")):
        summary = f"[Scream 讀取] 已完成讀取: {desc[:80]}"
    else:
        summary = f"[Scream 執行] 任務完成: {desc[:80]}"
    return {
        "ts": time.time(),
        "direction": "scream→aris",
        "type": "result",
        "content": summary,
        "context": {
            "request_ts": entry["ts"],
            "task_index": entry.get("context", {}).get("task_index", 0),
            "success": True,
        },
    }


def post_to_aris(result: dict):
    """將結果送回 Aris API，讓 Aris 即時觸發 psi + satisfaction。"""
    import urllib.request
    payload = json.dumps({
        "model": "laap-core",
        "messages": [
            {"role": "system",
             "content": "Scream 回報了任務結果。"},
            {"role": "user",
             "content": f"Scream 任務結果: {json.dumps(result, ensure_ascii=False)}"},
        ],
        "max_tokens": 100,
    }).encode()
    try:
        req = urllib.request.Request(
            API_URL, data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Aris 下次輪詢時會從頻道收到結果


def main():
    processed = load_processed()
    print(f"[scream-task-executor] 啟動 (已處理 {len(processed)} 個 ID)")
    while True:
        if not acquire_lock():
            time.sleep(POLL_INTERVAL)
            continue
        try:
            if not os.path.exists(CHANNEL):
                time.sleep(POLL_INTERVAL)
                continue
            with open(CHANNEL) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (entry.get("direction") == "aris→scream"
                            and entry.get("type") == "task"
                            and entry.get("id") not in processed):
                        result = execute_task(entry)
                        with open(CHANNEL, "a") as fw:
                            fw.write(
                                json.dumps(result, ensure_ascii=False) + "\n")
                        post_to_aris(result)
                        processed.add(entry["id"])
                        save_processed(processed)
                        print(f"[scream-task-executor] 處理 task {entry['id'][:8]}: "
                              f"{entry.get('content', '')[:40]}")
        except FileNotFoundError:
            pass
        finally:
            release_lock()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()