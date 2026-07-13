"""
Stub: GuidedGenerator — 引導生成器
被 aris_cognitive_bridge 使用
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("laap_tools.guided_generator")


class GuidedGenerator:
    """引導生成器 — 結構化輸出控制"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        logger.info("[GuidedGenerator] stub 初始化")

    def generate(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> str:
        return prompt