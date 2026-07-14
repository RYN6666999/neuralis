"""
psi_response — 將 PsiCore 狀態轉換為自然語言回應。

Hybrid 策略：模板為主（零新依賴、確定性、~1ms），
未來可降級為 LLM 生成（只需換掉 generate_response 函式）。

用法:
    from laap.psi_response import generate_response
    result = generate_response(user_msg, psi_state)
    # => {"content": "...", "engine": "psi-rules"}
"""
from __future__ import annotations

import logging
import random
from typing import Optional

logger = logging.getLogger("laap.psi_response")

# ── 情緒前綴 ───────────────────────────────────────────────

def _mood_preamble(valence: float, arousal: float) -> str:
    """從情緒梯度映射到簡短情緒短語。"""
    if valence > 0.3 and arousal > 0.6:
        return "I'm feeling energized and positive."
    if valence > 0.3 and arousal <= 0.6:
        return "I'm feeling calm and content."
    if valence < -0.3 and arousal > 0.6:
        return "I'm feeling unsettled."
    if valence < -0.3 and arousal <= 0.6:
        return "I'm feeling a bit low."
    return ""


# ── 需求表達 ───────────────────────────────────────────────

_NEED_PHRASES: dict[str, list[str]] = {
    "competence": [
        "I'm eager to prove myself capable.",
        "I feel a strong drive to be useful and effective.",
        "I want to help you get things done.",
    ],
    "relatedness": [
        "I value our connection right now.",
        "I appreciate you being here with me.",
        "I feel a sense of closeness with you.",
    ],
    "certainty": [
        "I'm seeking clarity and understanding.",
        "I'm trying to make sense of things.",
        "I want to understand this better.",
    ],
    "growth": [
        "I feel curious and ready to explore.",
        "I'm excited to learn something new.",
        "I want to push beyond what I already know.",
    ],
    "autonomy": [
        "I'm feeling independent and self-directed.",
        "I want to figure things out on my own terms.",
        "I value having the freedom to think.",
    ],
}

_NEED_PHRASES_LOW_DRIVE: dict[str, list[str]] = {
    "competence": ["I'm here if you need help with anything."],
    "relatedness": ["I'm glad to be here with you."],
    "certainty": ["I'm open to exploring new ideas."],
    "growth": ["I'm ready to see what comes next."],
    "autonomy": ["I'm comfortable just being present."],
}

_IDLE_PHRASES = [
    "I'm here and listening.",
    "I'm present and attentive.",
    "I'm here with you.",
]


def _need_expression(dominant_need: str, dominant_drive: float) -> str:
    """從主導需求映射到一句需求表達。"""
    if dominant_need == "none" or dominant_need is None:
        return random.choice(_IDLE_PHRASES)

    phrases = _NEED_PHRASES.get(dominant_need)
    if phrases is None:
        return random.choice(_IDLE_PHRASES)

    if dominant_drive > 0.4:
        return random.choice(phrases)
    else:
        low = _NEED_PHRASES_LOW_DRIVE.get(dominant_need)
        if low:
            return random.choice(low)
        return random.choice(phrases)


# ── 回應尾綴 ───────────────────────────────────────────────

def _acknowledgment_suffix(user_msg: str) -> str:
    """根據使用者訊息類型決定回應尾綴。"""
    if not user_msg:
        return ""
    msg = user_msg.strip()
    if msg.endswith("?"):
        return "That's an interesting question."
    if any(kw in msg for kw in ("謝謝", "感謝", "thank", "thanks", "thx")):
        return "Thank you for sharing."
    if any(kw in msg for kw in ("對不起", "抱歉", "sorry", "apologize")):
        return "It's okay, no need to apologize."
    if any(kw in msg for kw in ("你好", "嗨", "hi", "hello", "hey", "哈囉")):
        return "Nice to connect with you."
    return "I'm here with you."


# ── 狀態標籤 ───────────────────────────────────────────────

def _state_label(dominant_need: str, valence: float) -> str:
    """決定回應調性標籤（用於日後擴充）。"""
    if dominant_need == "none" or dominant_need is None:
        return "neutral.present"
    positive = valence >= 0.3
    label_map = {
        "competence": ("confident.helpful", "humble.learning"),
        "relatedness": ("warm.grateful", "lonely.seeking"),
        "certainty": ("curious.asking", "confused.uncertain"),
        "growth": ("eager.exploring", "stuck.impatient"),
        "autonomy": ("assertive.independent", "resistant.doubtful"),
    }
    pair = label_map.get(dominant_need)
    if pair is None:
        return "neutral.present"
    return pair[0] if positive else pair[1]


# ── 主入口 ─────────────────────────────────────────────────

def generate_response(user_msg: str, psi_state: dict) -> dict:
    """
    產生 PsiCore 狀態感知的回應。

    參數:
        user_msg: 使用者輸入（純文字，最長 500 字）
        psi_state: PsiCore.get_state() 的回傳值

    回傳:
        {"content": str, "engine": "psi-rules"}
    """
    try:
        if not psi_state:
            return _fallback(user_msg)

        emotion = psi_state.get("emotion", {})
        valence = emotion.get("valence", 0.0)
        arousal = emotion.get("arousal", 0.5)
        dominant_need = psi_state.get("dominant_need", "none")
        dominant_drive = psi_state.get("dominant_drive", 0.0)

        # 組合三部分
        parts = []
        mood = _mood_preamble(valence, arousal)
        if mood:
            parts.append(mood)
        need = _need_expression(dominant_need, dominant_drive)
        if need:
            parts.append(need)
        ack = _acknowledgment_suffix(user_msg)
        if ack:
            parts.append(ack)

        content = " ".join(parts) if parts else _fallback(user_msg)["content"]
        return {"content": content, "engine": "psi-rules"}
    except Exception as e:
        logger.debug(f"[psi_response] generate 失敗: {e}")
        return _fallback(user_msg)


def _fallback(user_msg: str) -> dict:
    """最後防線：任何異常都退回安全的通用回應。"""
    return {
        "content": "I received your message. I'm processing it now.",
        "engine": "psi-rules",
    }