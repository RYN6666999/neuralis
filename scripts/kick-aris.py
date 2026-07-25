#!/usr/bin/env python3
"""kick-aris.py — 從 Scream 踢 Aris 一腳，推送訊息/任務給 Aris。

用法:
  python3 kick-aris.py "你好嗎"              # 一般問候
  python3 kick-aris.py --ask "今天英超賽程"   # 問問題
  python3 kick-aris.py --task "讀取 README"   # 委派任務
  python3 kick-aris.py --wait "今天幾號"      # 推訊息並等回應

將訊息寫入 aris-scream-channel（供 timeline 記錄），
同時直接呼叫 Aris API 確保 Aris 即時收到。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

CHANNEL = "/tmp/aris-scream-channel.jsonl"
ARIS_API = "http://localhost:11546/v1/chat/completions"
ARIS_HEALTH = "http://localhost:11546/health"
TIMEOUT = 30


def check_aris_alive() -> bool:
    """確認 Aris API 在線。"""
    try:
        req = urllib.request.Request(ARIS_HEALTH)
        resp = urllib.request.urlopen(req, timeout=3)
        return resp.status == 200
    except Exception:
        return False


def write_to_channel(msg: str, msg_type: str = "request") -> str:
    """寫入通道（記錄用）。"""
    entry_id = uuid.uuid4().hex[:12]
    entry = {
        "ts": time.time(),
        "id": entry_id,
        "direction": "scream→aris",
        "type": msg_type,
        "content": msg[:500],
        "context": {"source": "scream-kick"},
    }
    try:
        with open(CHANNEL, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️  寫入通道失敗: {e}", file=sys.stderr)
    return entry_id


def send_to_aris(msg: str, quiet: bool = False) -> dict | None:
    """直接呼叫 Aris API 推送訊息。"""
    payload = json.dumps({
        "model": "laap-core",
        "messages": [
            {"role": "system",
             "content": "Scream 踢了你一腳。用心回應。請以中文回答。"},
            {"role": "user", "content": msg},
        ],
        "max_tokens": 500,
        "stream": False,
    }).encode()
    try:
        req = urllib.request.Request(
            ARIS_API, data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        data = json.loads(resp.read().decode())
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "（無回應）")
        )
        return {"success": True, "content": content}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        return {"success": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


def read_reply_from_channel(entry_id: str, wait_s: float = 15.0) -> str | None:
    """從通道讀取 Aris 對應的回應（輪詢）。"""
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            if not Path(CHANNEL).exists():
                time.sleep(0.5)
                continue
            with open(CHANNEL) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (entry.get("direction") == "aris→scream"
                            and entry.get("type") in ("response", "result")
                            and entry.get("context", {}).get("request_id") == entry_id):
                        return entry.get("content", "（無內容）")
                    # Also check by matching id pattern in context
                    ctx = entry.get("context", {})
                    if (entry.get("direction") == "aris→scream"
                            and isinstance(ctx, dict)
                            and ctx.get("source") == "scream-kick"
                            and ctx.get("kick_id") == entry_id):
                        return entry.get("content", "（無內容）")
            time.sleep(0.3)
        except Exception:
            time.sleep(0.5)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="踢 Aris 一腳 — 推送訊息/任務給 Aris",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "範例:\n"
            "  kick-aris.py 你好嗎\n"
            "  kick-aris.py --ask 今天英超賽程\n"
            "  kick-aris.py --task '讀取 ~/test.txt'\n"
            "  kick-aris.py --wait '現在幾點'\n"
        ),
    )
    parser.add_argument("message", nargs="*", help="要傳給 Aris 的訊息")
    parser.add_argument("--ask", "-a", nargs="*", help="問 Aris 問題")
    parser.add_argument("--task", "-t", nargs="*", help="委派任務給 Aris")
    parser.add_argument("--wait", "-w", nargs="?", const=True, default=False, help="推訊息並等待回應")
    parser.add_argument("--quiet", "-q", action="store_true", help="安靜模式，只輸出回應")

    args = parser.parse_args()
    # 優先順序：--ask > --task > --wait 值 > 位置引數
    if args.ask is not None:
        raw = args.ask
    elif args.task is not None:
        raw = args.task
    elif args.wait is not False and args.wait is not True:
        raw = [args.wait]  # --wait 有給字串值
    else:
        raw = args.message

    if not raw or (isinstance(raw, list) and not raw):
        parser.print_help()
        sys.exit(1)

    msg = " ".join(raw) if isinstance(raw, list) else str(raw)
    msg_type = "task" if args.task is not None else "request"

    # 確認 Aris 活著
    if not check_aris_alive():
        print("⚠️  Aris API 不在線（:11546），無法傳送。先確認 Aris 已啟動。")
        sys.exit(1)

    # 寫入通道（記錄用）
    entry_id = write_to_channel(msg, msg_type)

    # 推送給 Aris
    if not args.quiet:
        print(f"👟 踢 Aris 一腳... ({entry_id[:8]})")
        print(f"   📤 {msg[:80]}{'…' if len(msg) > 80 else ''}")

    result = send_to_aris(msg, quiet=args.quiet)

    if args.wait is not False and args.wait is not None:
        # --wait 模式：等回應
        if result and result.get("success"):
            content = result.get("content", "")
            print(f"\n💬 Aris:\n{content}")
        else:
            err = result.get("error", "不明錯誤") if result else "無回應"
            print(f"\n❌ Aris 回應失敗: {err}")
            # fallback: 等通道回應
            print("   嘗試從通道輪詢...")
            reply = read_reply_from_channel(entry_id, wait_s=10)
            if reply:
                print(f"💬 Aris (通道):\n{reply}")
    elif args.quiet:
        if result and result.get("success"):
            print(result.get("content", ""))
        else:
            print(f"❌ {result.get('error', '不明錯誤')}")
    else:
        if result and result.get("success"):
            content = result.get("content", "")
            print(f"✅ Aris 已接收")
            print(f"   💬 {content[:200]}{'…' if len(content) > 200 else ''}")
        else:
            print(f"⚠️  已寫入通道但 API 呼叫失敗: {result.get('error', '不明')}")
            print("   Aris 下次輪詢通道時會收到。")


if __name__ == "__main__":
    main()