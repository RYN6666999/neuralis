"""Guard for the executor supervised (propose) mode — S2 canary prerequisite.

The scream-task-executor is the RCE-surface component headed for the supervised
canary. In propose mode (the default) it must NOT auto-execute: propose the
action, wait for a human approval on the channel, execute only then. Pins the
pure decision logic so the human-in-loop gate can't silently regress to auto.
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "ste", os.path.join(os.path.dirname(__file__), "..", "scripts", "scream-task-executor.py"))
ste = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ste)


def test_default_mode_is_propose():
    # 安全預設：未設 env → propose（不自動執行）
    assert ste._MODE == "propose" or os.environ.get("NEURALIS_EXECUTOR_MODE")


def test_scan_decisions_extracts_all_kinds():
    entries = [
        {"type": "task", "id": "t1", "content": "x"},
        {"type": "proposal", "task_id": "t1"},
        {"type": "approval", "task_id": "t1"},
        {"type": "proposal", "task_id": "t2"},
        {"type": "rejection", "task_id": "t3"},
        {"type": "result"},  # no id → ignored
    ]
    d = ste.scan_decisions(entries)
    assert d["approved"] == {"t1"}
    assert d["proposed"] == {"t1", "t2"}
    assert d["rejected"] == {"t3"}


_EMPTY = {"approved": set(), "rejected": set(), "proposed": set()}


def test_decide_auto_always_executes():
    assert ste.decide("t1", "auto", _EMPTY) == "execute"
    assert ste.decide("t1", "auto", {"approved": set(), "rejected": {"t1"},
                                     "proposed": set()}) == "execute"


def test_decide_propose_unproposed_proposes():
    assert ste.decide("t1", "propose", _EMPTY) == "propose"


def test_decide_propose_proposed_waits():
    d = {"approved": set(), "rejected": set(), "proposed": {"t1"}}
    assert ste.decide("t1", "propose", d) == "wait"


def test_decide_propose_approved_executes():
    d = {"approved": {"t1"}, "rejected": set(), "proposed": {"t1"}}
    assert ste.decide("t1", "propose", d) == "execute"


def test_decide_propose_rejected_skips():
    d = {"approved": set(), "rejected": {"t1"}, "proposed": {"t1"}}
    assert ste.decide("t1", "propose", d) == "skip"


def test_rejection_wins_over_approval():
    # 拒絕優先於批准（防誤批）
    d = {"approved": {"t1"}, "rejected": {"t1"}, "proposed": {"t1"}}
    assert ste.decide("t1", "propose", d) == "skip"


def test_make_proposal_shape():
    p = ste.make_proposal({"id": "t9", "content": "讀取 `/etc/hostname`"})
    assert p["type"] == "proposal" and p["task_id"] == "t9"
    assert p["direction"] == "scream→aris"
    assert "讀取" in p["preview"] and "approval" in p["note"]
