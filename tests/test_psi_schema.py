"""
Executable contract tests for the PSI backend v1 JSON Schemas.

Validates docs/contracts/psi-state.schema.json and
docs/contracts/psi-input.schema.json (JSON Schema Draft 2020-12)
against the CURRENT Python reference implementation (PsiCore) and
against hand-built negative cases.

Isolation (same rules as test_psi_contract.py / conftest.py):
- PsiCore is never start()ed — no heartbeat thread
- No network, no gbrain, no LAAP API
- Constitution is off (conftest sets NEURALIS_CONSTITUTION=off) — no
  audit writes
- Repo-relative paths only
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from laap.psi_core import PsiCore

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "docs" / "contracts"
STATE_SCHEMA_PATH = CONTRACTS_DIR / "psi-state.schema.json"
INPUT_SCHEMA_PATH = CONTRACTS_DIR / "psi-input.schema.json"

NEED_NAMES = ("certainty", "competence", "autonomy", "relatedness", "growth")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def state_schema() -> dict:
    return _load(STATE_SCHEMA_PATH)


@pytest.fixture(scope="module")
def input_schema() -> dict:
    return _load(INPUT_SCHEMA_PATH)


@pytest.fixture(scope="module")
def state_validator(state_schema: dict) -> Draft202012Validator:
    return Draft202012Validator(state_schema)


@pytest.fixture(scope="module")
def input_validator(input_schema: dict) -> Draft202012Validator:
    return Draft202012Validator(input_schema)


# ── Schema files themselves ──────────────────────────────────────


class TestSchemaFiles:

    def test_schema_files_are_valid_json(self) -> None:
        for path in (STATE_SCHEMA_PATH, INPUT_SCHEMA_PATH):
            assert path.is_file(), f"missing {path.name}"
            json.loads(path.read_text(encoding="utf-8"))  # raises if invalid

    def test_schemas_pass_draft_2020_12_check_schema(
            self, state_schema: dict, input_schema: dict) -> None:
        for schema in (state_schema, input_schema):
            assert schema["$schema"] == \
                "https://json-schema.org/draft/2020-12/schema"
            Draft202012Validator.check_schema(schema)  # raises if invalid


# ── State schema vs current Python reference ─────────────────────


class TestStateSchema:

    def test_current_get_state_passes(
            self, psi: PsiCore,
            state_validator: Draft202012Validator) -> None:
        """The schema MUST accept what the reference implementation
        actually emits — both the initial state and a post-input state.
        (No heartbeat: psi fixture is never started; competence stays
        dominant so KNOWN-ISSUE-1's relatedness path is not hit.)"""
        state_validator.validate(psi.get_state())
        psi.process_input("我懂了，已經完成解決了這個問題")
        state_validator.validate(psi.get_state())

    @pytest.mark.parametrize("need", NEED_NAMES)
    def test_missing_need_fails(
            self, psi: PsiCore, need: str,
            state_validator: Draft202012Validator) -> None:
        state = psi.get_state()
        del state["needs"][need]
        assert not state_validator.is_valid(state), \
            f"schema accepted state missing need '{need}'"

    @pytest.mark.parametrize("bad", [1.5, -0.1])
    def test_need_current_out_of_range_fails(
            self, psi: PsiCore, bad: float,
            state_validator: Draft202012Validator) -> None:
        state = psi.get_state()
        state["needs"]["competence"]["current"] = bad
        assert not state_validator.is_valid(state), \
            f"schema accepted needs.competence.current={bad}"

    @pytest.mark.parametrize("bad", [1.01, -1.01])
    def test_emotion_valence_out_of_range_fails(
            self, psi: PsiCore, bad: float,
            state_validator: Draft202012Validator) -> None:
        state = psi.get_state()
        state["emotion"]["valence"] = bad
        assert not state_validator.is_valid(state), \
            f"schema accepted emotion.valence={bad}"

    def test_unknown_dominant_need_fails(
            self, psi: PsiCore,
            state_validator: Draft202012Validator) -> None:
        state = psi.get_state()
        state["dominant_need"] = "hunger"
        assert not state_validator.is_valid(state)

    def test_attention_social_fails(
            self, psi: PsiCore, state_schema: dict,
            state_validator: Draft202012Validator) -> None:
        """KNOWN-ISSUE-1: AttentionFocus.SOCIAL does not exist in the
        enum; production code that would set it crashes first, so
        SOCIAL never appears in get_state() output.  It is therefore
        deliberately NOT a legal v1 value."""
        assert "SOCIAL" not in \
            state_schema["properties"]["attention"]["enum"]
        state = psi.get_state()
        state["attention"] = "SOCIAL"
        assert not state_validator.is_valid(state)


# ── Input schema ─────────────────────────────────────────────────


class TestInputSchema:

    def test_minimal_input_passes(
            self, input_validator: Draft202012Validator) -> None:
        input_validator.validate({"text": "你好"})
        input_validator.validate({"text": ""})  # empty text is legal

    def test_full_input_passes(
            self, input_validator: Draft202012Validator) -> None:
        input_validator.validate({
            "text": "gbrain 記憶架構",
            "schema_version": "1",
            "source": "agency",
            "timestamp": 1752537600.25,
            "metadata": {"channel": "chat", "turn": 3,
                         "tags": ["a", "b"], "nested": {"ok": True}},
        })

    def test_missing_text_fails(
            self, input_validator: Draft202012Validator) -> None:
        assert not input_validator.is_valid({})
        assert not input_validator.is_valid({"source": "user"})

    @pytest.mark.parametrize("bad", [123, None, ["x"], {"t": "x"}, True])
    def test_text_not_string_fails(
            self, bad: object,
            input_validator: Draft202012Validator) -> None:
        assert not input_validator.is_valid({"text": bad})
