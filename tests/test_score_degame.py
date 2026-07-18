"""E1.1 acceptance test — de-game _score_result（堵 len/500 刷分漏洞）。

驗真的 laap.agency.AgencyLoop._score_result（_score_result 不碰 self，__new__ 即可）。
未修前：not_gamed_by_length 應紅（現況長度越長分越高）。
修後：四案全綠。E1.1 只動無 [score] 前綴的 base 路徑，不碰 [score] 真分數線。
"""
from laap.agency import AgencyLoop

_ag = AgencyLoop.__new__(AgencyLoop)  # _score_result 不用 self


def test_score_not_gamed_by_length():
    """核心：長垃圾不該比短結果分數高（len/500 刷分漏洞）。"""
    short = _ag._score_result("找到了", tool="web-search")
    long_garbage = _ag._score_result("x" * 800, tool="web-search")
    assert short == long_garbage, \
        f"分數不該因長度不同（刷分漏洞）：short={short}, long={long_garbage}"


def test_empty_result_still_zero():
    """空/無結果維持 0 —— 修復不能弄丟這個信號。"""
    assert _ag._score_result("", tool="web-search") == 0.0
    assert _ag._score_result("無結果", tool="web-search") == 0.0


def test_found_something_scores_above_nothing():
    """找到東西 > 無結果 —— 修復要保住『有 vs 無』這個不可作弊的信號。"""
    found = _ag._score_result("some real content here", tool="web-search")
    nothing = _ag._score_result("無結果", tool="web-search")
    assert found > nothing, f"找到東西應 > 無結果：found={found}, nothing={nothing}"


def test_scored_gbrain_result_unchanged():
    """[score] 前綴走真分數線，E1.1 不動它（回歸保護）。"""
    r = _ag._score_result("[0.9] good hit\n[0.8] another hit", tool="gbrain")
    assert r > 0.5, f"高分 gbrain 結果應 > 0.5：{r}"
