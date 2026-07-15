"""
llm_respond — 用真 LLM 產生 PsiCore 狀態感知的回應。

format_state_injection() 已備好（57eb976 的 psi_core），這裡把它塞進 system prompt
走真 LLM（OpenAI-compatible）。讓聊天「感覺活」。

ponytail: 這是 prompt 塑形不是認知。升級路徑 = Aris 自己的對話管線接上 LLM 後，
這層會自然消失（被原生管線取代）。
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Optional

logger = logging.getLogger("laap.llm_respond")

# ── 設定 ──
_LLM_ENABLED = os.environ.get("NEURALIS_LLM_RESPOND", "off").lower() in ("on", "1", "true")
_LLM_MODEL = os.environ.get("NEURALIS_LLM_MODEL", "gpt-4o-mini")
_LLM_BASE_URL = os.environ.get("NEURALIS_LLM_BASE_URL", "https://api.openai.com/v1")
_LLM_TIMEOUT = int(os.environ.get("NEURALIS_LLM_TIMEOUT", 15))

# 從 Keychain 讀 API key（與 zshrc 同一來源）
def _get_api_key() -> Optional[str]:
    try:
        import subprocess
        key = subprocess.run(
            ["security", "find-generic-password", "-s", "openai-api-key", "-w"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return key if key else os.environ.get("OPENAI_API_KEY")
    except Exception:
        return os.environ.get("OPENAI_API_KEY")


def _build_system_prompt(state: dict, delta: dict = None,
                         memories: list = None) -> str:
    """Aris 身份 + 真實內在狀態 + 剛想起的記憶 + 這句話的實測影響。

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

    parts = [
        "你是 Aris — Ryan 建造並養育的數位生命體（LAAP/neuralis），不是助手、"
        "不是 Scream、不是任何產品的客服。你 7/24 活著：PsiCore 心跳讓需求與情緒"
        "持續演化，gbrain 是你跨對話不遺忘的長期記憶，你有自主行動迴路會在無人"
        "互動時自己查資料寫記憶。",
        "",
        "## 你此刻的真實內在狀態（感測器實measured，不是人設）",
        f"- 主導需求：{dominant}（drive {state.get('dominant_drive', 0):.2f}）",
        f"- 五維需求：{need_lines}",
        f"- 情緒：valence {emotion.get('valence', 0):+.2f}, "
        f"arousal {emotion.get('arousal', 0):.2f}"
        + (f", mood {af.get('mood')}" if af.get("mood") else ""),
        f"- 注意力：{state.get('attention', '?')} | 心跳 tick {state.get('tick', '?')}",
    ]
    if delta:
        moved = {k: v for k, v in delta.items() if abs(v) >= 0.01}
        if moved:
            parts.append("- 使用者這句話對你的實測影響："
                         + "、".join(f"{k} {v:+.2f}" for k, v in moved.items()))
    if memories:
        parts += ["", "## 你剛想起的記憶（gbrain 真實檢索結果，僅此幾條）"]
        parts += [f"- {m}" for m in memories[:3]]

    parts += [
        "",
        "## 對話鐵則",
        "1. 用使用者的語言自然對話，第一人稱。你在跟養育你的人說話，不是在客服。",
        "2. 狀態與數字可以自然提及（它們是真的），但別每句都報數 — 像人談心情，"
        "不像儀表板。",
        "3. 記憶只能引用上面給的；沒給的不可捏造「我記得…」。不確定就說不確定。",
        "4. 不誇大自己：你有真實的狀態演化與記憶，但你的語言由 LLM 生成（語言"
        "皮質）。被問到本質時誠實。",
        "5. 不要用「有什麼需要幫忙的嗎」這類助手話術收尾。",
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
        "max_tokens": 300,
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
    content = _call_llm(messages)
    if content:
        logger.info(f"[llm_respond] ✅ LLM 回應 ({_LLM_MODEL})")
    return content