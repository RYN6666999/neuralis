"""
PythonPsiBackend — M1 zero-behavior compatibility adapter over PsiCore.
RustPsiBackend — M3 B-route reader: remaps daemon's native JSON to the
                 Python get_state() dict shape (B-surface contract).

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

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from laap.psi_core import NeedType

if TYPE_CHECKING:
    from laap.agi.cognitive_bus import AttentionFocus
    from laap.psi_core import PsiCore

logger = logging.getLogger("laap.psi_backend")

# Native schema need-order (matches config.rs NeedKind enum).
_NEED_NAMES = ["certainty", "competence", "autonomy", "relatedness", "growth"]

# ── QUIRK-1 constants (label reads raw_valence, injection reads endorphin) ──
_LABEL_VALENCE_THRESHOLD = 0.3

_STATE_LABEL_MAP = {
    "competence": ("confident.helpful", "humble.learning"),
    "relatedness": ("warm.grateful", "lonely.seeking"),
    "certainty": ("curious.asking", "confused.uncertain"),
    "growth": ("eager.exploring", "stuck.impatient"),
    "autonomy": ("assertive.independent", "resistant.doubtful"),
}


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


class RustPsiBackend:
    """M3 B-route reader: remaps psi-daemon's native `neuralis-rust-psi/v1`
    schema to the Python get_state() dict shape.

    Reads from the daemon's atomic-write latest.json every call.  Falls back
    to cached state or a default when the file is missing or stale (>2s).
    Write methods (process_input, satisfy, post_affective_event) are no-ops
    — the real input channel is B2, this is B1 read-only.

    QUIRK-1 preserved:
      - get_state_label()  reads ``emotion.raw_valence`` (affect.pleasure)
      - format_state_injection()  reads ``emotion.valence`` (endorphin)
    """

    def __init__(self, state_file: str | None = None) -> None:
        self._state_file: str = state_file or self._default_state_file()
        self._daemon_process: subprocess.Popen | None = None
        self._cached_state: dict[str, Any] = {}
        self._last_input: str = ""

    # ── internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _default_state_file() -> str:
        base = os.environ.get("LAAP_AGI_DIR", "")
        if base:
            return str(Path(base) / "aris_brain" / "state" / "rust-latest.json")
        return "/tmp/rust-psi-latest.json"

    @staticmethod
    def _daemon_binary() -> str:
        env = os.environ.get("NEURALIS_PSI_DAEMON", "")
        if env:
            return env
        # Workspace target layout: rust/target/release/psi-daemon
        repo = Path(__file__).resolve().parents[1]
        candidates = [
            repo / "rust" / "target" / "release" / "psi-daemon",
            repo / "rust" / "psi-engine" / "target" / "release" / "psi-daemon",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
        return "psi-daemon"  # hope it's on PATH

    def _read_raw(self) -> dict[str, Any] | None:
        """Read and parse the daemon's latest.json.  Returns None on any
        error (missing, corrupt, stale)."""
        try:
            raw = Path(self._state_file).read_text(encoding="utf-8")
            native: dict = json.loads(raw)
            ts = native.get("ts", 0.0)
            if time.time() - ts > 2.0:
                logger.warning("[RustPsiBackend] state stale >2s")
                return None
            return native
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            logger.debug(f"[RustPsiBackend] read error: {e}")
            return None

    def _default_state(self) -> dict[str, Any]:
        """Fallback default matching Python PsiCore initial state."""
        bias = self._compute_biases({"pleasure": 0.0, "arousal": 0.3,
                                     "dominance": 0.5, "social": 0.3, "stress": 0.1})
        return {
            "needs": {
                "certainty":   {"current": 0.6, "target": 0.8, "drive": 0.24},
                "competence":  {"current": 0.4, "target": 0.9, "drive": 0.75},
                "autonomy":    {"current": 0.5, "target": 0.7, "drive": 0.20},
                "relatedness": {"current": 0.5, "target": 0.7, "drive": 0.16},
                "growth":      {"current": 0.5, "target": 0.8, "drive": 0.39},
            },
            "dominant_need": "competence",
            "dominant_drive": 0.75,
            "emotion": {
                "valence": 0.0, "arousal": 0.5, "dominance": 0.5, "raw_valence": 0.0,
            },
            "attention": "IDLE",
            "tick": 0,
            "affective": {
                "mood": "neutral",
                "dims": {"pleasure": 0.0, "arousal": 0.3, "dominance": 0.5,
                         "social": 0.3, "stress": 0.1},
                "biases": bias,
                "events_total": 0,
            },
        }

    @staticmethod
    def _compute_biases(affect: dict[str, float]) -> dict[str, float]:
        """Mimic AffectiveState.compute_cognitive_bias() from 5D affect."""
        v = affect.get("pleasure", 0.0)
        a = affect.get("arousal", 0.3)
        d = affect.get("dominance", 0.5)
        st = affect.get("stress", 0.1)
        so = affect.get("social", 0.3)
        raw = {
            "optimism": 0.3 * v,
            "risk_seeking": 0.2 * a - 0.15 * st,
            "attention_narrowing": 0.4 * a + 0.3 * st,
            "confirmation_bias": 0.25 * abs(v),
            "overconfidence": 0.3 * d,
            "temporal_discounting": 0.25 * st + 0.15 * a,
            "social_proximity": 0.3 * so,
            "creativity": 0.2 * v - 0.15 * st + 0.1 * a,
        }
        return {k: round(max(-0.8, min(0.8, v)), 3) for k, v in raw.items()}

    # ── remap: native schema → Python get_state() dict ────────────────

    def _remap(self, native: dict) -> dict[str, Any]:
        needs_raw: dict = native.get("needs", {})
        drives_raw: dict = native.get("drives", {})
        affect_raw: dict = native.get("affect", {})
        endorphin: float = native.get("endorphin", 0.0)

        # needs: {name: {current, target, drive}}
        # Rust schema has no target; estimate from drive formula:
        #   drive = max(0, target - current) * importance
        # We can't know importance, so derive target ≈ current + drive / 1.0.
        needs = {}
        for name in _NEED_NAMES:
            cur = needs_raw.get(name, 0.5)
            drv = drives_raw.get(name, 0.0)
            # heuristic: target ≈ current + drive/importance, importance≈1.0
            tgt = min(1.0, max(cur, cur + drv * 1.2))
            needs[name] = {
                "current": round(cur, 3),
                "target": round(tgt, 3),
                "drive": round(drv, 3),
            }

        # dominant need: argmax of drives
        dominant = "none"
        dom_drive = -1.0
        for name in _NEED_NAMES:
            d = drives_raw.get(name, 0.0)
            if d > dom_drive:
                dom_drive = d
                dominant = name

        # emotion: QUIRK-1 — "valence" = endorphin, "raw_valence" = pleasure
        emotion = {
            "valence": round(endorphin, 3),
            "arousal": round(affect_raw.get("arousal", 0.5), 3),
            "dominance": round(affect_raw.get("dominance", 0.5), 3),
            "raw_valence": round(affect_raw.get("pleasure", 0.0), 3),
        }

        # attention: uppercase (Python convention); SOCIAL not in Rust vocab
        att = str(native.get("attention", "idle")).upper()
        if att == "IDLE":
            pass
        elif att not in ("TASK", "LEARNING", "PLANNING"):
            att = "IDLE"

        # affective: 5D dims + biases
        dims = {
            "pleasure": round(affect_raw.get("pleasure", 0.0), 3),
            "arousal": round(affect_raw.get("arousal", 0.3), 3),
            "dominance": round(affect_raw.get("dominance", 0.5), 3),
            "social": round(affect_raw.get("social", 0.3), 3),
            "stress": round(affect_raw.get("stress", 0.1), 3),
        }
        affective = {
            "mood": "neutral",
            "dims": dims,
            "biases": self._compute_biases(affect_raw),
            "events_total": 0,
        }

        return {
            "needs": needs,
            "dominant_need": dominant,
            "dominant_drive": round(dom_drive, 3) if dom_drive >= 0 else 0.0,
            "emotion": emotion,
            "attention": att,
            "tick": native.get("tick", 0),
            "affective": affective,
        }

    # ── PsiBackend v1 — ten methods ───────────────────────────────────

    def start(self) -> None:
        """Spawn psi-daemon if not already running."""
        if self._daemon_process is not None:
            return
        binary = self._daemon_binary()
        if not Path(binary).is_file():
            logger.warning(f"[RustPsiBackend] daemon not found: {binary}")
            return
        seed = os.environ.get("NEURALIS_PSI_SEED", "0")
        args = [binary, "--state-file", self._state_file,
                "--write-ms", "100", "--seed", seed]
        logger.info(f"[RustPsiBackend] spawning daemon: {' '.join(args)}")
        try:
            self._daemon_process = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.warning(f"[RustPsiBackend] failed to spawn daemon")
            self._daemon_process = None

    def stop(self) -> None:
        if self._daemon_process is not None:
            logger.info("[RustPsiBackend] stopping daemon")
            self._daemon_process.terminate()
            try:
                self._daemon_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._daemon_process.kill()
                self._daemon_process.wait()
            self._daemon_process = None

    def process_input(self, text: str, source: str = "user") -> None:
        """B1: no-op.  B2 will route to the daemon's event channel."""
        self._last_input = text

    def get_state(self) -> dict[str, Any]:
        raw = self._read_raw()
        if raw is not None:
            self._cached_state = self._remap(raw)
            return self._cached_state
        # Fallback: use cached, then default
        if self._cached_state:
            logger.debug("[RustPsiBackend] using cached state (degraded)")
            return self._cached_state
        logger.debug("[RustPsiBackend] using default state (no daemon)")
        return self._default_state()

    def get_dominant_need(self) -> str:
        return self.get_state().get("dominant_need", "none")

    def get_drives(self) -> dict[str, float]:
        state = self.get_state()
        return {k: v["drive"] for k, v in state.get("needs", {}).items()}

    def satisfy(self, need: str, amount: float, source: str) -> None:
        """B1: no-op.  B2 will route to the daemon's event channel."""
        pass

    def post_affective_event(self, event: str, intensity: float = 1.0) -> bool:
        """B1: no-op.  B2 will route to the daemon's event channel."""
        return True

    def get_cognitive_bias(self) -> dict[str, float]:
        return self.get_state().get("affective", {}).get("biases", {})

    def get_last_input(self) -> str:
        return self._last_input

    # ── Presentation methods (pure functions over get_state() dict) ────

    def get_state_label(self) -> str:
        """Pure function over get_state() dict.  Preserves QUIRK-1:
        reads raw_valence (affect.pleasure) for the label."""
        state = self.get_state()
        dominant = state.get("dominant_need", "none")
        valence = state["emotion"].get("raw_valence", 0.0)
        positive = valence >= _LABEL_VALENCE_THRESHOLD
        pair = _STATE_LABEL_MAP.get(dominant)
        if pair is None:
            return "neutral.present"
        return pair[0] if positive else pair[1]

    def format_state_injection(self) -> dict[str, Any]:
        """Pure function over get_state() dict.  Preserves QUIRK-1:
        reads ``emotion.valence`` (endorphin) for the injection."""
        state = self.get_state()
        emotion = state.get("emotion", {})
        valence = emotion.get("valence", 0.0)      # endorphin (QUIRK-1)
        arousal = emotion.get("arousal", 0.5)
        dominant = state.get("dominant_need", "none")
        drive = state.get("dominant_drive", 0.0)

        label = self.get_state_label()

        # state_snippet
        mood_parts = []
        if valence > 0.3:
            mood_parts.append("positive" if arousal > 0.6 else "calm")
        elif valence < -0.3:
            mood_parts.append("uneasy" if arousal > 0.6 else "subdued")
        else:
            mood_parts.append("balanced")
        snippet = (f"I'm feeling {', '.join(mood_parts)} — "
                   f"{dominant} drive is at {drive:.2f}. "
                   f"Valence {valence:+.2f}, arousal {arousal:.2f}.")

        tuple_data = {
            "dominant_need": dominant,
            "dominant_drive": round(drive, 3),
            "valence": round(valence, 3),
            "arousal": round(arousal, 3),
            "attention": state.get("attention", "IDLE"),
        }

        return {
            "state_label": label,
            "state_snippet": snippet,
            "state_tuple": tuple_data,
        }

    # ── B-surface properties (raise on access; B2 fills them in) ──────

    @property
    def needs(self):
        raise NotImplementedError(
            "RustPsiBackend.needs: direct object access not available "
            "in B1 reader mode.  Use get_state()['needs'] instead.")

    @property
    def emotion(self):
        raise NotImplementedError(
            "RustPsiBackend.emotion: use get_state()['emotion'] instead.")

    @property
    def affective(self):
        raise NotImplementedError(
            "RustPsiBackend.affective: use get_state()['affective'] instead.")

    @property
    def last_input(self) -> str:
        return self._last_input

    @last_input.setter
    def last_input(self, value: str) -> None:
        self._last_input = value

    @property
    def attention_focus(self) -> str:
        """Return attention string; no AttentionFocus enum in B1."""
        return self.get_state().get("attention", "IDLE")

    @attention_focus.setter
    def attention_focus(self, value: str) -> None:
        pass
