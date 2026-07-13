"""
Stub: UnifiedWorldModel — 統一世界模型
laap-AGI 的認知模組透過 try/except import 使用。
實際實作待 neuralis 後續疊代。
"""
import logging
from enum import Enum, auto
from typing import Any, Dict, List, Optional

logger = logging.getLogger("laap.agi.world_model")


class EntityType(Enum):
    UNKNOWN = auto()
    PERSON = auto()
    OBJECT = auto()
    CONCEPT = auto()
    LOCATION = auto()
    EVENT = auto()


class RelationType(Enum):
    UNKNOWN = auto()
    CAUSES = auto()
    CONTAINS = auto()
    DEPENDS_ON = auto()
    SIMILAR_TO = auto()
    OPPOSITE_TO = auto()


class UnifiedWorldModel:
    """世界模型 — 追蹤實體與關係的動態語意圖"""

    def __init__(self, capacity: int = 1024):
        self.capacity = capacity
        self._entities: Dict[str, dict] = {}
        self._relations: List[dict] = []
        logger.info(f"[WorldModel] stub 初始化, capacity={capacity}")

    def add_entity(self, name: str, entity_type: EntityType = EntityType.UNKNOWN, properties: Optional[dict] = None) -> str:
        return name

    def add_relation(self, source: str, target: str, rel_type: RelationType = RelationType.UNKNOWN, weight: float = 1.0) -> None:
        pass

    def query(self, query: str, top_k: int = 5) -> List[dict]:
        return []

    def __len__(self) -> int:
        return len(self._entities)