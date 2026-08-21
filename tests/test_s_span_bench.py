"""E3 度量 acceptance — 熵 + 選擇非隨機性（學了 vs 規則表）。"""
import math

from laap.s_span_bench import behavior_entropy, learning_correlation


def test_entropy_uniform_is_max():
    # 4 個等頻選擇 → 熵 = log2(4) = 2 bits
    assert abs(behavior_entropy(["a", "b", "c", "d"]) - 2.0) < 1e-9


def test_entropy_single_choice_is_zero():
    # 規則表固定一個選擇 → 熵 0
    assert behavior_entropy(["a", "a", "a"]) == 0.0


def test_entropy_empty():
    assert behavior_entropy([]) == 0.0


def test_learning_positive_correlation():
    # 學了：常選的選擇 outcome 高（正相關）
    recs = ([{"choice": "good", "outcome": 0.9}] * 8 +
            [{"choice": "bad", "outcome": 0.2}] * 2)
    r = learning_correlation(recs)
    assert r["corr"] is not None and r["corr"] > 0.5, "常選=高 outcome → 正相關（學了）"


def test_learning_no_correlation_random():
    # 隨機/規則表：選擇頻率跟 outcome 無關
    recs = ([{"choice": "a", "outcome": 0.9}] * 5 +
            [{"choice": "b", "outcome": 0.9}] * 5)
    r = learning_correlation(recs)
    # 兩個選擇同頻同 outcome → 頻率無變異 → corr 0
    assert r["corr"] == 0.0


def test_learning_single_choice_uncomputable():
    r = learning_correlation([{"choice": "a", "outcome": 0.5}] * 3)
    assert r["corr"] is None, "只有一個選擇算不了相關"


# ── E3.2 可信度校準（2026-08-20）──────────────────────────────────────
# 這些測試守的不是「函式回對的數字」，是**這個 benchmark 能分出學習與隨機**。
# 舊判準 corr>0.2 對隨機對照組有約 40% 誤判率且不隨樣本量下降 —— 一個會說謊
# 的度量比沒有度量更糟，因為它會讓人拿它下結論。

import random

from laap.s_span_bench import learning_verdict, realized_advantage


def _sim(learn: bool, n: int, seed: int) -> list:
    """四選項、品質固定、outcome 有噪聲。learn=True 依權重選並用 outcome 更新權重。"""
    rng = random.Random(seed)
    quality = {"A": 0.8, "B": 0.6, "C": 0.4, "D": 0.2}
    weights = {k: 1.0 for k in quality}
    recs = []
    for _ in range(n):
        if learn:
            total = sum(weights.values())
            r, acc = rng.random() * total, 0.0
            choice = list(weights)[-1]
            for k, v in weights.items():
                acc += v
                if r <= acc:
                    choice = k
                    break
        else:
            choice = rng.choice(list(quality))
        out = max(0.0, min(1.0, rng.gauss(quality[choice], 0.15)))
        recs.append({"choice": choice, "outcome": out})
        if learn:
            weights[choice] = max(0.1, min(3.0, weights[choice] + (out - 0.5) * 0.1))
    return recs


def test_entropy_never_negative():
    """單一選擇時舊版回 -0.0，印成「-0.00 bits」—— 負熵讓讀報告的人以為度量壞了。"""
    from laap.s_span_bench import behavior_entropy
    for choices in (["a"], ["a", "a", "a"], []):
        e = behavior_entropy(choices)
        assert e >= 0.0, f"{choices!r} → {e!r}"
        assert f"{e:.2f}" != "-0.00"


def test_realized_advantage_positive_when_learning():
    assert realized_advantage(_sim(True, 600, 0)) > 0.02


def test_realized_advantage_near_zero_when_random():
    """均勻亂選 → 實現優勢應接近 0（有單位的量，不是尺度不變的相關係數）。"""
    for seed in range(5):
        assert abs(realized_advantage(_sim(False, 600, 1000 + seed))) < 0.02


def test_verdict_detects_learning():
    for seed in range(5):
        assert learning_verdict(_sim(True, 300, seed), iters=200, seed=seed)["learned"]


def test_verdict_rejects_random_control():
    """關鍵測試：隨機對照組不得被判成「學了」。
    舊判準在這條上有約 40% 誤判率 —— 這是整段 E3.2 存在的理由。"""
    verdicts = [learning_verdict(_sim(False, 300, 2000 + s), iters=200, seed=s)["learned"]
                for s in range(10)]
    assert sum(verdicts) <= 1, f"隨機對照組誤判 {sum(verdicts)}/10 —— 判準不可信"


def test_verdict_flags_underpowered_instead_of_concluding():
    """樣本不足時要說「測不出來」，不能說「沒學」——後者是錯誤結論。"""
    v = learning_verdict(_sim(True, 20, 0), iters=100, seed=0)
    assert v["underpowered"] is True
    v2 = learning_verdict(_sim(True, 300, 0), iters=200, seed=0)
    assert v2["underpowered"] is False


def test_verdict_handles_single_choice_and_empty():
    for recs in ([], [{"choice": "a", "outcome": 0.5}] * 10):
        v = learning_verdict(recs, iters=50)
        assert v["learned"] is False
        assert v["underpowered"] is True
