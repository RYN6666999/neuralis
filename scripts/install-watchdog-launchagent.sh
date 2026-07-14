#!/usr/bin/env bash
# install-watchdog-launchagent.sh — 7/24 自啟動的最後一塊：launchd 守 watchdog。
#
# 守護鏈：launchd（開機自啟 + watchdog 死了拉起來）
#         → watchdog.sh（API 崩/假死 → 殺殘進程 + 重啟）
#         → start-laap-api.sh → start.sh（完整 Aris：心跳+42工具+agency+固化）
#
# 環境：plist 用 `zsh -c 'source ~/.zshrc'` 帶入 OPENAI_API_KEY + PATH（gbrain 在
# ~/.bun/bin）。launchd 原生環境沒這些，漏了的話重啟出來的 Aris 會退化 lex-only。
#
# 煞車不衝突：watchdog crash-loop 停手時落地 lock 檔；launchd KeepAlive 把 watchdog
# 拉起來後，它會先睡完冷卻期（WINDOW 秒）才恢復 —— 不會無限重啟刷 log。
#
# 用法:
#   scripts/install-watchdog-launchagent.sh          # 安裝 + 立即生效
#   scripts/install-watchdog-launchagent.sh -u       # 卸載
#   launchctl print gui/$UID/com.neuralis.watchdog   # 看狀態
set -euo pipefail

LABEL="com.neuralis.watchdog"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ "${1:-}" == "-u" ]]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "[launchagent] 已卸載 $LABEL"
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-c</string>
        <string>source ~/.zshrc 2>/dev/null; exec "$HERE/scripts/watchdog.sh"</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ThrottleInterval</key><integer>30</integer>
    <key>StandardOutPath</key><string>$HERE/watchdog.log</string>
    <key>StandardErrPath</key><string>$HERE/watchdog.log</string>
</dict>
</plist>
EOF

# 冪等：舊的先收掉再裝
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 1
if launchctl print "gui/$(id -u)/$LABEL" | grep -q "state = running"; then
    echo "[launchagent] ✅ $LABEL 已安裝並運行 — 開機自啟 + watchdog 永生"
    echo "[launchagent] log: $HERE/watchdog.log | 卸載: $0 -u"
else
    echo "[launchagent] ⚠️ 已 bootstrap 但未見 running，查: launchctl print gui/$(id -u)/$LABEL"
    exit 1
fi
