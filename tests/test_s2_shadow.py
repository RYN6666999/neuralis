"""S2-shadow guard — 前瞻預測器 + lookahead_accuracy 度量。

§9 投資閘：投 tree-search 前，要先證明 lookahead 會贏過現況 bandit。做法是 shadow —
每次真實行動額外算 1-step 預測、記 predicted vs actual，**不改行為**。這裡釘預測器
（權重高→預測高、夾 [0,1]）與相關度量（追得準→正、隨機→~0）。
"""
from laap.agency import AgencyLoop
from laap.s_span_bench import lookahead_accuracy


def _ag():
    ag = AgencyLoop.__new__(AgencyLoop)
    ag._need_stats = {}
    return ag


def test_predict_higher_for_favored_tool():
    ag = _ag()
    ag._need_stats = {"competence": {"expected": 0.5,
                                     "tool_weights": {"gbrain": 0.5, "web-search": 2.5}}}
    p_low = ag._predict_outcome("competence", "gbrain")
    p_high = ag._predict_outcome("competence", "web-search")
    assert p_high > p_low


def test_predict_clamped_0_1():
    ag = _ag()
    ag._need_stats = {"competence": {"expected": 0.9,
                                     "tool_weights": {"web-search": 3.0, "gbrain": 0.1}}}
    p = ag._predict_outcome("competence", "web-search")
    assert 0.0 <= p <= 1.0


def test_predict_default_for_unknown_need():
    # 無 stats → base 0.3、均勻權重 → 預測 ≈ base，仍在 [0,1]
    p = _ag()._predict_outcome("growth", "gbrain")
    assert 0.0 <= p <= 1.0


def test_lookahead_accuracy_tracks_actual():
    recs = [{"predicted": 0.1, "outcome": 0.15}, {"predicted": 0.4, "outcome": 0.45},
            {"predicted": 0.7, "outcome": 0.66}, {"predicted": 0.9, "outcome": 0.95}]
    r = lookahead_accuracy(recs)
    assert r["corr"] is not None and r["corr"] > 0.8 and r["n"] == 4


def test_lookahead_accuracy_anticorrelated_negative():
    recs = [{"predicted": 0.1, "outcome": 0.9}, {"predicted": 0.9, "outcome": 0.1}]
    assert lookahead_accuracy(recs)["corr"] < 0


def test_lookahead_accuracy_ignores_missing_predicted():
    recs = [{"outcome": 0.5}, {"predicted": 0.3, "outcome": 0.3}]
    assert lookahead_accuracy(recs)["n"] == 1        # 只有 1 筆有 predicted
    assert lookahead_accuracy(recs)["corr"] is None  # n<2 算不了


def test_lookahead_accuracy_empty():
    assert lookahead_accuracy([])["corr"] is None
