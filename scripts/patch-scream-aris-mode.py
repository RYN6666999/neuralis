#!/usr/bin/env python3
"""patch-scream-aris-mode.py: 在 scream-code 0.10.0 重建 /aris-mode 切換 + 直通串流。

npm update 後 patch 會被覆寫，需要重跑本腳本。
"""
import re, sys, os

DIST_DIR = "/opt/homebrew/lib/node_modules/scream-code/dist"
app_files = [f for f in os.listdir(DIST_DIR) if f.startswith("app-") and f.endswith(".mjs") and not f.endswith(".bak")]
if not app_files:
    print("❌ 找不到 app-*.mjs")
    sys.exit(1)

target = os.path.join(DIST_DIR, app_files[0])
print(f"📄 目標: {target}")

with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# === Patch 1: dispatchInput — 加入 aris-mode 路由 ===
old_dispatch = """function dispatchInput(host, text) {
\tif (parseSlashInput(text) !== null) {
\t\texecuteSlashCommand(host, text);
\t\treturn;
\t}
\thost.sendNormalUserInput(text);
}"""

new_dispatch = """function dispatchInput(host, text) {
\t// aris v1: scream 0.10.0 移除原生 aris-mode，這裡在單一路由點重建（切換 + 直通串流）
\tif (text.trim() === "/aris-mode") {
\t\tif (!host.state.appState.arisMode) {
\t\t\thost.setAppState({ arisMode: true, _prevArisModel: host.state.appState.model });
\t\t\tperformModelSwitch(host, "laap/laap-core", host.state.appState.thinkingLevel);
\t\t} else {
\t\t\tconst prev = host.state.appState._prevArisModel || "";
\t\t\thost.setAppState({ arisMode: false });
\t\t\tif (prev) performModelSwitch(host, prev, host.state.appState.thinkingLevel);
\t\t}
\t\thost.state.ui.requestRender();
\t\treturn;
\t}
\tif (host.state.appState.arisMode && parseSlashInput(text) === null) {
\t\tconst arisScript = (process.env.HOME || "") + "/Developer/neuralis/scripts/aris-chat.py";
\t\tconst child = spawn("python3", ["-u", arisScript, "--once", text], { timeout: 120000 });
\t\tlet arisFull = "", arisErr = "", started = false, done = false;
\t\thost.setAppState({ streamingPhase: "streaming" });
\t\tconst finishAris = (failMsg) => {
\t\t\tif (done) return;
\t\t\tdone = true;
\t\t\tif (started) {
\t\t\t\thost.streamingUI.onStreamingTextUpdate(arisFull.trim() || "(empty response)");
\t\t\t\thost.streamingUI.onStreamingTextEnd();
\t\t\t} else if (failMsg !== void 0) host.showError(failMsg);
\t\t\thost.setAppState({ streamingPhase: "idle" });
\t\t\thost.state.ui.requestRender();
\t\t};
\t\tchild.stdout.setEncoding("utf8");
\t\tchild.stdout.on("data", (chunk) => {
\t\t\tif (!started) { started = true; host.streamingUI.onStreamingTextStart(); }
\t\t\tarisFull += chunk;
\t\t\thost.streamingUI.onStreamingTextUpdate(arisFull);
\t\t});
\t\tchild.stderr.setEncoding("utf8");
\t\tchild.stderr.on("data", (chunk) => { arisErr += chunk; });
\t\tchild.on("error", (e) => finishAris("Aris error: " + e.message));
\t\tchild.on("close", (code) => finishAris(code === 0 || started ? void 0 : (arisErr.trim() || "Aris exited " + code)));
\t\treturn;
\t}
\tif (parseSlashInput(text) !== null) {
\t\texecuteSlashCommand(host, text);
\t\treturn;
\t}
\thost.sendNormalUserInput(text);
}"""

if old_dispatch in content:
    content = content.replace(old_dispatch, new_dispatch)
    print("✅ Patch 1: dispatchInput — aris-mode 路由已加入")
else:
    print("⚠️  Patch 1: dispatchInput 找不到原始碼，可能已 patch 過")
    # 檢查是否已存在
    if "aris-mode" in content:
        print("   → aris-mode 已存在，跳過")

# === Patch 2: appState 初始值 — 加入 arisMode ===
old_state = """\t\tsubagentUsage: {}
\t};
}"""
new_state = """\t\tarisMode: true,
\t\t_prevArisModel: "",
\t\tsubagentUsage: {}
\t};
}"""

if old_state in content:
    content = content.replace(old_state, new_state)
    print("✅ Patch 2: appState 初始值 — arisMode: false 已加入")
else:
    print("⚠️  Patch 2: appState 初始值找不到，檢查中...")
    if "arisMode" in content:
        print("   → arisMode 已存在，跳過")

# === 寫回 ===
with open(target, "w", encoding="utf-8") as f:
    f.write(content)

# === 驗證語法 ===
import subprocess
r = subprocess.run(["node", "--check", target], capture_output=True, text=True)
if r.returncode == 0:
    print(f"✅ 語法驗證通過")
    print(f"✅ 完成！預設 Aris 直通模式 — 啟動 scream 即直連 Aris")
else:
    print(f"❌ 語法錯誤：{r.stderr}")
    sys.exit(1)