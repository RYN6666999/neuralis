#!/usr/bin/env bash
# install-support-daemons.sh — 三個支援 daemon 的 launchd 自動化。
#
# 之前這三隻靠「啟動協定」手動起（SCREAM-ARIS-ARCHITECTURE.md 六步），實測結果
# 就是全躺著沒人記得起 — 時間軸和任務通道整天是死的。launchd RunAtLoad+KeepAlive
# 一勞永逸：
#   com.neuralis.phase-logger   → 雙源時間軸記錄（scream-phase + aris-channel）
#   com.neuralis.task-executor  → 任務通道執行精靈（type=task → result）
#   com.neuralis.scream-monitor → channel 監聽（tool_execution → 即時狀態檔）
#
# 環境同 watchdog 慣例：zsh -c 'source ~/.zshrc' 帶 PATH/key。
# 重複執行冪等（bootout 舊的再裝新的）。
#
# 用法:
#   scripts/install-support-daemons.sh       # 安裝 + 立即生效
#   scripts/install-support-daemons.sh -u    # 卸載全部
#   python3 scripts/check-daemons.py         # 驗證三隻都活著
set -euo pipefail

AGENTS_DIR="$HOME/Library/LaunchAgents"
NEURALIS="$HOME/Developer/neuralis"
mkdir -p "$AGENTS_DIR"

# label|指令 清單（指令在 zsh -c 內執行）
DAEMONS=(
  "com.neuralis.phase-logger|exec python3 $HOME/agent-sandbox/scripts/scream-phase-logger.py"
  "com.neuralis.agentos-bridge|cd $NEURALIS && exec python3 scripts/agentos-aris-bridge.py --daemon"
  "com.neuralis.scream-monitor|exec bash $NEURALIS/scripts/scream-monitor.sh"
)

uninstall_one() {
  local label="$1"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$AGENTS_DIR/$label.plist"
}

if [ "${1:-}" = "-u" ]; then
  for entry in "${DAEMONS[@]}"; do
    label="${entry%%|*}"
    uninstall_one "$label"
    echo "[uninstall] $label"
  done
  exit 0
fi

for entry in "${DAEMONS[@]}"; do
  label="${entry%%|*}"
  cmd="${entry#*|}"
  plist="$AGENTS_DIR/$label.plist"
  uninstall_one "$label"   # 冪等：先清舊的

  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-c</string>
    <string>source ~/.zshrc 2>/dev/null; $cmd</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>/tmp/$label.log</string>
  <key>StandardErrorPath</key><string>/tmp/$label.log</string>
</dict>
</plist>
PLIST

  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "[install] $label → $plist"
done

echo "[done] 驗證: python3 $NEURALIS/scripts/check-daemons.py"
