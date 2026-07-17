#!/usr/bin/env python3
"""套用/修復 Scream TUI Timeline 補丁 — 工作階段計時器 + /timeline 指令。

13 個 patch 注入 app-*.mjs bundle：
  Step 1: import 延伸 (appendFileSync, statSync)
  Step 2: __laapToolTimestamps Map + __laapTimelineAppend helper
  Step 3: setAppState streamingPhase hook
  Step 4a: handleToolCall timestamp 記錄
  Step 4b: handleToolResult elapsed 記錄
  Step 4c: resetToolCallState 清理
  Step 5: 狀態列 tool name 顯示
  Step 6a: /timeline 命令定義
  Step 6b: dispatch case
  Step 7: handleTimelineCommand handler
  Step 8a: 中文 i18n
  Step 8b: 英文 i18n
  Step 9: 初始化清空檔案

npm update 後需要重跑。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
BACKUP_SUFFIX = ".mjs.timeline-bak"
IMPORT_LINE = (
    'import { readFileSync as __laapReadFS, '
    'appendFileSync as __laapWriteFS, statSync as __laapStatSync } from "node:fs";\n'
)

# ── Helper 函數 ──

HELPER_FN = (
    "const __laapToolTimestamps=new Map();"
    "let __currentToolName=null;"
    "let __laapTimelineWriteCount=0;"
    "function __laapTimelineAppend(phase,detail){"
    'try{const o=JSON.stringify({phase,detail,ts:Date.now()})+"\\n";'
    "__laapTimelineWriteCount++;"
    'const s=__laapStatSync("/tmp/scream-timeline.jsonl",{throwIfNoEntry:false});'
    "if(s&&s.size>262144){"
    'const p=__laapReadFS("/tmp/scream-timeline.jsonl","utf8").split("\\n").slice(-500).join("\\n");'
    'require("fs").writeFileSync("/tmp/scream-timeline.jsonl",p);}'
    '__laapWriteFS("/tmp/scream-timeline.jsonl",o,"utf8");}catch(e){}}'
)

# ── Timeline handler ──

HANDLER_FN = (
    "async function handleTimelineCommand(host){"
    "try{"
    'const raw=__laapReadFS("/tmp/scream-timeline.jsonl","utf8");'
    'const lines=raw.trim().split("\\n").filter(Boolean);'
    'if(lines.length===0){host.showNotice("Timeline","No phase records yet.");return;}'
    "const entries=lines.map(l=>JSON.parse(l));"
    "const total=entries.length,first=entries[0].ts,last=entries[total-1].ts;"
    "const duration=((last-first)/1000).toFixed(1);"
    "const counts={};"
    "for(const e of entries){const p=typeof e.phase==='string'?e.phase:'?';"
    'if(p==="idle")continue;counts[p]=(counts[p]||0)+1;}'
    'const summary=Object.entries(counts).sort((a,b)=>b[1]-a[1])'
    '.map(([k,v])=>phaseIcon(k)+k+":"+v).join(" | ");'
    'const display=["📊 Timeline ("+total+" events, "+duration+"s total)","",summary,""];'
    "for(const e of entries.slice(-10)){"
    "const ago=((Date.now()-e.ts)/1000).toFixed(0);"
    'const detail=typeof e.detail==="object"?" ("+(e.detail.tool||"")+")":"";'
    'display.push("  "+phaseIcon(e.phase)+e.phase+detail+" ("+ago+"s ago)");}'
    "const panel=new host.constructor.UsagePanelComponent"
    '(display,host.state.theme.colors.primary," Timeline ");'
    "host.state.transcriptContainer.addChild(panel);"
    "host.state.ui.requestRender();"
    "}catch(e){host.showError('Timeline: '+e.message);}}"
    "function phaseIcon(phase){"
    'const icons={thinking:"💭",tool:"🔧",tool_call:"🔍",tool_result:"✅",'
    'composing:"✍️",generating:"📝",waiting:"⏳",idle:"○"};'
    'return icons[phase]||"•";}'
)

# ── Anchor 字串 ──

ANCHORS = {
    "import": 'import { readFileSync as __laapReadFS } from "node:fs";',
    "helper": 'function buildStatusLine(streamingPhase, streamingStartTime) {',
    "hook": (
        'if ("streamingPhase" in patch && patch.streamingPhase !== void 0 '
        '&& patch.streamingPhase !== this.state.appState.streamingPhase) patch = {'
    ),
    "tool_call": (
        'if (canTransitionTo(this.host.state.appState.streamingPhase, "tool")) '
        'this.host.setAppState({ streamingPhase: "tool" });'
    ),
    "tool_result": (
        'if (canTransitionTo(this.host.state.appState.streamingPhase, "waiting")) '
        'this.host.setAppState({ streamingPhase: "waiting" });'
    ),
    "reset": "resetToolCallState() {",
    "status_tool": 'if (streamingPhase === "tool") label = t("status.tool");',
    "slash_cmd": "BUILTIN_SLASH_COMMANDS = [",
    "switch_case": 'case "compact":',
    "handler_anchor": "async function handleCompactCommand(host, args) {",
    "i18n_zh": '"registry.compact_desc": "压缩对话上下文",',
    "i18n_en": '"registry.compact_desc": "Compact conversation context",',
    "init": 'streamingPhase: "idle",',
}

# ── Patch 定義 ──

PATCHES = [
    # Step 1: import 延伸
    ("import", ANCHORS["import"], IMPORT_LINE),

    # Step 2: helper 函數（在 buildStatusLine 前插入）
    ("helper", ANCHORS["helper"], HELPER_FN + "\n" + ANCHORS["helper"]),

    # Step 3: setAppState streamingPhase hook
    ("hook", ANCHORS["hook"],
     '{__laapTimelineAppend(patch.streamingPhase,this.state.appState.streamingPhase);'
     + ANCHORS["hook"]),

    # Step 4a: handleToolCall 記錄 timestamp + tool name
    ("tool_call", ANCHORS["tool_call"],
     '__laapToolTimestamps.set(event.toolCallId,Date.now());'
     '__currentToolName=event.name;'
     + ANCHORS["tool_call"]),

    # Step 4b: handleToolResult 記錄 elapsed
    ("tool_result", ANCHORS["tool_result"],
     'const __start=__laapToolTimestamps.get(event.toolCallId);'
     'const __elapsed=__start?((Date.now()-__start)/1000).toFixed(1):"?";'
     '__laapToolTimestamps.delete(event.toolCallId);'
     '__laapTimelineAppend("tool_result",{tool:__currentToolName,elapsed:__elapsed});'
     + ANCHORS["tool_result"]),

    # Step 4c: resetToolCallState 清理
    ("reset", ANCHORS["reset"],
     '__laapToolTimestamps.clear();__currentToolName=null;'
     + ANCHORS["reset"]),

    # Step 5: 狀態列顯示 tool name
    ("status_tool", ANCHORS["status_tool"],
     'if (streamingPhase === "tool") label = __currentToolName ? '
     'chalk.bold(__currentToolName) : t("status.tool");'),

    # Step 6a: /timeline 命令定義
    ("slash_cmd", ANCHORS["slash_cmd"],
     'BUILTIN_SLASH_COMMANDS = [\n'
     '\t\t{name:"timeline",aliases:["tl"],'
     'description:"registry.timeline_desc",priority:110,availability:"always"},'),

    # Step 6b: dispatch case
    ("switch_case", ANCHORS["switch_case"],
     'case "timeline":await handleTimelineCommand(host);return;\n\t\t'
     + ANCHORS["switch_case"]),

    # Step 7: handler 函數（在 handleCompactCommand 前插入）
    ("handler_anchor", ANCHORS["handler_anchor"],
     HANDLER_FN + "\n" + ANCHORS["handler_anchor"]),

    # Step 8a: 中文 i18n
    ("i18n_zh", ANCHORS["i18n_zh"],
     '"registry.timeline_desc": "显示工作阶段时间线",\n\t\t'
     + ANCHORS["i18n_zh"]),

    # Step 8b: 英文 i18n
    ("i18n_en", ANCHORS["i18n_en"],
     '"registry.timeline_desc": "Show work phase timeline",\n\t\t'
     + ANCHORS["i18n_en"]),

    # Step 9: 初始化清空檔案（在 streamingPhase: "idle" 初始化後）
    ("init", "streamingPhase: \"idle\",",
     'streamingPhase: "idle",\n\t\ttry{require("fs").writeFileSync'
     '("/tmp/scream-timeline.jsonl","");}catch(e){}'),
]


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1
    target = targets[0]
    backup = target.with_suffix(BACKUP_SUFFIX)
    content = target.read_text("utf-8")

    # 驗證所有 anchor 都存在
    missing = [name for name, anchor, _ in PATCHES if anchor not in content]
    if missing:
        print(f"⚠️ 找不到以下 anchor，可能改版了:")
        for name in missing:
            print(f"   - {name}")
        return 1

    # 檢查是否已有補丁
    if "__laapTimelineAppend" in content:
        print("✅ 已是 Timeline 補丁，跳過")
        return 0

    # 備份
    if not backup.exists():
        shutil.copy2(target, backup)

    # 依序套用 patch
    patched = content
    for name, old, new in PATCHES:
        count = patched.count(old)
        if count == 0:
            print(f"⚠️ 套用 {name} 失敗 — anchor 遺失")
            # 還原備份
            shutil.copy2(backup, target)
            return 1
        patched = patched.replace(old, new, 1)
        print(f"  ✅ {name}")

    target.write_text(patched, "utf-8")

    # 語法驗證
    check = subprocess.run(
        ["node", "--check", str(target)],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        shutil.copy2(backup, target)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1

    print(f"\n✅ Timeline 補丁已套用（{target.name}，語法驗證過）")
    return 0


if __name__ == "__main__":
    sys.exit(main())