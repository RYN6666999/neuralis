"""Guard for laap/error_log.log_abort — the Aris turn-abort observability sink.

Aris turns were aborting mid-way with no durable trace (operator was blind).
log_abort writes a JSONL record per abort. It must (1) capture the context +
traceback and (2) NEVER raise — observability must not become a new failure mode.
"""
import json
from pathlib import Path

from laap import error_log


def test_writes_record_and_makes_parent(tmp_path, monkeypatch):
    log = tmp_path / "sub" / "errors.jsonl"   # parent dir does not exist yet
    monkeypatch.setattr(error_log, "_LOG", log)
    error_log.log_abort("test.point", model="m", round=2, emitted=False)
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["where"] == "test.point"
    assert rec["model"] == "m" and rec["round"] == 2 and rec["emitted"] is False
    assert "ts" in rec and "iso" in rec
    assert "error" not in rec  # no exception passed → no error fields


def test_captures_exception_and_traceback(tmp_path, monkeypatch):
    log = tmp_path / "errors.jsonl"
    monkeypatch.setattr(error_log, "_LOG", log)
    try:
        raise ValueError("boom")
    except ValueError as e:
        error_log.log_abort("test.err", err=e, tool="search")
    rec = json.loads(log.read_text(encoding="utf-8").strip())
    assert rec["error"] == "boom"
    assert rec["error_type"] == "ValueError"
    assert "ValueError: boom" in rec["traceback"]
    assert rec["tool"] == "search"


def test_never_raises_on_unwritable_path(monkeypatch):
    # a regular file used as a directory parent → mkdir/open would fail
    monkeypatch.setattr(error_log, "_LOG", Path("/dev/null/nope/errors.jsonl"))
    error_log.log_abort("test.safe", err=RuntimeError("x"))  # must not raise


def test_appends_across_calls(tmp_path, monkeypatch):
    log = tmp_path / "errors.jsonl"
    monkeypatch.setattr(error_log, "_LOG", log)
    error_log.log_abort("a")
    error_log.log_abort("b")
    assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 2
