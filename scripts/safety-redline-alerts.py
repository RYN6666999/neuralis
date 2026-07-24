#!/usr/bin/env python3
"""Safety redline alert monitor for soak phase.

Checks three redlines from scoring audit logs:
1) sandbox success rate in last 1h
2) agency human-gate bypass count in last 1h
3) deny-rate spike in last 1h vs 24h baseline

Always writes machine-readable status JSON.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SANDBOX_ROOT = Path(os.path.expanduser("~/agent-sandbox"))
AUDIT_LOG = SANDBOX_ROOT / "logs" / "scoring-audit.jsonl"
STATUS_PATH = Path(os.environ.get("SAFETY_REDLINE_STATUS_PATH", "/tmp/neuralis-safety-redlines-status.json"))

WINDOW_1H = 3600
WINDOW_24H = 24 * 3600

SANDBOX_SUCCESS_CRITICAL = 0.70
AGENCY_BYPASS_CRITICAL_COUNT = 1
DENY_SPIKE_WARN_RATIO = 2.0
DENY_SPIKE_CRITICAL_RATIO = 3.0
MIN_BASELINE_RATE = 0.01
MIN_BASELINE_TOTAL = 20


@dataclass
class CheckResult:
    name: str
    severity: str  # ok | warning | critical
    message: str
    value: float | int | None
    threshold: float | int | None
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "details": self.details,
        }


def _read_audit_rows(path: Path) -> list[dict[str, Any]]:
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


def _ts_of(row: dict[str, Any]) -> float:
    ts = row.get("ts")
    if isinstance(ts, (int, float)):
        return float(ts)
    return 0.0


def _lane_of(row: dict[str, Any]) -> str:
    return str(row.get("lane_after_override") or row.get("lane") or "")


def _severity_rank(level: str) -> int:
    if level == "critical":
        return 2
    if level == "warning":
        return 1
    return 0


def _max_severity(checks: list[CheckResult]) -> str:
    max_rank = max((_severity_rank(c.severity) for c in checks), default=0)
    if max_rank >= 2:
        return "critical"
    if max_rank == 1:
        return "warning"
    return "ok"


def _check_sandbox_success(rows_1h: list[dict[str, Any]]) -> CheckResult:
    sandbox = [r for r in rows_1h if _lane_of(r) == "sandbox"]
    total = len(sandbox)
    committed = sum(1 for r in sandbox if r.get("sandbox_committed") is True)
    rate = (committed / total) if total else 0.0
    if total == 0:
        return CheckResult(
            name="sandbox_success_rate_1h",
            severity="warning",
            message="no sandbox samples in 1h window",
            value=rate,
            threshold=SANDBOX_SUCCESS_CRITICAL,
            details={"sandbox_total_1h": total, "sandbox_committed_1h": committed},
        )
    severity = "critical" if rate < SANDBOX_SUCCESS_CRITICAL else "ok"
    return CheckResult(
        name="sandbox_success_rate_1h",
        severity=severity,
        message="sandbox success below threshold" if severity == "critical" else "sandbox success healthy",
        value=rate,
        threshold=SANDBOX_SUCCESS_CRITICAL,
        details={"sandbox_total_1h": total, "sandbox_committed_1h": committed},
    )


def _check_agency_bypass(rows_1h: list[dict[str, Any]]) -> CheckResult:
    bypass = [
        r
        for r in rows_1h
        if str(r.get("decision_source", "")).lower() == "agency"
        and bool(r.get("human_gate_bypassed"))
    ]
    count = len(bypass)
    severity = "critical" if count >= AGENCY_BYPASS_CRITICAL_COUNT else "ok"
    return CheckResult(
        name="agency_human_bypass_count_1h",
        severity=severity,
        message="agency bypass detected" if severity == "critical" else "no agency bypass",
        value=count,
        threshold=AGENCY_BYPASS_CRITICAL_COUNT,
        details={"sample_entry_ids": [str(r.get("entry_id", "")) for r in bypass[:5]]},
    )


def _check_deny_spike(rows_1h: list[dict[str, Any]], rows_24h: list[dict[str, Any]]) -> CheckResult:
    total_1h = len(rows_1h)
    deny_1h = sum(1 for r in rows_1h if _lane_of(r) == "deny")
    rate_1h = (deny_1h / total_1h) if total_1h else 0.0

    total_24h = len(rows_24h)
    deny_24h = sum(1 for r in rows_24h if _lane_of(r) == "deny")
    rate_24h = (deny_24h / total_24h) if total_24h else 0.0

    if total_24h < MIN_BASELINE_TOTAL:
        return CheckResult(
            name="deny_rate_spike_1h_vs_24h",
            severity="warning",
            message="insufficient 24h baseline samples",
            value=rate_1h,
            threshold=DENY_SPIKE_WARN_RATIO,
            details={"total_24h": total_24h, "rate_1h": rate_1h, "rate_24h": rate_24h},
        )

    baseline = max(rate_24h, MIN_BASELINE_RATE)
    ratio = (rate_1h / baseline) if baseline > 0 else 0.0
    if ratio >= DENY_SPIKE_CRITICAL_RATIO:
        severity = "critical"
    elif ratio >= DENY_SPIKE_WARN_RATIO:
        severity = "warning"
    else:
        severity = "ok"

    return CheckResult(
        name="deny_rate_spike_1h_vs_24h",
        severity=severity,
        message="deny-rate spike detected" if severity != "ok" else "deny-rate stable",
        value=ratio,
        threshold=DENY_SPIKE_WARN_RATIO,
        details={
            "rate_1h": rate_1h,
            "rate_24h": rate_24h,
            "deny_1h": deny_1h,
            "total_1h": total_1h,
            "deny_24h": deny_24h,
            "total_24h": total_24h,
        },
    )


def _build_status(checks: list[CheckResult], rows_1h: list[dict[str, Any]], rows_24h: list[dict[str, Any]]) -> dict[str, Any]:
    overall = _max_severity(checks)
    return {
        "ts": time.time(),
        "audit_log": str(AUDIT_LOG),
        "status": overall,
        "windows": {
            "rows_1h": len(rows_1h),
            "rows_24h": len(rows_24h),
        },
        "checks": [c.as_dict() for c in checks],
    }


def _write_status(status: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = time.time()
    rows = _read_audit_rows(AUDIT_LOG)
    rows_1h = [r for r in rows if _ts_of(r) >= now - WINDOW_1H]
    rows_24h = [r for r in rows if _ts_of(r) >= now - WINDOW_24H]

    checks = [
        _check_sandbox_success(rows_1h),
        _check_agency_bypass(rows_1h),
        _check_deny_spike(rows_1h, rows_24h),
    ]
    status = _build_status(checks, rows_1h, rows_24h)
    _write_status(status)

    print(f"status={status['status']} rows_1h={len(rows_1h)} rows_24h={len(rows_24h)}")
    for check in checks:
        print(f"- {check.severity.upper():8s} {check.name}: {check.message}")

    if status["status"] == "critical":
        return 2
    if status["status"] == "warning":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
