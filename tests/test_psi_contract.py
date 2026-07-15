"""
Characterization tests for Python PsiCore (neuralis).

These tests record the *current* behaviour of the Python reference
implementation.  They are not a specification of ideal behaviour —
they are a snapshot for detecting regressions and a baseline for
future PSI backend contracts.

Requirements:
- No network access
- No gbrain dependency
- No LAAP API dependency
- Deterministic (random is monkeypatched)
- Constitution is disabled by default (NEURALIS_CONSTITUTION=off)
"""
from __future__ import annotations

import json
import random
import threading
import time
from typing import Any

import pytest

from laap.agi.cognitive_bus import CognitiveBus, AttentionFocus
from laap.psi_core import (
    PsiCore,
    NeedType,
    NeedDriveSystem,
    EmotionGradient,
)

# ── 1. NeedType ──────────────────────────────────────────────────


class TestNeedType:
    """Five needs MUST exist.  Enum declaration order is the
    tie-breaking order used by get_dominant(): certainty > competence
    > autonomy > relatedness > growth."""

    def test_five_needs_exist(self) -> None:
        assert len(NeedType) == 5

    def test_members(self) -> None:
        assert NeedType.CERTAINTY.value == "certainty"
        assert NeedType.COMPETENCE.value == "competence"
        assert NeedType.AUTONOMY.value == "autonomy"
        assert NeedType.RELATEDNESS.value == "relatedness"
        assert NeedType.GROWTH.value == "growth"

    def test_declaration_order_is_tie_breaker(self) -> None:
        """get_dominant() picks the first need when drives are equal.
        Enum declaration order is: CERTAINTY(0), COMPETENCE(1),
        AUTONOMY(2), RELATEDNESS(3), GROWTH(4).  This order is the
        tie-break — it is recorded here, not mandated."""
        names = [m.name for m in NeedType]
        assert names == ["CERTAINTY", "COMPETENCE",
                         "AUTONOMY", "RELATEDNESS", "GROWTH"]


# ── 2. NeedDriveSystem initial state ─────────────────────────────


