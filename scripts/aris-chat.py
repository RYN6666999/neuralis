#!/usr/bin/env python3
"""aris-chat — 直連 Aris（:11546），零中間人、零轉述。

用法:
    aris                    # REPL 對話（exit / Ctrl-D 離開）
    aris 你好嗎             # 一次性對話（streaming）
    aris --once "你好嗎"    # 同上（給 scream /aris 技能呼叫）
    aris --state            # 一頁內在狀態

對話歷史存 ~/.aris-conversations/current.json（與 scream /aris 共用，
兩個入口聊的是同一場對話）。每次回應後 reflect 進 Aris 長期記憶。

v2: 加入 SSE streaming，逐 token 即時輸出。
"""
import json
import sys
import time
import http.client as hc
import urllib.request
from pathlib import Path

API = "http://localhost:11546"
CONV_DIR = Path.home() / ".aris-conversations"
CURRENT = CONV_DIR / "current.json"


def _load() -> list:
    try:
        return json.loads(CURRENT.read_text(encoding="utf-8")).get("messages", [])
    except Exception:
        return []


def _save(messages: list) -> None:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT.write_text(json.dumps(
        {"session_id": "aris-current", "messages": messages[-50:]},
        ensure_ascii=False, indent=1), encoding="utf-8")


def _post(path: str, payload: dict, timeout: float = 40) -> dict:
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _http_post(path: str, body: str, timeout: float = 40):
    """Low-level HTTP POST, returns (connection, response)."""
    api = API
    host = api.replace("http://", "").replace("https://", "").split(":")[0]
    port = 80
    if ":" in api.replace("http://", "").replace("https://", ""):
        port = int(api.split(":")[-1])
    conn = hc.HTTPConnection(host, port, timeout=timeout)
    conn.request("POST", path, body.encode() if isinstance(body, str) else body,
                 {"Content-Type": "application/json"})
    return conn, conn.getresponse()


def _alive() -> bool:
    try:
        urllib.request.urlopen(API + "/health", timeout=3)
        return True
    except OSError:
        return False


def chat_stream(user_msg: str, out=sys.stdout) -> str:
    """Streaming chat: 送 stream:true 到 Aris API，逐 token 輸出到 out，
    回傳完整 content。對話歷史與 reflect 在串流結束時自動處理。"""
    messages = _load()
    messages.append({"role": "user", "content": user_msg, "ts": time.time()})

    body = json.dumps({
        "model": "laap-core",
        "messages": [{"role": m["role"], "content": m["content"]}
                     for m in messages[-20:]],
        "stream": True,
    })

    conn, resp = _http_post("/v1/chat/completions", body, timeout=40)
    content_parts = []
    engine = "psi-llm"

    try:
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
                    out.write(token)
                    out.flush()
                fr = chunk.get("choices", [{}])[0].get("finish_reason")
                if fr:
                    engine = chunk.get("engine", engine)
                    break
            except json.JSONDecodeError:
                continue
    finally:
        conn.close()

    content = "".join(content_parts)
    messages.append({"role": "assistant", "content": content,
                     "engine": engine, "ts": time.time()})
    _save(messages)
    try:
        _post("/v1/reflect", {"assistant_message": content}, timeout=10)
    except Exception:
        pass  # 記憶寫入失敗不擋對話
    return content


def chat_once(user_msg: str) -> str:
    """向後相容：同步版，回傳完整的 [Aris/engine]\ncontent 字串。"""
    messages = _load()
    messages.append({"role": "user", "content": user_msg, "ts": time.time()})
    r = _post("/v1/chat/completions", {
        "model": "laap-core",
        "messages": [{"role": m["role"], "content": m["content"]}
                     for m in messages[-20:]],
    })
    content = r["choices"][0]["message"]["content"]
    engine = r.get("engine", "?")
    messages.append({"role": "assistant", "content": content,
                     "engine": engine, "ts": time.time()})
    _save(messages)
    try:
        _post("/v1/reflect", {"assistant_message": content}, timeout=10)
    except Exception:
        pass  # 記憶寫入失敗不擋對話
    return f"[Aris/{engine}]\n{content}"


def show_state() -> None:
    status = Path.home() / "Developer/neuralis/status.json"
    try:
        d = json.loads(status.read_text(encoding="utf-8"))
        psi = d.get("psi", {})
        e = psi.get("emotion", {})
        af = psi.get("affective") or {}
        print(f"主導需求 {psi.get('dominant_need')} (drive {psi.get('dominant_drive')}) | "
              f"v{e.get('valence', 0):+.2f} a{e.get('arousal', 0):.2f} | "
              f"mood {af.get('mood', '?')} | tick {psi.get('tick')}")
    except Exception:
        print("（讀不到 status.json — API 可能剛重啟）")


def main() -> None:
    args = sys.argv[1:]
    if not _alive():
        print("Aris 離線中 — watchdog 會在 ~100 秒內自動救回，稍等再試。"
              "（不要手動起 server，會跟 watchdog 打架）")
        sys.exit(1)

    if args and args[0] == "--state":
        show_state()
        return

    if args and args[0] == "--sync":
        # 明確要求同步模式（給需要完整字串的整合點）
        msg = " ".join(args[1:]).strip()
        if not msg:
            print("用法: aris --sync \"要說的話\"")
            sys.exit(1)
        print(chat_once(msg))
        return

    if args and args[0] == "--once":
        msg = " ".join(args[1:]).strip()
        if not msg:
            print("用法: aris --once \"要說的話\"")
            sys.exit(1)
        # streaming 輸出到 stdout，結束後印 engine 標記
        content = chat_stream(msg)
        # 如果完全沒輸出（空回應），補一句
        if not content:
            print("（Aris 沒有回應）")
        return

    if args:                      # aris 你好嗎 → 一次性 streaming
        print(f"[Aris 思考中…]", end="\r")
        content = chat_stream(" ".join(args).strip())
        print()
        return

    # REPL
    print("直連 Aris（exit / Ctrl-D 離開，/state 看內在狀態，/sync 切同步模式）")
    show_state()
    sync_mode = False
    while True:
        try:
            msg = input("\n你 › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg:
            continue
        if msg in ("exit", "quit", "/exit"):
            break
        if msg == "/state":
            show_state()
            continue
        if msg == "/sync":
            sync_mode = not sync_mode
            print(f"{'同步' if sync_mode else '串流'}模式")
            continue
        try:
            if sync_mode:
                print(chat_once(msg))
            else:
                chat_stream(msg)
                print()
        except Exception as e:
            print(f"（這輪失敗: {e} — Aris 可能在重啟，稍等重試）")


if __name__ == "__main__":
    main()