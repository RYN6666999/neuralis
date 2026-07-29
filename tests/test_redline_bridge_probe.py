"""_check_bridge_env 的 pgrep 分支。

背景：這個檢查連續誤報 477 次 "no bridge process running"，而 bridge
一直活著。原因有二 ——
  1. UTF-8 locale 下 pgrep 對某些進程 cmdline 解碼失敗（exit 3）
  2. 舊碼把 exit>=2（工具壞了）和 exit 1（真的沒有）都當成 count=0

所以這裡盯三件事：LC_ALL=C 有被帶上、三種 exit code 分開處理。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "safety-redline-alerts.py"
_spec = importlib.util.spec_from_file_location("redline_alerts", _SRC)
redline = importlib.util.module_from_spec(_spec)
# @dataclass 在 exec 期間會回頭查 sys.modules[cls.__module__]，
# 沒先註冊就 AttributeError: 'NoneType' object has no attribute '__dict__'。
sys.modules["redline_alerts"] = redline
_spec.loader.exec_module(redline)


class _Proc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def captured_env(monkeypatch):
    """攔截 subprocess.run，回傳被記錄下來的呼叫參數。"""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["env"] = kw.get("env") or {}
        return seen["result"]

    # 受測碼是在函式內 `import subprocess`，所以要 patch 真正的模組，
    # 不是 redline 的屬性（那個不存在）。
    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_pgrep_runs_under_c_locale(captured_env):
    """LC_ALL=C 沒帶上的話，UTF-8 環境會重現原本的 illegal byte sequence。"""
    captured_env["result"] = _Proc(0, stdout="7576\n")
    redline._check_bridge_env()
    assert captured_env["env"].get("LC_ALL") == "C"
    assert "pgrep" in captured_env["cmd"][0]


def test_found_one_bridge_is_healthy(captured_env):
    captured_env["result"] = _Proc(0, stdout="7576\n")
    r = redline._check_bridge_env()
    assert r.details["bridge_process_count"] == 1
    assert r.details["bridge_probe_failed"] is False
    assert "no bridge process running" not in r.message


def test_exit_1_means_genuinely_absent(captured_env):
    """exit 1 = pgrep 正常運作但沒 match → 這才是真的沒在跑。"""
    captured_env["result"] = _Proc(1, stdout="")
    r = redline._check_bridge_env()
    assert r.details["bridge_process_count"] == 0
    assert r.details["bridge_probe_failed"] is False
    assert "no bridge process running" in r.message


def test_exit_3_is_probe_failure_not_absence(captured_env):
    """回歸測試：477 次誤報的那條路。工具壞了不可以報成 bridge 掛了。"""
    captured_env["result"] = _Proc(
        3, stderr="pgrep: Regular expression evaluation error (illegal byte sequence)")
    r = redline._check_bridge_env()
    assert r.details["bridge_probe_failed"] is True
    assert "no bridge process running" not in r.message
    assert "process state unknown" in r.message


def test_multiple_bridges_still_flagged(captured_env):
    captured_env["result"] = _Proc(0, stdout="7576\n38831\n")
    r = redline._check_bridge_env()
    assert r.details["bridge_process_count"] == 2
    assert "expected 1" in r.message
