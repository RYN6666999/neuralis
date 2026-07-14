#!/usr/bin/env bash
# reload-aris.sh — 開發用正規重載（載入新碼），不消耗 watchdog 重啟預算。
#
# 錯誤示範：kill -9 然後等 watchdog 救 — 那會吃掉 5 次/h 的 crash 預算，
# 連續開發重載幾次就把煞車撞鎖死（Aris 躺冷卻期 1h，誰連都是 connection refused）。
# 正解：kill 後立刻自己重啟 — watchdog 要連續 3 次探測失敗（~90s）才出手，
# start-laap-api 在那之前就把 API 帶回來了，預算一毛不花。
set -uo pipefail
PORT="${1:-11546}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 清過期的 crashloop 鎖（開發重載撞出來的，不是真故障）
LOCK="$HERE/watchdog-crashloop-$PORT.lock"
if [[ -f "$LOCK" ]]; then
    echo "[reload] 發現 crashloop 鎖，清掉（開發重載造成的假警報）"
    rm -f "$LOCK"
fi

PID="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null)"
if [[ -n "$PID" ]]; then
    echo "[reload] 停舊行程 $PID"
    # shellcheck disable=SC2086
    kill -TERM $PID 2>/dev/null; sleep 2
    lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && kill -KILL $PID 2>/dev/null
    sleep 1
fi

# 立刻重啟（帶 zshrc 環境 — key 在 Keychain）
/bin/zsh -c "source ~/.zshrc 2>/dev/null; exec '$HERE/scripts/start-laap-api.sh' '$PORT'"
