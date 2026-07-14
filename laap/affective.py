"""
affective — 5 維情緒引擎（PAD + Social + Stress），採自作者開源版。

Adapted from lorryjovens-hub/laap-AGI `laap/agi/affective_engine.py`
(Apache License 2.0, by Lorry)。保留原數學：維度耦合矩陣、損失趨避非線性
(×1.5)、1/f 粉紅噪聲、32 事件刺激表、認知偏差公式。neuralis 端改動：
  - threading.Lock（心跳執行緒 update + agency/chatflow 執行緒 post_event）
  - 事件走佇列，統一在 update() 套用（單寫者，不搶狀態）
  - 與既有 EmotionGradient 並存不取代（overlay 原則：舊消費者不動，
    新消費者接 compute_cognitive_bias 的真參數輸出）

作者原版把 cognitive_bias 塞進 kernel dict 沒人消費；這裡的偏差接真迴路
（agency 探索率/角度溫度），這是移植的全部意義 — 功能性，不是裝飾。
"""
from __future__ import annotations

import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np


class EmotionDimension(Enum):
    PLEASURE = 0
    AROUSAL = 1
    DOMINANCE = 2
    SOCIAL = 3
    STRESS = 4


@dataclass
class PersonalityProfile:
    name: str = "Default"
    baseline: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.3, 0.0, 0.0]))
    sensitivity: np.ndarray = field(default_factory=lambda: np.array([2.5, 2.0, 1.5, 2.0, 2.2]))
    decay_rates: np.ndarray = field(default_factory=lambda: np.array([0.04, 0.06, 0.05, 0.03, 0.07]))
    noise_amplitude: float = 0.03


# 事件 → 5 維刺激向量 [pleasure, arousal, dominance, social, stress]（作者原表）
EVENT_EMOTION_MAP: Dict[str, np.ndarray] = {
    "user_positive_feedback": np.array([1.0, 0.5, 0.3, 0.5, -0.4]),
    "user_negative_feedback": np.array([-1.0, 0.5, -0.4, -0.4, 0.6]),
    "task_success": np.array([0.6, 0.2, 0.4, 0.3, -0.2]),
    "task_failure": np.array([-0.6, 0.35, -0.35, -0.25, 0.5]),
    "user_engagement": np.array([0.4, 0.3, 0.2, 0.5, -0.15]),
    "user_disengagement": np.array([-0.3, -0.15, -0.15, -0.4, 0.25]),
    "system_error": np.array([-0.4, 0.5, -0.2, -0.15, 0.6]),
    "system_recovery": np.array([0.35, -0.2, 0.25, 0.2, -0.4]),
    "learning_progress": np.array([0.5, 0.15, 0.3, 0.35, -0.15]),
    "idle_period": np.array([0.0, -0.3, 0.0, -0.15, -0.15]),
    "surprise_positive": np.array([0.6, 0.5, 0.1, 0.3, -0.1]),
    "surprise_negative": np.array([-0.5, 0.6, -0.2, -0.2, 0.5]),
    "frustration": np.array([-0.4, 0.5, -0.3, -0.1, 0.6]),
    "curiosity_aroused": np.array([0.2, 0.4, 0.1, 0.2, -0.1]),
    "achievement": np.array([0.7, 0.3, 0.5, 0.3, -0.25]),
    "anxiety": np.array([-0.1, 0.7, -0.2, -0.1, 0.6]),
    "relief": np.array([0.4, -0.3, 0.2, 0.2, -0.5]),
    "gratitude": np.array([0.6, 0.15, 0.2, 0.5, -0.2]),
}


