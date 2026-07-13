# LAAP 生態系與理論基礎研究報告

> 目標：最大化借力，找出我們可以直接用、可以學、可以避免重複造輪子的所有資源
> 研究日期：2026-07-14
> 研究範圍：PyPI、GitHub、作者論文、學術理論

---

## 1. 核心發現：LAAP 不是一個專案，是一個生態系

### 我們本以為的

我們以為 LAAP 就是 `lorryjovens-hub/laap-AGI` 這個 GitHub repo——一個 34 stars 的零 LLM 認知引擎。

### 實際上的 LAAP 生態系

作者 Lorry (黄俊华) 在過去一年建立了完整的生態系：

```
LAAP Ecosystem (作者 lorryjovens-hub, 30+ repos)
│
├── laap-AGI (GitHub)              ← 我們正在用的開源認知引擎
│   ├── Python 認知引擎 (25+ 模組)
│   ├── Rust PSI Core (2000Hz)
│   └── 三框架整合 (Hermes/OpenClaw/OpenCode)
│
├── laap (PyPI v0.3.2, 694KB)     ← 完整工業級版本 ⭐
│   ├── PSI 認知引擎 (完整實作)
│   ├── RSI 遞迴自我改進 (Darwin-Gödel Machine)
│   ├── 數位生命體系統 (生理/自我意識/人格)
│   ├── 五層階層記憶 (工作→情景→語義→程序→向量)
│   ├── LLMFactory (27 個提供商)
│   ├── 14 平台通訊閘道
│   ├── Web Dashboard (FastAPI)
│   ├── Hermes 金龍 TUI
│   ├── Swarm 多 Agent 編排
│   ├── MCP 協議支援
│   ├── Rust PyO3 加速
│   └── 21 內建工具 + 五級權限
│
├── claude-code-rust (1,666 stars) ← Rust 重寫的 Claude Code CLI
│   └── 2.5x 更快啟動，97% 更小體積
│
├── hermes-agent                   ← Hermes Agent 框架
│
├── Chat2API                       ← 多模型統一出入口
│
├── 影視生產工具鏈                  ← Seedance 2.0 整合
│   ├── FrameCraft-Pro (21 stars)
│   └── AI 影視生產平台
│
├── 開源貢獻
│   ├── llama.cpp (C/C++)
│   ├── oh-my-codex (Rust)
│   ├── crawl4ai (Python, llm crawler)
│   └── MOSS-Audio (語音理解)
│
└── 其他基礎設施
    ├── computer-use (雲端桌面 Agent)
    ├── xiaozhi-esp32 (IoT 語音)
    └── FinceptTerminal (金融數據)
```

---

## 2. 理論基礎：作者引用的學術根源

### 2.1 PSI 理論 (Dörner, 1999)

**引用來源:** PyPI 文檔明確寫著「完整實現了 Dörner 的 PSI 認知理論」

**原始論文:** Dörner, D. (1999). *Bauplan für eine Seele* (Blueprint for a Soul)

**核心內容:**
- 人類認知不是「輸入→處理→輸出」的資訊處理模型
- 認知是由**內在需求**驅動的——不是由外部指令
- 五大需求：確定性、能力感、自主性、關聯性、能量
- 需求不平衡 → 情緒 → 行為選擇 → 學習 → 更新需求

**影響:**
LAAP 的五維需求（competence/autonomy/relatedness/certainty/growth）直接來自 PSI 理論。我們的 `NeedState` 資料類別就是這個理論的實作。

### 2.2 Self-Determination Theory (SDT) — Deci & Ryan, 2000

**引用來源:** PSI 需求的擴展，三基本需求理論

**核心內容:**
- 自主性 (Autonomy)
- 勝任感 (Competence)
- 關聯性 (Relatedness)

**與 PSI 的關係:**
LAAP 把 SDT 的三需求 + PSI 的確定性 + 能量 = 五維需求

### 2.3 Darwin-Gödel Machine (RSI 遞迴自我改進)

**引用來源:** PyPI 文檔: 「實現了 Darwin-Gödel Machine」

**核心概念:**
- **Darwin 部分:** 變異 + 選擇 = 演化
- **Gödel 部分:** 系統可以在自身之上進行元推理
- 結合：Agent 可以觀察自己的程式碼 → 提出改進 → 沙盒測試 → 評估 → 採納/拒絕

**LAAP 的實作模式:**
```
觀察 → 提案 → 沙盒測試 → 評估 → 採納/拒絕
  ↑                                    │
  └────────── 循環迭代 ────────────────┘
```

### 2.4 Prigogine 的耗散結構理論 (1977)

**引用來源:** PyPI 文檔: 「基於普利高津耗散結構理論」

**核心內容:**
- 開放系統可以從混沌中自發產生秩序
- 生命是遠離平衡態的耗散結構
- 能量流動驅動自組織

**與 LAAP 的關係:**
PSI 需求系統就是一個耗散結構——能量輸入（對話）驅動需求動力學，產生有序的認知行為。

### 2.5 複雜系統湧現

