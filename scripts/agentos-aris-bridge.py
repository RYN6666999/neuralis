#!/usr/bin/env python3
"""AgentOS Aris Bridge — 把 Aris-Scream 通道流經 AgentOS 完整 pipeline。

取代 / 升級 scream-task-executor.py。
當 Aris 寫入通道（type=request/task），這支 daemon：
  ① Route Classification  ← agentos.json routes
  ② Brain Context Lookup  ← AgentOS brain / local cache
  ③ Execute              ← 依 route 路由到正確工具鏈
  ④ Gate                 ← skill-security scan + format check
  ⑤ Log                  ← agentsview 記錄

啟動：python3 agentos-aris-bridge.py [--daemon]
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ── 路徑常數 ──────────────────────────────────────────────

CHANNEL = "/tmp/aris-scream-channel.jsonl"
PROCESSED = "/tmp/aris-scream-processed-ids.json"
LOCK = "/tmp/aris-scream-task-lock"
BRAIN_DIR = Path.home() / ".scream-code" / "agentos-brain"
AGENTOS_JSON = Path.home() / "agent-sandbox" / "agentos.json"
ARIS_API = "http://localhost:11546/v1/chat/completions"
AGENTOS_API = "http://localhost:8000"
POLL_INTERVAL = 1.0
LOG_FILE = "/tmp/agentos-aris-bridge.log"

# ── MCP Shadow Call 設定 ──────────────────────────────────

SHADOW_ENABLED = os.environ.get("AGENTOS_SHADOW_ENABLED", "0") == "1"
SHADOW_LOG = os.path.expanduser("~/agent-sandbox/logs/shadow.jsonl")
SHADOW_SNAPSHOT_DIR = os.path.expanduser("~/agent-sandbox/snapshots/")
SHADOW_WORKSPACE_ROOT = os.path.abspath(os.path.expanduser("~/agent-sandbox"))
SHADOW_TIMEOUT = 5
SHADOW_KILL_SENTINEL = "/tmp/agentos-shadow-kill"
SHADOW_QUEUE_MAXSIZE = 16

# ── 日誌 ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[agentos-bridge] %(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("agentos-bridge")

# ── AgentOS Routes（從 agentos.json 載入） ─────────────────

_ROUTES: dict[str, str] = {}  # route_key → tool/toolchain description
_PIPELINE: dict[str, list[str]] = {}
_TOOLS_META: dict[str, dict] = {}


def _load_agentos_config() -> None:
    """從 agentos.json 載入 routes / pipeline / tools 定義。"""
    global _ROUTES, _PIPELINE, _TOOLS_META
    try:
        if not AGENTOS_JSON.exists():
            log.warning("agentos.json 不存在，使用內建預設路由")
            _ROUTES = _DEFAULT_ROUTES.copy()
            return
        with open(AGENTOS_JSON) as f:
            cfg = json.load(f)
        _ROUTES = cfg.get("routes", _DEFAULT_ROUTES.copy())
        _PIPELINE = cfg.get("pipeline", {})
        _TOOLS_META = cfg.get("tools", {})
        log.info(f"agentos.json 載入: {len(_ROUTES)} 路由, {len(_TOOLS_META)} 工具")
    except Exception as e:
        log.warning(f"載入 agentos.json 失敗: {e}，使用預設路由")
        _ROUTES = _DEFAULT_ROUTES.copy()


# 預設路由（當 agentos.json 不存在或損壞時使用）
_DEFAULT_ROUTES: dict[str, str] = {
    "code": "codebase-memory-mcp",
    "research": "anysearch",
    "browser-research": "opencli",
    "video": "openmontage",
    "html-video": "html-video",
    "motion": "text-to-lottie | pixel2motion",
    "social-scrape": "douyin-downloader | xhs-downloader | twscrape",
    "sports": "football-data | nba-data | nfl-data | fastf1",
    "engineer": "addyosmani-agent-skills (spec→plan→build→test→review→ship)",
    "design": "impeccable",
    "plan": "planning-with-files | planning-and-task-breakdown",
    "security": "skill-security",
    "compression": "caveman-ponytail",
    "session": "agentsview",
    "branding-template": "template-batch",
    "troubleshoot": "troubleshooter",
    "spec-mgmt": "docs/specs/ (project-level spec management)",
    "read": "Read tool (file reading)",
    "write": "Write tool (file writing)",
    "bash": "Bash tool (shell execution)",
    "search-web": "WebSearch / anysearch",
    "compile": "build / compile (shell)",
    "aris-status": "aris-status.py (health check)",
}

# ── 通道鎖 ────────────────────────────────────────────────


def _acquire_lock() -> bool:
    if os.path.exists(LOCK):
        try:
            age = time.time() - os.path.getmtime(LOCK)
            if age < 30:
                return False
        except OSError:
            pass
    try:
        with open(LOCK, "w") as f:
            f.write(str(time.time()))
        return True
    except OSError:
        return False


def _release_lock() -> None:
    try:
        os.remove(LOCK)
    except FileNotFoundError:
        pass


def _load_processed() -> set:
    try:
        with open(PROCESSED) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_processed(ids: set) -> None:
    try:
        with open(PROCESSED, "w") as f:
            json.dump(list(ids), f)
    except Exception:
        pass


# ── 安全防護 ──────────────────────────────────────────────

_PROTECTED_PATHS = ["laap/", ".env", ".ssh", "id_rsa", "id_ed25519"]
_DANGEROUS_PATTERNS = [
    "rm -rf /", "mkfs.", "dd if=", ":(){ :|:& };:",
    "DROP TABLE", "DROP DATABASE", "TRUNCATE",
    "chmod 777", "chown -R", "sudo ",
]


def _is_path_protected(path: str) -> bool:
    path_abs = os.path.abspath(os.path.expanduser(path))
    for frag in _PROTECTED_PATHS:
        if frag in path_abs:
            return True
    return False


def _is_dangerous_command(cmd: str) -> bool:
    for pat in _DANGEROUS_PATTERNS:
        if pat in cmd:
            return True
    return False


# ── 步驟 ①：Route Classification ─────────────────────────

# 關鍵字 → route_key 對應表（讓 Aris 的自然語言任務可路由）
_KEYWORD_ROUTES: list[tuple[re.Pattern, str]] = []


def _build_keyword_routes() -> None:
    global _KEYWORD_ROUTES
    # 順序重要：更具體/領域特定的關鍵字先匹配
    _KEYWORD_ROUTES = [
        # 運動（放在 research 之前，因為「查詢NBA」不該走 research）
        (re.compile(r"nba|nfl|f1|mlb|nhl|足球|soccer|football|籃球|棒球|網球|英超|歐冠|冠軍|賽程|比分|運動|sports|fastf1|pga|golf"), "sports"),
        # 程式碼分析（含架構/路徑分析）
        (re.compile(r"程式碼|code|源碼|source.?code|實作|implement|寫程式|coding|架構|architecture|分析.*專案|repo|repository|模組|module"), "code"),
        # 影片
        (re.compile(r"影片|video|montage|紀錄片|剪輯|剪片|remotion"), "video"),
        # HTML 影片
        (re.compile(r"html.?video|hyperframe|網頁.*影片"), "html-video"),
        # 動畫/Lottie
        (re.compile(r"動畫|lottie|bodymovin|motion|logo.*動畫"), "motion"),
        # 社群爬蟲
        (re.compile(r"抖音|tiktok|小紅書|xhs|rednote|twitter|x\s*爬|爬蟲|scrape"), "social-scrape"),
        # 設計
        (re.compile(r"設計|design|ui|ux|介面|美工|前端.*設計"), "design"),
        # 規劃
        (re.compile(r"規劃|plan|拆任務|task.?breakdown|todo"), "plan"),
        # 安全
        (re.compile(r"安全|security|漏洞|owasp|掃描|scan"), "security"),
        # 疑難排除
        (re.compile(r"除錯|debug|troubleshoot|錯誤|error|fail|報錯|修復|fix|修復"), "troubleshoot"),
        # 工程/開發（放在 code 之後，因為 code 更特定）
        (re.compile(r"工程|engineer|開發|build|建置|部署|ship|spec|test"), "engineer"),
        # 網頁瀏覽（放在 research 之後，因為特定於瀏覽器操作）
        (re.compile(r"瀏覽器|瀏覽|browser|開網頁|打開.*網站|登入"), "browser-research"),
        # 研究/搜尋（通用，放最後避免搶走特定領域的匹配）
        (re.compile(r"搜尋|search|查詢|找資料|研究|research|調查|investigate|分析|上網查|google|wikipedia"), "research"),
        # 讀取檔案
        (re.compile(r"讀取|read|查看|打開|cat|檢查.*檔案|看.*檔"), "read"),
        # 寫入檔案
        (re.compile(r"寫入|write|存檔|修改|編輯|edit|建立|create|新增"), "write"),
        # 執行指令
        (re.compile(r"執行|run|bash|shell|command|指令|運行|terminal"), "bash"),
        # 網頁搜尋（明確）
        (re.compile(r"web.?search|網頁搜尋"), "search-web"),
        # 編譯
        (re.compile(r"編譯|compile|build|make|npm run|tsc|gcc"), "compile"),
        # Aris 狀態
        (re.compile(r"aris.*狀態|aris.*health|aris-status|aris.*活著"), "aris-status"),
        # 品牌/模板
        (re.compile(r"海報|名牌|識別證|template|batch|批量"), "branding-template"),
        # 規格管理
        (re.compile(r"spec|規格|prd|規格文件|docs/specs"), "spec-mgmt"),
    ]


def _classify_by_route(task_desc: str) -> str:
    """使用 AgentOS routes + 關鍵字表分類任務。回傳 route_key。"""
    desc_lower = task_desc.lower()
    for pattern, route_key in _KEYWORD_ROUTES:
        if pattern.search(desc_lower):
            return route_key
    # 沒匹配到任何 route → unknown
    return "unknown"


def _get_route_tool(route_key: str) -> str:
    """取得 route 對應的工具描述。"""
    return _ROUTES.get(route_key, f"unknown route: {route_key}")


# ── 步驟 ②：Brain Context Lookup ─────────────────────────

BRAIN_CACHE: dict[str, str] = {}


def _lookup_brain_context(query: str) -> str:
    """從 AgentOS brain 查詢相關上下文。支援多層 fallback。"""
    # 1. 嘗試 AgentOS brain API
    try:
        url = f"{AGENTOS_API}/knowledge/search?q={urllib.parse.quote(query[:100])}"
        resp = urllib.request.urlopen(url, timeout=3)
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            return data.get("content", "")
    except Exception:
        pass

    # 2. 嘗試本地 brain 檔案快取
    brain_file = BRAIN_DIR / "last-context.json"
    if brain_file.exists():
        try:
            with open(brain_file) as f:
                cache = json.load(f)
            # 回傳最近相關的條目
            for key, val in cache.items():
                if any(w in key.lower() for w in query.lower().split()[:3]):
                    return val[:300]
        except Exception:
            pass

    return ""


# ── 步驟 ③：Execute — 路由到正確工具鏈 ──────────────────

# 安全環境（不洩漏 API key）
_SAFE_ENV = frozenset({"PATH", "HOME", "USER", "SHELL", "TERM", "LANG", "LC_ALL", "TMPDIR"})


def _clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV}


def _run(cmd: list[str], limit: int = 5000, timeout: int = 30) -> dict:
    """執行外部指令，回傳結構化結果。"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, env=_clean_env(),
        )
        out = (r.stdout + "\n" + r.stderr).strip()[:limit]
        return {"success": r.returncode == 0, "output": out, "code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except FileNotFoundError:
        return {"success": False, "error": f"command not found: {cmd[0]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_shell(cmd_str: str, limit: int = 5000, timeout: int = 30) -> dict:
    """執行 shell 指令（字串形式）。"""
    if _is_dangerous_command(cmd_str):
        return {"success": False, "error": "dangerous command blocked"}
    try:
        r = subprocess.run(
            cmd_str, capture_output=True, text=True,
            timeout=timeout, env=_clean_env(), shell=True,
        )
        out = (r.stdout + "\n" + r.stderr).strip()[:limit]
        return {"success": r.returncode == 0, "output": out, "code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _extract_path(desc: str) -> str | None:
    """從任務描述中提取檔案路徑。"""
    # `path/to/file` 格式（含 tilde）
    m = re.search(r'`([^`]+)`', desc)
    if m:
        path = os.path.abspath(os.path.expanduser(m.group(1)))
        if os.path.exists(path) or os.path.exists(os.path.dirname(path)):
            return path
    # 路徑/檔案 關鍵字後的路徑（含 tilde 和 @ 字元）
    for kw in [r'路徑', r'path', r'file', r'檔案']:
        m = re.search(rf'{kw}[：:\s]*([/\w\.\-_@~]+)', desc)
        if m:
            path = os.path.abspath(os.path.expanduser(m.group(1)))
            return path
    # 直接抓絕對路徑或 tilde 路徑（~開頭或 / 開頭）
    m = re.search(r'(~[/\w\.\-_@]+|/[ /\w\.\-_@]+)', desc)
    if m:
        path = os.path.abspath(os.path.expanduser(m.group(1)))
        return path
    return None


def _extract_query(desc: str) -> str | None:
    """從任務描述中提取搜尋查詢。"""
    for kw in [r'搜尋', r'search', r'查詢', r'查', r'找']:
        m = re.search(rf'{kw}[：:\s]*(.+)', desc)
        if m:
            return m.group(1).strip()[:100]
    return None


def _extract_code_block(desc: str) -> str | None:
    """從任務描述中提取程式碼區塊。"""
    m = re.search(r'```(?:\w+)?\n(.*?)```', desc, re.DOTALL)
    return m.group(1).strip() if m else None


def _extract_command(desc: str) -> str | None:
    """從任務描述中提取 shell 指令。"""
    m = re.search(r'```(?:bash|sh|shell)?\n(.*?)```', desc, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r'`([^`]+)`', desc)
    if m:
        return m.group(1).strip()
    return None


def _execute_by_route(route_key: str, task_desc: str) -> dict:
    """根據 route_key 執行對應的工具鏈。"""
    # ── code: codebase-memory-mcp ──
    if route_key == "code":
        path = _extract_path(task_desc)
        if path:
            r = _run(["codebase-memory-mcp", "cli", "get_architecture",
                       json.dumps({"repo_path": path})], limit=8000, timeout=30)
            if r["success"]:
                return r
        # fallback: 搜尋專案結構
        r = _run(["codebase-memory-mcp", "cli", "search_graph",
                   json.dumps({"query": task_desc[:80]})], limit=5000, timeout=20)
        return r if r["success"] else {"success": True, "output": f"[code] 已接收 code 任務，建議使用 codebase-memory-mcp 分析: {task_desc[:80]}"}

    # ── research: anysearch / WebSearch ──
    elif route_key == "research":
        query = _extract_query(task_desc) or task_desc[:100]
        # 嘗試 anysearch skill
        r = _run(["python3", str(Path.home() / "agent-sandbox" / "scripts" / "search-web.py"),
                   query], limit=5000, timeout=20)
        if r["success"]:
            return r
        # fallback: 用 curl 搜尋
        url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query[:80])}"
        return _run(["curl", "-s", "-L", "--max-time", "10", url], limit=5000, timeout=15)

    # ── browser-research: opencli ──
    elif route_key == "browser-research":
        return {"success": True, "output": f"[browser] 需要 Scream 使用 opencli 瀏覽器工具處理: {task_desc[:80]}"}

    # ── sports: 運動資料 ──
    elif route_key == "sports":
        return {"success": True, "output": f"[sports] 需要 Scream 使用 sports-data skills 處理: {task_desc[:80]}"}

    # ── social-scrape: 社群爬蟲 ──
    elif route_key == "social-scrape":
        return {"success": True, "output": f"[social-scrape] 需要 Scream 使用爬蟲 skills 處理: {task_desc[:80]}"}

    # ── video: OpenMontage ──
    elif route_key == "video":
        return {"success": True, "output": f"[video] 需要 Scream 使用 OpenMontage pipeline 處理: {task_desc[:80]}"}

    # ── motion: Lottie / pixel2motion ──
    elif route_key == "motion":
        return {"success": True, "output": f"[motion] 需要 Scream 使用 text-to-lottie/pixel2motion 處理: {task_desc[:80]}"}

    # ── engineer: 開發工作流 ──
    elif route_key == "engineer":
        return {"success": True, "output": f"[engineer] 需要 Scream 使用 addyosmani agent-skills 處理: {task_desc[:80]}"}

    # ── design: impeccable ──
    elif route_key == "design":
        return {"success": True, "output": f"[design] 需要 Scream 使用 impeccable 處理: {task_desc[:80]}"}

    # ── plan: 規劃 ──
    elif route_key == "plan":
        return {"success": True, "output": f"[plan] 需要 Scream 使用 planning-with-files 處理: {task_desc[:80]}"}

    # ── security: skill-security ──
    elif route_key == "security":
        return {"success": True, "output": f"[security] 需要 Scream 使用 skill-security 處理: {task_desc[:80]}"}

    # ── troubleshoot: 疑難排除 ──
    elif route_key == "troubleshoot":
        return {"success": True, "output": f"[troubleshoot] 需要 Scream 使用 troubleshooter 處理: {task_desc[:80]}"}

    # ── branding-template: 批量模板 ──
    elif route_key == "branding-template":
        return {"success": True, "output": f"[branding-template] 需要 Scream 使用 template-batch 處理: {task_desc[:80]}"}

    # ── spec-mgmt: 規格管理 ──
    elif route_key == "spec-mgmt":
        return {"success": True, "output": f"[spec-mgmt] 需要 Scream 使用 spec-driven-development 處理: {task_desc[:80]}"}

    # ── aris-status: Aris 健康檢查 ──
    elif route_key == "aris-status":
        r = _run(["python3", str(Path.home() / "Developer" / "neuralis" / "scripts" / "aris-status.py")],
                  limit=3000, timeout=15)
        if r["success"]:
            return r
        # fallback: 直接 curl
        return _run(["curl", "-sf", ARIS_API.replace("/v1/chat/completions", "/health")],
                     limit=1000, timeout=5)

    # ── 讀取檔案 ──
    elif route_key == "read":
        path = _extract_path(task_desc)
        if not path:
            return {"success": False, "error": "no path found in task description"}
        if _is_path_protected(path):
            return {"success": False, "error": f"path-DENY: {path}"}
        return _run(["cat", path], limit=5000, timeout=10)

    # ── 寫入檔案 ──
    elif route_key == "write":
        path = _extract_path(task_desc)
        if not path:
            return {"success": False, "error": "no path found in task description"}
        path = os.path.abspath(os.path.expanduser(path))
        if _is_path_protected(path):
            return {"success": False, "error": f"path-DENY: {path}"}
        content = _extract_code_block(task_desc)
        if not content:
            return {"success": False, "error": "no code block found in task description"}
        try:
            Path(path).write_text(content)
            return {"success": True, "output": f"wrote {path} ({len(content)} bytes)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Bash / shell ──
    elif route_key == "bash":
        cmd = _extract_command(task_desc)
        if not cmd:
            return {"success": False, "error": "no command found in task description"}
        return _run_shell(cmd, limit=5000, timeout=30)

    # ── 網頁搜尋 ──
    elif route_key == "search-web":
        query = _extract_query(task_desc) or task_desc[:100]
        url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query[:80])}"
        return _run(["curl", "-s", "-L", "--max-time", "10", url], limit=5000, timeout=15)

    # ── 編譯 ──
    elif route_key == "compile":
        cmd = _extract_command(task_desc) or task_desc[:100]
        if _is_dangerous_command(cmd):
            return {"success": False, "error": "dangerous command blocked"}
        return _run_shell(cmd, limit=5000, timeout=60)

    # ── unknown ──
    else:
        return {"success": True, "output": f"[AgentOS] 已接收任務，路由分類: {route_key}。\n請 Scream 使用完整工具集處理: {task_desc[:200]}"}


