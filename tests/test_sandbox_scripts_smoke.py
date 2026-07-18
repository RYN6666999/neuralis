"""Smoke tests for the standalone Phase 1-3 scripts.

These two scripts (scripts/sandbox.py, scripts/scream-task-executor.py) live
outside the laap package and had zero coverage, so the ponytail refactor
(5dcd0a3) could drop function-scoped imports and ship five runtime NameError /
AttributeError bugs while "188 pytest passed" stayed green — the suite never
touched them. This file wires them into that gate.

The goal is cheap regression detection for the exact failure class that shipped:
- missing module-level imports surfacing as NameError at tool-call time,
- the __import__('urllib.parse').quote AttributeError,
- the cmd_ccp l[2] IndexError on any file change,
- credential leakage into spawned subprocesses.
Not a full functional test — a "did anyone run this after editing it" guard.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_task(ex, content: str) -> dict:
    return ex.execute_task({"ts": 1, "content": content, "context": {}})


_IMPORT_ERR = ("is not defined", "has no attribute", "No module named")


def _assert_no_import_regression(result: dict):
    err = str(result.get("content", "")) + str(result.get("context", {}))
    for bad in _IMPORT_ERR:
        assert bad not in err, f"import-class regression leaked: {err[:200]}"


def test_executor_tools_no_import_regression():
    """Every tool path must run without a NameError/AttributeError.

    Catches: missing `import subprocess`, missing `from pathlib import Path`,
    the broken `__import__('urllib.parse').quote`, and `_bash` without shell=True.
    """
    ex = _load("scream-task-executor.py")

    # read: cat a neutral probe file (its content must not itself contain the
    # sentinel phrases, or the guard false-positives on the echoed body)
    probe = Path("/tmp/aris-smoke-read.txt")
    probe.write_text("smoke-ok")
    try:
        r = _run_task(ex, f"讀取 `{probe}`")
        _assert_no_import_regression(r)
        assert r["context"]["success"] is True and "smoke-ok" in r["content"]
    finally:
        probe.unlink(missing_ok=True)

    # bash: needs shell=True or "echo hi" is treated as a filename
    r = _run_task(ex, "執行 `echo hi`")
    _assert_no_import_regression(r)
    assert r["context"]["success"] is True and "hi" in r["content"]

    # search: exercises urllib.parse.quote (do NOT assert success — needs network)
    r = _run_task(ex, "搜尋 pytest smoke test")
    _assert_no_import_regression(r)

    # write: exercises pathlib.Path
    out = Path("/tmp/aris-smoke-write.txt")
    out.unlink(missing_ok=True)
    r = _run_task(ex, f"寫入 `{out}`\n```\nhello\n```")
    _assert_no_import_regression(r)
    assert r["context"]["success"] is True and out.read_text() == "hello"
    out.unlink(missing_ok=True)


def test_executor_write_path_deny():
    """Writes into laap/ must be blocked by the shared safety_gate path-DENY."""
    ex = _load("scream-task-executor.py")
    r = _run_task(ex, "寫入 `laap/should_never_write.py`\n```\nx\n```")
    assert r["context"]["success"] is False
    assert "path-DENY" in r["content"]


def test_executor_credential_isolation(monkeypatch):
    """Spawned subprocesses must not inherit API keys from the parent env."""
    ex = _load("scream-task-executor.py")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SMOKE-must-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-SMOKE-must-not-leak")
    r = ex._bash("執行 `printf %s $OPENAI_API_KEY$ANTHROPIC_API_KEY; echo DONE`")
    assert "sk-SMOKE" not in r.get("output", "")
    assert r.get("output", "").strip() == "DONE"


def test_sandbox_ccp_parses_files():
    """A real minimal sandbox cycle: cmd_ccp must parse changed files.

    Catches the cmd_ccp `l[2]` IndexError — split("\\t", 1) yields 2 elements,
    so any file change made the core Phase 3 output crash.
    """
    sb = _load("sandbox.py")
    shutil.rmtree(sb.SB_ROOT, ignore_errors=True)  # clean stale global state
    info = sb.cmd_sandbox_create("smoke-ccp")
    sid = info["id"]
    try:
        wt = Path(info["path"])
        (wt / "smoke-probe.txt").write_text("change")
        env_flags = ["-c", "user.email=smoke@test", "-c", "user.name=smoke"]
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(wt), *env_flags, "commit", "-m", "probe"],
                       check=True, capture_output=True)
        ccp = sb.cmd_ccp(sid)
        assert ccp["files"], "cmd_ccp returned no files"
        assert all("p" in f and f["p"] for f in ccp["files"]), f"bad file rows: {ccp['files']}"
        assert any(f["p"] == "smoke-probe.txt" for f in ccp["files"])
    finally:
        sb.cmd_sandbox_destroy(sid)
        shutil.rmtree(sb.SB_ROOT, ignore_errors=True)
