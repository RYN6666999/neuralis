"""
conftest — PsiCore characterization test fixtures.

Isolation notes:
- Constitution writes to constitution-audit.jsonl on disk.
  We set NEURALIS_CONSTITUTION=off before any PsiCore import so the
  default singleton is a no-op. Tests that need constitution use a
  fresh Constitution() instance that writes to a temp path.
- AffectiveState uses unseeded numpy RNG for 1/f noise.  We use
  PersonalityProfile(noise_amplitude=0.0) to disable it.
- random.gauss in NeedDriveSystem.tick() is monkeypatched locally.
- PsiCore.start() spawns a daemon thread.  Tests that start it must
  stop it in a finalizer.
"""
from __future__ import annotations

import os

# Disable constitution BEFORE any laap module is imported.
# The singleton is created on first access; if it's created before
# this env var is set, it will be the production version.
os.environ.setdefault("NEURALIS_CONSTITUTION", "off")

import threading
import time
from typing import Generator

import pytest

from laap.agi.cognitive_bus import CognitiveBus
from laap.psi_core import PsiCore, NeedDriveSystem, EmotionGradient


@pytest.fixture
def bus() -> CognitiveBus:
    """A fresh CognitiveBus for each test."""
    return CognitiveBus(agent_name="test")


@pytest.fixture
def psi(bus: CognitiveBus) -> Generator[PsiCore, None, None]:
    """A PsiCore instance with heartbeat running.

    Starts the background thread and ensures it gets stopped,
    even if the test fails.
    """
    core = PsiCore(bus=bus, interval=0.1)
    core.start()
    yield core
    core.stop()
    # Give the thread a chance to exit before next test
    time.sleep(0.15)


@pytest.fixture
def psi_stopped(bus: CognitiveBus) -> PsiCore:
    """A PsiCore instance that has NOT been started (no heartbeat)."""
    return PsiCore(bus=bus, interval=1.0)


@pytest.fixture
def needs() -> NeedDriveSystem:
    """A fresh NeedDriveSystem."""
    return NeedDriveSystem()


@pytest.fixture
def emotion() -> EmotionGradient:
    """A fresh EmotionGradient."""
    return EmotionGradient()