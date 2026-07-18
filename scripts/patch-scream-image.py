#!/usr/bin/env python3
"""aris-image 圖片輸入補丁（npm update 後需要重跑）。

問題：拖圖進 Scream 對話窗 → 直接跳「The current model does not support image
input」。scream-code 的 gate 是 `!this.capabilities.image_in`，而 laap-core 這種
自訂 OpenAI-compatible provider 的 getCapability() 無條件回 UNKNOWN_CAPABILITY
（image_in: false）→ 圖根本沒送到 Aris。

修法：只讓 laap-core 的 getCapability 回 OPENAI_VISION_TOOL_CAPABILITY
（image_in: true, tool_use: true — bundle 內建 const），其餘 model 不動。這樣 Scream
會放行拖曳的圖，以 image_url content part 送進 Aris 的 /v1/chat/completions。
（Aris 端把含圖那輪路由到 vision 模型是 Part B，另一支 patch/neuralis 改。）

慣例同 patch-scream-aris-stream.py v2：glob dist 檔名、精確錨點、獨立備份
（.aris-image-bak）、node --check 失敗自動還原。
"""
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
MARK = "aris-image v1"

# OpenAI-compatible provider 的能力解析（byte-exact，含 tab）。scream 改版錨不到就 loud fail。
OLD = "getCapability(_model) {\n\t\treturn UNKNOWN_CAPABILITY;\n\t}"

NEW = (
    "getCapability(_model) {\n"
    "\t\t/* aris-image v1 */ if (typeof _model === \"string\" && _model.includes(\"laap-core\")) return OPENAI_VISION_TOOL_CAPABILITY;\n"
    "\t\treturn UNKNOWN_CAPABILITY;\n"
    "\t}"
)


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1
    target = targets[0]
    backup = Path(str(target) + ".aris-image-bak")
    content = target.read_text("utf-8")

    if MARK in content:
        print("✅ 已是 aris-image v1 補丁，跳過")
        return 0
    if OLD not in content:
        print("⚠️ 找不到 getCapability→UNKNOWN 錨點 — scream 改版了或補丁形狀變了，人工對齊")
        return 1
    if "OPENAI_VISION_TOOL_CAPABILITY" not in content:
        print("⚠️ bundle 內找不到 OPENAI_VISION_TOOL_CAPABILITY const — 人工對齊")
        return 1

    if not backup.exists():
        shutil.copy2(target, backup)

    target.write_text(content.replace(OLD, NEW, 1), "utf-8")

    check = subprocess.run(["node", "--check", str(target)],
                           capture_output=True, text=True)
    if check.returncode != 0:
        shutil.copy2(backup, target)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1
    print(f"✅ aris-image v1 補丁已套用（{target.name}，語法驗證過）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
