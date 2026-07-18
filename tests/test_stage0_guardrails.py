"""Stage 0 硬邊界 acceptance — scream-task 重分類 + commit 快照。"""
import subprocess
from pathlib import Path

from laap.safety_gate import classify, check
from laap.snapshot import create_snapshot, restore_snapshot


def _no_local_approval(monkeypatch):
    """讓測試 hermetic：清掉本機 approved-tools.txt / env（否則 scream-task 若被
    批准過，approval 相關斷言會受本機狀態影響）。"""
    monkeypatch.setattr("laap.safety_gate.APPROVED_PATH", Path("/nonexistent-approved-xyz"))
    monkeypatch.delenv("NEURALIS_TOOL_ALLOW", raising=False)


# ── scream-task 重分類為 write ──

def test_scream_task_is_write_not_readonly():
    assert classify("scream-task") == "write", \
        "scream-task 是委派-寫入工具，不該是唯讀"


def test_scream_task_benign_needs_approval(monkeypatch):
    # 未批准的委派（非 laap 路徑）→ 排隊等批，不自動放行
    _no_local_approval(monkeypatch)
    allowed, reason = check("scream-task", "在外部專案跑個測試")
    assert not allowed and "批准" in reason, f"未批准委派應排隊：{reason}"


def test_scream_ask_still_readonly():
    assert classify("scream-ask") == "readonly_builtin", "scream-ask 純 Q&A 留唯讀"


def test_path_deny_still_wins_over_approval():
    # laap/** 委派：path-DENY（層 0）先於批准閘，reason 是路徑不是批准
    allowed, reason = check("scream-task", "改 laap/psi_core.py")
    assert not allowed and "認知碼" in reason, f"laap 委派應被 path-DENY：{reason}"


# ── commit 快照：建 → 改檔 → 還原 ──

def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def test_snapshot_create_and_restore(tmp_path):
    repo = str(tmp_path)
    _git(["init"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    f = tmp_path / "a.txt"
    f.write_text("v1")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)

    snap = create_snapshot("test 還原點", cwd=repo)
    assert snap, "快照應回 SHA"

    f.write_text("v2 改壞了")            # 模擬自動改動
    assert f.read_text() == "v2 改壞了"

    restore_snapshot(snap, cwd=repo)     # 一鍵還原
    assert f.read_text() == "v1", "還原後應回快照狀態"

    # 審計有紀錄
    audit = tmp_path / "snapshot-audit.jsonl"
    assert audit.exists() and snap in audit.read_text()


def test_snapshot_captures_dirty_tree(tmp_path):
    """工作樹已髒時，快照要捕捉當下（不是只有 HEAD）。"""
    repo = str(tmp_path)
    _git(["init"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    f = tmp_path / "a.txt"
    f.write_text("committed")
    _git(["add", "."], repo)
    _git(["commit", "-m", "init"], repo)

    f.write_text("dirty-at-snapshot")    # 未提交
    snap = create_snapshot("dirty", cwd=repo)
    f.write_text("changed-again")
    restore_snapshot(snap, cwd=repo)
    assert f.read_text() == "dirty-at-snapshot", "髒工作樹的快照要能還原到當下"
