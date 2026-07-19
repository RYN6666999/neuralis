#!/bin/bash
# rollback.sh — 從 snapshot 回滾三層狀態
# Usage: ./scripts/rollback.sh <snapshot-name>

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <snapshot-name>"
    echo "Available: ls ~/aris-snapshots/"
    exit 1
fi

NAME="$1"
SNAPSHOT_DIR="$HOME/aris-snapshots/$NAME"

if [[ ! -d "$SNAPSHOT_DIR" ]]; then
    echo "[rollback] ❌ Snapshot not found: $SNAPSHOT_DIR"
    exit 1
fi

echo "[rollback] ⚠️  即將回滾到 snapshot: $NAME"
echo "[rollback]    來源: $SNAPSHOT_DIR"
read -rp "  確認？(yes/no): " confirm
[[ "$confirm" == "yes" ]] || { echo "取消"; exit 1; }

# ── 步驟 0｜拉閘 ────────────────────────────────────
echo "[rollback] 🛑 拉閘..."
touch "$HOME/.aris-halt"
sleep 2
echo "[rollback] ✅ Halt signal issued"

# ── 步驟 1｜停 daemon ───────────────────────────────
echo "[rollback] 🔄 停 daemon..."
launchctl bootout gui/$(id -u)/com.neuralis.watchdog 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.neuralis.brain 2>/dev/null || true
pkill -f "laap_brain_api" 2>/dev/null || true
pkill -f "watchdog" 2>/dev/null || true
sleep 2
echo "[rollback] ✅ Daemon stopped"

# ── 步驟 2｜git reset ──────────────────────────────
cd "$HOME/Developer/neuralis"
TAG="pre-upgrade-$NAME-$(date +%Y%m%d)"
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "[rollback] 🔄 git reset --hard $TAG ..."
    git reset --hard "$TAG"
    echo "[rollback] ✅ Git reset to $TAG"
else
    # 試模糊匹配
    MATCH=$(git tag -l | grep "pre-upgrade-$NAME" | head -1)
    if [[ -n "$MATCH" ]]; then
        echo "[rollback] 🔄 git reset --hard $MATCH ..."
        git reset --hard "$MATCH"
        echo "[rollback] ✅ Git reset to $MATCH"
    else
        echo "[rollback] ⚠️  No git tag found for $NAME, skipping code rollback"
    fi
fi

# ── 步驟 3｜還原神經網路狀態 ─────────────────────────
STATE_TAR=$(ls "$SNAPSHOT_DIR"/state-*.tgz 2>/dev/null | head -1)
if [[ -n "$STATE_TAR" ]]; then
    echo "[rollback] 🔄 還原 state tar: $STATE_TAR"
    tar xzf "$STATE_TAR" -C "$HOME/Developer/neuralis/"
    echo "[rollback] ✅ State restored from tar"
else
    echo "[rollback] ⚠️  No state tar found, skip"
fi

# ── 步驟 4｜還原 gbrain ────────────────────────────
GEXPORT="$SNAPSHOT_DIR/gbrain-export"
if [[ -d "$GEXPORT" ]] && command -v gbrain &>/dev/null; then
    echo "[rollback] 🔄 gbrain import ..."
    gbrain import --dir "$GEXPORT" 2>/dev/null && \
        echo "[rollback] ✅ gbrain restored" || \
        echo "[rollback] ⚠️  gbrain import failed (may need manual)"
fi

# ── 步驟 5｜清除拉閘 + 重啟 ─────────────────────────
echo "[rollback] 🔄 清除拉閘..."
rm -f "$HOME/.aris-halt"
echo "[rollback] ✅ 拉閘清除"

echo "[rollback] 🔄 重啟 daemon... 請手動執行:"
echo "    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.neuralis.watchdog.plist"
echo "    或使用: ./scripts/reload-aris.sh"

cat <<EOF

────────────────────────────────────────
✅ Rollback 完成（部分需手動重啟）
   Snapshot: $NAME
   Git tag:  $TAG
────────────────────────────────────────
EOF
