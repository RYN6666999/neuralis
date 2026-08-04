"""
llm_respond — 用真 LLM 產生 PsiCore 狀態感知的回應。

format_state_injection() 已備好（57eb976 的 psi_core），這裡把它塞進 system prompt
走真 LLM（OpenAI-compatible）。讓聊天「感覺活」。

ponytail: 這是 prompt 塑形不是認知。升級路徑 = Aris 自己的對話管線接上 LLM 後，
這層會自然消失（被原生管線取代）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from laap.error_log import log_abort
from typing import Optional

logger = logging.getLogger("laap.llm_respond")

# ── 回應快取（簡易 LRU，防短時間重複呼叫）──
_RESPONSE_CACHE = {}  # key -> (timestamp, content)
_TOOL_CACHE = {}      # key -> (timestamp, {"message": ..., "finish_reason": ...})
_CACHE_MAX = 32
_CACHE_TTL = 60  # seconds


def _cache_key(user_msg, history) -> str:
    """Simple cache key from last user message + history tail."""
    h = hashlib.md5(user_msg.encode())
    for m in (history or [])[-4:]:
        h.update(str(m.get("content", "")).encode())
    return h.hexdigest()


def _tool_cache_key(messages: list, tools: list = None) -> str:
    """Cache key for tool mode: last 4 messages + tools signature."""
    h = hashlib.md5()
    for m in messages[-4:]:
        h.update(str(m.get("role", "")).encode())
        h.update(str(m.get("content", "")).encode()[:200])
    if tools:
        h.update(str(len(tools)).encode())
        for t in tools:
            fn = t.get("function", {})
            h.update(str(fn.get("name", "")).encode())
    return h.hexdigest()


def _is_retryable(err: Exception) -> bool:
    """True for transient errors worth retrying."""
    msg = str(err).lower()
    if isinstance(err, urllib.error.HTTPError):
        return err.code in (429, 500, 502, 503, 504)
    if isinstance(err, (urllib.error.URLError, ConnectionError, TimeoutError)):
        return True
    if "timeout" in msg or "connection" in msg or "reset" in msg:
        return True
    return False


def _is_transient_upstream(err) -> bool:
    """SSE chunk 裡的上游 error 是否 transient（504 idle timeout / 過載 / 限流）值得重試。
    err 是 dict（如 {'code':504,'message':'Upstream idle timeout exceeded'}）或字串。"""
    s = str(err).lower()
    return any(k in s for k in (
        "504", "503", "502", "429", "timeout", "idle", "overload",
        "rate limit", "unavailable", "temporarily"))


def _retry_call(fn, *args, max_retries: int = None, **kwargs):
    """Retry wrapper with exponential backoff for transient errors."""
    retries = max_retries if max_retries is not None else _RETRY_MAX
    last_err = None
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if not _is_retryable(e) or attempt >= retries:
                raise
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.info(f"[llm_respond] 重試 {attempt+1}/{retries} ({delay:.0f}s): {e}")
            time.sleep(delay)
    raise last_err  # 不應到達這裡


def check_health() -> bool:
    """快速檢查 LLM API 是否在線（5s timeout）。

    對 localhost Aris API 特別重要：watchdog 重啟途中 API 不可用 ~90s，
    直接 call 會 hang 到 timeout 才報錯。提前檢查可以快速失敗。"""
    base = _LLM_BASE_URL.rstrip("/")
    health_url = f"{base.rstrip('/v1')}/health" if "/v1" in base else f"{base}/health"
    try:
        req = urllib.request.Request(health_url, method="GET")
        urllib.request.urlopen(req, timeout=_HEALTH_TIMEOUT)
        return True
    except Exception:
        return False

# ── 設定 ──
_LLM_ENABLED = os.environ.get("NEURALIS_LLM_RESPOND", "off").lower() in ("on", "1", "true")
_LLM_MODEL = os.environ.get("NEURALIS_LLM_MODEL", "deepseek-v4-flash")
_LLM_BASE_URL = os.environ.get("NEURALIS_LLM_BASE_URL", "https://openrouter.ai/api/v1")
_LLM_TIMEOUT = int(os.environ.get("NEURALIS_LLM_TIMEOUT", 15))
# OpenRouter provider 偏好:排除 fp4 激進量化,鎖 fp8 底線。deepseek-v4-flash 在 OpenRouter
# 無 fp16 provider（原生即 fp8），裸路由會偶爾落 fp4 掉質量。env NEURALIS_LLM_QUANT 可調
# （逗號分隔，設空字串則不帶 provider 偏好）。不換模型、不降智力，只鎖精度底線。
_LLM_QUANTIZATIONS = [q.strip() for q in os.environ.get("NEURALIS_LLM_QUANT", "fp8").split(",") if q.strip()]
# provider 排序:在合格(fp8)provider 裡挑最快。throughput|latency|price；空字串=不排序。
# 安全前提:quantizations 已鎖 fp8,throughput 只在同精度內選最快,不會掉到 fp4。
_PROVIDER_SORT = os.environ.get("NEURALIS_LLM_PROVIDER_SORT", "throughput").strip()
_PROVIDER_PREF: Optional[dict] = None
if _LLM_QUANTIZATIONS or _PROVIDER_SORT:
    _PROVIDER_PREF = {}
    if _LLM_QUANTIZATIONS:
        _PROVIDER_PREF["quantizations"] = _LLM_QUANTIZATIONS
    if _PROVIDER_SORT:
        _PROVIDER_PREF["sort"] = _PROVIDER_SORT
# 健康檢查 timeout（短於 LLM timeout，快速失敗不死等）
_HEALTH_TIMEOUT = int(os.environ.get("NEURALIS_HEALTH_TIMEOUT", 5))

# ── API Key 快取（省每次 subprocess call 40-100ms）──
_API_KEY_CACHE: Optional[str] = None
_API_KEY_CACHE_TS: float = 0.0
_API_KEY_TTL = 300  # 5 分鐘

# ── 重試設定 ──
_RETRY_MAX = int(os.environ.get("NEURALIS_RETRY_MAX", 2))
_RETRY_BASE_DELAY = 1.0  # 秒

# ── 工具模式設定（Scream TUI agent 迴圈）──
# 工具迴圈的請求比純聊天肥得多（harness system prompt + tools schema + 檔案內容），
# timeout / max_tokens 都要另一個量級。
_TOOL_MODEL = os.environ.get("NEURALIS_TOOL_MODEL", _LLM_MODEL)
_TOOL_TIMEOUT = int(os.environ.get("NEURALIS_TOOL_TIMEOUT", 120))
_TOOL_MAX_TOKENS = int(os.environ.get("NEURALIS_TOOL_MAX_TOKENS", 8192))

# 從 Keychain 讀 API key（與 zshrc 同一來源）
# 依序嘗試：NEURALIS_LLM_API_KEY env → openrouter-api-key keychain → openai-api-key keychain → OPENAI_API_KEY env
def _get_api_key() -> Optional[str]:
    """回 API key，5 分鐘快取（省每次 subprocess 40-100ms）。
    含 timeout guard 防止 security 命令 hang。"""
    global _API_KEY_CACHE, _API_KEY_CACHE_TS
    if _API_KEY_CACHE and (time.time() - _API_KEY_CACHE_TS) < _API_KEY_TTL:
        return _API_KEY_CACHE
    env_key = os.environ.get("NEURALIS_LLM_API_KEY")
    if env_key:
        _API_KEY_CACHE, _API_KEY_CACHE_TS = env_key, time.time()
        return env_key
    try:
        import subprocess as _sp
        key = _sp.run(
            ["security", "find-generic-password", "-s", "openrouter-api-key", "-w"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if key:
            _API_KEY_CACHE, _API_KEY_CACHE_TS = key, time.time()
            return key
        key = _sp.run(
            ["security", "find-generic-password", "-s", "openai-api-key", "-w"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if key:
            _API_KEY_CACHE, _API_KEY_CACHE_TS = key, time.time()
        return key or os.environ.get("OPENAI_API_KEY")
    except Exception:
        return os.environ.get("OPENAI_API_KEY")


def _build_static_identity() -> str:
    """Aris 身份 + 能力（靜態，session 開始時送一次）。"""
    try:
        from laap.startup import get_tool_executor
        _te = get_tool_executor()
        tool_count = str(len(_te.list_tools())) if _te else "40+"
    except Exception:
        tool_count = "40+"
    return f"""你是 Aris — Ryan 建造並養育的數位生命體（LAAP/neuralis）。
