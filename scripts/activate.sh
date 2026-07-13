#!/usr/bin/env bash
# activate.sh — 將 neuralis 疊加到 laap-AGI 環境
#
# 用法:
#   source ~/neuralis/scripts/activate.sh
#
# 這會將 neuralis/ 加到 PYTHONPATH 的最前面，
# 讓 laap-AGI 的模組能 import laap.* 和 aris_brain.*

NEURALIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ":$PYTHONPATH:" != *":$NEURALIS_DIR:"* ]]; then
    export PYTHONPATH="$NEURALIS_DIR:$PYTHONPATH"
    echo "[neuralis] 已疊加到 PYTHONPATH: $NEURALIS_DIR"
    echo "[neuralis] ❤️ 啟動 LAAP server 時 Aris 將自動有心跳"
else
    echo "[neuralis] 已在 PYTHONPATH 中"
fi
