"""A2 guard — _call_llm_stream 對 transient 失敗自動重試（止「手動繼續」痛點）。

規則：504 idle timeout / mid-stream timeout / 空串流，且**還沒吐 token** → 自動重連重試；
已吐 token 的不重試（避免重複輸出）；非 transient（404）不重試。
"""
import io
import urllib.error

import laap.llm_respond as lr


class FakeResp:
    """SSE 回應：逐行 yield bytes；raise_after=N → 在第 N 行前拋 timeout。"""

    def __init__(self, lines, raise_after=None):
        self._lines = [l.encode() if isinstance(l, str) else l for l in lines]
        self._raise_after = raise_after

    def __iter__(self):
        for i, l in enumerate(self._lines):
            if self._raise_after is not None and i == self._raise_after:
                raise TimeoutError("simulated mid-stream timeout")
            yield l

    def close(self):
        pass


def _make_urlopen(queue):
    state = {"n": 0}

    def fake(req, timeout=None):
        state["n"] += 1
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    fake.state = state
    return fake


def _patch(monkeypatch, queue):
    monkeypatch.setattr(lr, "_get_api_key", lambda: "k")
    monkeypatch.setattr(lr.time, "sleep", lambda *a, **k: None)
    uo = _make_urlopen(queue)
    monkeypatch.setattr(lr.urllib.request, "urlopen", uo)
    return uo


TOKEN = 'data: {"choices":[{"delta":{"content":"hi"}}]}'
DONE = "data: [DONE]"


def test_is_transient_upstream():
    assert lr._is_transient_upstream({"code": 504, "message": "Upstream idle timeout"})
    assert lr._is_transient_upstream("rate limit exceeded")
    assert not lr._is_transient_upstream({"code": 404, "message": "Not Found"})
    assert not lr._is_transient_upstream("invalid api key")


def test_retries_transient_504_then_succeeds(monkeypatch):
    uo = _patch(monkeypatch, [
        FakeResp(['data: {"error":{"code":504,"message":"Upstream idle timeout exceeded"}}', DONE]),
        FakeResp([TOKEN, DONE]),
    ])
    evs = list(lr._call_llm_stream([{"role": "user", "content": "x"}]))
    assert any(e["type"] == "token" and e["text"] == "hi" for e in evs)
    assert all(e["type"] != "error" for e in evs)   # 重試成功，沒有 error 冒出
    assert uo.state["n"] == 2                        # 真的重連了一次


def test_retries_midstream_timeout_then_succeeds(monkeypatch):
    uo = _patch(monkeypatch, [
        FakeResp(["data: {}", "BOOM"], raise_after=1),  # 第 2 行前 timeout，還沒吐 token
        FakeResp([TOKEN, DONE]),
    ])
    evs = list(lr._call_llm_stream([{"role": "user", "content": "x"}]))
    assert any(e["type"] == "token" and e["text"] == "hi" for e in evs)
    assert uo.state["n"] == 2


def test_no_retry_after_token_emitted(monkeypatch):
    # 吐了 token 才中斷 → 不重試（避免重複輸出），直接冒 error
    uo = _patch(monkeypatch, [FakeResp([TOKEN, "BOOM"], raise_after=1)])
    evs = list(lr._call_llm_stream([{"role": "user", "content": "x"}]))
    assert any(e["type"] == "token" and e["text"] == "hi" for e in evs)
    assert any(e["type"] == "error" for e in evs)
    assert uo.state["n"] == 1                        # 沒重試


def test_no_retry_on_404(monkeypatch):
    err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"nf"))
    uo = _patch(monkeypatch, [err])
    evs = list(lr._call_llm_stream([{"role": "user", "content": "x"}]))
    assert any(e["type"] == "error" for e in evs)
    assert uo.state["n"] == 1                        # 404 非 transient，不重試
