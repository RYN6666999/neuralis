"""Characterization tests for laap/chatflow.py — the request→response hot path.

GUARD-FIRST. chatflow.py is 911 lines, 17 recent commits, zero dedicated tests,
and every chat request flows through `_make_chat_handler` (196 lines) and
`_tool_chat` (126 lines). Those two functions are the next ponytail target.
This file pins current behavior BEFORE any cut so a refactor that changes
observable behavior turns a test red instead of shipping (cf. the ponytail
regression that broke scream-task-executor at 0% coverage).

These are characterization tests: they assert what the code DOES today, not
what it "should" do. If a pin feels wrong, fix it in a deliberate, separate
change — do not loosen it silently to make a refactor pass.

No pytest-asyncio (not installed, and ponytail says don't add deps). Async
handlers are driven directly with asyncio.run().
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import types
from pathlib import Path

import pytest

import laap.chatflow as cf

TOOL_STATUS = Path("/tmp/laap-tool-status.json")


def _run(coro):
    return asyncio.run(coro)


class FakeRequest:
    """Minimal aiohttp-Request stand-in: the handler only awaits .json()."""

    def __init__(self, body, raise_on_json=False):
        self._body = body
        self._raise = raise_on_json

    async def json(self):
        if self._raise:
            raise ValueError("bad body")
        return self._body


# ────────────────────────── pure helpers ──────────────────────────

def test_content_text_variants():
    assert cf._content_text("hi") == "hi"
    assert cf._content_text([{"type": "text", "text": "a"},
                             {"type": "image", "url": "x"},
                             {"type": "text", "text": "b"}]) == "a b"
    assert cf._content_text(None) == ""
    assert cf._content_text(123) == ""


def test_extract_user_msg_takes_last_user_and_truncates():
    body = {"messages": [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "x" * 800},
    ]}
    out = cf._extract_user_msg(body)
    assert out == "x" * 500  # last user, capped at 500
    assert cf._extract_user_msg({"messages": []}) == ""
    assert cf._extract_user_msg({}) == ""


def test_is_user_turn():
    assert cf._is_user_turn({"messages": [{"role": "user", "content": "hi"}]}) is True
    assert cf._is_user_turn({"messages": [{"role": "user", "content": "hi"},
                                          {"role": "tool", "content": "r"}]}) is False
    assert cf._is_user_turn({"messages": []}) is False
    assert cf._is_user_turn({}) is False


def test_is_harness_noise():
    assert cf._is_harness_noise("Summarize the following conversation") is True
    assert cf._is_harness_noise("Generate a title") is True
    assert cf._is_harness_noise("以下是会话记录") is True
    assert cf._is_harness_noise("今天天氣如何") is False
    assert cf._is_harness_noise("") is False


def test_build_response_envelope():
    r = cf._build_response("hello", "psi-llm", "laap-core", prompt_chars=40)
    assert r["object"] == "chat.completion"
    assert r["id"].startswith("laap-")
    assert r["model"] == "laap-core"
    assert r["engine"] == "psi-llm"
    assert r["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert r["choices"][0]["finish_reason"] == "stop"
    assert r["usage"]["prompt_tokens"] == 10  # 40 // 4


def test_build_tool_response_includes_tool_calls():
    result = {"message": {"role": "assistant", "content": None,
                          "tool_calls": [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}]},
              "finish_reason": "tool_calls"}
    r = cf._build_tool_response(result, "laap-core", prompt_chars=8)
    assert r["engine"] == "psi-llm-tools"
    assert r["choices"][0]["message"]["tool_calls"][0]["id"] == "c1"
    assert r["choices"][0]["finish_reason"] == "tool_calls"
    # no tool_calls → key omitted
    r2 = cf._build_tool_response({"message": {"role": "assistant", "content": "plain"}},
                                 "laap-core", prompt_chars=4)
    assert "tool_calls" not in r2["choices"][0]["message"]


def test_sse_chunk_shape():
    s = cf._sse_chunk("rid", 100, "m", delta={"content": "x"})
    assert s.startswith("data: ") and s.endswith("\n\n")
    payload = json.loads(s[len("data: "):].strip())
    assert payload["object"] == "chat.completion.chunk"
    assert payload["choices"][0]["delta"] == {"content": "x"}
    assert "finish_reason" not in payload["choices"][0]
    s2 = cf._sse_chunk("rid", 100, "m", delta={}, finish_reason="stop")
    assert json.loads(s2[len("data: "):].strip())["choices"][0]["finish_reason"] == "stop"


def test_compose_psi_reply_is_traceable():
    st = {"emotion": {"valence": 0.2, "arousal": 0.6},
          "dominant_need": "competence", "dominant_drive": 0.7,
          "attention": "工作"}
    delta = {"competence": 0.05, "relatedness": 0.0, "valence": 0.03}
    reply = cf._compose_psi_reply(st, delta)
    assert "competence" in reply and "工作" in reply
    assert "competence +0.05" in reply       # moved need surfaced with sign
    assert cf._NEED_PHRASE["competence"] in reply
    # memory weaving is opt-in
    assert "想起" not in reply
    reply_mem = cf._compose_psi_reply(st, delta, memories=["某段記憶"])
    assert "某段記憶" in reply_mem and "想起" in reply_mem


def test_take_pending_memories_freshness():
    cf._pending_memories["lines"] = ["late recall"]
    cf._pending_memories["ts"] = time.time()
    assert cf._take_pending_memories() == ["late recall"]
    assert cf._take_pending_memories() == []          # consumed
    cf._pending_memories["lines"] = ["stale"]
    cf._pending_memories["ts"] = time.time() - 400     # > 300s window
    assert cf._take_pending_memories() == []


# ────────────────────── handler routing (async) ──────────────────────

@pytest.fixture
def no_psi(monkeypatch):
    """Force fed=None / no agency so the handler's deterministic branches run."""
    monkeypatch.setattr("laap.startup.get_psi_core", lambda: None)
    monkeypatch.setattr("laap.startup.get_agency", lambda: None)
    monkeypatch.setattr("laap.startup.get_consolidation", lambda: None)
    monkeypatch.setenv("NEURALIS_PSI_MEMORY", "off")   # skip gbrain recall path
    TOOL_STATUS.unlink(missing_ok=True)                 # no stale busy guard
    yield
    TOOL_STATUS.unlink(missing_ok=True)


