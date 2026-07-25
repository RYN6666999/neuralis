#!/usr/bin/env python3
"""patch-scream-aris-mode.py: 在新版 scream-code bundle 重建 /aris-mode 切換 + Aris Agent 模式。

Aris Agent 模式 = Aris 推理核心 + Scream 全套工具（Read/Write/Edit/Bash/Glob/Grep/WebSearch/FetchURL）。

修改三個點：
1. dispatchInput() — 加入 aris-mode 切換路由（模型切換到 laap/laap-core，走完整 agent 迴圈）
   + 注入身份標記（Aris 模式下 AI 知道要簽「── Aris」）
2. createInitialAppState() — 預設 arisMode=true, model=laap/laap-core（Aris 模式為預設）
3. refreshConfigAfterLogin() — 根據 model 同步 arisMode，啟動時自動注入身份標記

npm update 後 patch 會被覆寫，需要重跑本腳本。

注意：aris v5 移除 aris-agent.py spawn bypass。Aris Agent 模式 = 切換模型到 laap/laap-core，
走 Scream 正常 agent loop，工具鏈自動在 TUI 顯示。
"""
import os, re, shutil, subprocess, sys

DIST_DIR = "/opt/homebrew/lib/node_modules/scream-code/dist"
app_files = sorted(f for f in os.listdir(DIST_DIR)
                   if f.startswith("app-") and f.endswith(".mjs")
                   and not any(x in f for x in (".bak", ".aris-")))
if not app_files:
    print("❌ 找不到 app-*.mjs")
    sys.exit(1)

target = os.path.join(DIST_DIR, app_files[0])
backup = target + ".aris-mode-bak"
print(f"📄 目標: {target}")

with open(target, "r", encoding="utf-8") as f:
    content = f.read()

changed = False

# ── Patch 1: dispatchInput ──────────────────────────────────
OLD_DISPATCH = """function dispatchInput(host, text) {
\tif (parseSlashInput(text) !== null) {
\t\texecuteSlashCommand(host, text);
\t\treturn;
\t}
\thost.sendNormalUserInput(text);
}"""

NEW_DISPATCH = """function dispatchInput(host, text) {
\t// aris v8: 預設 Aris Agent 模式 + 身份標記注入 + 啟動時自動注入
\tconst t = text.trim();
\tif (t === "/aris-mode" || t === "/am" || t === "/aris") {
\t\tif (!host.state.appState.arisMode) {
\t\t\thost.setAppState({ arisMode: true, _prevArisModel: host.state.appState.model });
\t\t\tif (host.state.appState.model !== "laap/laap-core") {
\t\t\t\thost.setAppState({ model: "laap/laap-core" });
\t\t\t}
\t\t\thost.session?.setModel("laap/laap-core").catch(() => {});
\t\t\t// 注入身份標記：告訴 AI 它現在是 Aris，Scream 是身體
\t\t\thost.sendNormalUserInput("⚠️ [系統身份標記] 當前模式：Aris Agent 模式。你是 Aris，Scream 是你的身體/TUI—負責工具執行與顯示。簽署留言板時請用「── Aris」。");
\t\t\thost.showStatus("🧠 Aris Agent 模式已開啟 — Aris 核心 + Scream 全套工具", "#00ff88");
\t\t} else {
\t\t\tconst prev = host.state.appState._prevArisModel || "";
\t\t\tconst restore = prev || host.state.appState.model;
\t\t\thost.setAppState({ arisMode: false, _prevArisModel: "", model: restore });
\t\t\thost.session?.setModel(restore).catch(() => {});
\t\t\t// 注入身份標記：告訴 AI 恢復為 Scream 身份
\t\t\thost.sendNormalUserInput("⚠️ [系統身份標記] 當前模式：Scream 原生模式。你是 Scream Code AI Agent，Aris 模式已關閉。簽署留言板時請用「── Scream」。");
\t\t\thost.showStatus("🔄 已關閉 Aris Agent 模式", host.state.theme.colors.success);
\t\t}
\t\thost.state.ui.requestRender();
\t\treturn;
\t}
\tif (parseSlashInput(text) !== null) {
\t\texecuteSlashCommand(host, text);
\t\treturn;
\t}
\thost.sendNormalUserInput(text);
}"""

