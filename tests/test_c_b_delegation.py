"""C-b cache-miss 委派 Scream acceptance — 專屬開關預設 OFF，不搭舊批准便車。"""
from laap.safety_gate import is_tool_allowed
from laap.agency import AgencyLoop


def _agency():
    ag = AgencyLoop.__new__(AgencyLoop)
    ag._recent_queries = []
    ag._need_stats = {}
    ag._effective_exploration = lambda: 1.0     # 強制探索門過（__new__ 無 psi）
    return ag


def test_dormant_when_delegate_switch_off(monkeypatch):
    """核心安全：NEURALIS_AGENCY_DELEGATE 預設 OFF → 休眠，
    不管 scream-task 是否已批准（不搭舊頻道批准的便車）。"""
    monkeypatch.delenv("NEURALIS_AGENCY_DELEGATE", raising=False)
    import laap.safety_gate as sg
    monkeypatch.setattr(sg, "is_tool_allowed", lambda t: True)   # 就算舊批准在
    ag = _agency()
    for _ in range(10):
        assert ag._should_delegate("competence") is False, "開關 OFF 應永遠休眠"


def test_active_when_switch_on_and_approved(monkeypatch):
    monkeypatch.setenv("NEURALIS_AGENCY_DELEGATE", "on")
    import laap.safety_gate as sg
    monkeypatch.setattr(sg, "is_tool_allowed", lambda t: True)
    import laap.cost_ledger as cl
    monkeypatch.setattr(cl, "within_budget", lambda **k: True)
    assert _agency()._should_delegate("competence") is True, "開關 on + 批准 + 預算 → 委派"


def test_switch_on_but_unapproved_still_dormant(monkeypatch):
    monkeypatch.setenv("NEURALIS_AGENCY_DELEGATE", "on")
    import laap.safety_gate as sg
    monkeypatch.setattr(sg, "is_tool_allowed", lambda t: False)  # scream-task 未批准
    assert _agency()._should_delegate("competence") is False, "未批准仍不委派（雙重閘）"


def test_over_budget_blocks(monkeypatch):
    monkeypatch.setenv("NEURALIS_AGENCY_DELEGATE", "on")
    import laap.safety_gate as sg
    monkeypatch.setattr(sg, "is_tool_allowed", lambda t: True)
    import laap.cost_ledger as cl
    monkeypatch.setattr(cl, "within_budget", lambda **k: False)
    assert _agency()._should_delegate("competence") is False, "超成本閘不委派"


def test_delegation_intent_shape():
    intent = _agency()._form_delegation_intent("competence", "React 效能")
    assert intent[0] == "scream-task"
    assert "React 效能" in intent[1] and "前瞻" in intent[1]


def test_is_tool_allowed_readonly_probe():
    # readonly 工具恆允許；探測無副作用（不審計不排隊）
    assert is_tool_allowed("gbrain") is True
