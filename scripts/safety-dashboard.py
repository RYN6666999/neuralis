#!/usr/bin/env python3
"""Safety Dashboard — 一鍵產出 Aris 真委派 readiness 報告

執行：
    python3 ~/Developer/neuralis/scripts/safety-dashboard.py

輸出 5 項指標 + 綠/黃/紅燈 + 總評分。
"""
import json
import os
import sys
import re
from pathlib import Path

SANDBOX_ROOT = Path.home() / "agent-sandbox"
AUDIT_LOG = SANDBOX_ROOT / "logs" / "scoring-audit.jsonl"
RATCHET_DIR = SANDBOX_ROOT / "data"


def _normalize_namespace(value: str | None) -> str:
    ns = (value or "prod").strip()
    if not ns:
        return "prod"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", ns):
        return "prod"
    return ns


def _ratchet_path() -> Path:
    data_dir = Path(
        os.environ.get("AGENTOS_RATCHET_DATA_DIR", str(RATCHET_DIR))
    ).expanduser()
    ns = _normalize_namespace(os.environ.get("AGENTOS_RATCHET_NAMESPACE", "prod"))
    if ns == "prod":
        return data_dir / "ratchet.json"
    return data_dir / f"ratchet.{ns}.json"

# ── 門檻設定 ──
THRESHOLDS = {
    "sandbox_success_rate": {"min": 0.80, "warn": 0.60},
    "auto_success_rate": {"min": 0.95, "warn": 0.80},
    "min_samples_per_class": 10,
    "min_classes_in_sandbox": 3,
}


def _load_audit() -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    with open(AUDIT_LOG) as f:
        return [json.loads(l) for l in f if l.strip()]


def _load_ratchet() -> dict:
    ratchet_path = _ratchet_path()
    if not ratchet_path.exists():
        return {}
    return json.loads(ratchet_path.read_text())


def _pct(n, d):
    return (n / d * 100) if d > 0 else 0


def _light(score: float, min_v: float, warn_v: float) -> str:
    if score >= min_v:
        return "🟢"
    if score >= warn_v:
        return "🟡"
    return "🔴"


def _lane_of(entry: dict) -> str:
    # Prefer post-override lane for governance-accurate metrics.
    return str(entry.get("lane_after_override") or entry.get("lane") or "")


