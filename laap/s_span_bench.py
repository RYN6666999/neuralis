"""E3：S_span 誠實驗收度量（安全脊椎 Stage 4 尾）。

問一個問題：這套學習/分工，真的比純規則表 baseline 強嗎？
關鍵不是『更多樣』（填磚也會多），是：
  1. 選擇非隨機性 —— 選擇有沒有跟獎勵相關（學到偏好好選擇 = 學了；~0 = 規則表/隨機）
  2. 動作多樣性熵 —— 對照規則表（固定 = 只有 need 那層熵）

純度量函式，無 I/O，可單測。runner 見 scripts/benchmark-s-span.py。
"""
from __future__ import annotations

import math
import random
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
    # + 0.0 消掉 -0.0：單一選擇時 -1*(1*log2(1)) = -0.0，印出來是「-0.00 bits」，
    # 負熵在物理上無意義，讀報告的人會以為度量壞了。
    return -sum((k / n) * math.log2(k / n) for k in counts.values()) + 0.0


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


# ── E3.2：可信度校準（2026-08-20）─────────────────────────────────────
#
# 為什麼加這段：`learning_correlation` 的判準（corr > 0.2）**分不出學習與隨機**。
# 蒙地卡羅實測（四選項、品質 0.8/0.6/0.4/0.2、200 次重複）：
#
#     n      學習組通過率   隨機對照組誤判率
#     30        58%            42%
#    100       100%            39%
#    600       100%            42%
#   1200       100%            42%
#
# 誤判率約 40% **且不隨樣本量下降** —— 這不是資料不夠，是判準本身的問題。
# 根因：Pearson 對「選擇頻率 vs 平均 outcome」只有 4 個點，而相關係數是
# 尺度不變的。均勻亂選時各選項頻率幾乎相同（例：152/144/154/150），
# 只有 ~10% 的隨機抖動，但 Pearson 不看抖動多小，只看方向 —— 抖動偶然
# 與品質同向就得高 corr。
#
# 所以「讓 Aris 多跑一陣再驗」不會讓結論變可信，只會讓一個 40% 會說謊的
# 判準跑在更多資料上。
#
# 改用 realized_advantage：**你實際選出來的平均 outcome，比均勻亂選好多少**。
# 這是有單位、有方向、不會因尺度不變而失真的量。閾值不人工挑，用虛無重抽
# 得出（見 learning_verdict）。同一套蒙地卡羅：
#
#     n      學習組檢出率   隨機對照組誤判率
#    100        92%             4%
#    300       100%             4%
#    600       100%             0%
#   1200       100%             2%
#
# 誤判率落在設計值 5% 附近且隨樣本量收斂 —— 這才是能拿來下結論的判準。

def realized_advantage(records: list) -> float:
    """實際取得的平均 outcome − 均勻亂選的期望 outcome。

    >0 = 選擇偏向了高品質選項（學了）；~0 = 跟亂選沒差別。
    有單位（outcome 的單位），可直接讀「好多少」。
    """
    agg = defaultdict(lambda: {"count": 0, "sum": 0.0})
    for r in records:
        a = agg[r["choice"]]
        a["count"] += 1
        a["sum"] += float(r.get("outcome", 0))
    if not agg:
        return 0.0
    n = sum(a["count"] for a in agg.values())
    realized = sum(a["sum"] for a in agg.values()) / n
    uniform = sum(a["sum"] / a["count"] for a in agg.values()) / len(agg)
    return realized - uniform


def learning_verdict(records: list, iters: int = 400, seed: int = 0) -> dict:
    """虛無重抽檢定：realized_advantage 是否超過「均勻亂選」的 95 百分位。

    虛無分佈的建法：保留每個選項觀測到的 outcome 分佈，但把**選擇**換成均勻隨機，
    重抽同樣筆數 iters 次。這樣虛無假設就是「選擇與品質無關」，而選項本身的
    品質差異與 outcome 噪聲都保留 —— 閾值由資料自己決定，不人工挑。

    回 {advantage, null_p95, learned, n_records, n_choices, underpowered}。
    underpowered=True 代表樣本量不足以下任何結論（見上方誤判率表：n<100 時
    學習組檢出率也只有 ~50%，這時「未證實」不等於「沒學」）。
    """
    by_choice = defaultdict(list)
    for r in records:
        by_choice[r["choice"]].append(float(r.get("outcome", 0)))
    n = len(records)
    out = {"advantage": realized_advantage(records), "null_p95": None,
           "learned": False, "n_records": n, "n_choices": len(by_choice),
           "underpowered": n < 100 or len(by_choice) < 2}
    if len(by_choice) < 2 or n == 0:
        return out
    keys = list(by_choice)
    rng = random.Random(seed)
    null = []
    for _ in range(iters):
        sim = []
        for _ in range(n):
            c = rng.choice(keys)
            sim.append({"choice": c, "outcome": rng.choice(by_choice[c])})
        null.append(realized_advantage(sim))
    null.sort()
    out["null_p95"] = null[min(int(0.95 * len(null)), len(null) - 1)]
    out["learned"] = out["advantage"] > out["null_p95"]
    return out
