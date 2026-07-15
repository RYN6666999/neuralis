"""
PythonPsiBackend — M1 zero-behavior compatibility adapter over PsiCore.

Wraps an existing `PsiCore` behind the ten PsiBackend v1 methods
(docs/contracts/psi-backend.md §5) plus a transitional B-surface of
explicit properties.  This is M1: it changes NO behavior.  Every call
delegates straight to the wrapped core; there is no second copy of
needs/emotion/affective, no fresh CognitiveBus, no recomputation.

Scope (see the contract):
- M1 only.  Not wired into startup.py; production call sites are NOT
  migrated (that is M2).  The backend is still not swappable.
- Presentation methods (`get_state_label` / `format_state_injection`)
  delegate as-is and PRESERVE QUIRK-1 (label reads raw valence,
  injection reads endorphin valence).  Do not unify the channels here.
- KNOWN-ISSUE-1 (AttentionFocus.SOCIAL) and KNOWN-ISSUE-2 (stop() does
  not join) are preserved unchanged.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from laap.psi_core import NeedType

if TYPE_CHECKING:
    from laap.agi.cognitive_bus import AttentionFocus
    from laap.psi_core import PsiCore


class PythonPsiBackend:
    """Explicit adapter over PsiCore.  No `__getattr__`, no wildcard
    proxying — only the methods and properties named below.  `_core`
    is a controlled private handle, NOT part of the public v1 API."""

    def __init__(self, core: "PsiCore") -> None:
        self._core = core

    # ── PsiBackend v1 — ten methods (contract §5) ──

    def start(self) -> None:
        self._core.start()

    def stop(self) -> None:
        # Delegates as-is.  Does NOT join the worker thread —
        # KNOWN-ISSUE-2 is preserved; M1 is not the place to fix it.
        self._core.stop()

    def process_input(self, text: str, source: str = "user") -> None:
        # M1 compatibility limit: the current PsiCore.process_input has
        # no `source` parameter, so `source` is ACCEPTED but not stored,
        # not audited, and not forwarded to the constitution.  It has
        # zero effect on PSI behavior here.  Real provenance/constitution
        # wiring is future work; do not add a `last_source` field.
        self._core.process_input(text)

    def get_state(self) -> Dict[str, Any]:
        # As-is: no copy, no recompute, no injected schema_version/
        # backend/timestamp fields.
        return self._core.get_state()

    def get_dominant_need(self) -> str:
        return self._core.get_dominant_need()

    def get_drives(self) -> Dict[str, float]:
        return self._core.needs.get_drives()

    def satisfy(self, need: str, amount: float, source: str) -> None:
        # NeedType(need) raises ValueError on an unknown need — that
        # error is preserved, not swallowed.  Constitution accept/reject
        # semantics live in NeedDriveSystem.satisfy and are untouched.
        self._core.needs.satisfy(NeedType(need), amount, source)

    def post_affective_event(self, event: str,
                             intensity: float = 1.0) -> bool:
        # Returns the underlying bool as-is (known event queued -> True,
        # unknown event -> False).  Must not be turned into None.
        return self._core.affective.post_event(event, intensity)

    def get_cognitive_bias(self) -> Dict[str, float]:
        return self._core.affective.compute_cognitive_bias()

    def get_last_input(self) -> str:
        return self._core.last_input

    # ── Presentation methods (contract §6) — delegate as-is ──

    def get_state_label(self) -> str:
        # Delegates to PsiCore.  Preserves QUIRK-1 (raw valence).
        return self._core.get_state_label()

    def format_state_injection(self) -> Dict[str, Any]:
        # Delegates to PsiCore.  Preserves QUIRK-1 (endorphin valence).
        return self._core.format_state_injection()

    # ── Transitional B-surface (contract §12) — explicit properties ──
    # These return the SAME underlying objects (identity preserved) so
    # M2 can migrate call sites one at a time.  Not part of the
    # permanent v1 API.

    @property
    def needs(self):
        return self._core.needs

    @property
    def emotion(self):
        return self._core.emotion

    @property
    def affective(self):
        return self._core.affective

    @property
    def last_input(self) -> str:
        return self._core.last_input

    @last_input.setter
    def last_input(self, value: str) -> None:
        # check scripts write this directly; keep the setter passthrough.
        self._core.last_input = value

    @property
    def attention_focus(self) -> "AttentionFocus":
        return self._core.attention_focus

    @attention_focus.setter
    def attention_focus(self, value: "AttentionFocus") -> None:
        self._core.attention_focus = value
