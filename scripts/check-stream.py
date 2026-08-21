#!/usr/bin/env python3
"""交錯串流自檢：五段（工具串流時序 / execute drain 等價 / LLM SSE 解析 /
respond_stream 工具迴圈交錯 / 線上 E2E）。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-stream.py

exit code（三態，見 scripts/_check_verdict.py）:
    0 = 驗過且都好      1 = 驗過，有壞的      2 = 沒驗到（:11546 不在）

E 段需要 :11546 活著。舊版在它不在時印 `SKIP` 然後照樣印
`ALL STREAM CHECKS PASSED` exit 0 —— 「線上真的會漸進到達」這件事一次都
沒驗到，訊號卻跟驗過一樣。現在改為 exit 2：不是綠燈，也不算失敗
（服務本來就不該要求在 CI 上跑；`guard.yml` 寫過假紅比沒有更糟）。

A-D 段不需要任何外部服務，**一定會跑** —— 「因為 E 沒驗到就整支不跑」
會把偵測力一起關掉，那是比綠燈說謊更差的解。

自我驗證鉤子：`NEURALIS_CHECK_STREAM_SABOTAGE=1` 把 stream-test 的逐步輸出
換成整塊回傳（模擬串流管線真的壞掉）。本腳本必須因此 exit 1。
`tests/test_check_scripts_no_green_lie.py` 用它證明修完仍抓得到真問題。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _check_verdict import Verdict, guard

from laap.agi.cognitive_bus import CognitiveBus
from laap.tool_executor import ToolExecutor

V = Verdict("stream")

tools = ToolExecutor(bus=CognitiveBus(agent_name="check-stream"), agentos_registry=None)

if os.environ.get("NEURALIS_CHECK_STREAM_SABOTAGE") == "1":
    # 植入真的壞掉的串流：一次吐完，沒有中間輸出、沒有時間差。
    # 這正是 A/D 段存在的理由所對應的故障，腳本必須抓到。
    _blob = ["step 1/3 開始", "step 2/3 處理中", "step 3/3 done"]
    tools.register_tool("stream-test", lambda _p: "\n".join(_blob),
                        "sabotaged: 整塊回傳",
                        stream_fn=lambda _p: iter(["\n".join(_blob)]))


# ── A. stream-test 工具逐步輸出 + 時序（證明中間輸出真的先到）──
def seg_a():
    events = []
    for ev in tools.stream("stream-test", "self-test"):
        events.append((time.time(), ev))
    types = [e["type"] for _, e in events]
    assert types[-1] == "result", f"最後一個事件必須是 result: {types}"
    assert types.count("result") == 1, f"result 恰一個: {types}"
    outputs = [(t, e) for t, e in events if e["type"] == "output"]
    assert len(outputs) >= 3, f"stream-test 應有 ≥3 行中間輸出: {types}"
    t_first_output = outputs[0][0]
    t_result = events[-1][0]
    gap = t_result - t_first_output
    assert gap >= 1.5, f"首行輸出應早於結果 ≥1.5s（實測 {gap:.2f}s）— 不是整塊回傳"
    V.ok("A. 工具串流時序",
         f"{len(outputs)} 行中間輸出，首行早於結果 {gap:.2f}s")


# ── B. execute() = stream() 的 drain（舊呼叫者行為不變）──
def seg_b():
    r = tools.execute("stream-test", "self-test")
    assert "step 1/3" in r and "step 3/3 done" in r, f"execute 應回全部行拼接: {r!r}"
    r = tools.execute("no-such-tool", "x")
    assert r.startswith("[安全閘]") or r.startswith("[未知工具]"), r
    r_deny = tools.execute("http-get", "https://example.com")   # http-get 不在白名單
    assert r_deny.startswith("[安全閘]"), f"未批准工具應拒: {r_deny}"
    evs = list(tools.stream("http-get", "https://example.com"))
    assert len(evs) == 1 and evs[0]["type"] == "result" and evs[0]["text"].startswith("[安全閘]"), evs
    V.ok("B. execute drain 等價 + 安全閘直通")


# ── C. _call_llm_stream SSE 解析（token + 分段 tool_call arguments 累加）──
_SSE = b"""data: {"choices":[{"delta":{"role":"assistant"}}]}

data: {"choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}

data: {"choices":[{"delta":{"content":"\xe5\xa5\xbd"}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc","function":{"name":"use_tool","arguments":"{\\"tool\\":"}}]}}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"gbrain\\",\\"prompt\\":\\"hi\\"}"}}]}}]}

data: [DONE]

