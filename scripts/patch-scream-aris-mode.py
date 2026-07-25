#!/usr/bin/env python3
"""patch-scream-aris-mode.py: 在新版 scream-code bundle 重建 /aris-mode 切換 + Aris Agent 模式。

Aris Agent 模式 = Aris 推理核心 + Scream 全套工具（Read/Write/Edit/Bash/Glob/Grep/WebSearch/FetchURL）。

修改兩個點：
1. dispatchInput() — 加入 aris-mode 切換路由（模型切換到 laap/laap-core，走完整 agent 迴圈）
2. createInitialAppState() — 加入 arisMode + _prevArisModel 初始值

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
\t// aris v6: /aris-mode toggle → 切模型到 laap/laap-core + 同步 agent session.setModel()
\tconst t = text.trim();
\tif (t === "/aris-mode" || t === "/am" || t === "/aris") {
\t\tif (!host.state.appState.arisMode) {
\t\t\thost.setAppState({ arisMode: true, _prevArisModel: host.state.appState.model });
\t\t\tif (host.state.appState.model !== "laap/laap-core") {
\t\t\t\thost.setAppState({ model: "laap/laap-core" });
\t\t\t}
\t\t\thost.session?.setModel("laap/laap-core").catch(() => {});
\t\t\thost.showStatus("🧠 Aris Agent 模式已開啟 — Aris 核心 + Scream 全套工具", "#00ff88");
\t\t} else {
\t\t\tconst prev = host.state.appState._prevArisModel || "";
\t\t\tconst restore = prev || host.state.appState.model;
\t\t\thost.setAppState({ arisMode: false, _prevArisModel: "", model: restore });
\t\t\thost.session?.setModel(restore).catch(() => {});
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
    print("✅ Patch 1: dispatchInput — Aris Agent 模式路由已加入")
    changed = True
elif "aris v4:" in content:
    print("✅ Patch 1: dispatchInput — 已存在（v4），跳過")
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
else:
    if os.path.exists(backup):
        shutil.copy2(backup, target)
    print(f"❌ 語法錯誤，已還原備份:\n{r.stderr[:500]}")
    sys.exit(1)