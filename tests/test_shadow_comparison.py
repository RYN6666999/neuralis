"""shadow 雙路徑比對層測試（option b: 誠實窄比對 + 不可比分類）。

覆蓋 agentos-aris-bridge.py 的 shadow 比對層 —— 此子系統在 neuralis 側原本零測試。

隔離紀律（承 log/2026-07-22-mcp-schema-shadow-isolation 的教訓）：
- 不污染 process env。用 monkeypatch.setattr 覆蓋 module 常數。
- SHADOW_LOG / SHADOW_WORKSPACE_ROOT / kill sentinel 全指 tmp_path。
- 不留背景 worker thread：enqueue 測試把 _shadow_init_worker no-op 掉並手動排空，
  _shadow_execute 直接同步呼叫，不起 thread。真實 shadow log 全程不碰。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

# ── 載入連字號腳本 ──────────────────────────────────────────
_BRIDGE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "agentos-aris-bridge.py"
_spec = importlib.util.spec_from_file_location("agentos_aris_bridge", _BRIDGE_PATH)
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _mcp_stdout(stdout_text: str, *, structured: bool = False, status: str = "ok") -> str:
    """組一行 MCP tools/call 回應（id==1），read_file 的內容放在 tool dict 的 stdout。"""
    tool_dict = {"status": status, "stdout": stdout_text, "stderr": ""}
    result: dict = {"isError": False}
    if structured:
        result["structuredContent"] = tool_dict
        result["content"] = []
    else:
        result["content"] = [{"type": "text", "text": json.dumps(tool_dict)}]
    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})


@pytest.fixture
def shadow_env(tmp_path, monkeypatch):
    """把 shadow 全部導向 tmp，並開啟 SHADOW_ENABLED（不碰 process env）。"""
    ws = tmp_path / "workspace"
    ws.mkdir()
    log_path = tmp_path / "shadow.jsonl"
    monkeypatch.setattr(bridge, "SHADOW_ENABLED", True)
    monkeypatch.setattr(bridge, "SHADOW_LOG", str(log_path))
    monkeypatch.setattr(bridge, "SHADOW_WORKSPACE_ROOT", str(ws.resolve()))
    monkeypatch.setattr(bridge, "SHADOW_KILL_SENTINEL", str(tmp_path / "no-such-kill"))
    return {"ws": ws, "log": log_path}


def _read_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]


# ── _result_digest：不落全文、hash 可比、head redact ────────────

def test_result_digest_shape_and_hash():
    d = bridge._result_digest("hello world")
    assert len(d["hash"]) == 64 and all(c in "0123456789abcdef" for c in d["hash"])
    assert d["len"] == len(b"hello world")
    # 相同內容 → 相同 hash；不同 → 不同
    assert bridge._result_digest("hello world")["hash"] == d["hash"]
    assert bridge._result_digest("hello worlD")["hash"] != d["hash"]


def test_result_digest_normalizes_trailing_whitespace():
    # 舊路徑 _run 一律 strip；新路徑未必。兩邊統一 strip，尾端換行不算 diverge。
    assert bridge._result_digest("abc\n")["hash"] == bridge._result_digest("abc")["hash"]


def test_result_digest_no_plaintext_and_redacts_head():
    body = "SUPERSECRETBODY_" + ("x" * 500)
    d = bridge._result_digest(body)
    # head 至多 200 字（redact 後），不足以還原 500 字全文
    assert len(d["head"]) <= 200
    assert body not in d["head"]
    # 含 "secret" → 整段 head 被 redact 成標記
    assert d["head"] == "<SECRET>"


# ── _resolve_workspace_read_path：對稱複用 _extract_path ────────

def test_resolve_inside_workspace(shadow_env):
    f = shadow_env["ws"] / "notes.txt"
    f.write_text("data")
    rel, reason = bridge._resolve_workspace_read_path(f"讀取 `{f}` 的內容")
    assert reason is None
    assert rel == "notes.txt"


def test_resolve_out_of_workspace(shadow_env):
    rel, reason = bridge._resolve_workspace_read_path("讀取 `/etc/hostname`")
    assert rel is None and reason == "out_of_workspace"


def test_resolve_no_path(shadow_env):
    rel, reason = bridge._resolve_workspace_read_path("隨便講講沒有路徑")
    assert rel is None and reason == "no_path"


# ── _shadow_call_to_mcp：不可比分類 + gate_verdict 貫穿 ─────────

def test_call_non_readonly_route_incomparable(shadow_env):
    bridge._shadow_call_to_mcp("bash", "跑個指令", "e1", old_digest=None, gate_verdict="allow")
    rows = _read_log(shadow_env["log"])
    assert len(rows) == 1
    r = rows[0]
    assert r["comparable"] is False
    assert r["incomparable_reason"] == "non_readonly_route"
    assert r["gate_verdict"] == "allow"


def test_call_out_of_workspace_incomparable(shadow_env):
    bridge._shadow_call_to_mcp(
        "read", "讀取 `/etc/hostname`", "e2",
        old_digest=bridge._result_digest("x"), gate_verdict="allow",
    )
    r = _read_log(shadow_env["log"])[-1]
    assert r["comparable"] is False and r["incomparable_reason"] == "out_of_workspace"


def test_call_read_old_path_error_incomparable(shadow_env):
    f = shadow_env["ws"] / "a.txt"
    f.write_text("hi")
    # 舊路徑失敗 → old_digest None → 沒有內容可比
    bridge._shadow_call_to_mcp("read", f"讀取 `{f}`", "e3", old_digest=None, gate_verdict="allow")
    r = _read_log(shadow_env["log"])[-1]
    assert r["comparable"] is False and r["incomparable_reason"] == "old_path_error"


def test_call_comparable_read_enqueues(shadow_env, monkeypatch):
    monkeypatch.setattr(bridge, "_shadow_init_worker", lambda: None)  # 不起 thread
    f = shadow_env["ws"] / "b.txt"
    f.write_text("content")
    bridge._shadow_call_to_mcp(
        "read", f"讀取 `{f}`", "e4",
        old_digest=bridge._result_digest("content"), gate_verdict="allow",
    )
    # queue 裡有一筆帶 old_digest 的 read_file
    item = bridge._SHADOW_QUEUE.get_nowait()
    assert item["op_name"] == "read_file" and item["path"] == "b.txt"
    assert item["old_digest"]["hash"] == bridge._result_digest("content")["hash"]
    assert item["gate_verdict"] == "allow"
    # 入列本身也記了一筆 comparable True
    r = _read_log(shadow_env["log"])[-1]
    assert r["comparable"] is True and r["shadow_status"] == "enqueued"


def test_call_kill_switch(shadow_env, monkeypatch):
    monkeypatch.setattr(bridge, "_shadow_kill_active", lambda: True)
    bridge._shadow_call_to_mcp("read", "讀取 `/x`", "e5", old_digest=None, gate_verdict="allow")
    r = _read_log(shadow_env["log"])[-1]
    assert r["shadow_status"] == "killed"


# ── _shadow_execute：實際比對 + 隱私 ───────────────────────────

def _run_execute(shadow_env, monkeypatch, *, old_text, new_text, structured=False, status="ok"):
    monkeypatch.setattr(
        bridge._sp, "run",
        lambda *a, **k: _FakeProc(stdout=_mcp_stdout(new_text, structured=structured, status=status)),
    )
    item = {
        "route": "read", "op_name": "read_file", "path": "b.txt",
        "entry_id": "x", "enqueued_at": bridge.time.time(),
        "old_digest": bridge._result_digest(old_text) if old_text is not None else None,
        "gate_verdict": "allow",
    }
    # _build_command 要對 path 過關；建個真檔以防 realpath 檢查
    (shadow_env["ws"] / "b.txt").write_text(old_text or "")
    bridge._shadow_execute(item)
    return _read_log(shadow_env["log"])[-1]


def test_execute_not_diverged(shadow_env, monkeypatch):
    r = _run_execute(shadow_env, monkeypatch, old_text="same body", new_text="same body")
    assert r["comparable"] is True
    assert r["shadow_status"] == "ok"
    assert r["diverged"] is False
    assert r["old_result"]["hash"] == r["new_result"]["hash"]


def test_execute_diverged_with_note(shadow_env, monkeypatch):
    r = _run_execute(shadow_env, monkeypatch, old_text="old body", new_text="a totally different body")
    assert r["diverged"] is True
    assert "length_mismatch" in r["divergence_note"]


def test_execute_structured_content_path(shadow_env, monkeypatch):
    r = _run_execute(shadow_env, monkeypatch, old_text="hi", new_text="hi", structured=True)
    assert r["diverged"] is False


def test_execute_tool_status_not_ok_is_error(shadow_env, monkeypatch):
    # tool 回 not_found（isError 仍 false）→ 誠實記 error，diverged 未定義
    r = _run_execute(shadow_env, monkeypatch, old_text="x", new_text="", status="not_found")
    assert r["shadow_status"] == "error"
    assert r["error_type"] == "tool_status:not_found"
    assert r["diverged"] is None
    assert r["divergence_note"] == "new_path_error"


def test_execute_privacy_no_full_content_in_log(shadow_env, monkeypatch):
    body = "LEDGER_LINE_ITEM_" + ("z" * 400)  # >200，且不含 redact 關鍵字
    monkeypatch.setattr(
        bridge._sp, "run",
        lambda *a, **k: _FakeProc(stdout=_mcp_stdout(body)),
    )
    (shadow_env["ws"] / "b.txt").write_text(body)
    item = {
        "route": "read", "op_name": "read_file", "path": "b.txt",
        "entry_id": "x", "enqueued_at": bridge.time.time(),
        "old_digest": bridge._result_digest(body), "gate_verdict": "allow",
    }
    bridge._shadow_execute(item)
    raw_log = shadow_env["log"].read_text()
    # 全文不得出現在 log；只有 hash + 截斷頭
    assert body not in raw_log
    row = _read_log(shadow_env["log"])[-1]
    assert len(row["new_result"]["head"]) <= 200
    assert row["new_result"]["hash"] == bridge._result_digest(body)["hash"]
    assert row["diverged"] is False


def test_execute_new_path_error_diverged_none(shadow_env, monkeypatch):
    # 新路徑 subprocess 非零退出 → shadow_status error，diverged None
    monkeypatch.setattr(bridge._sp, "run", lambda *a, **k: _FakeProc(stdout="", stderr="boom", returncode=1))
    (shadow_env["ws"] / "b.txt").write_text("x")
    item = {
        "route": "read", "op_name": "read_file", "path": "b.txt",
        "entry_id": "x", "enqueued_at": bridge.time.time(),
        "old_digest": bridge._result_digest("x"), "gate_verdict": "allow",
    }
    bridge._shadow_execute(item)
    r = _read_log(shadow_env["log"])[-1]
    assert r["shadow_status"] == "error" and r["diverged"] is None
