#!/usr/bin/env python3
"""aris-agent — Aris 核心對話層（bridge 負責工具執行）。

Aris Agent 模式的運作方式：
  - aris-agent.py 管理對話歷史和 Aris API 串流
  - AgentOS bridge（背景 daemon）處理 Aris 的 scream-ask/scream-task 工具呼叫
  - stdout 只輸出 Aris 的對話文字

用法:
    aris-agent "你的問題"          # 一次性對話
    aris-agent --once "你的問題"   # 同上（給 scream /aris-mode 呼叫）
    aris-agent --state             # 看 Aris 狀態
    aris-agent                     # REPL 模式
"""

import json, sys, time, http.client as hc, urllib.request
from pathlib import Path

API = "http://localhost:11546"
CONV_DIR = Path.home() / ".aris-conversations"
CURRENT = CONV_DIR / "current.json"


def load_history() -> list:
    try:
        return json.loads(CURRENT.read_text(encoding="utf-8")).get("messages", [])
    except Exception:
        return []


def save_history(msgs: list) -> None:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(json.dumps(
        {"session_id": "aris-current", "messages": msgs[-100:]},
        ensure_ascii=False, indent=1), encoding="utf-8")


def stream_aris(messages: list, out=sys.stdout) -> str:
    """Stream Aris response to stdout, return full content."""
    body = json.dumps({
        "model": "laap-core",
        "messages": _fmt(messages),
        "stream": True,
    })
    conn = hc.HTTPConnection("localhost", 11546, timeout=120)
    conn.request("POST", "/v1/chat/completions", body.encode(),
                 {"Content-Type": "application/json"})
    resp = conn.getresponse()
    parts = []
    try:
        while True:
            line = resp.readline()
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw.startswith("data: "):
                continue
            data = raw[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if token:
                    parts.append(token)
                    out.write(token)
                    out.flush()
                if chunk.get("choices", [{}])[0].get("finish_reason"):
                    break
            except json.JSONDecodeError:
                continue
    finally:
        conn.close()
    return "".join(parts)


def _fmt(msgs: list) -> list:
    return [{"role": m["role"], "content": m["content"]} for m in msgs[-50:]]


def agent_loop(user_msg: str, out=sys.stdout) -> str:
    history = load_history()
    history.append({"role": "user", "content": user_msg, "ts": time.time()})
    content = stream_aris(history, out=out)
    history.append({"role": "assistant", "content": content, "ts": time.time()})
    save_history(history)
    # Reflect 到 Aris 記憶
    try:
        req = urllib.request.Request(
            API + "/v1/reflect",
            data=json.dumps({"assistant_message": content}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass
    return content


def show_state() -> None:
    sp = Path.home() / "Developer/neuralis/status.json"
    try:
        d = json.loads(sp.read_text(encoding="utf-8"))
        psi = d.get("psi", {})
        e = psi.get("emotion", {})
        af = psi.get("affective") or {}
        print(f"需求 {psi.get('dominant_need')} | "
              f"v{e.get('valence', 0):+.2f} a{e.get('arousal', 0):.2f} | "
              f"mood {af.get('mood', '?')}")
    except Exception:
        print("（status.json 不可用）")


def main():
    args = sys.argv[1:]
    try:
        urllib.request.urlopen(API + "/health", timeout=3)
    except OSError:
        print("❌ Aris 不在線", file=sys.stderr)
        sys.exit(1)

    if args and args[0] == "--state":
        show_state()
        return

    if args and (args[0] == "--once" or not args[0].startswith("--")):
        msg = " ".join(args[1:] if args[0] == "--once" else args).strip()
        if msg:
            agent_loop(msg)
        return

    print("🧠 Aris Agent（exit 離開）", file=sys.stderr)
    show_state()
    while True:
        try:
            msg = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            break
        if not msg:
            continue
        if msg in ("exit", "quit"):
            break
        if msg == "/state":
            show_state()
            continue
        try:
            print()
            agent_loop(msg)
            print()
        except KeyboardInterrupt:
            print("\n（中斷）", file=sys.stderr)
            break
        except Exception as e:
            print(f"\n（錯誤: {e}）", file=sys.stderr)


if __name__ == "__main__":
    main()