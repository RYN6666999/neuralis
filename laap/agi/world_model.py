"""
UnifiedWorldModel — dict-based 世界模型 (純 Python)

從 stub 升級為可運行的語意圖引擎。
管理實體、關係、屬性，支援關鍵詞查詢。
"""
import logging
import re
from collections import defaultdict
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set

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

    def __init__(self, capacity: int = 1024, **kwargs):
        self.capacity = capacity
        self._entities: Dict[str, dict] = {}           # name → {type, properties, created}
        self._relations: List[dict] = []                # [{source, target, type, weight}]
        self._tags: Dict[str, Set[str]] = defaultdict(set)  # tag → {entity_names}
        logger.info(f"[WorldModel] dict-based 初始化, capacity={capacity}")

    def add_entity(self, name: str, entity_type: EntityType = EntityType.UNKNOWN,
                   properties: Optional[dict] = None) -> str:
        """新增或更新實體。"""
        key = name.lower().strip()
        if key not in self._entities:
            self._entities[key] = {
                "name": name, "type": entity_type.name,
                "properties": properties or {},
            }
        elif properties:
            self._entities[key]["properties"].update(properties)

        if properties:
            for tag in properties.get("tags", []):
                self._tags[str(tag)].add(key)
        return name

    def add_relation(self, source: str, target: str,
                     rel_type: RelationType = RelationType.UNKNOWN,
                     weight: float = 1.0) -> None:
        """新增實體之間的關係。"""
        self._relations.append({
            "source": source.lower().strip(),
            "target": target.lower().strip(),
            "type": rel_type.name,
            "weight": weight,
        })

    def query(self, query: str, top_k: int = 5) -> List[dict]:
        """查詢匹配的實體與關係。關鍵詞重疊模糊匹配。"""
        q = query.lower().strip()
        q_words = set(q.split())
        results = []

        # 實體匹配
        for key, info in self._entities.items():
            score = 0.0
            if q == key:
                score = 1.0
            elif q in key:
                score = 0.8
            else:
                e_words = set(key.split())
                overlap = len(q_words & e_words)
                if overlap > 0:
                    score = overlap / max(len(q_words), len(e_words)) * 0.6
            if score > 0:
                results.append({"type": "entity", "name": info["name"],
                                "entity_type": info["type"], "properties": info["properties"],
                                "score": round(score, 3)})

        # 關係匹配（透過 source/target 名稱）
        for rel in self._relations:
            if q in rel["source"] or q in rel["target"]:
                results.append({"type": "relation", "source": rel["source"],
                                "target": rel["target"], "rel_type": rel["type"],
                                "weight": rel["weight"], "score": 0.5})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def get_entity(self, name: str) -> Optional[dict]:
        """取得單一實體。"""
        return self._entities.get(name.lower().strip())

    def get_relations(self, name: str) -> List[dict]:
        """取得與某實體相關的所有關係。"""
        key = name.lower().strip()
        return [r for r in self._relations if r["source"] == key or r["target"] == key]

    def __len__(self) -> int:
        return len(self._entities)