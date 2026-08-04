#!/usr/bin/env bash
# check-signoff.sh — 簽名逾期通知
# 檢查 Ryan 是否每週簽署了 signed-off.md

SIGNOFF_FILE="$(cd "$(dirname "$0")/.." && pwd)/brain/signed-off.md"
MAX_DAYS=7

if [ ! -f "$SIGNOFF_FILE" ]; then
    echo "missing: $SIGNOFF_FILE"
    exit 1
fi

# 取最後一次簽名日期（## YYYY-MM-DD 格式，排除 ## 規則 這類非簽名行）
LAST_SIGNED=$(grep -E '^## [0-9]{4}-[0-9]{2}-[0-9]{2}' "$SIGNOFF_FILE" | grep -v '規則\|規則' | head -1 | sed 's/^## //')

if [ -z "$LAST_SIGNED" ]; then
    echo "no sign-off date found in $SIGNOFF_FILE"
    exit 1
fi

# macOS date
if [[ "$(uname)" == "Darwin" ]]; then
    LAST_TS=$(date -j -f "%Y-%m-%d" "$LAST_SIGNED" "+%s" 2>/dev/null)
else
    LAST_TS=$(date -d "$LAST_SIGNED" "+%s" 2>/dev/null)
fi

if [ -z "$LAST_TS" ]; then
    echo "cannot parse date: $LAST_SIGNED"
    exit 1
fi

NOW_TS=$(date "+%s")
DAYS_AGO=$(( (NOW_TS - LAST_TS) / 86400 ))

if [ "$1" == "--cron" ]; then
    if [ "$DAYS_AGO" -gt "$MAX_DAYS" ]; then
        echo "signoff overdue: ${DAYS_AGO}d (max ${MAX_DAYS}d) last: $LAST_SIGNED"
        exit 1
    fi
    exit 0
fi

echo "last sign-off: $LAST_SIGNED (${DAYS_AGO}d ago)"
if [ "$DAYS_AGO" -gt "$MAX_DAYS" ]; then
    echo "OVERDUE by $((DAYS_AGO - MAX_DAYS))d"
    exit 1
else
    echo "valid ($((MAX_DAYS - DAYS_AGO))d remaining)"
    exit 0
fi