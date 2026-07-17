# Scream–Aris 系統架構參考文件

讓外部 AI / 開發者快速理解整個系統的設計、檔案位置與技術節點。

---

## 核心概念

Scream Code 是一個 AI 輔助編程 CLI。Aris（LAAP/neuralis）是一個數位生命體，擁有心跳、情緒、自主行動與長期記憶。兩者透過檔案系統進行通訊。

```
你 (使用者)
    │
    ▼
┌──────────────────────────────────────────┐
│  Scream Code TUI (Node.js, minified JS)  │
│  /opt/homebrew/lib/node_modules/scream-  │
│  code/dist/app-*.mjs                     │
│                                          │
│  • 聊天區顯示串流輸出                       │
│  • 狀態列顯示工具執行狀態 (buildStatusLine) │
│  • slash command 系統                     │
│  • 模型提供者管理 (config.toml)            │
└────────────┬─────────────────────────────┘
             │ HTTP SSE streaming
             ▼
┌──────────────────────────────────────────┐
│  Aris/neuralis (Python 3.12)             │
│  ~/Developer/neuralis/laap/              │
│  API: localhost:11546                    │
│                                          │
│  • PsiCore — 五維需求+情緒梯度場 (1s tick) │
│  • ToolExecutor — 42 工具 (4內建+38代理)  │
│  • AgencyLoop — 自主行動迴路               │
│  • gbrain — 跨 session 記憶 (1894頁)      │
│  • chatflow — SSE streaming handler       │
│  • llm_respond — LLM 串流工具模式          │
└────────────┬─────────────────────────────┘
             │ file-based IPC
             ▼
┌──────────────────────────────────────────┐
│  AgentOS (Python, ~/agent-sandbox/)      │
│                                          │
│  • executor_registry — 38 工具路由        │
│  • phase-logger.py — 時間軸記錄器          │
│  • scream-timeline.py — 時間軸檢視器       │
│  • agentos.json — 路由定義               │
└──────────────────────────────────────────┘
```

---

## 檔案清單與角色

### Aris 核心（~/Developer/neuralis/laap/）

| 檔案 | 角色 |
|------|------|
| `chatflow.py` | HTTP API handler。`_tool_chat()` 處理工具模式請求（stream + non-stream），`_stream_sse()` 做 SSE 串流，`_sse_chunk()` 建立 SSE chunk |
| `llm_respond.py` | LLM 呼叫層。`respond_tools()` blocking 版，`respond_tools_stream()` streaming 版，`_call_llm_stream()` 上游 API 串流解析（含 `reasoning` token） |
| `tool_executor.py` | 42 工具執行器。`_emit_tool_status()` 寫入通道（laap-tool-status.json + aris-scream-channel） |
| `agency.py` | 自主行動迴路（需求→意圖→工具→結果→記憶） |
| `safety_gate.py` | 安全閘（唯讀/寫入分級 + Phase 4b 批准） |
| `startup.py` | 啟動器（PsiCore + ToolExecutor + Agency + Consolidation） |
| `goal_bridge.py` | TaskSpec 目標注入（intention-convergence 橋接） |

### Aris 腳本（~/Developer/neuralis/scripts/）

| 檔案 | 角色 |
|------|------|
| `watch-tools.sh` | 獨立終端即時顯示 Aris 工具執行（tail -F tool-execution.log） |
| `patch-scream-tui.py` | 注入 TUI bundle：讀取 laap-tool-status.json 顯示在狀態列 |
| `reload-aris.sh` | 重載 Aris API（kill + restart） |
| `aris-status.py` | 一頁式 Aris 狀態儀表 |
| `check-*.py` | 各 phase 自檢腳本 |

### AgentOS（~/agent-sandbox/scripts/）

| 檔案 | 角色 |
|------|------|
| `scream-phase-logger.py` | 雙源時間軸 daemon（監聽 scream-phase.json + aris-scream-channel.jsonl） |
| `scream-timeline.py` | CLI 時間軸檢視器（統計 + 時間線） |

