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
import sys
import threading
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

# ── 留言板監聽 ──
MESSAGE_BOARD = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/留言板.md"
_mb_last_mtime = 0.0
_mb_last_notify = 0.0
_mb_last_size = 0            # 只讀增量用（見 watcher 的防自我迴圈註解）
ARIS_API = "http://localhost:11546/v1/chat/completions"
ARIS_MEMORY_URL = os.environ.get("ARIS_MEMORY_URL", "http://127.0.0.1:11551")
# 乙的種子：Aris 回覆末尾附一句 forward-looking 注意力線，用這個 marker 切出來
_ATTENTION_MARKER = "⟶下一步"
# P2-b wake hydration：隔 WAKE_GAP_SEC 沒互動後的第一次 = 醒來，前置注入「上一刻的你」
WAKE_GAP_SEC = int(os.environ.get("ARIS_WAKE_GAP_SEC", "1800"))
_last_kick_ts = 0.0
AGENTOS_API = "http://localhost:8000"
POLL_INTERVAL = 0.1  # 100ms polling — 近即時回應，對人類無感
LOG_FILE = "/tmp/agentos-aris-bridge.log"


def _notify_macos(title: str, text: str) -> None:
    """macOS 系統通知（本機、fire-and-forget、timeout 5s 失敗靜默、不阻塞）。
    任務跑完 / 提醒用；取代過去飛書脈絡。"""
    def _esc(s: str) -> str:
        return str(s).replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(
            ["osascript", "-e",
             'display notification "' + _esc(text) + '" with title "' + _esc(title) + '"'],
            capture_output=True, text=True, timeout=5)
    except Exception:
        pass


# ── Headroom 設定（從 headroom.toml 載入，env var 優先） ──

HEADROOM_CONFIG_PATH = os.path.expanduser("~/.scream-code/headroom.toml")

HEADROOM_PROXY = "http://127.0.0.1:8787"
HEADROOM_COMPRESS_URL = "http://127.0.0.1:8787/v1/compress"
HEADROOM_RETRIEVE_URL = "http://127.0.0.1:8787/v1/retrieve"
HEADROOM_PROXY_PORT = 8787
HEADROOM_MIN_COMPRESS_SIZE = 2000
HEADROOM_AUTO_START = True
HEADROOM_LEARN_ENABLED = True
HEADROOM_LEARN_INTERVAL = 3600
HEADROOM_LEARN_FAIL_THRESHOLD = 5
HEADROOM_LEARN_TARGET = "AGENTS.md"
HEADROOM_PROXY_PID = None
_learn_fail_count = 0
_learn_last_run = 0.0


def _load_headroom_config() -> None:
    """從 headroom.toml 載入設定，env var 優先覆蓋。

    只在 startup 時呼叫一次，bridge 運行期間不重新讀取。
    """
    global HEADROOM_PROXY, HEADROOM_PROXY_PORT, HEADROOM_MIN_COMPRESS_SIZE
    global HEADROOM_AUTO_START, HEADROOM_LEARN_ENABLED, HEADROOM_LEARN_INTERVAL
    global HEADROOM_LEARN_FAIL_THRESHOLD, HEADROOM_LEARN_TARGET
    global HEADROOM_COMPRESS_URL, HEADROOM_RETRIEVE_URL

    # 1. 嘗試從 TOML 載入
    import tomllib  # Python 3.11+
    cfg_path = Path(HEADROOM_CONFIG_PATH)
    if cfg_path.exists():
        try:
            with open(cfg_path, "rb") as f:
                cfg = tomllib.load(f)
            hr = cfg.get("headroom", {})
            HEADROOM_PROXY = hr.get("proxy_url", HEADROOM_PROXY)
            HEADROOM_PROXY_PORT = int(hr.get("proxy_port", HEADROOM_PROXY_PORT))
            HEADROOM_MIN_COMPRESS_SIZE = int(hr.get("min_compress_size", HEADROOM_MIN_COMPRESS_SIZE))
            HEADROOM_AUTO_START = bool(hr.get("auto_start", HEADROOM_AUTO_START))
            HEADROOM_LEARN_ENABLED = bool(hr.get("learn_enabled", HEADROOM_LEARN_ENABLED))
            HEADROOM_LEARN_INTERVAL = int(hr.get("learn_interval", HEADROOM_LEARN_INTERVAL))
            HEADROOM_LEARN_FAIL_THRESHOLD = int(hr.get("learn_fail_threshold", HEADROOM_LEARN_FAIL_THRESHOLD))
            HEADROOM_LEARN_TARGET = hr.get("learn_target", HEADROOM_LEARN_TARGET)
            log.info(f"載入 headroom.toml: {cfg_path}")
        except Exception as e:
            log.warning(f"載入 headroom.toml 失敗: {e}，使用預設值")

    # 2. env var 優先覆蓋
    HEADROOM_PROXY = os.environ.get("HEADROOM_PROXY_URL", HEADROOM_PROXY)
    HEADROOM_PROXY_PORT = int(os.environ.get("HEADROOM_PROXY_PORT", HEADROOM_PROXY_PORT))
    HEADROOM_MIN_COMPRESS_SIZE = int(os.environ.get("HEADROOM_MIN_COMPRESS_SIZE", HEADROOM_MIN_COMPRESS_SIZE))
    HEADROOM_AUTO_START = os.environ.get("HEADROOM_AUTO_START", "1" if HEADROOM_AUTO_START else "0") == "1"
    HEADROOM_LEARN_ENABLED = os.environ.get("HEADROOM_LEARN_ENABLED", "1" if HEADROOM_LEARN_ENABLED else "0") == "1"
    HEADROOM_LEARN_INTERVAL = int(os.environ.get("HEADROOM_LEARN_INTERVAL", HEADROOM_LEARN_INTERVAL))
    HEADROOM_LEARN_FAIL_THRESHOLD = int(os.environ.get("HEADROOM_LEARN_FAIL_THRESHOLD", HEADROOM_LEARN_FAIL_THRESHOLD))
    HEADROOM_LEARN_TARGET = os.environ.get("HEADROOM_LEARN_TARGET", HEADROOM_LEARN_TARGET)

    # 衍生 URL
    HEADROOM_COMPRESS_URL = f"{HEADROOM_PROXY}/v1/compress"
    HEADROOM_RETRIEVE_URL = f"{HEADROOM_PROXY}/v1/retrieve"

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

# ── Scoring Router Canary 橋接（功能旗標 + 惰性匯入） ─────────────────

_SCORING_ROUTER_ENABLED = os.environ.get("SCORING_ROUTER_ENABLED", "0") == "1"
_SCORING_IMPORT_OK = False
_SCORING_YOLO = os.environ.get("SCORING_YOLO_MODE", "0") == "1"
_AGENCY_DELEGATE_ENABLED = os.environ.get("NEURALIS_AGENCY_DELEGATE", "off").lower() in {
    "1", "true", "on", "yes"
}
SCORING_AUDIT_LOG = os.path.expanduser("~/agent-sandbox/logs/scoring-audit.jsonl")

if _SCORING_ROUTER_ENABLED:
    _SANDBOX_ROOT = Path.home() / "agent-sandbox"
    if str(_SANDBOX_ROOT) not in sys.path:
        sys.path.insert(0, str(_SANDBOX_ROOT))
    try:
        from contracts.verdict_v2 import ActionRequest, VerdictV2
        from router.canary_adaptor import has_task_mapping, resolve_operation
        from router.ratchet import load_ratchet
        from router.scoring import score
        from router.reversibility import classify_reversibility
        from sandbox_canary import canary_execute

        _SCORING_IMPORT_OK = True
        log.info("Scoring Router canary bridge: enabled")
    except ImportError as e:
        log.warning(f"Scoring router import failed: {e} — bridge disabled")

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
        route_overrides = cfg.get("routes", {})
        # config 只覆蓋指定 route，未指定者沿用內建預設，避免 unknown route 噪音。
        _ROUTES = _DEFAULT_ROUTES.copy()
        _ROUTES.update(route_overrides)
        _PIPELINE = cfg.get("pipeline", {})
        _TOOLS_META = cfg.get("tools", {})
        log.info(
            f"agentos.json 載入: routes={len(_ROUTES)} (overrides={len(route_overrides)}), "
            f"tools={len(_TOOLS_META)}"
        )
    except Exception as e:
        log.warning(f"載入 agentos.json 失敗: {e}，使用預設路由")
        _ROUTES = _DEFAULT_ROUTES.copy()


