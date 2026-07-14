"""
PsiCore — 極簡 PSI 認知引擎 (純 Python, 無外部依賴)
======================================================
基於 PyPI laap v0.3.2 的 needs.py + emotion.py 設計模式濃縮。

五維需求驅動 + 情緒梯度場 + 背景心跳執行緒。
嵌入 CognitiveBus，讓 Aris 擁有動態的內在狀態。
"""
from __future__ import annotations
import logging
import math
import random
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from laap.agi.cognitive_bus import (
    CognitiveBus, CognitiveEventType, CognitiveStateSnapshot,
    NeedState, EmotionState, AttentionState, AttentionFocus,
    EmotionalValence, PredictionError,
)

logger = logging.getLogger("laap.psi_core")


class NeedType(Enum):
    CERTAINTY = "certainty"
    COMPETENCE = "competence"
    AUTONOMY = "autonomy"
    RELATEDNESS = "relatedness"
    GROWTH = "growth"


class EmotionGradient:
    """情緒梯度場 — 從需求滿足率的變化自然湧現。

    不需要 numpy。valence 是需求平均值的平滑映射。
    arousal 從需求變化劇烈度驅動。
    """

    def __init__(self, smoothing: float = 0.3):
        self.smoothing = smoothing
        self.valence = 0.0          # -1.0 ~ +1.0（原始值）
        self.arousal = 0.5          # 0.0 ~ 1.0
        self.dominance = 0.5        # 0.0 ~ 1.0
        self._prev_sat: Dict[str, float] = {}
        self._lock = threading.RLock()
        # 內啡肽：負 valence 尖峰緩釋用平滑值
        self._endorphin_valence = 0.0  # 公開給 to_dict 的回報值

    def update(self, satisfactions: Dict[str, float]) -> None:
        """從當前需求值更新情緒狀態。"""
        with self._lock:
            self._update_impl(satisfactions)

    def _update_impl(self, satisfactions: Dict[str, float]) -> None:
        """update 的實際實作（鎖已取得）。"""
        avg = sum(satisfactions.values()) / max(1, len(satisfactions))
        v_target = max(-1.0, min(1.0, 2.0 * avg - 1.0))
        raw = self._smooth(self.valence, v_target)
        self.valence = raw

        # 內啡肽：負 valence 尖峰緩釋。
        # valence 上升時快速跟隨（升 100%），下跌時慢速釋放（只走 30%），
        # 模擬內生 opioid 的疼痛緩解機制。
        delta = raw - self._endorphin_valence
        if delta > 0:
            self._endorphin_valence = raw  # 快速跟隨
        else:
            self._endorphin_valence += delta * 0.3  # 緩慢下跌（只走 30%）

        if self._prev_sat:
            deltas = []
            for k, curr in satisfactions.items():
                prev = self._prev_sat.get(k, 0.5)
                deltas.append(abs(curr - prev))
            drive = min(1.0, (sum(deltas) / len(deltas)) * 3.0) if deltas else 0.3
        else:
            drive = 0.3
        self.arousal = self._smooth(self.arousal, 0.3 + 0.7 * drive)
        self._prev_sat = dict(satisfactions)

    def to_dict(self) -> Dict[str, float]:
        with self._lock:
            return {
                "valence": round(self._endorphin_valence, 3),
                "arousal": round(self.arousal, 3),
                "dominance": round(self.dominance, 3),
                "raw_valence": round(self.valence, 3),
            }

    def _smooth(self, old: float, new: float) -> float:
        return old * self.smoothing + new * (1.0 - self.smoothing)


