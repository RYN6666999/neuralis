#!/usr/bin/env python3
"""
Phase 3：沙箱管理器 — 建立/銷毀/管理隔離 Git worktree。

沙箱是一次性的 Git worktree（detached HEAD），在隔離目錄中進行修改。
沙箱銷毀時自動清理殘留。

用法：
  python3 scripts/phase3-sandbox-manager.py create --reason "修 scream-task-executor"
  python3 scripts/phase3-sandbox-manager.py list
  python3 scripts/phase3-sandbox-manager.py destroy --id 001
  python3 scripts/phase3-sandbox-manager.py ccp --id 001 --output /tmp/ccp.yaml

遵循 spec: docs/specs/aris-sandbox-learning/part-03-sandbox.md Ch 6
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
SANDBOX_ROOT = Path("/tmp/aris-sandboxes")
SANDBOX_INDEX = SANDBOX_ROOT / ".index.json"
MAX_SANDBOXES = 3
MAX_LIFETIME_HOURS = 24

# 沙箱環境白名單（正式憑證隔離）
# 沙箱內只能看到這些環境變數，正式 API Key / Token 被隔離
_SAFE_ENV_VARS = frozenset({
    "PATH", "HOME", "USER", "SHELL", "TERM", "LANG", "LC_ALL",
    "TMPDIR", "LOGNAME", "PWD",
    # 沙箱允許的 Neuralis 控制變數（非敏感）
    "NEURALIS_AGENCY_INTERVAL", "NEURALIS_AGENCY_MAX_PER_HOUR",
    "NEURALIS_AGENCY_DRIVE_THRESHOLD", "NEURALIS_AGENCY_DELEGATE",
    "NEURALIS_CONSTITUTION", "NEURALIS_CONSOLIDATION",
    "NEURALIS_AGENCY_HOURLY_TOKEN_BUDGET",
    "NEURALIS_STREAM_FIRST_S", "NEURALIS_STREAM_IDLE_S",
    "NEURALIS_LLM_MODEL", "NEURALIS_TOOL_MODEL",
    "NEURALIS_CHAT_TOOLS", "NEURALIS_CHAT_TOOL_ROUNDS",
    "NEURALIS_AGENCY_DELEGATE",
    # 沙箱工具設定
    "AGENTOS_EXECUTOR_REGISTRY", "AGENTOS_ORCHESTRATOR_PORT",
})


def _build_sandbox_env() -> dict:
    """建立沙箱環境變數（僅白名單變數，隔離正式憑證）。"""
    clean = {}
    for var in _SAFE_ENV_VARS:
        if var in os.environ:
            clean[var] = os.environ[var]
    return clean


# ── 核心沙箱管理 ──────────────────────────────────────────


def _git(args: List[str], cwd: Optional[Path] = None) -> str:
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd or REPO),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _git_quiet(args: List[str], cwd: Optional[Path] = None) -> bool:
    r = subprocess.run(
        ["git"] + args, cwd=str(cwd or REPO),
        capture_output=True, text=True,
    )
    return r.returncode == 0


def _load_index() -> Dict[str, Any]:
    if SANDBOX_INDEX.exists():
        return json.loads(SANDBOX_INDEX.read_text())
    return {"sandboxes": [], "next_id": 1}


def _save_index(index: Dict[str, Any]):
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    SANDBOX_INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False))


def _find_sandbox(sandbox_id: str) -> Optional[Dict[str, Any]]:
    index = _load_index()
    for s in index["sandboxes"]:
        if s["id"] == sandbox_id:
            return s
    return None


def _get_head_sha() -> str:
    return _git(["rev-parse", "--short", "HEAD"])


def create_sandbox(reason: str, plan_ref: Optional[str] = None) -> Dict[str, Any]:
    """建立一次性 Git worktree 沙箱。

    回傳沙箱資訊 dict。
    """
    index = _load_index()

    # 檢查上限
    active = [s for s in index["sandboxes"] if s["status"] == "active"]
    if len(active) >= MAX_SANDBOXES:
        print(f"⚠️ 已達沙箱上限 ({MAX_SANDBOXES})，請先銷毀一個", file=sys.stderr)
        for s in active:
            print(f"   active: {s['id']} — {s['reason'][:50]}", file=sys.stderr)
        sys.exit(1)

    sandbox_id = f"{index['next_id']:03d}"
    index["next_id"] += 1

    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason.lower())[:30]
    sandbox_dir = SANDBOX_ROOT / f"sandbox-{sandbox_id}-{slug}"
    branch_name = f"sandbox/{sandbox_id}-{slug}"
    base_sha = _get_head_sha()

    # 建立 worktree
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    try:
        _git(["worktree", "add", "--detach", str(sandbox_dir), "HEAD"])
    except subprocess.CalledProcessError as e:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
        print(f"❌ 建立 worktree 失敗: {e}", file=sys.stderr)
        sys.exit(1)

    # 沙箱標記檔案（用於殘留檢查）
    start_marker = sandbox_dir / ".sandbox-start"
    start_marker.write_text(str(time.time()))

    # 沙箱資訊
    info = {
        "id": sandbox_id,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "plan_ref": plan_ref,
        "base_commit": base_sha,
        "branch": branch_name,
        "path": str(sandbox_dir),
        "commits": [],
        "test_results": {},
    }

    index["sandboxes"].append(info)
    _save_index(index)

    print(f"✅ 沙箱 {sandbox_id} 建立成功", file=sys.stderr)
    print(f"   路徑: {sandbox_dir}", file=sys.stderr)
    print(f"   base: {base_sha}", file=sys.stderr)
    print(f"   分支: {branch_name}", file=sys.stderr)
    print(f"   原因: {reason}", file=sys.stderr)

    return info


def destroy_sandbox(sandbox_id: str, keep_branch: bool = False):
    """銷毀沙箱 worktree，可選保留分支。"""
    info = _find_sandbox(sandbox_id)
    if not info:
        print(f"❌ 找不到沙箱 {sandbox_id}", file=sys.stderr)
        sys.exit(1)

    sandbox_dir = Path(info["path"])
    if not sandbox_dir.exists():
        print(f"⚠️ 沙箱目錄 {sandbox_dir} 已不存在，跳過", file=sys.stderr)
    else:
        # 殘留檢查
        _check_residue(sandbox_dir)

        # 移除 worktree
        try:
            _git(["worktree", "remove", "--force", str(sandbox_dir)])
        except subprocess.CalledProcessError as e:
            print(f"⚠️ worktree remove 失敗: {e}", file=sys.stderr)
            # fallback: 直接刪目錄
            shutil.rmtree(sandbox_dir, ignore_errors=True)

        # 確保目錄已刪除
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    # 更新狀態
    index = _load_index()
    for s in index["sandboxes"]:
        if s["id"] == sandbox_id:
            s["status"] = "destroyed"
            s["destroyed_at"] = datetime.now(timezone.utc).isoformat()
            break
    _save_index(index)

    print(f"✅ 沙箱 {sandbox_id} 已銷毀", file=sys.stderr)


def _check_residue(sandbox_dir: Path):
    """檢查沙箱外的殘留檔案。"""
    start_marker = sandbox_dir / ".sandbox-start"
    if not start_marker.exists():
        return
    start_time = float(start_marker.read_text().strip())

    # 檢查沙箱內的未追蹤檔案
    result = subprocess.run(
        ["git", "clean", "-n", "-d"],
        cwd=str(sandbox_dir), capture_output=True, text=True,
    )
    untracked = [l for l in result.stdout.split("\n") if l.strip()]
    if untracked:
        print(f"⚠️ 沙箱內有 {len(untracked)} 個未追蹤檔案:", file=sys.stderr)
        for f in untracked[:10]:
            print(f"   {f}", file=sys.stderr)

    # 檢查沙箱外的殘留（找 /tmp 下其他沙箱檔案）
    for p in SANDBOX_ROOT.glob("*"):
        if p != sandbox_dir and p != SANDBOX_INDEX:
            print(f"⚠️ 發現其他沙箱殘留: {p}", file=sys.stderr)


def list_sandboxes() -> List[Dict[str, Any]]:
    """列出所有沙箱。"""
    index = _load_index()
    return index["sandboxes"]


def get_ccp(sandbox_id: str) -> Dict[str, Any]:
    """從沙箱產出候選變更包。"""
    info = _find_sandbox(sandbox_id)
    if not info:
        print(f"❌ 找不到沙箱 {sandbox_id}", file=sys.stderr)
        sys.exit(1)

    sandbox_dir = Path(info["path"])
    if not sandbox_dir.exists():
        print(f"❌ 沙箱目錄不存在: {sandbox_dir}", file=sys.stderr)
        sys.exit(1)

    # 取得沙箱中的 commit 列表
    try:
        log = _git(["log", "--oneline", f"{info['base_commit']}..HEAD"],
                    cwd=sandbox_dir)
    except subprocess.CalledProcessError:
        log = ""

    commits = []
    for line in log.strip().split("\n"):
        if line.strip():
            parts = line.split(" ", 1)
            commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})

    # diff 統計
    try:
        stat_raw = _git(["diff", "--stat", f"{info['base_commit']}..HEAD"],
                        cwd=sandbox_dir)
        diff_stats = _parse_diff_stat(stat_raw)
    except subprocess.CalledProcessError:
        diff_stats = {"files": 0, "insertions": 0, "deletions": 0}

    # 完整 diff
    try:
        diff_full = _git(["diff", f"{info['base_commit']}..HEAD"],
                         cwd=sandbox_dir)
    except subprocess.CalledProcessError:
        diff_full = ""

    # 修改檔案
    try:
        files_raw = _git(["diff", "--name-status", f"{info['base_commit']}..HEAD"],
                         cwd=sandbox_dir)
        files_changed = []
        for line in files_raw.strip().split("\n"):
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files_changed.append({"status": parts[0], "path": parts[1]})
    except subprocess.CalledProcessError:
        files_changed = []

    ccp = {
        "ccp_id": f"CCP-{sandbox_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sandbox_id": sandbox_id,
        "base_commit": info["base_commit"],
        "candidate_commits": commits,
        "diff_stats": diff_stats,
        "files_changed": files_changed,
        "diff": diff_full,
        "diff_truncated": len(diff_full.split("\n")) > 500,
        "sandbox_path": str(sandbox_dir),
        "test_results": info.get("test_results", {}),
    }

    return ccp


def _parse_diff_stat(raw: str) -> Dict[str, int]:
    lines = [l for l in raw.split("\n") if l.strip()]
    files = 0
    insertions = 0
    deletions = 0
    for line in lines:
        if "file" in line and "changed" in line:
            for p in line.split(","):
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


def format_ccp_yaml(ccp: Dict[str, Any]) -> str:
    lines = []
    lines.append("---")
    lines.append(f"ccp_id: '{ccp['ccp_id']}'")
    lines.append(f"generated_at: '{ccp['generated_at']}'")
    lines.append(f"sandbox_id: '{ccp['sandbox_id']}'")
    lines.append(f"base_commit: '{ccp['base_commit']}'")
    lines.append("")
    lines.append("candidate_commits:")
    for c in ccp["candidate_commits"]:
        lines.append(f"  - hash: '{c['hash']}'")
        lines.append(f"    message: '{c['message']}'")
    lines.append("")
    lines.append(f"diff_stats: {{files: {ccp['diff_stats']['files']}, "
                 f"ins: {ccp['diff_stats']['insertions']}, "
                 f"del: {ccp['diff_stats']['deletions']}}}")
    lines.append("")
    lines.append("files_changed:")
    for f in ccp["files_changed"]:
        lines.append(f"  - status: '{f['status']}'")
        lines.append(f"    path: '{f['path']}'")
    lines.append("")
    lines.append("diff: |")
    diff_lines = ccp["diff"].split("\n")
    for dl in diff_lines[:200]:
        lines.append(f"  {dl}")
    if len(diff_lines) > 200:
        lines.append(f"  # ... diff truncated ({len(diff_lines)} total lines)")
    lines.append("")
    if ccp["test_results"]:
        lines.append("test_results:")
        for k, v in ccp["test_results"].items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Phase 3: 沙箱管理器")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml",
                        help="輸出格式 (default: yaml)")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="建立沙箱")
    p_create.add_argument("--reason", "-r", required=True, help="變更原因")
    p_create.add_argument("--plan", "-p", default=None, help="對應的計畫 ID")

    # destroy
    p_destroy = sub.add_parser("destroy", help="銷毀沙箱")
    p_destroy.add_argument("--id", required=True, help="沙箱 ID")
    p_destroy.add_argument("--keep-branch", action="store_true", help="保留分支")

    # list
    sub.add_parser("list", help="列出沙箱")

    # ccp
    p_ccp = sub.add_parser("ccp", help="產出候選變更包")
    p_ccp.add_argument("--id", required=True, help="沙箱 ID")
    p_ccp.add_argument("--output", "-o", default=None, help="輸出檔案")
    p_ccp.add_argument("--format", choices=["yaml", "json"], default=None,
                       help="輸出格式 (default: 繼承上層 --format)")

    # test-result
    p_test = sub.add_parser("test-result", help="記錄測試結果")
    p_test.add_argument("--id", required=True, help="沙箱 ID")
    p_test.add_argument("--passed", type=int, default=0)
    p_test.add_argument("--failed", type=int, default=0)

    args = parser.parse_args()

    if args.command == "create":
        info = create_sandbox(args.reason, args.plan)
        print(json.dumps(info, indent=2, ensure_ascii=False))

    elif args.command == "destroy":
        destroy_sandbox(args.id, args.keep_branch)

    elif args.command == "list":
        sandboxes = list_sandboxes()
        if args.format == "json":
            print(json.dumps(sandboxes, indent=2, ensure_ascii=False))
            return
        if not sandboxes:
            print("無沙箱紀錄")
            return
        print(f"{'ID':<6} {'狀態':<12} {'原因':<40} {'路徑'}")
        print("-" * 80)
        for s in sandboxes:
            path = Path(s.get("path", ""))
            exists = "✅" if path.exists() else "❌"
            print(f"{s['id']:<6} {s['status']:<12} {s['reason'][:38]:<40} {exists} {s.get('path', '')}")

    elif args.command == "ccp":
        ccp = get_ccp(args.id)
        fmt = args.format or "yaml"
        if fmt == "json":
            output = json.dumps(ccp, indent=2, ensure_ascii=False)
        else:
            output = format_ccp_yaml(ccp)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"📄 已寫入 {args.output}", file=sys.stderr)
        else:
            print(output)

    elif args.command == "test-result":
        info = _find_sandbox(args.id)
        if not info:
            print(f"❌ 找不到沙箱 {args.id}", file=sys.stderr)
            sys.exit(1)
        index = _load_index()
        for s in index["sandboxes"]:
            if s["id"] == args.id:
                s["test_results"] = {"passed": args.passed, "failed": args.failed}
                break
        _save_index(index)
        print(f"✅ 沙箱 {args.id} 測試結果已記錄: {args.passed} passed, {args.failed} failed",
              file=sys.stderr)


if __name__ == "__main__":
    main()