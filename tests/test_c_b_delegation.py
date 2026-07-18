"""C-b cache-miss 委派 Scream acceptance — 預設休眠，簽名後才活。"""
import random

from laap.safety_gate import is_tool_allowed
from laap.agency import AgencyLoop


def _agency():
    ag = AgencyLoop.__new__(AgencyLoop)
    ag._recent_queries = []
    ag._exploration_rate = 1.0            # 強制探索，讓 _should_delegate 的隨機門過
    ag._need_stats = {}
    return ag


def test_is_tool_allowed_probe_no_side_effect():
    # scream-task 是 write、未批准 → 探測回 False（不審計不排隊）
    assert is_tool_allowed("gbrain") is True
    assert is_tool_allowed("scream-task") is False


def test_should_delegate_dormant_when_scream_task_unapproved():
    ag = _agency()
    # scream-task 未批准 → C-b 休眠，永不委派（不管探索多高）
    for _ in range(20):
        assert ag._should_delegate("competence") is False, "未簽名應永遠不委派"


def test_should_delegate_active_when_approved(monkeypatch):
    ag = _agency()
    ag._effective_exploration = lambda: 1.0     # 強制探索門過（__new__ 無 psi）
    import laap.safety_gate as sg
    monkeypatch.setattr(sg, "is_tool_allowed", lambda t: True)   # 模擬已簽名
    import laap.cost_ledger as cl
    monkeypatch.setattr(cl, "within_budget", lambda **k: True)
    assert ag._should_delegate("competence") is True, "批准+預算+探索 → 委派"


def test_over_budget_blocks_delegation(monkeypatch):
    ag = _agency()
    import laap.safety_gate as sg
    monkeypatch.setattr(sg, "is_tool_allowed", lambda t: True)
    import laap.cost_ledger as cl
    monkeypatch.setattr(cl, "within_budget", lambda **k: False)   # 超預算
    assert ag._should_delegate("competence") is False, "超成本閘不委派"


def test_delegation_intent_shape(tmp_path):
    ag = _agency()
    intent = ag._form_delegation_intent("competence", "React 效能")
    assert intent[0] == "scream-task"
    assert "React 效能" in intent[1] and "前瞻" in intent[1]
