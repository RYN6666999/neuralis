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
BRIDGE_SCRIPT = Path(os.path.expanduser("~/Developer/neuralis/scripts/agentos-aris-bridge.py"))
BRIDGE_PLIST = Path(os.path.expanduser("~/Library/LaunchAgents")).glob("com.neuralis.*.plist")
CANARY_PLIST = Path(os.path.expanduser("~/Library/LaunchAgents/com.neuralis.task-executor.plist"))


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


def _check_bridge_env() -> CheckResult:
    """"bridge_env" probe（第七條邊）：驗證執行環境完整性。
    
    三項檢查（任一 fail → critical）：
    1. canary enabled — 試 import pydantic（失敗 = 評分路由被靜默降級）
    2. 單一 bridge process — 確保不多實例衝突
    3. plist 完整性 — com.neuralis.*.plist 全存在且 XML 可 parse
    """
    issues = []
    details: dict[str, Any] = {}

    # 1. canary enabled
    pydantic_ok = False
    try:
        import pydantic  # noqa: F401
        pydantic_ok = True
    except ImportError:
        pydantic_ok = False
    details["pydantic_importable"] = pydantic_ok
    if not pydantic_ok:
        issues.append("pydantic import failed — canary scoring disabled")

    # 2. single bridge process
    #
    # LC_ALL=C 是必要的，不是保險：在 UTF-8 locale 下 pgrep 會對某些進程的
    # command line 解碼失敗，吐 "Regular expression evaluation error
    # (illegal byte sequence)" 並以 exit 3 收場。C locale 走逐位元組比對，免疫。
    # 這個 bug 讓本檢查連續誤報 477 次 "no bridge process running"，
    # 而 bridge 其實一直活著（task-executor 起的，uptime 2 天以上）。
    #
    # exit code 語義必須分開：0=找到、1=真的沒有、>=2=pgrep 自己壞了。
    # 舊版把三者一律當成 count=0，於是「工具故障」被報成「bridge 掛了」。
    import subprocess
    bridge_probe_failed = False
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "agentos-aris-bridge.py"],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "LC_ALL": "C"},
        )
        if proc.returncode >= 2:
            bridge_probe_failed = True
            pids = []
            details["bridge_probe_error"] = (
                f"pgrep exit={proc.returncode}: {proc.stderr.strip()[:120]}")
        else:
            # returncode 0 = 有 match；1 = 沒 match（stdout 空）
            pids = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
    except subprocess.TimeoutExpired:
        bridge_probe_failed = True
        pids = []
        details["bridge_probe_error"] = "pgrep timeout after 5s"

    bridge_count = len(pids)
    details["bridge_pids"] = pids
    details["bridge_process_count"] = bridge_count
    details["bridge_probe_failed"] = bridge_probe_failed

    if bridge_probe_failed:
        # 探測壞掉 != bridge 掛掉。照實說，不要假裝知道。
        issues.append(
            f"bridge probe failed, process state unknown "
            f"({details['bridge_probe_error']})")
    elif bridge_count == 0:
        issues.append("no bridge process running")
    elif bridge_count > 1:
        issues.append(f"{bridge_count} bridge processes running — expected 1")

    # 3. plist integrity
    plist_dir = Path(os.path.expanduser("~/Library/LaunchAgents"))
    plists = sorted(plist_dir.glob("com.neuralis.*.plist"))
    details["plist_count"] = len(plists)
    details["plist_paths"] = [str(p) for p in plists]
    xml_broken = []
    for p in plists:
        try:
            raw = p.read_bytes()
            if b"<?xml" not in raw:
                xml_broken.append(p.name)
        except OSError:
            xml_broken.append(p.name)
    if xml_broken:
        issues.append(f"plist XML broken: {', '.join(xml_broken)}")
    # 檢查 task-executor 這個關鍵 plist 是否存在
    has_canary_plist = CANARY_PLIST.exists()
    details["canary_plist_exists"] = has_canary_plist
    if not has_canary_plist:
        issues.append("com.neuralis.task-executor.plist missing — bridge won't survive reboot")

    severity = "critical" if issues else "ok"
    return CheckResult(
        name="bridge_env",
        severity=severity,
        message="; ".join(issues) if issues else "bridge environment healthy",
        value=float(bridge_count),
        threshold=1.0,
        details=details,
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
        _check_bridge_env(),
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
