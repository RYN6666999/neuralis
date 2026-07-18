#!/usr/bin/env python3
"""
Phase 2：沙箱建議模式 — 從問題描述產出結構化實作計畫。

Scream 不修改正式檔案，只產出計畫（存成候選變更包格式，diff 為空）。
Aris 先產出問題與假設 → Scream 產出實作計畫 → Aris 四面向分析。

用法：
  python3 scripts/phase2-plan-change.py --problem "..." --target "file1,file2"
  python3 scripts/phase2-plan-change.py --from-file /tmp/problem.yaml

遵循 spec: docs/specs/aris-sandbox-learning/part-02-full-flow.md Ch 5（問題與假設）
         docs/specs/aris-sandbox-learning/part-04-decision-analysis.md Ch 9（CCP）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
CASES_DIR = REPO / "docs" / "specs" / "aris-sandbox-learning" / "cases"


def generate_plan(
    problem: str,
    target_files: List[str],
    approach: str,
    estimated_effort: str = "medium",
    domain: str = "other",
    problem_category: str = "other",
    success_criteria: Optional[List[str]] = None,
    stop_conditions: Optional[List[str]] = None,
    routes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """產出結構化實作計畫（CCP 格式，diff 為空）。"""

    plan_id = _next_plan_id()

    if success_criteria is None:
        success_criteria = ["修改後既有測試仍全部通過"]
    if stop_conditions is None:
        stop_conditions = ["測試失敗且無法在三輪迭代內修復"]

    if routes is None or len(routes) == 0:
        routes = [
            {
                "route": "A",
                "description": f"直接修改 {', '.join(target_files)}",
                "approach": approach,
                "files": target_files,
                "effort": estimated_effort,
            }
        ]

    plan: Dict[str, Any] = {
        "plan_id": plan_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "2-suggestion",
        "status": "draft",
        "files_modified": [],  # Phase 2: 不修改任何檔案
    }

    # Chapter 5: 問題與假設
    plan["problem"] = {
        "statement": problem,
        "category": problem_category,
        "domain": domain,
        "evidence": "基於既有程式碼分析和 handoff-next-session.md 記錄",
        "if_not_done": f"如果不處理此問題，{_default_consequence(problem_category)}",
        "falsifiable": f"可證偽：如果修改後 {_default_falsifiable(problem_category)}",
    }

    # Chapter 5: 預測（簡化版）
    plan["prediction"] = {
        "benefit": {
            "expected_improvement": _default_benefit(problem_category, target_files),
            "measurable_criterion": success_criteria[0] if success_criteria else "",
        },
        "risk": {
            "worst_case": f"修改 {', '.join(target_files)} 導致既有功能異常",
            "recoverable": True,
        },
        "cost": {
            "dev_time_hours": _default_cost(estimated_effort),
            "api_cost_usd": 0,
        },
    }

    # Chapter 5: 候選路線
    plan["candidates"] = routes

    # Chapter 9: CCP（diff 為空 — Phase 2 尚未實作）
    plan["ccp"] = {
        "purpose": problem,
        "base_commit": _get_head_sha(),
        "candidate_commit": None,
        "files_changed": target_files,
        "diff": None,  # Phase 2: diff 為空
        "diff_stats": {"files": len(target_files), "insertions": 0, "deletions": 0},
        "test_plan": f"修改後執行 pytest {_test_paths(target_files)}",
        "rollback_method": "Phase 2 尚未實作，無需回退",
    }

    # 成功/停止條件
    plan["conditions"] = {
        "success": success_criteria,
        "stop": stop_conditions,
    }

    return plan


def _next_plan_id() -> str:
    """產生下一個計畫 ID。"""
    if not CASES_DIR.exists():
        CASES_DIR.mkdir(parents=True, exist_ok=True)
        return "PLAN-001"
    existing = list(CASES_DIR.glob("plan-*.json"))
    if not existing:
        return "PLAN-001"
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem.split("-")[1]))
        except (IndexError, ValueError):
            pass
    return f"PLAN-{max(nums, default=0) + 1:03d}"


def _get_head_sha() -> str:
    """取得當前 HEAD SHA。"""
    import subprocess
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO), capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def _test_paths(files: List[str]) -> str:
    """從修改的檔案推測測試路徑。"""
    test_dirs = set()
    for f in files:
        if f.startswith("laap/"):
            test_dirs.add("tests/")
        elif f.startswith("scripts/"):
            test_dirs.add("tests/")
    return " ".join(sorted(test_dirs)) if test_dirs else "tests/"


def _default_benefit(category: str, files: List[str]) -> str:
    benefits = {
        "performance": "效能改善",
        "safety": "安全邊界強化",
        "reliability": "穩定性提升",
        "usability": "使用體驗改善",
        "maintainability": "程式碼可維護性提升",
        "cost": "成本降低",
        "integration": "整合完善",
        "correctness": "邏輯正確性改善",
        "observability": "可觀測性提升",
    }
    return benefits.get(category, f"改善 {', '.join(files)}")


def _default_consequence(category: str) -> str:
    consequences = {
        "performance": "效能問題持續存在",
        "safety": "安全風險未解決",
        "reliability": "不穩定因素未排除",
        "maintainability": "技術債持續累積",
    }
    return consequences.get(category, "問題持續存在")


def _default_falsifiable(category: str) -> str:
    falsifiables = {
        "performance": "benchmark 分數沒有提升，則方案無效",
        "reliability": "問題仍然可復現，則方案無效",
        "safety": "安全閘仍然可以被繞過，則方案無效",
    }
    return falsifiables.get(category, "問題仍然存在，則方案無效")


def _default_cost(effort: str) -> float:
    mapping = {"small": 0.5, "medium": 2.0, "large": 8.0}
    return mapping.get(effort, 2.0)


def format_yaml(plan: Dict[str, Any]) -> str:
    """轉為 YAML 樣式輸出。"""
    lines: List[str] = []
    lines.append("---")
    lines.append(f"plan_id: '{plan['plan_id']}'")
    lines.append(f"generated_at: '{plan['generated_at']}'")
    lines.append(f"phase: '{plan['phase']}'")
    lines.append(f"status: '{plan['status']}'")
    lines.append("")
    lines.append("# ── 問題與假設 ──")
    lines.append(f"problem: '{plan['problem']['statement']}'")
    lines.append(f"category: '{plan['problem']['category']}'")
    lines.append(f"domain: '{plan['problem']['domain']}'")
    lines.append(f"if_not_done: '{plan['problem']['if_not_done']}'")
    lines.append(f"falsifiable: '{plan['problem']['falsifiable']}'")
    lines.append("")
    lines.append("# ── 預測 ──")
    p = plan["prediction"]
    lines.append(f"predicted_benefit: '{p['benefit']['expected_improvement']}'")
    lines.append(f"measurable: '{p['benefit']['measurable_criterion']}'")
    lines.append(f"worst_case: '{p['risk']['worst_case']}'")
    lines.append(f"recoverable: {json.dumps(p['risk']['recoverable'])}")
    lines.append(f"est_dev_hours: {p['cost']['dev_time_hours']}")
    lines.append(f"est_api_cost: {p['cost']['api_cost_usd']}")
    lines.append("")
    lines.append("# ── 候選路線 ──")
    for c in plan["candidates"]:
        lines.append(f"  - route: '{c['route']}'")
        lines.append(f"    description: '{c['description']}'")
        lines.append(f"    files: {json.dumps(c['files'])}")
        lines.append(f"    effort: '{c['effort']}'")
    lines.append("")
    lines.append("# ── CCP（diff 為空 — Phase 2）──")
    lines.append(f"base_commit: '{plan['ccp']['base_commit']}'")
    lines.append(f"candidate_commit: null")
    lines.append(f"files_to_modify: {json.dumps(plan['ccp']['files_changed'])}")
    lines.append(f"diff: null")
    lines.append(f"diff_stats: {{files: {plan['ccp']['diff_stats']['files']}, ins: 0, del: 0}}")
    lines.append(f"test_plan: '{plan['ccp']['test_plan']}'")
    lines.append("")
    lines.append("# ── 條件 ──")
    lines.append("success_conditions:")
    for sc in plan["conditions"]["success"]:
        lines.append(f"  - '{sc}'")
    lines.append("stop_conditions:")
    for sc in plan["conditions"]["stop"]:
        lines.append(f"  - '{sc}'")
    lines.append("")
    lines.append("# ⚠️ Phase 2：計畫尚未實作。diff 為空，無沙箱建立。")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Phase 2: 沙箱建議模式 — 產出實作計畫")
    parser.add_argument("--problem", required=True, help="問題描述")
    parser.add_argument("--target", required=True, help="目標檔案，逗號分隔")
    parser.add_argument("--approach", default=None, help="實作方式")
    parser.add_argument("--domain", default="other", help="領域分類")
    parser.add_argument("--category", default="other", help="問題分類")
    parser.add_argument("--effort", default="medium", choices=["small", "medium", "large"])
    parser.add_argument("--output", "-o", default=None, help="輸出路徑 (default: cases/plan-NNN.yaml)")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml")
    args = parser.parse_args()

    target_files = [f.strip() for f in args.target.split(",")]
    approach = args.approach or f"修改 {', '.join(target_files)}"

    plan = generate_plan(
        problem=args.problem,
        target_files=target_files,
        approach=approach,
        estimated_effort=args.effort,
        domain=args.domain,
        problem_category=args.category,
    )

    if args.format == "json":
        output = json.dumps(plan, indent=2, ensure_ascii=False)
    else:
        output = format_yaml(plan)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"📄 已寫入 {args.output}", file=sys.stderr)
    else:
        # 預設寫入 cases/
        CASES_DIR.mkdir(parents=True, exist_ok=True)
        out_path = CASES_DIR / f"{plan['plan_id'].lower()}.yaml"
        out_path.write_text(output, encoding="utf-8")
        print(f"📄 已寫入 {out_path}", file=sys.stderr)

    print(output)


if __name__ == "__main__":
    main()
