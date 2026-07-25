#!/usr/bin/env bash
# aris-iterm — 用 iTerm2 開新視窗直連 Aris REPL
osascript -e '
tell application "iTerm2"
    activate
    tell current window
        create tab with default profile
        tell current session
            write text "cd ~/Developer/neuralis && python3 scripts/aris-chat.py"
        end tell
    end tell
end tell
' 2>/dev/null || {
  # fallback: 如果 iTerm2 沒開，開它
  open -a iTerm2
  sleep 2
  osascript -e '
  tell application "iTerm2"
      activate
      tell current window
          create tab with default profile
          tell current session
              write text "cd ~/Developer/neuralis && python3 scripts/aris-chat.py"
          end tell
      end tell
  end tell
  '
}