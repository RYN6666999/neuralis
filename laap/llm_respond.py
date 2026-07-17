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

# ── 設定 ──
_LLM_ENABLED = os.environ.get("NEURALIS_LLM_RESPOND", "off").lower() in ("on", "1", "true")
_LLM_MODEL = os.environ.get("NEURALIS_LLM_MODEL", "deepseek-v4-flash")
_LLM_BASE_URL = os.environ.get("NEURALIS_LLM_BASE_URL", "https://openrouter.ai/api/v1")
_LLM_TIMEOUT = int(os.environ.get("NEURALIS_LLM_TIMEOUT", 15))

# ── API Key 快取（省每次 subprocess call 40-100ms）──
_API_KEY_CACHE: Optional[str] = None
_API_KEY_CACHE_TS: float = 0.0
_API_KEY_TTL = 300  # 5 分鐘

# ── 工具模式設定（Scream TUI agent 迴圈）──
# 工具迴圈的請求比純聊天肥得多（harness system prompt + tools schema + 檔案內容），
# timeout / max_tokens 都要另一個量級。
_TOOL_MODEL = os.environ.get("NEURALIS_TOOL_MODEL", _LLM_MODEL)
_TOOL_TIMEOUT = int(os.environ.get("NEURALIS_TOOL_TIMEOUT", 120))
_TOOL_MAX_TOKENS = int(os.environ.get("NEURALIS_TOOL_MAX_TOKENS", 8192))

# 從 Keychain 讀 API key（與 zshrc 同一來源）
# 依序嘗試：NEURALIS_LLM_API_KEY env → openrouter-api-key keychain → openai-api-key keychain → OPENAI_API_KEY env
def _get_api_key() -> Optional[str]:
    """回 API key，5 分鐘快取（省每次 subprocess 40-100ms）。"""
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


def _build_system_prompt(state: dict, delta: dict = None,
                         memories: list = None) -> str:
    """Aris 身份 + 真實內在狀態 + 真實能力 + 剛想起的記憶 + 這句話的實測影響。

    誠實鐵則寫進 prompt：狀態數字是量出來的不是設定的；記憶只能引用給定的，
    不可捏造。LLM 在這裡是語言皮質（I/O），不是認知 — 認知是 psi/agency/gbrain。
    """
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
        parts += ["", "## 你剛想起的記憶（gbrain 真實檢索結果，僅此幾條）"]
        parts += [f"- {m}" for m in memories[:3]]

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

    body = json.dumps({
        "model": _LLM_MODEL,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.8,
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
        resp = json.loads(urllib.request.urlopen(req, timeout=_LLM_TIMEOUT).read())
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
    }
    for k in ("tools", "tool_choice", "parallel_tool_calls",
              "response_format", "stop", "top_p"):
        if body.get(k) is not None:
            out[k] = body[k]

    req = urllib.request.Request(
        f"{_LLM_BASE_URL}/chat/completions",
        data=json.dumps(out).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=_TOOL_TIMEOUT).read())
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        if not msg.get("content") and not msg.get("tool_calls"):
            logger.warning(f"[llm_respond] 工具模式空回應: {str(resp)[:300]}")
            return None
        logger.info(f"[llm_respond] ✅ 工具模式回應 ({_TOOL_MODEL}, "
                    f"finish={choice.get('finish_reason')})")
        result = {"message": msg,
                  "finish_reason": choice.get("finish_reason", "stop"),
                  "usage": resp.get("usage") or {}}
        # 寫入快取（僅短回應）
        content_len = len(msg.get("content") or "")
        if content_len < 500:
            _TOOL_CACHE[_tc_key] = (time.time(), result)
            if len(_TOOL_CACHE) > _CACHE_MAX:
                oldest = min(_TOOL_CACHE, key=lambda k: _TOOL_CACHE[k][0])
                del _TOOL_CACHE[oldest]
        return result
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            detail = ""
        logger.warning(f"[llm_respond] 工具模式 API {e.code}: {detail}")
        return None
    except Exception as e:
        logger.warning(f"[llm_respond] 工具模式 API 失敗: {e}")
        return None


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
    }
    if tools:
        payload["tools"] = tools

    req = urllib.request.Request(
        f"{_LLM_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout or max(_LLM_TIMEOUT, 30))
    except Exception as e:
        yield {"type": "error", "text": f"API 連線失敗: {e}"}
        return

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
        yield {"type": "error", "text": f"串流中斷: {e}"}
        return
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if calls:
        yield {"type": "tool_calls", "calls": [calls[i] for i in sorted(calls)]}
    elif not saw_token:
        # 整條 stream 零 token 零 call — 上游回了非 SSE 錯誤 body 或空 choices，
        # 靜默吞掉 = caller 無聲斷尾。給出可回溯的錯誤。
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