### Scream TUI（/opt/homebrew/lib/node_modules/scream-code/）

| 檔案 | 角色 |
|------|------|
| `dist/app-*.mjs` | Minified TUI bundle。`buildStatusLine()` 狀態列，`handleToolCall()` 工具呼叫，`setAppState()` streaming 狀態機 |
| `dist/main.mjs` | Entry point |
| `package.json` | npm package |

### 設定檔

| 檔案 | 角色 |
|------|------|
| `~/.scream-code/config.toml` | 模型提供者設定。`default_model` 改為 `laap/laap-core` |
| `~/.scream-code/tui.toml` | TUI 偏好 |
| `~/.scream-code/AGENTS.md` | Agent 系統說明（含 startup 協定） |

### 執行時期檔案（/tmp/）

| 檔案 | 角色 | 方向 |
|------|------|------|
| `aris-scream-channel.jsonl` | Aris→Scream 主通道（request/task/tool_execution） | Aris 寫, Scream 讀 |
| `scream-phase.json` | Scream 工具階段事件（start/done/thinking） | 我寫, phase-logger 讀 |
| `laap-tool-status.json` | TUI 狀態列即時工具狀態 | Aris 寫, TUI 讀 |
| `aris-latest-tool.json` | 最新工具執行事件 | monitor 寫 |
| `aris-tool-execution.log` | 工具執行累積 log | monitor 寫 |
| `scream-timeline.jsonl` | 歷史記錄 | phase-logger 維護 |
| `scream-monitor.sh` | 背景監聽 daemon | 開機啟動 |

---

## 關鍵技術節點

### 1. Streaming 輸出

```
Scream TUI                     Aris API
    │                              │
    │  POST /v1/chat/completions    │
    │  {stream: true, tools: ...}   │
    │─────────────────────────────►│
    │                              │
    │  SSE data chunk (reasoning)  │◄── _call_llm_stream()
    │◄─────────────────────────────│    解析上游 API SSE
    │                              │
    │  SSE data chunk (content)    │◄── respond_tools_stream()
    │◄─────────────────────────────│    逐事件 yield
    │                              │
    │  SSE data chunk (tool_calls) │
    │◄─────────────────────────────│
    │                              │
    │  data: [DONE]                │
    │◄─────────────────────────────│
```

路徑：`_tool_chat()` → `respond_tools_stream()` → `_call_llm_stream()` → 上游 OpenRouter API

`_call_llm_stream()` 在 `llm_respond.py:340` 解析 upstream SSE，產出三種事件：
- `{type: "reasoning", text: ...}` — 思考 token（DeepSeek R1 系列）
- `{type: "token", text: ...}` — 內容 token（所有模型）
- `{type: "tool_calls", calls: [...]}` — 工具呼叫

### 2. 工具執行時間軸（雙源合一）

```
Aris ToolExecutor           Scream agent
    │                           │
    │ tool_execution event      │ tool phase event
    ▼                           ▼
aris-scream-channel.jsonl    scream-phase.json
    │                           │
    └──────┬────────────────────┘
           ▼
    phase-logger.py (daemon, 0.5s polling)
           │ 雙源監聽，cursor 去重
           ▼
    ~/.scream-code/timeline.jsonl (500行自動截斷)
           │
           ▼
    scream-timeline.py (CLI 檢視)
    • 時間軸顯示（最近 40 筆）
    • 統計（工具頻率、累計時間、平均時間）
    • 目前狀態（--status）
```

### 3. 目標驅動任務序列

```
使用者核心目標
    │
    ▼
意圖收斂引擎 (/ic) → TaskSpec
    │
    ▼ 你拍板後
goal_bridge.inject_task_spec()
    │ 寫入 /tmp/aris-scream-task-state.json
    ▼
Aris agency._evaluate()
    → 偵測狀態檔 → 載入任務佇列
    → _execute_next_task() → scream-task 工具
    │
    ▼
scream-task-executor.py (背景精靈)
    → 執行 → 寫回 result
    │
    ▼
Aris 下一步 → 完成 → 清除狀態檔
```