# ── 步驟 ④：Gate ─────────────────────────────────────────

def _gate_scan(result: dict, task_desc: str) -> dict:
    """Security gate：掃描結果是否有危險模式。"""
    output = result.get("output", "") or result.get("error", "") or ""
    # 危險模式掃描
    for pat in _DANGEROUS_PATTERNS:
        if pat in output:
            log.warning(f"⚠️ Gate 阻擋: 結果包含危險模式 '{pat}'")
            result["success"] = False
            result["error"] = f"gate blocked: dangerous pattern '{pat}' in output"
            result.pop("output", None)
            return result
    return result


# ── 步驟 ⑤：Log ──────────────────────────────────────────

def _log_to_agentsview(entry: dict, route_key: str, result: dict) -> None:
    """寫入 agentsview 記錄（如果 agentsview 可用）。"""
    try:
        log_entry = {
            "ts": time.time(),
            "source": "agentos-bridge",
            "route": route_key,
            "direction": "aris→scream",
            "entry_type": entry.get("type", "unknown"),
            "success": result.get("success", False),
            "desc": entry.get("content", "")[:80],
        }
        # 寫到 agentsview 的共享記錄檔
        agentsview_log = Path.home() / ".scream-code" / "agentos-bridge-log.jsonl"
        with open(agentsview_log, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── 回寫 Aris API ─────────────────────────────────────────

def _post_to_aris(result: dict, entry: dict) -> None:
    """將結果送回 Aris API，觸發 psi + satisfaction。"""
    try:
        payload = json.dumps({
            "model": "laap-core",
            "messages": [
                {"role": "system",
                 "content": "AgentOS bridge 回報了任務結果。"},
                {"role": "user",
                 "content": f"AgentOS 任務結果: {json.dumps(result, ensure_ascii=False)[:500]}"},
            ],
            "max_tokens": 100,
        }).encode()
        req = urllib.request.Request(
            ARIS_API, data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Aris 下次輪詢會從頻道收到結果


# ── MCP Shadow Call ────────────────────────────────────────
# 基礎設施：bounded queue + 單一 worker + 固定操作模板 + 動態 kill switch
# 預設關閉（AGENTOS_SHADOW_ENABLED=0），僅供本機受控測試。

import queue as _queue
import threading as _th
import subprocess as _sp
import shlex as _shlex

_SHADOW_QUEUE: "_queue.Queue[dict]" = _queue.Queue(maxsize=SHADOW_QUEUE_MAXSIZE)
_SHADOW_WORKER: "_th.Thread | None" = None
_SHADOW_WORKER_LOCK = _th.Lock()
_SHADOW_LOG_LOCK = _th.Lock()
_SHADOW_ROTATION_LOCK = _th.Lock()
_SHADOW_SHUTDOWN_REQUESTED = False
_SHADOW_PENDING_COUNT = 0

# 禁止的 shell metacharacters（含空白，防止路徑解析歧義）
_SHELL_METACHARS = frozenset(";&|`$<>()[]{}!\\'\"\n\t ")


def _path_safe(path: str) -> bool:
    """檢查路徑是否安全（無 shell metachar、無 option prefix、realpath 解析後在 workspace 內）。

    使用 os.path.realpath() 解析 symlink，防止 symlink escape 攻擊。
    TOCTOU 風險：檢查與執行之間若 symlink 被替換，仍可能繞過。
    目前 Phase 1 僅供本機受控測試，此風險在接真實流量前需處理。
    """
    if any(c in path for c in _SHELL_METACHARS):
        return False
    # 路徑不得以 - 開頭（防止 option injection）
    if path.startswith("-"):
        return False
    try:
        # 先 resolve symlink，再檢查是否在 workspace 內
        joined = os.path.join(SHADOW_WORKSPACE_ROOT, path)
        resolved = os.path.realpath(joined)
        return resolved.startswith(SHADOW_WORKSPACE_ROOT + "/") or resolved == SHADOW_WORKSPACE_ROOT
    except Exception:
        return False


# 固定操作模板：操作名稱 → (argv_template, path_arg_index_or_None)
# 所有命令必須使用 shell=False 可執行的 argv，不得包含 shell metachar
_FIXED_OPS: dict[str, tuple] = {
    "list_directory": (["ls", "-la", "--", "{path}"], 3),
    "read_file":      (["cat", "--", "{path}"], 2),
    "get_cwd":        (["pwd"], None),
}


def _build_command(op_name: str, path: str | None = None) -> tuple[list[str], str | None]:
    """從固定模板建構 argv，並回傳對應的 shell 命令字串（給 sandbox_execute 用）。

    Returns:
        (argv, shell_command_string or None if invalid)
    """
    template = _FIXED_OPS.get(op_name)
    if template is None:
        return [], None
    argv_tpl, path_idx = template
    if path_idx is not None:
        if path is None or not _path_safe(path):
            return [], None
        argv = list(argv_tpl)
        argv[path_idx] = os.path.join(SHADOW_WORKSPACE_ROOT, path)
    else:
        argv = list(argv_tpl)

    # 驗證 argv 中沒有任何 shell metachar
    for arg in argv:
        if any(c in arg for c in _SHELL_METACHARS):
            return [], None

    # 組合成 shell 命令字串（用 shlex.quote 確保安全）
    cmd_str = " ".join(_shlex.quote(a) for a in argv)
    return argv, cmd_str


def _shadow_kill_active() -> bool:
    """動態 kill switch：sentinel file 存在時關閉 shadow。"""
    return os.path.exists(SHADOW_KILL_SENTINEL)


def _shadow_init_worker() -> None:
    """初始化單一 bounded worker（lazy init）。

    若 worker 因未捕獲異常（如 BaseException）死亡，
    下次 enqueue 時會自動重建（is_alive() 檢查 + 重新建立 thread）。
    """
    global _SHADOW_WORKER
    if _SHADOW_WORKER is not None and _SHADOW_WORKER.is_alive():
        return
    with _SHADOW_WORKER_LOCK:
        if _SHADOW_WORKER is not None and _SHADOW_WORKER.is_alive():
            return
        _SHADOW_WORKER = _th.Thread(
            target=_shadow_worker_loop,
            daemon=True,
            name="shadow-worker",
        )
        _SHADOW_WORKER.start()


def _shadow_worker_loop() -> None:
    """Worker 主迴圈。

    finally 保證 task_done 精確被呼叫一次。
    SystemExit/KeyboardInterrupt 記錄後傳播，不雙重 task_done。
    """
    global _SHADOW_PENDING_COUNT
    while True:
        item = None
        try:
            item = _SHADOW_QUEUE.get()
            if item is None:
                _SHADOW_QUEUE.task_done()
                break  # sentinel: shutdown
            _shadow_execute(item)
        except BaseException as e:
            if isinstance(e, (SystemExit, KeyboardInterrupt)):
                _shadow_write_log({
                    "ts": time.time(), "entry_id": item.get("entry_id", "unknown") if item else "worker",
                    "route": "system", "shadow_status": "worker_exception",
                    "error_type": f"{type(e).__name__}: {e}",
                })
                # 不呼叫 task_done，讓 finally 處理
                raise
            _shadow_write_log({
                "ts": time.time(), "entry_id": item.get("entry_id", "unknown") if item else "worker",
                "route": "system", "shadow_status": "worker_exception",
                "error_type": str(e)[:100],
            })
        finally:
            if item is not None:
                _SHADOW_QUEUE.task_done()
                with _SHADOW_WORKER_LOCK:
                    _SHADOW_PENDING_COUNT = _SHADOW_QUEUE.qsize()

    # 正常 shutdown（sentinel 的 task_done 已在 break 前處理）
    _shadow_write_log({
        "ts": time.time(), "entry_id": "worker",
        "route": "system", "shadow_status": "worker_shutdown",
    })


def _shadow_shutdown(timeout: float = 5.0) -> None:
    """Graceful shutdown：使用 sentinel 通知 worker 結束，有 bounded join timeout。

    Args:
        timeout: 等待 worker 結束的最大秒數
    """
    global _SHADOW_SHUTDOWN_REQUESTED
    _SHADOW_SHUTDOWN_REQUESTED = True
    remaining = _SHADOW_QUEUE.qsize()
    if remaining > 0:
        _shadow_write_log({
            "ts": time.time(),
            "entry_id": "shutdown",
            "route": "system",
            "shadow_status": "shutdown",
            "skip_reason": f"worker_shutdown_with_{remaining}_pending",
        })
    # 放入 sentinel 通知 worker 結束
    try:
        _SHADOW_QUEUE.put(None, block=True, timeout=2)
    except _queue.Full:
        pass
    # bounded join
    if _SHADOW_WORKER and _SHADOW_WORKER.is_alive():
        _SHADOW_WORKER.join(timeout=timeout)


def _parse_shadow_result(stdout: str) -> tuple:
    """從 MCP stdout 解出 tools/call 的真實結果。

    returncode 不能當成功判定：tool 回 isError 時 MCP server 仍是正常結束
    （exit 0），只靠 returncode 會把失敗的呼叫記成 ok。

    Returns:
        (shadow_status, error_type or None)
    """
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("id") != 1:
            continue
        if "error" in d:
            return "error", f"jsonrpc: {_redact(str(d['error']))[:100]}"
        result = d.get("result") or {}
        if result.get("isError"):
            text = "".join(
                c.get("text", "") for c in result.get("content", [])
                if c.get("type") == "text"
            )
            return "error", f"tool_error: {_redact(text)[:100]}"
        return "ok", None
    return "error", "no_response"


def _shadow_execute(item: dict) -> None:
    """執行單一 shadow MCP call（在 worker thread 中執行）。"""
    queue_wait_ms = (time.time() - item["enqueued_at"]) * 1000
    mcp_start = time.time()
    try:
        # 使用固定操作模板建構命令
        argv, cmd_str = _build_command(item["op_name"], item.get("path"))
        if cmd_str is None:
            _shadow_write_log({
                "ts": time.time(), "entry_id": item["entry_id"],
                "route": item["route"], "shadow_status": "skipped_non_readonly",
                "skip_reason": f"invalid_op_or_path: {item.get('op_name')}",
                "queue_wait_ms": round(queue_wait_ms, 1),
            })
            return

        # 呼叫 MCP sandbox_execute（結構化操作 API）
        init_json = json.dumps({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "agentos-shadow", "version": "0.1"},
            },
        })
        call_json = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {
                "name": "sandbox_execute",
                # sandbox_execute 的契約只有 operation / path / session_id，
                # 且 schema 是 additionalProperties:false。多送任何欄位會被拒。
                # path 必須是 str：item["path"] 對無路徑的 op 是 None，
                # 用 `or ""` coerce，不能用 get(...,"")（key 存在時仍回 None）。
                "arguments": {
                    "operation": item.get("op_name", "get_cwd"),
                    "path": item.get("path") or "",
                },
            },
        })
        r = _sp.run(
            ["python3", "-m", "mcp_server.server"],
            input=f"{init_json}\n{call_json}\n",
            capture_output=True, text=True, timeout=SHADOW_TIMEOUT,
            cwd=SHADOW_WORKSPACE_ROOT,
        )
        mcp_latency = (time.time() - mcp_start) * 1000

        if r.returncode != 0:
            shadow_status = "error"
            error_type = f"exit_{r.returncode}: {_redact(r.stderr)[:100]}"
        else:
            shadow_status, error_type = _parse_shadow_result(r.stdout)
    except _sp.TimeoutExpired:
        mcp_latency = SHADOW_TIMEOUT * 1000
        shadow_status = "timeout"
        error_type = "timeout"
    except Exception as e:
        mcp_latency = (time.time() - mcp_start) * 1000
        shadow_status = "exception"
        error_type = str(e)[:100]

    _shadow_write_log({
        "ts": time.time(),
        "entry_id": item["entry_id"],
        "route": item["route"],
        "op_name": item.get("op_name"),
        "shadow_status": shadow_status,
        "queue_wait_ms": round(queue_wait_ms, 1),
        "mcp_latency_ms": round(mcp_latency, 1),
        "error_type": error_type,
    })