**引用來源:** PyPI 文檔: 「複雜系統湧現原理」

**核心內容:**
- 簡單規則的組合可以產生複雜行為
- LAAP 的 25+ 引擎各自簡單，但組合在一起產生「生命感」

### 2.6 EG-MRSI（情緒梯度 RSI）

**引用來源:** PyPI 文檔獨有

**核心內容:**
- 情緒不是狀態（happy=true），而是**梯度場**
- valence = 需求變化量 × α + 喚醒度 × β
- emotion = f(valence, arousal, dominance, confidence)
- 情緒從需求滿足率的變化率自然湧現

---

## 3. PyPI 版 vs laap-AGI 版 vs neuralis 版

### 三版對比

| 維度 | laap-AGI (GitHub) | laap (PyPI v0.3.2) | neuralis (我們的) |
|------|------------------|-------------------|-----------------|
| 發布日期 | 2026-07 | 2026-06-10 | 2026-07-13 |
| 定位 | 開源認知引擎 | 完整 Agent 框架 | 擴充 overlay |
| PSI Core | ⚠️ 缺 Rust 二進位 | ✅ 完整實作 | 🏗️ 計畫中 |
| RSI 自我改進 | ❌ 無 | ✅ Darwin-Gödel Machine | ❌ 無 |
| 五層記憶 | ✅ 三層現有 | ✅ 完整五層 | ⚠️ stub |
| 情緒系統 | ✅ 七情六欲 | ✅ 梯度系統 | ❌ 無 |
| 人格系統 | ✅ 五維 + 依戀 | ✅ 五因素 | ❌ 無 |
| LLM 整合 | ❌ 無 | ✅ 27 提供商 | ❌ 無 |
| 閘道層 | ❌ 無 | ✅ 14 平台 | ❌ 無 |
| 工具系統 | ❌ 無 | ✅ 21 內建工具 | ❌ 無 |
| Swarm 多 Agent | ❌ 無 | ✅ 有 | ❌ 無 |
| Rust 加速 | ⚠️ 承諾但缺 | ✅ PyO3 | ❌ 無 |
| TUI/Web 介面 | ❌ 無 | ✅ 金龍 TUI + Dashboard | ❌ 無 |
| 安裝方式 | git clone | pip install laap | git clone |
| 授權 | Apache 2.0 | MIT | MIT |
| 發布頻率 | 一次 | 持續更新 (v0.3.2) | 起步階段 |

### 關鍵洞察

**laap-AGI 是「大腦」，laap (PyPI) 是「完整生命體」。**

作者把認知引擎（開源在 laap-AGI）和完整框架（PyPI 版）分開了。這解釋了為什麼 laap-AGI 缺少那麼多模組——更完整的都在 PyPI 版裡。

---

## 4. 最大化借力策略

### 4.1 可以直接用的（不需要自己寫）

| 資源 | 來源 | 用法 |
|------|------|------|
| laap-AGI 的 12 個 Python 引擎 | `aris_brain/` | RulesEngine, EmotionEngine, 記憶, 人格, 儀式等 |
| Harness 論文 | `references/` | 理論基礎與架構哲學 |
| 整合指南 | `references/agent-integration-guide.md` | 框架接入方式 |
| PyPI laap 套件 | `pip install laap` | 完整框架參考實作 |

### 4.2 可以學的（研究設計模式，不複製程式碼）

| 概念 | 來源 | 為什麼重要 |
|------|------|-----------|
| Darwin-Gödel Machine | PyPI RSI 引擎 | Agent 自我改進的閉環模式 |
| 情緒梯度場 | PyPI 情緒引擎 | 情緒從需求微分自然湧現，不是硬編碼 |
| 五層記憶分層 | PyPI 記憶引擎 | 工作→情景→語義→程序→向量 |
| 14 平台閘道模式 | PyPI 閘道層 | 多平台統一接入 |
| 耗散結構認知 | Prigogine 理論 | 需求動力學的數學基礎 |

### 4.3 不需要做的（已經存在，直接用）

| 不要做 | 原因 |
|--------|------|
| 不要重寫情緒引擎 | laap-AGI 已有完整 `aris_emotion_engine.py` |
| 不要重寫記憶系統 | laap-AGI 三層記憶 + PyPI 五層參考 |
| 不要重寫人格系統 | laap-AGI 五維 + 依戀完全可用 |
| 不要重寫規則引擎 | laap-AGI 的 7×7 RulesEngine 完整 |
| 不要重寫儀式/覺醒 | laap-AGI 的 Ceremony + Bootstrap 完整 |
| 不要做 LLM Factory | PyPI 已經有 27 提供商整合 |
| 不要做平台閘道 | PyPI 已經有 14 平台 |
| 不要做工具系統 | PyPI 已經有 21 內建工具 |

### 4.4 應該做的（我們的獨特價值）

