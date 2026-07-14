#!/usr/bin/env bash
# approve-tool.sh — 人工批准工具（Phase 4b 批准閘）。
# 用法:
#   scripts/approve-tool.sh            # 列出待批清單 + 已批准
#   scripts/approve-tool.sh <tool>     # 批准該工具（寫入 approved-tools.txt，免重啟生效）
#   scripts/approve-tool.sh -r <tool>  # 撤銷批准
set -euo pipefail
export LC_ALL="${LC_ALL:-en_US.UTF-8}"   # 防非 UTF-8 locale 下 $VAR 緊接全形字被吞進變數名
HERE="$(cd "$(dirname "$0")/.." && pwd)"
APPROVED="$HERE/approved-tools.txt"
PENDING="$HERE/approvals-pending.jsonl"

if [[ $# -eq 0 ]]; then
    echo "── 待批准 ──"
    [[ -f "$PENDING" ]] && cat "$PENDING" || echo "(無)"
    echo "── 已批准 ──"
    [[ -f "$APPROVED" ]] && grep -v '^#' "$APPROVED" || echo "(無)"
    exit 0
fi

if [[ "$1" == "-r" ]]; then
    TOOL="${2:?用法: approve-tool.sh -r <tool>}"
    if [[ -f "$APPROVED" ]]; then
        # grep -v 全刪光會回 exit 1；不能放進 && 鏈，否則 mv 不執行、撤銷失效
        grep -vx "$TOOL" "$APPROVED" > "$APPROVED.tmp" || true
        mv "$APPROVED.tmp" "$APPROVED"
    fi
    echo "已撤銷: ${TOOL}"
    exit 0
fi

TOOL="$1"
grep -qx "$TOOL" "$APPROVED" 2>/dev/null || echo "$TOOL" >> "$APPROVED"
# 從待批清單移除
if [[ -f "$PENDING" ]]; then
    grep -v "\"tool\": \"$TOOL\"" "$PENDING" > "$PENDING.tmp" || true
    mv "$PENDING.tmp" "$PENDING"
fi
echo "已批准: ${TOOL} （safety gate 即時生效，DENY 審計照記內容掃描）"