def test_handler_body_parse_failure_falls_back_to_author():
    called = {}

    async def orig(request):
        called["hit"] = True
        return "ORIG"

    handler = cf._make_chat_handler(orig)
    out = _run(handler(FakeRequest(None, raise_on_json=True)))
    assert called.get("hit") is True and out == "ORIG"


def test_handler_tools_routes_to_tool_chat(no_psi, monkeypatch):
    monkeypatch.setattr(
        "laap.llm_respond.respond_tools",
        lambda body, psi_state, delta: {
            "message": {"role": "assistant", "content": "TOOLRESP"},
            "finish_reason": "stop", "usage": {}})
    body = {"model": "laap-core",
            "messages": [{"role": "user", "content": "do it"}],
            "tools": [{"type": "function", "function": {"name": "f"}}]}
    handler = cf._make_chat_handler(lambda r: None)
    resp = _run(handler(FakeRequest(body)))
    out = json.loads(resp.body)
    assert out["engine"] == "psi-llm-tools"
    assert out["choices"][0]["message"]["content"] == "TOOLRESP"


def test_handler_busy_guard_short_circuits(no_psi):
    TOOL_STATUS.write_text(json.dumps({
        "status": "running", "tool": "scream-ask",
        "ts": time.time(), "description": "問 Scream"}))
    body = {"model": "laap-core",
            "messages": [{"role": "user", "content": "在嗎"}]}
    handler = cf._make_chat_handler(lambda r: None)
    resp = _run(handler(FakeRequest(body)))
    out = json.loads(resp.body)
    assert out["engine"] == "laap-busy"
    assert "請稍等" in out["choices"][0]["message"]["content"]


def test_handler_author_path_wins(no_psi):
    fake_api = types.ModuleType("laap_brain_api")
    fake_api.process_with_laap = lambda messages, model: {
        "content": "AUTH-OK", "engine": "laap-core"}
    sys.modules["laap_brain_api"] = fake_api
    try:
        body = {"model": "laap-core",
                "messages": [{"role": "user", "content": "普通問句"}]}
        handler = cf._make_chat_handler(lambda r: None)
        resp = _run(handler(FakeRequest(body)))
        out = json.loads(resp.body)
        assert out["choices"][0]["message"]["content"] == "AUTH-OK"
        assert out["engine"] == "laap-core"
    finally:
        sys.modules.pop("laap_brain_api", None)
