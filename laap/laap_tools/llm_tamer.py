"""
Stub: LLMTamer — LLM 輸出馴服器
被 aris_cognitive_bridge.py 透過 laap.laap_tools.llm_tamer 匯入
"""
import logging
from typing import Any, Dict

logger = logging.getLogger("laap_tools.llm_tamer")


class LLMTamer:
    """LLM 輸出馴服器 — 限制輸出範圍與格式"""

    def __init__(self):
        logger.info("[LLMTamer] stub 初始化")

    def tame(self, prompt: str, constraints: Dict[str, Any]) -> str:
        return prompt