#!/usr/bin/env bash
# scream-code 更新 + 補丁一鍵重套
# 用法: ./update-scream.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 1/2 更新 scream-code ==="
npm update -g scream-code 2>&1 | tail -3

echo ""
echo "=== 2/2 重套補丁 ==="
bash "$SCRIPT_DIR/apply-all-patches.sh"