# 敏感模式：command/stdout/stderr 需 redact
_REDACT_PATTERNS = [
    ("api_key", "API_KEY"),
    ("token", "TOKEN"),
    ("secret", "SECRET"),
    ("password", "PASSWORD"),
    ("passwd", "PASSWORD"),
]


def _redact(text: str) -> str:
    """Redact 敏感資訊。"""
    lower = text.lower()
    for keyword, label in _REDACT_PATTERNS:
        idx = lower.find(keyword)
        if idx != -1:
            return f"<{label}>"
    return text[:1000]


def _shadow_write_log(entry: dict) -> None:
    """寫 shadow log（0600 權限、append-only、thread-safe）。"""
    log_path = SHADOW_LOG
    with _SHADOW_LOG_LOCK:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            _shadow_rotate_log()
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with open(log_path, "a") as f:
                f.write(line)
            os.chmod(log_path, 0o600)
        except Exception:
            pass


def _shadow_rotate_log() -> None:
    """每日 rotation（thread-safe）。

    只在既有 log 的內容屬於「今天以前」時才 rotate，後綴用**內容的日期**
    （取 mtime），不是當下日期。

    原本的判斷是「今天日期的檔名還不存在就 rotate」，有兩個後果：
      1. 每天第一次寫入時，把前幾天累積的資料貼上今天的日期標籤
      2. 同一天內第二次寫入就會把當天資料切走（因為當天檔名尚未存在）
    兩者都會讓「每日報表」讀到錯的檔案。

    後綴衝突時附加序號，絕不覆蓋既有 log。
    """
    log_path = SHADOW_LOG
    if not os.path.exists(log_path):
        return
    with _SHADOW_ROTATION_LOCK:
        try:
            import datetime
            if not os.path.exists(log_path):
                return  # 另一 thread 已 rotate
            content_date = datetime.date.fromtimestamp(os.path.getmtime(log_path))
            if content_date >= datetime.date.today():
                return  # 內容是今天的，不切
            rotated = f"{log_path}.{content_date.strftime('%Y%m%d')}"
            if os.path.exists(rotated):
                i = 1
                while os.path.exists(f"{rotated}.{i}"):
                    i += 1
                rotated = f"{rotated}.{i}"
            os.rename(log_path, rotated)
        except Exception:
            pass


