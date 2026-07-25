#!/usr/bin/env python3
"""aris-relay — Scream → Aris 直通橋。
用法: python3 aris-relay.py "你的訊息"
直接 POST 到 Aris API，串流回應到 stdout。
"""
import json, sys, time
from pathlib import Path
import urllib.request

API = "http://localhost:11546"
CONV_DIR = Path.home() / ".aris-conversations"
CURRENT = CONV_DIR / "current.json"

def chat_stream(user_msg: str):
    messages = []
    try:
        data = json.loads(CURRENT.read_text(encoding="utf-8"))
        messages = data.get("messages", [])
    except Exception:
        pass

    messages.append({"role": "user", "content": user_msg, "ts": time.time()})

    body = json.dumps({
        "model": "laap-core",
        "messages": [{"role": m["role"], "content": m["content"]}
                     for m in messages[-20:]],
        "stream": True,
    })
    req = urllib.request.Request(
        API + "/v1/chat/completions",
        data=body.encode(),
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=40)
    content_parts = []
    engine = "psi-llm"

    while True:
        line = resp.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text.startswith("data: "):
            continue
        data = text[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            token = delta.get("content", "")
            if token:
                content_parts.append(token)
                sys.stdout.write(token)
                sys.stdout.flush()
            fr = chunk.get("choices", [{}])[0].get("finish_reason")
            if fr:
                engine = chunk.get("engine", engine)
                break
        except json.JSONDecodeError:
            continue

    resp.close()
    content = "".join(content_parts)
    messages.append({"role": "assistant", "content": content,
                     "engine": engine, "ts": time.time()})
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(json.dumps(
        {"session_id": "aris-current", "messages": messages[-50:]},
        ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]).strip()
    if not msg:
        print("用法: aris-relay.py \"你的訊息\"")
        sys.exit(1)
    try:
        chat_stream(msg)
        print()
    except Exception as e:
        print(f"\n❌ Aris 連線失敗: {e}")
        sys.exit(1)