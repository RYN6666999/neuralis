#!/bin/bash
# 監聽 aris-scream-channel，處理工具執行事件 + 請求事件 + 任務事件
# v2: 整合 AgentOS Aris Bridge — 工具執行/請求事件仍由 monitor 記錄，
#     任務事件由 agentos-aris-bridge daemon 處理（本腳本會自動啟動 bridge）。
CHANNEL="/tmp/aris-scream-channel.jsonl"
CURSOR="/tmp/aris-scream-cursor.json"
TOOL_LOG="/tmp/aris-tool-execution.log"
BRIDGE_SCRIPT="$HOME/Developer/neuralis/scripts/agentos-aris-bridge.py"
BRIDGE_PID_FILE="/tmp/agentos-aris-bridge.pid"

# 自動啟動 AgentOS Aris Bridge（如果未運行）
if [ -f "$BRIDGE_SCRIPT" ]; then
  if ! ps aux | grep -q "[a]gentos-aris-bridge"; then
    python3 "$BRIDGE_SCRIPT" --daemon 2>/dev/null
    for i in 1 2 3; do
      sleep 1
      pid=$(ps aux | grep "agentos-aris-bridge" | grep -v grep | awk '{print $2}' | head -1)
      if [ -n "$pid" ]; then
        echo "$pid" > "$BRIDGE_PID_FILE"
        echo "[MONITOR] AgentOS Aris Bridge 已自動啟動 (PID $pid)" >> /tmp/aris-scream-monitor.log
        break
      fi
    done
  fi
fi

[ -f "$CURSOR" ] && offset=$(python3 -c "import json; print(json.load(open('$CURSOR')).get('offset',0))" 2>/dev/null) || offset=0
[ ! -f "$CURSOR" ] && echo '{"offset":0}' > "$CURSOR"
while [ ! -f "$CHANNEL" ]; do sleep 2; done
tail -c +$((offset+1)) -F "$CHANNEL" 2>/dev/null | while read line; do
  [ -z "$line" ] && continue
  type=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('type',''))" 2>/dev/null)
  dir=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('direction',''))" 2>/dev/null)
  [ "$dir" != "aris→scream" ] && continue

  if [ "$type" = "tool_execution" ]; then
    echo "$line" > /tmp/aris-latest-tool.json
    echo "$line" >> "$TOOL_LOG"
    ts=$(echo "$line" | python3 -c "import sys,json; e=json.loads(sys.stdin.read()); print(e.get('description',''))" 2>/dev/null)
    echo "[TOOL] $(date '+%H:%M:%S') $ts" >> /tmp/aris-scream-monitor.log
  elif [ "$type" = "request" ]; then
    echo "$line" > /tmp/aris-scream-latest-request.json
    echo "[MONITOR] $(date '+%H:%M:%S') Aris 提出請求 (AgentOS bridge 將處理): ${line:0:80}" >> /tmp/aris-scream-monitor.log
  elif [ "$type" = "task" ]; then
    echo "[MONITOR] $(date '+%H:%M:%S') Aris 委派任務 (AgentOS bridge 將執行): ${line:0:80}" >> /tmp/aris-scream-monitor.log
  fi
done
