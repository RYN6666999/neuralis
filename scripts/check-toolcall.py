#!/usr/bin/env python3
"""工具呼叫協議自檢：scream agent 迴圈賴以運作的 OpenAI function-calling。
A. 純函式護欄（_is_user_turn / _content_text，不需 server）
B. 非 streaming：帶 tools 請求 → 回 tool_calls + finish_reason=tool_calls
C. 工具結果往返：assistant tool_calls + tool 結果 → 最終 content
D. streaming：SSE delta 累加出完整 tool_call
E. 迴歸：無 tools 純聊天照常
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-toolcall.py
（B-E 需要 :11546 活著；NEURALIS_TOOLCHECK_BASE 可改目標）
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get("NEURALIS_TOOLCHECK_BASE", "http://localhost:11546")

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查詢指定城市目前天氣",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名"}},
            "required": ["city"],
        },
    },
}]


def post(body: dict, timeout=150):
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def seg_a():
    from laap.chatflow import _is_user_turn, _content_text, _is_harness_noise
    assert _is_user_turn({"messages": [{"role": "user", "content": "嗨"}]})
    assert not _is_user_turn({"messages": [
        {"role": "user", "content": "嗨"},
        {"role": "assistant", "content": None, "tool_calls": [{}]},
        {"role": "tool", "content": "結果"},
    ]}), "工具 round-trip 不可算使用者回合"
    assert not _is_user_turn({"messages": []})
    assert _content_text("abc") == "abc"
    assert _content_text(None) == ""
    assert _content_text([{"type": "text", "text": "a"},
                          {"type": "image_url", "image_url": {}}]) == "a"
    assert _is_harness_noise('以下是会话 "session_xxx" 的对话内容，请总结'), \
        "scream 簿記請求要被擋"
    assert not _is_harness_noise("嗨，今天感覺怎麼樣？")
    print("A. user-turn 護欄 + content 安全抽取 + 簿記過濾: OK")


def seg_f():
    """T2：工具結果 → affective 事件（離線，假 psi 收事件）。"""
    import laap.startup as st
    from laap import chatflow
    events = []

    class FakeAff:
        def post_event(self, name, intensity=1.0):
            events.append((name, round(intensity, 2)))
            return True

    class FakePsi:
        affective = FakeAff()
        def post_affective_event(self, name, intensity=1.0):
            return self.affective.post_event(name, intensity)

    orig = st.get_psi_core
    st.get_psi_core = lambda: FakePsi()
    try:
        chatflow._post_tool_outcomes({"messages": [
            {"role": "user", "content": "做事"},
            {"role": "assistant", "content": None, "tool_calls": [{}]},
            {"role": "tool", "content": "Error: permission denied"},
            {"role": "tool", "content": "done, 3 files listed"},
        ]})
        chatflow._post_tool_outcomes({"messages": [
            {"role": "user", "content": "純聊天不該有事件"}]})
    finally:
        st.get_psi_core = orig
    assert ("task_failure", 0.5) in events and ("task_success", 0.3) in events, events
    assert len(events) == 2, f"純聊天不該產生事件: {events}"
    print(f"F. 工具結果→情緒事件: OK ({events})")


def seg_b():
    resp = json.loads(post({
        "model": "laap-core",
        "messages": [{"role": "user", "content": "用工具查台北現在的天氣"}],
        "tools": TOOLS,
        "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
    }).read())
    msg = resp["choices"][0]["message"]
    fin = resp["choices"][0]["finish_reason"]
    tcs = msg.get("tool_calls") or []
    assert tcs, f"沒有 tool_calls: {json.dumps(resp, ensure_ascii=False)[:300]}"
    assert tcs[0]["function"]["name"] == "get_weather"
    args = json.loads(tcs[0]["function"]["arguments"])
    assert "city" in args, f"arguments 缺 city: {args}"
    assert fin == "tool_calls", f"finish_reason={fin}"
    assert resp.get("engine") == "psi-llm-tools"
    print(f"B. 非 streaming tool call: OK (city={args['city']}, finish={fin})")
    return tcs[0]


def seg_c(tc):
    resp = json.loads(post({
        "model": "laap-core",
        "messages": [
            {"role": "user", "content": "用工具查台北現在的天氣"},
            {"role": "assistant", "content": None, "tool_calls": [tc]},
            {"role": "tool", "tool_call_id": tc["id"],
             "content": '{"temp_c": 31, "condition": "晴時多雲"}'},
        ],
        "tools": TOOLS,
    }).read())
    msg = resp["choices"][0]["message"]
    fin = resp["choices"][0]["finish_reason"]
    assert msg.get("content"), "工具結果後沒有最終 content"
    assert "31" in msg["content"] or "晴" in msg["content"], \
        f"最終回應沒用到工具結果: {msg['content'][:120]}"
    assert fin == "stop", f"finish_reason={fin}"
    print(f"C. 工具結果往返: OK ({msg['content'][:60]}...)")


def seg_d():
    raw = post({
        "model": "laap-core",
        "messages": [{"role": "user", "content": "用工具查東京現在的天氣"}],
        "tools": TOOLS,
        "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
        "stream": True,
    }).read().decode()
    name, args, fin = "", "", None
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        c = json.loads(line[6:])["choices"][0]
        if c.get("finish_reason"):
            fin = c["finish_reason"]
        for tcd in (c["delta"].get("tool_calls") or []):
            f = tcd.get("function") or {}
            name += f.get("name") or ""
            args += f.get("arguments") or ""
    assert name == "get_weather", f"SSE 累加 name={name!r}"
    parsed = json.loads(args)
    assert "city" in parsed, f"SSE 累加 arguments 壞掉: {args!r}"
    assert fin == "tool_calls", f"SSE finish_reason={fin}"
    print(f"D. streaming tool call: OK (city={parsed['city']})")


def seg_e():
    resp = json.loads(post({
        "model": "laap-core",
        "messages": [{"role": "user", "content": "嗨，現在感覺怎麼樣？"}],
    }).read())
    msg = resp["choices"][0]["message"]
    assert msg.get("content"), "純聊天壞了"
    assert not msg.get("tool_calls")
    print(f"E. 純聊天迴歸: OK (engine={resp.get('engine')})")


def main():
    seg_a()
    seg_f()
    try:
        urllib.request.urlopen(f"{BASE}/health", timeout=5)
    except Exception as e:
        print(f"⚠️ {BASE} 不在線（{e}），B-E 跳過 — 起 server 後重跑")
        sys.exit(1)
    tc = seg_b()
    seg_c(tc)
    seg_d()
    seg_e()
    print("\n✅ check-toolcall 全過 — scream agent 迴圈的協議底座就緒")


if __name__ == "__main__":
    main()
