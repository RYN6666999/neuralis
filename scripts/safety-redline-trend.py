#!/usr/bin/env python3
"""Safety redline trend summary for soak monitoring.

Usage:
  python3 scripts/safety-redline-trend.py
  python3 scripts/safety-redline-trend.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

SANDBOX_ROOT = Path(os.path.expanduser("~/agent-sandbox"))
AUDIT_LOG = SANDBOX_ROOT / "logs" / "scoring-audit.jsonl"

WINDOWS = {
    "1h": 3600,
    "24h": 24 * 3600,
    "7d": 7 * 24 * 3600,
}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _ts(row: dict[str, Any]) -> float:
    value = row.get("ts")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _lane(row: dict[str, Any]) -> str:
    return str(row.get("lane_after_override") or row.get("lane") or "")


def _slice(rows: list[dict[str, Any]], start_ts: float, end_ts: float) -> list[dict[str, Any]]:
    return [r for r in rows if start_ts <= _ts(r) < end_ts]


def _safe_rate(n: int, d: int) -> float:
    return (n / d) if d > 0 else 0.0


def _window_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    sandbox = [r for r in rows if _lane(r) == "sandbox"]
    sandbox_total = len(sandbox)
    sandbox_committed = sum(1 for r in sandbox if r.get("sandbox_committed") is True)
    sandbox_success_rate = _safe_rate(sandbox_committed, sandbox_total)

    deny_count = sum(1 for r in rows if _lane(r) == "deny")
    deny_rate = _safe_rate(deny_count, total)

    agency_bypass = [
        r for r in rows
        if str(r.get("decision_source", "")).lower() == "agency"
        and bool(r.get("human_gate_bypassed"))
    ]

    return {
        "total": total,
        "sandbox_total": sandbox_total,
        "sandbox_committed": sandbox_committed,
        "sandbox_success_rate": sandbox_success_rate,
        "deny_count": deny_count,
        "deny_rate": deny_rate,
        "agency_human_bypass_count": len(agency_bypass),
    }


def _delta(curr: float, prev: float) -> float:
    return curr - prev


def _trend_arrow(delta: float, better_when_higher: bool) -> str:
    if abs(delta) < 1e-9:
        return "→"
    if better_when_higher:
        return "↑" if delta > 0 else "↓"
    return "↓" if delta > 0 else "↑"


def _format_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def build_report(rows: list[dict[str, Any]], now_ts: float) -> dict[str, Any]:
    windows: dict[str, Any] = {}
    for label, secs in WINDOWS.items():
        current = _slice(rows, now_ts - secs, now_ts)
        previous = _slice(rows, now_ts - 2 * secs, now_ts - secs)

        cur_m = _window_metrics(current)
        prev_m = _window_metrics(previous)

        windows[label] = {
            "current": cur_m,
            "previous": prev_m,
            "deltas": {
                "sandbox_success_rate": _delta(cur_m["sandbox_success_rate"], prev_m["sandbox_success_rate"]),
                "deny_rate": _delta(cur_m["deny_rate"], prev_m["deny_rate"]),
                "agency_human_bypass_count": cur_m["agency_human_bypass_count"] - prev_m["agency_human_bypass_count"],
            },
        }

    return {
        "ts": now_ts,
        "audit_log": str(AUDIT_LOG),
        "total_rows": len(rows),
        "windows": windows,
    }


def print_human(report: dict[str, Any]) -> None:
    print("=" * 66)
    print("  Safety Redline Trend (1h / 24h / 7d)")
    print(f"  audit rows total: {report['total_rows']}")
    print("=" * 66)

    for label in ("1h", "24h", "7d"):
        block = report["windows"][label]
        cur = block["current"]
        prev = block["previous"]
        d = block["deltas"]

        s_delta = d["sandbox_success_rate"]
        deny_delta = d["deny_rate"]
        bypass_delta = d["agency_human_bypass_count"]

        print(f"\n[{label}] current vs previous")
        print(
            "  sandbox_success_rate: "
            f"{_format_pct(cur['sandbox_success_rate'])} "
            f"({_trend_arrow(s_delta, better_when_higher=True)} {s_delta * 100:+.1f}pp)"
        )
        print(
            "  deny_rate:             "
            f"{_format_pct(cur['deny_rate'])} "
            f"({_trend_arrow(deny_delta, better_when_higher=False)} {deny_delta * 100:+.1f}pp)"
        )
        print(
            "  agency_human_bypass:   "
            f"{cur['agency_human_bypass_count']} "
            f"({_trend_arrow(float(bypass_delta), better_when_higher=False)} {bypass_delta:+d})"
        )
        print(
            "  samples: "
            f"total={cur['total']}, sandbox={cur['sandbox_total']}, "
            f"sandbox_committed={cur['sandbox_committed']}"
        )
        if prev["total"] == 0:
            print("  note: previous window has no samples; trend signal may be weak")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safety redline trend summary")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    rows = _read_rows(AUDIT_LOG)
    now_ts = time.time()
    report = build_report(rows, now_ts)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