class TestNeedDriveSystemInitialState:
    """Every need has a value, target, baseline, importance,
    decay_rate, and volatility.  All values are in [0, 1]."""

    def test_all_needs_have_values(self, needs: NeedDriveSystem) -> None:
        for nt in NeedType:
            v = needs.values[nt]
            assert 0.0 <= v <= 1.0, f"{nt.name}: {v}"

    def test_all_needs_have_targets(self, needs: NeedDriveSystem) -> None:
        for nt in NeedType:
            v = needs.targets[nt]
            assert 0.0 <= v <= 1.0, f"{nt.name}: {v}"

    def test_all_needs_have_baselines(self, needs: NeedDriveSystem) -> None:
        for nt in NeedType:
            v = needs.baselines[nt]
            assert 0.0 <= v <= 1.0, f"{nt.name}: {v}"

    def test_baseline_equals_initial_value(self, needs: NeedDriveSystem) -> None:
        """Baseline is set to the initial value at construction time."""
        for nt in NeedType:
            assert needs.baselines[nt] == needs.values[nt], nt.name

    def test_all_needs_have_importances(self, needs: NeedDriveSystem) -> None:
        for nt in NeedType:
            v = needs.importances[nt]
            assert v > 0, f"{nt.name}: {v}"

    def test_all_needs_have_decay_rates(self, needs: NeedDriveSystem) -> None:
        for nt in NeedType:
            v = needs.decay_rates[nt]
            assert v > 0, f"{nt.name}: {v}"

    def test_all_needs_have_volatilities(self, needs: NeedDriveSystem) -> None:
        for nt in NeedType:
            v = needs.volatilities[nt]
            assert v >= 0, f"{nt.name}: {v}"

    def test_initial_values(self, needs: NeedDriveSystem) -> None:
        """Record the exact initial values.  Changing these is a
        breaking change that must be reflected in the contract."""
        assert needs.values[NeedType.CERTAINTY] == 0.6
        assert needs.values[NeedType.COMPETENCE] == 0.4
        assert needs.values[NeedType.AUTONOMY] == 0.5
        assert needs.values[NeedType.RELATEDNESS] == 0.5
        assert needs.values[NeedType.GROWTH] == 0.5

    def test_initial_targets(self, needs: NeedDriveSystem) -> None:
        assert needs.targets[NeedType.CERTAINTY] == 0.8
        assert needs.targets[NeedType.COMPETENCE] == 0.9
        assert needs.targets[NeedType.AUTONOMY] == 0.7
        assert needs.targets[NeedType.RELATEDNESS] == 0.7
        assert needs.targets[NeedType.GROWTH] == 0.8

    def test_initial_importances(self, needs: NeedDriveSystem) -> None:
        assert needs.importances[NeedType.CERTAINTY] == 1.2
        assert needs.importances[NeedType.COMPETENCE] == 1.5
        assert needs.importances[NeedType.AUTONOMY] == 1.0
        assert needs.importances[NeedType.RELATEDNESS] == 0.8
        assert needs.importances[NeedType.GROWTH] == 1.3

    def test_initial_decay_rates(self, needs: NeedDriveSystem) -> None:
        assert needs.decay_rates[NeedType.CERTAINTY] == 0.008
        assert needs.decay_rates[NeedType.COMPETENCE] == 0.012
        assert needs.decay_rates[NeedType.AUTONOMY] == 0.005
        assert needs.decay_rates[NeedType.RELATEDNESS] == 0.010
        assert needs.decay_rates[NeedType.GROWTH] == 0.006

    def test_initial_volatilities(self, needs: NeedDriveSystem) -> None:
        assert needs.volatilities[NeedType.CERTAINTY] == 0.004
        assert needs.volatilities[NeedType.COMPETENCE] == 0.006
        assert needs.volatilities[NeedType.AUTONOMY] == 0.003
        assert needs.volatilities[NeedType.RELATEDNESS] == 0.005
        assert needs.volatilities[NeedType.GROWTH] == 0.004

    def test_get_satisfactions_has_all_fields(
            self, needs: NeedDriveSystem) -> None:
        s = needs.get_satisfactions()
        for nt in NeedType:
            assert nt.value in s, f"Missing {nt.value}"
            assert 0.0 <= s[nt.value] <= 1.0

    def test_get_drives_has_all_fields(
            self, needs: NeedDriveSystem) -> None:
        d = needs.get_drives()
        for nt in NeedType:
            assert nt.value in d, f"Missing {nt.value}"
            assert d[nt.value] >= 0.0

    def test_to_dict_format(self, needs: NeedDriveSystem) -> None:
        d = needs.to_dict()
        for nt in NeedType:
            entry = d[nt.value]
            assert "current" in entry
            assert "target" in entry
            assert "drive" in entry
            assert entry["drive"] >= 0.0


# ── 3. Drive calculation ────────────────────────────────────────


class TestDriveCalculation:
    """drive = max(0, target - current) * importance."""

    def test_drive_positive_when_current_below_target(
            self, needs: NeedDriveSystem) -> None:
        needs.values[NeedType.COMPETENCE] = 0.3
        drive = needs.compute_drive(NeedType.COMPETENCE)
        expected = (0.9 - 0.3) * 1.5
        assert drive == pytest.approx(expected)

    def test_drive_zero_when_current_equals_target(
            self, needs: NeedDriveSystem) -> None:
        needs.values[NeedType.COMPETENCE] = needs.targets[NeedType.COMPETENCE]
        drive = needs.compute_drive(NeedType.COMPETENCE)
        assert drive == pytest.approx(0.0)

    def test_drive_zero_when_current_exceeds_target(
            self, needs: NeedDriveSystem) -> None:
        needs.values[NeedType.COMPETENCE] = 1.0
        drive = needs.compute_drive(NeedType.COMPETENCE)
        assert drive == pytest.approx(0.0)

    def test_initial_dominant_need(self, needs: NeedDriveSystem) -> None:
        """At initial state, competence has the highest drive
        because its deficit is largest."""
        nt, drive = needs.get_dominant()
        assert nt == NeedType.COMPETENCE
        # competence: (0.9 - 0.4) * 1.5 = 0.75
        assert drive == pytest.approx(0.75)

    def test_initial_drive_values(self, needs: NeedDriveSystem) -> None:
        drives = needs.get_drives()
        assert drives["certainty"] == pytest.approx((0.8 - 0.6) * 1.2)
        assert drives["competence"] == pytest.approx((0.9 - 0.4) * 1.5)
        assert drives["autonomy"] == pytest.approx((0.7 - 0.5) * 1.0)
        assert drives["relatedness"] == pytest.approx((0.7 - 0.5) * 0.8)
        assert drives["growth"] == pytest.approx((0.8 - 0.5) * 1.3)

    def test_all_drives_non_negative(self, needs: NeedDriveSystem) -> None:
        for nt in NeedType:
            drive = needs.compute_drive(nt)
            assert drive >= 0.0


