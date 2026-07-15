"""
conftest — PsiCore characterization test fixtures.

Isolation notes:
- Constitution writes to constitution-audit.jsonl on disk.
  We set NEURALIS_CONSTITUTION=off BEFORE any laap module is imported,
  so the default singleton is a no-op.  This affects the entire pytest
  process — tests that need real constitution behaviour must create a
  fresh Constitution() instance and pass it explicitly.
- AffectiveState uses unseeded numpy RNG for 1/f noise.  Tests that
  need determinism use PersonalityProfile(noise_amplitude=0.0).
- random.gauss in NeedDriveSystem.tick() is monkeypatched per test.
- PsiCore.start() spawns a daemon thread.  Only tests that need the
  heartbeat start the core explicitly in a try/finally block.
"""
from __future__ import annotations

import os

# Disable constitution BEFORE any laap module is imported.
# This affects the entire pytest process.
os.environ.setdefault("NEURALIS_CONSTITUTION", "off")

import pytest

from laap.agi.cognitive_bus import CognitiveBus
from laap.psi_core import PsiCore, NeedDriveSystem, EmotionGradient


@pytest.fixture
def bus() -> CognitiveBus:
    """A fresh CognitiveBus for each test."""
    return CognitiveBus(agent_name="test")


@pytest.fixture
def psi(bus: CognitiveBus) -> PsiCore:
    """A PsiCore instance that has NOT been started (no heartbeat).
    Tests that need the heartbeat must call core.start() in a
    try/finally block and core.stop() in the finally clause."""
    return PsiCore(bus=bus, interval=1.0)


@pytest.fixture
def needs() -> NeedDriveSystem:
    """A fresh NeedDriveSystem."""
    return NeedDriveSystem()


@pytest.fixture
def emotion() -> EmotionGradient:
    """A fresh EmotionGradient."""
    return EmotionGradient()