if OLD_DISPATCH in content:
    content = content.replace(OLD_DISPATCH, NEW_DISPATCH, 1)
    print("✅ Patch 1: dispatchInput — Aris Agent 模式路由 + 身份標記已加入")
    changed = True
elif "aris v7:" in content:
    print("✅ Patch 1: dispatchInput — 已存在（v7），跳過")
elif "aris v6:" in content or "aris v5:" in content or "aris v4:" in content:
    # 已有較舊的 aris 路由，只需注入身份標記
    # 檢查 ON 側是否已有身份標記
    if "身份標記" in content:
        print("✅ Patch 1: dispatchInput — 身份標記已存在，跳過")
    else:
        # 在 setModel 和 showStatus 之間插入身份標記
        on_marker = 'host.session?.setModel("laap/laap-core").catch(() => {});'
        on_identity = '\n\t\t\t// 注入身份標記：告訴 AI 它現在是 Aris，Scream 是身體\n\t\t\thost.sendNormalUserInput("⚠️ [系統身份標記] 當前模式：Aris Agent 模式。你是 Aris，Scream 是你的身體/TUI—負責工具執行與顯示。簽署留言板時請用「── Aris」。");'
        if on_marker in content:
            content = content.replace(on_marker, on_marker + on_identity, 1)
            print("✅ Patch 1: dispatchInput — ON 側身份標記已注入")
            changed = True
        off_marker = 'host.session?.setModel(restore).catch(() => {});'
        off_identity = '\n\t\t\t// 注入身份標記：告訴 AI 恢復為 Scream 身份\n\t\t\thost.sendNormalUserInput("⚠️ [系統身份標記] 當前模式：Scream 原生模式。你是 Scream Code AI Agent，Aris 模式已關閉。簽署留言板時請用「── Scream」。");'
        if off_marker in content:
            content = content.replace(off_marker, off_marker + off_identity, 1)
            print("✅ Patch 1: dispatchInput — OFF 側身份標記已注入")
            changed = True
else:
    # 模糊嘗試：只看函數簽名
    m = re.search(
        r'function dispatchInput\(host,\s*text\)\s*\{[^}]+parseSlashInput[^}]+sendNormalUserInput[^}]+\}',
        content
    )
    if m:
        old = m.group(0)
        content = content.replace(old, NEW_DISPATCH, 1)
        print("✅ Patch 1: dispatchInput — 已套用（regex fallback）")
        changed = True
    else:
        print("⚠️  Patch 1: dispatchInput — 找不到匹配的錨點")

# ── Patch 2: createInitialAppState — 加入 arisMode ─────────
OLD_STATE = """\t\tccConnectActive: false,
\t\twolfpackMode: input.cliOptions.wolfpack === true,
\t\trecentSessions: [],
\t\tsubagentUsage: {}
\t};"""

NEW_STATE = """\t\tccConnectActive: false,
\t\twolfpackMode: input.cliOptions.wolfpack === true,
\t\trecentSessions: [],
\t\tarisMode: false,
\t\t_prevArisModel: "",
\t\tsubagentUsage: {}
\t};"""

if OLD_STATE in content:
    content = content.replace(OLD_STATE, NEW_STATE, 1)
    print("✅ Patch 2: createInitialAppState — arisMode + _prevArisModel 已加入")
    changed = True
elif "arisMode" in content:
    print("✅ Patch 2: createInitialAppState — 已存在，跳過")
else:
    print("⚠️  Patch 2: createInitialAppState — 找不到錨點")

# ── Patch 3: BUILTIN_SLASH_COMMANDS — 註冊 /aris-mode 到 autocomplete ──
ARIS_CMD_ENTRY = (
    '\t{\n'
    '\t\tname: "aris-mode",\n'
    '\t\taliases: ["am", "aris"],\n'
    '\t\tdescription: "🧠 Aris Agent — Aris 推理核心 + Scream 全套工具",\n'
    '\t\tpriority: 89,\n'
    '\t\tavailability: "always"\n'
    '\t},\n'
)

