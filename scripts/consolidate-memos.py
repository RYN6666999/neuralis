#!/usr/bin/env python3
"""夜班笨固化 — Scream memos → gbrain `mem/YYYY-MM-DD`。

為什麼「笨」是刻意的：
  海馬→皮質固化的完整設計要求「抽語義 + 過三繩 + confidence 判斷」，卡了三個月。
  這支不抽取、不叫 LLM、不判斷可信度 —— 原文搬過去，日期分頁。
  不做語義抽取就不會幻覺；不幻覺就不需要三繩。
  想升級抽取時資料已經在 gbrain 裡了，不會白做。

冪等：每次重建整天的頁面（不是 append），所以重跑不會長出重複。
可逆：`gbrain delete mem/YYYY-MM-DD` 即還原，原始 memos 沒被動過。
watermark（~/.aris-consolidate.json）只用來決定「哪幾天要重建」，不影響正確性。

用法：
    consolidate-memos.py [--dry-run] [--since YYYY-MM-DD] [--all]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

MEMOS_DB = os.environ.get(
    "ARIS_MEMOS_DB", str(Path.home() / ".scream-code/memory/memos.sqlite"))
STATE = Path(os.environ.get(
    "ARIS_CONSOLIDATE_STATE", str(Path.home() / ".aris-consolidate.json")))
GBRAIN = os.environ.get("GBRAIN_BIN", "gbrain")

_NONE = {"", "none", "n/a", "無", "沒有"}


def _clean(v: str | None) -> str:
    v = (v or "").strip()
    return "" if v.lower() in _NONE else v


def load_watermark() -> int:
    try:
        return int(json.loads(STATE.read_text()).get("last_recorded_at", 0))
    except Exception:
        return 0


def save_watermark(ms: int) -> None:
    STATE.write_text(json.dumps({"last_recorded_at": int(ms),
                                 "updated_at": dt.datetime.now().isoformat()}))


def fetch(since_ms: int) -> list[tuple]:
    """撈 what_worked 非空的 memos。只有『學到東西』的才值得固化。"""
    db = sqlite3.connect(f"file:{MEMOS_DB}?mode=ro", uri=True)
    try:
        return db.execute(
            "SELECT recorded_at, user_need, approach, outcome, what_worked, "
            "what_failed, project_dir FROM memos "
            "WHERE recorded_at > ? AND what_worked IS NOT NULL AND TRIM(what_worked) != '' "
            "ORDER BY recorded_at", (since_ms,)).fetchall()
    finally:
        db.close()


def day_of(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000).date().isoformat()


def render(day: str, rows: list[tuple]) -> str:
    """整天一頁。原文搬運，不改寫、不摘要。"""
    out = [f"# mem/{day}", "",
           "> Scream session 的工程經驗，由 `consolidate-memos.py` 夜班原文搬運。",
           "> 未經語義抽取，未過三繩驗證 —— 這是海馬層原始事件，不是皮質層結論。", ""]
    for ms, need, approach, outcome, worked, failed, proj in rows:
        t = dt.datetime.fromtimestamp(ms / 1000).strftime("%H:%M")
        out.append(f"## {t} · {_clean(need) or '(無標題)'}")
        for label, val in (("做法", approach), ("結果", outcome),
                           ("有效", worked), ("失敗", failed)):
            v = _clean(val)
            if v:
                out.append(f"- **{label}：** {v}")
        p = _clean(proj)
        if p:
            out.append(f"- **專案：** `{p}`")
        out.append("")
    return "\n".join(out)


def put(slug: str, body: str) -> None:
    subprocess.run([GBRAIN, "put", slug], input=body.encode(),
                   check=True, capture_output=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since", help="YYYY-MM-DD，覆蓋 watermark")
    ap.add_argument("--all", action="store_true", help="無視 watermark，重建全部")
    a = ap.parse_args(argv)

    if a.all:
        since = 0
    elif a.since:
        since = int(dt.datetime.fromisoformat(a.since).timestamp() * 1000)
    else:
        since = load_watermark()

    new_rows = fetch(since)
    if not new_rows:
        print(f"沒有新的可固化 memos（watermark={since}）")
        return 0

    # 只有「有新資料的那幾天」要重建，但重建時撈那天的全部（冪等）。
    days = sorted({day_of(r[0]) for r in new_rows})
    all_rows = fetch(0)
    by_day: dict[str, list[tuple]] = {}
    for r in all_rows:
        by_day.setdefault(day_of(r[0]), []).append(r)

    for day in days:
        rows = by_day.get(day, [])
        body = render(day, rows)
        slug = f"mem/{day}"
        if a.dry_run:
            print(f"[dry-run] {slug} ← {len(rows)} 筆 / {len(body)} 字元")
            continue
        try:
            put(slug, body)
            print(f"✅ {slug} ← {len(rows)} 筆")
        except subprocess.CalledProcessError as e:
            print(f"❌ {slug}: {e.stderr.decode()[:200]}", file=sys.stderr)
            return 1

    if not a.dry_run:
        save_watermark(max(r[0] for r in new_rows))
    print(f"固化 {len(days)} 天 / {len(new_rows)} 筆新記錄"
          + ("（dry-run，未寫入）" if a.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
