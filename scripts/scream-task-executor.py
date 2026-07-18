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


def _tool_read(desc: str) -> dict:
    """讀取檔案 — 透過 subprocess cat 實作。"""
    import subprocess
    # 從描述中猜測檔案路徑
    path = _extract_path(desc)
    if not path:
        return {"success": False, "error": "無法從描述中判斷要讀取的檔案"}

    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        return {"success": False, "error": f"檔案不存在: {path}"}

    try:
        result = subprocess.run(
            ["cat", path], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            output = result.stdout[:2000]  # 限制輸出長度
            return {"success": True, "output": output, "path": path, "truncated": len(result.stdout) > 2000}
        else:
            return {"success": False, "error": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "讀取超時"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _tool_write(desc: str) -> dict:
    """寫入檔案 — 受 path-DENY 保護，禁止修改受保護路徑。"""
    import subprocess
    path = _extract_path(desc)
    if not path:
        return {"success": False, "error": "無法從描述中判斷要寫入的檔案"}

    path = os.path.abspath(os.path.expanduser(path))

    # path-DENY：共用 safety_gate 保護規則
    if _is_path_protected(path):
        return {
            "success": False,
            "error": f"path-DENY：禁止修改受保護路徑 ({path})",
        }

    # 檢查父目錄是否存在
    parent = os.path.dirname(path)
    if not os.path.exists(parent):
        return {"success": False, "error": f"父目錄不存在: {parent}"}

    # 從描述中猜測內容（簡化版）
    content = _extract_content(desc)
    if not content:
        return {"success": False, "error": "無法從描述中判斷要寫入的內容"}

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".tmp") as tf:
            tf.write(content)
            tmp_path = tf.name
        subprocess.run(["cp", tmp_path, path], check=True, timeout=5)
        os.unlink(tmp_path)
        return {"success": True, "output": f"已寫入 {path} ({len(content)} bytes)", "path": path}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "寫入超時"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _tool_search(desc: str) -> dict:
    """網頁搜尋 — 透過 curl 或 web-search 工具。"""
    import subprocess
    query = _extract_query(desc)
    if not query:
        return {"success": False, "error": "無法從描述中判斷搜尋關鍵字"}

    try:
        # 使用 DuckDuckGo lite（無需 API key）
        url = f"https://lite.duckduckgo.com/lite/?q={_url_encode(query)}"
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "10", url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout:
            # 簡單萃取文字（去除 HTML tag 是升級路徑）
            text = result.stdout[:2000]
            return {"success": True, "output": text[:2000], "query": query, "truncated": len(text) > 2000}
        else:
            return {"success": True, "output": f"搜尋完成: {query}（無詳細結果，可透過頻道回傳更多資訊）",
                    "query": query}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "搜尋超時"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _tool_bash(desc: str) -> dict:
    """執行 Shell 指令 — 限制執行時間。"""
    import subprocess
    import shlex
    cmd = _extract_command(desc)
    if not cmd:
        return {"success": False, "error": "無法從描述中判斷要執行的指令"}

    # 安全檢查：禁止危險指令
    dangerous = ["rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:"]
    for d in dangerous:
        if d in cmd:
            return {"success": False, "error": f"指令包含危險操作，已阻擋: {d}"}

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        output = (result.stdout + result.stderr)[:3000]
        return {
            "success": result.returncode == 0,
            "output": output,
            "exit_code": result.returncode,
            "truncated": len(result.stdout + result.stderr) > 3000,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "指令執行超時 (30s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 輔助函數 ──────────────────────────────────────────────

def _extract_path(desc: str) -> str | None:
    """從任務描述中猜測檔案路徑。"""
    import re
    # 優先匹配常見路徑模式
    patterns = [
        r"(?:檔案|文件|file|path|路徑)[：:\s]*([/\w\.\-_]+)",
        r"(?:讀取|讀|read|open|cat|查看|打開|修改|編輯|write|寫入)\s+([/\w\.\-_]+)",
        r"`([^`]+)`",  # backtick 中的路徑
    ]
    for pat in patterns:
        m = re.search(pat, desc)
        if m:
            return m.group(1).strip()
    return None


def _extract_content(desc: str) -> str | None:
    """從任務描述中猜測要寫入的內容。"""
    import re
    # 匹配 ```code block```
    m = re.search(r"```(?:\w+)?\n(.*?)```", desc, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 匹配 「內容：...」
    m = re.search(r"(?:內容|content)[：:\s]*(.+)", desc)
    if m:
        return m.group(1).strip()
    return None


def _extract_query(desc: str) -> str | None:
    """從任務描述中猜測搜尋關鍵字。"""
    import re
    m = re.search(r"(?:搜尋|搜索|search|查詢|查|找)[：:\s]*(.+)", desc)
    if m:
        return m.group(1).strip()
    # fallback: 截取描述的前 100 字
    if len(desc) > 10:
        return desc.strip()[:100]
    return None


def _extract_command(desc: str) -> str | None:
    """從任務描述中猜測要執行的指令。"""
    import re
    # 匹配 ```bash block```
    m = re.search(r"```(?:bash|sh|shell)?\n(.*?)```", desc, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 匹配 `inline command`
    m = re.search(r"`([^`]+)`", desc)
    if m:
        return m.group(1).strip()
    # 匹配 「執行：...」
    m = re.search(r"(?:執行|執行|run|bash)[：:\s]*(.+)", desc)
    if m:
        return m.group(1).strip()
    return None


def _url_encode(text: str) -> str:
    """URL encode。"""
    import urllib.parse
    return urllib.parse.quote(text)


def _format_result(result: dict, desc: str) -> str:
    """格式化工具執行結果為 Aris 可讀的文字。"""
    if result.get("success"):
        output = result.get("output", "")
        truncated = result.get("truncated", False)
        suffix = "\n...(輸出截斷)" if truncated else ""
        return f"[Scream] 任務完成 ✅\n{output[:1500]}{suffix}"
    else:
        error = result.get("error", "未知錯誤")
        return f"[Scream] 任務失敗 ❌\n錯誤: {error}"



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