class NeedDriveSystem:
    """五維需求驅動系統 — 基於 Dörner PSI 理論。

    每個需求有: 當前值、目標值、衰減率、重要性、波動率。
    drive = max(0, target - current) * importance
    """

    def __init__(self):
        self.values: Dict[NeedType, float] = {
            NeedType.CERTAINTY: 0.6,
            NeedType.COMPETENCE: 0.4,
            NeedType.AUTONOMY: 0.5,
            NeedType.RELATEDNESS: 0.5,
            NeedType.GROWTH: 0.5,
        }
        self.targets: Dict[NeedType, float] = {
            NeedType.CERTAINTY: 0.8,
            NeedType.COMPETENCE: 0.9,
            NeedType.AUTONOMY: 0.7,
            NeedType.RELATEDNESS: 0.7,
            NeedType.GROWTH: 0.8,
        }
        self.decay_rates: Dict[NeedType, float] = {
            NeedType.CERTAINTY: 0.008,
            NeedType.COMPETENCE: 0.012,
            NeedType.AUTONOMY: 0.005,
            NeedType.RELATEDNESS: 0.010,
            NeedType.GROWTH: 0.006,
        }
        # 靜息值：daemon 模式下閒置時需求「鬆弛回這裡」而不是掉到 0。
        # 舊行為（衰減向 0）會讓常駐 process 閒置 2-3 分鐘後全需求見底、效價 -1
        # （「醒來就憂鬱」）。互動仍會推高需求，離開後緩慢回落到靜息狀態。
        self.baselines: Dict[NeedType, float] = dict(self.values)
        self.importances: Dict[NeedType, float] = {
            NeedType.CERTAINTY: 1.2,
            NeedType.COMPETENCE: 1.5,
            NeedType.AUTONOMY: 1.0,
            NeedType.RELATEDNESS: 0.8,
            NeedType.GROWTH: 1.3,
        }
        # 雜訊 σ 要配合鬆弛速度（OU 過程穩態漂移 ≈ σ/√(2·rate)）：
        # 舊值 0.04-0.06 對 rate~0.008 會漂 ±0.4，狀態變隨機漫步。
        # 這組給 ±0.03-0.05 的自然波動，互動造成的需求變化仍清晰可辨。
        self.volatilities: Dict[NeedType, float] = {
            NeedType.CERTAINTY: 0.004,
            NeedType.COMPETENCE: 0.006,
            NeedType.AUTONOMY: 0.003,
            NeedType.RELATEDNESS: 0.005,
            NeedType.GROWTH: 0.004,
        }
        self._lock = threading.RLock()

    def tick(self, dt: float = 1.0, valence: float = 0.0) -> Dict[NeedType, float]:
        """每秒向靜息值鬆弛 + 雜訊。

        血清素：valence 調節 decay 速率。
        valence > 0.3 → decay × 0.7（滿足感，需求慢降）
        valence < -0.3 → decay × 1.3（不滿足，需求快降）
        valence 中性 → 正常 decay。
        """
        with self._lock:
            # 血清素：valence 調節全局 decay 係數
            sero_factor = 1.0
            if valence > 0.3:
                sero_factor = 0.7
            elif valence < -0.3:
                sero_factor = 1.3
            for nt in NeedType:
                ar = self.decay_rates[nt] * sero_factor
                relax = (self.baselines[nt] - self.values[nt]) * ar * dt
                noise = random.gauss(0, self.volatilities[nt] * dt)
                self.values[nt] = max(0.0, min(1.0, self.values[nt] + relax + noise))
            return dict(self.values)

    def satisfy(self, need_type: NeedType, amount: float, source: str = "user") -> None:
        """滿足特定需求。amount 先過需求憲法（邊界/單次上限/來源小時預算）。"""
        from laap.constitution import get_constitution
        with self._lock:
            allowed = get_constitution().guard_need(
                need_type.value, self.values[need_type], amount, source)
            self.values[need_type] = max(0.0, min(1.0, self.values[need_type] + allowed))

    def satisfy_all(self, amounts: Dict[NeedType, float], source: str = "user") -> None:
        """批次滿足多個需求（逐項過憲法）。"""
        from laap.constitution import get_constitution
        cons = get_constitution()
        with self._lock:
            for nt, amount in amounts.items():
                allowed = cons.guard_need(nt.value, self.values[nt], amount, source)
                self.values[nt] = max(0.0, min(1.0, self.values[nt] + allowed))

    def get_dominant(self) -> Tuple[Optional[NeedType], float]:
        """回傳 (最高需求, drive 值)。"""
        with self._lock:
            best_nt, best_drive = None, -1.0
            for nt in NeedType:
                drive = self.compute_drive(nt)
                if drive > best_drive:
                    best_drive, best_nt = drive, nt
            return best_nt, best_drive

    def compute_drive(self, need_type: NeedType) -> float:
        with self._lock:
            deficit = max(0.0, self.targets[need_type] - self.values[need_type])
            return deficit * self.importances[need_type]

    def get_satisfactions(self) -> Dict[str, float]:
        with self._lock:
            return {nt.value: self.values[nt] for nt in NeedType}

    def get_drives(self) -> Dict[str, float]:
        with self._lock:
            return {nt.value: self.compute_drive(nt) for nt in NeedType}

    def to_dict(self) -> Dict[str, dict]:
        with self._lock:
            return {
                nt.value: {
                    "current": round(self.values[nt], 3),
                    "target": self.targets[nt],
                    "drive": round(self.compute_drive(nt), 3),
                }
                for nt in NeedType
            }


