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
