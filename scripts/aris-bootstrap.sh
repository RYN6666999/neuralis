#!/usr/bin/env bash
# aris-bootstrap.sh — 機械化 Bootstrap 檢查
# 三鐵律一：事實只能推導，不能複製。所有值都是跑出來的，不是寫死的。
#
# 用法：
#   aris-bootstrap.sh              # 完整檢查 + 輸出
#   aris-bootstrap.sh --check-only # exit code のみ
#   aris-bootstrap.sh --check      # exit code + 簡短一行
#
# exit code:
#   0 = 全部通過
#   1 = snapshot 缺失（致命）
#   2 = vault 不可讀（可恢復）
#   3 = gbrain API 不可達（可恢復）
#   4 = 多重失敗

set -euo pipefail

VAULT="${HOME}/Library/Mobile Documents/iCloud~md~obsidian/Documents"
SNAPSHOT="${HOME}/Developer/neuralis/aris-snapshot.md"
API_HEALTH="http://localhost:11546/health"
MODE="${1:-full}"

all_pass=true
failures=()

# ── 1. Snapshot ────────────────────────────────────────
check_snapshot() {
    if [ ! -f "$SNAPSHOT" ]; then
        echo "  🔴 snapshot — 不存在: $SNAPSHOT"
        failures+=("snapshot:missing")
        return 1
    fi
    local size
    size=$(stat -f%z "$SNAPSHOT" 2>/dev/null || stat -c%s "$SNAPSHOT" 2>/dev/null || echo "0")
    if [ "$size" -lt 100 ]; then
        echo "  🔴 snapshot — 檔案過小 ($size bytes)"
        failures+=("snapshot:too-small")
        return 1
    fi
    # 驗證有內容（最後更新時間戳）
    if grep -q "Autoupdated by cron" "$SNAPSHOT" 2>/dev/null; then
        echo "  ✅ snapshot — $(head -1 "$SNAPSHOT"), ${size}bytes"
        return 0
    fi
    # 沒 cron 簽名但檔案存在且夠大 → 仍可接受
    echo "  ✅ snapshot — ${size}bytes（無 autoupdate 簽名）"
    return 0
}

# ── 2. Vault ────────────────────────────────────────────
check_vault() {
    local board="${VAULT}/Fun/Aris/留言板.md"
    if [ ! -f "$board" ]; then
        echo "  🔴 vault — 留言板.md 不存在"
        failures+=("vault:board-missing")
        return 1
    fi
    local board_size board_lines
    board_size=$(stat -f%z "$board" 2>/dev/null || stat -c%s "$board" 2>/dev/null || echo "0")
    board_lines=$(wc -l < "$board" 2>/dev/null || echo "0")
    if [ "$board_size" -lt 500 ]; then
        echo "  🔴 vault — 留言板過小 ($board_size bytes)"
        failures+=("vault:board-too-small")
        return 1
    fi
    # 列出 vault 關鍵檔案可用性
    local files=("關係日記.md" "自我認知.md" "成長日記.md" "認知遷移.md")
    local found=0
    for f in "${files[@]}"; do
        if [ -f "${VAULT}/Fun/Aris/${f}" ]; then
            found=$((found + 1))
        fi
    done
    echo "  ✅ vault — 留言板 ${board_size}b/${board_lines}行，${found}/4 關鍵檔案存在"
    return 0
}

# ── 3. gbrain API ──────────────────────────────────────
check_gbrain() {
    if curl -sf --connect-timeout 3 "$API_HEALTH" >/dev/null 2>&1; then
        local status
        status=$(curl -s --connect-timeout 3 "$API_HEALTH" 2>/dev/null | head -1)
        echo "  ✅ gbrain — $API_HEALTH → $status"
        return 0
    fi
    echo "  🔴 gbrain — $API_HEALTH 不可達"
    failures+=("gbrain:unreachable")
    return 1
}

# ── 4. AgentOS ─────────────────────────────────────────
check_agentos() {
    if curl -sf --connect-timeout 2 http://localhost:8000/health >/dev/null 2>&1; then
        echo "  ✅ agentos — :8000 運行中"
        return 0
    fi
    echo "  ⚠️  agentos — :8000 未啟動（可選）"
    return 0  # 非致命
}

# ── Main ───────────────────────────────────────────────
if [ "$MODE" = "--check-only" ] || [ "$MODE" = "--check" ]; then
    check_snapshot >/dev/null 2>&1 || true
    check_vault >/dev/null 2>&1 || true
    check_gbrain >/dev/null 2>&1 || true
    if [ ${#failures[@]} -eq 0 ]; then
        [ "$MODE" = "--check" ] && echo "✅ bootstrap: pass"
        exit 0
    fi
    if [ "$MODE" = "--check" ]; then
        echo "❌ bootstrap: ${failures[*]}"
    fi
    # 用最高優先級錯誤碼
    for f in "${failures[@]}"; do
        case "$f" in
            snapshot:*) exit 1 ;;
            vault:*)    exit 2 ;;
            gbrain:*)   exit 3 ;;
        esac
    done
    exit 4
fi

# ── Fast mode ──────────────────────────────────────────
if [ "$MODE" = "--fast" ]; then
    SUMMARY="${HOME}/Developer/neuralis/scripts/aris-bootstrap-summary.sh"
    if [ -f "$SUMMARY" ]; then
        bash "$SUMMARY"
        exit 0
    fi
    # fallback: 沒 summary 腳本時走完整檢查
    MODE="full"
fi

# ── Full output ────────────────────────────────────────
echo "🧪 Aris Bootstrap Check"
echo ""

echo "📄 Snapshot"
check_snapshot || all_pass=false

echo ""
echo "📁 Vault（OB）"
check_vault || all_pass=false

echo ""
echo "🧠 gbrain API"
check_gbrain || all_pass=false

echo ""
echo "⚙️  AgentOS"
check_agentos

echo ""
echo "🔍 Health Scan"
HEALTH_SCRIPT="${HOME}/Developer/neuralis/scripts/aris-bootstrap-health.sh"
if [ -f "$HEALTH_SCRIPT" ]; then
    bash "$HEALTH_SCRIPT" --summary 2>/dev/null || true
else
    echo "  ⚪ health scan — 腳本不存在"
fi

echo ""
if $all_pass && [ ${#failures[@]} -eq 0 ]; then
    echo "✅ Bootstrap: ALL PASS"
    exit 0
else
    echo "⚠️  Bootstrap: ${#failures[@]} failure(s) — ${failures[*]}"
    echo "   修復後重跑: aris-bootstrap.sh --check"
    exit 4
fi