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


def snapshot_to_self_state_output(snapshot: CognitiveStateSnapshot) -> SelfStateOutput:
    """認知快照 → 自我模型輸出。

    作者在 aris_cognitive_bridge.py 把三個 adapter import 綁在同一個 try，
    缺這個函式會讓整個 three-paths（tamer/generator/self_model）靜默停用。
    最小可用：從 snapshot 取得的欄位映射到 SelfStateOutput，取不到就用預設。
    """
    logger.debug("[adapter] snapshot_to_self_state_output")
    get = lambda k, d: getattr(snapshot, k, d)
    return SelfStateOutput(
        coherence=float(get("coherence", 0.5)),
        identity_strength=float(get("identity_strength", 0.5)),
        narrative=str(get("narrative", "")),
        anomaly_score=float(get("anomaly_score", 0.0)),
    )