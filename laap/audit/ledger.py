"""稽核軌跡：append-only JSONL。

這是整套東西唯一的產出。舊版把 `[審計報告]` 拼成字串後回傳，而呼叫端沒有
接住回傳值 —— 報告落地即蒸發，等於沒有稽核。這裡改成：**先落盤，再談別的**。
只要 `audit_text()` 跑過，不管結果是 PASS / FAIL / INVALID，磁碟上一定留一行。

寫入是 best-effort（稽核不該把 Aris 弄掛），但失敗會寫 stderr，不靜默。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_LEDGER = Path.home() / "Developer" / "neuralis" / "data" / "audit-ledger.jsonl"


def ledger_path() -> Path:
    """允許用環境變數改路徑，測試就不必碰真的 ledger。"""
    override = os.environ.get("LAAP_AUDIT_LEDGER")
    if override:
        return Path(os.path.expanduser(override))
    return DEFAULT_LEDGER


def append(record: Dict[str, Any], path: Optional[Path] = None) -> bool:
    """寫一行 JSONL。回傳是否成功寫入。"""
    target = path or ledger_path()
    row = dict(record)
    row.setdefault("ts", datetime.now(timezone.utc).isoformat())

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 - 稽核不該讓主流程掛掉
        print(f"[laap.audit] ledger 寫入失敗 {target}: {exc}", file=sys.stderr, flush=True)
        return False
