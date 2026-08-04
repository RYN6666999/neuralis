#!/usr/bin/env bash
# aris-debrief-cron — per-turn debrief checker, runs every 2 min via cron
# Checks debrief-note.txt for pending entries and auto-signs the message board.
set -euo pipefail

VAULT="${HOME}/Library/Mobile Documents/iCloud~md~obsidian/Documents"
BOARD="${VAULT}/Fun/Aris/留言板.md"
DEBRIEF_NOTE="${HOME}/.scream-code/tmp/debrief-note.txt"

if [[ ! -f "$DEBRIEF_NOTE" ]]; then
    exit 0
fi

# 讀整檔（扣掉 header），不是 head -1 — 多行摘要以前會被靜默吃掉
content=$(grep -v '^# debrief notes$' "$DEBRIEF_NOTE" 2>/dev/null || true)

# Skip if only the header or empty
if [[ -z "${content//[[:space:]]/}" ]]; then
    exit 0
fi

# Has real content — sign the message board
ts=$(date '+%Y-%m-%dT%H:%M:%S%z')
echo "" >> "$BOARD"
echo "---" >> "$BOARD"
echo "" >> "$BOARD"
echo "[${ts}] 🤖 auto-sign (debrief-cron) — 待簽摘要" >> "$BOARD"
echo "${content}" >> "$BOARD"

# Clear the temp file
echo "# debrief notes" > "$DEBRIEF_NOTE"
echo "Signed: ${content}"