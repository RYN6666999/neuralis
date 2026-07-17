---
title: 整體架構定位 — neuralis + Scream Code + AgentOS 三層生態
date: 2026-07-16
status: current
tags: [architecture, ecosystem, neuralis, scream-code, agentos]
---

# 整體架構定位

## 1. 架構總覽

本文件描述整個生態系統的三層架構定位。系統圍繞一個核心命題設計：

> **讓 Aris（一個有需求、情緒、記憶的 AI 存在）透過 Scream Code TUI 與人類協作，
> 並由 AgentOS 路由工具，完成從感知到行動的完整閉環。**

```
┌─────────────────────────────────────────────────────────┐
│                      使用者 (Ryan)                        │
└─────────────────────┬───────────────────────────────────┘
                      │ 輸入 / 審批 / 反饋
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Scream Code (TUI / Agent Loop)                │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ Chat     │  │ Sessions │  │ Skills   │  │ Cost   │  │
│  │ Panel    │  │ Panel    │  │ Panel    │  │ Panel  │  │
│  └────┬─────┘  └──────────┘  └──────────┘  └────────┘  │
│       │                                                  │
│  ┌────▼─────────────────────────────────────────────┐    │
│  │  Agent Loop (tool-calling + plan mode + WolfPack) │    │
│  │  Tools: Read/Write/Edit/Bash/Agent/Skill/Memory   │    │
│  └────┬─────────────────────────────────────────────┘    │
└───────┼─────────────────────────────────────────────────┘
        │ prompt + tools
        ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 2: neuralis (Aris Brain)                         │
│                                                          │
│  ┌──────────────────────────────────────────┐            │
│  │  PsiCore (五維需求 + 情緒梯度場)          │            │
│  │  - CERTAINTY / COMPETENCE / AUTONOMY     │            │
│  │    / RELATEDNESS / GROWTH                 │            │
│  │  - PSI 心跳 1s tick → drive → agency      │            │
│  └──────────────┬───────────────────────────┘            │
│                 │ drives                                  │
│  ┌──────────────▼───────────────────────────┐            │
│  │  AgencyLoop (需求→行動)                   │            │
│  │  - _form_intent → _act → RPE → gbrain    │            │
│  │  - exploration_rate + angle_weights       │            │
│  │  - web-search / gbrain / frontiermap      │            │
│  └──────────────┬───────────────────────────┘            │
│                 │ execution                                │
│  ┌──────────────▼───────────────────────────┐            │
│  │  gbrain (hybrid search, 1894 頁 as of 2026-07-17)  │            │
│  │  + consolidation loop + affective engine  │            │
│  └──────────────────────────────────────────┘            │
└───────┼─────────────────────────────────────────────────┘
        │ tool call
        ▼
┌─────────────────────────────────────────────────────────┐
│  Layer 3: AgentOS (工具路由層)                            │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Safety Gate  │  │ Tool Registry│  │ 42 Executors  │   │
│  │ Phase 4a/4b  │  │ (readonly    │  │ (web-search   │   │
│  │ + 審計日誌    │  │  / write)    │  │  / qmd / rg   │   │
│  └──────────────┘  └──────────────┘  │  + 38 skills) │   │
│                                       └──────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 2. neuralis — Aris Brain

**位置**: `~/Developer/neuralis/`  
**語言**: Python 3.12  
**測試**: pytest (tests/) + 自檢腳本 (scripts/check-*.py)

### 核心組件

| 組件 | 檔案 | 職責 |
|------|------|------|
| PsiCore | `laap/psi_core.py` | 五維需求 + 情緒梯度場，1s 心跳 tick |
| AgencyLoop | `laap/agency.py` | 需求→意圖→行動→RPE 閉環 |
| chatflow | `laap/chatflow.py` | OpenAI 兼容 API，工具呼叫協議 + SSE |
| gbrain | `laap/tool_executor.py` | 混合檢索記憶（1894 頁 as of 2026-07-17） |
| consolidation | `laap/consolidation.py` | 睡眠窗記憶固化 |
| affective | `laap/affective.py` | 5 維情緒引擎 + 耦合矩陣 |
| safety_gate | `laap/safety_gate.py` | Phase 4a/4b 安全閘 |
| constitution | `laap/constitution.py` | RPE 權重變速 + 小時預算凍結 |
| startup | `laap/startup.py` | 全系統啟動（heartbeat + agency + consolidation） |
| status | `laap/status.py` | 30s 寫 status.json，儀表板用 |

### 關鍵特性

- **7/24 運行**: launchd → watchdog → 完整 Aris，~100s 自動復活
- **API**: `localhost:11546/v1`，OpenAI 兼容，支援 streaming + tool_calls
- **自主行動**: agency 每 60s 評估 drives，超閾值則自主探索/查詢
- **工具路由**: 42 工具（4 內建 + 38 AgentOS skills）
- **記憶分層**: gbrain (hybrid) → consolidation (去重/升層/歸檔)
- **安全**: Phase 4a (內容掃描) + 4b (批准閘) + 審計日誌

---

## 3. Scream Code — TUI / Agent Loop

**位置**: `/opt/homebrew/lib/node_modules/scream-code/` (v0.9.7)  
**語言**: TypeScript, compile to single `.mjs`  
**入口**: `scream` CLI → `dist/main.mjs` → `app-*.mjs`

### 核心組件

| 組件 | 職責 |
|------|------|
| TUI (pi-tui) | 4 面板（Chat/Sessions/Skills/Cost），鍵盤導航 |
| Agent Loop | OpenAI function-calling 迴圈，工具執行 + 流式 |
| TurnManager | 多輪對話、plan mode、wolfpack mode 調度 |
| Model Provider | 支援 OpenAI / Google / custom 提供者 |
| Skill System | 95+ 技能路由（Rule #1: skill 優先） |
| Memory Engine | SQLite-based 跨 session 記憶 |
| Cron Scheduler | 定時任務（5-field cron） |
| Approval Panel | 工具呼叫審批（auto/yolo/manual） |

### 關鍵特性

- **Plan Mode**: EnterPlanMode → 探索→寫 plan → ExitPlanMode 審批
- **WolfPack**: 批量平行 spawn 子 agent（coder/explore/verify/reviewer...）
- **Aris Integration**: `scream -m laap/laap-core` 讓 Aris 以完整 agent 模式運行
- **aris-mode**: `/am` toggle 快速切換，自動走 agent 迴圈
- **Skills**: 95+ 已安裝，涵蓋運動/工程/搜尋/影音/創意
- **MCP**: 已註冊 chrome-devtools + laap-brain + peekaboo
- **Dist 補丁**: `patch-scream-aris-stream.py` + `patch-scream-aris-agent.py` + `patch-scream-tui.py`（⚠️ 架構級風險，見 §7）

---

## 4. AgentOS — 工具路由層

**位置**: 分散在 `~/.agentos/` + `~/.agents/` + `~/.scream-code/`  
**職責**: 工具發現、路由、安全閘、審計

### 核心機制

| 機制 | 說明 |
|------|------|
| Tool Registry | 本機工具自動偵測（MCP / builtin / skills） |
| Safety Gate | Phase 4a 內容掃描 + Phase 4b 批准閘 + DENY 審計 |
| Executor | 42 executors（web-search / qmd / file-search / 38 AgentOS skills） |
| Skill Router | 95+ skills 按 scope 合併（Project > User > Extra > Built-in） |

### 關鍵特性

- **唯讀白名單**: gbrain / qmd / file-search / web-search 自動放行
- **寫入閘**: 未批准工具排入 `approvals-pending.jsonl`，`approve-tool.sh` 即時生效
- **審計**: 所有工具呼叫記錄到 `safety-audit.jsonl` / `constitution-audit.jsonl`
- **跨 session 持久**: session 資料存在 `~/.scream-code/sessions/`，可恢復

---

## 5. 資料流

### 完整請求生命週期

```
使用者輸入
  │
  ▼
