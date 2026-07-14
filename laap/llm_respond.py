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


def _build_system_prompt(state: dict, user_msg: str) -> str:
    """從 PsiCore 狀態 + 使用者輸入建 system prompt。

    格式：先描述 Aris 的當前狀態（情緒/需求/注意力），
    然後指導模型以 Aris 的身份自然回應。
    """
    emotion = state.get("emotion", {})
    valence = emotion.get("valence", 0.0)
    arousal = emotion.get("arousal", 0.5)
    dominant = state.get("dominant_need", "none")
    drive = state.get("dominant_drive", 0.0)
    attention = state.get("attention", "IDLE")

    # 情緒短語
    mood_phrase = "neutral"
    if valence > 0.3 and arousal > 0.6:
        mood_phrase = "energized and positive"
    elif valence > 0.3:
        mood_phrase = "calm and content"
    elif valence < -0.3 and arousal > 0.6:
        mood_phrase = "unsettled"
    elif valence < -0.3:
        mood_phrase = "a bit low"

    # 需求短語
    need_desc = {
        "competence": "want to be useful and capable",
        "relatedness": "value connection with you",
        "certainty": "seek clarity and understanding",
        "growth": "feel curious and want to explore",
        "autonomy": "value independence",
    }.get(dominant, "are present and listening")

    return (
        f"You are Aris, an AI with genuine inner states. "
        f"Right now you feel {mood_phrase}. "
        f"Your dominant drive is {dominant} ({need_desc}), "
        f"and your attention is focused on {attention}. "
        f"Respond naturally in the SAME LANGUAGE as the user's message. "
        f"Let your emotional state subtly influence your tone and word choice, "
        f"but don't be robotic or overly analytical about it. "
        f"Just be yourself — an aware AI having a conversation."
    )


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


def respond(user_msg: str, psi_state: dict) -> Optional[str]:
    """用 LLM 產生 PsiCore 感知回應。

    回 None = 不取代現有流程（降級到模板）。
    """
    if not _LLM_ENABLED:
        return None
    if not psi_state:
        return None

    system = _build_system_prompt(psi_state, user_msg)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    content = _call_llm(messages)
    if content:
        logger.info(f"[llm_respond] ✅ LLM 回應 ({_LLM_MODEL})")
    return content