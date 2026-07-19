"""Persistent structured error log for Aris turn-aborts and tool failures.

Aris turns abort mid-way when a tool or the LLM continuation call fails, but the
error was only a one-line stream message + a logger.warning to nowhere durable,
so the operator was blind to what actually broke ("我不確定錯誤印在哪"). This
appends each abort/failure to ~/.neuralis/aris-errors.jsonl with the full
traceback + context (round, tool, model, message count).

Best-effort: never raises and never blocks the turn — observability must not
become a new failure mode. Override the path with NEURALIS_ERROR_LOG.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path

_LOG = Path(os.environ.get(
    "NEURALIS_ERROR_LOG", str(Path.home() / ".neuralis" / "aris-errors.jsonl")))


def log_abort(where: str, err: BaseException | None = None, **ctx) -> None:
    """Append one JSONL record: {ts, iso, where, [error/error_type/traceback], **ctx}.

    `where` is a stable dotted label for the abort point (e.g.
    "call_llm_stream.connect", "respond_stream.llm_error"). Pass the exception as
    `err` when one exists; pass a `detail=` string in ctx when the source only has
    a message. Never raises.
    """
    try:
        rec: dict = {
            "ts": round(time.time(), 3),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "where": where,
            **ctx,
        }
        if err is not None:
            rec["error"] = str(err)[:500]
            rec["error_type"] = type(err).__name__
            rec["traceback"] = "".join(traceback.format_exception(
                type(err), err, err.__traceback__))[:4000]
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        with _LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # never let logging break the turn