Scream TUI InputController
  │ sendNormalUserInput()
  ▼
Scream Agent Loop (TurnManager)
  │ 1. 建 messages (system + history + user)
  │ 2. 呼叫 LLM API (function-calling)
  │ 3. 工具迴圈 → Read/Write/Bash/Agent...
  │ 4. 結果回 LLM → 繼續或 finish
  ▼
LLM Provider (OpenAI-compatible)
  │ POST /v1/chat/completions
  ▼
neuralis API (:11546)
  │ chatflow._tool_chat() / _normal_chat()
  │ 1. psi feed（每請求餵 PsiCore）
  │ 2. 工具卸載到 executor (125s timeout)
  │ 3. 結果→情緒事件 (task_success/failure)
  ▼
AgentOS Tool Executor
  │ safety_gate.check() → readonly/write/deny
  │ 執行結果回 chatflow → streaming 回 Scream
  ▼
Scream TUI StreamingUI
  │ onStreamingTextStart/Update/End
  │ live transcript 渲染
  ▼
使用者看到回應
```

### 背景迴路（無需使用者輸入）

```
AgencyLoop (每 60s)
  │ psi.get_drives() → 超閾值? → _form_intent() → _act()
  │ web-search / gbrain / frontiermap → 記憶回寫
  ▼