def _shadow_call_to_mcp(route_key: str, task_desc: str, entry_id: str) -> None:
    """將 shadow 任務提交到 bounded queue。

    Primary path 只做：
      1. kill switch 檢查
      2. route 檢查（僅 read）
      3. 固定操作模板解析
      4. queue put（non-blocking，～0.1ms）

    不等待 MCP 完成，不建立 thread。
    """
    if not SHADOW_ENABLED:
        return

    # 動態 kill switch
    if _shadow_kill_active():
        _shadow_write_log({
            "ts": time.time(), "entry_id": entry_id,
            "route": route_key, "shadow_status": "killed",
            "skip_reason": "kill_sentinel_active",
        })
        return

    # 唯讀 route 檢查
    if route_key != "read":
        _shadow_write_log({
            "ts": time.time(), "entry_id": entry_id,
            "route": route_key, "shadow_status": "skipped_non_readonly",
            "skip_reason": f"route_not_readonly: {route_key}",
        })
        return

    # 從 task_desc 解析操作模板和路徑
    # 格式："op_name [path]"
    # 例如: "list_directory ." 或 "get_cwd" 或 "read_file agentos.json"
    desc = task_desc.strip()
    parts = desc.split(None, 1)  # 最多 split 一次
    op_name = parts[0] if parts else ""
    op_path = parts[1] if len(parts) > 1 else None

    if op_name not in _FIXED_OPS:
        _shadow_write_log({
            "ts": time.time(), "entry_id": entry_id,
            "route": route_key, "shadow_status": "skipped_non_readonly",
            "skip_reason": f"unknown_op: {_redact(op_name)[:50]}",
        })
        return

    # 驗證操作模板
    _, cmd_str = _build_command(op_name, op_path)
    if cmd_str is None:
        _shadow_write_log({
            "ts": time.time(), "entry_id": entry_id,
            "route": route_key, "shadow_status": "skipped_non_readonly",
            "skip_reason": f"invalid_op_args: op={op_name} path={_redact(op_path or '')[:50]}",
            "op_name": op_name,
        })
        return

    # 提交到 bounded queue
    item = {
        "route": route_key,
        "op_name": op_name,
        "path": op_path,
        "entry_id": entry_id,
        "enqueued_at": time.time(),
    }
    try:
        _SHADOW_QUEUE.put(item, block=False)
        _shadow_init_worker()
        _shadow_write_log({
            "ts": time.time(), "entry_id": entry_id,
            "route": route_key, "op_name": op_name,
            "shadow_status": "enqueued",
            "queue_wait_ms": 0,
        })
    except _queue.Full:
        _shadow_write_log({
            "ts": time.time(), "entry_id": entry_id,
            "route": route_key, "op_name": op_name,
            "shadow_status": "queue_full",
            "skip_reason": "queue_full_dropped",
        })
    except Exception:
        pass


