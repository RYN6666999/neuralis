"""
CognitiveBus — LAAP AGI 事件總線
===================================
所有認知模組的唯一通訊中樞：事件發佈/訂閱、狀態快照、模組心跳。

這不是 stub。這是 neuralis 提供給 laap-AGI 的真實總線實作。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("laap.agi.cognitive_bus")


# ── 枚舉 ─────────────────────────────────────────────


class CognitiveEventType(Enum):
    CONSCIOUS_FRAME = auto()
    NEED_CHANGED = auto()
    EMOTION_CHANGED = auto()
    ATTENTION_SHIFTED = auto()


class EmotionalValence(Enum):
    POSITIVE_HIGH = auto()
    POSITIVE_MILD = auto()
    NEUTRAL = auto()
    NEGATIVE_MILD = auto()
    NEGATIVE_HIGH = auto()
    CURIOUS = auto()
    CONFUSED = auto()


class AttentionFocus(Enum):
    USER = auto()
    TASK = auto()
    SELF = auto()
    ENVIRONMENT = auto()
    MEMORY = auto()
    PLANNING = auto()
    LEARNING = auto()
    IDLE = auto()


# ── 資料類別 ──────────────────────────────────────────


@dataclass
class NeedState:
    """SDT 五維需求狀態"""
    competence: float = 0.5
    autonomy: float = 0.5
    relatedness: float = 0.5
    certainty: float = 0.5
    growth: float = 0.5

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> "NeedState":
        return cls(**{k: d.get(k, 0.5) for k in cls.__dataclass_fields__})


@dataclass
class EmotionState:
    """情感狀態：Valence-Arousal-Dominance 三維"""
    valence: EmotionalValence = EmotionalValence.NEUTRAL
    arousal: float = 0.5
    dominance: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valence": self.valence.name,
            "arousal": self.arousal,
            "dominance": self.dominance,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EmotionState":
        valence = EmotionalValence[d.get("valence", "NEUTRAL")]
        return cls(valence=valence, arousal=d.get("arousal", 0.5), dominance=d.get("dominance", 0.5))


@dataclass
class AttentionState:
    """注意力焦點 + 強度"""
    focus: AttentionFocus = AttentionFocus.IDLE
    intensity: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {"focus": self.focus.name, "intensity": self.intensity}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AttentionState":
        focus = AttentionFocus[d.get("focus", "IDLE")]
        return cls(focus=focus, intensity=d.get("intensity", 0.5))


@dataclass
class PredictionError:
    """預測誤差 — 驅動好奇心的核心信號"""
    total: float = 0.0
    sensory: float = 0.0
    cognitive: float = 0.0
    social: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> "PredictionError":
        return cls(**{k: d.get(k, 0.0) for k in cls.__dataclass_fields__})


@dataclass
class CognitiveStateSnapshot:
    """認知狀態的全域快照 — 時間點拷貝"""
    timestamp: float = 0.0
    needs: NeedState = field(default_factory=NeedState)
    emotion: EmotionState = field(default_factory=EmotionState)
    attention: AttentionState = field(default_factory=AttentionState)
    self_presence: float = 0.5
    curiosity: float = 0.5
    prediction_error: PredictionError = field(default_factory=PredictionError)
    active_modules: List[str] = field(default_factory=list)
    narrative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "needs": self.needs.to_dict(),
            "emotion": self.emotion.to_dict(),
            "attention": self.attention.to_dict(),
            "self_presence": self.self_presence,
            "curiosity": self.curiosity,
            "prediction_error": self.prediction_error.to_dict(),
            "active_modules": list(self.active_modules),
            "narrative": self.narrative,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveStateSnapshot":
        return cls(
            timestamp=d.get("timestamp", time.time()),
            needs=NeedState.from_dict(d.get("needs", {})),
            emotion=EmotionState.from_dict(d.get("emotion", {})),
            attention=AttentionState.from_dict(d.get("attention", {})),
            self_presence=d.get("self_presence", 0.5),
            curiosity=d.get("curiosity", 0.5),
            prediction_error=PredictionError.from_dict(d.get("prediction_error", {})),
            active_modules=list(d.get("active_modules", [])),
            narrative=d.get("narrative", ""),
        )


# ── 事件總線 ──────────────────────────────────────────


class CognitiveBus:
    """認知事件總線 — 模組之間唯一的通訊通道。

    特性：
    - publish/subscribe 模式
    - 線程安全（RLock）
    - 內建狀態（needs / emotion / attention）
    - 模組心跳與存活追蹤
    - 自動快照生成
    """

    def __init__(self, agent_name: str = "Aris"):
        self.agent_name = agent_name
        self._lock = threading.RLock()
        self._modules: Dict[str, dict] = {}            # name → {version, capabilities, last_heartbeat}
        self._subscribers: Dict[CognitiveEventType, List[tuple[str, Callable]]] = {
            et: [] for et in CognitiveEventType
        }

        # 當前認知狀態（可被外部模組直接讀寫）
        self.needs = NeedState()
        self.emotion = EmotionState()
        self.attention = AttentionState()
        self.self_presence = 0.5
        self.curiosity = 0.5
        self.prediction_error = PredictionError()
        self.active_modules: List[str] = []
        self.narrative = ""

        logger.info(f"[CognitiveBus] 初始化 — agent={agent_name}")

    # ── 模組管理 ──

    def register_module(self, name: str, version: str, capabilities: list) -> None:
        """註冊一個認知模組到總線。"""
        with self._lock:
            self._modules[name] = {
                "version": version,
                "capabilities": list(capabilities),
                "last_heartbeat": time.time(),
            }
            if name not in self.active_modules:
                self.active_modules.append(name)
            logger.debug(f"[CognitiveBus] 模組註冊: {name} v{version} — {capabilities}")

    def module_heartbeat(self, module_name: str) -> None:
        """模組心跳更新。"""
        with self._lock:
            if module_name in self._modules:
                self._modules[module_name]["last_heartbeat"] = time.time()

    def get_module_info(self, module_name: str) -> Optional[dict]:
        return self._modules.get(module_name)

    def get_alive_modules(self, stale_threshold: float = 10.0) -> List[str]:
        """回傳在 stale_threshold 秒內有 heartbeat 的模組列表。"""
        now = time.time()
        alive = []
        with self._lock:
            for name, info in self._modules.items():
                if now - info["last_heartbeat"] < stale_threshold:
                    alive.append(name)
        return alive

    # ── 事件發佈/訂閱 ──

    def subscribe(self, module_name: str, event_type: CognitiveEventType, callback: Callable) -> None:
        """訂閱某類型事件。callback 簽名: callback(source: str, data: dict)"""
        with self._lock:
            self._subscribers[event_type].append((module_name, callback))
            logger.debug(f"[CognitiveBus] {module_name} 訂閱 {event_type.name}")

    def publish(self, event_type: CognitiveEventType, source: str, data: Any) -> None:
        """發布事件給所有訂閱者。"""
        callbacks = []
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
        for module_name, cb in callbacks:
            try:
                cb(source, data)
            except Exception:
                logger.exception(f"[CognitiveBus] {module_name} 處理 {event_type.name} 時異常")

    # ── 快照 ──

    def take_snapshot(self) -> CognitiveStateSnapshot:
        """從當即狀態建立快照。"""
        with self._lock:
            return CognitiveStateSnapshot(
                timestamp=time.time(),
                needs=self.needs,
                emotion=self.emotion,
                attention=self.attention,
                self_presence=self.self_presence,
                curiosity=self.curiosity,
                prediction_error=self.prediction_error,
                active_modules=list(self.active_modules),
                narrative=self.narrative,
            )

    def apply_snapshot(self, snapshot: CognitiveStateSnapshot) -> None:
        """用快照覆蓋當前狀態（psi_core 驅動）。"""
        with self._lock:
            self.needs = snapshot.needs
            self.emotion = snapshot.emotion
            self.attention = snapshot.attention
            self.self_presence = snapshot.self_presence
            self.curiosity = snapshot.curiosity
            self.prediction_error = snapshot.prediction_error
            self.active_modules = list(snapshot.active_modules)
            self.narrative = snapshot.narrative

    # ── 生命週期掛鉤 ──

    def before_turn(self) -> None:
        """每輪對話前調用（供 psi_core_bridge publish_psi_state 使用）。"""
        pass

    def __repr__(self) -> str:
        return f"<CognitiveBus agent={self.agent_name} modules={len(self._modules)}>"
