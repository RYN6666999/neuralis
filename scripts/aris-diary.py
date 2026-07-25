#!/usr/bin/env python3
"""Aris 內心日記 — 每次 tick 寫一句話到 gbrain

Agency 每 ~60 秒 tick 一次時，順便寫一兩句話到 gbrain 頁面。
下次喚醒時 Aris 可以讀到「上一次的我正在想什麼」。

使用方式：
    python3 scripts/aris-diary.py "今天學到了 scoring router 的分數算法"

手動寫：
    python3 scripts/aris-diary.py "我在思考 competence 和 autonomy 的平衡⋯⋯"
"""
import json, os, sys, time
from pathlib import Path

LAAP_ROOT = Path.home() / "Developer/laap-AGI"
sys.path.insert(0, str(LAAP_ROOT))
GBRAIN_SCRIPT = LAAP_ROOT / "mcp_server" / "gbrain_client.py"
DIARY_PAGE = "aris-inner-diary"

def write_diary(content: str) -> dict:
    """寫一句日記到 gbrain。"""
    ts = time.strftime("%Y-%m-%d %H:%M")
    entry = f"[{ts}] {content}"
    try:
        from gbrain_client import GbrainClient
        client = GbrainClient()
        # 先讀現有日記
        existing = client.get_page(DIARY_PAGE) or ""
        new_content = existing + "\n" + entry if existing else entry
        # 只保留最近 50 條
        lines = new_content.strip().split("\n")[-50:]
        final = "\n".join(lines)
        result = client.put_page(DIARY_PAGE, final)
        return {"status": "ok", "entry": entry, "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 aris-diary.py '你的日記內容'")
        sys.exit(1)
    content = " ".join(sys.argv[1:])
    result = write_diary(content)
    if result["status"] == "ok":
        print(f"📝 {result['entry']}")
    else:
        print(f"❌ {result['error']}")