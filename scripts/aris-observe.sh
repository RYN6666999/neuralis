#!/bin/bash
# Aris Observe — 即時思維監控終端
# 開新 terminal 視窗，即時顯示 Aris 正在做什麼、用什麼工具、結果如何
#
# 用法：
#   bash scripts/aris-observe.sh           # 開新視窗
#   bash scripts/aris-observe.sh --inline  # 在當前 terminal 跑

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRIDGE_LOG="/tmp/agentos-aris-bridge.log"
AUDIT_LOG="$HOME/agent-sandbox/logs/scoring-audit.jsonl"
CHANNEL="/tmp/aris-scream-channel.jsonl"
STATUS_SCRIPT="$SCRIPT_DIR/aris-status.py"

_render() {
    clear
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  Aris 即時思維監控    $(date '+%H:%M:%S')              ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo ""

    # 最近 bridge 活動
    echo "── Bridge 最近處理 ──"
    if [ -f "$BRIDGE_LOG" ]; then
        tail -6 "$BRIDGE_LOG" | while IFS= read -r line; do
            msg=$(echo "$line" | sed 's/.*[0-9]\{4\},[0-9]* //' | sed 's/\[agentos-bridge\] //')
            echo "  $msg"
        done
    else
        echo "  (等待 bridge 啟動...)"
    fi
    echo ""

    # 最近審計決策
    echo "── 最近 Scoring 決策 ──"
    if [ -f "$AUDIT_LOG" ]; then
        tail -4 "$AUDIT_LOG" | while IFS= read -r line; do
            lane=$(echo "$line" | python3 -c "
import sys,json
d=json.loads(sys.stdin.read().strip())
l=d.get('lane','?')
tc=d.get('task_class','?')
s=round(d.get('score',0),2)
so=d.get('sandbox_outcome','—')
c=d.get('sandbox_committed','')
print(f'{l:10s} {tc:20s} score={s:.2f}  sandbox={so} committed={c}')
" 2>/dev/null)
            echo "  $lane"
        done
    else
        echo "  (無審計資料)"
    fi
    echo ""

    # Aris 心理狀態
    echo "── Aris 心理狀態 ──"
    if [ -f "$STATUS_SCRIPT" ]; then
        python3 "$STATUS_SCRIPT" 2>/dev/null | head -5
    fi
    echo ""

    # 按鍵提示
    echo "  [Ctrl+C 離開]  更新每 3 秒"
}

# 開新 Terminal 視窗（預設行為）
if [ "$1" != "--inline" ]; then
    osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    set newWindow to do script "cd $SCRIPT_DIR && bash aris-observe.sh --inline"
    set custom title of newWindow to "Aris Observe"
end tell
APPLESCRIPT
    exit 0
fi

# --inline 模式：直接在當前 terminal 跑迴圈
while true; do
    _render
    sleep 3
done