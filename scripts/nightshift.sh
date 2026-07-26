#!/bin/zsh
# 夜班：固化 memos → gbrain，然後驗每條邊還通不通。
# probe 紅了就寫留言板 —— 留言板 watcher 會叫醒 Aris，不另造通知通道。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

echo "=== nightshift $(date '+%F %T') ==="
python3 scripts/consolidate-memos.py

python3 scripts/probe.py
rc=$?
if [ $rc -ne 0 ]; then
  BOARD="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/留言板.md"
  {
    printf '\n[%s] nightshift — 🔴 **拓樸有邊斷了**\n\n' "$(date '+%F %H:%M')"
    printf '```\n%s\n```\n\n' "$(python3 scripts/probe.py 2>&1 | grep -E '^(❌|🟡)')"
    printf '修法：`python3 scripts/probe.py <edge_id>` 單跑那條，對照 topology.yaml 的 contract。\n'
  } >> "$BOARD"
  echo "已寫留言板告警"
fi
exit $rc
