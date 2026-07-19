#!/usr/bin/env python3
"""scream-tui 畫面跳頂補丁（npm update 後需要重跑）。

問題：模型輸出長內容時，pi-tui 的 doRender 偵測到 firstChanged < prevViewportTop
（串流更新導致元件從頭 re-render），觸發 fullRender(true) → 送出 \x1B[2J\x1B[H
（清螢幕 + 游標歸位）→ 終端機捲到最上面。

修法：把 fullRender(true) 改成不送 \x1B[2J\x1B[H，改為調整 viewport 位置後
以非清除方式重繪。這樣畫面不會跳頂，串流內容正常追加在底部。

慣例同 patch-scream-image.py：glob dist 檔名、精確錨點、獨立備份、node --check
失敗自動還原。
"""
import shutil
import subprocess
import sys
from pathlib import Path

PI_TUI = Path("/opt/homebrew/lib/node_modules/scream-code/node_modules/@liutod-scream/pi-tui/dist/index.mjs")
MARK = "scream-tui v1"

# 精確錨點：firstChanged < prevViewportTop → fullRender(true)
OLD = (
    '\t\tif (firstChanged < prevViewportTop) {\n'
    '\t\t\tlogRedraw(`firstChanged < viewportTop (${firstChanged} < ${prevViewportTop})`);\n'
    '\t\t\tfullRender(true);\n'
    '\t\t\treturn;\n'
    '\t\t}'
)

# 改為不送 \x1B[2J\x1B[H，只調整 viewport 後非清除重繪
NEW = (
    '\t\tif (firstChanged < prevViewportTop) {\n'
    '\t\t\tlogRedraw(`firstChanged < viewportTop (${firstChanged} < ${prevViewportTop})`);\n'
    '\t\t\t/* scream-tui v1: 不送 \\x1B[2J\\x1B[H（清螢幕+游標歸位=跳頂），'
    '只調整 viewport */\n'
    '\t\t\tprevViewportTop = Math.max(0, firstChanged);\n'
    '\t\t\tfullRender(false);\n'
    '\t\t\treturn;\n'
    '\t\t}'
)


def main() -> int:
    if not PI_TUI.exists():
        print(f"❌ {PI_TUI} 不存在")
        return 1

    backup = Path(str(PI_TUI) + ".scream-tui-bak")
    content = PI_TUI.read_text("utf-8")

    if MARK in content:
        print("✅ 已是 scream-tui v1 補丁，跳過")
        return 0
    if OLD not in content:
        print("⚠️ 找不到 firstChanged < prevViewportTop 錨點 — pi-tui 改版了，人工對齊")
        return 1

    if not backup.exists():
        shutil.copy2(PI_TUI, backup)

    PI_TUI.write_text(content.replace(OLD, NEW, 1), "utf-8")

    check = subprocess.run(["node", "--check", str(PI_TUI)],
                           capture_output=True, text=True)
    if check.returncode != 0:
        shutil.copy2(backup, PI_TUI)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1
    print(f"✅ scream-tui v1 補丁已套用（{PI_TUI.name}，語法驗證過）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