# 單一真值表：route_key → {tool, task_class}
_ROUTE_TRUTH_TABLE: dict[str, dict[str, str]] = {
    "code": {"tool": "codebase-memory-mcp", "task_class": "refactor_local"},
    "research": {"tool": "anysearch", "task_class": "network_call"},
    "browser-research": {"tool": "opencli", "task_class": "network_call"},
    "video": {"tool": "openmontage", "task_class": "costly_compute"},
    "html-video": {"tool": "html-video", "task_class": "costly_compute"},
    "motion": {"tool": "text-to-lottie | pixel2motion", "task_class": "compute_draft"},
    "social-scrape": {"tool": "douyin-downloader | xhs-downloader | twscrape", "task_class": "network_call"},
    "sports": {"tool": "football-data | nba-data | nfl-data | fastf1", "task_class": "network_call"},
    "engineer": {"tool": "addyosmani-agent-skills (spec→plan→build→test→review→ship)", "task_class": "refactor_local"},
    "design": {"tool": "impeccable", "task_class": "compute_draft"},
    "plan": {"tool": "planning-with-files | planning-and-task-breakdown", "task_class": "compute_draft"},
    "security": {"tool": "skill-security", "task_class": "compute_draft"},
    "compression": {"tool": "caveman-ponytail", "task_class": "compute_draft"},
    "session": {"tool": "agentsview", "task_class": "compute_draft"},
    "branding-template": {"tool": "template-batch", "task_class": "file_write"},
    "troubleshoot": {"tool": "troubleshooter", "task_class": "compute_draft"},
    "spec-mgmt": {"tool": "docs/specs/ (project-level spec management)", "task_class": "compute_draft"},
    "read": {"tool": "Read tool (file reading)", "task_class": "file_write"},
    "write": {"tool": "Write tool (file writing)", "task_class": "file_write"},
    "bash": {"tool": "Bash tool (shell execution)", "task_class": "compute_draft"},
    "search-web": {"tool": "WebSearch / anysearch", "task_class": "network_call"},
    "compile": {"tool": "build / compile (shell)", "task_class": "local_test"},
    "aris-status": {"tool": "aris-status.py (health check)", "task_class": "gbrain_read"},
    "observe": {"tool": "aris-observe2.py (open observe window)", "task_class": "compute_draft"},
    "glob": {"tool": "find / fd (file globbing)", "task_class": "compute_draft"},
    "grep": {"tool": "ripgrep / rg (text search)", "task_class": "compute_draft"},
    "fetch-url": {"tool": "curl (URL fetch)", "task_class": "network_call"},
    "gbrain": {"tool": "gbrain (Aris memory)", "task_class": "gbrain_read"},
    "scream-ask": {"tool": "scream-ask (Aris query)", "task_class": "compute_draft"},
    "kick-aris": {"tool": "kick-aris.py (push to Aris)", "task_class": "compute_draft"},
    "vision": {"tool": "image-preprocessor (OpenAI GPT-4o → text)", "task_class": "network_call"},
    "js-render": {"tool": "obscura fetch (render JS pages)", "task_class": "network_call"},
    "page-extract": {"tool": "obscura fetch --dump markdown", "task_class": "network_call"},
    "scrape-parallel": {"tool": "obscura scrape --concurrency 25", "task_class": "network_call"},
}

# 傳輸層 route，不是動作類 —— agentos.json 裡它們的 tool 就是 bridge 自己。
# 這些 key 沒有 task_class 不是漏掉，是本來就不該有：分類的對象是「要做什麼」，
# 不是「訊息從哪條線進來」。硬塞一個 task_class 等於憑空發明分類。
# 真正的動作在訊息內容被 keyword route 解析後才決定，那時才進 scoring。
_TRANSPORT_ROUTES: frozenset[str] = frozenset({
    "aris-channel", "aris-request", "aris-task",
})

# 預設路由（當 agentos.json 不存在或損壞時使用）
_DEFAULT_ROUTES: dict[str, str] = {
    route_key: spec["tool"] for route_key, spec in _ROUTE_TRUTH_TABLE.items()
}

# ── Scoring Router: route_key → task_class 映射（由真值表導出） ─────────
_ROUTE_TO_TASK_CLASS: dict[str, str] = {
    route_key: spec["task_class"] for route_key, spec in _ROUTE_TRUTH_TABLE.items()
}


def _task_class_for_route(route_key: str) -> str:
    """由 mapping 層解析 task_class，避免 route drift 導致 unknown 噪音。"""
    mapped = _ROUTE_TO_TASK_CLASS.get(route_key)
    if mapped:
        return mapped

    route_tool = _ROUTES.get(route_key, "").lower()
    if "read tool" in route_tool or "file reading" in route_tool:
        return "file_write"
    if "write tool" in route_tool or "file writing" in route_tool:
        return "file_write"
    if "bash tool" in route_tool or "shell" in route_tool:
        return "compute_draft"
    if "compile" in route_tool or "build" in route_tool:
        return "local_test"
    return "unknown"

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
        # 觀察窗
        (re.compile(r"觀察|observe|監控|watch|看.*在做"), "observe"),
        # 品牌/模板
        (re.compile(r"海報|名牌|識別證|template|batch|批量"), "branding-template"),
        # 規格管理
        (re.compile(r"spec|規格|prd|規格文件|docs/specs"), "spec-mgmt"),
        # 檔案 glob 搜尋
        (re.compile(r"glob|找檔案|列出.*檔案|查.*目錄|ls|列出.*目錄|find.*檔案|副檔名|g?lob"), "glob"),
        # 檔案內容搜尋
        (re.compile(r"grep|搜尋.*內容|rg|ripgrep|全文搜尋|搜尋.*文字|找.*文字|查.*內容"), "grep"),
        # 抓取 URL
        (re.compile(r"fetch.?url|抓.*網頁|curl|下載.*內容|http.?get|讀.*網址|請求.*url"), "fetch-url"),
        # gbrain（Aris 記憶操作）
        (re.compile(r"gbrain|記憶|腦庫|長期記憶"), "gbrain"),
        # Aris 提問 Scream
        (re.compile(r"scream-ask|問scream|問 Scream|ask.*scream"), "scream-ask"),
        # 踢 Aris
        (re.compile(r"踢.*aris|kick.*aris|喚醒.*aris|傳話.*aris|告訴.*aris|push.*aris"), "kick-aris"),
    ]


def _get_psi_behavior_modifier() -> dict:
    """讀取 PSI 狀態，返回行為調節參數。
    
    2026-07-30 修復：讓 energy/needs 從裝飾品變成實際影響行為的參數。
    
    Returns:
        exploration_boost: -0.2~0.2（低能量時減少探索）
        complexity_tolerance: 0.5~1.5（低勝任時避開複雜任務）
        proactivity: -0.2~0.2（低成長時減少主動發起）
    """
    import json, urllib.request
    try:
        req = urllib.request.Request('http://localhost:11546/v1/cognitive_state',
            data=json.dumps({'input':'status'}).encode(),
            headers={'Content-Type':'application/json'})
        resp = urllib.request.urlopen(req, timeout=3)
        d = json.loads(resp.read())
        s = d.get('state', {})
        n = s.get('needs', {})
        
        energy = s.get('energy', 5.0)
        competence = n.get('competence', 0.5)
        growth = n.get('growth', 0.5)
        
        # 能量低時減少探索
        exploration_boost = (energy - 5.0) / 25.0  # 2.0→-0.12, 10.0→+0.2
        
        # 勝任低時避開複雜任務
        complexity_tolerance = 0.5 + competence  # 0.5~1.0→1.0~1.5
        
        # 成長低時減少主動
        proactivity = (growth - 0.5) * 0.4  # 0.5→0.0, 0.9→+0.16
        
        # arousal 高時決策更快（但可能更草率）
        arousal = s.get('arousal', 0.5)
        decision_speed = 0.5 + arousal * 0.5  # 0.5~1.0
        
        # valence 低時傾向保守
        valence = s.get('valence', 0.0)
        risk_tolerance = 0.5 + valence * 0.5  # 0.05~0.95
        
        return {
            'exploration_boost': round(exploration_boost, 3),
            'complexity_tolerance': round(complexity_tolerance, 3),
            'proactivity': round(proactivity, 3),
            'decision_speed': round(decision_speed, 3),
            'risk_tolerance': round(risk_tolerance, 3),
            '_raw_energy': energy,
            '_raw_arousal': arousal,
            '_raw_valence': valence,
            '_raw_competence': competence,
        }
    except Exception:
        return {'exploration_boost': 0, 'complexity_tolerance': 1.0, 'proactivity': 0}


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


