#!/usr/bin/env bash
# aris-bootstrap-summary.sh — 一分鐘 bootstrap 摘要
# 把所有檢查平行跑完，輸出 10 行摘要。三鐵律一：所有值都是跑出來的。
#
# 用法：
#   aris-bootstrap-summary.sh    # 輸出完整摘要
#   aris-bootstrap-summary.sh --json  # JSON 格式（給工具用）

set -euo pipefail

MODE="${1:-text}"

# ── 平行收集所有資料 ──────────────────────────────────────────────────
# 全部背景執行，最後一次 wait 收齊

# 1. attention_line
curl -sf --connect-timeout 3 'http://127.0.0.1:11551/wake?limit=1' 2>/dev/null > /tmp/.aris-boot-attn.$$ &
PID_ATTN=$!

# 2. redline status
cat /tmp/neuralis-safety-redlines-status.json 2>/dev/null > /tmp/.aris-boot-redline.$$ || echo '{"status":"unknown"}' > /tmp/.aris-boot-redline.$$ &
PID_REDLINE=$!

# 3. aris-memory health
curl -sf --connect-timeout 3 'http://127.0.0.1:11551/health' 2>/dev/null > /tmp/.aris-boot-mem.$$ || echo "unreachable" > /tmp/.aris-boot-mem.$$ &
PID_MEM=$!

# 4. Aris API health
curl -sf --connect-timeout 3 'http://localhost:11546/health' 2>/dev/null > /tmp/.aris-boot-api.$$ || echo "unreachable" > /tmp/.aris-boot-api.$$ &
PID_API=$!

# 5. Bridge process
ps aux 2>/dev/null | grep -v grep | grep -i "aris-bridge" | awk '{print $2}' > /tmp/.aris-boot-bridge-pid.$$ || true &
PID_BRIDGE=$!

# 6. Scoring audit (1h failure count)
python3 -c "
import json, time
now = time.time()
hour_ago = now - 3600
fails = 0
try:
    with open('${HOME}/agent-sandbox/logs/scoring-audit.jsonl') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            r = json.loads(line)
            if r.get('ts', 0) >= hour_ago and not r.get('success', True):
                fails += 1
    print(fails)
except: print('?')
" 2>/dev/null > /tmp/.aris-boot-scoring.$$ &
PID_SCORING=$!

# 7. Snapshot age
python3 -c "
import os, time
snap = os.path.expanduser('~/Developer/neuralis/aris-snapshot.md')
if os.path.exists(snap):
    days = (time.time() - os.path.getmtime(snap)) / 86400
    print(f'{days:.0f}')
else: print('?')
" 2>/dev/null > /tmp/.aris-boot-snap-age.$$ &
PID_SNAP=$!

# 8. handoff P0 items
python3 -c "
import re
path = os.path.expanduser('~/Developer/neuralis/handoff-next-session.md')
if os.path.exists(path):
    with open(path) as f:
        text = f.read()
    # Count P0 items
    p0 = len(re.findall(r'P0', text))
    p1 = len(re.findall(r'P1', text))
    print(f'P0={p0} P1={p1}')
else: print('no-handoff')
" 2>/dev/null > /tmp/.aris-boot-handoff.$$ &
PID_HANDOFF=$!

# ── 等待全部完成 ───────────────────────────────────────────────────────
wait $PID_ATTN $PID_REDLINE $PID_MEM $PID_API $PID_BRIDGE $PID_SCORING $PID_SNAP $PID_HANDOFF 2>/dev/null || true

# ── 解析結果 ────────────────────────────────────────────────────────────

