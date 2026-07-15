#!/usr/bin/env python3
"""重新套用 LAAP 工具狀態通道的 Scream TUI 補丁（npm update 後需要重跑）。"""
import re, sys
from pathlib import Path

SCREAM_DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
TARGET = SCREAM_DIST / "app-0DJZPbGz.mjs"
BACKUP = SCREAM_DIST / "app-0DJZPbGz.mjs.bak"

if not TARGET.exists():
    print(f"❌ 找不到 {TARGET}")
    sys.exit(1)

content = TARGET.read_text("utf-8")

# 如果已經 patch 過了就跳過
if "laap-tool-status" in content:
    print("✅ 已 patch 過，跳過")
    sys.exit(0)

old = '''function buildStatusLine(streamingPhase, streamingStartTime) {
\tif (streamingPhase === "idle") return t("status.idle");'''

new = '''function buildStatusLine(streamingPhase, streamingStartTime) {
\t// LAAP \\u5de5\\u5177\\u72b6\\u6001\\u901a\\u9053
\ttry { const fs2=require("fs"); const raw=fs2.readFileSync("/tmp/laap-tool-status.json","utf8"); const laap=JSON.parse(raw); if(laap.status==="start"||laap.status==="running"){const n=Date.now();const f=SPINNER_FRAMES\\$1[Math.floor(n/SPINNER_TICK_MS)%SPINNER_FRAMES\\$1.length];const g=lerpGradient(n%GRADIENT_CYCLE_MS/GRADIENT_CYCLE_MS);return chalk.hex(g).bold(f)+" "+laap.icon+" "+laap.description;}}catch(e){}
\tif (streamingPhase === "idle") return t("status.idle");'''

if old not in content:
    print("⚠️ 找不到目標文字，buildStatusLine 可能已變更")
    sys.exit(1)

# 備份
TARGET.rename(BACKUP)
content = content.replace(old, new)
TARGET.write_text(content, "utf-8")
print(f"✅ patch 已套用（備份: {BACKUP.name}）")