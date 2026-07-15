"""
Parity tests for PythonPsiBackend (M1 zero-behavior adapter).

Every check proves the adapter delegates to the wrapped PsiCore
without changing behavior.  Design rules (task §8):
- Parity is proven against a REAL PsiCore, never by monkeypatching the
  adapter's own methods.
- Read-parity compares adapter vs the SAME wrapped core (pure reads).
- Mutation-parity applies identical ops to two freshly-built twin cores
  (identical deterministic initial state, no heartbeat) and compares.
- process_input parity uses competence-dominant text so KNOWN-ISSUE-1's
  relatedness/SOCIAL path is never hit.
- Constitution stays off (conftest sets NEURALIS_CONSTITUTION=off), so
  no audit file is written.  No network / gbrain / runtime files.
- No new xfail; the two existing strict xfails in test_psi_contract.py
  are untouched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from laap.agi.cognitive_bus import CognitiveBus, AttentionFocus
from laap.psi_core import PsiCore, NeedType
from laap.psi_backend import PythonPsiBackend

# Competence-dominant input: hits 懂了/完成/解決 keywords.  Keeps
# competence the dominant need, so _update_attention never reaches the
# non-existent AttentionFocus.SOCIAL (KNOWN-ISSUE-1).
SAFE_INPUT = "我懂了，已經完成解決了這個問題"

STATE_SCHEMA_PATH = (Path(__file__).resolve().parents[1]
                     / "docs" / "contracts" / "psi-state.schema.json")


def _fresh_core() -> PsiCore:
    """A stopped PsiCore over its own bus (no heartbeat).  Two of these
    have identical deterministic initial state."""
    return PsiCore(bus=CognitiveBus(agent_name="twin"), interval=1.0)


@pytest.fixture
def adapter(psi: PsiCore) -> PythonPsiBackend:
    """Adapter over the stopped `psi` fixture core."""
    return PythonPsiBackend(psi)


# ── A. Structure ─────────────────────────────────────────────────


class TestStructure:

    def test_constructor_stores_same_core(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        # _core is a controlled private observation point, not public API.
        assert adapter._core is psi

    def test_does_not_copy_subsystems(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.needs is psi.needs
        assert adapter.emotion is psi.emotion
        assert adapter.affective is psi.affective

    def test_no_wildcard_getattr(
            self, adapter: PythonPsiBackend) -> None:
        assert not hasattr(type(adapter), "__getattr__")
        with pytest.raises(AttributeError):
            adapter.some_unknown_attribute  # noqa: B018

    def test_private_core_fields_not_proxied(
            self, adapter: PythonPsiBackend) -> None:
        for name in ("_thread", "_running", "_tick_count"):
            with pytest.raises(AttributeError):
                getattr(adapter, name)


# ── B. Ten-method parity ─────────────────────────────────────────


class TestMethodParity:

    def test_get_state_parity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.get_state() == psi.get_state()

    def test_get_dominant_need_parity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.get_dominant_need() == psi.get_dominant_need()

    def test_get_drives_parity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.get_drives() == psi.needs.get_drives()

    def test_satisfy_parity(self) -> None:
        core_a, core_b = _fresh_core(), _fresh_core()
        adapter = PythonPsiBackend(core_a)
        adapter.satisfy("competence", 0.1, "user")
        core_b.needs.satisfy(NeedType.COMPETENCE, 0.1, "user")
        assert core_a.get_state() == core_b.get_state()

    def test_satisfy_unknown_need_raises(
            self, adapter: PythonPsiBackend) -> None:
        with pytest.raises(ValueError):
            adapter.satisfy("hunger", 0.1, "user")

    def test_post_affective_event_known_returns_true(
            self, adapter: PythonPsiBackend) -> None:
        assert adapter.post_affective_event("user_engagement", 0.5) is True

    def test_post_affective_event_unknown_returns_false(
            self, adapter: PythonPsiBackend) -> None:
        result = adapter.post_affective_event("no_such_event", 0.5)
        assert result is False  # must be False, not None

    def test_get_cognitive_bias_parity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.get_cognitive_bias() == \
            psi.affective.compute_cognitive_bias()

    def test_get_last_input_parity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        psi.process_input(SAFE_INPUT)
        assert adapter.get_last_input() == psi.last_input

    def test_process_input_parity(self) -> None:
        core_a, core_b = _fresh_core(), _fresh_core()
        adapter = PythonPsiBackend(core_a)
        adapter.process_input(SAFE_INPUT)
        core_b.process_input(SAFE_INPUT)
        assert core_a.get_state() == core_b.get_state()
        assert core_a.last_input == core_b.last_input

    def test_process_input_source_does_not_change_behavior(self) -> None:
        core_a, core_b = _fresh_core(), _fresh_core()
        a, b = PythonPsiBackend(core_a), PythonPsiBackend(core_b)
        a.process_input(SAFE_INPUT, source="user")
        b.process_input(SAFE_INPUT, source="agency")
        assert core_a.get_state() == core_b.get_state()
        # source is accepted but discarded by the adapter — it must
        # not leak into state or introduce a last_source field.
        state = core_a.get_state()
        assert "source" not in state
        assert "last_source" not in state
        assert not hasattr(core_a, "last_source")

    def test_get_state_label_parity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.get_state_label() == psi.get_state_label()

    def test_format_state_injection_parity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.format_state_injection() == \
            psi.format_state_injection()


# ── C. B-surface passthrough ─────────────────────────────────────


class TestCompatibilitySurface:

    def test_needs_identity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.needs is psi.needs

    def test_emotion_identity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.emotion is psi.emotion

    def test_affective_identity(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert adapter.affective is psi.affective

    def test_last_input_getter_setter(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        adapter.last_input = "直接寫入"
        assert psi.last_input == "直接寫入"
        psi.last_input = "從 core 改"
        assert adapter.last_input == "從 core 改"

    def test_attention_focus_getter_setter(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        adapter.attention_focus = AttentionFocus.TASK
        assert psi.attention_focus is AttentionFocus.TASK
        psi.attention_focus = AttentionFocus.IDLE
        assert adapter.attention_focus is AttentionFocus.IDLE


# ── D. Lifecycle ─────────────────────────────────────────────────


class TestLifecycle:
    """start()/stop() delegate.  KNOWN-ISSUE-2 (stop does not join) is
    preserved; the adapter adds no join and no third xfail."""

    def test_start_delegates_and_idempotent(
            self, bus: CognitiveBus) -> None:
        core = PsiCore(bus=bus, interval=0.1)
        adapter = PythonPsiBackend(core)
        try:
            adapter.start()
            assert core._running  # private observation point
            t1 = core._thread
            adapter.start()  # idempotent: same thread, no restart
            assert core._thread is t1
        finally:
            adapter.stop()
            if core._thread is not None:
                core._thread.join(timeout=1.0)

    def test_stop_delegates(self, bus: CognitiveBus) -> None:
        core = PsiCore(bus=bus, interval=0.1)
        adapter = PythonPsiBackend(core)
        try:
            adapter.start()
            assert core._running
            adapter.stop()
            # Delegation observable: running flag cleared.  Adapter does
            # NOT join (KNOWN-ISSUE-2 preserved) — no thread assertion.
            assert not core._running
        finally:
            adapter.stop()  # idempotent — safe even if start failed
            if core._thread is not None:
                core._thread.join(timeout=1.0)


# ── E. Schema conformance ────────────────────────────────────────


class TestSchemaConformance:

    @pytest.fixture(scope="class")
    def validator(self) -> Draft202012Validator:
        schema = json.loads(STATE_SCHEMA_PATH.read_text(encoding="utf-8"))
        return Draft202012Validator(schema)

    def test_adapter_state_passes_schema(
            self, adapter: PythonPsiBackend,
            validator: Draft202012Validator) -> None:
        validator.validate(adapter.get_state())
        adapter.process_input(SAFE_INPUT)
        validator.validate(adapter.get_state())

    def test_adapter_adds_no_fields(
            self, psi: PsiCore, adapter: PythonPsiBackend) -> None:
        assert set(adapter.get_state().keys()) == set(psi.get_state().keys())

    def test_adapter_state_json_serializable(
            self, adapter: PythonPsiBackend) -> None:
        json.dumps(adapter.get_state())  # must not raise
