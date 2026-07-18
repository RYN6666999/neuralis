"""E3：S_span 誠實驗收度量（安全脊椎 Stage 4 尾）。

問一個問題：這套學習/分工，真的比純規則表 baseline 強嗎？
關鍵不是『更多樣』（填磚也會多），是：
  1. 選擇非隨機性 —— 選擇有沒有跟獎勵相關（學到偏好好選擇 = 學了；~0 = 規則表/隨機）
  2. 動作多樣性熵 —— 對照規則表（固定 = 只有 need 那層熵）

純度量函式，無 I/O，可單測。runner 見 scripts/benchmark-s-span.py。
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable


def behavior_entropy(choices: Iterable) -> float:
    """選擇分佈的 Shannon 熵（bits）。越高越多樣。"""
    counts = defaultdict(int)
    n = 0
    for c in choices:
        counts[c] += 1
        n += 1
    if n == 0:
        return 0.0
    return -sum((k / n) * math.log2(k / n) for k in counts.values())


def learning_correlation(records: list) -> dict:
    """選擇非隨機性 = 選擇頻率 vs 平均 outcome 的相關。
    records: [{choice, outcome}]。學了 → 常選的選擇平均 outcome 較高（正相關）。
    回 {corr, n_choices, n_records}。n_choices < 2 → corr=None（算不了）。"""
    agg = defaultdict(lambda: {"count": 0, "sum": 0.0})
    for r in records:
        a = agg[r["choice"]]
        a["count"] += 1
        a["sum"] += float(r.get("outcome", 0))
    xs = [a["count"] for a in agg.values()]                       # 選擇頻率
    ys = [a["sum"] / a["count"] for a in agg.values()]            # 平均 outcome
    n = len(xs)
    if n < 2:
        return {"corr": None, "n_choices": n, "n_records": len(records)}
    return {"corr": _pearson(xs, ys), "n_choices": n, "n_records": len(records)}


def _pearson(xs: list, ys: list) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if vx == 0 or vy == 0:
        return 0.0
    return cov / (vx * vy)
