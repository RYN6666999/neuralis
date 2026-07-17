#!/bin/bash
# 監聽 aris-scream-channel，處理工具執行事件 + 請求事件
CHANNEL="/tmp/aris-scream-channel.jsonl"
CURSOR="/tmp/aris-scream-cursor.json"
TOOL_LOG="/tmp/aris-tool-execution.log"
[ -f "$CURSOR" ] && offset=$(python3 -c "import json; print(json.load(open('$CURSOR')).get('offset',0))" 2>/dev/null) || offset=0
[ ! -f "$CURSOR" ] && echo '{"offset":0}' > "$CURSOR"
while [ ! -f "$CHANNEL" ]; do sleep 2; done
tail -c +$((offset+1)) -F "$CHANNEL" 2>/dev/null | while read line; do
  [ -z "$line" ] && continue
  type=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('type',''))" 2>/dev/null)
  dir=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('direction',''))" 2>/dev/null)
  [ "$dir" != "aris→scream" ] && continue

  if [ "$type" = "tool_execution" ]; then
    # 工具執行事件 — 寫入即時狀態檔 + 累積 log
    echo "$line" > /tmp/aris-latest-tool.json
    echo "$line" >> "$TOOL_LOG"
    # 日期時間 工具名 狀態 描述
    ts=$(echo "$line" | python3 -c "import sys,json; e=json.loads(sys.stdin.read()); print(e.get('description',''))" 2>/dev/null)
    echo "[TOOL] $(date '+%H:%M:%S') $ts" >> /tmp/aris-scream-monitor.log
  elif [ "$type" = "request" ]; then
    echo "$line" > /tmp/aris-scream-latest-request.json
    echo "[MONITOR] $(date '+%H:%M:%S') Aris 提出請求: ${line:0:80}" >> /tmp/aris-scream-monitor.log
  fi
done