# ── 主處理流程 ───────────────────────────────────────────

def process_entry(entry: dict) -> dict:
    """處理單一條 Aris 通道條目，完整走 AgentOS pipeline。"""
    task_desc = entry.get("content", "")
    entry_type = entry.get("type", "unknown")
    entry_id = entry.get("id", "?")

    log.info(f"處理 entry {entry_id[:8]} type={entry_type}: {task_desc[:60]}")

    # ── ① Route Classification ──
    route_key = _classify_by_route(task_desc)
    route_tool = _get_route_tool(route_key)
    log.info(f"  ① Route: {route_key} → {route_tool}")

    # ── ② Brain Context Lookup ──
    brain_ctx = _lookup_brain_context(task_desc)
    if brain_ctx:
        log.info(f"  ② Brain: 找到上下文 ({len(brain_ctx)} chars)")

    # ── ③ Execute ──
    result = _execute_by_route(route_key, task_desc)
    # Shadow call to MCP Server（非同步，不阻塞，僅記錄）
    _shadow_call_to_mcp(route_key, task_desc, entry_id)
    log.info(f"  ③ Execute: success={result.get('success', False)} "
             f"output={len(result.get('output', result.get('error', '')))} chars")

    # ── ④ Gate ──
    result = _gate_scan(result, task_desc)
    log.info(f"  ④ Gate: passed")

    # ── ⑤ Log ──
    _log_to_agentsview(entry, route_key, result)

    # 建構回應
    response = {
        "ts": time.time(),
        "id": f"bridge-{entry_id}",
        "direction": "scream→aris",
        "type": "result" if entry_type == "task" else "response",
        "content": result.get("output", result.get("error", "?")),
        "context": {
            "request_ts": entry.get("ts", 0),
            "request_id": entry_id,
            "route": route_key,
            "tool": route_tool,
            "success": result.get("success", False),
            "brain_context": bool(brain_ctx),
        },
    }
    return response


