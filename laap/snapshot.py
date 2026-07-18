"""commit 級快照 — 自主寫入前的還原點（安全脊椎 Stage 0，協定鐵律 2）。

任何自動放行的改動前建快照，壞了一鍵 revert。用 `git stash create` 捕捉當前
工作樹（不改動工作樹本身），回一個 commit SHA；工作樹乾淨時退回 HEAD SHA。
`restore` 把 tracked 檔還原到該 SHA。

ponytail: 只還原 tracked 檔內容；快照後「新增」的檔不會被刪、快照前「已刪」的
檔不會被復原（完整還原是升級路徑，可改 reflog / worktree）。cwd 參數讓測試用
temp repo，不碰真 repo。
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Optional

_AUDIT = Path(__file__).resolve().parents[1] / "snapshot-audit.jsonl"


def _git(args: list, cwd: Optional[str] = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


def create_snapshot(reason: str, cwd: Optional[str] = None) -> str:
    """建還原點，回 commit SHA。工作樹髒 → stash-create 捕捉；乾淨 → HEAD。"""
    sha = _git(["stash", "create"], cwd=cwd)
    if not sha:                      # 乾淨工作樹，無可 stash
        sha = _git(["rev-parse", "HEAD"], cwd=cwd)
    _audit(sha, reason, cwd)
    return sha


def restore_snapshot(sha: str, cwd: Optional[str] = None) -> None:
    """把 tracked 檔還原到快照 SHA 的狀態。"""
    _git(["checkout", sha, "--", "."], cwd=cwd)


def _audit(sha: str, reason: str, cwd: Optional[str]) -> None:
    audit = (Path(cwd) / "snapshot-audit.jsonl") if cwd else _AUDIT
    try:
        with audit.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "sha": sha,
                                "reason": reason[:120]}, ensure_ascii=False) + "\n")
    except Exception:
        pass
