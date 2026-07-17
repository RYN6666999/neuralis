#!/usr/bin/env python3
"""aris-mode 完整 agent 補丁（npm update 後需要重跑）。

問題：/aris-mode 直通過去 spawn aris-chat.py --once，完全繞過 Scream
agent 迴圈，導致 plan mode / WolfPack / skills / TUI panels 全部不可用。

修法：
1. aris-mode toggle 時自動切換模型到 laap/laap-core（走 performModelSwitch）
2. aris-mode toggle 關閉時還原前一個模型
3. 移除 sendNormalUserInput 中的 arisMode bypass（不再 spawn aris-chat.py）
4. appState 新增 _prevArisModel 欄位

慣例同 patch-scream-aris-stream.py v2：glob dist 檔名、精確錨點、
獨立備份（.aris-agent-bak）、node --check 失敗自動還原。
"""
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
MARK = "aris-agent v1"

# ── 錨點 1: initial state ──────────────────────────────────────
OLD_INIT = '\t\tarisMode: false\n\t};\n}\nvar ScreamTUI'
NEW_INIT = '\t\tarisMode: false,\n\t\t_prevArisModel: ""\n\t};\n}\nvar ScreamTUI'

# ── 錨點 2: aris-mode handler ─────────────────────────────────
OLD_HANDLER = '''case "aris-mode": {
\t\t\tconst current = host.state.appState.arisMode;
\t\t\thost.setAppState({ arisMode: !current });
\t\t\thost.showNotice("Aris Mode", !current ? "ON - All messages go directly to Aris" : "OFF - Normal Scream agent mode");
\t\t\thost.state.ui.requestRender();
\t\t\treturn;
\t\t}'''

NEW_HANDLER = '''case "aris-mode": {
\t\t\tconst current = host.state.appState.arisMode;
\t\t\tif (!current) {
\t\t\t\tconst prevModel = host.state.appState.model;
\t\t\t\tif (prevModel !== "laap/laap-core") {
\t\t\t\t\thost.setAppState({ arisMode: true, _prevArisModel: prevModel });
\t\t\t\t\tawait performModelSwitch(host, "laap/laap-core", "off");
\t\t\t\t\thost.showNotice("Aris Mode", "ON - Full agent mode with laap/laap-core");
\t\t\t\t} else {
\t\t\t\t\thost.setAppState({ arisMode: true });
\t\t\t\t\thost.showNotice("Aris Mode", "Already using laap/laap-core");
\t\t\t\t}
\t\t\t} else {
\t\t\t\tconst prev = host.state.appState._prevArisModel;
\t\t\t\tif (prev && prev !== "laap/laap-core") {
\t\t\t\t\thost.setAppState({ arisMode: false });
\t\t\t\t\tawait performModelSwitch(host, prev, "off");
\t\t\t\t\thost.showNotice("Aris Mode", "OFF - Restored previous model");
\t\t\t\t} else {
\t\t\t\t\thost.setAppState({ arisMode: false });
\t\t\t\t\thost.showNotice("Aris Mode", "OFF");
\t\t\t\t}
\t\t\t}
\t\t\thost.state.ui.requestRender();
\t\t\treturn;
\t\t}'''

# ── 錨點 3: sendNormalUserInput bypass ────────────────────────
OLD_BYPASS = '// ARIS MODE: direct passthrough to Aris, no Scream agent'
REPL_BYPASS = 'if (this.host.state.appState.model.trim().length === 0)'


def find_mjs() -> Path:
    """Glob dist for the main chunk (app-*.mjs)."""
    candidates = list(DIST.glob("app-*.mjs"))
    if not candidates:
        print("❌ No app-*.mjs found in dist")
        sys.exit(1)
    if len(candidates) > 1:
        print(f"⚠️ Multiple candidates: {candidates}, using first")
    return candidates[0]


def patch(fpath: Path) -> None:
    bak = fpath.with_suffix(fpath.suffix + ".aris-agent-bak")
    if bak.exists():
        print(f"⚠️  Backup {bak.name} exists — previous patch may be applied. Restoring first.")
        shutil.copy2(bak, fpath)

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    edits = 0

    # Edit 1: initial state
    if OLD_INIT in content:
        content = content.replace(OLD_INIT, NEW_INIT, 1)
        edits += 1
        print("✅  Edit 1: _prevArisModel added to initial state")
    elif NEW_INIT in content[:content.find("}\nvar ScreamTUI") + 50]:
        print("⚠️  Edit 1: already applied (skipping)")
        edits += 1
    else:
        print("❌  Edit 1: anchor not found")
        # Search for context
        idx = content.find("arisMode: false")
        if idx >= 0:
            print(f"    Found 'arisMode: false' at {idx}: {repr(content[idx:idx+30])}")

    # Edit 2: aris-mode handler
    if OLD_HANDLER in content:
        content = content.replace(OLD_HANDLER, NEW_HANDLER, 1)
        edits += 1
        print("✅  Edit 2: aris-mode handler rewritten")
    elif NEW_HANDLER in content:
        print("⚠️  Edit 2: already applied (skipping)")
        edits += 1
    else:
        print("❌  Edit 2: anchor not found")
        idx = content.find('case "aris-mode"')
        if idx >= 0:
            print(f"    Found at {idx}: {repr(content[idx:idx+200])}")

    # Edit 3: remove bypass
    if OLD_BYPASS in content:
        idx_start = content.index(OLD_BYPASS)
        idx_end = content.index(REPL_BYPASS)
        content = content[:idx_start] + content[idx_end:]
        edits += 1
        print("✅  Edit 3: sendNormalUserInput bypass removed")
    elif OLD_BYPASS not in content:
        # Check if it was already removed
        idx_snu = content.find("async sendNormalUserInput")
        after = content[idx_snu:idx_snu+200]
        if "if (this.host.state.appState.model.trim().length === 0)" in after:
            print("⚠️  Edit 3: already applied (skipping)")
            edits += 1
        else:
            print("❌  Edit 3: unexpected state")
    else:
        print("❌  Edit 3: anchor not found")

    if edits < 3:
        print(f"\n❌  Only {edits}/3 edits applied. Aborting.")
        if bak.exists():
            shutil.copy2(bak, fpath)
            print("↩️  Restored from backup.")
        sys.exit(1)

    # Backup first time
    if not bak.exists():
        shutil.copy2(fpath, bak)
        print(f"💾  Backup saved to {bak.name}")

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

    # Syntax check
    result = subprocess.run(["node", "--check", str(fpath)], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"\n🎉  {MARK} patch applied successfully!")
        print(f"    File: {fpath.name}")
        print(f"    Backup: {bak.name}")
    else:
        print(f"\n❌  Syntax check failed: {result.stderr}")
        if bak.exists():
            shutil.copy2(bak, fpath)
            print("↩️  Restored from backup.")
        sys.exit(1)


def main():
    fpath = find_mjs()
    patch(fpath)


if __name__ == "__main__":
    main()