class AffectiveState:
    """5 維情緒狀態 + 耦合動力學。執行緒安全（單一 Lock）。"""

    def __init__(self, profile: PersonalityProfile | None = None):
        self.profile = profile or PersonalityProfile()
        self.state_vector = np.array(self.profile.baseline, dtype=np.float64)
        self.coupling_matrix = self._init_coupling()
        self._noise_buffer: np.ndarray = np.array([])
        self._pending_stimulus = np.zeros(5)   # post_event 累積，update 時套用
        self._lock = threading.Lock()
        self.events_total = 0

    @staticmethod
    def _init_coupling() -> np.ndarray:
        c = np.zeros((5, 5))
        c[EmotionDimension.STRESS.value, EmotionDimension.PLEASURE.value] = -0.4
        c[EmotionDimension.SOCIAL.value, EmotionDimension.PLEASURE.value] = 0.3
        c[EmotionDimension.STRESS.value, EmotionDimension.AROUSAL.value] = 0.5
        c[EmotionDimension.AROUSAL.value, EmotionDimension.STRESS.value] = 0.2
        c[EmotionDimension.SOCIAL.value, EmotionDimension.AROUSAL.value] = 0.25
        c[EmotionDimension.DOMINANCE.value, EmotionDimension.PLEASURE.value] = 0.2
        c[EmotionDimension.DOMINANCE.value, EmotionDimension.AROUSAL.value] = -0.15
        c[EmotionDimension.PLEASURE.value, EmotionDimension.SOCIAL.value] = 0.15
        return c

    @staticmethod
    def _nonlinear_transfer(x: np.ndarray) -> np.ndarray:
        """損失趨避：負向刺激 ×1.5（prospect theory）。"""
        loss_aversion = 1.5
        out = np.where(x >= 0, np.tanh(x), -loss_aversion * np.tanh(-x))
        return np.clip(out, -1.0, 1.0)

    def _noise_sample(self) -> float:
        """1/f 粉紅噪聲（生物性波動；白噪聲頻譜整形）。"""
        if len(self._noise_buffer) < 100:
            white = np.random.default_rng().standard_normal(1000)
            fft = np.fft.rfft(white)
            freqs = np.fft.rfftfreq(1000)
            freqs[0] = freqs[1]
            pink = np.fft.irfft(fft / np.sqrt(freqs), n=1000)
            self._noise_buffer = (pink - pink.mean()) / pink.std()
        sample = float(self._noise_buffer[0]) * self.profile.noise_amplitude
        self._noise_buffer = self._noise_buffer[1:]
        return sample

    # ── 寫入 ──

    def post_event(self, event_type: str, intensity: float = 1.0) -> bool:
        """事件 → 刺激佇列（下次 update 套用）。未知事件回 False。"""
        stim = EVENT_EMOTION_MAP.get(event_type)
        if stim is None:
            return False
        with self._lock:
            self._pending_stimulus += np.clip(stim * intensity, -1.0, 1.0)
            self.events_total += 1
        return True

    def update(self, dt: float = 1.0) -> None:
        """動力學積分：回歸基線 + 刺激 + 維度耦合 + 噪聲 → 損失趨避轉移。

        作者動力學以 dt=0.1 設計；粗步長（如 1s tick 的 dt=1.0）會讓耦合項
        過衝震盪 → 內部切 ≤0.1 子步積分。刺激是脈衝，只進第一子步。"""
        with self._lock:
            stimulus = self._pending_stimulus
            self._pending_stimulus = np.zeros(5)
            n = max(1, int(round(dt / 0.1)))
            dt_sub = dt / n
            for i in range(n):
                regression = (self.profile.baseline - self.state_vector) * self.profile.decay_rates
                coupling = np.dot(self.coupling_matrix, self.state_vector)
                stim = stimulus * self.profile.sensitivity if i == 0 else 0.0
                raw = regression + stim + coupling + self._noise_sample()
                self.state_vector = np.clip(
                    self.state_vector + self._nonlinear_transfer(raw * dt_sub), -1.0, 1.0)

    # ── 讀取 ──

    def get_valence_arousal(self) -> Tuple[float, float]:
        with self._lock:
            return (float(self.state_vector[EmotionDimension.PLEASURE.value]),
                    float(self.state_vector[EmotionDimension.AROUSAL.value]))

    def compute_mood(self) -> str:
        v, a = self.get_valence_arousal()
        if v > 0.5 and a > 0.3:
            return "joyful"
        if v > 0.3 and a < -0.2:
            return "relaxed"
        if v > 0.3:
            return "content"
        if v <= -0.5 and a > 0.3:
            return "angry"
        if v < -0.3 and a < -0.2:
            return "depressed"
        if v <= -0.3:
            return "sad"
        if a > 0.5:
            return "anxious"
        if a <= -0.3:
            return "calm"
        return "neutral"

    def compute_cognitive_bias(self) -> Dict[str, float]:
        """情緒 → 計算偏差（作者原公式）。消費端接真參數，這是移植的意義。"""
        with self._lock:
            s = self.state_vector
        v = float(s[EmotionDimension.PLEASURE.value])
        a = float(s[EmotionDimension.AROUSAL.value])
        d = float(s[EmotionDimension.DOMINANCE.value])
        st = float(s[EmotionDimension.STRESS.value])
        so = float(s[EmotionDimension.SOCIAL.value])
        bias = {
            "optimism": 0.3 * v,
            "risk_seeking": 0.2 * a - 0.15 * st,
            "attention_narrowing": 0.4 * a + 0.3 * st,
            "confirmation_bias": 0.25 * abs(v),
            "overconfidence": 0.3 * d,
            "temporal_discounting": 0.25 * st + 0.15 * a,
            "social_proximity": 0.3 * so,
            "creativity": 0.2 * v - 0.15 * st + 0.1 * a,
        }
        return {k: float(np.clip(val, -0.8, 0.8)) for k, val in bias.items()}

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            s = self.state_vector.copy()
        return {
            "mood": self.compute_mood(),
            "dims": {dim.name.lower(): round(float(s[dim.value]), 3)
                     for dim in EmotionDimension},
            "biases": {k: round(v, 3) for k, v in self.compute_cognitive_bias().items()},
            "events_total": self.events_total,
        }
