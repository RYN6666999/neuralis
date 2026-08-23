"""audit 行必須帶來源，否則事後分不出誰寫的。

為什麼有這支測試（2026-08-23）：

`agency-audit.jsonl` 被當成「Aris 的真實決策紀錄」用了很久 —— S_span 的
learning_verdict 直接吃它。實際盤點 1099 筆的結果：

    prompt 含 "test"                 234 筆 (21.3%)
    其中 'test query 作法' 一模一樣   158 筆
    prompt 是 <system-reminder>...    56 筆（某個 agent 的系統提示洩進來）

三種來源混在同一個檔：真實自主迴圈、`scripts/check-agency.py` 的測試流量
（該檔 :42 的註解自己承認「線上 agency loop 也寫入同一個 agency-audit.jsonl」）、
以及來路不明的 harness 洩漏。**而每一行都沒寫是誰寫的，所以事後拆不開。**

那 1099 筆已經救不回來了。這支測試守的是「從今以後每一行都說得出出處」。

設計上刻意只記**機器測得的事實**（pid / proc），不記我猜的分類：
分類是推論，推論會過期，事實不會。要顯式標記就設 NEURALIS_AUDIT_SOURCE，
沒設就不寫那個欄位 —— 寧可缺欄位，不要填一個猜的預設值進去。
"""
from __future__ import annotations

import json
import os
import sys

import pytest

from laap import agency


@pytest.fixture
def audit_file(tmp_path, monkeypatch):
    """把 AUDIT_PATH 導到 tmp，絕不碰真的 agency-audit.jsonl。"""
    p = tmp_path / "agency-audit.jsonl"
    monkeypatch.setattr(agency, "AUDIT_PATH", p)
    return p


def _write(entry: dict) -> dict:
    agency.AgencyLoop._audit(entry)
    return entry


def _read_one(p) -> dict:
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, f"應恰好寫一行，實際 {len(lines)}"
    return json.loads(lines[0])


def test_audit_line_records_pid(audit_file):
    _write({"need": "competence", "tool": "gbrain"})
    assert _read_one(audit_file)["pid"] == os.getpid()


def test_audit_line_records_proc(audit_file):
    """proc = 執行中的腳本檔名。

    task-executor 與 agentos-aris-bridge 是兩個獨立的 launchd 服務、跑同一支
    腳本、寫同一個檔，但 scoring 設定不同（一個開 SCORING_ROUTER_ENABLED=1，
    一個沒開）。光靠 pid 分不出重啟前後，proc 才看得出是哪支在寫。
    """
    _write({"need": "competence", "tool": "gbrain"})
    assert _read_one(audit_file)["proc"] == os.path.basename(sys.argv[0])


def test_explicit_source_is_recorded(audit_file, monkeypatch):
    monkeypatch.setenv("NEURALIS_AUDIT_SOURCE", "test")
    _write({"need": "competence", "tool": "gbrain"})
    assert _read_one(audit_file)["src"] == "test"


def test_absent_source_writes_no_key(audit_file, monkeypatch):
    """沒設就不要寫 —— 缺欄位是誠實的，猜一個預設值是說謊。

    如果這裡預設填 "autonomous"，那 check-agency.py 忘了設環境變數時，
    測試流量就會被標成自主決策 —— 比沒有欄位更糟，因為它看起來可信。
    """
    monkeypatch.delenv("NEURALIS_AUDIT_SOURCE", raising=False)
    _write({"need": "competence", "tool": "gbrain"})
    assert "src" not in _read_one(audit_file)


def test_blank_source_writes_no_key(audit_file, monkeypatch):
    """空字串等同沒設，不要寫出 src:"" 這種既非缺席也非有值的第三態。"""
    monkeypatch.setenv("NEURALIS_AUDIT_SOURCE", "   ")
    _write({"need": "competence", "tool": "gbrain"})
    assert "src" not in _read_one(audit_file)


def test_caller_entry_is_not_mutated(audit_file):
    """_audit 不准改呼叫端的 dict —— 呼叫端可能還要用它做別的事。"""
    entry = {"need": "competence", "tool": "gbrain"}
    before = dict(entry)
    _write(entry)
    assert entry == before


def test_original_fields_survive(audit_file):
    entry = {"need": "competence", "tool": "gbrain", "outcome": 0.7, "ok": True}
    _write(entry)
    got = _read_one(audit_file)
    for k, v in entry.items():
        assert got[k] == v


def test_write_failure_still_does_not_raise(tmp_path, monkeypatch):
    """既有行為不變：審計寫不進去不該炸掉決策迴圈。

    路徑指向一個不存在的目錄 → open("a") 丟 FileNotFoundError。
    """
    monkeypatch.setattr(agency, "AUDIT_PATH", tmp_path / "no-such-dir" / "a.jsonl")
    agency.AgencyLoop._audit({"need": "competence", "tool": "gbrain"})
