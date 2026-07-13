"""
Stub: self_model adapter — 狀態轉換器
被 aris_cognitive_bridge 使用
"""
import logging
from typing import Any, Dict

from laap.agi.cognitive_bus import CognitiveStateSnapshot
from laap.laap_tools.self_model.model import SelfStateOutput

logger = logging.getLogger("laap_tools.self_model.adapter")


def bridge_state_to_snapshot(bridge_state: Dict[str, Any]) -> CognitiveStateSnapshot:
    """橋接狀態 → 認知快照"""
    logger.debug("[adapter] bridge_state_to_snapshot stub")
    return CognitiveStateSnapshot()


def self_state_output_to_snapshot(output: SelfStateOutput, base: CognitiveStateSnapshot) -> CognitiveStateSnapshot:
    """自我模型輸出 → 認知快照（合併）"""
    logger.debug("[adapter] self_state_output_to_snapshot stub")
    return base