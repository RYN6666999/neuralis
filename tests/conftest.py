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

# Stamp every audit line written during a test run as src="pytest".
#
# 2026-08-23: agency-audit.jsonl 的 1099 筆裡有 234 筆 (21.3%) 是測試流量
# （158 筆一模一樣的 'test query 作法'），但沒有任何欄位分得出來，所以整份
# 資料拿去算 learning_verdict 時，測試噪音跟真實決策是混在一起的。
# 加了 src 欄位還不夠 —— 沒有這一行，測試跑出來的 audit 仍然不會署名。
# setdefault 而非 setenv：呼叫端已經標了更精確的來源就別蓋掉它。
os.environ.setdefault("NEURALIS_AUDIT_SOURCE", "pytest")

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