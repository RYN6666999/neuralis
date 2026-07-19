#!/usr/bin/env bash
# watchdog.sh — 韌性層：health 探測 + 自動重啟。
#
# 為什麼不是 launchd KeepAlive：KeepAlive 只在「行程退出」時重啟。Aris 觀察到的
# 崩法包含「行程還活著但不回應」（event loop 阻塞 / 假死 / OOM 前的垂死掙扎），
# 那種 launchd 抓不到。health 探測兩種都抓。
#
# 用法:
#   scripts/watchdog.sh [PORT]                 # 前景守著（Ctrl-C 停）
#   nohup scripts/watchdog.sh > watchdog.log 2>&1 &   # 背景
#
# 調參（env）:
#   NEURALIS_WATCHDOG_INTERVAL   探測間隔秒（預設 30）
#   NEURALIS_WATCHDOG_TIMEOUT    單次 health 逾時秒（預設 5）——假死靠這個抓
#   NEURALIS_WATCHDOG_FAILS      連續幾次失敗才重啟（預設 3）
#   NEURALIS_WATCHDOG_MAX_RESTARTS  視窗內最多重啟幾次（預設 5）
#   NEURALIS_WATCHDOG_WINDOW     crash-loop 視窗秒（預設 3600）
#   NEURALIS_WATCHDOG_READY_WAIT 重啟後等就緒秒數（預設 30）
#   NEURALIS_WATCHDOG_MAX_CYCLES 跑幾輪後退出，0=永遠（預設 0，自檢用）
#   NEURALIS_WATCHDOG_START_CMD  重啟指令（預設 scripts/start-laap-api.sh PORT）
#
# 審計: watchdog-audit.jsonl（probe_fail / restart / restart_ok / restart_failed / crashloop）
#
# crash-loop 煞車跨行程持久（launchd 用）：撞上限時寫 watchdog-crashloop-<PORT>.lock，
# 下次啟動若 lock 未過期（< WINDOW 秒）就睡到冷卻結束再試 —— launchd KeepAlive 重啟
# watchdog 不會歸零煞車、也不會刷 log。手動解鎖：rm 該 lock 檔。
set -uo pipefail   # 不用 -e：探測失敗是正常路徑，迴圈必須活下來
export LC_ALL="${LC_ALL:-C}"

PORT="${1:-11546}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUDIT="$HERE/watchdog-audit.jsonl"
CRASHLOOP_LOCK="$HERE/watchdog-crashloop-$PORT.lock"

INTERVAL="${NEURALIS_WATCHDOG_INTERVAL:-30}"
TIMEOUT="${NEURALIS_WATCHDOG_TIMEOUT:-5}"
FAILS="${NEURALIS_WATCHDOG_FAILS:-3}"
MAX_RESTARTS="${NEURALIS_WATCHDOG_MAX_RESTARTS:-5}"
WINDOW="${NEURALIS_WATCHDOG_WINDOW:-3600}"
READY_WAIT="${NEURALIS_WATCHDOG_READY_WAIT:-30}"
MAX_CYCLES="${NEURALIS_WATCHDOG_MAX_CYCLES:-0}"
START_CMD="${NEURALIS_WATCHDOG_START_CMD:-$HERE/scripts/start-laap-api.sh $PORT}"

audit() {  # audit <event> <extra-json-fields>
    printf '{"ts":%s,"iso":"%s","event":"%s","port":%s%s}\n' \
        "$(date +%s)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$PORT" "${2:-}" >> "$AUDIT"
}

probe() { curl -sf -m "$TIMEOUT" "http://localhost:$PORT/health" >/dev/null 2>&1; }

# 殺殘進程：認 port listener，不認 cmdline（start.sh 的 heredoc python 認不出來）。
# 連子進程一起收（gbrain MCP subprocess 會被 reparent 到 init 繼續佔記憶體）。
kill_stale() {
    local pids kids p
    pids="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null)"
    [[ -z "$pids" ]] && { echo "[watchdog] 沒有 listener（行程已死），直接重起"; return 0; }
    kids=""
    for p in $pids; do kids="$kids $(pgrep -P "$p" 2>/dev/null)"; done
    echo "[watchdog] 殺殘進程: $pids $kids"
    # shellcheck disable=SC2086
    kill -TERM $pids $kids 2>/dev/null
    for _ in $(seq 1 10); do
        sleep 1
        lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || return 0
    done
    echo "[watchdog] TERM 沒收乾淨 → KILL"
    # shellcheck disable=SC2086
    kill -KILL $pids $kids 2>/dev/null
    sleep 1
}

