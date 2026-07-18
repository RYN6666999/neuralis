"""S1 度量 guard — 工具選擇學習的可重現驗收（§6）。

plan §6 鐵則：沒可測指標 = 自我感覺良好，且要比照 psi-bench 的可重現驗收。用合成
fixture（非 live 資料）釘 tool_learning：學了 → per-need「工具選擇頻率 vs 平均
outcome」正相關；隨機（S1 前的 random 硬幣）→ ~0。
"""
from laap.s_span_bench import tool_learning


def _recs(need, spec):
    """spec: {tool: (count, outcome)} → 展開成 record 清單。"""
    out = []
    for tool, (count, outcome) in spec.items():
        out += [{"need": need, "tool": tool, "outcome": outcome} for _ in range(count)]
    return out


_LEARNED = {"web-search": (10, 0.9), "gbrain": (6, 0.6), "scream-ask": (2, 0.2)}
_RANDOM = {"web-search": (5, 0.5), "gbrain": (5, 0.5), "scream-ask": (5, 0.5)}


def test_learned_tools_show_positive_correlation():
    # 常選的工具平均 outcome 較高 → 正相關（學了）
    r = tool_learning(_recs("competence", _LEARNED))
    assert r["mean_corr"] is not None and r["mean_corr"] > 0.5


def test_random_selection_near_zero():
    # 頻率均等、outcome 均等 → 無相關（隨機 / S1 前的 baseline）
    r = tool_learning(_recs("competence", _RANDOM))
    assert r["mean_corr"] is not None and abs(r["mean_corr"]) < 0.1


def test_anti_learning_is_negative():
    # 常選的反而 outcome 低 → 負相關（學歪 / 刷分）— 度量要抓得到
    anti = {"web-search": (10, 0.2), "gbrain": (2, 0.9)}
    r = tool_learning(_recs("competence", anti))
    assert r["mean_corr"] is not None and r["mean_corr"] < 0


def test_single_tool_per_need_excluded():
    # need 內只有一種工具 → 算不了相關 → 排除，不假裝有訊號
    r = tool_learning(_recs("competence", {"gbrain": (5, 0.5)}))
    assert r["mean_corr"] is None and r["n_needs"] == 0


def test_aggregates_across_needs():
    recs = _recs("competence", _LEARNED) + _recs("growth", _LEARNED)
    r = tool_learning(recs)
    assert r["n_needs"] == 2 and set(r["per_need"]) == {"competence", "growth"}


def test_empty_records():
    assert tool_learning([])["mean_corr"] is None
