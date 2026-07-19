#!/usr/bin/env python3
"""aris-mode 整合補丁（scream 0.10.0+，取代舊版 aris-agent + aris-stream）。

背景：scream 0.10.0 **整塊移除**了原生 aris-mode（`arisMode` 在 bundle 出現 0 次）。
舊 patch-scream-aris-agent/aris-stream 的錨點（散在 3+ 處）全失效。0.10.0 把使用者
輸入收斂到單一 choke point `dispatchInput(host, text)`，所以整合重建成兩個注入點：

1. `createInitialAppState` 回傳加 `arisMode` / `_prevArisModel` 狀態欄位。
2. `dispatchInput` 重寫：`/aris-mode` 切換模型到 laap/laap-core（記/還原前一模型）；
   arisMode 開時把非 slash 輸入 spawn `aris-chat.py --once` 直通 Aris，逐塊 stdout
   走 `host.streamingUI.onStreamingTextStart/Update/End` 串流（0.10.0 仍有這些 method）。
   否則沿用原 slash 分派 / sendNormalUserInput。

慣例同其他 patch：glob dist、精確錨點、獨立備份（.aris-bak）、node --check 失敗自還原。
npm update 後需重跑；`check-scream-patches.py` 驗是否全套上。
"""
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
MARK = "aris v1"

# ── 注入 1：state 欄位 ──
OLD_STATE = 'return {\n\t\tmodel: "",\n\t\tworkDir: input.workDir,'
NEW_STATE = ('return {\n\t\t/* aris v1 */ arisMode: false,\n\t\t_prevArisModel: "",\n'
             '\t\tmodel: "",\n\t\tworkDir: input.workDir,')

# ── 注入 2：dispatchInput（整個函式體，byte-exact）──
OLD_DISPATCH = (
    "function dispatchInput(host, text) {\n"
    "\tif (parseSlashInput(text) !== null) {\n"
    "\t\texecuteSlashCommand(host, text);\n"
    "\t\treturn;\n"
    "\t}\n"
    "\thost.sendNormalUserInput(text);\n"
    "}"
)
NEW_DISPATCH = (
    "function dispatchInput(host, text) {\n"
    "\t// aris v1: scream 0.10.0 移除原生 aris-mode，這裡在單一路由點重建（切換 + 直通串流）\n"
    '\tif (text.trim() === "/aris-mode") {\n'
    "\t\tif (!host.state.appState.arisMode) {\n"
    "\t\t\thost.setAppState({ arisMode: true, _prevArisModel: host.state.appState.model });\n"
    '\t\t\tperformModelSwitch(host, "laap/laap-core", host.state.appState.thinkingLevel);\n'
    "\t\t} else {\n"
    '\t\t\tconst prev = host.state.appState._prevArisModel || "";\n'
    "\t\t\thost.setAppState({ arisMode: false });\n"
    "\t\t\tif (prev) performModelSwitch(host, prev, host.state.appState.thinkingLevel);\n"
    "\t\t}\n"
    "\t\thost.state.ui.requestRender();\n"
    "\t\treturn;\n"
    "\t}\n"
    "\tif (host.state.appState.arisMode && parseSlashInput(text) === null) {\n"
    '\t\tconst arisScript = (process.env.HOME || "") + "/Developer/neuralis/scripts/aris-chat.py";\n'
    '\t\tconst child = spawn("python3", ["-u", arisScript, "--once", text], { timeout: 120000 });\n'
    '\t\tlet arisFull = "", arisErr = "", started = false, done = false;\n'
    '\t\thost.setAppState({ streamingPhase: "streaming" });\n'
    "\t\tconst finishAris = (failMsg) => {\n"
    "\t\t\tif (done) return;\n"
    "\t\t\tdone = true;\n"
    "\t\t\tif (started) {\n"
    '\t\t\t\thost.streamingUI.onStreamingTextUpdate(arisFull.trim() || "(empty response)");\n'
    "\t\t\t\thost.streamingUI.onStreamingTextEnd();\n"
    "\t\t\t} else if (failMsg !== void 0) host.showError(failMsg);\n"
    '\t\t\thost.setAppState({ streamingPhase: "idle" });\n'
    "\t\t\thost.state.ui.requestRender();\n"
    "\t\t};\n"
    '\t\tchild.stdout.setEncoding("utf8");\n'
    '\t\tchild.stdout.on("data", (chunk) => {\n'
    "\t\t\tif (!started) { started = true; host.streamingUI.onStreamingTextStart(); }\n"
    "\t\t\tarisFull += chunk;\n"
    "\t\t\thost.streamingUI.onStreamingTextUpdate(arisFull);\n"
    "\t\t});\n"
    '\t\tchild.stderr.setEncoding("utf8");\n'
    '\t\tchild.stderr.on("data", (chunk) => { arisErr += chunk; });\n'
    '\t\tchild.on("error", (e) => finishAris("Aris error: " + e.message));\n'
    '\t\tchild.on("close", (code) => finishAris(code === 0 || started ? void 0 : (arisErr.trim() || "Aris exited " + code)));\n'
    "\t\treturn;\n"
    "\t}\n"
    "\tif (parseSlashInput(text) !== null) {\n"
    "\t\texecuteSlashCommand(host, text);\n"
    "\t\treturn;\n"
    "\t}\n"
    "\thost.sendNormalUserInput(text);\n"
    "}"
)


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1
    target = targets[0]
    backup = Path(str(target) + ".aris-bak")
    content = target.read_text("utf-8")

    if MARK in content:
        print("✅ 已是 aris v1 補丁，跳過")
        return 0
    for label, old in (("state", OLD_STATE), ("dispatchInput", OLD_DISPATCH)):
        if old not in content:
            print(f"⚠️ 找不到 {label} 錨點 — scream 又改版了或補丁形狀變了，人工對齊")
            return 1

    if not backup.exists():
        shutil.copy2(target, backup)

    patched = content.replace(OLD_STATE, NEW_STATE, 1).replace(OLD_DISPATCH, NEW_DISPATCH, 1)
    target.write_text(patched, "utf-8")

    check = subprocess.run(["node", "--check", str(target)],
                           capture_output=True, text=True)
    if check.returncode != 0:
        shutil.copy2(backup, target)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1
    print(f"✅ aris v1 補丁已套用（{target.name}，語法驗證過）")
    print("   /aris-mode 切換 + 直通 Aris 串流。重啟 Scream 生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