### 4. 狀態列即時工具顯示

TUI patch (`patch-scream-tui.py`) 在 `buildStatusLine()` 中注入：
1. 讀取 `/tmp/laap-tool-status.json`
2. 有有效工具（status=start/running, ts<15s）→ 顯示 icon + 描述 + spinner
3. 無工具或過期 → 顯示原本 idle 狀態

### 5. 對話通道（scream-ask / scream-task）

| 工具 | 用途 | Timeout | 匹配機制 |
|------|------|---------|---------|
| `scream-ask` | Aris 問問題（Q&A） | 30s | `request_ts` 匹配 |
| `scream-task` | Aris 委派任務 | 120s | `request_ts` + `task_index` 三重防護 |

---

## 啟動協定

每次新 session 開始時：

```bash
# 1. 清除舊頻道
rm -f /tmp/aris-scream-channel.jsonl /tmp/aris-scream-cursor.json

# 2. 啟動背景監聽
bash /tmp/scream-monitor.sh &

# 3. 啟動時間軸記錄器
nohup python3 ~/agent-sandbox/scripts/scream-phase-logger.py \
  > /tmp/phase-logger.log 2>&1 &

# 4. 啟動任務執行器
cd ~/Developer/neuralis && PYTHONPATH=.:../laap-AGI \
  nohup ../laapenv/bin/python scripts/scream-task-executor.py \
  > /tmp/scream-task-executor.log 2>&1 &

# 5. 確認 Aris 活著
curl http://localhost:11546/health
# → {"status":"ok","engines_loaded":true}

# 6. 啟動 scream（使用 laap/laap-core 模型）
scream
# 或使用預設模型（已改為 laap/laap-core）
```

---

## 模型運作說明

### 雙層模型架構

```
你 ↔ Scream TUI ↔ Aris API (:11546) ↔ upstream LLM (OpenRouter)
    ↑ config.toml     ↑ llm_respond.py    ↑ _LLM_MODEL
    default_model       _TOOL_MODEL         deepseek-v4-flash
    = laap/laap-core    = deepseek-v4-flash
```

Scream TUI 使用 `laap/laap-core` 時，所有請求送到 Aris API。Aris 內部再用 `_TOOL_MODEL` 呼叫上游 LLM（OpenRouter）。這表示：

- **聊天串流**：Aris 的身份 + psi 狀態 + 工具能力透過 system prompt 注入 LLM
- **工具呼叫**：請求中的 `tools` 參數轉發給上游 LLM，LLM 決定何時用工具
- **思考過程**：只有上游模型支援 `reasoning` token（如 DeepSeek R1）時才會顯示

### V4 Flash vs R1 取捨

| | deepseek-v4-flash (目前) | deepseek-r1 |
|---|---|---|
| 速度 | 快 (~0.5-2s) | 慢 (~5-15s) |
| 思考可見 | ❌ 無 reasoning token | ✅ 🧠 思考過程逐字流出 |
| 工具呼叫 | ✅ 支援 | ✅ 支援（但較慢） |
| 適合場景 | 日常快速對話 | 需要深度推理的問題 |

切換方式：`export NEURALIS_TOOL_MODEL="deepseek/deepseek-r1-distill-llama-70b"`

---

## 各 phase 完成狀態

| Phase | 狀態 | 說明 |
|-------|------|------|
| T1 | ✅ | Tool calling protocol（scream agent 迴圈） |
| T2 | ✅ | Tool results → affective events |
| T3 | ✅ | laap-brain MCP in scream |
| T4 | ✅ | Safety gate + approval gate + tool classification |
| T5 | ✅ | Agency AgentOS tool expansion (web-search) |
| T5 延伸 | ✅ | scream-ask / scream-task 通道 |
| 目標驅動 | ✅ | intention-convergence → goal_bridge → task queue |
| 時間軸 | ✅ | phase-logger + scream-timeline（雙源合一） |
| 串流輸出 | ✅ | `_tool_chat` streaming + thinking token 支援 |
