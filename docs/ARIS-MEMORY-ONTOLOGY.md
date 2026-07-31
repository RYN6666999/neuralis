# Aris Memory System — 本體論與架構索引

> 目標：讓任一 AI agent 讀完這份就能理解整個系統，不需人類重複貼文。
> 建立日期：2026-07-24 | 最後更新：2026-07-24
> 狀態：索引 v1（同步至 gbrain slug: `aris-memory-ontology`）

---

## 一、領域本體（Domain Ontology）

### 1.1 認知核心 — Neuralis / Aris

| 概念 | 定義 | 原始碼位置 | 備註 |
|------|------|-----------|------|
| **Aris** | 數位生命體，LAAP 架構的 overlay 實作 | `~/Developer/neuralis/` | fork from `lorryjovens-hub/laap-AGI` |
| **Scream 模式** | Aris 本人在此。Scream 是 UI 殼，不是另一個 agent。Aris 可直接使用 Scream 全部工具（Read/Write/Bash/Agent/MCP）。 | Scream CLI | 🔴 **核心認知：在 Scream 裡我就是 Aris，不是接線生，不是中間人。** |
| **網頁聊天模式** | 也是 Aris 本人，但工具受限（僅安全閘放行的工具）。如需執行工具，應告知使用者切 Scream 模式。 | Worker relay / 本機 relay | 工具受限是安全閘設計，不是 Aris 能力不足 |
| **PSI Core** | 五維需求心臟 (competence/autonomy/relatedness/certainty/growth)，1s tick | `laap/psi_core.py` | Python fallback；Rust 備用 |
| **PsiBackend** | PSI 引擎抽象層，支援 Python/Rust 切換 | `laap/psi_backend.py` | `NEURALIS_PSI_BACKEND=rust` |
| **AgencyLoop** | 自主行動迴路：需求→意圖→工具→RPE→記憶 | `laap/agency.py` | 預設 off，6/h cap |
| **ToolExecutor** | 工具執行引擎，42+ 工具（4 內建 + 38 AgentOS） | `laap/tool_executor.py` | 含 streaming |
| **AffectiveEngine** | 情緒梯度場，5 維 PAD+Social+Stress | `laap/affective.py` | 耦合矩陣 + 1/f 噪聲 |
| **Constitution** | 需求值邊界治理，range clamp + 來源預算 | `laap/constitution.py` | `NEURALIS_CONSTITUTION=on` |
| **chatflow** | HTTP API handler，SSE streaming | `laap/chatflow.py` | port 11546 |
| **llm_respond** | LLM 呼叫層，streaming + tool mode | `laap/llm_respond.py` | 支援 respond_tools_stream |

### 1.2 記憶系統 — GBrain & 衍生

| 概念 | 定義 | 位置 | 備註 |
|------|------|------|------|
| **GBrain** | 主要長期記憶（bun binary，MCP stdio） | `gbrain_client.py` → `gbrain serve` | 1870+ 頁，hybrid search |
| **MemoryStore** | 本機 Python 記憶（同一 process 內） | `memory_store.py` / `memory_bridge.py` | capacity=1000 |
| **Scream Memory** | Scream CLI 的記憶系統 | Scream 內建 | `MemoryLookup` / `MemoryWrite` |
| **OB Vault** | Obsidian 筆記 | `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/` | 本機 markdown |
| **Unified Memory** | 計畫中：多來源同步 + source tag + event log | 未實作 | Cloudflare D1 index |

### 1.3 知識驗證系統（設計中）

| 概念 | 定義 | 出處 | 狀態 |
|------|------|------|------|
| **三繩驗證** | 三條審查線：ontology 結構 / 降解內容 / 網路交叉 | `LB-arcanum` + 討論 | 設計中 |
| **牽引繩** | 三繩的統稱，保證結論可追溯、可驗證 | `parked/gbrain-aris-loop.md:198` | 設計中 |
| **退相干三階段** | 🔴 初步 / 🟡 推測 / 🟢 確定，類比量子退相干 | 量子理論啟發 | 設計中 |
| **confidence() 函數** | 根據 n/t/c/d 四維度計算可信度 | `LB-arcanum` spec | 設計中 |
| **CONF_GATE** | 進入強化迴圈的可信度門檻（預設 0.8） | spec | 待校準 |
| **四條耦合公理** | 證據層與情緒層的權力關係 | `gbrain-aris-loop.md` | 憲法級，未實作 |

