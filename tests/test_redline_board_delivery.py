"""_deliver_to_board：狀態轉換才寫，寫失敗要出聲。

背景：redline 判定 critical 後只寫 log，沒有任何送達路徑，
bridge_env 連喊 477 次無人知曉。這條邊是補那個洞的。

兩個相反的失敗都要防：
  - 不送達（原本的死法）
  - 每輪都送（477 次洗版，等於另一種沒人看）
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "safety-redline-alerts.py"
_spec = importlib.util.spec_from_file_location("redline_board", _SRC)
redline = importlib.util.module_from_spec(_spec)
sys.modules["redline_board"] = redline          # @dataclass 需要
_spec.loader.exec_module(redline)


def _status(sev, checks=None):
    return {
        "status": sev,
        "checks": checks or [
            {"name": "bridge_env", "severity": sev, "message": "no bridge process running"}
        ],
    }


@pytest.fixture
def board(tmp_path, monkeypatch):
    """導向暫存檔。絕不能碰真的留言板。"""
    b = tmp_path / "board.md"
    b.write_text("# 既有內容\n", encoding="utf-8")
    monkeypatch.setattr(redline, "BOARD_PATH", b)
    monkeypatch.setattr(redline, "DELIVERY_STATE_PATH", tmp_path / "state.json")
    return b


def test_critical_gets_written(board):
    redline._deliver_to_board(_status("critical"))
    txt = board.read_text(encoding="utf-8")
    assert "safety-redline CRITICAL" in txt
    assert "bridge_env" in txt
    assert "no bridge process running" in txt
    assert "# 既有內容" in txt          # append，不是覆寫


def test_repeated_critical_written_once(board):
    for _ in range(10):
        redline._deliver_to_board(_status("critical"))
    assert board.read_text(encoding="utf-8").count("safety-redline CRITICAL") == 1


def test_recovery_written_once(board):
    redline._deliver_to_board(_status("critical"))
    redline._deliver_to_board(_status("ok"))
    redline._deliver_to_board(_status("ok"))
    txt = board.read_text(encoding="utf-8")
    assert txt.count("safety-redline 恢復") == 1


def test_warning_to_ok_does_not_touch_board(board):
    before = board.read_text(encoding="utf-8")
    redline._deliver_to_board(_status("warning"))
    redline._deliver_to_board(_status("ok"))
    assert board.read_text(encoding="utf-8") == before


def test_critical_after_recovery_alerts_again(board):
    redline._deliver_to_board(_status("critical"))
    redline._deliver_to_board(_status("ok"))
    redline._deliver_to_board(_status("critical"))
    assert board.read_text(encoding="utf-8").count("safety-redline CRITICAL") == 2


def test_write_failure_is_loud_and_not_recorded(board, tmp_path, monkeypatch, capsys):
    """送不到必須出聲，而且不可以記成已送達 —— 否則下次轉換就永遠不補送。"""
    monkeypatch.setattr(redline, "BOARD_PATH", tmp_path / "no-such-dir" / "board.md")
    redline._deliver_to_board(_status("critical"))
    assert "留言板寫入失敗" in capsys.readouterr().out
    assert redline._last_delivered() == "unknown"


def test_state_file_records_delivered_status(board, tmp_path):
    redline._deliver_to_board(_status("critical"))
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["status"] == "critical"