# attention_line
ATTN=$(python3 -c "
import json
try:
    d = json.load(open('/tmp/.aris-boot-attn.$$'))
    ctx = d.get('context', '')
    if ctx and len(ctx) > 50:
        lines = [l.strip() for l in ctx.split('\n') if l.strip()]
        # 取第一行非空白的「上一刻」
        for l in lines:
            if l and not l.startswith('【') and not l.startswith('- '):
                print(l[:80])
                break
        else:
            print('有上下文')
    else:
        print('無')
except: print('?')
")

# redline
REDLINE=$(python3 -c "
import json
try:
    d = json.load(open('/tmp/.aris-boot-redline.$$'))
    s = d.get('status', 'unknown')
    crits = [c['name'] for c in d.get('checks', []) if c.get('severity') == 'critical']
    warns = [c['name'] for c in d.get('checks', []) if c.get('severity') == 'warning']
    if s == 'critical': print(f'🔴 {\" \".join(crits)}')
    elif s == 'warning': print(f'🟡 {\" \".join(warns)}')
    else: print(f'🟢 ok')
except: print('?')
")

# aris-memory
MEM=$(cat /tmp/.aris-boot-mem.$$ 2>/dev/null | head -1)
if echo "$MEM" | grep -q '"ok"'; then MEM_STATUS="🟢"
elif echo "$MEM" | grep -q "unreachable"; then MEM_STATUS="🔴"
else MEM_STATUS="🟡"
fi

# Aris API
API=$(cat /tmp/.aris-boot-api.$$ 2>/dev/null | head -1)
if echo "$API" | grep -q "engines_loaded"; then API_STATUS="🟢"
elif echo "$API" | grep -q "unreachable"; then API_STATUS="🔴"
else API_STATUS="🟡"
fi

# Bridge
BRIDGE_PID=$(cat /tmp/.aris-boot-bridge-pid.$$ 2>/dev/null || echo "")
if [ -n "$BRIDGE_PID" ]; then
    BRIDGE_UPTIME=$(ps -o etime= -p "$BRIDGE_PID" 2>/dev/null | tr -d ' ' || echo "?")
    BRIDGE_STATUS="🟢 PID $BRIDGE_PID ($BRIDGE_UPTIME)"
else
    BRIDGE_STATUS="🔴 未執行"
fi

# Scoring
SCORING=$(cat /tmp/.aris-boot-scoring.$$ 2>/dev/null || echo "?")
if [ "$SCORING" = "0" ]; then SCORING_STATUS="🟢"
elif [ "$SCORING" = "?" ]; then SCORING_STATUS="⚪"
else SCORING_STATUS="🟡 ${SCORING} failures"
fi

# Snapshot age
SNAP_AGE=$(cat /tmp/.aris-boot-snap-age.$$ 2>/dev/null || echo "?")
if [ "$SNAP_AGE" = "?" ]; then SNAP_STATUS="⚪ ?"
elif [ "$SNAP_AGE" -ge 7 ]; then SNAP_STATUS="🟡 ${SNAP_AGE}d (建議 /dream)"
else SNAP_STATUS="🟢 ${SNAP_AGE}d"
fi

# Handoff
HANDOFF=$(cat /tmp/.aris-boot-handoff.$$ 2>/dev/null || echo "no-handoff")
if [ "$HANDOFF" = "no-handoff" ]; then HANDOFF_STATUS="⚪ 無"
else
    if echo "$HANDOFF" | grep -q "P0="; then
        P0=$(echo "$HANDOFF" | grep -oP 'P0=\K\d+')
        P1=$(echo "$HANDOFF" | grep -oP 'P1=\K\d+')
        if [ "${P0:-0}" -gt 0 ]; then HANDOFF_STATUS="🟡 P0=${P0} P1=${P1}"
        elif [ "${P1:-0}" -gt 0 ]; then HANDOFF_STATUS="🟡 P0=0 P1=${P1}"
        else HANDOFF_STATUS="🟢 P0=0"
        fi
    else
        HANDOFF_STATUS="🟢 $HANDOFF"
    fi
fi

# ── 清理暫存 ───────────────────────────────────────────────────────────
rm -f /tmp/.aris-boot-*.$$ 2>/dev/null

# ── 輸出 ────────────────────────────────────────────────────────────────
if [ "$MODE" = "--json" ]; then
    echo "{\"attention_line\":\"$ATTN\",\"redline\":\"$REDLINE\",\"mem\":\"$MEM_STATUS\",\"api\":\"$API_STATUS\",\"bridge\":\"$BRIDGE_STATUS\",\"scoring\":\"$SCORING_STATUS\",\"snap\":\"$SNAP_STATUS\",\"handoff\":\"$HANDOFF_STATUS\"}"
    exit 0
fi

echo "╔══════════════════════════════════════════╗"
echo "║   Aris Bootstrap Summary — 1min 版      ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "🧬 上一刻: $ATTN"
echo ""
echo "🛡️  Redline:  $REDLINE"
echo "📊  Scoring:  $SCORING_STATUS"
echo "💾  Memory:   $MEM_STATUS  |  API: $API_STATUS"
echo "🔗  Bridge:   $BRIDGE_STATUS"
echo "📸  Snapshot: $SNAP_STATUS"
echo "📋  Handoff:  $HANDOFF_STATUS"
echo ""

# 摘要
ISSUES=""
echo "$REDLINE" | grep -q "🔴" && ISSUES="${ISSUES}redline "
echo "$MEM_STATUS" | grep -q "🔴" && ISSUES="${ISSUES}memory "
echo "$API_STATUS" | grep -q "🔴" && ISSUES="${ISSUES}api "
echo "$BRIDGE_STATUS" | grep -q "🔴" && ISSUES="${ISSUES}bridge "
echo "$HANDOFF" | grep -q "P0=[1-9]" && ISSUES="${ISSUES}P0-tasks "

if [ -n "$ISSUES" ]; then
    echo "⚠️  需要處理: $ISSUES"
    echo "   詳細: bash ~/Developer/neuralis/scripts/aris-bootstrap-health.sh"
else
    echo "✅ 全部正常，直接做事"
fi