| 該做 | 原因 |
|------|------|
| **Python PSI Core** | 作者的是 Rust 版，我們需要純 Python 心臟 |
| **AGI stub 升級** | Causal/WorldModel/Analogical 作者說有但不在 repo |
| **neuralis 作為 overlay 層** | 讓我們的擴充與作者生態共存 |
| **fable5 專屬擴充** | 作者沒有的功能我們補上 |

---

## 5. 三條路線選擇

### 路線 A: 直接使用 PyPI 版 laap

**做法:** `pip install laap`，直接使用完整框架

**優點:**
- 694KB 完整套件，開箱即用
- 27 LLM 提供商 + 14 平台閘道
- RSI 自我改進 + 五層記憶
- 作者持續維護更新

**缺點:**
- 依賴作者的生態系
- 客製化空間較小
- 需要學習 PyPI 版的 API 設計

**適合場景:** fable5 需要最快獲得完整認知架構

### 路線 B: 繼續疊加 neuralis

**做法:** 維持現狀，neuralis 疊在 laap-AGI 上

**優點:**
- 完全自主控制
- MIT 授權，可獨立演化
- 不需要理解 PyPI 版的複雜 API

**缺點:**
- 需要更多實作工作
- 沒有 RSI、多平台、Swarm 等高階功能

**適合場景:** fable5 需要高度客製化

### 路線 C: 混合策略（推薦）

```
Layer 1: laap-AGI 的 12+ 現有引擎 (直接使用，不改)
Layer 2: neuralis overlay (我們維護，逐步擴充)
Layer 3: 參考 PyPI 版的設計模式 (不複製程式碼)
```

**做法:**
1. 繼續用 laap-AGI 的 Python 引擎模組
2. neuralis 補 Python PSI Core + AGI stub
3. 研究 PyPI 版的 RSI/情緒梯度/五層記憶設計
4. 把學到的設計模式用 neuralis 實作

**優點:** 三層各自獨立，靈活度最高
**缺點:** 需要理解三個層次的設計

---

## 6. 關鍵資源索引

### 可直接讀取的檔案（在 laap-AGI repo 中）

| 文件 | 路徑 | 內容 |
|------|------|------|
| Harness 論文 | `references/Harness-Consciousness-Engineering.md` | 完整架構哲學 (436 行) |
| 英文版論文 | `references/Harness-Consciousness-Engineering.en.md` | 同上，英文 |
| Hermes 提案信 | `references/TO-HERMES-TEAM.md` | 作者給 Hermes 團隊的信 |
| 整合指南 | `references/agent-integration-guide.md` | 三框架接入方式 |
| 作者 README | `README.md` | 專案總覽與架構圖 |

### 需要網路存取的資源

| 資源 | URL | 內容 |
|------|-----|------|
| LAAP 官網 | https://laap-agi.netlify.app | 文檔 (React SPA) |
| PyPI 套件 | https://pypi.org/project/laap/ | laap v0.3.2 (694KB) |
| 作者 GitHub | https://github.com/lorryjovens-hub | 30+ repos |
| laap-AGI repo | https://github.com/lorryjovens-hub/laap-AGI | 開源認知引擎 |
| claude-code-rust | https://github.com/lorryjovens-hub/claude-code-rust | 1.6k stars |
| libraries.io | https://libraries.io/pypi/laap | 套件依賴分析 |

### 學術理論

| 理論 | 原始文獻 | LAAP 中的應用 |
|------|---------|-------------|
| PSI Theory | Dörner (1999). *Bauplan für eine Seele* | 五維需求驅動 |
| SDT | Deci & Ryan (2000). *Self-Determination Theory* | 三基本需求 |
| Darwin-Gödel Machine | Schmidhuber (2006). *Gödel machines* | RSI 遞迴改進 |
| 耗散結構 | Prigogine (1977, Nobel) | 需求動力學 |
| 複雜系統湧現 | Holland (1998). *Emergence* | 多引擎組合 |

---

## 7. 結論

### 我們最大的機會

作者已經完成了**最難的部分**——25+ 認知引擎模組、PSI 理論實作、RSI 引擎、完整框架。這些都在 PyPI 版裡 (`pip install laap`)。

我們不需要從零開始。我們需要的是：

1. **理解**作者做了什麼（這份報告）
2. **選擇**哪些直接用（laap-AGI 的 12 個模組）
3. **補上**作者沒給的（Python PSI Core、AGI stub 升級）
4. **參考** PyPI 版的設計模式但不複製

### 最關鍵的決定

要不要直接 `pip install laap` 用 PyPI 版？

如果答案是**要**，那 neuralis 的角色就變成「laap 的配置層 + 擴充層」，而不是「laap-AGI 的補丁層」。這會大幅改變路線圖。

如果答案是**不要**，那我們繼續走現在的路——疊加 neuralis 在 laap-AGI 之上，逐步補實 Python PSI Core 和 AGI stub。

### 無論如何，下一步是

研究 PyPI 版的 `laap/cognition/needs.py` 和 `laap/rsi/engine.py`——這兩個檔案是作者最成熟的心血，值得深入理解。

---

*研究基於公開資料：PyPI、GitHub、作者論文、libraries.io*
*產生於 2026-07-14*