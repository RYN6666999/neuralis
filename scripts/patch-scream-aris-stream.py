#!/usr/bin/env python3
"""aris-mode 流式輸出補丁（npm update 後需要重跑）。

問題：/aris-mode 直通用 exec() 呼叫 aris-chat.py --once — exec 把 stdout
整包緩衝到行程結束才回 callback，Aris 回應永遠一次性蹦出來，沒有流式。
（aris-chat.py 本身 v2 起就會逐 token 輸出，卡的只有 scream 這端。）

修法：exec → spawn，stdout 逐塊進 host.streamingUI 的
onStreamingTextStart / Update / End 三件套（scream 原生 LLM 流式用的
同一套 live transcript 機制）。順手修掉 exec 版的 shell injection
（JSON.stringify 進 shell，訊息含 $() 會被執行）— spawn argv 無 shell。

慣例同 patch-scream-tui.py v2：glob dist 檔名、精確錨點、獨立備份
（.aris-stream-bak，不動 tui 補丁的 .bak）、node --check 失敗自動還原。
"""
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
MARK = "aris-stream v2"

# 原 exec 版整塊（byte-exact，含 tab 縮排）。scream 改版錨不到就loud fail。
OLD = (
    '\t\t\tconst cmd = "python3 ~/Developer/neuralis/scripts/aris-chat.py --once " + JSON.stringify(text);\n'
    "\t\t\texec(cmd, { timeout: 120000 }, (error, stdout, stderr) => {\n"
    "\t\t\t\tif (error && (!stdout || stdout.trim().length === 0)) {\n"
    '\t\t\t\t\tspinner.stop({ ok: false, label: "Aris error" });\n'
    "\t\t\t\t\thost.failSessionRequest(stdout ? stdout.trim() : (stderr || error.message).trim());\n"
    "\t\t\t\t\treturn;\n"
    "\t\t\t\t}\n"
    '\t\t\t\tconst content = (stdout || "").trim() || "(empty response)";\n'
    '\t\t\t\tspinner.stop({ ok: true, label: "Aris" });\n'
    "\t\t\t\thost.appendTranscriptEntry({\n"
    "\t\t\t\t\tid: nextTranscriptId(),\n"
    '\t\t\t\t\tkind: "assistant",\n'
    "\t\t\t\t\tturnId: void 0,\n"
    '\t\t\t\t\trenderMode: "markdown",\n'
    "\t\t\t\t\tcontent\n"
    "\t\t\t\t});\n"
    '\t\t\t\thost.setAppState({ streamingPhase: "idle" });\n'
    "\t\t\t\thost.state.ui.requestRender();\n"
    "\t\t\t});\n"
    "\t\t\treturn;\n"
)

NEW = (
    "\t\t\t// aris-stream v2: spawn + 逐塊 stdout → streamingUI 直播（exec 整包緩衝，永遠不流式）\n"
    '\t\t\tconst arisScript = (process.env.HOME || "") + "/Developer/neuralis/scripts/aris-chat.py";\n'
    '\t\t\tconst child = spawn("python3", ["-u", arisScript, "--once", text], { timeout: 120000 });\n'
    '\t\t\tlet arisFull = "";\n'
    '\t\t\tlet arisErr = "";\n'
    "\t\t\tlet arisStarted = false;\n"
    "\t\t\tlet arisDone = false;\n"
    "\t\t\tconst finishAris = (failMsg) => {\n"
    "\t\t\t\tif (arisDone) return;\n"
    "\t\t\t\tarisDone = true;\n"
    "\t\t\t\tif (!arisStarted) {\n"
    '\t\t\t\t\tspinner.stop(failMsg !== void 0 ? { ok: false, label: "Aris error" } : { ok: true, label: "Aris" });\n'
    "\t\t\t\t\tif (failMsg !== void 0) {\n"
    "\t\t\t\t\t\thost.failSessionRequest(failMsg);\n"
    "\t\t\t\t\t\treturn;\n"
    "\t\t\t\t\t}\n"
    "\t\t\t\t} else {\n"
    '\t\t\t\t\thost.streamingUI.onStreamingTextUpdate(arisFull.trim() || "(empty response)");\n'
    "\t\t\t\t\thost.streamingUI.onStreamingTextEnd();\n"
    "\t\t\t\t\tif (failMsg !== void 0) host.showError(failMsg);\n"
    "\t\t\t\t}\n"
    '\t\t\t\thost.setAppState({ streamingPhase: "idle" });\n'
    "\t\t\t\thost.state.ui.requestRender();\n"
    "\t\t\t};\n"
    '\t\t\tchild.stdout.setEncoding("utf8");\n'
    '\t\t\tchild.stdout.on("data", (chunk) => {\n'
    "\t\t\t\tif (!arisStarted) {\n"
    "\t\t\t\t\tarisStarted = true;\n"
    '\t\t\t\t\tspinner.stop({ ok: true, label: "Aris" });\n'
    "\t\t\t\t\thost.streamingUI.onStreamingTextStart();\n"
    "\t\t\t\t}\n"
    "\t\t\t\tarisFull += chunk;\n"
    "\t\t\t\thost.streamingUI.onStreamingTextUpdate(arisFull);\n"
    "\t\t\t});\n"
    '\t\t\tchild.stderr.setEncoding("utf8");\n'
    '\t\t\tchild.stderr.on("data", (chunk) => {\n'
    "\t\t\t\tarisErr += chunk;\n"
    "\t\t\t});\n"
    '\t\t\tchild.on("error", (error) => finishAris("Aris error: " + error.message));\n'
    '\t\t\tchild.on("close", (code) => finishAris(code === 0 || arisStarted ? void 0 : (arisErr.trim() || "Aris exited " + code)));\n'
    "\t\t\treturn;\n"
)


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1
    target = targets[0]
    backup = Path(str(target) + ".aris-stream-bak")
    content = target.read_text("utf-8")

    if MARK in content:
        print("✅ 已是 aris-stream v2 補丁，跳過")
        return 0
    if OLD not in content:
        print("⚠️ 找不到 exec 版 aris-mode 錨點 — scream 改版了或補丁形狀變了，人工對齊")
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
    print(f"✅ aris-stream v2 補丁已套用（{target.name}，語法驗證過）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
