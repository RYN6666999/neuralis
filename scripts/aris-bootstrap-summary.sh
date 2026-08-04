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
import os, re
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
elif [ -z "$HANDOFF" ] || [ "$HANDOFF" = "?" ]; then HANDOFF_STATUS="🔴 讀取失敗（空內容）"
else
    if echo "$HANDOFF" | grep -q "P0="; then
        P0=$(echo "$HANDOFF" | sed 's/.*P0=//;s/ .*//')
        P1=$(echo "$HANDOFF" | sed 's/.*P1=//;s/ .*//')
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

# 進程新鮮度：跑著的 API 是不是磁碟上最新的碼。
# 「改了檔就當作生效」是實測出來的固定失敗模式，這行把它變成看得見的紅燈。
#
# 用 ps -o etime=（純數字 [[dd-]hh:]mm:ss）不用 lstart。
# lstart 是 "Wed Aug  5 01:37:59 2026" 這種帶月份名的格式，要 strptime 解，
# 換個環境就 ValueError（2026-08-05 在另一個 shell 實際炸過三次）。
# etime 沒有語系、沒有月份名、沒有雙空格對齊問題。
#
# 錯誤一律連訊息一起印。上一版只印 type(e).__name__，結果現場只看到
# 「ValueError」一個詞，無法診斷——那是自己違反「錯誤不准降級」。
STALE=$(python3 -c "
import os, subprocess, glob, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath('$0')))
try:
    pid = subprocess.run(['lsof','-ti','tcp:11546','-sTCP:LISTEN'],
                         capture_output=True, text=True).stdout.strip().split()
    if not pid:
        print('⚪ API 沒在跑'); raise SystemExit
    et = subprocess.run(['ps','-o','etime=','-p',pid[0]],
                        capture_output=True, text=True).stdout.strip()
    if not et:
        print('⚪ 抓不到 pid ' + pid[0] + ' 的 etime'); raise SystemExit
    days, _, clock = et.rpartition('-')
    parts = [int(x) for x in clock.split(':')]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    if days:
        secs += int(days) * 86400
    started = time.time() - secs
    src = glob.glob(os.path.join(ROOT, 'laap', '*.py'))
    if not src:
        print('⚪ 找不到 laap/*.py（ROOT=' + ROOT + '）'); raise SystemExit
    newer = [f for f in src if os.path.getmtime(f) > started]
    if newer:
        print('🔴 進程舊於 ' + ', '.join(os.path.basename(f) for f in newer[:3]) +
              ' —— 跑 scripts/reload-aris.sh')
    else:
        print('🟢')
except SystemExit:
    pass
except Exception as e:
    print('⚪ 無法判定: ' + type(e).__name__ + ': ' + str(e))
" || echo "⚪ 檢查失敗")
echo "♻️  進程碼:   $STALE"

# 金絲雀新鮮度。顯示的是「上次跑完距今多久」，不是「有沒有失敗」——
# 它死掉的表現形式是 canary.jsonl 停止增長，沒有人會注意到一個沒有新行的檔案。
# 沉默必須等於失敗，所以這裡看的是時間戳不是結果。
CANARY=$(python3 -c "
import json, os, time
p = os.path.expanduser('~/.neuralis/canary-state.json')
if not os.path.exists(p):
    print('🔴 從未跑過 —— python3 scripts/mutation-canary.py'); raise SystemExit
try:
    d = json.load(open(p))
except Exception as e:
    print('🔴 狀態檔壞了: ' + type(e).__name__ + ': ' + str(e)); raise SystemExit
h = (time.time() - d.get('last_run', 0)) / 3600
if not d.get('control_ok', False):
    print('🚨 CONTROL 失敗 —— 金絲雀偵測邏輯本身壞了，結果全部作廢')
elif h > 36:
    print('🔴 上次 %.0fh 前（超過 36h）—— 排程可能死了' % h)
else:
    dead = [k for k, v in (d.get('mechanisms') or {}).items() if not v.get('last_ok')]
    print(('🟡 %.0fh 前，閘門失效: ' % h) + ', '.join(dead) if dead else '🟢 %.0fh 前' % h)
" 2>&1 || echo "⚪ 檢查失敗")
echo "🐤  金絲雀:   $CANARY"
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

# 「我不確定」的守門。2026-08-05 一天內三次把可查證的事留成懸案：
# 常數來源不明（git log -S 就有）、ValueError 成因不明（git log 就有）、
# commit 宣稱是否屬實（git show 就有）。工單裡有防呆，自由對話沒有——
# 這行補的就是自由對話那段。放在最後一行，是每個 session 的最後一眼。
echo ""
echo "🚧 說「不確定」之前，先跑一條："
echo "   git log -S '<字串>' -- <檔>   誰引進的"
echo "   git log --oneline -5 -- <檔>  最近誰動過"
echo "   git show <sha> -- <檔>        那次到底改了什麼"
echo "   查過還是不確定 → 寫出你查了什麼、為什麼仍不確定。"