restart() {
    audit restart ',"reason":"health_fail"'
    kill_stale
    echo "[watchdog] 重啟: $START_CMD"
    # shellcheck disable=SC2086
    if $START_CMD >/dev/null 2>&1 && probe; then
        echo "[watchdog] ✅ 重啟成功"; audit restart_ok; return 0
    fi
    for _ in $(seq 1 "$READY_WAIT"); do   # 啟動腳本自己有等，這裡是二重保險（慢機器）
        sleep 1
        probe && { echo "[watchdog] ✅ 重啟成功（延遲就緒）"; audit restart_ok; return 0; }
    done
    echo "[watchdog] ❌ 重啟後仍不健康"; audit restart_failed; return 1
}

# 開機先看煞車：上一世 crash-loop 的冷卻期還沒過就睡完它（launchd 重啟不繞過煞車）
if [[ -f "$CRASHLOOP_LOCK" ]]; then
    lock_ts="$(cat "$CRASHLOOP_LOCK" 2>/dev/null || echo 0)"
    remaining=$(( lock_ts + WINDOW - $(date +%s) ))
    if [[ $remaining -gt 0 ]]; then
        echo "[watchdog] 🚨 上次 crash-loop 冷卻中，再等 ${remaining}s（手動解鎖: rm $CRASHLOOP_LOCK）"
        audit cooldown ",\"remaining\":$remaining"
        sleep "$remaining"
    fi
    rm -f "$CRASHLOOP_LOCK"
    echo "[watchdog] 冷卻結束，恢復守望"
fi

echo "[watchdog] 盯 :$PORT — 每 ${INTERVAL}s 探測，連續 ${FAILS} 次失敗即重啟"
audit start ",\"interval\":$INTERVAL,\"fails\":$FAILS"

consecutive=0
restarts=()          # crash-loop 視窗內的重啟時間戳
cycles=0

while :; do
    # ── 熔斷 kill switch ──────────────────────────
    HALT="$HOME/.aris-halt"
    if [[ -f "$HALT" ]]; then
        echo "[watchdog] 🛑  halt 檔存在 → 停 agency/executor + daemon（解除: rm $HALT）"
        audit halt
        kill_stale
        exit 0
    fi

    if probe; then
        [[ $consecutive -gt 0 ]] && echo "[watchdog] 恢復健康（先前連續失敗 $consecutive 次）"
        consecutive=0
    else
        consecutive=$((consecutive + 1))
        echo "[watchdog] health 失敗 ($consecutive/$FAILS)"
        audit probe_fail ",\"consecutive\":$consecutive"

        if [[ $consecutive -ge $FAILS ]]; then
            now="$(date +%s)"
            recent=()
            for t in ${restarts[@]+"${restarts[@]}"}; do
                [[ $((now - t)) -lt $WINDOW ]] && recent+=("$t")
            done
            restarts=(${recent[@]+"${recent[@]}"})

            if [[ ${#restarts[@]} -ge $MAX_RESTARTS ]]; then
                # 重啟解不了 = 更嚴重的問題。繼續重啟只會刷 log 蓋掉真因。
                # lock 檔讓煞車跨行程存活：launchd 重啟 watchdog 會先睡完冷卻期。
                echo "[watchdog] 🚨 crash-loop：${WINDOW}s 內已重啟 ${#restarts[@]} 次，停手。看 laap-api.log"
                date +%s > "$CRASHLOOP_LOCK"
                audit crashloop ",\"restarts\":${#restarts[@]},\"window\":$WINDOW"
                exit 1
            fi
            restarts+=("$now")
            restart
            consecutive=0
        fi
    fi

    cycles=$((cycles + 1))
    [[ $MAX_CYCLES -gt 0 && $cycles -ge $MAX_CYCLES ]] && { echo "[watchdog] 達 MAX_CYCLES=$MAX_CYCLES，退出"; exit 0; }
    sleep "$INTERVAL"
done