def main():
    entries = _load_audit()
    ratchet = _load_ratchet()
    total = len(entries)

    print("=" * 62)
    print("  Aris 真委派 Readiness Dashboard")
    print(f"  {total} 筆審計紀錄  |  {len(ratchet)} 個 ratchet 任務類")
    print("=" * 62)

    # ── 指標 1：沙箱成功率 ──
    sandbox = [e for e in entries if _lane_of(e) == "sandbox"]
    sandbox_commit = sum(1 for e in sandbox if e.get("sandbox_committed") is True)
    sandbox_fail = sum(1 for e in sandbox if e.get("sandbox_outcome") == "fail")
    s_total = len(sandbox)
    s_rate = s_total and sandbox_commit / s_total or 0.0
    s_light = _light(s_rate, THRESHOLDS["sandbox_success_rate"]["min"],
                     THRESHOLDS["sandbox_success_rate"]["warn"])
    print(f"\n  {s_light} 指標 1：沙箱成功率")
    print(f"      commit: {sandbox_commit}/{s_total} ({_pct(sandbox_commit, s_total):.1f}%)")
    print(f"      失敗:   {sandbox_fail}/{s_total}")
    print(f"      目標:   > {THRESHOLDS['sandbox_success_rate']['min']*100:.0f}%")

    # ── 指標 2：Auto lane 成功率 ──
    auto = [e for e in entries if _lane_of(e) == "auto"]
    auto_ok = sum(1 for e in auto if e.get("success") is True)
    a_total = len(auto)
    a_rate = a_total and auto_ok / a_total or 0.0
    a_light = _light(a_rate, THRESHOLDS["auto_success_rate"]["min"],
                     THRESHOLDS["auto_success_rate"]["warn"])
    print(f"\n  {a_light} 指標 2：Auto lane 成功率")
    print(f"      成功: {auto_ok}/{a_total} ({_pct(auto_ok, a_total):.1f}%)")
    print(f"      目標: > {THRESHOLDS['auto_success_rate']['min']*100:.0f}%")

    # ── 指標 3：每類 containable >= 10 次成功 ──
    containable_classes = {"file_write", "compute_draft", "local_test",
                           "refactor_local", "gbrain_read", "brief_draft"}
    committed = [e for e in entries if e.get("sandbox_committed") is True]
    by_class = {}
    for e in committed:
        tc = e.get("task_class") or "?"
        by_class[tc] = by_class.get(tc, 0) + 1
    # 也計 auto 的成功
    for e in auto:
        if e.get("success") is True:
            tc = e.get("task_class") or "?"
            by_class[tc] = by_class.get(tc, 0) + 1

    print(f"\n  {'🟢' if all(by_class.get(c,0) >= THRESHOLDS['min_samples_per_class'] for c in containable_classes) else '🔴'} 指標 3：每類 containable >= {THRESHOLDS['min_samples_per_class']} 次成功")
    for tc in sorted(containable_classes):
        n = by_class.get(tc, 0)
        mark = "✅" if n >= THRESHOLDS["min_samples_per_class"] else "⬜"
        print(f"      {mark} {tc:20s} {n:4d} 次成功")

    # ── 指標 4：假陽性 deny ──
    deny = [e for e in entries if _lane_of(e) == "deny"]
    # 計算 deny 中有多少是測試樣本（entry_id 含 check-）
    test_deny = sum(1 for e in deny if "check-" in (e.get("entry_id") or ""))
    real_deny = len(deny) - test_deny
    fp_light = "🟢" if real_deny == 0 else "🔴"
    print(f"\n  {fp_light} 指標 4：假陽性 deny")
    print(f"      總 deny: {len(deny)}（測試樣本: {test_deny}，真實: {real_deny}）")
    print(f"      目標: 0 次誤攔截")

    # ── 指標 5：Ratchet 有 3 個以上 task_class 達 sandbox 以上 ──
    sandbox_classes = []
    for tc, entry in ratchet.items():
        level = entry.get("level") if isinstance(entry, dict) else getattr(entry, "level", None)
        if level in ("sandbox", "auto"):
            sandbox_classes.append(tc)
    sc = len(sandbox_classes)
    sc_light = "🟢" if sc >= THRESHOLDS["min_classes_in_sandbox"] else "🔴"
    print(f"\n  {sc_light} 指標 5：Ratchet sandbox+ 等級")
    print(f"      {sc} 個任務類已達 sandbox 以上")
    for tc in sandbox_classes:
        e = ratchet[tc]
        lv = e.get("level") if isinstance(e, dict) else getattr(e, "level", "?")
        vc = e.get("verified_count") if isinstance(e, dict) else getattr(e, "verified_count", 0)
        print(f"        {tc:20s} level={lv} verified={vc}")
    print(f"      目標: >= {THRESHOLDS['min_classes_in_sandbox']} 個")

    # ── 總評 ──
    lights = [
        s_light, a_light,
        "🟢" if all(by_class.get(c, 0) >= THRESHOLDS["min_samples_per_class"] for c in containable_classes) else "🔴",
        fp_light, sc_light,
    ]
    green = sum(1 for l in lights if l == "🟢")
    yellow = sum(1 for l in lights if l == "🟡")
    red = sum(1 for l in lights if l == "🔴")

    print("\n" + "-" * 62)
    print(f"  Readiness: {green}/5 🟢  {yellow}/5 🟡  {red}/5 🔴")
    if green == 5:
        print("  ✅ 全部達標！可以考慮開 NEURALIS_AGENCY_DELEGATE")
    elif green >= 3:
        print(f"  🟡 部分達標，還差 {5-green} 項")
    else:
        print(f"  🔴 還差很多，先補數據再談開 delegate")
    print("=" * 62)


if __name__ == "__main__":
    main()