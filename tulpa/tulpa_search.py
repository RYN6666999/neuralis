#!/usr/bin/env python3
"""tulpa_search — 被動知識搜尋（按需加載）。

切割自 tulpa_engine.py（947 行）。
純檔案操作 + ontology cache，無競爭邏輯。
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

from tulpa.tulpa_db import _db

KNOWLEDGE_ROOTS = [
    os.path.expanduser("~/Desktop/房多多"),
    os.path.expanduser("~/Downloads"),
]


def _search_files(keyword: str) -> list:
    """在 KNOWLEDGE_ROOTS 下找檔名包含 keyword 的檔案。"""
    found = []
    for root in KNOWLEDGE_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if keyword.lower() in f.lower() and f.endswith((".json", ".md", ".csv", ".txt")):
                    found.append(os.path.join(dirpath, f))
    return found[:5]


def _read_head(path: str, max_chars: int = 2000) -> str:
    """讀檔案前 max_chars 字元。失敗時記錄錯誤。"""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception as e:
        print(f"[tulpa] ⚠️ _read_head 失敗: {path} — {e}", file=sys.stderr)
        return ""


def passive_search(text: str, _turn_counter: int = 0, _session_id: str = "") -> dict:
    """根據輸入文字搜尋相關知識檔案。

    先查 ontology cache，沒有再從檔案系統搜尋，找到後建立記錄。
    """
    triggers = ["C單", "c單", "房多多", "產品", "學費", "提貨", "報名",
                "謄本", "聯徵", "客戶", "定價", "名單", "CRM"]
    matched_kw = None
    for kw in triggers:
        if kw in text:
            matched_kw = kw
            break
    if not matched_kw:
        return {"found": False, "content": "", "paths": []}

    db = _db()
    rows = db.execute(
        "SELECT target, strength, hits FROM ontology "
        "WHERE source=? AND relation='keyword→file' ORDER BY strength DESC LIMIT 3",
        (matched_kw,)
    ).fetchall()

    if rows and rows[0]["strength"] > 0.5:
        path = rows[0]["target"]
        content = _read_head(path)
        db.close()
        if content:
            return {"found": True, "content": content, "paths": [path]}

    paths = _search_files(matched_kw)
    if not paths:
        db.close()
        return {"found": False, "content": "", "paths": []}

    content_parts = []
    for p in paths:
        head = _read_head(p)
        if head:
            content_parts.append(f"--- {p} ---\n{head}")
    content = "\n\n".join(content_parts[:2])

    now = datetime.utcnow().isoformat()
    for p in paths[:1]:
        db.execute("""
            INSERT INTO ontology (source, relation, target, strength, hits, last_seen, last_turn)
            VALUES (?, 'keyword→file', ?, 0.5, 1, '', ?)
            ON CONFLICT(source, relation, target) DO UPDATE SET
                strength=MIN(1.0, strength+0.05), hits=hits+1, last_turn=excluded.last_turn
        """, (matched_kw, p, _turn_counter))
    db.commit()
    db.close()

    return {"found": True, "content": content, "paths": paths}