#!/bin/bash
# 即時觀看 Aris 工具執行狀態 — 在 TUI 外的另一個終端視窗執行
# 用法: bash scripts/watch-tools.sh

TOOL_LOG="/tmp/aris-tool-execution.log"
CHANNEL="/tmp/aris-scream-channel.jsonl"

printf '╔══════════════════════════════════════════════════╗\n'
printf '║   Aris 工具執行監視器                            ║\n'
printf '║   開另一個終端執行此腳本，即可看到 Aris 每一動    ║\n'
printf '╚══════════════════════════════════════════════════╝\n\n'

# 確保 log 檔存在
touch "$TOOL_LOG"

# 顯示最新狀態（如果檔案有內容）
if [ -f /tmp/aris-latest-tool.json ]; then
  printf '最新工具狀態:\n'
  python3 -c "
import json
with open('/tmp/aris-latest-tool.json') as f:
    e = json.load(f)
icon = e.get('icon','⚙️')
tool = e.get('tool','?')
status = e.get('status','?')
desc = e.get('description','')
elapsed = e.get('elapsed',0)
print(f'  {icon} [{status}] {tool}: {desc} ({elapsed}s)')
" 2>/dev/null || printf '  (無資料)\n'
  printf '\n'
fi

printf '正在監聽工具執行事件... (Ctrl+C 離開)\n'
printf '──────────────────────────────────────────────\n'

# tail -F 累積 log，每行解析後顯示
tail -F "$TOOL_LOG" 2>/dev/null | while read line; do
  [ -z "$line" ] && continue
  python3 -c "
import json, sys
try:
    e = json.loads('$line')
    icon = e.get('icon','⚙️')
    tool = e.get('tool','?')
    status = e.get('status','?')
    desc = e.get('description','')
    elapsed = e.get('elapsed', 0)
    ts = e.get('ts', 0)
    
    # 狀態圖示
    status_icon = {'start':'▶️','running':'🔄','done':'✅','fail':'❌','idle':'⏸️'}
    si = status_icon.get(status, '⚪')
    
    if status == 'start':
        print(f'{si} {icon} {tool} 開始 — {desc}')
    elif status == 'running':
        print(f'   {icon} 執行中... {desc[:50]}')
    elif status == 'done':
        print(f'{si} {icon} {tool} 完成 ({elapsed:.1f}s)')
    elif status == 'fail':
        print(f'❌ {icon} {tool} 失敗: {desc}')
    else:
        print(f'  [{status}] {icon} {tool}: {desc}')
except Exception:
    pass
" 2>/dev/null
done