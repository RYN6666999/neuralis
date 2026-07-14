#!/usr/bin/env bash
# 背景啟動 LAAP Brain API（scream-code 的 MCP proxy 依賴它跑在 :11546）。
# 冪等：已經在跑就不重複起。用法： ./scripts/start-laap-api.sh [PORT]
# 內部委派 start.sh（PsiCore 心跳 + API 同 process），背景 + log + health check。
set -euo pipefail
PORT="${1:-11546}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # neuralis 根

if curl -s -m2 "http://localhost:$PORT/health" >/dev/null 2>&1; then
  echo "[laap] 已在 :$PORT 運作中"; exit 0
fi
echo "[laap] 背景啟動（PsiCore 心跳 + API）on :$PORT"
nohup "$HERE/scripts/start.sh" "$PORT" > "$HERE/laap-api.log" 2>&1 &
echo "[laap] pid $! → log: $HERE/laap-api.log"
for _ in $(seq 1 20); do
  sleep 1
  if curl -s -m2 "http://localhost:$PORT/health" >/dev/null 2>&1; then
    curl -s -m3 "http://localhost:$PORT/health"; echo " ← LAAP ready"; exit 0
  fi
done
echo "[laap] 未就緒，看 log"; exit 1