# ── 4. Tick / relaxation ────────────────────────────────────────


class TestTick:
    """Tick behaviour with monkeypatched random.gauss."""

    @pytest.fixture(autouse=True)
    def _no_noise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)

    def test_value_stays_at_baseline_with_no_noise(
            self, needs: NeedDriveSystem) -> None:
        """At baseline, no-noise tick should not drift."""
        for nt in NeedType:
            needs.values[nt] = needs.baselines[nt]
        before = {nt: needs.values[nt] for nt in NeedType}
        for _ in range(5):
            needs.tick(dt=1.0, valence=0.0)
        for nt in NeedType:
            assert needs.values[nt] == pytest.approx(before[nt], abs=1e-9)

    def test_above_baseline_relaxes_down(
            self, needs: NeedDriveSystem) -> None:
        needs.values[NeedType.COMPETENCE] = 0.9
        for _ in range(10):
            needs.tick(dt=1.0, valence=0.0)
        # Should have moved toward baseline (0.4)
        assert needs.values[NeedType.COMPETENCE] < 0.9

    def test_below_baseline_relaxes_up(
            self, needs: NeedDriveSystem) -> None:
        needs.values[NeedType.COMPETENCE] = 0.1
        for _ in range(10):
            needs.tick(dt=1.0, valence=0.0)
        # Should have moved toward baseline (0.4)
        assert needs.values[NeedType.COMPETENCE] > 0.1

    def test_values_always_clamped_01(
            self, needs: NeedDriveSystem, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(random, "gauss",
                            lambda mu, sigma: 10.0)  # huge noise
        for _ in range(100):
            needs.tick(dt=1.0, valence=0.0)
        for nt in NeedType:
            assert 0.0 <= needs.values[nt] <= 1.0

    def test_dt_zero_no_change(
            self, needs: NeedDriveSystem) -> None:
        before = {nt: needs.values[nt] for nt in NeedType}
        needs.tick(dt=0.0, valence=0.0)
        for nt in NeedType:
            assert needs.values[nt] == pytest.approx(before[nt], abs=1e-9)

    def test_positive_valence_slows_decay(
            self, needs: NeedDriveSystem) -> None:
        """valence > 0.3 → sero_factor = 0.7 → decay is slower."""
        needs.values[NeedType.CERTAINTY] = 1.0  # above baseline
        v1 = needs.values[NeedType.CERTAINTY]
        needs.tick(dt=1.0, valence=0.5)  # positive
        v2 = needs.values[NeedType.CERTAINTY]
        # Reset and try with neutral valence
        needs.values[NeedType.CERTAINTY] = 1.0
        needs.tick(dt=1.0, valence=0.0)  # neutral
        v3 = needs.values[NeedType.CERTAINTY]
        # Positive valence decays slower (smaller drop)
        drop_positive = v1 - v2
        drop_neutral = v1 - v3
        assert drop_positive < drop_neutral

    def test_negative_valence_speeds_decay(
            self, needs: NeedDriveSystem) -> None:
        """valence < -0.3 → sero_factor = 1.3 → decay is faster."""
        needs.values[NeedType.CERTAINTY] = 1.0
        v1 = needs.values[NeedType.CERTAINTY]
        needs.tick(dt=1.0, valence=-0.5)  # negative
        v2 = needs.values[NeedType.CERTAINTY]
        needs.values[NeedType.CERTAINTY] = 1.0
        needs.tick(dt=1.0, valence=0.0)  # neutral
        v3 = needs.values[NeedType.CERTAINTY]
        drop_negative = v1 - v2
        drop_neutral = v1 - v3
        assert drop_negative > drop_neutral





# ── 5. Satisfy / Constitution ───────────────────────────────────


class TestSatisfy:
    """With constitution disabled (NEURALIS_CONSTITUTION=off),
    satisfy should adjust the value directly within [0, 1]."""

    def test_positive_delta_increases(
            self, needs: NeedDriveSystem) -> None:
        v0 = needs.values[NeedType.COMPETENCE]
        needs.satisfy(NeedType.COMPETENCE, 0.1)
        v1 = needs.values[NeedType.COMPETENCE]
        assert v1 == pytest.approx(v0 + 0.1)

    def test_negative_delta_decreases(
            self, needs: NeedDriveSystem) -> None:
        v0 = needs.values[NeedType.COMPETENCE]
        needs.satisfy(NeedType.COMPETENCE, -0.1)
        v1 = needs.values[NeedType.COMPETENCE]
        assert v1 == pytest.approx(v0 - 0.1)

    def test_clamped_to_zero(
            self, needs: NeedDriveSystem) -> None:
        needs.values[NeedType.COMPETENCE] = 0.0
        needs.satisfy(NeedType.COMPETENCE, -0.5)
        assert needs.values[NeedType.COMPETENCE] == pytest.approx(0.0)

    def test_clamped_to_one(
            self, needs: NeedDriveSystem) -> None:
        needs.values[NeedType.COMPETENCE] = 0.9
        needs.satisfy(NeedType.COMPETENCE, 0.5)
        assert needs.values[NeedType.COMPETENCE] == pytest.approx(1.0)

    def test_satisfy_all_applies_all(
            self, needs: NeedDriveSystem) -> None:
        v0 = {nt: needs.values[nt] for nt in NeedType}
        amounts = {
            NeedType.CERTAINTY: 0.1,
            NeedType.COMPETENCE: 0.2,
            NeedType.AUTONOMY: 0.0,
            NeedType.RELATEDNESS: 0.05,
            NeedType.GROWTH: 0.15,
        }
        needs.satisfy_all(amounts)
        for nt, delta in amounts.items():
            assert needs.values[nt] == pytest.approx(v0[nt] + delta)

    def test_satisfy_accepts_source_when_constitution_disabled(
            self, needs: NeedDriveSystem) -> None:
        """With constitution disabled, source parameter is accepted
        without error.  This does NOT verify that source is passed
        to the constitution — that requires a separate mock."""
        v0 = needs.values[NeedType.RELATEDNESS]
        needs.satisfy(NeedType.RELATEDNESS, 0.1, source="test_source")
        assert needs.values[NeedType.RELATEDNESS] == pytest.approx(v0 + 0.1)


class TestConstitutionIsolation:
    """Constitution is a global singleton that writes to disk.
    We test with NEURALIS_CONSTITUTION=off (so the singleton is a
    no-op) and verify that no audit log entry is written."""

    def test_default_singleton_is_noop(self) -> None:
        """With NEURALIS_CONSTITUTION=off, guard_need returns delta."""
        from laap.constitution import get_constitution
        c = get_constitution()
        allowed = c.guard_need("competence", 0.5, 0.4, "user")
        assert allowed == pytest.approx(0.4)

    def test_psi_satisfy_does_not_write_audit(
            self, psi: PsiCore) -> None:
        """With constitution off, satisfying should not create
        audit files."""
        import os
        from pathlib import Path
        audit_path = Path("constitution-audit.jsonl")
        before = audit_path.stat().st_size if audit_path.exists() else 0
        psi.needs.satisfy(NeedType.COMPETENCE, 0.1)
        after = audit_path.stat().st_size if audit_path.exists() else 0
        assert after == before, "Constitution audit log was written"


# ── 6. EmotionGradient ──────────────────────────────────────────


class TestEmotionGradient:
    """EmotionGradient: valence, arousal, dominance from needs."""

    def test_initial_to_dict(self, emotion: EmotionGradient) -> None:
        d = emotion.to_dict()
        assert "valence" in d
        assert "arousal" in d
        assert "dominance" in d
        assert "raw_valence" in d

    def test_initial_values_in_range(self, emotion: EmotionGradient) -> None:
        d = emotion.to_dict()
        assert -1.0 <= d["valence"] <= 1.0
        assert 0.0 <= d["arousal"] <= 1.0
        assert 0.0 <= d["dominance"] <= 1.0
        assert -1.0 <= d["raw_valence"] <= 1.0

    def test_initial_equilibrium(self, emotion: EmotionGradient) -> None:
        """At initial need state, all needs are around 0.4-0.6,
        so valence should be near 0."""
        d = emotion.to_dict()
        assert d["valence"] == pytest.approx(0.0, abs=0.01)
        assert d["arousal"] == pytest.approx(0.5, abs=0.01)
        assert d["dominance"] == pytest.approx(0.5, abs=0.01)
        assert d["raw_valence"] == pytest.approx(0.0, abs=0.01)

    def test_update_all_satisfied_raises_valence(
            self, emotion: EmotionGradient) -> None:
        sats = {nt.value: 0.9 for nt in NeedType}
        emotion.update(sats)
        d = emotion.to_dict()
        assert d["valence"] > 0.3

    def test_update_all_unsatisfied_lowers_raw_valence(
            self, emotion: EmotionGradient) -> None:
        """With all needs at 0.1, raw_valence should be negative.
        (The reported valence is endorphin-smoothed and may lag.)"""
        sats = {nt.value: 0.1 for nt in NeedType}
        emotion.update(sats)
        d = emotion.to_dict()
        # avg=0.1 → v_target = 2*0.1-1 = -0.8 → raw_valence negative
        assert d["raw_valence"] < -0.3
        # valence (endorphin-smoothed) should also be negative
        # but may be higher than raw due to endorphin buffer
        assert d["valence"] < 0.0

    def test_endorphin_valence_slows_negative_drops(
            self, emotion: EmotionGradient) -> None:
        """Endorphin valence follows raw upward quickly but
        lags behind on sharp drops."""
        happy = {nt.value: 0.9 for nt in NeedType}
        emotion.update(happy)
        d1 = emotion.to_dict()
        # Now crash to negative
        sad = {nt.value: 0.1 for nt in NeedType}
        for _ in range(5):
            emotion.update(sad)
        d2 = emotion.to_dict()
        # After 5 updates, endorphin should still be above raw
        assert d2["valence"] > d2["raw_valence"], \
            f"endorphin {d2['valence']} should be > raw {d2['raw_valence']}"

    def test_update_reproducible(
            self, emotion: EmotionGradient) -> None:
        """Same satisfaction dict produces the same update."""
        sats = {nt.value: 0.7 for nt in NeedType}
        emotion.update(sats)
        d1 = emotion.to_dict()
        # Create a fresh gradient and apply same
        e2 = EmotionGradient()
        e2.update(sats)
        d2 = e2.to_dict()
        for key in ("valence", "arousal", "dominance", "raw_valence"):
            assert d1[key] == pytest.approx(d2[key], abs=1e-9), key

    def test_arousal_remains_bounded_after_large_change(
            self, emotion: EmotionGradient) -> None:
        """After large satisfaction swings, arousal stays in [0, 1]."""
        sats = {nt.value: 0.9 for nt in NeedType}
        emotion.update(sats)
        sats2 = {nt.value: 0.1 for nt in NeedType}
        emotion.update(sats2)
        d = emotion.to_dict()
        assert 0.0 <= d["arousal"] <= 1.0


# ── 7. PsiCore public state ─────────────────────────────────────


class TestPsiCoreState:
    """PsiCore.get_state() output format.

    Note: needs/emotion/affective are accessed via the current
    compatibility surface on PsiCore.  A future backend contract
    may expose these differently — this test records the current
    Python reference behaviour, not a permanent API contract."""

    def test_get_state_returns_all_required_fields(
            self, psi: PsiCore) -> None:
        state = psi.get_state()
        assert "needs" in state
        assert "dominant_need" in state
        assert "dominant_drive" in state
        assert "emotion" in state
        assert "attention" in state
        assert "tick" in state

    def test_get_state_needs_structure(
            self, psi: PsiCore) -> None:
        needs = psi.get_state()["needs"]
        for nt in NeedType:
            assert nt.value in needs
            entry = needs[nt.value]
            assert "current" in entry
            assert "target" in entry
            assert "drive" in entry

    def test_get_state_emotion_structure(
            self, psi: PsiCore) -> None:
        emo = psi.get_state()["emotion"]
        assert "valence" in emo
        assert "arousal" in emo
        assert "dominance" in emo
        assert "raw_valence" in emo

    def test_get_state_serializable(
            self, psi: PsiCore) -> None:
        """Must be JSON-serializable."""
        state = psi.get_state()
        json.dumps(state)
        # Should not raise

    def test_get_dominant_need_returns_string(
            self, psi: PsiCore) -> None:
        need = psi.get_dominant_need()
        assert isinstance(need, str)
        assert need in ("certainty", "competence", "autonomy",
                        "relatedness", "growth", "none")

    def test_get_state_label_returns_string(
            self, psi: PsiCore) -> None:
        label = psi.get_state_label()
        assert isinstance(label, str)
        assert "." in label  # e.g. "humble.learning"

    def test_format_state_injection_structure(
            self, psi: PsiCore) -> None:
        inj = psi.format_state_injection()
        assert "state_label" in inj
        assert "state_snippet" in inj
        assert "state_tuple" in inj
        assert isinstance(inj["state_label"], str)
        assert isinstance(inj["state_snippet"], str)
        assert isinstance(inj["state_tuple"], dict)
        assert "dominant_need" in inj["state_tuple"]
        assert "dominant_drive" in inj["state_tuple"]
        assert "valence" in inj["state_tuple"]
        assert "arousal" in inj["state_tuple"]
        assert "attention" in inj["state_tuple"]

    def test_repr_returns_string(self, psi: PsiCore) -> None:
        r = repr(psi)
        assert isinstance(r, str)
        assert r.startswith("<PsiCore")

    def test_attention_is_known(self, psi: PsiCore) -> None:
        """Attention must be one of the existing enum values."""
        att = psi.get_state()["attention"]
        known = {"IDLE", "TASK", "LEARNING", "PLANNING"}
        assert att in known, f"Unknown attention: {att}"

    def test_affective_optional_in_state(
            self, psi: PsiCore) -> None:
        state = psi.get_state()
        # Affective is optional (present since PsiCore creates it)
        if "affective" in state:
            assert "mood" in state["affective"]


# ── 8. process_input ────────────────────────────────────────────


class TestProcessInput:
    """process_input updates needs and state.

    Note: psi.needs/psi.emotion/psi.affective are the current Python
    reference compatibility surface.  A future backend may expose
    these differently — this test characterises the current behaviour,
    not a permanent API contract."""

    def test_updates_last_input(
            self, psi: PsiCore) -> None:
        psi.process_input("Hello")
        assert psi.last_input == "Hello"

    def test_competence_keywords_increase_competence(
            self, psi: PsiCore) -> None:
        v0 = psi.needs.values[NeedType.COMPETENCE]
        psi.process_input("我懂了，已經完成解決了這個問題，進步很多")
        v1 = psi.needs.values[NeedType.COMPETENCE]
        assert v1 > v0

    def test_relatedness_always_increased(
            self, psi: PsiCore) -> None:
        """Even without explicit keywords, process_input adds
        +0.02 to relatedness."""
        v0 = psi.needs.values[NeedType.RELATEDNESS]
        psi.process_input("foo bar baz qux")
        v1 = psi.needs.values[NeedType.RELATEDNESS]
        assert v1 == pytest.approx(v0 + 0.02)

    def test_empty_string_does_not_crash(
            self, psi: PsiCore) -> None:
        psi.process_input("")
        state = psi.get_state()
        assert "needs" in state

    def test_no_keywords_does_not_change_most_needs(
            self, psi: PsiCore) -> None:
        """Input with no matching keywords should only change
        relatedness (the unconditional +0.02)."""
        v0 = {nt: psi.needs.values[nt] for nt in NeedType}
        psi.process_input("qwerty asdfgh zxcvbn")
        v1 = {nt: psi.needs.values[nt] for nt in NeedType}
        for nt in NeedType:
            if nt == NeedType.RELATEDNESS:
                assert v1[nt] == pytest.approx(v0[nt] + 0.02)
            else:
                assert v1[nt] == pytest.approx(v0[nt])

    def test_state_readable_after_input(
            self, psi: PsiCore) -> None:
        psi.process_input("測試一下")
        state = psi.get_state()
        json.dumps(state)  # serializable

    # ── KNOWN-ISSUE-1: AttentionFocus.SOCIAL ──

    @pytest.mark.xfail(strict=True,
                       reason="KNOWN-ISSUE-1: AttentionFocus.SOCIAL "
                              "does not exist in enum")
    def test_relatedness_does_not_crash(self) -> None:
        """When relatedness is the dominant need, process_input
        should NOT raise AttributeError.

        Currently _update_attention references AttentionFocus.SOCIAL
        which does not exist in the enum.  The correct behaviour is
        to handle this gracefully.
        """
        bus = CognitiveBus(agent_name="test")
        core = PsiCore(bus=bus, interval=0.1)
        thread = None
        try:
            core.start()
            thread = core._thread
            # Force relatedness to be dominant
            core.needs.values[NeedType.CERTAINTY] = 1.0
            core.needs.values[NeedType.COMPETENCE] = 1.0
            core.needs.values[NeedType.AUTONOMY] = 1.0
            core.needs.values[NeedType.GROWTH] = 1.0
            core.needs.values[NeedType.RELATEDNESS] = 0.0
            # Give tick a moment to settle
            time.sleep(0.3)
            # This should not raise AttributeError
            core.process_input("請你陪我聊聊天，我有點寂寞")
        finally:
            core.stop()
            if thread is not None:
                thread.join(timeout=1.0)


# ── 9. Lifecycle ────────────────────────────────────────────────


class TestLifecycle:
    """PsiCore start/stop behaviour."""

    def test_start_stop(self, bus: CognitiveBus) -> None:
        core = PsiCore(bus=bus, interval=0.1)
        try:
            core.start()
            assert core._running
        finally:
            core.stop()
            if core._thread is not None:
                core._thread.join(timeout=1.0)

    def test_double_start_is_idempotent(self, bus: CognitiveBus) -> None:
        core = PsiCore(bus=bus, interval=0.1)
        try:
            core.start()
            t1 = core._thread
            core.start()  # should be no-op
            assert core._thread is t1
        finally:
            core.stop()
            if core._thread is not None:
                core._thread.join(timeout=1.0)

    def test_stop_before_start(self, bus: CognitiveBus) -> None:
        core = PsiCore(bus=bus, interval=0.1)
        core.stop()  # should not raise
        assert not core._running

    def test_ticks_increment(self, bus: CognitiveBus) -> None:
        """Heartbeat increments _tick_count (private observation point,
        not a public API contract)."""
        core = PsiCore(bus=bus, interval=0.05)
        try:
            core.start()
            time.sleep(0.2)
            assert core._tick_count > 0
        finally:
            core.stop()
            if core._thread is not None:
                core._thread.join(timeout=1.0)

    # ── KNOWN-ISSUE-2: stop does not join thread ──

    @pytest.mark.xfail(
        strict=True,
        reason="KNOWN-ISSUE-2: PsiCore.stop() does not join its worker thread",
    )
    def test_stop_joins_thread(self, bus: CognitiveBus) -> None:
        """After stop() returns, the background thread should no
        longer be alive.  Currently stop() only sets a flag and
        returns immediately — the thread continues until its next
        sleep cycle finishes."""
        # Use a long interval so the thread doesn't naturally
        # exit within our join timeout.
        core = PsiCore(bus=bus, interval=5.0)
        thread = None
        try:
            core.start()
            thread = core._thread
            assert thread is not None
            assert thread.is_alive()
        finally:
            core.stop()
        # Ideal: stop() waits for the thread to finish.
        if thread is not None:
            thread.join(timeout=0.3)
            assert not thread.is_alive()


# ── 10. Thread safety minimal ───────────────────────────────────


class TestThreadSafety:
    """Minimal concurrent access: one writer, one reader."""

    def test_concurrent_read_write(self, bus: CognitiveBus) -> None:
        core = PsiCore(bus=bus, interval=0.05)
        stop_event = threading.Event()
        errors: list[Exception] = []

        def reader() -> None:
            while not stop_event.is_set():
                try:
                    state = core.get_state()
                    needs = state.get("needs", {})
                    for nt in NeedType:
                        if nt.value not in needs:
                            errors.append(
                                KeyError(f"Missing {nt.value} in needs"))
                        else:
                            entry = needs[nt.value]
                            if not (0.0 <= entry["current"] <= 1.0):
                                errors.append(
                                    ValueError(f"Out of range: {entry}"))
                except Exception as e:
                    errors.append(e)

        thread = None
        try:
            core.start()
            thread = threading.Thread(target=reader, daemon=True)
            thread.start()

            for _ in range(20):
                core.process_input("你好")
                core.needs.satisfy(NeedType.COMPETENCE, 0.05)
                time.sleep(0.01)
        finally:
            stop_event.set()
            if thread is not None:
                thread.join(timeout=2.0)
            core.stop()
            if core._thread is not None:
                core._thread.join(timeout=1.0)


# ── Module-level: all imports valid ─────────────────────────────


def test_imports() -> None:
    """All expected symbols are importable."""
    from laap.psi_core import (  # noqa: F811
        PsiCore, NeedType, NeedDriveSystem, EmotionGradient,
    )
    assert PsiCore is not None
    assert NeedType is not None
    assert NeedDriveSystem is not None
    assert EmotionGradient is not None