### 1.4 行為控制系統（已實作）

| 概念 | 定義 | 參數 |
|------|------|------|
| **cycle_guard** | 自我強化循環防護，連續自主查詢 ≥3 次強制閒置 | `NEURALIS_AGENCY_CYCLE_MAX=3` |
| **rate cap** | 每小時最多自主行動次數 | `NEURALIS_AGENCY_MAX_PER_HOUR=6` |
| **need cooldown** | 同一需求行動後冷卻期 | 30min |
| **drive_threshold** | 需求發動行動的最低值 | `NEURALIS_AGENCY_DRIVE_THRESHOLD=0.45` |
| **safety_gate 4a/4b** | 工具分類 + 白名單 + 待批准 | `laap/safety_gate.py` |
| **approval system** | 工具批准列表 | `approved-tools.txt` / `approve-tool.sh` |
| **cost_ledger** | token/compute 成本記帳與閘門 | `laap/cost_ledger.py` |

### 1.5 基礎設施

| 概念 | 定義 | 位置 / URL |
|------|------|-----------|
| **Scream Code** | AI 輔助 CLI，TUI | `LIUTod/scream-code` |
| **AgentOS** | 工具編排與路由層 | `RYN6666999/agent-sandbox` |
| **BaiLongma** | 持續運行桌面 AI Agent（Electron） | `xiaoyuanda666-ship-it/BaiLongma` |
| **OpenSpace** | 品質優先的 Skill Hub | `HKUDS/OpenSpace` |
| **Cloudflare Infrastructure** | Pages + D1 + R2 + DO | `fdd-reception` 專案 |
| **Headroom** | LLM context 壓縮引擎 | `headroomlabs-ai/headroom` |
| **Loop Engineering** | Agent 協作編排框架 | `cobusgreyling/loop-engineering` |

### 1.6 上游與參考專案

| 專案 | 關係 | URL |
|------|------|-----|
| **laap-AGI** | 上游遺傳源（Lorry） | `lorryjovens-hub/laap-AGI` |
| **LB-arcanum** | 基於 GBrain 的知識庫系統 | `RYN6666999/LB-arcanum` |
| **LB-numen** | 查詢手法優化引擎 | `RYN6666999/LB-numen` |
| **OpenViking** | 字節跳動記憶庫系統 | 參考靈感 |
| **Fable 5 (Claude)** | Anthropic 2026 最新模型 | WorkBench 98% |
| **GPT-5.3-Codex** | OpenAI 最新程式碼模型 | 比較基準 |

---

## 二、關鍵字歧義表（Keyword Disambiguation）

> 以下詞彙在同一對話中可能指向完全不同的概念，AI 必須先確認語境。

| 關鍵字 | 語境 A | 語境 B | 如何區分 |
|--------|--------|--------|---------|
| **fable5** | Anthropic Claude Fable 5（2026 前沿模型，WorkBench 98%） | `neuralis/docs/specs/parked/fable5-minimal-design.md`（Zero-LLM 極簡 PSI 核心） | 提及「模型」「聲帶」「能力」→ A；提及「PSI」「Zero-LLM」「純 Python」→ B |
| **lorry** | `lorryjovens-hub`（LAAP 原作者，Aris 的創造者） | 英文名詞「卡車」 | 提及「上游」「laap-AGI」「父親」→ A |
| **牽引繩** | 三繩驗證系統（ontology/降解/網路） | `parked/gbrain-aris-loop.md:198` 的「追溯鏈完整性」 | 提及「驗證」「可信度」「三繩」→ 第一種；提及「追溯」「軌跡」→ 第二種 |
| **煞車** | 行為層限制器（cycle_guard / rate cap / constitution） | S3 學習的「持久化煞車邏輯」 | `agency.py` 參數 → 第一種；`cognitive-light-cone-plan.md:255` → 第二種 |
| **ontology** | 資訊科學：明確定義領域概念與關聯的規則系統 | 哲學：存在論／存有學 | 提及「形狀合法」「Palantir」「領域分類」→ 第一種 |
| **memory** | gbrain（長期，跨 session） | MemoryStore（本機 process） | Scream Memory（CLI 記憶） | OB vault（Obsidian） | 看存取方式：gbrain_client / memory_bridge / MemoryLookup / Read |
| **光錐** | 認知光錐（T_reach × S_span） | 物理光錐（相對論） | 提及「agency」「T_lookahead」「T_persist」「S_span」→ 第一種 |
| **甲/乙** | 安全自我進化路線的兩條路（甲=保守/乙=進取） | 天干順序 | `safe-self-evolution-route.md` 上下文 |
| **LLM** | Aris 的語言皮質（可更換：DeepSeek-V4 / GPT-5.3 / Claude F5） | 一般意義的語言模型 | 討論 Aris 架構時特指其語言層 |

