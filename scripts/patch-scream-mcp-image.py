#!/usr/bin/env python3
"""scream-mcp-image MCP 圖片備用路線補丁（npm update 後需要重跑）。

問題：scream 貼圖時直接把 image_url content part 送進 LLM API。
如果 LLM 沒有 vision 能力（如 psi-llm），圖就丟了。

修法：patch imagePartForAttachment()，把貼上的圖存到 /tmp/ 再以文字路徑
取代 image_url。這樣 agent 收到訊息時會看到檔案路徑，可以用 peekaboo analyze
（MCP）或 ReadMediaFile 工具讀取圖片，再餵給有 vision 的模型。

這是 neuralis vision 路由的備用方案，適用於任何沒有 vision 的 LLM。

慣例同 patch-scream-image.py：glob dist 檔名、精確錨點、獨立備份、node --check
失敗自動還原。
"""
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
MARK = "scream-mcp-image v1"

# 完整舊函式（byte-exact）
OLD_FN = (
    'function imagePartForAttachment(att) {\n'
    '\tconst base64 = Buffer.from(att.bytes).toString("base64");\n'
    '\treturn {\n'
    '\t\ttype: "image_url",\n'
    '\t\timageUrl: { url: `data:${att.mime};base64,${base64}` }\n'
    '\t};\n'
    '}'
)

# 完整新函式
NEW_FN = (
    'function imagePartForAttachment(att) {\n'
    '\t/* scream-mcp-image v1 */\n'
    '\tconst ext = att.mime === "image/png" ? "png"'
    ' : att.mime === "image/jpeg" ? "jpg"'
    ' : att.mime === "image/gif" ? "gif"'
    ' : att.mime === "image/webp" ? "webp" : "img";\n'
    '\tconst tmp = "/tmp/scream-image-" + String(att.id) + "." + ext;\n'
    '\twriteFileSync(tmp, att.bytes);\n'
    '\treturn { type: "text", text: "（圖片已存至 " + tmp + "，可用 peekaboo analyze 分析）" };\n'
    '}'
)


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1
    target = targets[0]
    backup = Path(str(target) + ".mcp-image-bak")
    content = target.read_text("utf-8")

    if MARK in content:
        print("✅ 已是 scream-mcp-image v1 補丁，跳過")
        return 0
    if OLD_FN not in content:
        print("⚠️ 找不到 imagePartForAttachment 舊函式 — scream 改版了，人工對齊")
        print("   期望錨點開頭:", repr(OLD_FN[:80]))
        return 1

    if not backup.exists():
        shutil.copy2(target, backup)

    target.write_text(content.replace(OLD_FN, NEW_FN, 1), "utf-8")

    check = subprocess.run(["node", "--check", str(target)],
                           capture_output=True, text=True)
    if check.returncode != 0:
        shutil.copy2(backup, target)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1
    print(f"✅ scream-mcp-image v1 補丁已套用（{target.name}，語法驗證過）")
    print("  貼圖 → 存到 /tmp/scream-image-{id}.{ext} → 文字路徑取代 image_url")
    return 0


if __name__ == "__main__":
    sys.exit(main())
