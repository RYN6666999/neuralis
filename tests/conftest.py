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

# Stamp every audit line written during a test run as src_service="pytest".
#
# 2026-08-23: agency-audit.jsonl 的 1099 筆裡有 234 筆 (21.3%) 是測試流量
# （158 筆一模一樣的 'test query 作法'），但沒有任何欄位分得出來，所以整份
# 資料拿去算 learning_verdict 時，測試噪音跟真實決策是混在一起的。
# laap/agency.py 的 _PROVENANCE 加了 src_service 還不夠 —— 沒有這一行，
# 測試跑出來的 audit 只會拿到 sys.executable 推出來的 "?agentos-aris-bridge"，
# 也就是**被誤標成一個真的 service**。
# setdefault 而非 setenv：呼叫端已經標了更精確的來源就別蓋掉它。
os.environ.setdefault("NEURALIS_SERVICE", "pytest")

import pytest

from laap.agi.cognitive_bus import CognitiveBus
from laap.psi_core import PsiCore, NeedDriveSystem, EmotionGradient


@pytest.fixture(autouse=True)
def _isolate_failure_trail(tmp_path, monkeypatch):
    """任何測試都不得寫到真的 audit-failures.jsonl。

    2026-08-23：這條是被自己抓到的。`test_failure_trail_never_raises` 沒有
    導向 tmp，於是跑一次全套測試就在 repo 根產生 6 行 `weird_kind` ——
    **而 sentinel 的全部價值就是「存在即異常」**。測試把它變成常態存在，
    等於親手廢掉自己要守護的性質。這跟 `check-agency.py` 污染
    agency-audit.jsonl 是同一個病，只是發生在修那個病的 patch 裡。

    用 autouse 而不是逐個測試加 fixture，理由同 `_audit` 把 provenance 加在
    唯一寫入路徑：**「忘記帶」不可能發生**。逐個加就會有下一個測試忘記。
    """
    from laap import failure_trail
    monkeypatch.setattr(failure_trail, "FAILURE_PATH",
                        tmp_path / "audit-failures.jsonl")
    monkeypatch.setattr(failure_trail, "_counts", {})


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