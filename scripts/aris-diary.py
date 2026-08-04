#!/usr/bin/env python3
"""Aris 內心日記 — 寫到本機檔案，不經 gbrain

使用方式：
    python3 scripts/aris-diary.py "今天學到了 scoring router 的分數算法"
"""
import json, os, sys, time
from pathlib import Path

DIARY_DIR = Path.home() / ".aris-diary"
DIARY_FILE = DIARY_DIR / "entries.jsonl"
MAX_ENTRIES = 500


def write_diary(content: str) -> dict:
    """寫一句日記到本機檔案。"""
    ts = time.strftime("%Y-%m-%d %H:%M")
    DIARY_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"ts": ts, "content": content, "epoch": int(time.time())}
    try:
        with open(DIARY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # 修剪過多條目
        lines = DIARY_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_ENTRIES:
            DIARY_FILE.write_text("\n".join(lines[-MAX_ENTRIES:]) + "\n", encoding="utf-8")
        return {"status": "ok", "entry": entry}
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