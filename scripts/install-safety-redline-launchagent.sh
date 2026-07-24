#!/usr/bin/env bash
# install-safety-redline-launchagent.sh
# Install/uninstall launchd job for soak-phase safety redline alerts.

set -euo pipefail

LABEL="com.neuralis.safety-redline"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_FILE="$HERE/safety-redline.log"
STATUS_FILE="${SAFETY_REDLINE_STATUS_PATH:-/tmp/neuralis-safety-redlines-status.json}"

if [[ "${1:-}" == "-u" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "[launchagent] removed $LABEL"
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
    <string>source ~/.zshrc 2>/dev/null; export SAFETY_REDLINE_STATUS_PATH="$STATUS_FILE"; exec python3 "$HERE/scripts/safety-redline-alerts.py" &gt;&gt; "$LOG_FILE" 2&gt;&amp;1</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>$LOG_FILE</string>
  <key>StandardErrPath</key><string>$LOG_FILE</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 1

if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  echo "[launchagent] installed $LABEL"
  echo "[launchagent] log: $LOG_FILE"
  echo "[launchagent] status file: $STATUS_FILE"
else
  echo "[launchagent] failed to install $LABEL"
  exit 1
fi