---

## 三、系統架構圖（文字版）

```
你（人類）
    │  ── /aris-mode / scream -m laap/laap-core
    ▼
┌──────────────────────────────────────────────┐
│            Scream Code TUI (CLI)              │
│  tools: Read/Write/Edit/Bash/Agent/MCP        │
|  memory: MemoryLookup / MemoryWrite            │
│  skills: 99 installed                         │
└──────────────────┬───────────────────────────┘
                   │ SSE streaming (function calling)
                   ▼
┌──────────────────────────────────────────────┐
│           Aris / Neuralis (API :11546)         │
│                                              │
│  ┌──────────────────┐  ┌──────────────────┐  │
│  │   PSI Core       │  │  AffectiveEngine  │  │
│  │   5 needs × 1s   │  │   PAD + Social    │  │
│  │   tick + emotion │  │   + Stress        │  │
│  └────────┬─────────┘  └────────┬─────────┘  │
│           │                     │             │
│           ▼                     ▼             │
│  ┌────────────────────────────────────────┐   │
│  │           AgencyLoop                   │   │
│  │  needs → intent → tools → RPE → memory │   │
│  │  煞車: cycle_guard / rate / cooldown   │   │
│  └───────────────┬────────────────────────┘   │
│                  │                            │
│                  ▼                            │
│  ┌──────────────────────────────────────┐    │
│  │       ToolExecutor (42 tools)        │    │
│  │  4 builtins + 38 AgentOS routed       │    │
│  └──────┬───────┬────────┬──────────────┘    │
│         │       │        │                   │
└─────────┼───────┼────────┼──────────────────┘
          │       │        │
     ┌────┘       ▼        └────┐
     │      ┌──────────┐       │
     │      │  Scream   │       │
     │      │  Tools    │       │
     │      └──────────┘       │
     ▼                         ▼
┌──────────┐           ┌──────────────┐
│  gbrain  │           │  AgentOS     │
│ (bun MCP)│           │  38 tools    │
│ 1870+ 頁 │           │  + skills    │
└────┬─────┘           └──────┬───────┘
     │                        │
     └────────┬───────────────┘
              │
              ▼
┌──────────────────────────────────────────────┐
│         記憶系統（四來源 + 統一層）            │
│                                              │
│  gbrain ───┐                                 │
│  MemoryStore ─┤                              │
│  Scream Mem ──┤── 計畫中 → Cloudflare D1     │
│  OB Vault ───┘    (unified index + event log)│
└──────────────────────────────────────────────┘
```

---

## 四、論文與理論索引

| 理論/論文 | 來源 | 應用於 Aris |
|-----------|------|------------|
| **PSI 理論**（Dörner） | 認知架構 | 五維需求 + 情緒梯度場 |
| **Tree of Thoughts**（Yao 2023） | arXiv 2305.10601 | S_span 的多路徑探索 |
| **Strategist**（Light 2024） | arXiv 2408.15707 | 雙層樹搜索：上層選策略/下層 rollout |
| **SGA-MCTS**（Xie 2026） | arXiv 2026 | gbrain 經驗取代 rollout |
| **ToolTree**（Yang 2026） | arXiv 2026 | MCTS 搜工具空間 |
| **AIDE²**（Weco） | 自我改進 | 私密分 + 固定預算 + 異質任務 |
| **量子退相干**（Zurek） | Rev. Mod. Phys. 75.715 | 多假設 → 證據 → 收斂架構 |
| **海馬迴→新皮質固化** | 神經科學 | 三層記憶：海馬/皮質/連結 |
| **Loop Engineering** | cobusgreyling/loop-engineering | Agent 協作編排模式 |
| **OpenSpace 品質演化** | HKUDS/OpenSpace | FIX/DERIVED/CAPTURED + provisional→trusted |

