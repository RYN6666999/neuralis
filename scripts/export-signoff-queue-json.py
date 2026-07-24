#!/usr/bin/env python3
"""Export Ryan signoff queue into a fixed JSON file for dashboards.

Default output: /tmp/agentos-signoff-queue.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SANDBOX_ROOT = Path.home() / "agent-sandbox"
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))

OUT_PATH = Path("/tmp/agentos-signoff-queue.json")


def main() -> int:
    try:
        from router.ratchet import get_signoff_queue, _RATCHET_NAMESPACE  # type: ignore
    except Exception as exc:
        print(f"FAIL import ratchet helpers: {exc}")
        return 1

    queue = get_signoff_queue()
    payload = {
        "ts": __import__("time").time(),
        "namespace": _RATCHET_NAMESPACE,
        "pending_count": len(queue),
        "pending": queue,
    }

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported: {OUT_PATH}")
    print(f"pending_count: {len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
