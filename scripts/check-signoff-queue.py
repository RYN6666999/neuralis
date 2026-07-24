#!/usr/bin/env python3
"""Inspect pending Ryan signoff queue for scoring-router ratchet.

Output:
- Pending task classes that require signoff
- Latest rejection reason (if available)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SANDBOX_ROOT = Path.home() / "agent-sandbox"
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Ryan signoff queue")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print queue as JSON (dashboard-ready)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Write JSON output to file path (implies --json)",
    )
    args = parser.parse_args()

    try:
        from router.ratchet import get_signoff_queue, _RATCHET_NAMESPACE  # type: ignore
    except Exception as exc:
        print(f"FAIL import ratchet helpers: {exc}")
        return 1

    queue = get_signoff_queue()

    payload = {
        "namespace": _RATCHET_NAMESPACE,
        "pending_count": len(queue),
        "pending": queue,
    }

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote signoff queue JSON: {out}")
        return 0

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("=== Ryan Signoff Queue ===")
    print(f"namespace: {_RATCHET_NAMESPACE}")
    print(f"pending: {len(queue)}")

    if not queue:
        print("no pending signoff tasks")
        return 0

    for item in queue:
        print("-")
        print(f"task_class: {item['task_class']}")
        print(f"level: {item['level']}")
        print(f"needs_signoff: {item['needs_signoff']}")
        print(f"pass_rate: {item['pass_rate']}")
        print(f"confidence_lower_bound: {item['confidence_lower_bound']}")
        print(f"verified_count: {item['verified_count']}  failed_count: {item['failed_count']}")
        print(f"last_verified_at: {item['last_verified_at']}")
        print(f"last_reject_ts: {item['last_reject_ts']}")
        print(f"last_reject_reason: {item['last_reject_reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
