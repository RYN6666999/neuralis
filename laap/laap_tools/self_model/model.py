"""
Stub: SelfModelNN / SelfModelConfig / SelfStateOutput
被 aris_cognitive_bridge 使用
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("laap_tools.self_model.model")


@dataclass
class SelfModelConfig:
    """自我模型配置"""
    hidden_dim: int = 512
    num_layers: int = 4
    dropout: float = 0.1


@dataclass
class SelfStateOutput:
    """自我狀態輸出"""
    coherence: float = 0.5
    identity_strength: float = 0.5
    narrative: str = ""
    anomaly_score: float = 0.0


class SelfModelNN:
    """自我模型神經網路 — stub"""

    def __init__(self, config: SelfModelConfig):
        self.config = config
        logger.info(f"[SelfModelNN] stub 初始化, config={config}")

    def forward(self, state: Dict[str, Any]) -> SelfStateOutput:
        return SelfStateOutput()