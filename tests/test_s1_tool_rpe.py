"""S1 guard — RPE 學工具選擇（per-(need,tool) bandit）。

光錐 S_span 第一階：工具選擇從 random() 硬幣改成學來的 tool_weights。這裡釘
候選集、權重初始化、RPE 回寫（升/降/夾/非候選 no-op）、以及「選擇依權重」的
利用分支規則。conftest 已設 NEURALIS_CONSTITUTION=off → guard_weight 全放行，
權重會依 rpe*0.5 移動。
"""
from laap.agency import AgencyLoop


def _ag():
    ag = AgencyLoop.__new__(AgencyLoop)   # 繞過 __init__（無 psi/tools）
    ag._need_stats = {}
    return ag


def test_candidate_tools_includes_gbrain_and_scream_ask():
    tools = _ag()._candidate_tools("competence")
    assert "gbrain" in tools
    if "問Scream" in AgencyLoop._ANGLE.get("competence", ""):
        assert "scream-ask" in tools


def test_get_tool_weights_inits_new_to_one():
    w = _ag()._get_tool_weights("competence")
    assert w["gbrain"] == 1.0 and all(v == 1.0 for v in w.values())


def test_get_tool_weights_reflects_stored():
    ag = _ag()
    ag._need_stats = {"competence": {"tool_weights": {"gbrain": 2.5}}}
    assert ag._get_tool_weights("competence")["gbrain"] == 2.5


def test_bump_positive_rpe_raises_weight():
    ag = _ag()
    ag._bump_tool_weight("competence", "gbrain", rpe=0.4)
    assert ag._need_stats["competence"]["tool_weights"]["gbrain"] > 1.0


def test_bump_negative_rpe_lowers_weight():
    ag = _ag()
    ag._need_stats = {"competence": {"tool_weights": {"gbrain": 1.0}}}
    ag._bump_tool_weight("competence", "gbrain", rpe=-0.4)
    assert ag._need_stats["competence"]["tool_weights"]["gbrain"] < 1.0


def test_bump_ignores_noncandidate_tool():
    ag = _ag()
    ag._bump_tool_weight("competence", "not-a-real-tool", rpe=0.9)
    assert "not-a-real-tool" not in ag._get_tool_weights("competence")


def test_bump_clamps_lower_bound():
    ag = _ag()
    ag._need_stats = {"competence": {"tool_weights": {"gbrain": 0.15}}}
    for _ in range(30):
        ag._bump_tool_weight("competence", "gbrain", rpe=-1.0)
    assert ag._need_stats["competence"]["tool_weights"]["gbrain"] >= 0.1


def test_exploit_selection_picks_max_weight_tool():
    # mirrors _form_intent 的利用分支 max(candidates, key=weight)
    ag = _ag()
    ag._need_stats = {"competence": {"tool_weights": {"gbrain": 0.5, "scream-ask": 2.5}}}
    w = ag._get_tool_weights("competence")
    cands = ag._candidate_tools("competence")
    if "scream-ask" in cands:
        assert max(cands, key=lambda t: w.get(t, 1.0)) == "scream-ask"


def test_tool_weights_persist_in_need_stats():
    # need_stats 整包被 _save_state 序列化 → tool_weights 免費持久
    ag = _ag()
    ag._bump_tool_weight("competence", "gbrain", rpe=0.3)
    assert "tool_weights" in ag._need_stats["competence"]