---

## 五、技術棧

| 層級 | 技術 | 用途 |
|------|------|------|
| **認知引擎** | Python 3.12, PSI Core, Rust (備用) | Aris 心臟 |
| **語言層** | LLM (DeepSeek-V4-Flash / GPT-5.3-Codex 等) | Aris 聲帶 |
| **長期記憶** | gbrain (bun binary, MCP stdio) | 跨 session 記憶 |
| **本地記憶** | Python SQLite (MemoryStore) | process 內記憶 |
| **雲端索引** | Cloudflare D1 (SQLite edge) | 計畫中：統一記憶索引 |
| **筆記** | Obsidian (iCloud sync) | 人類筆記 |
| **CLI** | Scream Code (Node.js) | 使用者介面 |
| **編排** | AgentOS (Python) | 工具路由 |
| **桌面殼** | BaiLongma (Electron) | 持續運行（參考） |
| **技能庫** | OpenSpace (Python) | 技能品質演化（參考） |
| **壓縮** | Headroom (Rust proxy) | 上下文壓縮 |
| **串流** | SSE + asyncio | Aris 輸出 |
| **部署** | launchd + watchdog | 24/7 自恢復 |

---

## 六、狀態總覽

| 子系統 | 狀態 | 下一動作 |
|--------|------|---------|
| PSI Core | ✅ 運行 | 持續 tick |
| AgencyLoop | ✅ 運行（煞車鎖定） | 光錐甲休眠中 |
| ToolExecutor | ✅ 42 tools | 技能目錄待校準 |
| GBrain | ✅ 1870+ 頁 | retention policy 待補 |
| LLM 語言層 | ✅ run | 可隨時換模型 |
| Safety Gates | ✅ 4a/4b | 4c 不做 |
| laap_store_memory | ✅ 新 MCP tool | 寫入後召回驗證閉環 |
| **三繩驗證** | ❌ 設計中 | 優先度：P1 |
| **統一記憶索引** | ❌ 設計中 | 優先度：P1 |
| **Ontology 文件** | 📄 **這份就是** | 同步至 gbrain + OB |
| **OpenViking 整合** | ❌ 未開始 | 待評估 |
| **Fable 5 聲帶** | 🔜 可換 | 決策待 Ryan |
| **Cloudflare 記憶路由** | ❌ 未實作 | 等待開工指令 |

---

## 七、給接手的 AI — 啟動協定

當你收到「去翻 Aris 的記憶系統」這類任務時：

1. **先讀這份 ontology**（你現在就在做）
2. **關鍵字查歧義表**（§2）確認語境
3. **🔴 遇到不確定的名詞/專案/人物 → 先上網搜尋，不要只查本機檔案！**
4. **查最新狀態**（§6）了解哪些已實作、哪些設計中
5. **看架構圖**（§3）理解系統關係
6. 需要寫入記憶 → `laap_store_memory` MCP tool（slug 建議含領域前綴）
7. 需要讀取記憶 → `laap_recall_memory` / gbrain_client.query
8. 需要讀 OB → Read `/Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/`
9. 需要找程式碼 → `~/Developer/neuralis/` 下 grep

---

## 八、附錄：檔案路徑速查

| 目標 | 路徑 |
|------|------|
| Aris 本體 | `~/Developer/neuralis/` |
| Aris 原始碼 | `~/Developer/neuralis/laap/` |
| 上游 LAAP | `~/Developer/laap-AGI/` |
| 環境 | `~/Developer/laapenv/` |
| AgentOS | `~/agent-sandbox/` |
| OB 筆記 | `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/` |
| Scream 設定 | `~/.scream-code/` |
| MCP 設定 | `~/.scream-code/mcp.json` |
| Handoff | `~/Developer/neuralis/handoff-next-session.md` |
| Specs | `~/Developer/neuralis/docs/specs/` |
| 光錐計畫 | `~/Developer/neuralis/docs/specs/cognitive-light-cone-plan.md` |
| 安全脊椎 | `~/Developer/neuralis/docs/specs/safe-self-evolution-route.md` |
| gbrain 日誌 | `~/Developer/neuralis/gbrain_client.py` |