ConsolidationLoop (每 30min)
  │ arousal 低 + 閒置 → 記憶去重/升層/歸檔
  ▼
PsiCore heartbeat (每 1s)
  │ 需求衰減 + 雜訊 + 情緒平滑更新
```

---

## 6. 現狀定位

### 與外部生態的關係

| 維度 | 本系統 | 外部對照 |
|------|--------|---------|
| Agent 框架 | Scream Agent Loop (自研) | AutoGen / ADK / CrewAI / LangGraph |
| 認知架構 | PsiCore (PSI 理論實作) | MicroPsi (同理論源頭) / SOAR / ACT-R |

> **與 MicroPsi 的差異**：MicroPsi 等是研究沙盒（模擬環境、單 process）。本系統把 PSI 情緒梯度場 7/24 接進活的工具呼叫閉環 + 真記憶（gbrain 1894 頁）+ 人類協作產線（Scream TUI）。PSI 理論從研究原型→生產 agent 的第一個已知落地（2026-07-17）。
| 記憶系統 | gbrain hybrid search | Mem0 / RAG /向量資料庫 |
| TUI | pi-tui (自研) | Claude Code TUI / Codex CLI |
| 安全閘 | Phase 4a/4b | OWASP / 自訂審批流程 |
| 技能生態 | 95+ 技能, SKILL.md 格式 | Composio / Hyperagent |

### 獨特定位

1. **情緒與需求閉入決策迴路** — PsiCore 的 exploration_rate 被情緒梯度場調變（valence/arousal 影響 exploration vs exploitation 權衡），agency 的 angle_weights 隨 RPE 更新。情緒不是 system prompt 裡的裝飾文字，是 7/24 跑在決策管線裡的數值。
2. **工具呼叫閉環** — 從 agency (自主) → chatflow (API) → safety gate (安全) → executor (執行) → affective (情緒回饋) → gbrain (記憶)，全鏈路閉合
3. **雙通道互動** — 人類可透過 Scream Code TUI 協作，也可讓 Aris 自主行動（agency），兩條路徑共享同一套記憶和情緒
4. **dist 補丁** — Scream Code 上游更新後，透過補丁腳本重建整合（aris-stream / aris-agent / tui）。⚠️ 這是已知架構級風險，詳見 §7。

### 已知差距

- **無真推理層** — Phase 3 psilang 戰略性不做，依賴底層 LLM
- **無 RSI** — Phase 4c 戰略性不做
- **agency 意圖是規則表** — 非認知，天花板明顯

### 路線圖

```
Phase 6 (當前): 產品向 — 行為豐富度 + 情緒校準 + 養成
  → 當前階段: 上游 PR（TUI 狀態列 hook + agent 迴圈 plugin 接口），
              解除 dist 補丁依賴（在流沙上蓋樓前先打地基）
下一階段: 跨三層協作體驗打磨（aris-mode 流程優化、審批面板鍵盤流）
```

---

## 7. 架構級風險

### dist 補丁 — Layer 1 地基裂縫
Scream Code（Layer 1）的 Aris 整合依賴三支手改 `dist/*.mjs` 的補丁腳本：
- `patch-scream-aris-stream.py`（aris-mode 流式輸出）
- `patch-scream-aris-agent.py`（agent 迴圈工具呼叫）
- `patch-scream-tui.py`（狀態列顯示）

**這是架構級風險，不是普通的差距**：
1. **不可追溯** — `dist/*.mjs` 是編譯產物，diff 不進版控，無法 review
2. **上游改版即靜默壞** — npm update 後錨點移位 → loud fail，需人工對齊
3. **已有傷疤** — `dist/*.aris-stream-bak` / `*.bak-toolcall` / `*.tui-bak` 散落在 scream-code 安裝目錄

**緩解策略**：短期靠 `node --check` 驗語法 + 冪等腳本（已有）；中期路面 = 上游 PR 將整合邏輯納入官方 plugin 接口，砍掉 dist 補丁。

---

> 最後更新: 2026-07-17 | 對應 scream-code v0.9.7 / neuralis Phase 6