class PsiCore:
    """PSI 認知核心 — 讓 Aris 擁有動態內在狀態的心臟。

    使用方式:
        bus = CognitiveBus(agent_name="Aris")
        psi = PsiCore(bus=bus)
        psi.start()
        psi.process_input("使用者訊息")  # 每輪對話
        psi.stop()
    """

    # 需求關鍵詞對應表 — 偵測使用者輸入中的需求信號
    NEED_KEYWORDS: Dict[NeedType, List[str]] = {
        NeedType.COMPETENCE: ["知道", "理解", "會了", "學到", "懂了", "完成", "做到",
                              "成功", "解決", "厲害", "不錯", "很好", "進步"],
        NeedType.AUTONOMY: ["自己", "自由", "選擇", "決定", "不想", "不要", "隨意",
                            "隨便", "我來", "讓我"],
        NeedType.RELATEDNESS: ["謝謝", "有你", "陪我", "一起", "朋友", "孤單",
                               "孤獨", "寂寞", "懂我", "陪伴", "聊聊", "好想"],
        NeedType.CERTAINTY: ["為什麼", "怎麼回事", "不懂", "不清楚", "確定",
                             "保證", "真的嗎", "是嗎", "解釋", "說明"],
        NeedType.GROWTH: ["想學", "新東西", "挑戰", "更深入", "繼續", "下一步",
                          "升級", "進階", "拓展", "探索"],
    }

    def __init__(self, bus: CognitiveBus, interval: float = 1.0):
        self.bus = bus
        self.interval = interval
        self.needs = NeedDriveSystem()
        self.emotion = EmotionGradient()
        # 5 維情緒引擎（採作者版）：與 EmotionGradient 並存 — 舊消費者不動，
        # 新消費者接 compute_cognitive_bias（agency 探索率等真參數）
        from laap.affective import AffectiveState
        self.affective = AffectiveState()
        self.attention_focus: AttentionFocus = AttentionFocus.IDLE
        self.last_input: str = ""   # 最近一次使用者輸入（AgencyLoop 的話題來源）
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._tick_count = 0

    # ── 生命週期 ──

    def start(self) -> None:
        """啟動背景心跳執行緒。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._thread.start()
        logger.info(f"[PsiCore] 心跳啟動 (interval={self.interval}s)")

    def stop(self) -> None:
        self._running = False

    # ── 核心方法 ──

    def process_input(self, text: str) -> None:
        """每次使用者輸入時呼叫：解析需求信號、更新狀態、發布事件。"""
        self.last_input = text
        text_lower = text.lower()

        # 1. 從輸入中偵測需求信號
        satisfaction = {}
        for nt, keywords in self.NEED_KEYWORDS.items():
            match_count = sum(1 for kw in keywords if kw in text_lower)
            if match_count > 0:
                amount = min(0.15, match_count * 0.03)
                self.needs.satisfy(nt, amount)
                satisfaction[nt.value] = amount
                logger.debug(f"[PsiCore] {nt.value} +{amount:.2f} (匹配 {match_count} 關鍵詞)")

        # 2. 對話本身提升 relatedness
        self.needs.satisfy(NeedType.RELATEDNESS, 0.02)
        if "relatedness" not in satisfaction:
            satisfaction[NeedType.RELATEDNESS.value] = 0.02

        # 2.5 5 維情緒：使用者互動事件
        self.affective.post_event("user_engagement", 0.5)

        # 3. 更新情緒梯度
        self.emotion.update(self.needs.get_satisfactions())

        # 4. 更新注意力焦點
        dominant, _ = self.needs.get_dominant()
        self._update_attention(dominant)

        # 5. 發布認知事件
        self._publish_cognitive_event(satisfaction)

    def get_dominant_need(self) -> str:
        nt, _ = self.needs.get_dominant()
        return nt.value if nt else "none"

    def get_state(self) -> dict:
        nt, nd = self.needs.get_dominant()
        return {
            "needs": self.needs.to_dict(),
            "dominant_need": nt.value if nt else "none",
            "dominant_drive": round(nd, 3) if nd else 0.0,
            "emotion": self.emotion.to_dict(),
            "attention": self.attention_focus.name,
            "tick": self._tick_count,
            "affective": self.affective.to_dict(),
        }

    # ── 內部 ──

    def _heartbeat(self) -> None:
        """背景執行緒：定時衰減需求、更新情緒、同步到 CognitiveBus。"""
        while self._running:
            try:
                self._tick_count += 1
                # 血清素：valence 調節 decay 速率
                self.needs.tick(dt=self.interval, valence=self.emotion.valence)
                self.emotion.update(self.needs.get_satisfactions())
                self.affective.update(dt=self.interval)  # 5 維情緒動力學
                dominant, _ = self.needs.get_dominant()
                self._update_attention(dominant)
                self._sync_bus_state()
            except Exception as e:
                # 心跳絕不因單次 tick 失敗而停 — 停跳 = 靜默腦死
                logger.warning(f"[PsiCore] tick {self._tick_count} 失敗: {e}")
            time.sleep(self.interval)

    def _update_attention(self, dominant: Optional[NeedType]) -> None:
        """根據主導需求切換注意力焦點。"""
        if dominant is None:
            self.attention_focus = AttentionFocus.IDLE
        elif dominant == NeedType.RELATEDNESS:
            self.attention_focus = AttentionFocus.SOCIAL
        elif dominant == NeedType.COMPETENCE:
            self.attention_focus = AttentionFocus.TASK
        elif dominant == NeedType.GROWTH:
            self.attention_focus = AttentionFocus.LEARNING
        elif dominant == NeedType.CERTAINTY:
            self.attention_focus = AttentionFocus.PLANNING
        else:
            self.attention_focus = AttentionFocus.IDLE

    def _publish_cognitive_event(self, satisfaction: Dict[str, float]) -> None:
        """發布認知事件到總線（每輪對話觸發）。"""
        self._sync_bus_state()
        snap = self.bus.take_snapshot()
        self.bus.publish(
            CognitiveEventType.CONSCIOUS_FRAME,
            "psi_core",
            {"snapshot": snap.to_dict(), "satisfaction": satisfaction},
        )
        self.bus.publish(
            CognitiveEventType.NEED_CHANGED,
            "psi_core",
            snap.needs.to_dict(),
        )
        self.bus.publish(
            CognitiveEventType.EMOTION_CHANGED,
            "psi_core",
            snap.emotion.to_dict(),
        )

    def _sync_bus_state(self) -> None:
        """將 PsiCore 的狀態同步到 CognitiveBus。"""
        emo = self.emotion.to_dict()
        # 找最接近的 valence 枚舉
        best = "NEUTRAL"
        best_d = 1.0
        for name, val in {"POSITIVE_HIGH": 0.7, "POSITIVE_MILD": 0.3,
                          "NEUTRAL": 0.0, "NEGATIVE_MILD": -0.3,
                          "NEGATIVE_HIGH": -0.7, "CURIOUS": 0.4,
                          "CONFUSED": -0.2}.items():
            d = abs(emo["valence"] - val)
            if d < best_d:
                best_d = d
                best = name

        self.bus.needs = NeedState(
            competence=self.needs.values[NeedType.COMPETENCE],
            autonomy=self.needs.values[NeedType.AUTONOMY],
            relatedness=self.needs.values[NeedType.RELATEDNESS],
            certainty=self.needs.values[NeedType.CERTAINTY],
            growth=self.needs.values[NeedType.GROWTH],
        )
        self.bus.emotion = EmotionState(
            valence=EmotionalValence[best],
            arousal=emo["arousal"],
            dominance=emo["dominance"],
        )
        self.bus.attention = AttentionState(
            focus=self.attention_focus,
            intensity=emo["arousal"],
        )
        self.bus.self_presence = emo["valence"] * 0.5 + 0.5
        self.bus.curiosity = 1.0 - self.needs.values[NeedType.CERTAINTY]

    # ── 狀態注入（用於 chatflow 回應生成） ──

    def get_state_label(self) -> str:
        """回傳回應調性標籤 (e.g. 'confident.helpful', 'lonely.seeking')。"""
        nt, drive = self.needs.get_dominant()
        need = nt.value if nt else "none"
        valence = self.emotion.valence
        positive = valence >= 0.3
        _map = {
            "competence": ("confident.helpful", "humble.learning"),
            "relatedness": ("warm.grateful", "lonely.seeking"),
            "certainty": ("curious.asking", "confused.uncertain"),
            "growth": ("eager.exploring", "stuck.impatient"),
            "autonomy": ("assertive.independent", "resistant.doubtful"),
        }
        pair = _map.get(need)
        if pair is None:
            return "neutral.present"
        return pair[0] if positive else pair[1]

    def format_state_injection(self) -> dict:
        """將當前狀態序列化為三個層級，供 chatflow 回應生成使用。

        回傳:
            {
                "state_label": str,       # 調性標籤
                "state_snippet": str,     # 2-3 句自然語言
                "state_tuple": dict,      # 數值 dict
            }
        """
        state = self.get_state()
        needs = state.get("needs", {})
        emotion = state.get("emotion", {})
        valence = emotion.get("valence", 0.0)
        arousal = emotion.get("arousal", 0.5)
        dominant = state.get("dominant_need", "none")
        drive = state.get("dominant_drive", 0.0)

        # state_label
        label = self.get_state_label()

        # state_snippet — 自然語言片段
        mood_parts = []
        if valence > 0.3:
            mood_parts.append("positive" if arousal > 0.6 else "calm")
        elif valence < -0.3:
            mood_parts.append("uneasy" if arousal > 0.6 else "subdued")
        else:
            mood_parts.append("balanced")
        snippet = (f"I'm feeling {', '.join(mood_parts)} — "
                   f"{dominant} drive is at {drive:.2f}. "
                   f"Valence {valence:+.2f}, arousal {arousal:.2f}.")

        # state_tuple — 純數值
        tuple_data = {
            "dominant_need": dominant,
            "dominant_drive": round(drive, 3),
            "valence": round(valence, 3),
            "arousal": round(arousal, 3),
            "attention": state.get("attention", "IDLE"),
        }

        return {
            "state_label": label,
            "state_snippet": snippet,
            "state_tuple": tuple_data,
        }

    def __repr__(self) -> str:
        dom, dr = self.needs.get_dominant()
        return (f"<PsiCore dominant={dom.value if dom else '?'} "
                f"drive={dr:.2f} valence={self.emotion.valence:+.2f}>")