#!/usr/bin/env bash
# neuralis patch 一鍵重套（npm update 後或任何 patch 失效時執行）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 1/5 aris-image patch ==="
python3 "$SCRIPT_DIR/patch-scream-image.py" || echo "⚠️ 跳過"

echo "=== 2/5 scream-tui patch ==="
python3 "$SCRIPT_DIR/patch-scream-tui.py" || echo "⚠️ 跳過"

echo "=== 3/5 scream-mcp-image patch ==="
python3 "$SCRIPT_DIR/patch-scream-mcp-image.py" || echo "⚠️ 跳過"

echo "=== 4/5 scream-timeout patch ==="
python3 "$SCRIPT_DIR/patch-scream-timeout.py" || echo "⚠️ 跳過"

echo "=== 5/5 驗證 ==="
for f in /opt/homebrew/lib/node_modules/scream-code/dist/app-*.mjs; do
    node --check "$f" && echo "✅ $f 語法正確"
done
node --check /opt/homebrew/lib/node_modules/scream-code/node_modules/@liutod-scream/pi-tui/dist/index.mjs \
    && echo "✅ pi-tui 語法正確"

echo ""
echo "=== 完成 ==="
echo "啟動 scream 後測試："
echo "  1. 貼圖 → 確認不走 404，模型切到 google/gemini-2.5-flash"
echo "  2. MCP 備用路線: /tmp/scream-image-* 檔案存在，agent 可用 peekaboo analyze"
echo "  3. 長輸出 → 確認畫面不跳頂"
echo "  4. tool timeout → 60s→120s，減少 Connect timeout"