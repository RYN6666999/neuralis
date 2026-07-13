#!/usr/bin/env bash
# 啟動 LAAP Brain API（scream-code 的 MCP proxy 依賴它跑在 :11546）。
# 冪等：已經在跑就不重複起。用法： ./scripts/start-laap-api.sh [PORT]
set -euo pipefail
PORT="${1:-11546}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # neuralis 根
LAAP="${LAAP_AGI_DIR:-$(cd "$HERE/../laap-AGI" && pwd)}"  # 預設 neuralis 旁邊的 laap-AGI
VENV="${LAAP_VENV:-$HERE/../laapenv}"             # 預設旁邊的 laapenv

if curl -s -m2 "http://localhost:$PORT/health" >/dev/null 2>&1; then
  echo "[laap] 已在 :$PORT 運作中"; exit 0
fi
export PYTHONPATH="$HERE:$LAAP"                    # neuralis overlay 疊在 laap-AGI 之上
echo "[laap] 啟動 API on :$PORT (PYTHONPATH=$PYTHONPATH)"
nohup "$VENV/bin/python" "$LAAP/aris_brain/laap_brain_api.py" --port "$PORT" \
  > "$HERE/laap-api.log" 2>&1 &
echo "[laap] pid $! → log: $HERE/laap-api.log"
sleep 6
curl -s -m3 "http://localhost:$PORT/health" && echo " ← LAAP ready" || { echo "[laap] 未就緒，看 log"; exit 1; }
