#!/usr/bin/env bash
# aris-bootstrap-health.sh — 主動掃問題模式
# 由 aris-bootstrap.sh 在啟動時呼叫，或獨立執行。
# 三鐵律一：所有值都是跑出來的，不是寫死的。
#
# 用法：
#   aris-bootstrap-health.sh           # 完整檢查 + 輸出
#   aris-bootstrap-health.sh --summary # 只剩一行摘要
#
# exit code:
#   0 = 全部健康
#   1 = 有 warning（非致命，但建議查看）
#   2 = 有 error（需要處理）

set -euo pipefail

MODE="${1:-full}"
issues=()
warnings=()

# ── Helper ──────────────────────────────────────────────────────
_red()    { echo "[31m$1[0m"; }
_green()  { echo "[32m$1[0m"; }
_yellow() { echo "[33m$1[0m"; }

# ── 1. Safety-redline 狀態 ─────────────────────────────────────
check_redline() {
    local status_file="/tmp/neuralis-safety-redlines-status.json"
    local status="unknown"
    local summary=""
    if [ -f "$status_file" ]; then
        status=$(python3 -c "
import json
try:
    d = json.load(open('$status_file'))
    print(d.get('status', 'unknown'))
except: print('parse-error')
" 2>/dev/null || echo "unknown")
        summary=$(python3 -c "
import json
try:
    d = json.load(open('$status_file'))
    crits = [c['name'] for c in d.get('checks', []) if c.get('severity') == 'critical']
    warns = [c['name'] for c in d.get('checks', []) if c.get('severity') == 'warning']
    if crits: print(f'CRITICAL: {\" \".join(crits)}')
    elif warns: print(f'warning: {\" \".join(warns)}')
    else: print('ok')
except: print('unknown')
" 2>/dev/null || echo "unknown")
    fi

    case "$status" in
        "critical")
            echo "  🔴 redline — $summary"
            issues+=("redline:critical")
            ;;
        "warning")
            echo "  🟡 redline — $summary"
            warnings+=("redline:warning")
            ;;
        "ok")
            echo "  🟢 redline — $summary"
            ;;
        *)
            echo "  ⚪ redline — 無法讀取狀態"
            warnings+=("redline:unknown")
            ;;
    esac
}

# ── 2. Scoring audit 最近失敗 ─────────────────────────────────
check_scoring_audit() {
    local audit_log="${HOME}/agent-sandbox/logs/scoring-audit.jsonl"
    if [ ! -f "$audit_log" ]; then
        echo "  ⚪ scoring audit — 無日誌檔案"
        return 0
    fi
    local result
    result=$(python3 -c "
import json, time
now = time.time()
hour_ago = now - 3600
fails = []
with open('$audit_log') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            r = json.loads(line)
            ts = r.get('ts', 0)
            if ts < hour_ago: continue
            if not r.get('success', True):
                lane = r.get('lane', '?')
                tc = r.get('task_class', '?') or '?'
                err = r.get('error', '') or ''
                fails.append(f'{lane}/{tc}: {err[:80]}')
        except: continue
if fails:
    print(f'{len(fails)} failures in 1h')
    for f in fails[:5]:
        print(f'    {f}')
    if len(fails) > 5:
        print(f'    ... and {len(fails)-5} more')
else:
    print('0 failures in 1h')
" 2>/dev/null) || result="parse-error"

    case "$result" in
        "0 failures in 1h")
            echo "  🟢 scoring audit — $result"
            ;;
        "parse-error")
            echo "  ⚪ scoring audit — 解析錯誤"
            ;;
        "")
            echo "  ⚪ scoring audit — 無資料"
            ;;
        *)
            local count
            count=$(echo "$result" | head -1 | grep -oP '^\d+')
            if [ "$count" -ge 5 ]; then
                echo "  🔴 $result" | head -1
                echo "$result" | tail -n +2
                issues+=("scoring:${count}failures")
            else
                echo "  🟡 $result" | head -1
                echo "$result" | tail -n +2
                warnings+=("scoring:${count}failures")
            fi
            ;;
    esac
}

# ── 3. Bridge log 最近錯誤 ────────────────────────────────────
check_bridge_log() {
    local log_file="/tmp/com.neuralis.task-executor.log"
    if [ ! -f "$log_file" ]; then
        log_file="/tmp/agentos-aris-bridge.log"
    fi
    if [ ! -f "$log_file" ]; then
        echo "  ⚪ bridge log — 無日誌檔案"
        return 0
    fi

    local result
    result=$(python3 -c "
import re, time
now = time.time()
hour_ago = now - 3600
errors = []
with open('$log_file') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        # 抓時間戳: 2026-08-03 19:57:15
        m = re.match(r'\[agentos-bridge\]\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', line)
        if not m: continue
        # 只要 ERROR 或 CRITICAL 或 WARNING
        if 'ERROR' in line or 'CRITICAL' in line or 'WARNING' in line:
            msg = line[:200]
            errors.append(msg)

if errors:
    print(f'{len(errors)} issues in bridge log')
    for e in errors[:5]:
        print(f'    {e[:150]}')
    if len(errors) > 5:
        print(f'    ... and {len(errors)-5} more')
else:
    print('no issues in bridge log')
" 2>/dev/null) || result="parse-error"

    case "$result" in
        "no issues in bridge log")
            echo "  🟢 bridge log — $result"
            ;;
        "parse-error")
            echo "  ⚪ bridge log — 解析錯誤"
            ;;
        "")
            echo "  ⚪ bridge log — 無資料"
            ;;
        *)
            echo "  🟡 $result" | head -1
            echo "$result" | tail -n +2
            warnings+=("bridge:log-issues")
            ;;
    esac
}

