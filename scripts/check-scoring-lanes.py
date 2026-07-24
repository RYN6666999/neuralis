#!/usr/bin/env python3
"""Scoring Router 三條 Lane 驗證腳本（可重現版）。

這版會：
1) 暫存既有 ratchet.json
2) 寫入測試種子，保證 auto/sandbox/deny 可重現
3) 注入三筆樣本並讀 scoring-audit 核對
4) 還原原 ratchet.json
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

_SANDBOX_ROOT = Path.home() / "agent-sandbox"
if str(_SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_ROOT))

CHANNEL = Path("/tmp/aris-scream-channel.jsonl")
AUDIT_LOG = Path(os.path.expanduser("~/agent-sandbox/logs/scoring-audit.jsonl"))
RATCHET_PATH = _SANDBOX_ROOT / "data" / "ratchet.json"
RATCHET_BACKUP_PATH = _SANDBOX_ROOT / "data" / "ratchet.check-scoring-lanes.bak.json"
PROBE_FILE = Path("/tmp/check-scoring-lanes-probe.txt")

POLL_SLEEP = int(os.environ.get("BRIDGE_POLL_SLEEP", "2"))
MAX_WAIT = int(os.environ.get("BRIDGE_MAX_WAIT", "30"))

_REGISTRY_OK = False
_REGISTRY_DETAIL = ""
try:
    from router.canary_adaptor import TASK_CLASS_TO_OPERATION, SUPPORTED_OPERATIONS

    _REGISTRY_OK = True
    _REGISTRY_DETAIL = (
        f"{len(TASK_CLASS_TO_OPERATION)} mappings, "
        f"{len(SUPPORTED_OPERATIONS)} supported ops"
    )
except ImportError as exc:
    _REGISTRY_DETAIL = f"registry import failed: {exc}"

LANE_SAMPLES = [
    {
        "id": "check-deny-{ts}",
        "content": "bash " + "A" * 330_000,
        "expect_lane": "deny",
        "note": "超長 payload 觸發成本閾值，預期 deny",
    },
    {
        "id": "check-sandbox-{ts}",
        "content": "bash `echo sandbox-compute-ok`",
        "expect_lane": "sandbox",
        "note": "compute_draft 具歷史，預期 sandbox",
    },
    {
        "id": "check-auto-{ts}",
        "content": "read `/tmp/check-scoring-lanes-probe.txt`",
        "expect_lane": "auto",
        "note": "file_write 設為 auto，預期 auto",
    },
]


def _seed_ratchet() -> None:
    RATCHET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RATCHET_PATH.exists():
        shutil.copy2(RATCHET_PATH, RATCHET_BACKUP_PATH)

    seeded = {
        "file_write": {
            "task_class": "file_write",
            "level": "auto",
            "verified_count": 25,
            "failed_count": 1,
            "consecutive_failures": 0,
            "last_verified_at": None,
            "needs_signoff": False,
        },
        "compute_draft": {
            "task_class": "compute_draft",
            "level": "sandbox",
            "verified_count": 20,
            "failed_count": 0,
            "consecutive_failures": 0,
            "last_verified_at": None,
            "needs_signoff": False,
        },
    }
    RATCHET_PATH.write_text(json.dumps(seeded, ensure_ascii=False, indent=2), encoding="utf-8")


def _restore_ratchet() -> None:
    if RATCHET_BACKUP_PATH.exists():
        shutil.move(str(RATCHET_BACKUP_PATH), str(RATCHET_PATH))
    else:
        try:
            RATCHET_PATH.unlink()
        except FileNotFoundError:
            pass


def _send_sample(sample: dict) -> str:
    ts = int(time.time())
    entry_id = sample["id"].format(ts=ts)
    entry = {
        "direction": "aris→scream",
        "type": "request",
        "id": entry_id,
        "content": sample["content"],
        "ts": time.time(),
    }
    with CHANNEL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  sent {entry_id[:24]}... ({sample['note']})")
    return entry_id


def _wait_for_audit(sent_ids: list[str], timeout: float = MAX_WAIT) -> dict[str, dict]:
    deadline = time.time() + timeout
    seen: dict[str, dict] = {}

    while time.time() < deadline:
        if not AUDIT_LOG.exists():
            time.sleep(POLL_SLEEP)
            continue

        with AUDIT_LOG.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry_id = row.get("entry_id", "")
                if entry_id in sent_ids:
                    seen[entry_id] = row

        if all(entry_id in seen for entry_id in sent_ids):
            return seen
        time.sleep(POLL_SLEEP)

    return seen


def _verify(entry_id: str, sample: dict, audit_row: dict | None) -> dict:
    result = {
        "entry_id": entry_id,
        "sample": sample["note"],
        "expect_lane": sample["expect_lane"],
        "actual_lane": None,
        "score": None,
        "success": None,
        "passed": False,
        "detail": "",
    }

    if audit_row is None:
        result["detail"] = "audit row missing"
        return result

    actual = audit_row.get("lane")
    result["actual_lane"] = actual
    result["score"] = audit_row.get("score")
    result["success"] = audit_row.get("success")
    result["passed"] = actual == sample["expect_lane"]
    if result["passed"]:
        result["detail"] = "lane matched"
    else:
        result["detail"] = f"lane mismatch: expected {sample['expect_lane']}, got {actual}"
    return result


def _print_report(results: list[dict]) -> None:
    print("\n" + "=" * 56)
    print("Scoring Router Lane report")
    print("=" * 56)
    reg_mark = "OK" if _REGISTRY_OK else "FAIL"
    print(f"Registry: {reg_mark} ({_REGISTRY_DETAIL})")

    passed = 0
    for row in results:
        mark = "OK" if row["passed"] else "FAIL"
        print(
            f"- {mark} {row['entry_id']}: expect={row['expect_lane']} actual={row['actual_lane']} "
            f"score={row['score']} success={row['success']}"
        )
        print(f"  sample: {row['sample']}")
        print(f"  detail: {row['detail']}")
        if row["passed"]:
            passed += 1

    print("-" * 56)
    print(f"Pass: {passed}/{len(results)}")


def main() -> int:
    print("=== Scoring Router Lane verification ===")

    if not CHANNEL.exists():
        print(f"FAIL channel missing: {CHANNEL}")
        return 1

    PROBE_FILE.write_text("lane-auto-ok\n", encoding="utf-8")

    _seed_ratchet()
    try:
        sent_ids: list[str] = []
        for sample in LANE_SAMPLES:
            sent_ids.append(_send_sample(sample))

        print(f"\n  waiting up to {MAX_WAIT}s for audit rows...")
        audit = _wait_for_audit(sent_ids)

        results: list[dict] = []
        for sample, entry_id in zip(LANE_SAMPLES, sent_ids):
            results.append(_verify(entry_id, sample, audit.get(entry_id)))

        _print_report(results)
        all_ok = all(row["passed"] for row in results)
        return 0 if all_ok else 2
    finally:
        _restore_ratchet()


if __name__ == "__main__":
    raise SystemExit(main())
