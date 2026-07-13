"""
UnifiedCausalEngine — dict-based 因果推理引擎 (純 Python)

從 stub 升級為可運行的因果引擎。
用 cause→effect 映射表實現因果鏈追蹤。
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("laap.agi.causal")


class UnifiedCausalEngine:
    """因果推理引擎 — 基於經驗的因果鏈"""

    def __init__(self, **kwargs):
        logger.info(f"[Causal] dict-based 初始化")
        self._rules: Dict[str, List[Dict[str, Any]]] = {}  # cause → [{effect, confidence, count}]
        self._effects: Dict[str, List[Dict[str, Any]]] = {}  # effect → [{cause, confidence, count}]

    def observe(self, cause: str, effect: str, confidence: float = 0.5) -> None:
        """學習一條因果關係。多次觀察提升置信度。"""
        c = cause.lower().strip()
        e = effect.lower().strip()

        if c not in self._rules:
            self._rules[c] = []
        existing = [r for r in self._rules[c] if r["effect"] == e]
        if existing:
            existing[0]["count"] += 1
            existing[0]["confidence"] = min(0.99, existing[0]["confidence"] + 0.1)
        else:
            self._rules[c].append({"effect": e, "confidence": confidence, "count": 1})

        if e not in self._effects:
            self._effects[e] = []
        existing_rev = [r for r in self._effects[e] if r["cause"] == c]
        if existing_rev:
            existing_rev[0]["count"] += 1
        else:
            self._effects[e].append({"cause": c, "confidence": confidence, "count": 1})

    def predict(self, query: str, mode: str = "default", top_k: int = 3) -> List[Dict[str, Any]]:
        """給定原因(query)，預測可能的結果。"""
        q = query.lower().strip()
        results = []

        # 精確匹配
        if q in self._rules:
            for r in sorted(self._rules[q], key=lambda x: x["confidence"], reverse=True):
                results.append({"cause": q, "effect": r["effect"],
                                "confidence": r["confidence"], "type": "exact"})

        # 部分匹配（關鍵詞重疊）
        if len(results) < top_k:
            q_words = set(q.split())
            for cause, rules in self._rules.items():
                if cause == q:
                    continue
                c_words = set(cause.split())
                overlap = len(q_words & c_words)
                if overlap > 0:
                    sim = overlap / max(len(q_words), len(c_words))
                    for r in rules:
                        results.append({"cause": cause, "effect": r["effect"],
                                        "confidence": r["confidence"] * sim, "type": "fuzzy"})

        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[:top_k]

    def explain(self, effect: str) -> List[Dict[str, Any]]:
        """給定結果(effect)，追溯可能的原因。"""
        e = effect.lower().strip()
        results = []
        if e in self._effects:
            for r in sorted(self._effects[e], key=lambda x: x["confidence"], reverse=True):
                results.append({"effect": e, "cause": r["cause"],
                                "confidence": r["confidence"]})
        return results

    def forward(self, cause: str) -> List[Dict[str, Any]]:
        """同 predict，語意別名。"""
        return self.predict(cause)

    def backward(self, effect: str) -> List[Dict[str, Any]]:
        """同 explain，語意別名。"""
        return self.explain(effect)

    def __len__(self) -> int:
        return len(self._rules)