# ── 4. aris-memory 健康 ───────────────────────────────────────
check_aris_memory() {
    local result
    result=$(curl -sf --connect-timeout 3 http://127.0.0.1:11551/health 2>/dev/null || echo "unreachable")
    case "$result" in
        *"ok"*)
            echo "  🟢 aris-memory — :11551 健康"
            ;;
        "unreachable")
            echo "  🔴 aris-memory — :11551 不可達"
            issues+=("aris-memory:unreachable")
            ;;
        *)
            echo "  🟡 aris-memory — $result"
            warnings+=("aris-memory:degraded")
            ;;
    esac
}

# ── 5. Bridge 行程 ────────────────────────────────────────────
check_bridge_process() {
    local pid uptime
    pid=$(ps aux 2>/dev/null | grep -v grep | grep -i "aris-bridge" | awk '{print $2}' | head -1 || echo "")
    if [ -n "$pid" ]; then
        uptime=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ' || echo "?")
        echo "  🟢 bridge — PID $pid (uptime $uptime)"
    else
        echo "  🔴 bridge — 未執行"
        issues+=("bridge:not-running")
    fi
}

# ── 6. 記憶健康檢查 ────────────────────────────────────────────
check_memory_health() {
    # 檢查 aris-memory 條數
    local count
    count=$(curl -sf --connect-timeout 3 'http://127.0.0.1:11551/memories/query?q=' 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    if isinstance(d, list):
        print(len(d))
    elif isinstance(d, dict):
        print(d.get('total', d.get('count', len(d))))
    else:
        print('?')
except: print('?')
" 2>/dev/null || echo "?")
    echo "  🟢 aris-memory — ${count} 條記憶"

    # 檢查 /dream 是否需要（日期啟發式）
    local dream_check
    dream_check=$(python3 -c "
import time, os
now = time.time()
snap = os.path.expanduser('~/Developer/neuralis/aris-snapshot.md')
if os.path.exists(snap):
    mtime = os.path.getmtime(snap)
    days = (now - mtime) / 86400
    if days > 7:
        print(f'snapshot 最後更新 {days:.0f} 天前 — 建議 /dream')
    else:
        print(f'snapshot 更新於 {days:.0f} 天前')
" 2>/dev/null) || dream_check="無法檢查記憶健康"

    case "$dream_check" in
        *"建議 /dream"*)
            echo "  🟡 dream — $dream_check"
            warnings+=("memory:needs-consolidation")
            ;;
        *)
            echo "  🟢 dream — $dream_check"
            ;;
    esac
}

# ── 7. 乙的種子：attention_line ────────────────────────────────
check_attention_line() {
    local result
    result=$(curl -sf --connect-timeout 3 'http://127.0.0.1:11551/wake?limit=1' 2>/dev/null || echo "unreachable")
    if [ "$result" = "unreachable" ]; then
        echo "  ⚪ attention_line — aris-memory 不可達，跳過"
        return 0
    fi
    local has_context
    has_context=$(echo "$result" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    ctx = d.get('context', '')
    if ctx and len(ctx) > 50:
        print('yes')
    else:
        print('no')
except: print('no')
" 2>/dev/null || echo "no")
    if [ "$has_context" = "yes" ]; then
        echo "  🟢 attention_line — 有上一刻上下文"
    else
        echo "  🟡 attention_line — 無上一刻上下文（新 session 正常）"
    fi
}

# ── Main ───────────────────────────────────────────────────────
if [ "$MODE" = "--summary" ]; then
    # 只輸出摘要行
    check_redline >/dev/null 2>&1 || true
    check_scoring_audit >/dev/null 2>&1 || true
    check_bridge_log >/dev/null 2>&1 || true
    check_aris_memory >/dev/null 2>&1 || true
    check_bridge_process >/dev/null 2>&1 || true
    check_memory_health >/dev/null 2>&1 || true
    if [ ${#issues[@]} -gt 0 ]; then
        echo "❌ health: ${issues[*]}"
        exit 2
    elif [ ${#warnings[@]} -gt 0 ]; then
        echo "⚠️  health: ${warnings[*]}"
        exit 1
    else
        echo "✅ health: all pass"
        exit 0
    fi
fi

echo "🔍 Aris Health Scan"
echo ""

echo "🛡️  Safety"
check_redline

echo ""
echo "📊 Scoring"
check_scoring_audit

echo ""
echo "📋 Bridge"
check_bridge_log
check_bridge_process

echo ""
echo "💾 Memory"
check_aris_memory
check_memory_health

echo ""
echo "🧬 Attention Line"
check_attention_line

echo ""
if [ ${#issues[@]} -gt 0 ]; then
    echo "❌ ${#issues[@]} issue(s): ${issues[*]}"
    echo "⚠️  ${#warnings[@]} warning(s): ${warnings[*]}"
    exit 2
elif [ ${#warnings[@]} -gt 0 ]; then
    echo "⚠️  ${#warnings[@]} warning(s): ${warnings[*]}"
    exit 1
else
    echo "✅ All checks passed"
    exit 0
fi