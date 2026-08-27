#!/usr/bin/env bash
# install-aris-loops-launchagent.sh — 安裝 aris_loops 常駐宿主。
#
# 這支腳本刻意分成兩步，預設只做第一步（--check）：
#   --check    只做啟動驗證，不裝、不常駐、不碰資料
#   --install  裝 plist 並 load
#
# 為什麼預設不裝：ConsolidationLoop 會刪 gbrain 的 episodic 頁
# （consolidation.py:143 run_pass → delete / move）。plist 預設把它關掉，
# 但先手動看過一次啟動輸出再常駐，是這次調查得到的教訓。
set -euo pipefail

NEURALIS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${LAAP_VENV:-$NEURALIS/../laapenv}/bin/python3"
LABEL="com.neuralis.aris-loops"
SRC="$NEURALIS/launchagents/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"

MODE="${1:---check}"

if [[ ! -x "$PY" ]]; then
    echo "❌ 找不到 venv python: $PY"
    exit 1
fi
if [[ ! -f "$SRC" ]]; then
    echo "❌ 找不到 plist: $SRC"
    exit 1
fi

echo "▸ 啟動驗證（--check-only，不常駐、不碰資料）"
# 兩個迴圈都關掉：這一步只驗 import 路徑與 startup_all 起不起得來。
# 迴圈本身能不能跑是下一步的事，混在一起驗會分不清是誰的問題。
if NEURALIS_AGENCY=off NEURALIS_CONSOLIDATION=off \
   "$PY" "$NEURALIS/aris_loops.py" --check-only; then
    echo "  ⚠️  預期應該失敗（兩個迴圈都關 = 沒有存在意義），卻通過了"
    echo "     aris_loops.py 的原則 6 檢查可能失效，先別裝。"
    exit 1
else
    rc=$?
    if [[ $rc -ne 1 ]]; then
        echo "  ❌ 預期 exit 1（兩迴圈全關），實際 exit $rc"
        exit 1
    fi
    echo "  ✅ 原則 6 生效：兩個迴圈全關時會拒絕啟動"
fi

echo "▸ 啟動驗證（只開 agency，不碰 gbrain 的刪除路徑）"
NEURALIS_AGENCY=on NEURALIS_CONSOLIDATION=off \
    "$PY" "$NEURALIS/aris_loops.py" --check-only
echo "  ✅ 起得來"

if [[ "$MODE" != "--install" ]]; then
    cat <<EOF

驗證通過，尚未安裝。要常駐請跑：

    $0 --install

裝之前先確認你接受 plist 裡的預設值：
    NEURALIS_AGENCY=on          自主迴圈開
    NEURALIS_CONSOLIDATION=off  固化先關（會刪 gbrain 頁，門檻是 07 月調的）
EOF
    exit 0
fi

echo "▸ 安裝 $DST"
mkdir -p "$HOME/Library/LaunchAgents"
if [[ -f "$DST" ]]; then
    bak="$DST.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$DST" "$bak"
    echo "  既有 plist 已備份 → $bak"
    launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
fi
cp "$SRC" "$DST"
launchctl bootstrap "gui/$UID" "$DST"
echo "  ✅ 已 load"

# 2026-08-24 實測：冷啟動到第一拍心跳約 29s（hermes plugin discovery 佔大宗），
# 不是原本寫的 5s。太早驗會拿到「心跳檔不存在」的假紅燈 —— 那正是這整套
# 東西要避免的事，結果差點寫進自己的安裝腳本。
echo "▸ 等心跳寫出來（冷啟動實測約 30s，最多等 90s）"
hb="${NEURALIS_LOOPS_HEARTBEAT:-$HOME/.neuralis/loops-heartbeat.json}"
for _ in $(seq 1 18); do
    [[ -f "$hb" ]] && break
    sleep 5
done
if [[ ! -f "$hb" ]]; then
    echo "  ❌ 90s 後心跳仍未出現。看 /tmp/com.neuralis.aris-loops.log"
    exit 1
fi
PYTHONPATH="$NEURALIS" "$PY" "$NEURALIS/scripts/check-loops.py" || true

cat <<EOF

裝完了。接下來：

1. 隔 10 分鐘再跑一次，確認 uptime 有在長（不是反覆重啟）：
       PYTHONPATH=$NEURALIS $PY $NEURALIS/scripts/check-loops.py

2. 確認宿主穩了之後，再決定要不要開固化。開之前先看一眼待掃的頁量：
       gbrain list-pages --prefix laap/memory/episodic | wc -l

3. **把 check-loops.py 接進 nightshift**（目前被 disable）。
   不做這步，你依然沒有辦法知道它哪天又死了 —— 那就是 2026-08-19 的重演。
EOF
