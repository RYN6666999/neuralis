#!/usr/bin/env python3
"""
evaluate-and-feedback.py — aris-evaluator 封閉迴路

評估最新 session log，如果分數低於閾值，自動寫入留言板。
留言板內容會在下次 bootstrap 時被載入，形成閉環。

用法:
    python3 evaluate-and-feedback.py <session_log_path>
    python3 evaluate-and-feedback.py --last     # 評估最近一次 session
    python3 evaluate-and-feedback.py --watch    # 監聽模式（cron 用）
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── 設定 ──
SCORE_THRESHOLD = 0.5  # 低於此分數觸發回饋
FEEDBACK_FILE = Path(os.environ.get("FEEDBACK_FILE",
    "/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/aris-evaluator-feedback.md"))

# evaluator 路徑
EVAL_DIR = Path.home() / ".aris-evaluator"
sys.path.insert(0, str(EVAL_DIR))

# 從 psi_evaluator import 正確的函式
from psi_evaluator import evaluate as psi_evaluate  # type: ignore


def compute_score(report: dict) -> float:
    """從評估報告計算綜合分數 0.0 ~ 1.0。"""
    events = report.get("events", {})
    failures = events.get("failures", 0)
    uncertainty = events.get("uncertainty_marks", 0)
    positive = events.get("positive_finds", 0)
    self_corrections = events.get("self_corrections", 0)

    score = 1.0
    score -= failures * 0.3
    score -= uncertainty * 0.2
    score += positive * 0.1
    score += self_corrections * 0.05
    return max(0.0, min(1.0, score))


def format_timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def write_feedback(report: dict) -> bool:
    """寫入回饋到留言板側邊檔案，低於閾值才寫。"""
    score = compute_score(report)
    dominant = report.get("dominant_need", "?")
    valence = report.get("valence", 0)
    events = report.get("events", {})
    failures = events.get("failures", 0)
    uncertainty = events.get("uncertainty_marks", 0)

    if score >= SCORE_THRESHOLD and failures == 0 and uncertainty == 0:
        return False  # 不需要回饋

    # 建立回饋內容
    ts = format_timestamp()
    lines = []
    lines.append(f"## 評估回饋 — {ts}")
    lines.append(f"")
    lines.append(f"| 項目 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 分數 | {score:.2f} |")
    lines.append(f"| 主導需求 | {dominant} |")
    lines.append(f"| 情緒價 | {valence:+.2f} |")
    lines.append(f"| 失敗事件 | {failures} |")
    lines.append(f"| 不確定標記 | {uncertainty} |")
    lines.append(f"")

    if score < SCORE_THRESHOLD:
        lines.append(f"⚠️ 分數 {score:.2f} 低於閾值 {SCORE_THRESHOLD}，建議檢視該 session。")
    if failures > 0:
        lines.append(f"⚠️ 偵測到 {failures} 次失敗事件，可能需調整。")
    if uncertainty > 0:
        lines.append(f"ℹ️ 有 {uncertainty} 處不確定標記。")
    lines.append(f"")
    lines.append(f"— 自動回饋（aris-evaluator）")
    lines.append(f"")

    # 寫入（append）
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"✅ 回饋已寫入 {FEEDBACK_FILE}")
    print(f"   分數: {score:.2f}, 失敗: {failures}, 不確定: {uncertainty}")
    return True


def find_last_session_log() -> str:
    """找 scream 最新的 session log。"""
    session_dir = Path.home() / ".scream-code" / "sessions"
    if not session_dir.exists():
        # 也檢查 .pi/sessions
        session_dir = Path.home() / ".pi" / "agent" / "sessions"
    if not session_dir.exists():
        # 也檢查 .claude/sessions
        session_dir = Path.home() / ".claude" / "sessions"

    if not session_dir.exists():
        print(f"❌ 找不到 session 目錄", file=sys.stderr)
        sys.exit(1)

    # 找最新的 session 檔
    sessions = sorted(session_dir.glob("**/wire.jsonl"), key=os.path.getmtime, reverse=True)
    if not sessions:
        sessions = sorted(session_dir.glob("**/session_*/agents/main/wire.jsonl"),
                          key=os.path.getmtime, reverse=True)

    if not sessions:
        print(f"❌ 找不到 session log", file=sys.stderr)
        sys.exit(1)

    return str(sessions[0])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--last":
        log_path = find_last_session_log()
        print(f"📄 評估最新 session: {log_path}")
    elif len(sys.argv) > 1 and sys.argv[1] == "--watch":
        print("👀 監聽模式（每 30 分鐘檢查新 session）")
        last_checked = ""
        while True:
            latest = find_last_session_log()
            if latest != last_checked:
                last_checked = latest
                print(f"  新 session: {latest}")
                try:
                    report = psi_evaluate(latest)
                    write_feedback(report)
                except Exception as e:
                    print(f"  ⚠️ 評估失敗: {e}")
            time.sleep(1800)  # 30 min
        return
    elif len(sys.argv) > 1:
        log_path = sys.argv[1]
    else:
        print("用法: python3 evaluate-and-feedback.py <session_log> | --last | --watch")
        sys.exit(1)

    # 評估單一 session
    print(f"📄 評估: {log_path}")
    try:
        report = psi_evaluate(log_path)
        score = compute_score(report)
        print(f"   分數: {score:.2f}")
        print(f"   主導需求: {report.get('dominant_need', '?')}")
        written = write_feedback(report)
        if written:
            print(f"   ✅ 回饋已寫入")
        else:
            print(f"   ✅ 分數正常，無需回饋")
    except Exception as e:
        print(f"❌ 評估失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()