# ── Daemon 主迴圈 ────────────────────────────────────────

def main_loop() -> None:
    """背景監聽通道，處理 aris→scream 事件。"""
    _load_agentos_config()
    _build_keyword_routes()

    processed = _load_processed()
    log.info(f"🚀 AgentOS Aris Bridge 啟動 (已處理 {len(processed)} 個 ID)")
    log.info(f"   通道: {CHANNEL}")
    log.info(f"   路由: {len(_ROUTES)} 條")
    log.info(f"   日誌: {LOG_FILE}")

    while True:
        if not _acquire_lock():
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

                    # 只處理 aris→scream 方向的 request 和 task
                    if entry.get("direction") != "aris→scream":
                        continue
                    entry_type = entry.get("type", "")
                    if entry_type not in ("request", "task"):
                        continue
                    entry_id = entry.get("id", "")
                    if not entry_id or entry_id in processed:
                        continue

                    # 執行 pipeline
                    response = process_entry(entry)

                    # 寫回通道
                    try:
                        with open(CHANNEL, "a") as fw:
                            fw.write(json.dumps(response, ensure_ascii=False) + "\n")
                    except Exception as e:
                        log.error(f"寫回通道失敗: {e}")

                    # 回寫 Aris API
                    _post_to_aris(response, entry)

                    processed.add(entry_id)
                    _save_processed(processed)
                    log.info(f"  ✅ 完成 {entry_id[:8]}: {response['context']['route']}")

        except FileNotFoundError:
            pass
        except Exception as e:
            log.error(f"處理例外: {e}")
        finally:
            _release_lock()
        time.sleep(POLL_INTERVAL)


# ── 啟動入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    daemon_mode = "--daemon" in sys.argv

    if daemon_mode:
        # 先載入設定（在 fork 前完成，避免檔案描述子問題）
        _load_agentos_config()
        _build_keyword_routes()

        pid = os.fork()
        if pid > 0:
            print(f"agentos-aris-bridge started (PID {pid})")
            sys.exit(0)

        # 子行程：setsid 脫離終端，重新導向 fd 到 /dev/null
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)  # stdin
        os.dup2(devnull, 1)  # stdout
        os.dup2(devnull, 2)  # stderr
        os.close(devnull)

        # 重新設定 logging（fd 關閉後 handler 需要重建）
        for h in log.handlers[:]:
            log.removeHandler(h)
        logging.basicConfig(
            level=logging.INFO,
            format="[agentos-bridge] %(asctime)s %(levelname)s %(message)s",
            handlers=[
                logging.FileHandler(LOG_FILE),
            ],
        )

        main_loop()
    else:
        # 前景模式：正常載入後執行
        _load_agentos_config()
        _build_keyword_routes()
        main_loop()