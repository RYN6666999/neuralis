"""evolve_gate — Aris 演化閘門（2026-08-12，Ryan 拍板「可回退範圍內全面啟動」）。

原則：
- AGI kernel 的自主/演化/自癒引擎只有「提案權」，沒有「落地權」。
- 所有提案寫入 ~/Developer/neuralis/evolve-gate/tickets.jsonl（可審、可溯源、可回退）。
- approve 只標狀態並顯示內容；實際落地由人決定（--apply 走 git，可 revert）。
- 預設 zero auto-apply：閘門外的引擎永不改碼。

CLI：
  python -m laap.evolve_gate list | show <id> | approve <id> | reject <id> <reason>
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
import uuid
from pathlib import Path

logger = logging.getLogger("laap.evolve_gate")

GATE_DIR = Path(os.environ.get("EVOLVE_GATE_DIR", os.path.expanduser("~/Developer/neuralis/evolve-gate")))
TICKETS = GATE_DIR / "tickets.jsonl"


def _ensure() -> Path:
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    return TICKETS


def record(engine: str, kind: str, payload: dict | None = None, note: str = "") -> dict:
    """引擎產出 → 閘門佇列。只記錄，不落地。"""
    t = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "engine": engine,
        "kind": kind,
        "status": "pending",
        "note": note,
        "payload": payload or {},
    }
    p = _ensure()
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(t, ensure_ascii=False) + "\n")
    logger.info("[evolve_gate] %s/%s 提案入閘 %s", engine, kind, t["id"])
    return t


def _load() -> list[dict]:
    p = TICKETS
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def queue(status: str | None = None) -> list[dict]:
    ts = _load()
    if status:
        ts = [t for t in ts if t.get("status") == status]
    return ts


def show(tid: str) -> dict | None:
    for t in _load():
        if t["id"] == tid:
            return t
    return None


def update(tid: str, status: str, reason: str = "") -> bool:
    ts = _load()
    hit = False
    with open(TICKETS, "w", encoding="utf-8") as f:
        for t in ts:
            if t["id"] == tid:
                t["status"] = status
                if reason:
                    t["note"] = (t.get("note", "") + " | " + reason).strip(" |")
                hit = True
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return hit


def approve(tid: str) -> bool:
    return update(tid, "approved")


def reject(tid: str, reason: str = "rejected") -> bool:
    return update(tid, "rejected", reason)


def main() -> None:
    ap = argparse.ArgumentParser(description="Aris 演化閘門審查")
    ap.add_argument("cmd", choices=["list", "show", "approve", "reject"])
    ap.add_argument("id", nargs="?", default=None)
    ap.add_argument("reason", nargs="*", default=[])
    a = ap.parse_args()
    if a.cmd == "list":
        for t in queue():
            print("\n".join([
                f"[{t['id']}] {t['status']} {t['iso']} {t['engine']}/{t['kind']}",
                f"    note: {t.get('note','')}",
                f"    payload: {json.dumps(t['payload'], ensure_ascii=False)[:200]}",
            ]))
    elif a.cmd == "show" and a.id:
        t = show(a.id)
        print(json.dumps(t, ensure_ascii=False, indent=2) if t else f"票 {a.id} 不存在")
    elif a.cmd == "approve" and a.id:
        print("approved" if approve(a.id) else f"票 {a.id} 不存在")
    elif a.cmd == "reject" and a.id:
        print("rejected" if reject(a.id, " ".join(a.reason)) else f"票 {a.id} 不存在")


if __name__ == "__main__":
    main()