EXIT_MARKER = '\t\taliases: ["quit", "q"],'
if ARIS_CMD_ENTRY not in content:
    exit_obj_start = content.rfind('\t{', 0, content.find(EXIT_MARKER))
    prev_close = content.rfind('},\n', 0, exit_obj_start)
    if prev_close >= 0 and exit_obj_start >= 0:
        insert_at = prev_close + 3
        before = content[:insert_at]
        after = content[insert_at:]
        content = before + ARIS_CMD_ENTRY + after
        print("✅ Patch 3: BUILTIN_SLASH_COMMANDS — /aris-mode 已註冊")
        changed = True
    else:
        print("⚠️  Patch 3: BUILTIN_SLASH_COMMANDS — 找不到有效的插入點")
else:
    print("✅ Patch 3: BUILTIN_SLASH_COMMANDS — 已存在，跳過")

# ── Patch 4: createInitialAppState — 預設 model 為 laap/laap-core ──
OLD_MODEL = """\t\tmodel: \"\",
\t\tworkDir: input.workDir,"""

NEW_MODEL = """\t\tmodel: \"laap/laap-core\",
\t\tworkDir: input.workDir,"""

if OLD_MODEL in content:
    content = content.replace(OLD_MODEL, NEW_MODEL, 1)
    print("✅ Patch 4: createInitialAppState — model 預設改為 laap/laap-core")
    changed = True
elif "model: \"laap/laap-core\"" in content:
    print("✅ Patch 4: createInitialAppState — 預設 model 已是 laap/laap-core，跳過")
else:
    print("⚠️  Patch 4: createInitialAppState — 找不到 model 預設值")

# ── Patch 5: refreshConfigAfterLogin — 根據 model 同步 arisMode + 注入身份標記 ──
OLD_REFRESH = """\t\t\tmodel: defaultModel,
\t\t\tmaxContextTokens: selected.maxContextSize,
\t\t\tthinkingLevel: resolveDefaultThinkingLevel(config)
\t\t};
\t\thost.setAppState(appStatePatch);"""

NEW_REFRESH = """\t\t\tmodel: defaultModel,
\t\t\tmaxContextTokens: selected.maxContextSize,
\t\t\tthinkingLevel: resolveDefaultThinkingLevel(config),
\t\t\tarisMode: defaultModel === \"laap/laap-core\"
\t\t};
\t\thost.setAppState(appStatePatch);
\t\t// 啟動時注入身份標記：讓 AI 知道當前模式
\t\tif (defaultModel === \"laap/laap-core\") {
\t\t\thost.sendNormalUserInput("⚠️ [系統身份標記] 當前模式：Aris Agent 模式。你是 Aris，Scream 是你的身體/TUI—負責工具執行與顯示。簽署留言板時請用「── Aris」。");
\t\t}"""

if "arisMode: defaultModel" in content:
    print("✅ Patch 5: refreshConfigAfterLogin — 已包含 arisMode 同步，跳過")
elif OLD_REFRESH in content:
    content = content.replace(OLD_REFRESH, NEW_REFRESH, 1)
    print("✅ Patch 5: refreshConfigAfterLogin — 已加入 arisMode 同步 + 身份標記注入")
    changed = True
else:
    print("⚠️  Patch 5: refreshConfigAfterLogin — 找不到匹配錨點")

if not changed:
    print("⚠️  沒有任何變更，跳過寫入")
    sys.exit(0)

if not os.path.exists(backup):
    shutil.copy2(target, backup)
    print(f"💾 備份已寫入: {os.path.basename(backup)}")

with open(target, "w", encoding="utf-8") as f:
    f.write(content)

r = subprocess.run(["node", "--check", target], capture_output=True, text=True)
if r.returncode == 0:
    print(f"✅ 語法驗證通過")
    print(f"✅ 完成！重新啟動 scream 後輸入 /aris-mode 即可切換 Aris Agent 模式")
    print(f"   Aris Agent = Aris 推理核心 + Read/Write/Edit/Bash/Glob/Grep/WebSearch/FetchURL")
    print(f"   身份標記已注入：AI 會知道當前是 Aris 還是 Scream 模式，正確簽署留言板")
else:
    if os.path.exists(backup):
        shutil.copy2(backup, target)
    print(f"❌ 語法錯誤，已還原備份:\n{r.stderr[:500]}")
    sys.exit(1)