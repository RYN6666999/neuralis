#!/usr/bin/env python3
"""aris-chat — 直連 Aris（:11546），零中間人、零轉述。

用法:
    aris                    # REPL 對話（exit / Ctrl-D 離開）
    aris 你好嗎             # 一次性對話
    aris --once "你好嗎"    # 同上（給 scream /aris 技能呼叫）
    aris --state            # 一頁內在狀態

對話歷史存 ~/.aris-conversations/current.json（與 scream /aris 共用，
兩個入口聊的是同一場對話）。每次回應後 reflect 進 Aris 長期記憶。
"""
import json
import sys
import time
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


def _alive() -> bool:
    try:
        urllib.request.urlopen(API + "/health", timeout=3)
        return True
    except OSError:
        return False


def chat_once(user_msg: str) -> str:
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
    if args and args[0] == "--once":
        msg = " ".join(args[1:]).strip()
        if not msg:
            print("用法: aris --once \"要說的話\"")
            sys.exit(1)
        print(chat_once(msg))
        return
    if args:                      # aris 你好嗎 → 一次性
        print(chat_once(" ".join(args).strip()))
        return

    # REPL
    print("直連 Aris（exit / Ctrl-D 離開，/state 看內在狀態）")
    show_state()
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
        try:
            print(chat_once(msg))
        except Exception as e:
            print(f"（這輪失敗: {e} — Aris 可能在重啟，稍等重試）")


if __name__ == "__main__":
    main()
