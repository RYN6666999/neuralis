"""
Migration tests for M2 — production PSI call-site migration to PsiBackend v1.

These tests prove that production modules use the v1 adapter interface
instead of direct Python-object surface access.  They do not require
gbrain, LAAP API, or network access.
"""
from __future__ import annotations

import sys
import time
from collections import deque
from typing import Any, Dict

import pytest

from laap.psi_backend import PythonPsiBackend
from laap.psi_core import PsiCore
from laap.agi.cognitive_bus import CognitiveBus


# ── 1. Startup wiring ─────────────────────────────────────────────


class TestStartupWiring:
    """ensure_psi_core() returns PythonPsiBackend wrapping one PsiCore."""

    def test_ensure_returns_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch away the external bus dependency, then verify the
        startup function returns a PythonPsiBackend with finally cleanup."""
        bus = CognitiveBus(agent_name="test")
        monkeypatch.setattr(
            "laap.psi_core.CognitiveBus", lambda *a, **kw: bus)
        from laap.startup import ensure_psi_core

        # Reset the global for test isolation
        monkeypatch.setattr("laap.startup._psi_core", None)
        monkeypatch.setattr("laap.startup._bus", None)

        # Mock the upstream bus import
        import types
        fake_bridge = types.ModuleType("aris_brain.psi_core_bridge")
        fake_bridge.get_global_bus = lambda: bus
        monkeypatch.setitem(sys.modules, "aris_brain.psi_core_bridge", fake_bridge)

        result = None
        # Save original globals for restoration
        from laap.startup import _psi_core as _orig_core, _bus as _orig_bus  # type: ignore[attr-defined]
        try:
            result = ensure_psi_core()
            assert isinstance(result, PythonPsiBackend), \
                f"Expected PythonPsiBackend, got {type(result)}"
            assert isinstance(result._core, PsiCore)
        finally:
            if result is not None:
                result.stop()
                if result._core._thread is not None:
                    # Use a generous timeout because the thread interval is
                    # 1.0s and stop() does not join (KNOWN-ISSUE-2).
                    result._core._thread.join(timeout=2.0)
                    assert not result._core._thread.is_alive()
            # Restore original globals
            import laap.startup as _st_mod
            _st_mod._psi_core = _orig_core
            _st_mod._bus = _orig_bus

    def test_ensure_idempotent_returns_same(self) -> None:
        """Repeated calls return the same adapter instance.
        Self-contained: resets globals and installs its own fake bus."""
        import types
        bus = CognitiveBus(agent_name="test")
        from laap.startup import ensure_psi_core

        # Save original globals for restoration
        import laap.startup as _st
        orig_core, orig_bus = _st._psi_core, _st._bus
        _st._psi_core = None
        _st._bus = None
        fake_bridge = types.ModuleType("aris_brain.psi_core_bridge")
        fake_bridge.get_global_bus = lambda: bus
        # Store original and install fake
        orig = sys.modules.get("aris_brain.psi_core_bridge")
        sys.modules["aris_brain.psi_core_bridge"] = fake_bridge

        a = None
        try:
            a = ensure_psi_core()
            assert isinstance(a, PythonPsiBackend), \
                f"Expected PythonPsiBackend, got {type(a)}"
            assert a is not None
            b = ensure_psi_core()
            assert b is a  # same instance
        finally:
            if a is not None:
                a.stop()
                if a._core._thread is not None:
                    # Use a generous timeout because the thread interval is
                    # 1.0s and stop() does not join (KNOWN-ISSUE-2).
                    a._core._thread.join(timeout=2.0)
                    assert not a._core._thread.is_alive()
            # Restore original globals
            _st._psi_core, _st._bus = orig_core, orig_bus
            # Restore original bridge module
            if orig is not None:
                sys.modules["aris_brain.psi_core_bridge"] = orig
            else:
                sys.modules.pop("aris_brain.psi_core_bridge", None)


# ── 2. Agency with strict fake backend ────────────────────────────


class FakeBackend:
    """Strict fake that exposes only v1 methods.  No needs/emotion/
    affective/last_input properties — this must be the only way
    production code accesses PSI state."""

    def __init__(self) -> None:
        self._drives: Dict[str, float] = {
            "competence": 0.75, "certainty": 0.24,
            "autonomy": 0.20, "relatedness": 0.16, "growth": 0.39}
        self._state: Dict[str, Any] = {
            "needs": {}, "emotion": {"valence": 0.0, "arousal": 0.3},
            "dominant_need": "competence", "dominant_drive": 0.75,
            "attention": "IDLE", "tick": 0}
        self._last_input: str = ""
        self._events: list[tuple[str, float]] = []
        self._satisfy_calls: list[tuple[str, float, str]] = []

    def get_drives(self) -> Dict[str, float]:
        return dict(self._drives)

    def get_state(self) -> Dict[str, Any]:
        return dict(self._state)

    def get_cognitive_bias(self) -> Dict[str, float]:
        return {"risk_seeking": 0.0, "attention_narrowing": 0.0,
                "optimism": 0.0, "confirmation_bias": 0.0,
                "overconfidence": 0.0, "temporal_discounting": 0.0,
                "social_proximity": 0.0, "creativity": 0.0}

    def post_affective_event(self, event: str, intensity: float = 1.0) -> bool:
        self._events.append((event, intensity))
        return True

    def get_last_input(self) -> str:
        return self._last_input

    def satisfy(self, need: str, amount: float, source: str) -> None:
        self._satisfy_calls.append((need, amount, source))


class TestAgencyMigration:
    """AgencyLoop uses v1 methods, not B-surface properties."""

    def test_agency_uses_v1_methods(self) -> None:
        """Verify the migration by checking that AgencyLoop's
        _evaluate and _act paths work with a strict v1-only backend."""
        from laap.agency import AgencyLoop

        fake = FakeBackend()
        # We need a minimal tools mock
        class FakeTools:
            def execute(self, tool, prompt, timeout=30):
                return "[1.0] mock result"

        agency = AgencyLoop.__new__(AgencyLoop)
        agency.psi = fake
        agency.tools = FakeTools()
        agency._action_ts = []
        agency._need_last_action = {}
        agency._recent_queries = []
        agency._seed_snippet = "test seed"
        agency._trust_scores = {"user": 0.3}
        agency._trust_decay_rate = 0.0005
        agency._need_stats = {}
        agency._rpe_buffer = []
        agency._exploration_rate = 0.15
        agency._rpe_total = 0.0
        agency._rpe_count = 0
        agency._last_was_gbrain = False
        agency._self_cycle_count = 0
        agency._cycle_max = 3
        agency._cycle_guard = True
        agency._state_loaded = True  # prevent save-state skip
        agency._checkpoint_counter = 0
        agency.interval = 60.0
        agency.max_per_hour = 6
        agency.drive_threshold = 0.45
        agency.actions_total = 0
        agency.skipped_stale = 0
        # 任務佇列模式（goal-driven execution）— _evaluate 首行就讀 _task_queue，
        # 空佇列 = 走原本的 drive 評估路徑。
        # ⚠️ 這個 fixture 用 __new__ 繞過 __init__，AgencyLoop 每次新增 instance
        # 屬性都要同步補在這裡，否則 _evaluate/_act 撞 AttributeError（本行的由來）。
        agency._task_queue = []
        agency._task_index = 0
        agency._goal_spec = ""
        agency._goal_completed = False
        agency._recent_tools = deque(maxlen=5)
        # S_span（認知光錐 Phase 1）— agency.__init__ L126-132 新增
        agency._last_predicted_value = 0.0
        agency._last_predicted_source = ""
        agency._prediction_confidence = 0.7
        agency.s_span_total = 0
        agency.s_span_count = 0
        agency.s_span_prediction_errors = deque(maxlen=50)

        # Test _effective_interval reads arousal from get_state()
        eff = agency._effective_interval()
        assert isinstance(eff, float)
        assert 0.0 < eff <= 60.0

        # Test _effective_exploration reads biases from get_cognitive_bias()
        eff_exp = agency._effective_exploration()
        assert isinstance(eff_exp, float)
        assert 0.02 <= eff_exp <= 0.5

        # Test _evaluate path: drives from get_drives()
        # Set a low drive threshold to trigger action
        agency.drive_threshold = 0.1
        # Set last_input via get_last_input
        fake._last_input = "test query"
        # Run evaluate — must trigger exactly one _act call
        agency._evaluate()
        # Verify exactly one satisfy() with correct params
        assert len(fake._satisfy_calls) == 1, \
            f"Expected 1 satisfy call, got {len(fake._satisfy_calls)}"
        need, amount, source = fake._satisfy_calls[0]
        assert need == "competence"
        assert amount == 0.2
        assert source == "agency"
        # Verify affective event was posted
        assert len(fake._events) > 0, \
            "Expected at least one affective event after _act"
        event, intensity = fake._events[-1]
        assert event in ("task_success", "task_failure")
        assert 0.0 <= intensity <= 1.0


# ── 3. Consolidation reads arousal from get_state ─────────────────


class TestConsolidationMigration:
    """ConsolidationLoop._asleep() reads arousal through get_state()."""

    def test_asleep_uses_get_state_emotion(self) -> None:
        from laap.consolidation import ConsolidationLoop

        fake = FakeBackend()
        fake._state["emotion"]["arousal"] = 0.1  # low arousal
        loop = ConsolidationLoop.__new__(ConsolidationLoop)
        loop.psi = fake
        loop.idle_s = 0.0
        loop.arousal_max = 0.5
        loop._last_interaction = time.time() - 100  # long idle

        asleep = loop._asleep()
        # Should be True (arousal 0.1 < 0.5, and idle)
        assert asleep is True

        fake._state["emotion"]["arousal"] = 0.9  # high arousal
        asleep = loop._asleep()
        assert asleep is False


# ── 4. Status uses get_state and get_last_input ────────────────────


class TestStatusMigration:
    """Status snapshot uses v1 methods."""

    def test_status_uses_get_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from laap.status import snapshot

        fake = FakeBackend()
        monkeypatch.setattr("laap.startup.get_psi_core", lambda: fake)
        monkeypatch.setattr("laap.startup.get_agency", lambda: None)
        monkeypatch.setattr("laap.startup.get_consolidation", lambda: None)

        # Mock the memory breakdown to avoid gbrain calls
        monkeypatch.setattr("laap.status._memory_breakdown", lambda: {})

        s = snapshot()
        psi = s.get("psi", {})
        assert "dominant_need" in psi
        assert "emotion" in psi
        assert "last_input" in psi
        assert "tick" in psi

    def test_status_no_direct_last_input_property(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        from laap.status import snapshot

        fake = FakeBackend()
        # Ensure there's no `last_input` property on the backend
        assert not hasattr(type(fake), "last_input")
        monkeypatch.setattr("laap.startup.get_psi_core", lambda: fake)
        monkeypatch.setattr("laap.startup.get_agency", lambda: None)
        monkeypatch.setattr("laap.startup.get_consolidation", lambda: None)
        monkeypatch.setattr("laap.status._memory_breakdown", lambda: {})

        s = snapshot()
        assert s["psi"]["last_input"] == ""


# ── 5. Chatflow uses post_affective_event ─────────────────────────


class TestChatflowMigration:
    """_post_tool_outcomes uses post_affective_event()."""

    def test_post_tool_outcomes_uses_v1_method(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        from laap.chatflow import _post_tool_outcomes

        fake = FakeBackend()
        monkeypatch.setattr("laap.startup.get_psi_core", lambda: fake)

        body = {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "let me check"},
                {"role": "tool", "content": "all good, result=42"},
                {"role": "tool", "content": "error: timeout"},
                {"role": "tool", "content": "success"},
            ]
        }

        _post_tool_outcomes(body)
        # Should have posted 3 events (max tail), one of which is failure
        assert len(fake._events) == 3
        # Last tool message "error: timeout" should be failure
        assert fake._events[1][0] == "task_failure"
        assert fake._events[1][1] == 0.5

    def test_post_tool_outcomes_max_three(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        from laap.chatflow import _post_tool_outcomes

        fake = FakeBackend()
        monkeypatch.setattr("laap.startup.get_psi_core", lambda: fake)

        body = {
            "messages": [
                {"role": "tool", "content": "msg1"},
                {"role": "tool", "content": "msg2"},
                {"role": "tool", "content": "msg3"},
                {"role": "tool", "content": "msg4"},
                {"role": "tool", "content": "msg5"},
            ]
        }

        _post_tool_outcomes(body)
        assert len(fake._events) <= 3

    def test_no_tool_messages_does_nothing(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        from laap.chatflow import _post_tool_outcomes

        fake = FakeBackend()
        monkeypatch.setattr("laap.startup.get_psi_core", lambda: fake)

        body = {"messages": [{"role": "user", "content": "hello"}]}
        _post_tool_outcomes(body)
        assert len(fake._events) == 0


# ── 6. memory_store uses get_state for emotion data ────────────────


class TestMemoryStoreMigration:
    """emotion_intensity() reads from get_state()["emotion"]."""

    def test_emotion_intensity_uses_get_state(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        from memory_store import emotion_intensity

        fake = FakeBackend()
        fake._state["emotion"] = {"valence": 0.6, "arousal": 0.5}
        monkeypatch.setattr("laap.startup.get_psi_core", lambda: fake)

        intensity = emotion_intensity()
        assert intensity == pytest.approx(0.6 * 0.5)

    def test_emotion_intensity_fallback_zero(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        from memory_store import emotion_intensity

        monkeypatch.setattr("laap.startup.get_psi_core", lambda: None)
        assert emotion_intensity() == 0.0


# ── 7. Static guard: no B-surface access in production files ──────


class TestStaticGuard:
    """Production files must not access needs/emotion/affective/last_input
    as runtime properties on the PSI object."""

    BANNED_ACCESS_PATTERNS = [
        "self.psi.needs", "psi.needs",
        "self.psi.emotion", "psi.emotion",
        "self.psi.affective", "psi.affective",
        "self.psi.last_input", "psi.last_input",
    ]

    PRODUCTION_FILES = [
        "laap/startup.py",
        "laap/agency.py",
        "laap/consolidation.py",
        "laap/status.py",
        "laap/chatflow.py",
        "memory_store.py",
    ]

    @pytest.mark.parametrize("filepath", PRODUCTION_FILES)
    def test_no_banned_access(self, filepath: str) -> None:
        """None of the BANNED_ACCESS_PATTERNS should appear as
        executable code in production files (comments/docstrings
        are allowed)."""
        import ast
        import re

        with open(filepath, encoding="utf-8") as f:
            source = f.read()

        # Remove comments and docstrings, then check for banned patterns
        try:
            tree = ast.parse(source)
        except SyntaxError:
            pytest.fail(f"Syntax error in {filepath}")

        # Extract all AST node text (excluding comments/docstrings)
        source_lines = source.splitlines()
        for pattern in self.BANNED_ACCESS_PATTERNS:
            # Check every line — if it matches, verify it's not a comment
            for i, line in enumerate(source_lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if pattern in stripped:
                    # Double-check: is this inside a docstring or comment?
                    # If it's code, it will be in the AST
                    pytest.fail(
                        f"{filepath}:{i}: B-surface access `{pattern}` "
                        f"still present in code: {stripped!r}")