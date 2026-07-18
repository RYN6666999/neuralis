#!/usr/bin/env python3
"""
Phase 1：只讀分析 — 從 git commit 萃取結構化資訊，產出候選變更包雛形。

用途：Aris 分析既有 diff，不修改程式碼。產出餵給四面向分析器。

用法：
  python3 scripts/phase1-analyze-commit.py              # 最近 5 筆
  python3 scripts/phase1-analyze-commit.py --range HEAD~3..HEAD
  python3 scripts/phase1-analyze-commit.py --range HEAD~1..HEAD --yaml

遵循 spec: docs/specs/aris-sandbox-learning/part-04-decision-analysis.md Ch 9
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]


def _git(args: List[str], cwd: Optional[str] = None) -> str:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd or str(REPO),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _git_quiet(args: List[str], cwd: Optional[str] = None) -> bool:
    """回 True 如果 exit code 0。"""
    r = subprocess.run(
        ["git"] + args,
        cwd=cwd or str(REPO),
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def get_commits(rev_range: str) -> List[str]:
    """回傳 commit hash 列表（最新在前）。"""
    out = _git(["log", "--oneline", "--no-decorate", rev_range])
    return [line.split()[0] for line in out.strip().splitlines() if line.strip()]


def get_commit_info(sha: str) -> Dict[str, Any]:
    """萃取單一 commit 的結構化資訊。"""
    # 基本資訊
    raw = _git(["log", "-1", "--format=%H%n%an%n%ae%n%ai%n%s%n%b", sha])
    lines = raw.split("\n", 5)
    info: Dict[str, Any] = {
        "commit": lines[0],
        "author": {"name": lines[1], "email": lines[2]},
        "date": lines[3],
        "subject": lines[4],
        "body": lines[5].strip() if len(lines) > 5 else "",
    }

    # diff 統計
    stat_raw = _git(["diff", "--stat", f"{sha}~1..{sha}"])
    info["diff_stats"] = _parse_diff_stat(stat_raw)

    # 檔案變更
    files_raw = _git(["diff", "--name-status", f"{sha}~1..{sha}"])
    info["files_changed"] = []
    for line in files_raw.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            info["files_changed"].append({"status": parts[0], "path": parts[1]})

    # 完整 diff（前 200 行）
    diff_raw = _git(["diff", f"{sha}~1..{sha}"])
    lines_diff = diff_raw.split("\n")
    truncated = len(lines_diff) > 200
    info["diff_preview"] = "\n".join(lines_diff[:200])
    info["diff_truncated"] = truncated
    info["diff_total_lines"] = len(lines_diff)

    # 測試是否相關（檢查檔案路徑含 test 或檔案變更含 tests/）
    info["has_tests"] = any(
        "test" in f["path"] or f["path"].startswith("tests/")
        for f in info["files_changed"]
    )

    # 相關測試檔案路徑
    info["test_files"] = [
        f["path"]
        for f in info["files_changed"]
        if "test" in f["path"] or f["path"].startswith("tests/")
    ]

    # 分類：修改了哪些領域
    info["domains"] = _classify_domains(info["files_changed"])

    return info


def _parse_diff_stat(raw: str) -> Dict[str, Any]:
    """解析 diff --stat 輸出。"""
    lines = [l for l in raw.split("\n") if l.strip()]
    if not lines:
        return {"files": 0, "insertions": 0, "deletions": 0}

    files = 0
    insertions = 0
    deletions = 0
    for line in lines:
        if "file changed" in line or "files changed" in line:
            parts = line.split(",")
            for p in parts:
                p = p.strip()
                if "file" in p:
                    try:
                        files = int(p.split()[0])
                    except (ValueError, IndexError):
                        pass
                elif "insertion" in p:
                    try:
                        insertions = int(p.split()[0])
                    except (ValueError, IndexError):
                        pass
                elif "deletion" in p:
                    try:
                        deletions = int(p.split()[0])
                    except (ValueError, IndexError):
                        pass
    return {"files": files, "insertions": insertions, "deletions": deletions}


_DOMAIN_KEYWORDS = {
    "safety-gate": ["safety_gate", "safety/"],
    "agency": ["agency.py"],
    "psi-core": ["psi_core", "psi_backend"],
    "tool-executor": ["tool_executor"],
    "constitution": ["constitution"],
    "cost-ledger": ["cost_ledger"],
    "s-span": ["s_span", "cognitive-light-cone"],
    "scream-channel": ["scream-", "scream_"],
    "infrastructure": ["scripts/", "watchdog", "launchd"],
    "documentation": ["docs/", ".md"],
    "upstream-agi": ["aris_brain/", "laap_brain/"],
    "tests": ["tests/"],
}


def _classify_domains(files: List[Dict[str, str]]) -> List[str]:
    """根據檔案路徑分類 commit 影響的領域。"""
    domains = set()
    for f in files:
        path = f["path"]
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if any(kw in path for kw in keywords):
                domains.add(domain)
    return sorted(domains) if domains else ["other"]


def format_ccp(commits: List[Dict[str, Any]]) -> str:
    """將 commit 列表格式化為候選變更包樣式。"""
    lines: List[str] = []
    lines.append("---")
    lines.append("phase1_analysis:")
    lines.append(f"  generated_at: '{__import__('datetime').datetime.now().isoformat()}'")
    lines.append(f"  commit_count: {len(commits)}")
    lines.append("")
    lines.append(f"  commits:")
    for c in commits:
        lines.append(f"    - hash: '{c['commit']}'")
        lines.append(f"      author: '{c['author']['name']} <{c['author']['email']}>'")
        lines.append(f"      date: '{c['date']}'")
        lines.append(f"      subject: '{c['subject']}'")
        lines.append(f"      body: '{c['body'][:200]}'")  # truncate body
        lines.append(f"      domains: {json.dumps(c['domains'])}")
        lines.append(f"      diff_stats:")
        ds = c["diff_stats"]
        lines.append(f"        files: {ds['files']}")
        lines.append(f"        insertions: {ds['insertions']}")
        lines.append(f"        deletions: {ds['deletions']}")
        lines.append(f"      files_changed:")
        for f in c["files_changed"]:
            lines.append(f"        - {{status: '{f['status']}', path: '{f['path']}'}}")
        lines.append(f"      has_tests: {json.dumps(c['has_tests'])}")
        lines.append(f"      test_files: {json.dumps(c['test_files'])}")
        lines.append(f"      diff_truncated: {json.dumps(c.get('diff_truncated', False))}")
        lines.append(f"      diff_total_lines: {c.get('diff_total_lines', 0)}")

    return "\n".join(lines)


def format_four_facet(commits: List[Dict[str, Any]]) -> str:
    """產出四面向分析框架（待 Aris 填入評分）。"""
    lines: List[str] = []
    lines.append("---")
    lines.append("four_facet_analysis:")
    lines.append(f"  target_commits: {len(commits)}")
    lines.append("")

    for c in commits:
        lines.append(f"  - commit: '{c['commit']}'")
        lines.append(f"    subject: '{c['subject']}'")
        lines.append(f"    domains: {json.dumps(c['domains'])}")
        lines.append("")
        lines.append("    # --- Aris 填入以下欄位 ---")
        lines.append("    benefit:")
        lines.append("      description: null  # 這個 commit 帶來什麼好處？")
        lines.append("      magnitude: null    # none / small / medium / large")
        lines.append("      who_feels_it: null")
        lines.append("      confidence: null")
        lines.append("")
        lines.append("    harm:")
        lines.append("      description: null  # 新增什麼複雜度或依賴？")
        lines.append("      complexity_increase: null  # none / minor / moderate / major")
        lines.append("      confidence: null")
        lines.append("")
        lines.append("    risk:")
        lines.append("      description: null  # 最壞情況？")
        lines.append("      probability: null  # 0.0-1.0")
        lines.append("      recoverable: null")
        lines.append("      confidence: null")
        lines.append("")
        lines.append("    cost:")
        lines.append("      dev_time_hours: null  # 估計開發時數")
        lines.append("      api_cost_usd: null")
        lines.append("      ryan_attention: null  # low / medium / high")
        lines.append("      confidence: null")
        lines.append("")
        lines.append("    overall:")
        lines.append("      evidence_strength: null  # none / weak / moderate / strong / conclusive")
        lines.append("      recommendation: null  # approve / modify / reject / observe")
        lines.append("      confidence: null")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Phase 1: 只讀分析 — commit 結構化萃取")
    parser.add_argument(
        "--range", default="HEAD~5..HEAD",
        help="git rev range (default: HEAD~5..HEAD)"
    )
    parser.add_argument(
        "--format", choices=["ccp", "four-facet", "json"], default="ccp",
        help="輸出格式 (default: ccp)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="輸出檔案路徑 (default: stdout)"
    )
    args = parser.parse_args()

    # 檢查是否在 git repo 中
    if not _git_quiet(["rev-parse", "--git-dir"]):
        print("❌ 不在 git repository 中", file=sys.stderr)
        sys.exit(1)

    # 萃取
    hashes = get_commits(args.range)
    if not hashes:
        print(f"⚠️ 在範圍 {args.range} 中找不到 commit", file=sys.stderr)
        sys.exit(0)

    commits = [get_commit_info(h) for h in hashes]
    print(f"✅ 萃取 {len(commits)} 個 commit: {', '.join(h[:8] for h in hashes)}",
          file=sys.stderr)

    # 格式化
    if args.format == "ccp":
        output = format_ccp(commits)
    elif args.format == "four-facet":
        output = format_four_facet(commits)
    elif args.format == "json":
        # JSON: 用 json.dumps，但注意 diff_preview 太長，只留 diff_stats
        json_commits = []
        for c in commits:
            jc = {k: v for k, v in c.items() if k != "diff_preview"}
            json_commits.append(jc)
        output = json.dumps(json_commits, indent=2, ensure_ascii=False)
    else:
        output = ""

    # 輸出
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"📄 寫入 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