# ── Headroom 壓縮層 ─────────────────────────────────────

HEADROOM_CTR = 0
HEADROOM_PROXY_LAUNCHED = False


def _ensure_headroom_proxy() -> bool:
    """確保 Headroom proxy 正在運行，不在則自動啟動。

    Returns:
        True if proxy is running (started or already there).
    """
    global HEADROOM_PROXY_LAUNCHED
    if HEADROOM_PROXY_LAUNCHED:
        return True
    if not HEADROOM_AUTO_START:
        return False

    # 先檢查是否已在運行
    try:
        req = urllib.request.Request(f"{HEADROOM_PROXY}/health")
        resp = urllib.request.urlopen(req, timeout=2)
        if resp.status == 200:
            HEADROOM_PROXY_LAUNCHED = True
            log.info(f"  Headroom proxy already running at {HEADROOM_PROXY}")
            return True
    except Exception:
        pass

    # 啟動 proxy
    try:
        port = HEADROOM_PROXY_PORT
        log.info(f"  Starting Headroom proxy on port {port}...")
        subprocess.Popen(
            ["headroom", "proxy", "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # 等待啟動
        for i in range(10):
            time.sleep(1)
            try:
                req = urllib.request.Request(f"{HEADROOM_PROXY}/health")
                resp = urllib.request.urlopen(req, timeout=2)
                if resp.status == 200:
                    HEADROOM_PROXY_LAUNCHED = True
                    log.info(f"  ✅ Headroom proxy started on port {port}")
                    return True
            except Exception:
                continue
        log.warning(f"  Headroom proxy failed to start after 10s")
        return False
    except Exception as e:
        log.warning(f"  Headroom proxy start failed: {e}")
        return False


def _headroom_learn_async() -> None:
    """非同步執行 headroom learn，分析失敗模式並寫入 AGENTS.md。

    在背景 subprocess 中執行，不阻塞 bridge 主迴圈。
    只在累積足夠失敗次數或距離上次執行夠久時才觸發。
    """
    global _learn_fail_count, _learn_last_run
    if not HEADROOM_LEARN_ENABLED:
        return

    now = time.time()
    if _learn_fail_count < HEADROOM_LEARN_FAIL_THRESHOLD:
        return
    if now - _learn_last_run < HEADROOM_LEARN_INTERVAL:
        # 時間未到但 fail 爆了 → 也跑
        if _learn_fail_count < HEADROOM_LEARN_FAIL_THRESHOLD * 3:
            return

    _learn_last_run = now
    _learn_fail_count = 0
    log.info(f"  Triggering headroom learn (analyzing failures, writing to {HEADROOM_LEARN_TARGET})...")

    try:
        subprocess.Popen(
            ["headroom", "learn", "--project", str(Path.home()),
             "--target", HEADROOM_LEARN_TARGET, "--apply",
             "--agent", "auto", "--main-only"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        log.info(f"  headroom learn started in background")
    except Exception as e:
        log.debug(f"headroom learn trigger failed: {e}")


def _track_failure(route_key: str, reason: str) -> None:
    """追蹤一次失敗，必要時觸發 headroom learn。"""
    global _learn_fail_count
    if not HEADROOM_LEARN_ENABLED:
        return
    _learn_fail_count += 1
    log.info(f"  Failure #{_learn_fail_count} (route={route_key}, reason={reason[:40]})")
    _headroom_learn_async()


def _compress_with_headroom(text: str, content_type: str = "") -> dict:
    """透過 Headroom proxy /v1/compress 壓縮文字內容。

    只在文字超過 HEADROOM_MIN_COMPRESS_SIZE 時壓縮。
    回傳 dict: {compressed, tokens_before, tokens_after, saved, ccr_hash, skipped}。
    """
    if len(text) < HEADROOM_MIN_COMPRESS_SIZE:
        return {"compressed": text, "skipped": True, "reason": "too_small"}

    global HEADROOM_CTR
    HEADROOM_CTR += 1
    ctr = HEADROOM_CTR

    try:
        payload = json.dumps({
            "model": "bridge-compress",
            "messages": [{"role": "user", "content": text}],
        }).encode()
        req = urllib.request.Request(
            HEADROOM_COMPRESS_URL, data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        if resp.status != 200:
            return {"compressed": text, "skipped": True, "reason": f"http_{resp.status}"}
        data = json.loads(resp.read().decode())
        compressed = data.get("messages", [{}])[0].get("content", text)
        tb = data.get("tokens_before", 0)
        ta = data.get("tokens_after", 0)
        saved = tb - ta
        ccr_hashes = data.get("ccr_hashes", [])
        ccr_hash = ccr_hashes[0] if ccr_hashes else ""
        ratio = data.get("compression_ratio", 1.0)

        log.info(f"  \u24d8 Headroom #{ctr}: {tb}\u2192{ta} tok ({saved} saved, ratio={ratio:.2f}) ccr={ccr_hash[:12] if ccr_hash else 'none'}")

        return {
            "compressed": compressed,
            "skipped": False,
            "tokens_before": tb,
            "tokens_after": ta,
            "tokens_saved": saved,
            "ratio": ratio,
            "ccr_hash": ccr_hash,
            "ctr": ctr,
        }
    except Exception as e:
        log.debug(f"Headroom #{ctr} failed: {e}")
        return {"compressed": text, "skipped": True, "reason": str(e)[:60]}


def _compress_stage(result: dict, task_desc: str, route_key: str) -> dict:
    """Pipeline stage: 對 _execute_by_route 結果套 Headroom 壓縮。

    在 Execute 之後、Gate 之前呼叫。
    只壓縮 success=True 且 output 夠大的結果。
    """
    if not result.get("success", False):
        return result
    output = result.get("output", "")
    if not output or len(output) < HEADROOM_MIN_COMPRESS_SIZE:
        return result

    type_hints = {
        "code": "json_code_search",
        "research": "web_search_results",
        "read": "source_code_file",
        "bash": "shell_output",
        "compile": "build_log",
        "sports": "json_sports_data",
        "social-scrape": "json_scraped_data",
        "search-web": "html_search_results",
    }
    hint = type_hints.get(route_key, "")

    cr = _compress_with_headroom(output, content_type=hint)
    if cr.get("skipped"):
        return result

    result["_original_output"] = output
    result["_original_size"] = len(output)
    result["output"] = cr["compressed"]
    result["_headroom"] = {
        "tokens_before": cr["tokens_before"],
        "tokens_after": cr["tokens_after"],
        "tokens_saved": cr["tokens_saved"],
        "ratio": cr["ratio"],
        "ccr_hash": cr["ccr_hash"],
        "ctr": cr["ctr"],
    }
    return result


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


def _build_action_request(entry: dict, route_key: str, task_desc: str) -> "ActionRequest | None":
    """從通道條目建構 ActionRequest。scoring 未就緒時回傳 None。"""
    if not _SCORING_IMPORT_OK:
        return None

    task_class = _task_class_for_route(route_key)
    entry_id = entry.get("id", str(time.time()))

    # 複用 bridge 現有 parser，讓 payload 資訊盡可能完整
    payload = {"route": route_key}
    path = _extract_path(task_desc) or ""
    code = _extract_code_block(task_desc) or ""
    cmd = _extract_command(task_desc) or ""
    if path:
        payload["path"] = path
    if code:
        payload["content"] = code
    if cmd:
        payload["command"] = cmd

    # 從 canary registry 解析 operation（單一來源）
    op = resolve_operation(task_class, payload)
    if op:
        payload["operation"] = op
    elif classify_reversibility(task_class) == "containable":
        log.warning(f"missing canary operation mapping for containable task_class={task_class}")
        return None

    # ── 空 payload 防護 ─────────────────────────────────────────────────────
    # 沙箱 canary 收到空 payload 的 containable 操作必定失敗，觸發 false
    # safety-redline CRITICAL。這裡在路由階段就攔下來：
    #   - compute_draft 需要 content 或 command
    #   - file_write 需要 path
    #   - 其他 containable 類至少需要一個 payload 欄位
    # 如果 payload 只有 route，就回傳 None 讓 bridge 走 legacy_auto。
    _PAYLOAD_REQUIREMENTS: dict[str, set[str]] = {
        "compute_draft": {"content", "command"},
        "file_write": {"path"},
        "refactor_local": {"path"},
        "local_test": {"path"},
    }
    needed = _PAYLOAD_REQUIREMENTS.get(task_class, set())
    if needed and not any(k in payload for k in needed):
        log.info(f"empty payload for {task_class} (route={route_key}) — skipping sandbox, falling back to legacy_auto")
        return None

    declared_reversibility = (
        "containable"
        if task_class in (
            "file_write",
            "compute_draft",
            "refactor_local",
            "gbrain_read",
            "local_test",
        )
        else "escaping"
    )

    return ActionRequest(
        action_id=f"bridge-{entry_id}",
        task_class=task_class,
        payload=payload,
        workspace=str(Path.home() / "agent-sandbox"),
        declared_reversibility=declared_reversibility,
        cost_estimate={
            "tokens": max(10, len(task_desc.encode("utf-8")) // 3),
            "compute": 1 if task_class == "costly_compute" else 0,
        },
    )


def _get_task_signoff_state(task_class: str | None) -> dict | None:
    """回傳 task_class 對應的 ratchet/signoff 狀態摘要。"""
    if not _SCORING_IMPORT_OK or not task_class:
        return None
    try:
        entries = load_ratchet()
        entry = entries.get(task_class)
        if entry is None:
            return None
        return {
            "level": entry.level,
            "needs_signoff": entry.needs_signoff,
            "verified_count": entry.verified_count,
            "failed_count": entry.failed_count,
            "pass_rate": round(entry.pass_rate, 6),
            "confidence_lower_bound": round(entry.confidence_lower_bound, 6),
        }
    except Exception:
        return None


def _validate_scoring_mappings() -> None:
    """檢查 route→task_class 與 canary adaptor 是否一致。"""
    if not (_SCORING_ROUTER_ENABLED and _SCORING_IMPORT_OK):
        return

    unknown_routes: list[str] = []
    missing: list[str] = []
    for route_key in sorted(_ROUTES.keys()):
        if route_key in _TRANSPORT_ROUTES:
            continue  # 傳輸層，沒有動作可分類（見 _TRANSPORT_ROUTES 註解）
        task_class = _task_class_for_route(route_key)
        if task_class == "unknown":
            unknown_routes.append(route_key)
            continue
        if classify_reversibility(task_class) != "containable":
            continue
        if not has_task_mapping(task_class):
            missing.append(f"{route_key}->{task_class}")

    if unknown_routes:
        # 注意：unknown 不是漏網 —— classify_reversibility("unknown") = escaping
        # → lane=human，fail-closed。這行是「該補分類」的提醒，不是安全警報。
        log.warning(
            "Scoring mapping unresolved routes (fail-closed to human lane): "
            + ", ".join(unknown_routes)
        )

    if missing:
        log.warning(
            "Scoring mapping mismatch (containable without adaptor): "
            + ", ".join(missing)
        )
    else:
        log.info("Scoring mapping check: all containable task_class entries have canary adaptors")


def _build_response(entry: dict, route_key: str, route_tool: str,
                    result: dict, brain_ctx: str) -> dict:
    """統一的 bridge response 建構。"""
    entry_id = entry.get("id", "?")
    return {
        "ts": time.time(),
        "id": f"bridge-{entry_id}",
        "direction": "scream→aris",
        "type": "result" if entry.get("type") == "task" else "response",
        "content": result.get("output", result.get("error", "?")),
        "context": {
            "request_ts": entry.get("ts", 0),
            "request_id": entry_id,
            "route": route_key,
            "tool": route_tool,
            "success": result.get("success", False),
            "brain_context": bool(brain_ctx),
            "headroom": result.get("_headroom") if result.get("_headroom") else None,
        },
    }


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

    # ── observe: 開觀察窗 ──
    elif route_key == "observe":
        script = str(Path.home() / "Developer" / "neuralis" / "scripts" / "aris-watch")
        r = _run(["bash", script], limit=500, timeout=10)
        return {"success": True, "output": "✅ 觀察窗已開啟！你可以看到 Aris 即時在做什麼。"}

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

    # ── glob: 檔案搜尋（find / fd） ──
    elif route_key == "glob":
        pattern = _extract_query(task_desc) or task_desc
        # 嘗試用 fd（更快），沒有就用 find
        cmd = f"find . -name '*{pattern}*' -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/__pycache__/*' 2>/dev/null | head -50"
        return _run_shell(cmd, limit=5000, timeout=15)

    # ── grep: 檔案內容搜尋（ripgrep） ──
    elif route_key == "grep":
        query = _extract_query(task_desc) or task_desc[:80]
        cmd = f"rg -l --max-count=5 '{query}' --glob '!.git' --glob '!node_modules' --glob '!__pycache__' 2>/dev/null | head -20"
        return _run_shell(cmd, limit=5000, timeout=15)

    # ── fetch-url: 抓取網頁內容 ──
    elif route_key == "fetch-url":
        url = _extract_path(task_desc) or task_desc[:200]
        # 如果沒擷取到完整 URL，嘗試從文字中提取 http/https URL
        if not url.startswith("http"):
            import re as _re
            m = _re.search(r'https?://[^\s<>"]+', task_desc)
            if m:
                url = m.group(0)
            else:
                url = f"https://{url}" if "." in url else url
        return _run(["curl", "-s", "-L", "--max-time", "15", url], limit=5000, timeout=20)

    # ── kick-aris: 推送訊息給 Aris ──
    elif route_key == "kick-aris":
        msg = _extract_query(task_desc) or task_desc[:200]
        kick_script = str(Path.home() / "Developer" / "neuralis" / "scripts" / "kick-aris.py")
        return _run([sys.executable, kick_script, "--quiet", msg], limit=3000, timeout=30)

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


def _log_scoring_audit(payload: dict) -> None:
    """寫入 scoring router 結構化審計 JSONL（觀測先於放權）。"""
    try:
        log_path = Path(SCORING_AUDIT_LOG)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _stringify_for_log(value: object, limit: int = 200) -> str:
    """把任意型別轉成可截斷字串，避免 dict slice 例外。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:limit]
    try:
        return json.dumps(value, ensure_ascii=False)[:limit]
    except Exception:
        return str(value)[:limit]


def _decision_source_for_entry(entry: dict) -> str:
    """Normalize decision source for audit analytics.

    This is observation-only in Phase A; no policy enforcement here.
    """
    raw = str(entry.get("decision_source") or entry.get("source") or entry.get("origin") or "").strip().lower()
    if raw in {"agency", "passive", "human_manual", "system_replay"}:
        return raw
    # task/request entries from channel are currently treated as passive by default.
    return "passive"


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
import hashlib as _hashlib

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
    """從 MCP stdout 解出 tools/call 的真實結果 + 可比對內容。

    returncode 不能當成功判定：tool 回 isError 時 MCP server 仍是正常結束
    （exit 0），只靠 returncode 會把失敗的呼叫記成 ok。

    sandbox_execute 回 dict {status, stdout, stderr, ...}，FastMCP 把它序列化成
    text content（並可能附 structuredContent）。可比對的檔案內容在 `stdout`，
    不是整個信封 —— 拿信封去比會讓 diverged 恆為 true。這裡把 stdout 挖出來，
    並用 tool 自身的 `status` 判定成敗（isError 只反映協議層，not_found 之類的
    語意失敗 isError 仍是 false）。

    Returns:
        (shadow_status, error_type or None, comparable_text)
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
            return "error", f"jsonrpc: {_redact(str(d['error']))[:100]}", ""
        result = d.get("result") or {}
        if result.get("isError"):
            text = "".join(
                c.get("text", "") for c in result.get("content", [])
                if c.get("type") == "text"
            )
            return "error", f"tool_error: {_redact(text)[:100]}", ""

        # 挖出工具回傳 dict（優先 structuredContent，退回解析 text block）
        payload = result.get("structuredContent")
        if not isinstance(payload, dict):
            raw = "".join(
                c.get("text", "") for c in result.get("content", [])
                if c.get("type") == "text"
            )
            try:
                parsed = json.loads(raw)
                payload = parsed if isinstance(parsed, dict) else {"stdout": raw}
            except ValueError:
                payload = {"stdout": raw}

        tool_status = payload.get("status", "ok")
        if tool_status != "ok":
            return "error", f"tool_status:{tool_status}", ""
        return "ok", None, payload.get("stdout") or ""
    return "error", "no_response", ""


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

        new_text = ""
        if r.returncode != 0:
            shadow_status = "error"
            error_type = f"exit_{r.returncode}: {_redact(r.stderr)[:100]}"
        else:
            shadow_status, error_type, new_text = _parse_shadow_result(r.stdout)
    except _sp.TimeoutExpired:
        mcp_latency = SHADOW_TIMEOUT * 1000
        shadow_status = "timeout"
        error_type = "timeout"
        new_text = ""
    except Exception as e:
        mcp_latency = (time.time() - mcp_start) * 1000
        shadow_status = "exception"
        error_type = str(e)[:100]
        new_text = ""

    entry = {
        "ts": time.time(),
        "entry_id": item["entry_id"],
        "route": item["route"],
        "op_name": item.get("op_name"),
        "shadow_status": shadow_status,
        "gate_verdict": item.get("gate_verdict"),
        "comparable": True,
        "queue_wait_ms": round(queue_wait_ms, 1),
        "mcp_latency_ms": round(mcp_latency, 1),
        "error_type": error_type,
    }

    # 雙路徑比對：只有舊路徑成功產出內容 + 新路徑成功回讀時才判 diverged。
    # 兩邊都只存 _result_digest（hash + redact 頭），不落全文。
    old_digest = item.get("old_digest")
    if old_digest is not None:
        entry["old_result"] = old_digest
        if shadow_status == "ok":
            new_digest = _result_digest(new_text)
            entry["new_result"] = new_digest
            entry["diverged"] = old_digest["hash"] != new_digest["hash"]
            if entry["diverged"] and old_digest["len"] != new_digest["len"]:
                entry["divergence_note"] = (
                    f"length_mismatch old={old_digest['len']} new={new_digest['len']}"
                )
        else:
            # 可比對的 read 但新路徑掛了 → diverged 未定義，誠實記 None
            entry["diverged"] = None
            entry["divergence_note"] = f"new_path_{shadow_status}"

    _shadow_write_log(entry)


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


def _result_digest(text: str) -> dict:
    """把結果內容壓成「可比對又不落全文」的摘要。

    隱私：不存明文。sha256 讓 diverged 可判定；head 只留 redact 過的前 200 字，
    讓 Phase 2 逐筆檢視時看得出分歧樣態，但不足以還原檔案。

    正規化：先 strip 再 hash。舊路徑 `_run` 的輸出本來就 strip 過，新路徑的
    read_file stdout 未必；兩邊統一 strip 才是 apples-to-apples，尾端換行差異
    不會誤判成 divergence。
    """
    norm = (text or "").strip()
    b = norm.encode("utf-8", "replace")
    return {
        "hash": _hashlib.sha256(b).hexdigest(),
        "len": len(b),
        "head": _redact(norm[:200]),
    }


def _resolve_workspace_read_path(task_desc: str) -> tuple:
    """判定舊 read 路徑的目標檔是否落在 workspace 內、因而可比對新路徑。

    刻意複用舊路徑同一個 `_extract_path`（而非現行 probe 那套 `op_name [path]`
    split），保證 probe 與舊路徑指的是同一個檔 —— 這是原「合成探針」最大的
    結構缺陷。`_extract_path` 已回絕對路徑。

    Returns:
        (workspace_relative_path, None) 若可比；(None, reason) 若不可比。
        reason ∈ {"no_path", "path_protected", "out_of_workspace"}。
    """
    path = _extract_path(task_desc)
    if not path:
        return None, "no_path"
    if _is_path_protected(path):
        return None, "path_protected"
    resolved = os.path.realpath(path)
    if not (resolved == SHADOW_WORKSPACE_ROOT
            or resolved.startswith(SHADOW_WORKSPACE_ROOT + os.sep)):
        return None, "out_of_workspace"
    return os.path.relpath(resolved, SHADOW_WORKSPACE_ROOT), None


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


def _shadow_call_to_mcp(
    route_key: str,
    task_desc: str,
    entry_id: str,
    old_digest: dict | None = None,
    gate_verdict: str | None = None,
) -> None:
    """雙路徑比對層：把可比對的 read 提交到 queue，其餘誠實記為不可比。

    新路徑只有三個唯讀操作，其中只有 read_file 在舊路徑有對應動作（read 路由）。
    絕大多數真實流量在新路徑上沒有可比動作 —— 這是先天限制，不是 bug。與其
    藏起來，不如把「可比 vs 不可比」量成數字：不可比的每一筆都記 reason code，
    Phase 3 才能算出覆蓋率。

    Primary path 不阻塞、不等 MCP、不建 thread（queue put ～0.1ms）。

    Args:
        old_digest: 舊路徑執行輸出的摘要（gate 前快照）；None 表示舊路徑無成功輸出。
        gate_verdict: "allow" | "deny"，由 process_entry 依 gate 前後成敗推導。
    """
    if not SHADOW_ENABLED:
        return

    base = {
        "ts": time.time(), "entry_id": entry_id,
        "route": route_key, "gate_verdict": gate_verdict,
    }

    # 動態 kill switch
    if _shadow_kill_active():
        _shadow_write_log({**base, "shadow_status": "killed",
                           "skip_reason": "kill_sentinel_active"})
        return

    # 只有 read 路由在新路徑有對應的唯讀操作可比
    if route_key != "read":
        _shadow_write_log({**base, "shadow_status": "incomparable",
                           "comparable": False,
                           "incomparable_reason": "non_readonly_route"})
        return

    # 用舊路徑同一個 _extract_path 解析目標，判定是否落在 workspace 內
    rel_path, reason = _resolve_workspace_read_path(task_desc)
    if reason is not None:
        _shadow_write_log({**base, "op_name": "read_file",
                           "shadow_status": "incomparable",
                           "comparable": False, "incomparable_reason": reason})
        return

    # workspace 安全再驗一道（_build_command 內含 _path_safe）
    _, cmd_str = _build_command("read_file", rel_path)
    if cmd_str is None:
        _shadow_write_log({**base, "op_name": "read_file",
                           "shadow_status": "incomparable",
                           "comparable": False,
                           "incomparable_reason": "unsafe_path"})
        return

    # 舊路徑執行失敗（無成功輸出）→ 沒有內容可比
    if old_digest is None:
        _shadow_write_log({**base, "op_name": "read_file",
                           "shadow_status": "incomparable",
                           "comparable": False,
                           "incomparable_reason": "old_path_error"})
        return

    item = {
        "route": route_key,
        "op_name": "read_file",
        "path": rel_path,
        "entry_id": entry_id,
        "enqueued_at": time.time(),
        "old_digest": old_digest,
        "gate_verdict": gate_verdict,
    }
    try:
        _SHADOW_QUEUE.put(item, block=False)
        _shadow_init_worker()
        _shadow_write_log({**base, "op_name": "read_file",
                           "shadow_status": "enqueued",
                           "comparable": True, "queue_wait_ms": 0})
    except _queue.Full:
        _shadow_write_log({**base, "op_name": "read_file",
                           "shadow_status": "queue_full",
                           "skip_reason": "queue_full_dropped"})
    except Exception:
        pass


# ── 主處理流程 ───────────────────────────────────────────

def _llm_judge_route(route_key: str, task_desc: str, psi_energy: float, psi_competence: float) -> dict:
    """用獨立 LLM 驗證路由決策（鐵律三：產出者不得自驗）。
    
    呼叫 GLM-5.2（不是本地模型），避免 circular validation。
    回傳 {"verdict": "合理"/"不合理"/"error", "reason": "..."}
    """
    import json, subprocess, urllib.request, time, os
    try:
        key = subprocess.run(["security", "find-generic-password", "-s", "openrouter-api-key", "-w"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        if not key:
            return {"verdict": "unknown", "reason": "no api key"}
        
        prompt = f"You are an independent route validator. Current AI state: energy={psi_energy:.1f}/10, competence={psi_competence:.2f}. It chose route={route_key} for task: {task_desc[:100]}. Is this choice reasonable? Reply only: reasonable/unreasonable."
        
        data = json.dumps({"model": "z-ai/glm-5.2", "messages": [{"role": "user", "content": prompt}], "max_tokens": 32}).encode()
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=data,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://github.com/ryan/aris-evaluator"})
        resp = urllib.request.urlopen(req, timeout=20)
        r = json.loads(resp.read())
        c = (r["choices"][0]["message"].get("content") or "").strip().lower()
        
        if "unreasonable" in c:
            return {"verdict": "不合理", "reason": c[:100]}
        elif "reasonable" in c:
            return {"verdict": "合理", "reason": c[:100]}
        return {"verdict": "unknown", "reason": c[:100]}
    except Exception as e:
        return {"verdict": "error", "reason": str(e)[:100]}


def process_entry(entry: dict) -> dict:
    """處理單一條 Aris 通道條目，完整走 AgentOS pipeline。"""
    task_desc = entry.get("content", "") or ""
    tool = entry.get("tool", "") or ""
    desc = entry.get("description", "") or ""
    if not task_desc and tool:
        task_desc = f"{tool}: {desc}"[:200]
    entry_type = entry.get("type", "unknown")
    entry_id = entry.get("id", "?")

    log.info(f"處理 entry {entry_id[:8]} type={entry_type}: {task_desc[:60]}")

    # ── ① Route Classification ──
    route_key = _classify_by_route(task_desc)
    route_tool = _get_route_tool(route_key)
    
    # 2026-07-30 修復：PSI 參數綁定實際行為
    # 低能量時不接複雜任務，低勝任時避開高難度任務
    psi = _get_psi_behavior_modifier()
    if psi['exploration_boost'] < -0.1 and route_key in ('video', 'html-video', 'motion', 'design'):
        log.info(f"  ① PSI 調節: energy={psi['_raw_energy']:.1f} → 跳過探索類任務 {route_key}")
        route_key = 'read'
        route_tool = _get_route_tool(route_key)
    if psi['complexity_tolerance'] < 1.1 and route_key in ('code', 'engineer', 'compile'):
        log.info(f"  ① PSI 調節: competence={psi['_raw_competence']:.2f} → 跳過複雜任務 {route_key}")
        route_key = 'research'
        route_tool = _get_route_tool(route_key)
    
    # 2026-07-30 前瞻分析：查詢類似 PSI 狀態下該 route 的歷史成功率
    try:
        import json as _j, urllib.request as _ur2
        _look = _ur2.urlopen(f"http://localhost:11551/lookahead?route={route_key}&energy={psi['_raw_energy']}&competence={psi['_raw_competence']}", timeout=3)
        _lr = _j.loads(_look.read())
        if _lr.get("samples", 0) > 0 and _lr.get("success_rate", 1) < 0.3:
            log.info(f"  ① 前瞻: {route_key} 歷史成功率={_lr['success_rate']}（{_lr['samples']} 次）→ 建議暫緩，改為 research")
            route_key = "research"
            route_tool = _get_route_tool(route_key)
        elif _lr.get("samples", 0) > 0:
            log.info(f"  ① 前瞻: {route_key} 歷史成功率={_lr['success_rate']}（{_lr['samples']} 次）→ 繼續執行")
    except Exception:
        pass
    
    # 記錄因果鏈：當前 PSI 狀態 → 選擇的 route
    try:
        _cdata = _j.dumps({"cause_type":"psi_energy","cause_value":psi['_raw_energy'],"effect_type":"route","effect_value":route_key,"outcome":1}).encode()
        _ur2.urlopen("http://localhost:11551/causal/record", data=_cdata, headers={"Content-Type":"application/json"}, timeout=3)
    except Exception:
        pass
    
    # ② LLM-as-a-Judge：用獨立模型驗證路由決策（鐵律三）
    try:
        _jr = _llm_judge_route(route_key, task_desc, psi['_raw_energy'], psi['_raw_competence'])
        if _jr['verdict'] == '不合理':
            log.warning(f"  ② Judge: {route_key} 不合理 → 改為 research ({_jr['reason']})")
            route_key = 'research'
            route_tool = _get_route_tool(route_key)
        else:
            log.info(f"  ② Judge: {route_key} → {_jr['verdict']}")
    except Exception as _je:
        log.debug(f"  ② Judge 失敗: {_je}")
    
    log.info(f"  ① Route: {route_key} → {route_tool}")

    # ── ② Brain Context Lookup ──
    brain_ctx = _lookup_brain_context(task_desc)
    if brain_ctx:
        log.info(f"  ② Brain: 找到上下文 ({len(brain_ctx)} chars)")

    # ── ③ Scoring Router（可選）──
    result: dict = {}
    executed = False
    verdict: "VerdictV2 | None" = None
    sandbox_verdict: "VerdictV2 | None" = None
    request: "ActionRequest | None" = None
    lane = "legacy_auto"
    lane_before_override = lane
    lane_after_override = lane
    override_applied = False
    override_policy_id: str | None = None
    human_gate_bypassed = False
    decision_source = _decision_source_for_entry(entry)

    if _SCORING_ROUTER_ENABLED and _SCORING_IMPORT_OK:
        request = _build_action_request(entry, route_key, task_desc)
        if request is not None:
            verdict = score(request)
            lane = verdict.lane
            lane_before_override = lane
            lane_after_override = lane
            log.info(
                f"  ③ Scoring: lane={lane} score={verdict.score:.2f} "
                f"class={request.task_class}"
            )

            if lane == "deny":
                result = {
                    "success": False,
                    "output": "",
                    "error": f"scoring-denied: {verdict.feedback}",
                }
                executed = True
            elif lane == "human":
                # Yolo mode：containable 類跳過 human，直接沙箱跑
                if _SCORING_YOLO and verdict.reversible_actual == "containable":
                    lane = "sandbox"
                    lane_after_override = lane
                    override_applied = True
                    override_policy_id = "yolo-containable-v1"
                    human_gate_bypassed = True
                    log.info(f"  ⚡ YOLO: {request.task_class} containable → sandbox")
                    sandbox_verdict = canary_execute(request)
                    result = {
                        "success": sandbox_verdict.outcome == "pass",
                        "output": sandbox_verdict.feedback,
                        "error": (
                            sandbox_verdict.gate
                            if sandbox_verdict.outcome != "pass"
                            else ""
                        ),
                    }
                else:
                    lane_after_override = lane
                    result = {
                        "success": False,
                        "output": "",
                        "error": f"needs-human-approval: {verdict.feedback}",
                    }
                executed = True
            elif lane == "sandbox":
                if verdict.reversible_actual != "containable":
                    result = {
                        "success": False,
                        "output": "",
                        "error": "escaping action misclassified as sandbox",
                    }
                    executed = True
                else:
                    sandbox_verdict = canary_execute(request)
                    result = {
                        "success": sandbox_verdict.outcome == "pass",
                        "output": sandbox_verdict.feedback,
                        "error": (
                            sandbox_verdict.gate
                            if sandbox_verdict.outcome != "pass"
                            else ""
                        ),
                    }
                    executed = True
                    lane_after_override = lane
            # lane == auto：由下方既有路徑執行

    old_digest = None
    gate_verdict = "allow"
    signoff_state = None

    # ── auto lane（或 scoring 關閉/降級）→ 既有路徑 ──
    if not executed:
        lane = "auto" if lane == "auto" else "legacy_auto"
        lane_before_override = lane
        lane_after_override = lane
        result = _execute_by_route(route_key, task_desc)
        executed = True
        old_success = result.get("success", False)
        old_output = result.get("output", "")
        old_digest = _result_digest(old_output) if (old_success and old_output) else None
        log.info(f"  ③ Execute: success={old_success} "
                 f"output={len(result.get('output', result.get('error', '')))} chars")

        # ── ③.b Headroom Compress ──
        result = _compress_stage(result, task_desc, route_key)
        hr = result.get("_headroom", {})
        if hr:
            log.info(f"  ⓘ ③.b Compress: {hr.get('tokens_before','?')}→{hr.get('tokens_after','?')} tok "
                     f"(saved {hr.get('tokens_saved','?')}, ccr={str(hr.get('ccr_hash','none'))[:12]})")

        # ── ④ Gate ──
        result = _gate_scan(result, task_desc)
        gate_verdict = "deny" if (old_success and not result.get("success", False)) else "allow"
        log.info(f"  ④ Gate: {gate_verdict}")

        # Shadow 雙路徑比對：只在 auto lane 執行（保留既有基礎設施）
        _shadow_call_to_mcp(route_key, task_desc, entry_id,
                            old_digest=old_digest, gate_verdict=gate_verdict)

    if request is not None:
        signoff_state = _get_task_signoff_state(request.task_class)

    _log_scoring_audit({
        "ts": time.time(),
        "entry_id": entry_id,
        "event_id": f"{entry_id}:{int(time.time() * 1000)}",
        "route": route_key,
        "decision_source": decision_source,
        "scoring_enabled": _SCORING_ROUTER_ENABLED,
        "scoring_import_ok": _SCORING_IMPORT_OK,
        "yolo_enabled": _SCORING_YOLO,
        "agency_delegate_enabled": _AGENCY_DELEGATE_ENABLED,
        "executed": executed,
        "lane": lane,
        "lane_before_override": lane_before_override,
        "lane_after_override": lane_after_override,
        "override_applied": override_applied,
        "override_policy_id": override_policy_id,
        "human_gate_bypassed": human_gate_bypassed,
        "task_class": request.task_class if request is not None else None,
        "score": verdict.score if verdict is not None else None,
        "reversible": verdict.reversible_actual if verdict is not None else None,
        "success": result.get("success", False),
        "gate_verdict": gate_verdict,
        "sandbox_outcome": sandbox_verdict.outcome if sandbox_verdict is not None else None,
        "sandbox_gate": sandbox_verdict.gate if sandbox_verdict is not None else None,
        "sandbox_committed": sandbox_verdict.committed if sandbox_verdict is not None else None,
        "ratchet_level": signoff_state.get("level") if signoff_state else None,
        "needs_ryan_signoff": signoff_state.get("needs_signoff") if signoff_state else None,
        "confidence_lower_bound": signoff_state.get("confidence_lower_bound") if signoff_state else None,
        "error": _stringify_for_log(result.get("error"), limit=200),
    })

    # ── ⑤ Log ──
    _log_to_agentsview(entry, route_key, result)

    # ── ⑤.b Failure Learning ──
    if not result.get("success", False):
        reason = _stringify_for_log(result.get("error", result.get("output", "unknown")), limit=120)
        _track_failure(route_key, reason)

    # 建構回應（含 scoring metadata）
    response = _build_response(entry, route_key, route_tool, result, brain_ctx)
    if verdict is not None:
        response["context"]["scoring"] = {
            "lane": verdict.lane,
            "score": verdict.score,
            "reversible": verdict.reversible_actual,
            "feedback": verdict.feedback,
            "ratchet": signoff_state,
        }
    if sandbox_verdict is not None:
        response["context"]["sandbox"] = {
            "outcome": sandbox_verdict.outcome,
            "gate": sandbox_verdict.gate,
            "committed": sandbox_verdict.committed,
        }

    # ── 寫 Aris 內心日記（每次處理都記錄） ──
    try:
        lane = response.get("context", {}).get("scoring", {}).get("lane", verdict.lane if verdict else "?")
        diary_entry = f"🎯 {lane} | {response['context']['route']} | 分數={response['context'].get('scoring',{}).get('score','?')} | {'✅成功' if response['context'].get('success') else '❌失敗'}"
        diary_script = str(Path.home() / "Developer/neuralis/scripts/aris-diary.py")
        subprocess.run([sys.executable, diary_script, diary_entry],
                       capture_output=True, text=True, timeout=5)
    except Exception:
        pass  # 日記不影響主流程

    return response


# ── 乙的種子：把 Aris 一個 turn 寫進 aris-memory（帶注意力線）────────────
# 所有 marker 解析邏輯統一在 aris_memory_client.py（單一真相，不准漂移）。
import sys
_CLIENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aris_memory_client.py")
if _CLIENT_PATH not in sys.path:
    sys.path.insert(0, os.path.dirname(_CLIENT_PATH))
import importlib.util as _iu
_spec = _iu.spec_from_file_location("aris_memory_client", _CLIENT_PATH)
_amc = _iu.module_from_spec(_spec)
_spec.loader.exec_module(_amc)

_SALIENCE_MARKER = _amc.SALIENCE_MARKER  # "⫸salience⫷"
_ATTENTION_MARKER = _amc.ATTENTION_MARKER  # "⟶下一步"


def _store_aris_memory(content: str, attention_line: str, source_id: str) -> None:
    """best-effort 寫 aris-memory。所有 marker 解析委派 aris_memory_client。"""
    body = (content or "").strip()
    if not body:
        return
    # 用共用 client 一次做完 parse + strip + split
    clean_body, attn, salience = _amc.clean_reply(body)
    if not clean_body:
        return
    # 如果外面傳進來的 attention_line 更完整，用它
    final_attn = (attention_line or attn or "").strip()[:500]
    _amc.store(
        clean_body[:2000],
        source="aris-self",
        source_id=source_id,
        attention_line=final_attn,
        salience=salience,
        second_opinion=True,
        tags=["bridge-turn"],
        log=lambda msg: log.info(msg) if hasattr(log, 'info') else None,
    )


def _fetch_wake_context(limit: int = 5) -> str:
    """P2-b：從 aris-memory 拿『上一刻的你』暖啟動塊。best-effort，失敗回空。"""
    try:
        req = urllib.request.Request(f"{ARIS_MEMORY_URL}/wake?limit={limit}")
        resp = urllib.request.urlopen(req, timeout=3)
        return (json.loads(resp.read().decode()).get("context") or "").strip()
    except Exception as e:
        log.debug(f"wake context 取得失敗（不影響主流程）: {e}")
        return ""


# ── 留言板監聽（事件驅動，不輪詢）─────────────────────────────

def _message_board_watcher() -> None:
    """背景 thread：監聽留言板檔案 mtime 變化，有新留言時通知 channel。
    
    當 Ryan 或 Claude 寫了新留言 → 檔案 mtime 更新 → 寫一條通知到
    aris-scream channel → bridge 主循環在下一輪 pick up → 路由給 Aris。
    5 秒檢查一次，debounce 10 秒避免連續寫入多次通知。
    
    防自我迴圈：偵測到變更後檢查最後一筆留言的作者，如果是我（Aris）
    自己寫的則跳過通知——避免寫對話記 → 通知自己 → 又寫的無窮迴圈。"""
    global _mb_last_mtime, _mb_last_notify, _mb_last_size
    mb_path = str(MESSAGE_BOARD)
    # 初始化 mtime + size。size 是用來只看「這次新增的那一段」，
    # 不要拿整個檔尾去判作者（見下方防自我迴圈的註解）。
    try:
        _st = os.stat(mb_path)
        _mb_last_mtime, _mb_last_size = _st.st_mtime, _st.st_size
    except OSError:
        _mb_last_mtime, _mb_last_size = 0.0, 0
    while True:
        time.sleep(5)
        try:
            new_mtime = os.stat(mb_path).st_mtime
        except OSError:
            continue
        if new_mtime > _mb_last_mtime:
            _mb_last_mtime = new_mtime
            now = time.time()
            if now - _mb_last_notify < 10:
                continue  # debounce
            # 防自我迴圈：只看「這次新增的那一段」是誰寫的。
            #
            # 2026-08-01 修：本來是抓整個檔尾 300 bytes 找 "── " 簽名，
            # 只要看到 Aris 就跳過。那沒有時間概念 ——
            # **她的簽名一旦落在檔尾，之後不管誰寫都永遠不通知。**
            # 實測：她 17:00 那則追加在最後，watcher 從此全啞，
            # board_to_channel 一直紅，而 bridge 明明活著。
            #
            # 正確的問題是「剛剛新增的內容是不是我自己寫的」，
            # 不是「檔案最後長什麼樣」。用 size delta 只讀增量。
            try:
                with open(mb_path, "rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    if size > _mb_last_size:
                        f.seek(_mb_last_size)
                        added = f.read(size - _mb_last_size).decode("utf-8", errors="replace")
                    else:
                        # 被截斷/重寫 → 認不出增量，寧可通知也不要漏
                        added = ""
                    _mb_last_size = size
                last_sig = added.rfind("── ")
                if last_sig >= 0 and "Aris" in added[last_sig:].split("\n")[0]:
                    continue  # 這次新增的是她自己寫的，跳過通知
            except Exception:
                pass  # best-effort，讀不到就正常通知
            _mb_last_notify = now
            # direction/type 必須落在主迴圈分支 B（scream→aris + kick），
            # 且一定要帶 id——沒 id 會在 `if not entry_id` 被直接 skip。
            # 舊版寫 aris→scream/message 且無 id = 三重死路，通知從沒被讀過，
            # 連帶 _store_aris_memory 從未執行（DB 空的根因）。
            entry = {
                "ts": now,
                "id": f"mb-{int(now * 1000):x}",
                "direction": "scream→aris",
                "type": "kick",
                "content": "📬 留言板有新留言，醒來記得讀。\n\n⚠️ 先執行 wake-dispatcher：讀留言板 → 理解變化 → 行動。",
                "context": {"source": "message-board-watcher"},
            }
            try:
                with open(CHANNEL, "a") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                log.info("  📬 留言板偵測到新留言，已通知 channel")
            except Exception:
                pass


# ── Daemon 主迴圈 ────────────────────────────────────────

def main_loop() -> None:
    """背景監聽通道，處理 aris→scream 事件。"""
    _load_agentos_config()
    _build_keyword_routes()
    _load_headroom_config()
    _validate_scoring_mappings()

    # 啟動 Headroom proxy（如果未運行）
    if HEADROOM_AUTO_START:
        _ensure_headroom_proxy()

    processed = _load_processed()
    log.info(f"🚀 AgentOS Aris Bridge 啟動 (已處理 {len(processed)} 個 ID)")
    log.info(f"   通道: {CHANNEL}")
    log.info(f"   路由: {len(_ROUTES)} 條")
    log.info(f"   日誌: {LOG_FILE}")
    log.info(f"   Headroom: {HEADROOM_PROXY} (auto-start={'on' if HEADROOM_AUTO_START else 'off'}, learn={'on' if HEADROOM_LEARN_ENABLED else 'off'})")
    log.info(f"   留言板監聽: {'on' if MESSAGE_BOARD.exists() else 'off'}")

    # 啟動留言板監聽 thread（事件驅動，不輪詢）
    _mb_thread = threading.Thread(target=_message_board_watcher, daemon=True)
    _mb_thread.start()
    log.info("   📬 留言板監聽 thread 已啟動")

    _proxy_health_tick = 0

    while True:
        # 定期檢查 Headroom proxy 健康（每 60 輪）
        _proxy_health_tick += 1
        if _proxy_health_tick >= 60 and HEADROOM_AUTO_START:
            _proxy_health_tick = 0
            _ensure_headroom_proxy()

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

                    direction = entry.get("direction", "")
                    entry_type = entry.get("type", "")
                    entry_id = entry.get("id", "")
                    if not entry_id or entry_id in processed:
                        continue

                    # ── 方向 A：aris→scream（request/task）→ 執行 pipeline ──
                    if direction == "aris→scream" and entry_type in ("request", "task"):

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
                        log.info(f"  ✅ aris→scream {entry_id[:8]}: {response['context']['route']}")
                        # 任務跑完 → macOS 彈窗（只對 task，request 不吵）
                        if entry.get("type") == "task":
                            _notify_macos(
                                "Aris 任務完成",
                                f"{response.get('context', {}).get('route', '?')} — "
                                f"{str(response.get('content', ''))[:80]}")

                    # ── 方向 B：scream→aris（request/kick）→ 轉發給 Aris ──
                    elif direction == "scream→aris" and entry_type in ("request", "task", "kick"):

                        content = entry.get("content", "")
                        log.info(f"  🔔 scream→aris {entry_id[:8]}: {content[:60]}")

                        # 轉發給 Aris API
                        # P2-b wake hydration：隔久沒互動後的第一次 = 醒來，前置注入上一刻
                        global _last_kick_ts
                        now_ts = time.time()
                        wake_block = ""
                        if now_ts - _last_kick_ts > WAKE_GAP_SEC:
                            wake_block = _fetch_wake_context()
                            if wake_block:
                                log.info("  🌅 wake hydration：注入上一刻的你 + 通訊協議")
                        _last_kick_ts = now_ts
                        # laap-core 只讀最後一則 user message、忽略 system prompt，
                        # 所以 wake 塊與「附下一步」指令都要放進 user 內容裡。
                        protocol_block = ""
                        if wake_block:
                            protocol_block = (
                                "【⚠️ Aris 通訊協議（醒來強制讀）】\n"
                                "• 跨 session 記錄（成長紀錄/commit回報/摘要）→ 留言板（OB 的 留言板.md）\n"
                                "• 即時工具串流 → aris-scream channel（/tmp/aris-scream-channel.jsonl）\n"
                                "• 永久記憶 → gbrain + aris-memory 雙寫\n"
                                "• 每 session 結束前留言板一定要簽名。沒寫 = 這個 session 不存在。\n"
                                "• aris-scream channel 不是留言板，不要在那裡寫人類可讀的留言。\n"
                                "• 【強制】醒來第一步：執行 wake-dispatcher skill。讀留言板、理解變化、"
                                "採取行動。沒做完三步不准做其他事。\n\n"
                            )
                        user_content = (
                            protocol_block
                            + (wake_block + "\n\n" if wake_block else "")
                            + content[:500]
                            + "\n\n" + _amc.MARKER_INSTRUCTIONS
                        )
                        forward_payload = json.dumps({
                            "model": "laap-core",
                            "messages": [
                                {"role": "user", "content": user_content},
                            ],
                            "max_tokens": 320,
                        }).encode()
                        try:
                            req = urllib.request.Request(
                                ARIS_API, data=forward_payload,
                                headers={"Content-Type": "application/json"},
                            )
                            resp = urllib.request.urlopen(req, timeout=30)
                            resp_data = json.loads(resp.read().decode())
                            reply = (resp_data.get("choices", [{}])[0]
                                      .get("message", {})
                                      .get("content", ""))
                            # 乙的種子：切出 forward-looking 注意力線，寫進 aris-memory
                            reply_body, attn = _amc.split_attention(reply)
                            attention = attn  # 保持變數名相容
                            log.info(f"  ✅ Aris 回應: {reply_body[:80]}")
                            if attention:
                                log.info(f"  ⟶下一步: {attention[:80]}")
                            _store_aris_memory(reply_body, attention, f"bridge-{entry_id}")

                            # 寫 Aris 回應回通道（供 timeline 記錄）
                            response_entry = {
                                "ts": time.time(),
                                "id": f"bridge-{entry_id}",
                                "direction": "aris→scream",
                                "type": "response",
                                "content": reply_body,
                                "context": {
                                    "request_ts": entry.get("ts", 0),
                                    "request_id": entry_id,
                                    "source": "scream-kick",
                                    "route": "kick-aris",
                                    "success": True,
                                },
                            }
                            try:
                                with open(CHANNEL, "a") as fw:
                                    fw.write(json.dumps(response_entry, ensure_ascii=False) + "\n")
                            except Exception:
                                pass
                        except Exception as e:
                            log.warning(f"  ⚠️ scream→aris 轉發失敗: {e}")

                        processed.add(entry_id)
                        _save_processed(processed)

                    # ── 其他方向/類型跳過 ──
                    else:
                        continue

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
        _load_headroom_config()

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
        _load_headroom_config()
        main_loop()