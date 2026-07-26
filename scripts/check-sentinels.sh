#!/usr/bin/env bash
# check-sentinels.sh — 機械化靜默失敗偵測
# 掃描 /tmp/aris-sentinels/ 下的哨兵檔，異常超過閾值秒數就寫留言板告警。
# 被健康檢查 cron 呼叫，不依賴 LLM 判斷。
set -u
SENTINEL_DIR="/tmp/aris-sentinels"
BOARD="/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/留言板.md"
THRESHOLD=600  # 10 分鐘

mkdir -p "$SENTINEL_DIR"
NOW=$(date +%s)
ALERTS=""

for f in "$SENTINEL_DIR"/*-*; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    mtime=$(stat -f "%m" "$f" 2>/dev/null || echo "0")
    age=$(( NOW - mtime ))
    if [ "$age" -gt "$THRESHOLD" ]; then
        ALERTS="$ALERTS
- ⚠️ $name: ${age}s 前觸發（閾值 ${THRESHOLD}s）"
    fi
done

# bridge 重複進程檢查
bridge_count=$(pgrep -f "agentos-aris-bridge" 2>/dev/null | grep -v grep | wc -l | tr -d ' ')
if [ "$bridge_count" -gt 1 ]; then
    touch "$SENTINEL_DIR/bridge-duplicate-${NOW}"
    ALERTS="$ALERTS
- ⚠️ bridge-duplicate: ${bridge_count} 個進程同時運行"
fi

# ratchet 空檔檢查
if [ -f "/Users/ryan/agent-sandbox/data/ratchet.json" ]; then
    if [ "$(cat /Users/ryan/agent-sandbox/data/ratchet.json)" = "{}" ]; then
        touch "$SENTINEL_DIR/ratchet-empty-${NOW}"
        ALERTS="$ALERTS
- ⚠️ ratchet-empty: ratchet.json 為空（畢業狀態遺失）"
    fi
fi

if [ -n "$ALERTS" ]; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
    echo "[$TIMESTAMP] Scream — ⚠️ 哨兵異常告警$ALERTS" >> "$BOARD"
    echo "[check-sentinels] Wrote alerts to 留言板"
else
    # 全部正常 → 清除久置的哨兵檔（但不清最近 5 分鐘內的，防止 race）
    for f in "$SENTINEL_DIR"/*-*; do
        [ -f "$f" ] || continue
        mtime=$(stat -f "%m" "$f" 2>/dev/null || echo "0")
        age=$(( NOW - mtime ))
        if [ "$age" -gt 300 ]; then
            rm -f "$f"
        fi
    done
    echo "[check-sentinels] All clear"
fi