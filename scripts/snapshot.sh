#!/bin/bash
# snapshot.sh — 三層快照：git tag + gbrain export + neuralis state tar
# 動手升級前必跑。Usage: ./scripts/snapshot.sh [name]
# 輸出：~/aris-snapshots/<name>/  + git tag pre-upgrade-<name>-YYYYMMDD

set -euo pipefail

NAME="${1:-$(date +%Y%m%d-%H%M)}"
SNAPSHOT_DIR="$HOME/aris-snapshots/$NAME"
TIMESTAMP=$(date +%s)

mkdir -p "$SNAPSHOT_DIR"
echo "[snapshot] 🗂  Snapshot dir: $SNAPSHOT_DIR"

# ── 層 1｜git tag ──────────────────────────────────
TAG="pre-upgrade-$NAME-$(date +%Y%m%d)"
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/Developer/neuralis")"

if ! git rev-parse "$TAG" >/dev/null 2>&1; then
    git tag -a "$TAG" HEAD -m "pre-upgrade snapshot: $NAME ($(date '+%Y-%m-%d %H:%M'))"
    echo "[snapshot] ✅ git tag: $TAG"
else
    echo "[snapshot] ⚠️  git tag $TAG already exists, skipping"
fi

# ── 層 2｜neuralis 本地狀態 ─────────────────────────
STATE_TAR="$SNAPSHOT_DIR/state-$TIMESTAMP.tgz"
tar czf "$STATE_TAR" \
    status.json 2>/dev/null || true \
    *.jsonl 2>/dev/null || true \
    aris_brain 2>/dev/null || true \
    data 2>/dev/null || true
echo "[snapshot] ✅ state tar: $(du -h "$STATE_TAR" | cut -f1)"

# ── 層 2｜gbrain export ────────────────────────────
if command -v gbrain &>/dev/null; then
    GEXPORT="$SNAPSHOT_DIR/gbrain-export"
    mkdir -p "$GEXPORT"
    gbrain export --dir "$GEXPORT" 2>/dev/null && \
        echo "[snapshot] ✅ gbrain export: $(ls "$GEXPORT" 2>/dev/null | wc -l) files" || \
        echo "[snapshot] ⚠️  gbrain export failed (not running? SKIP)"
else
    echo "[snapshot] ⚠️  gbrain CLI not found, skip export"
fi

cat <<EOF

────────────────────────────────────────
✅ Snapshot complete: $NAME
   Location: $SNAPSHOT_DIR
   Git tag:  $TAG
   Rollback: ./scripts/rollback.sh $NAME
────────────────────────────────────────
EOF
