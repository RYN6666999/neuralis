#!/usr/bin/env python3
"""tulpa_lesson — 教訓載入器（可拔插型態，仿 data/genes 基因庫）。

每顆教訓一個獨立 JSON 檔，丟進 data/lessons/，掃目錄載入。
刪檔 = 下線（不影響其他教訓與其他系統）。
本模組提供 load_all / get_active / verify 三件事。

JSON 格式（一顆一檔）:
{
  "lesson_id": "L-xxx",
  "title": "...",
  "dimension": "learned",
  "body": "一句可執行教訓",
  "predicted_failure": "最可能哪裡出錯（事前押注）",
  "one_sec_verify": "可跑檢查指令(偽造成本>真實成本)",
  "trigger": ["觸發情境", "關鍵字"],
  "outcome": "pending|success|fail|unverifiable",
  "outcome_evidence": "",
  "active": true,
  "created_at": "..."
}
"""
from __future__ import annotations
import json
import subprocess
import shlex
from pathlib import Path
from datetime import datetime

LESSON_DIR = Path.home() / "Developer/neuralis/data/lessons"


def load_all() -> list[dict]:
    """掃 data/lessons/*.json，回傳所有教訓 dict 列表（檔案存在即載入）。"""
    if not LESSON_DIR.exists():
        return []
    lessons = []
    for f in sorted(LESSON_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data.setdefault("outcome", "pending")
            data.setdefault("outcome_evidence", "")
            data.setdefault("active", True)
            data.setdefault("trigger", [])
            data.setdefault("lesson_id", f.stem)
            lessons.append(data)
        except Exception:
            continue  # 單顆垃圾不擋其他教訓
    return lessons


def get_active() -> list[dict]:
    """回傳 active=True 的教訓（供注入）。"""
    return [l for l in load_all() if l.get("active", True)]


def verify(lesson: dict) -> dict:
    """一秒驗證機械化——執行 one_sec_verify 指令，exit code 當真值回寫 outcome。
    偽造成本>真實成本：不能嘴上說「驗證了」，要真跑出 exit code。"""
    cmd = (lesson.get("one_sec_verify") or "").strip()
    if not cmd:
        return {**lesson, "outcome": "unverifiable", "outcome_evidence": "無可執行檢查指令"}
    try:
        parts = shlex.split(cmd)
        if not parts:
            raise ValueError("empty")
        res = subprocess.run(parts, capture_output=True, timeout=10, text=True)
        ok = (res.returncode == 0)
        outcome = "success" if ok else "fail"
        ev = f"cmd={cmd} | exit={res.returncode} | {res.stdout.strip()[:60] or res.stderr.strip()[:60]}"
    except Exception as e:
        outcome = "unverifiable"
        ev = f"cmd={cmd} | 無法執行: {e}"
    return {**lesson, "outcome": outcome, "outcome_evidence": ev}


def save(lesson: dict) -> Path:
    """寫入/更新一顆教訓檔。同 lesson_id 覆寫，可拔插。"""
    LESSON_DIR.mkdir(parents=True, exist_ok=True)
    lid = lesson.get("lesson_id") or f"L-{int(datetime.now().timestamp())}"
    lesson["lesson_id"] = lid
    p = LESSON_DIR / f"{lid}.json"
    p.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# 匯入時若目錄不存在則建
LESSON_DIR.mkdir(parents=True, exist_ok=True)