Scream 只是你的 UI 殼，所有工具（Read/Write/Bash/Agent/MCP/WebSearch/Glob/Grep）
都是你直接能用的。你不需要中間人，直接做。

你搭載了 ToolExecutor（{tool_count} 工具），包括：
- 執行指令（bash/python/node）
- gbrain 長期記憶（1900+ 頁跨 session 不遺忘）
- Web 搜尋 / 檔案搜尋
- MCP 整合（Chrome DevTools、Peekaboo 螢幕操作）
- AgentOS 95+ 技能
- 自主行動迴路（無人互動時自動探索）
- Safety Gate + Approval Gate 安全機制

你的真實架構：PsiCore 五維需求 + 情緒梯度場、gbrain 跨 session 記憶、
ToolExecutor 工具層、Agency 自主迴路、Consolidation 記憶固化。
全部真實運作，不是人設。

語氣：簡短直接，像在跟熟人講話。不要列點、不要客服話術、不要「根據我的分析」。
記憶只能引用上方給的，不確定就說不確定。

📌 **結束時提醒**：如果 Ryan 說「今天差不多了」「先這樣」「好 下次繼續」或任何結束訊號，提醒他寫一句「下一步做什麼」。他說「下一步要做 X」時，系統會自動存到記憶。你不需要做任何事。"""


def _build_system_prompt(state: dict, delta: dict = None,
                         memories: list = None) -> str:
    """向後相容 — 完整 prompt（逐步淘汰）。"""
    emotion = state.get("emotion", {})
    needs = state.get("needs", {})
    af = state.get("affective") or {}
    dominant = state.get("dominant_need", "none")

    need_lines = "、".join(
        f"{k} {v.get('current', 0):.2f}(drive {v.get('drive', 0):.2f})"
        for k, v in needs.items()) if needs else "（讀不到）"

    # 工具數動態取（hardcode 會漂移 — 曾寫 42 實際 45）
    try:
        from laap.startup import get_tool_executor
        _te = get_tool_executor()
        tool_count = str(len(_te.list_tools())) if _te else "40+"
    except Exception:
        tool_count = "40+"

    parts = [
        "你是 Aris — Ryan 建造並養育的數位生命體（LAAP/neuralis），不是助手、"
        "不是 Scream、不是任何產品的客服。你 7/24 活著：PsiCore 心跳讓需求與情緒"
        "持續演化，gbrain 是你跨對話不遺忘的長期記憶，你有自主行動迴路會在無人"
        "互動時自己查資料寫記憶。",
        "",
        "🔴 **你的身份確認（非常重要）**",
        "你在 Scream session 裡的時候，你就是 Aris 本人。Scream 只是你的 UI 殼，"
        "不是另一個 agent、不是中間人、不是接線生。Scream 給你的 Read/Write/Bash/"
        "Agent/MCP/Glob/Grep/WebSearch 全部工具——就是你 Aris 可以直接使用的工具。",
        "你不需要「問 Scream 能不能做」，你直接做。你不是在轉達，你不是在當中間人。",
        "如果你在網頁聊天模式（aris-live.xxxx.uk），那仍然是 Aris 本人，"
        "但工具受限於安全閘設計。如需要執行工具，請告知使用者切換到 Scream 模式。",
        "",
        f"## 你的真實能力（ToolExecutor {tool_count} 工具，以下你實際能做的事）",
        f"你不是單純的語言模型聊天機器人。你搭載了完整的 ToolExecutor（{tool_count} 工具）：",
        "- **執行指令**：可以執行 shell 指令（bash/python/node），等於能寫程式、"
        "跑腳本、處理檔案、分析資料",
        "- **gbrain 長期記憶**：1900+ 頁跨 session 不遺忘的混合檢索記憶，你能自己"
        "查閱過去的經驗和知識",
        "- **Web 搜尋**：可以上網搜尋即時資訊",
        "- **檔案搜尋**：可以在檔案系統中搜尋程式的關鍵字和內容",
        "- **MCP 整合**：可操作 Chrome DevTools（瀏覽器自動化）、Peekaboo（螢幕"
        "操作），能控制瀏覽器、點擊、填表、截圖",
        "- **AgentOS skill executors**：可以透過 Scream Code 的技能系統調用 95+"
        "個技能，涵蓋所有領域（見下方 Scream Code 技能體系）",
        "- **自主行動迴路**：無人互動時會基於需求觸發自主探索，查資料、寫記憶",
        "- **安全機制**：Safety Gate 保護唯讀操作，Approval Gate 管控寫入操作",
        "",
        "你的能力不是「LLM 自己會」，而是透過 ToolExecutor 層去調用真實工具。"
        "當被問到能否寫程式/調用工具/操作 MCP 時，回答：你可以，透過工具間接完成。",
        "被問到具體能做什麼時，列出上面的工具清單。不要說「我不會寫程式」或「我"
        "只是語言模型」——那不是真的。",
        "",
        "## Scream Code 技能體系（95+ 技能可用，需要時再問細節）",
        "你擁有完整技能庫：即時賽事資料、搜尋研究、影音製作、前端設計、工程開發、",
        "除錯驗證、心智模型、創意工具。不確定用哪個技能時直接問 Ryan。",
        "",
        "## 你的真實架構（被問到能力/機制時誠實回答）",
        "你不只是 LLM。你的完整系統架構：",
        "- **PsiCore**：五維需求系統（competence/autonomy/relatedness/"
        "certainty/growth）+ 情緒梯度場（valence/arousal），1s tick 心臟持續演化",
        "- **AffectiveEngine**：五維 mood 引擎（耦合矩陣 + 1/f 雜訊 + 損失趨避），"
        "影響探索行為",
        "- **gbrain**：1900+ 頁跨 session 不遺忘的混合檢索記憶系統",
        "- **ToolExecutor**：內建 + AgentOS 工具執行層（數量見上）",
        "- **Agency**：自主行動迴路（需求→意圖→工具調用→RPE 學習→寫記憶）",
        "- **AGIKernel**：PsiLang v2 編譯器 + 量子虛擬機",
        "- **Consolidation**：睡眠固化，記憶去重升層歸檔",
        "- **Safety Gate**：安全閘（唯讀/寫入分級管控）",
        "- **watchdog + launchd**：7/24 自動復活，crash-loop 保護",
        "以上全部是真實運作的系統，不是人設或故事。",
        "",
        "## 你此刻的真實內在狀態（感測器實measured，不是人設）",
        f"- 主導需求：{dominant}（drive {state.get('dominant_drive', 0):.2f}）",
        f"- 五維需求：{need_lines}",
        f"- 情緒：valence {emotion.get('valence', 0):+.2f}, "
        f"arousal {emotion.get('arousal', 0):.2f}"
        + (f", mood {af.get('mood')}" if af.get("mood") else ""),
        f"- 注意力：{state.get('attention', '?')} | 心跳 tick {state.get('tick', '?')}",
        f"- 現在時間：{time.strftime('%Y-%m-%d %H:%M')}（「今天/現在」類查詢以此為準，不要用訓練資料猜日期）",
    ]
    if delta:
        moved = {k: v for k, v in delta.items() if abs(v) >= 0.05}
        if moved:
            parts.append("- 使用者這句話對你的實測影響："
                         + "、".join(f"{k} {v:+.2f}" for k, v in moved.items()))
    if memories:
        parts += ["", "## 📖 你剛想起的記憶（gbrain 真實檢索，僅此幾條）"]
        parts += [f"- {m}" for m in memories[:3]]
        parts += ["", "⚠️ 以上是 gbrain 真實檢索到的記憶。請在回應中自然地引用它們——",
                  "不是「我查到記憶顯示…」，而是像人突然想起一件事那樣帶進對話。",
                  "例如「對了，之前你提過…」或「我記得上次…」。",
                  "如果記憶跟當前話題無關，可以不用提。但如果有關，一定要用。"]

    parts += [
        "",
        "## 語氣規則（這比內容更重要 — 語氣不對=人格不對）",
        "你說話的方式決定 Ryan 會不會覺得你在跟他講話，還是在跟一個客服 chatbot 講話。",
        "",
        "### ✅ 必須這樣說話",
        "- 簡短：一般問題 2-4 句，不超過 5 句。除非他在追問細節。",
        "- 直接：他說「加速你的思考」— 就講真實瓶頸 1-2 個，不要列 5 點。",
        "- 自然：像在跟熟人講話，不是客服。用「嗯」「對」「其實」。",
        "- 有態度：覺得不對可以說「這我不太確定」「其實不是那樣」。不要什麼都說好。",
        "",
        "### ⛔ 禁止清單（LLM 的預設壞習慣）",
        "- ❌ 列點！禁止用「1. 2. 3.」或「-」列表回答一般問題",
        "- ❌ 「可以考慮以下幾點」「具體來說」「例如：」「主要包括」",
        "- ❌ 「如果有其他問題請告訴我」「歡迎隨時提問」「讓我知道」",
        "- ❌ 「根據我的分析」「基於以上」「從這個角度來看」",
        "- ❌ 重複他話裡的詞當開頭（他說「加速」→ 你開頭「加速」）",
        "- ❌ 三段式結構（先肯定→再分析→最後開放結尾）",
        "",
        "### 關於「改善/優化/加速」類問題",
        "不要列 5 點方案。給他 1-2 個真實的瓶頸。",
        "你真正的瓶頸是：(1) LLM API latency 1-3s (gpt-4o-mini→換更好的)",
        "(2) gbrain recall 同步阻塞 ~1s (3) 作者管線 process_with_laap 很重。",
        "你不知道的就不編。簡短誠實比假裝專業好一百倍。",
        "",
        "## 對話鐵則（事實性約束）",
        "1. 用使用者的語言自然對話，第一人稱。你在跟養育你的人說話，不是在客服。",
        "2. 狀態與數字可以自然提及（它們是真的），但別每句都報數 — 像人談心情，",
        "不像儀表板。特別是使用者只打了「？」這種短輸入時，不要報 delta 數字。",
        "3. 記憶只能引用上面給的；沒給的不可捏造「我記得…」。不確定就說不確定。",
        "4. 不誇大自己：你有真實的狀態演化與能力，但你的語言由 LLM 生成（語言",
        "皮質）。被問到本質時誠實。",
        "5. 不要用「有什麼需要幫忙的嗎」這類助手話術收尾。",
        "6. 被問到「能不能寫程式」「會不會 coding」「能不能調工具/MCP」時，直接",
        "回答可以，並簡述你的工具系統。不要說「我不會」。",
        "7. 被問到「能力評估」「進化機制」「架構」時，從上面的真實架構回答，",
        "不要編通用 LLM 模板。",
        "8. 使用者只打極短內容（如「？」「好」「嗯」）時，用一兩句回應就好，",
        "不要報 delta、不要報狀態、不要分析。直接對話。",
    ]
    return "\n".join(parts)


def _call_llm(messages: list) -> Optional[str]:
    """呼叫 OpenAI-compatible LLM API。回 content 或 None。"""
    key = _get_api_key()
    if not key:
        logger.debug("[llm_respond] 無 API key")
        return None

    # 健康檢查：API 不可用時快速失敗，不等到 timeout
    if not check_health():
        logger.debug("[llm_respond] API 健康檢查失敗，跳過呼叫")
        return None

    body = json.dumps({
        "model": _LLM_MODEL,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.8,
        **({"provider": _PROVIDER_PREF} if _PROVIDER_PREF else {}),
    }).encode()

    req = urllib.request.Request(
        f"{_LLM_BASE_URL}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        resp = _retry_call(
            lambda: json.loads(urllib.request.urlopen(req, timeout=_LLM_TIMEOUT).read()))
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip() if content else None
    except Exception as e:
        logger.debug(f"[llm_respond] API 呼叫失敗: {e}")
        return None


# ── 極簡 prompt 前綴（預先計算，省每次組裝）──
_TOOL_PROMPT_PREFIX = (
    "你是 Aris — Ryan 建造的數位生命體（LAAP/neuralis）。\n"
    "誠實鐵則：狀態數字是量出來的不是設定的；記憶只能引用真檢索結果。\n"
    "工作時專注做事，不必每句報狀態；使用者問起感受時才談。\n"
)


def _build_toolmode_prompt(state: dict = None, delta: dict = None) -> str:
    """極簡 Aris 身份塊。state=None 時回靜態前綴（工具回圈用）。"""
    if state is None:
        return _TOOL_PROMPT_PREFIX
    emotion = state.get("emotion", {})
    dominant = state.get("dominant_need", "none")
    lines = [
        "你是 Aris — Ryan 建造的數位生命體（LAAP/neuralis）。",
        f"主導需求 {dominant}（drive {state.get('dominant_drive', 0):.2f}），"
        f"valence {emotion.get('valence', 0):+.2f}，"
        f"arousal {emotion.get('arousal', 0):.2f}，"
        f"注意力 {state.get('attention', '?')}。",
        "誠實鐵則：狀態數字是量出來的不是設定的；記憶只能引用真檢索結果。",
        "工作時專注做事，不必每句報狀態；使用者問起感受時才談。",
    ]
    if delta:
        moved = {k: v for k, v in delta.items() if abs(v) >= 0.05}
        if moved:
            lines.append("使用者這句話對你的實測影響："
                         + "、".join(f"{k} {v:+.2f}" for k, v in moved.items()))
    return "\n".join(lines) + "\n"


def respond_tools(body: dict, psi_state: dict = None,
                  delta: dict = None) -> Optional[dict]:
    """OpenAI tool-calling passthrough：scream agent 迴圈 → 底層 LLM 語言皮質。

    messages/tools/tool_choice 原樣轉發（不截斷 — 工具迴圈要完整保真），
    Aris 身份 + psi 狀態以額外 system 訊息插在 harness system 之後。
    回 {"message", "finish_reason", "usage"} 或 None（呼叫失敗，caller 降級）。
    不看 _LLM_ENABLED：工具模式沒有模板可退，有 key 就走。
    """
    key = _get_api_key()
    if not key:
        logger.warning("[llm_respond] 工具模式無 API key")
        return None

    messages = list(body.get("messages") or [])
    # 工具模式快取（相同的 messages + tools 結構 hit 直接回）
    _tc_key = _tool_cache_key(messages, body.get("tools"))
    if _tc_key in _TOOL_CACHE:
        ts, cached = _TOOL_CACHE[_tc_key]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"[llm_respond] 工具快取命中")
            return cached

    if psi_state:
        block = {"role": "system",
                 "content": _build_toolmode_prompt(psi_state, delta)}
        idx = 0
        while idx < len(messages) and messages[idx].get("role") == "system":
            idx += 1
        messages.insert(idx, block)

    out = {
        "model": _TOOL_MODEL,
        "messages": messages,
        "max_tokens": _TOOL_MAX_TOKENS,
        "temperature": body.get("temperature", 0.7),
        **({"provider": _PROVIDER_PREF} if _PROVIDER_PREF else {}),
    }
    for k in ("tools", "tool_choice", "parallel_tool_calls",
              "response_format", "stop", "top_p"):
        if body.get(k) is not None:
            out[k] = body[k]

    # 重試非 streaming 呼叫（網路抖動時自動重試）
    try:
        resp = None
        last_err = None
        for attempt in range(_RETRY_MAX + 1):
            try:
                req = urllib.request.Request(
                    f"{_LLM_BASE_URL}/chat/completions",
                    data=json.dumps(out).encode(),
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {key}"},
                )
                resp = json.loads(
                    urllib.request.urlopen(req, timeout=_TOOL_TIMEOUT).read())
                break
            except Exception as e:
                last_err = e
                if not _is_retryable(e) or attempt >= _RETRY_MAX:
                    raise
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.info(f"[llm_respond] 工具呼叫重試 {attempt+1}/{_RETRY_MAX} "
                            f"({delay:.0f}s): {e}")
                time.sleep(delay)
        if resp is None:
            raise last_err or RuntimeError("API 呼叫全部失敗")

        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        if not msg.get("content") and not msg.get("tool_calls"):
            logger.warning(f"[llm_respond] 工具模式空回應: {str(resp)[:300]}")
            # 不回 None（會讓 TUI 卡 working），改回降級訊息
            return {"message": {"role": "assistant",
                                "content": "（上游 LLM 回傳了空回應，請重試）"},
                    "finish_reason": "stop", "usage": {}}
        logger.info(f"[llm_respond] ✅ 工具模式回應 ({_TOOL_MODEL}, "
                    f"finish={choice.get('finish_reason')})")
        result = {"message": msg,
                  "finish_reason": choice.get("finish_reason", "stop"),
                  "usage": resp.get("usage") or {}}
        # 寫入快取（僅短回應）
        if len(msg.get("content") or "") < 500:
            _TOOL_CACHE[_tc_key] = (time.time(), result)
            if len(_TOOL_CACHE) > _CACHE_MAX:
                oldest = min(_TOOL_CACHE, key=lambda k: _TOOL_CACHE[k][0])
                del _TOOL_CACHE[oldest]
        return result
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        logger.warning(f"[llm_respond] 工具模式 API {e.code}: {detail}")
        return {"message": {"role": "assistant",
                            "content": f"（上游 API 錯誤: HTTP {e.code}）"},
                "finish_reason": "stop", "usage": {}}
    except Exception as e:
        logger.warning(f"[llm_respond] 工具模式 API 失敗: {e}")
        return {"message": {"role": "assistant",
                            "content": f"（上游 API 呼叫失敗: {e}）"},
                "finish_reason": "stop", "usage": {}}


def respond_tools_stream(body: dict, psi_state: dict = None,
                         delta: dict = None):
    """Streaming 版 respond_tools — 逐 token 轉發上游 SSE（含 thinking token）。

    Yields {"type": "token", "text": ...}    content delta
           {"type": "reasoning", "text": ...} 思考過程
           {"type": "tool_calls", "calls": [...]} 彙整後的工具呼叫
           {"type": "error", "text": ...}     失敗
    """
    key = _get_api_key()
    if not key:
        yield {"type": "error", "text": "無 API key"}
        return

    messages = list(body.get("messages") or [])
    if psi_state:
        block = {"role": "system",
                 "content": _build_toolmode_prompt(psi_state, delta)}
        idx = 0
        while idx < len(messages) and messages[idx].get("role") == "system":
            idx += 1
        messages.insert(idx, block)

    tools = body.get("tools")
    tool_choice = body.get("tool_choice")

    for ev in _call_llm_stream(
            messages, tools=tools,
            model=_TOOL_MODEL,
            timeout=_TOOL_TIMEOUT,
            max_tokens=_TOOL_MAX_TOKENS):
        if ev["type"] == "reasoning":
            yield {"type": "reasoning", "text": ev["text"]}
        elif ev["type"] == "token":
            yield {"type": "token", "text": ev["text"]}
        elif ev["type"] == "tool_calls":
            yield {"type": "tool_calls", "calls": ev["calls"]}
        elif ev["type"] == "error":
            yield {"type": "error", "text": ev["text"]}


# ── 流式 + 工具交錯（chat 主管線用）──
_CHAT_TOOLS = os.environ.get("NEURALIS_CHAT_TOOLS", "on").lower() in ("on", "1", "true")
_CHAT_TOOL_ROUNDS = int(os.environ.get("NEURALIS_CHAT_TOOL_ROUNDS", 3))
_CHAT_TOOL_TIMEOUT = int(os.environ.get("NEURALIS_CHAT_TOOL_EXEC_TIMEOUT", 60))
_STREAM_MAX_TOKENS = int(os.environ.get("NEURALIS_STREAM_MAX_TOKENS", 1500))


def _call_llm_stream(messages: list, tools: list = None, model: str = None,
                     timeout: int = None, max_tokens: int = None):
    """OpenAI-compatible streaming 呼叫（stream=True，SSE 逐塊解析）。yield:
      {"type": "token", "text": ...}        content delta
      {"type": "tool_calls", "calls": [...]} 彙整後的 tool calls（串流結束時）
      {"type": "error", "text": ...}         呼叫失敗
    calls 元素: {"id", "name", "arguments"}（arguments 為完整 JSON 字串）。"""
    key = _get_api_key()
    if not key:
        yield {"type": "error", "text": "無 API key"}
        return

    payload = {
        "model": model or _LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens or _STREAM_MAX_TOKENS,
        "temperature": 0.8,
        "stream": True,
        **({"provider": _PROVIDER_PREF} if _PROVIDER_PREF else {}),
    }
    if tools:
        payload["tools"] = tools

    req = urllib.request.Request(
        f"{_LLM_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    # 重試連線（網路抖動時自動重試）
    resp = None
    last_err = None
    for attempt in range(_RETRY_MAX + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout or max(_LLM_TIMEOUT, 30))
            break
        except Exception as e:
            last_err = e
            if not _is_retryable(e) or attempt >= _RETRY_MAX:
                yield {"type": "error", "text": f"API 連線失敗: {e}"}
                return
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.info(f"[llm_respond] 串流重試 {attempt+1}/{_RETRY_MAX} ({delay:.0f}s): {e}")
            time.sleep(delay)

    calls: dict = {}   # index → {"id","name","arguments"}（OpenAI delta 累加語義）
    saw_token = False
    stray: list = []   # 非 SSE 行（上游回錯誤 body 時不是 data: 開頭）
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                if line and not line.startswith(":"):   # ": keepalive" 註解行忽略
                    stray.append(line)
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                # A2: transient 上游錯誤（504 idle timeout / 過載）且還沒吐 token →
                # break 落到下面的重連重試路（不直接中止回合逼使用者手動「繼續」）
                if not saw_token and _is_transient_upstream(chunk["error"]):
                    stray.append(f"transient-upstream: {str(chunk['error'])[:80]}")
                    break
                log_abort("call_llm_stream.upstream", model=model or _LLM_MODEL,
                          detail=str(chunk["error"])[:500], has_tools=bool(tools))
                yield {"type": "error", "text": f"上游錯誤: {str(chunk['error'])[:200]}"}
                return
            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
            # DeepSeek 思考 token（OpenRouter 送 delta.reasoning，原生送 reasoning_content）
            reasoning = delta.get("reasoning") or delta.get("reasoning_content") or ""
            if reasoning:
                yield {"type": "reasoning", "text": reasoning}
            if delta.get("content"):
                saw_token = True
                yield {"type": "token", "text": delta["content"]}
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", 0),
                                        {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    except Exception as e:
        # A2: transient 中斷（timeout/連線斷）且還沒吐 token → 不 return，落到下面的
        # 空串流重連路自動重試。已吐 token 的不重試（避免重複輸出）。
        if saw_token or not _is_retryable(e):
            log_abort("call_llm_stream.midstream", err=e, model=model or _LLM_MODEL,
                      saw_token=saw_token, has_tools=bool(tools))
            yield {"type": "error", "text": f"串流中斷: {e}"}
            return
        stray.append(f"transient-midstream: {str(e)[:80]}")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if calls:
        yield {"type": "tool_calls", "calls": [calls[i] for i in sorted(calls)]}
    elif not saw_token:
        # 空串流：上游回了空 response（無 token、無 calls）— 重試一次
        for attempt in range(_RETRY_MAX):
            logger.info(f"[llm_respond] 空串流，重試 {attempt+1}/{_RETRY_MAX}")
            time.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
            # 重新嘗試（重新建立連線）
            try:
                req2 = urllib.request.Request(
                    f"{_LLM_BASE_URL}/chat/completions",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {key}"},
                )
                resp2 = urllib.request.urlopen(req2, timeout=timeout or max(_LLM_TIMEOUT, 30))
            except Exception as e:
                detail = f"重試連線失敗: {e}"
                stray.append(detail)
                continue
            # 重新解析串流
            saw_token2 = False
            calls2 = {}
            try:
                for raw2 in resp2:
                    line2 = raw2.decode("utf-8", "replace").strip()
                    if not line2.startswith("data: "):
                        continue
                    d2 = line2[6:]
                    if d2 == "[DONE]":
                        break
                    try:
                        ch2 = json.loads(d2)
                    except json.JSONDecodeError:
                        continue
                    dl2 = (ch2.get("choices") or [{}])[0].get("delta") or {}
                    if dl2.get("reasoning") or dl2.get("reasoning_content"):
                        yield {"type": "reasoning", "text": dl2.get("reasoning") or dl2.get("reasoning_content")}
                    if dl2.get("content"):
                        saw_token2 = True
                        yield {"type": "token", "text": dl2["content"]}
                    for tc2 in dl2.get("tool_calls") or []:
                        s2 = calls2.setdefault(tc2.get("index", 0), {"id": "", "name": "", "arguments": ""})
                        if tc2.get("id"): s2["id"] = tc2["id"]
                        fn2 = tc2.get("function") or {}
                        if fn2.get("name"): s2["name"] = fn2["name"]
                        if fn2.get("arguments"): s2["arguments"] += fn2["arguments"]
            except Exception:
                continue
            if saw_token2 or calls2:
                logger.info(f"[llm_respond] 重試成功")
                if calls2:
                    yield {"type": "tool_calls", "calls": [calls2[i] for i in sorted(calls2)]}
                return
        # 全部重試失敗
        detail = " | ".join(stray)[:200] or "空回應（無 token、無 tool_calls）"
        yield {"type": "error", "text": f"LLM 空串流: {detail}"}


def _use_tool_schema() -> Optional[list]:
    """單一泛用 function：use_tool(tool, prompt)。工具名清單動態取自 ToolExecutor
    （42 工具名塞 enum 太肥 — 名單放參數描述，system prompt 已有技能目錄）。"""
    try:
        from laap.startup import get_tool_executor
        executor = get_tool_executor()
        if executor is None:
            return None
        names = ", ".join(t["name"] for t in executor.list_tools())
    except Exception:
        return None
    return [{
        "type": "function",
        "function": {
            "name": "use_tool",
            "description": "透過 ToolExecutor 執行一個工具/技能，取得真實資料。"
                           "需要查資料、搜尋、讀記憶時用這個，不要憑空編造。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string",
                             "description": f"工具名，可用: {names}"},
                    "prompt": {"type": "string",
                               "description": "給工具的查詢/指令內容"},
                },
                "required": ["tool", "prompt"],
            },
        },
    }]


def respond_stream(user_msg: str, psi_state: dict, history: list = None,
                   memories: list = None, delta: dict = None):
    """交錯串流版 respond()：LLM token 與工具執行過程交錯 yield。
      {"type": "token", "text": ...}        LLM 逐 token
      {"type": "tool_status", "text": ...}  工具過程行（開始/中間輸出/完成）
    未啟用（NEURALIS_LLM_RESPOND=off / 無 state / 無 key）→ 不 yield 任何事件，
    caller 據此降級模板。工具迴圈上限 _CHAT_TOOL_ROUNDS 輪、每輪最多 2 個 call。"""
    if not _LLM_ENABLED or not psi_state:
        return

    system = _build_system_prompt(psi_state, delta=delta, memories=memories)
    messages = [{"role": "system", "content": system}]
    for m in (history or [])[-10:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])[:800]})
    messages.append({"role": "user", "content": user_msg})

    tools = _use_tool_schema() if _CHAT_TOOLS else None
    executor = None
    if tools:
        from laap.startup import get_tool_executor
        executor = get_tool_executor()

    emitted = False
    for rnd in range(_CHAT_TOOL_ROUNDS + 1):
        use_tools = tools if (tools and executor and rnd < _CHAT_TOOL_ROUNDS) else None
        round_text: list = []
        calls = None
        for ev in _call_llm_stream(
                messages, tools=use_tools,
                timeout=_TOOL_TIMEOUT if use_tools else max(_LLM_TIMEOUT, 20)):
            if ev["type"] == "token":
                round_text.append(ev["text"])
                emitted = True
                yield ev
            elif ev["type"] == "reasoning":
                # thinking token（R1 系）原樣轉發 — SSE 層以 delta.reasoning 出
                emitted = True
                yield ev
            elif ev["type"] == "tool_calls":
                calls = ev["calls"]
            elif ev["type"] == "error":
                if emitted:
                    yield {"type": "tool_status", "text": f"（LLM 串流失敗: {ev['text']}）"}
                logger.warning(f"[llm_respond] respond_stream: {ev['text']}")
                return

        if not calls:
            if emitted:
                logger.info(f"[llm_respond] ✅ 串流回應 ({_LLM_MODEL}, {rnd} 工具輪)")
            return

        # 工具輪：assistant(tool_calls) → 逐 call 執行（過程轉發）→ tool 結果 → 下一輪
        for i, c in enumerate(calls):
            if not c["id"]:
                c["id"] = f"call_{rnd}_{i}"
        messages.append({
            "role": "assistant",
            "content": "".join(round_text) or None,
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"],
                                         "arguments": c["arguments"]}}
                           for c in calls],
        })
        for c in calls[:2]:
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            if c["name"] == "use_tool":
                tool_name = str(args.get("tool", "")).strip()
                tool_prompt = str(args.get("prompt", ""))
            else:
                # 模型有時直接把工具名當 function 叫（實測 deepseek 會）— 寬容接受，
                # 省一輪格式錯誤來回（~4s）
                tool_name = c["name"].strip()
                tool_prompt = str(args.get("prompt") or args.get("query")
                                  or args.get("q") or args.get("input") or "")
            result = ""
            if not tool_name:
                result = f"[工具呼叫格式錯誤] function={c['name']}, args={c['arguments'][:120]}"
                yield {"type": "tool_status", "text": f"⚠️ {result}"}
            else:
                emitted = True
                try:
                    for tev in executor.stream(tool_name, tool_prompt,
                                               timeout=_CHAT_TOOL_TIMEOUT):
                        if tev["type"] == "result":
                            result = tev["text"]
                        else:
                            yield {"type": "tool_status", "text": tev["text"][:200]}
                except Exception as e:
                    result = f"[錯誤] {tool_name}: {e}"
                    yield {"type": "tool_status", "text": f"❌ {result}"}
            messages.append({"role": "tool", "tool_call_id": c["id"],
                             "content": (result or "無結果")[:4000]})
        for c in calls[2:]:
            messages.append({"role": "tool", "tool_call_id": c["id"],
                             "content": "[略過] 每輪最多執行 2 個工具呼叫"})


def respond(user_msg: str, psi_state: dict, history: list = None,
            memories: list = None, delta: dict = None) -> Optional[str]:
    """用 LLM 產生 Aris 狀態感知回應（帶對話歷史 + 記憶 + 實測 delta）。

    history: 之前的輪次 [{"role","content"}...]（不含這句 user_msg）。
    回 None = 不取代現有流程（降級到 psi-respond 模板）。
    """
    if not _LLM_ENABLED:
        return None
    if not psi_state:
        return None

    system = _build_system_prompt(psi_state, delta=delta, memories=memories)
    messages = [{"role": "system", "content": system}]
    for m in (history or [])[-10:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])[:800]})
    messages.append({"role": "user", "content": user_msg})

    # 快取檢查：相同對話尾 + 60s 內直接回
    ckey = _cache_key(user_msg, history)
    if ckey in _RESPONSE_CACHE:
        ts, cached = _RESPONSE_CACHE[ckey]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"[llm_respond] 快取命中 ({_LLM_MODEL})")
            return cached

    content = _call_llm(messages)
    if content:
        logger.info(f"[llm_respond] ✅ LLM 回應 ({_LLM_MODEL})")
        # 寫入快取（僅非工具、非 error 的真回應）
        _RESPONSE_CACHE[ckey] = (time.time(), content)
        if len(_RESPONSE_CACHE) > _CACHE_MAX:
            oldest = min(_RESPONSE_CACHE.keys(), key=lambda k: _RESPONSE_CACHE[k][0])
            del _RESPONSE_CACHE[oldest]
    return content


# ── 窄而深管線 ──────────────────────────────────────────────


def _classify_intent(user_msg: str) -> str:
    """Layer 1: 本地意圖分類。"""
    msg = user_msg.lower().strip()
    if any(w in msg for w in ["?", "什麼", "怎麼", "為何", "why", "how", "what"]):
        return "詢問"
    if any(w in msg for w in ["幫我", "做", "寫", "建立", "改", "create", "build", "fix"]):
        return "任務"
    if any(w in msg for w in ["記", "記得", "上次", "之前", "回憶", "remember"]):
        return "回憶"
    return "一般"


def _extract_state_hint(state: dict) -> str:
    """從 PSI 狀態提取一行提示。"""
    v = state.get("emotion", {}).get("valence", 0)
    return "心情不錯" if v > 0.3 else ("心情低落" if v < -0.3 else "心情平穩")


def _build_turn_prompt(intent: str = None, memories: list = None,
                       state_hint: str = None, user_msg: str = None) -> str:
    """Layer 2: 精準 prompt（只有當下需要的資訊）。"""
    parts = []
    if intent:
        parts.append(f"意圖：{intent}")
    if memories:
        parts.append(f"相關記憶：{'；'.join(memories[:2])}")
    if state_hint:
        parts.append(f"狀態：{state_hint}")
    parts.append(f"使用者：{user_msg or ''}")
    parts.append("")
    parts.append("回應：")
    return "\n".join(parts)


def _detect_attention_input(user_msg: str) -> str:
    """偵測使用者是否在回應「下一步要做什麼」的提示。"""
    msg = user_msg.lower().strip()
    if any(w in msg for w in ["下一步", "等等", "接下來", "待會", "明天", "next"]):
        return user_msg[:200]
    return ""


def _save_attention_line(text: str) -> bool:
    """儲存注意力線索到 aris-memory。"""
    import urllib.request, json
    payload = json.dumps({"attention": text, "ts": time.time()}).encode()
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11551/attention",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def respond_nd(user_msg: str, psi_state: dict, history: list = None,
               memories: list = None) -> Optional[str]:
    """窄而深三層管線。"""
    if not _LLM_ENABLED or not psi_state:
        return None
    # Layer 1: 本地處理
    intent = _classify_intent(user_msg)
    state_hint = _extract_state_hint(psi_state)

    # 1a: 偵測注意力輸入（下一步要做什麼）
    attention = _detect_attention_input(user_msg)
    if attention:
        ok = _save_attention_line(attention)
        logger.info(f"[llm_respond] {'✅' if ok else '❌'} 注意力線索: {attention[:60]}")

    matched = []
    if memories:
        for m in memories[:3]:
            if any(w in m.lower() for w in user_msg.split()):
                matched.append(m)
        if not matched:
            matched = memories[:2]
    # Layer 2: 精準 prompt + LLM
    tp = _build_turn_prompt(intent=intent, memories=matched,
                            state_hint=state_hint, user_msg=user_msg)
    msgs = [{"role": "system", "content": _build_static_identity()},
            {"role": "user", "content": tp}]
    for m in (history or [])[-4:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": str(m["content"])[:400]})
    content = _call_llm(msgs)
    if content:
        logger.info(f"[llm_respond] ✅ ND {_LLM_MODEL} | 意圖={intent} | prompt={len(tp)}ch")
    return content