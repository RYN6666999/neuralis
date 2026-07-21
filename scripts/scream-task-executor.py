#!/usr/bin/env python3
"""⚠️ 已棄用 — 由 agentos-aris-bridge.py 取代。

任務通道監聽器（Scream 端背景精靈）— 偵測 type='task' → 執行 → 寫回 type='result'。

此檔案保留向後相容。新功能請使用 AgentOS Aris Bridge：
  python3 ~/Developer/neuralis/scripts/agentos-aris-bridge.py [--daemon]

啟動：python3 ~/Developer/neuralis/scripts/scream-task-executor.py &
或由 scream-monitor.sh 自動 spawn。

v0：執行階段為模擬結果（標記 TODO 處）。v1：改為實際呼叫 Scream 工具。
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

# 沙箱憑證隔離白名單：subprocess 只繼承這些，API key 等一律不外洩給 cat/curl/bash
_SAFE = frozenset({"PATH", "HOME", "USER", "SHELL", "TERM", "LANG", "LC_ALL", "TMPDIR"})


def _clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if k in _SAFE}

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

    v1：實際呼叫 Scream 工具（Read/Write/Bash/WebSearch），不再回模擬結果。
    安全限制：寫入操作受 safety_gate path-DENY 保護，禁止修改 laap/ 目錄。

    支援的工具類型：
    - read：讀取檔案（subprocess cat / Read tool）
    - write：寫入檔案（subprocess 寫入，但阻擋 laap/ 路徑）
    - search：網頁搜尋（subprocess curl）
    - bash：執行 shell 指令
    """
    desc = entry.get("content", "")
    context = entry.get("context", {})
    task_type = _classify_task(desc)

    try:
        if task_type == "read":
            result = _TOOLS["read"](desc)
        elif task_type == "write":
            result = _TOOLS["write"](desc)
        elif task_type == "search":
            result = _TOOLS["search"](desc)
        elif task_type == "bash":
            result = _TOOLS["bash"](desc)
        else:
            result = {"success": True, "output": f"[Scream] 已接收任務，但無法分類: {desc[:80]}"}
    except Exception as e:
        result = {"success": False, "error": str(e)}

    return {
        "ts": time.time(),
        "direction": "scream→aris",
        "type": "result",
        "content": result.get("output", result.get("error", "?")),
        "context": {
            "request_ts": entry["ts"],
            "task_index": context.get("task_index", 0),
            "task_type": task_type,
            "success": result.get("success", False),
        },
    }


# ── 工具路由 ──────────────────────────────────────────────

# 嘗試從 safety_gate 共用 path-DENY 保護規則
# fallback：若 import 失敗（standalone 執行），使用內建複製
_PROTECTED_FRAGMENTS: list[str] | None = None
try:
    import sys as _sys
    _laap_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _laap_root not in _sys.path:
        _sys.path.insert(0, _laap_root)
    from laap.safety_gate import _protected_fragments as _pf
    _PROTECTED_FRAGMENTS = _pf()
except Exception:
    _PROTECTED_FRAGMENTS = ["laap/"]


def _is_path_protected(path: str) -> bool:
    """檢查路徑是否受 path-DENY 保護（共用 safety_gate 規則）。"""
    path_abs = os.path.abspath(os.path.expanduser(path))
    if _PROTECTED_FRAGMENTS:
        for frag in _PROTECTED_FRAGMENTS:
            if frag in path_abs:
                return True
    return False


def _classify_task(desc: str) -> str:
    """根據任務描述分類工具類型。"""
    desc_lower = desc.lower()
    if any(kw in desc_lower for kw in ("搜尋", "search", "查詢", "查", "找", "search")):
        return "search"
    if any(kw in desc_lower for kw in ("寫入", "write", "存檔", "建立", "新增", "修改",
                                        "編輯", "edit", "create")):
        return "write"
    if any(kw in desc_lower for kw in ("讀取", "read", "檢查", "看", "打開", "open",
                                        "cat", "查看")):
        return "read"
    if any(kw in desc_lower for kw in ("執行", "run", "bash", "shell", "command",
                                        "指令", "運行")):
        return "bash"
    return "unknown"


_TOOLS = {
    "read": lambda d: _run(["cat",_xp(d)],2000,10) if _xp(d) else {"success":False,"error":"no path"},
    "write": lambda d: _wr(d),
    "search": lambda d: _run(["curl","-s","-L","--max-time","10",
      f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(_xq(d) or '')}"],2000,15) if _xq(d) else {"success":False,"error":"no query"},
    "bash": lambda d: _bash(d),
}

def _run(cmd, limit, timeout, shell=False):
    try:
        r = subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,env=_clean_env(),shell=shell)
        out = (r.stdout+r.stderr)[:limit]
        return {"success":r.returncode==0,"output":out,"code":r.returncode}
    except subprocess.TimeoutExpired: return {"success":False,"error":"timeout"}
    except Exception as e: return {"success":False,"error":str(e)}

def _xp(d):
    import re
    for p in [r'`([^`]+)`',r'(?:路徑|path|file|檔案)[：:\s]*([/\w\.\-_]+)']:
        m = re.search(p, d)
        if m: return os.path.abspath(os.path.expanduser(m.group(1)))
    return None

def _xq(d):
    import re
    m = re.search(r'(?:搜尋|search|查詢|查|找)[：:\s]*(.+)', d)
    return m.group(1).strip()[:100] if m else d[:100] if len(d)>10 else None

def _wr(d):
    path = _xp(d)
    if not path: return {"success":False,"error":"no path"}
    path = os.path.abspath(os.path.expanduser(path))
    if _is_path_protected(path): return {"success":False,"error":f"path-DENY: {path}"}
    import re
    m = re.search(r'```(?:\w+)?\n(.*?)```', d, re.DOTALL)
    content = m.group(1).strip() if m else None
    if not content: return {"success":False,"error":"no content"}
    try:
        Path(path).write_text(content)
        return {"success":True,"output":f"wrote {path} ({len(content)}b)"}
    except Exception as e: return {"success":False,"error":str(e)}

def _bash(d):
    import re
    m = re.search(r'```(?:bash|sh|shell)?\n(.*?)```', d, re.DOTALL)
    cmd = m.group(1).strip() if m else None
    if not cmd:
        m = re.search(r'`([^`]+)`', d)
        cmd = m.group(1).strip() if m else None
    if not cmd: return {"success":False,"error":"no command"}
    for bad in ["rm -rf /","mkfs","dd if=",":(){ :|:& };:"]:
        if bad in cmd: return {"success":False,"error":"dangerous command blocked"}
    return _run(cmd,3000,30,shell=True)


# 這些已內聯到 _TOOLS / _run / _xp / _xq / _wr / _bash 中
# def _extract_path ... removed by Ponytail


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