"""


class _FakeResp:
    def __init__(self, payload: bytes):
        self._lines = payload.splitlines(keepends=True)

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        pass


def seg_c():
    import laap.llm_respond as lr

    _orig_urlopen = lr.urllib.request.urlopen
    _orig_get_key = lr._get_api_key
    lr.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(_SSE)
    lr._get_api_key = lambda: "test-key"
    try:
        got = list(lr._call_llm_stream([{"role": "user", "content": "hi"}]))
    finally:
        lr.urllib.request.urlopen = _orig_urlopen
        lr._get_api_key = _orig_get_key

    tokens = [e["text"] for e in got if e["type"] == "token"]
    tcs = [e for e in got if e["type"] == "tool_calls"]
    assert tokens == ["你", "好"], tokens
    assert len(tcs) == 1, got
    call = tcs[0]["calls"][0]
    assert call["id"] == "call_abc" and call["name"] == "use_tool", call
    args = json.loads(call["arguments"])
    assert args == {"tool": "gbrain", "prompt": "hi"}, args
    V.ok("C. LLM SSE 解析", "token 逐塊 + tool_call arguments 分段累加")


# ── D. respond_stream 工具迴圈交錯（腳本化 LLM + 真工具執行）──
def seg_d():
    import laap.llm_respond as lr
    import laap.startup as startup
    startup._tool_executor = tools   # get_tool_executor() 回測試 executor

    _round = {"n": 0, "messages_r2": None}

    def _fake_llm_stream(messages, tools=None, model=None, timeout=None, max_tokens=None):
        _round["n"] += 1
        if _round["n"] == 1:
            yield {"type": "token", "text": "我來"}
            yield {"type": "token", "text": "查。"}
            yield {"type": "tool_calls", "calls": [{
                "id": "call_1", "name": "use_tool",
                "arguments": json.dumps({"tool": "stream-test", "prompt": "x"})}]}
        else:
            _round["messages_r2"] = list(messages)
            yield {"type": "token", "text": "查到了。"}

    _orig_stream = lr._call_llm_stream
    _orig_enabled = lr._LLM_ENABLED
    lr._call_llm_stream = _fake_llm_stream
    lr._LLM_ENABLED = True
    try:
        seq = list(lr.respond_stream("stream_test 一下", {"emotion": {}, "needs": {}}))
    finally:
        lr._call_llm_stream = _orig_stream
        lr._LLM_ENABLED = _orig_enabled

    kinds = [(e["type"], e["text"]) for e in seq]
    token_texts = [t for k, t in kinds if k == "token"]
    status_texts = [t for k, t in kinds if k == "tool_status"]
    assert token_texts == ["我來", "查。", "查到了。"], token_texts
    assert any("step 2/3" in t for t in status_texts), f"工具中間輸出應被轉發: {status_texts}"
    # 順序：先 LLM token → 工具過程 → 再 LLM token（交錯，不是整塊）
    i_tok1 = kinds.index(("token", "查。"))
    i_status = next(i for i, (k, _) in enumerate(kinds) if k == "tool_status")
    i_tok2 = kinds.index(("token", "查到了。"))
    assert i_tok1 < i_status < i_tok2, f"事件應交錯: {kinds}"
    # 第二輪 LLM 要看到 tool 結果訊息
    r2 = _round["messages_r2"]
    assert r2 and r2[-1]["role"] == "tool" and "step 3/3 done" in r2[-1]["content"], \
        f"第二輪應帶 tool 結果: {r2 and r2[-1]}"
    V.ok("D. respond_stream 交錯迴圈", "token→工具過程→token，tool 結果回饋第二輪")


# ── E. 線上 E2E（:11546 活著才跑）──
def seg_e():
    import http.client as hc
    import urllib.request as ur

    try:
        ur.urlopen("http://localhost:11546/health", timeout=3)
    except OSError as e:
        # 服務不在 = 沒驗到。不是失敗（CI 上本來就沒有這個服務），
        # 但也絕對不是綠燈 —— 「線上真的漸進到達」這件事沒有任何證據。
        V.unknown("E. 線上 E2E（:11546）",
                  f"服務不在（{e}）—— 漸進到達只在單元層驗過，端到端沒驗到")
        return

    conn = hc.HTTPConnection("localhost", 11546, timeout=30)
    conn.request("POST", "/v1/chat/completions", json.dumps({
        "model": "laap-core", "stream": True,
        "messages": [{"role": "user", "content": "stream_test"}],
    }), {"Content-Type": "application/json"})
    resp = conn.getresponse()
    stamps = []
    engine = ""
    while True:
        line = resp.readline()
        if not line:
            break
        text = line.decode("utf-8", "replace").strip()
        if not text.startswith("data: "):
            continue
        if text[6:] == "[DONE]":
            break
        chunk = json.loads(text[6:])
        engine = chunk.get("engine", engine)
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if delta.get("content"):
            stamps.append((time.time(), delta["content"]))
    conn.close()
    assert engine == "tool-stream-test", f"engine 應為 tool-stream-test: {engine}"
    assert len(stamps) >= 4, f"應有 ≥4 個漸進 chunk: {[c for _, c in stamps]}"
    spread = stamps[-1][0] - stamps[0][0]
    assert spread >= 1.5, f"chunk 應跨 ≥1.5s 漸進到達（實測 {spread:.2f}s）"
    V.ok("E. 線上 E2E", f"{len(stamps)} chunks 跨 {spread:.2f}s 漸進到達")


def main() -> None:
    for label, fn in (("A", seg_a), ("B", seg_b), ("C", seg_c),
                      ("D", seg_d), ("E", seg_e)):
        with guard(V, f"{label} 段"):
            fn()
    V.finish()


if __name__ == "__main__":
    main()
