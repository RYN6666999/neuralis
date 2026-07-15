#!/usr/bin/env python3
"""套用/修復 LAAP 工具狀態通道的 Scream TUI 補丁（npm update 後需要重跑）。

v2 — 修掉 v1 的三個雷（2026-07-15 血的教訓，v1 曾把 scream 整個弄到起不來）：
1. `\\$1` 轉義錯 → 塞進非法 JS（SyntaxError，scream 直接掛）。
   現在自動偵測 SPINNER_FRAMES 的 minified 變體（此版是 SPINNER_FRAMES$1）。
2. .mjs (ESM) 沒有 require → 舊補丁 require("fs") 在 try/catch 裡靜默失效。
   現在檔首插入自有 import（__laapReadFS，名字自己取，不怕 minify 遮蔽）。
3. 狀態檔沒有過期護欄 → tool 行程掛掉狀態列永遠卡「running」。
   現在 ts 超過 15s 視為過期不顯示。
另外：dist 檔名帶 hash（app-*.mjs），每版不同 → 改用 glob 自動找。
patch 完跑 node --check 驗語法，失敗自動還原備份。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
IMPORT_LINE = 'import { readFileSync as __laapReadFS } from "node:fs";\n'
ANCHOR = ('function buildStatusLine(streamingPhase, streamingStartTime) {\n'
          '\tif (streamingPhase === "idle") return t("status.idle");')
MARK = "laap-tool-status"


def patch_line(spinner: str) -> str:
    return (
        "\t// LAAP 工具狀態通道（patch-scream-tui.py v2）\n"
        '\ttry { const raw=__laapReadFS("/tmp/laap-tool-status.json","utf8"); '
        "const laap=JSON.parse(raw); "
        'if((laap.status==="start"||laap.status==="running")'
        "&&(Date.now()/1000-laap.ts)<15){"
        "const n=Date.now();"
        f"const f={spinner}[Math.floor(n/SPINNER_TICK_MS)%{spinner}.length];"
        "const g=lerpGradient(n%GRADIENT_CYCLE_MS/GRADIENT_CYCLE_MS);"
        'return chalk.hex(g).bold(f)+" "+laap.icon+" "+laap.description;}}'
        "catch(e){}\n"
    )


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1
    target = targets[0]
    backup = target.with_suffix(".mjs.bak")
    content = target.read_text("utf-8")

    # 偵測本版 SPINNER_FRAMES 的 minified 名（原碼 status line 就在用它）
    m = re.search(r"(SPINNER_FRAMES\$?\w*)\[Math\.floor\(now / SPINNER_TICK_MS\)",
                  content)
    spinner = m.group(1) if m else "SPINNER_FRAMES"
    want = patch_line(spinner)

    # 清掉任何舊補丁（含 v1 壞版本），統一重灌
    cleaned = re.sub(r"\t// LAAP[^\n]*\n\ttry \{[^\n]*laap-tool-status[^\n]*\n",
                     "", content)
    if MARK in cleaned:
        print("⚠️ 殘留無法辨識的舊補丁，人工檢查")
        return 1
    if want in content and IMPORT_LINE in content:
        print("✅ 已是 v2 補丁，跳過")
        return 0

    if ANCHOR not in cleaned:
        print("⚠️ 找不到 buildStatusLine 錨點，scream 改版了 — 人工對齊")
        return 1

    if not backup.exists():   # 只留最原始的備份，不覆蓋
        shutil.copy2(target, backup)

    patched = cleaned.replace(
        ANCHOR,
        "function buildStatusLine(streamingPhase, streamingStartTime) {\n"
        + want + '\tif (streamingPhase === "idle") return t("status.idle");')
    if IMPORT_LINE not in patched:
        lines = patched.split("\n", 1)
        if lines[0].startswith("#!"):
            patched = lines[0] + "\n" + IMPORT_LINE + lines[1]
        else:
            patched = IMPORT_LINE + patched

    target.write_text(patched, "utf-8")

    # 語法驗證 — 壞了就還原，絕不留一個起不來的 scream
    check = subprocess.run(["node", "--check", str(target)],
                           capture_output=True, text=True)
    if check.returncode != 0:
        shutil.copy2(backup, target)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1
    print(f"✅ v2 補丁已套用（{target.name}, spinner={spinner}，語法驗證過）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
