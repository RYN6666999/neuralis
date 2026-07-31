# 第一部：定位與原則

> 對應章節：Ch 0～3
> 撰寫狀態：✅ 已完成（2026-07-18）
> 參考來源：
> - **上游 repo**：`lorryjovens-hub/laap-AGI`（branch `feat/env-config-hermes`）— Lorry 的純認知架構
> - **本地 repo**：`RYN6666999/neuralis`（branch `main`）— Ryan 的 overlay，含安全閘、agency、Scream 整合
> - 既有 spec：`safe-self-evolution-route.md`, `parked/core-architecture.md`, `cognitive-light-cone-plan.md`
> - 實際讀碼：`safety_gate.py`, `agency.py`, `constitution.py`, `cost_ledger.py`, `snapshot.py`, `laap/agi/*.py`

---

## 0. 文件摘要

### 0.1 系統要解決的問題

Neuralis（Ryan 的 overlay）已具備完整的自主迴路（Phase 6 AgencyLoop）和安全閘系統（Phase 4a/4b SafetyGate + path-DENY）。Aris 能在沙箱內執行唯讀工具、評估結果、並寫回 gbrain 記憶。

但目前的自主改進能力是**零**。Agency 只能操作白名單內的唯讀工具（gbrain/qmd/file-search/scream-ask/web-search），無法修改程式碼、無法配置、無法部署。

上游 repo（lorryjovens-hub/laap-AGI）的 `laap_integrator.py` 確實提到了自我進化模組（`self_evolve.py`, `rsi_engine.py`, `code_evolution.py`），但這些檔案在 disk 上**不存在**——它們是架構規劃中的佔位，不是真實實作。neuralis 的 `laap/agi/code_evolution.py` 和 `laap/evolution/rsi.py` 也是 stub（僅 class 骨架，無實質邏輯）。

下一個階段的問題是：**如何安全地讓 Aris 在隔離環境中試驗改進，學習判斷什麼值得做，並讓 Ryan 成為唯一正式升級批准者？**

### 0.2 最終運作方式

```
Aris 發現問題
  → 建立改進假設與預測
  → Scream 在沙箱 Git worktree 中實作
  → 客觀測試系統產生證據
  → Aris 做四面向決策分析（好處/壞處/風險/代價）
  → 必要時外部 AI 提供第二意見
  → Ryan 決定是否落地
  → 真實結果回饋
  → 形成學習案例
  → 校準判斷策略
```

### 0.3 三條主線

| 主線 | 名稱 | 核心問題 |
|------|------|---------|
| 安全試驗線 | Sandbox | 如何在不碰正式環境的前提下進行真實試驗？ |
| 決策學習線 | Learning | Aris 如何從每次建議的真實結果中學習判斷？ |
| 人類治理線 | Governance | Ryan 如何以最低負擔做出最佳決策？ |

### 0.4 一句話原則：自主試驗、證據學習、人工升級

改進在沙箱內自主試驗，決策由客觀證據驅動，正式的程式碼落地**永遠由 Ryan 批准**。Aris 可以學到「建議什麼、為什麼建議」，但不能學到「直接改寫生產環境」。

### 0.5 目前 Neuralis 狀態（讀碼確認，2026-07-18）

#### 上游（lorryjovens-hub/laap-AGI）

Pure cognitive architecture，無安全/自主/學習系統：
- `aris_brain/aris_cognitive_bridge.py`（71KB）— PSI 認知循環 ↔ Hermes 運行時橋接
- `aris_brain/aris_rules_engine.py`（43KB）— Zero-LLM 任務排程
- `aris_brain/aris_emotion_engine.py`（39KB）— 情緒引擎
- `aris_brain/aris_goal_engine.py`（39KB）— 目標引擎
- `aris_brain/aris_lm_v5.py`（76KB）— NLP 管線
- `aris_brain/laap_integrator.py`（60KB）— 全棧認知集成中樞
- `aris_brain/laap_sync_server.py`（35KB）— 同步服務器
- `laap_brain/api.py` — API 伺服器，port 11546
- 整合對象：Hermes Agent（`hermes-agent` pip 套件）
- **無** safety_gate、agency、constitution、cost_ledger、snapshot

#### 本地（RYN6666999/neuralis）

Ryan 的 overlay，在上游之上新增了完整的安全與自主層：

**已到位（安全與治理）：**
- **SafetyGate 4a/4b**（`laap/safety_gate.py`, 193 行）：三層閘 — 委派 path-DENY（Scream 永不得改 Aris 腦）→ 工具分級（唯讀安全組 AGENTOS_READONLY + READONLY_SAFE）→ 內容掃描（AgentOS check_command / 內建 fallback）。`scream-task` 已重分類為 write，`scream-ask` 留唯讀。每次 DENY 寫審計。
- **AgencyLoop**（`laap/agency.py`, 718 行）：閉合「需求→行動→結果→記憶」。煞車：唯讀白名單、6/h cap、每需求 30min cooldown、審計。RPE v0.1-v0.3 含持久化、神經調節物質、下游效用信號。
- **Constitution**（`laap/constitution.py`）：需求值變化的硬邊界、單次 delta 上限、小時預算、超預算凍結。
- **Cost Ledger**（`laap/cost_ledger.py`）：agency 算力預算 ledger（E2 Stage 2）。
- **Snapshot**（`laap/snapshot.py`）：commit 級快照機制。

**已到位（認知核心）：**
- **PsiCore**（`laap/psi_core.py`, 19663 行）：五維需求 + 情緒梯度場 + 1s tick 心跳。
- **ToolExecutor**（`laap/tool_executor.py`）：42 工具（4 內建 + 38 AgentOS），含交錯串流。
- **Scream–Aris 對話迴路**：`scream-ask` 工具 + 頻道 JSONL + 30s polling。
- **深度整合 T1-T5**：情緒事件、MCP、工具分類 API、agency AgentOS 路由、工具呼叫協議。

**Stub 級（僅骨架，無實質邏輯）：**
- `laap/agi/code_evolution.py` — 程式碼自我演化（stub，`evolve()` 直接 return 原碼）
- `laap/agi/rsi_engine.py` — 遞迴自我改良（stub，`propose_improvements()` 回傳空列表）
- `laap/evolution/rsi.py` — 同上（stub，接受 kwargs 但無實作）
- `laap/agi/self_healing.py` — 自我修復（stub）
- `laap/agi/world_model.py` — 世界模型（dict-based，非真 causal）
- `laap/agi/causal.py` — 因果推理（dict-based 替身）
- `laap/agi/analogical.py` — 類比推理（dict-based 替身）

**已定義但未完全到位（`docs/specs/safe-self-evolution-route.md`）：**
- **Stage 0**：path-DENY ✅ / 重分類 scream-task → write ✅ / commit 快照 ✅（但尚未整合進自動委派流程）
- **Stage 1**：E1 下游效用信號 ✅（commit 017a914）/ 評分權物理隔離未到位
- **Stage 2**：E2 成本 ledger ✅（commit f364bb4）
- **Stage 3**：委派通道 — `scream-task-executor` 仍是 v0 stub（模擬執行）
- **Stage 4**：C-a gbrain 快取當規劃器 ✅（commit ab0c71e）/ C-b cache-miss 委派 Scream 前瞻 ✅（commit ae95095，預設休眠）

### 0.6 本文件範圍與非目標

**範圍**：定義 Aris 如何在沙箱中試驗改進、從結果中學習判斷、以及 Ryan 如何治理這個過程。

**非目標**：
- 不是實作 RSI（Recursive Self-Improvement）— 上游的 `rsi_engine.py` 和 neuralis 的 `laap/evolution/rsi.py` 都是 stub，本系統不直接實作 RSI。如有需要走 Stage 5 人類專屬鑰匙
- 不是替換 agency/safety_gate 現有系統 — 本系統建立在其之上
- 不是承諾 Aris 能自主寫 code — 實作角色是 Scream（沙箱內）與 Ryan（正式落地）
- 不是實作上游的 `laap/agi/` 模組 — 那些 stubs 的實作是另一條線
- 不是承諾學習收斂 — 學習可能永遠無法產生「足夠好」的決策策略

---

## 1. 背景與問題

### 1.1 Neuralis「甲」完成狀態

「甲」= Aris 能自主運作但永遠不可修改自己的認知碼。目前狀態：

- ✅ 自主行動（AgencyLoop）：唯讀查詢、記憶檢索、結果寫入
- ✅ 安全閘（SafetyGate）：path-DENY、工具分級、內容掃描
- ✅ 需求憲法（Constitution）：硬邊界、預算、凍結
- ✅ 成本帳本（Cost Ledger）：算力預算追踪
- ✅ 快照（Snapshot）：commit 級還原點
- ✅ Scream 整合：工具呼叫、SSE 串流、aris-mode
- ✅ 深度整合 T1-T5：情緒事件、MCP、工具分類 API、agency AgentOS 路由
- ⬜ **沙箱試驗**：本文件要定義的
- ⬜ **自主學習**：本文件要定義的

### 1.2 為什麼不能直接開啟自主委派

直接讓 Aris 委派 Scream 改寫正式環境是「乙門」的行為。現有危險：

1. **Aris 的判斷目前是規則表，不是認知**（agency.py line 2-3 誠實標註）。基於規則表的「意圖形成」加上寫入權限 = 未經訓練的學生拿手術刀。
2. **Scream 寫入無審批模式存在**（handoff T4 安全發現）：`scream -p` 非互動模式直接放行寫入，沒有審批面板。如果 Aris 能裸走 `-p`，正式環境的 4b 批准閘形同虛設。
3. **學習需要客觀訊號**：在沒有「這個改進真的有用」的客觀驗收標準前，讓 Aris 自主委派只會學到刷分數。

### 1.3 `approved-tools` 狀態污染事故

（來源：`handoff-next-session.md` 實際記錄）

在 Phase 4b 批准閘的實作中，`approve-tool.sh` 使用 `approved-tools.txt` 管理批准狀態。踩坑包括：
- 非 UTF-8 locale 下 `$VAR` 緊接全形字被吞進變數名（`set -u` 報 unbound）
- `grep -v` 全刪光回 exit 1 不能進 `&&` 鏈
- 批准狀態持久在檔案系統，**不是僅僅靠環境變數**——但這個機制沒有被納入正式的沙箱隔離管理

**教訓**：任何持久化的能力開關都必須走正式的 Capability Manifest，不能靠散落的 `.txt` 檔被意外修改。

### 1.4 `git checkout` 遺失修改事故

（來源：`handoff-next-session.md` 實際記錄）

前一手的開發曾在錯誤分支（`task-007b-psi-borrowing-analysis`）工作，看到 `rust/` 只有 `target/` 就宣稱「rust 源碼不在 repo」——但實際上 Rust PsiEngine v2 一直好好地在 `task-008-rust-psi-engine` 分支上。

**教訓**：`git branch -a` + `git ls-tree <branch>` 才能看到 repo 全貌。單一分支的 `ls` 是盲人摸象。沙箱系統必須保留完整的分支與提交資訊，不能只看工作目錄。

### 1.5 兩開關機制的限制

現有安全開關系統依賴環境變數：
- `NEURALIS_AGENCY=off` — 關閉自主行動
- `NEURALIS_DELEGATION_TOOLS_EXTRA` — 擴充委派工具集
- `NEURALIS_TOOL_ALLOW` — 人工批准工具簽名
- `NEURALIS_CONSTITUTION=off` — 全放行需求憲法

限制：
- 環境變數是全局的 — 沙箱環境和正式環境共用同一套
- 沒有「沙箱內可以，正式環境不行」的精細度
- 環境變數無法審計誰在何時改了什麼
- 正式升級不應該由 env 自動決定（但 SafetyGate 的行為確實受 env 影響）

### 1.6 為什麼導入沙箱

沙箱解決：
1. **隔離風險**：改動在隔離的 Git worktree 中進行，正式工作區不受影響
2. **保留證據**：沙箱的測試結果、diff、log 全部保留作為決策證據
3. **可銷毀**：改動不滿意可以直接刪除 worktree，零殘留
4. **平行試驗**：可以同時有多個沙箱探索不同方案

### 1.7 為什麼需要自主學習

學習解決沙箱不能解決的問題：

| 問題 | 沙箱解法 | 學習解法 |
|------|---------|---------|
| 這次改動值得嗎？ | 無（沙箱不判斷價值） | 累積案例後校準 |
| 下次類似情況怎麼選？ | 無（沙箱不判斷） | 從 Ryan 的決策中學習偏好 |
| 我的風險估計準嗎？ | 無（沙箱僅測試） | 比較預測 vs 事故 |
| 何時需要外援？ | 無（沙箱不決定） | 學習信心校準 |

### 1.8 記憶、分析與真正學習的差別

Aris 目前能做到的：
- **記憶**（gbrain）：儲存和檢索資訊
- **分析**（Aris 四面向分析）：對一次改動的好處/壞處/風險/代價做評估

**真正學習**需要的：比較「執行前的預測」與「落地後的結果」，找出系統性的預測誤差，校準未來的判斷。這是 gbrain 做不到的。

### 1.9 沙箱與學習不能解決的問題

- **需求定義錯誤**：如果 Ryan 想要的功能不是 Aris 認為該改進的東西，沙箱和學習都沒有幫助 — 除非 Ryan 明確指定
- **外部 API 變更**：沙箱無法預測上游服務的 breaking change
- **惡意攻擊**：沙箱不防針對性的安全攻擊（那是 SafetyGate 的範圍）
- **學習收斂**：本文件不承諾學習一定會收斂到「足夠好」的決策策略
- **上游模組 stub 實作**：`laap/agi/code_evolution.py` 等 stubs 的實作不是本系統的責任

---

## 2. 核心目標與原則

### 2.1 自主試驗，人工升級

Aris 和 Scream 可以在沙箱中自由試驗。但正式環境的程式碼改動**只能由 Ryan 簽入**。這個原則不可妥協：試驗免費，升級收費（收的是 Ryan 的注意力）。

### 2.2 判斷權、實作權、批准權分離

| 角色 | 權力 | 限制 |
|------|------|------|
| Aris | 判斷「是否該做、哪個方案好」 | 不可實作、不可批准 |
| Scream | 在沙箱內實作方案 | 不可判斷是否值得做、不可批准落地 |
| 外部 AI | 提供第二意見 | 只有參謀權，看不到正式憑證 |
| Ryan | 批准正式落地 | 依賴 Aris 的分析和 Scream 的實作證據 |

這個三權分立是安全核心。任何角色越權都是紅線。

### 2.3 客觀證據優先於 AI 自評

Aris 說「這個改動很好」沒用。測試結果、benchmark 分數、diff 大小、成本變化才是證據。AI 自評只在客觀證據不足時作為輔助參考。

### 2.4 正式環境預設不可寫

沒有 Ryan 明確批准 → 任何工具不能修改正式 Neuralis 工作區。這個預設值寫死在 SafetyGate 的 path-DENY 層，不可被 env 繞過。

### 2.5 最小權限與最小修改

- 沙箱只給完成實驗所需的最小權限（網路、檔案系統、工具）
- 候選方案只改「解決問題所需的最小範圍」
- 測試只跑必要的驗證，不拿 benchmark 刷分

### 2.6 學習判斷，不直接放寬權限

Aris 學到的是「這個類型的改動通常值得做」或者「我對這類風險的估計通常偏高」，而不是「因為我學好了所以現在可以直接寫正式環境」。權限的放寬永遠是 Ryan 的決定。

### 2.7 失敗與回退必須保留

每個失敗都要被記錄、分析、學習。不能因為失敗難看就刪除。回退的原因（技術錯誤/風險太高/成本超支/時機不對）要跟最終決策一樣被保存。

### 2.8 能不做就不做

不是所有發現的問題都需要進沙箱。不是所有進沙箱的方案都需要落地。不做也是一個有效的決策，而且經常是最佳決策。學會判斷「不做」比學會「做什麼」更重要。

### 2.9 學會停止也是學習

如果一個沙箱實驗發現方案不可行，這是一次成功的學習（學到了什麼不可行），不是失敗。停止的條件要在實驗開始前就定義好。

### 2.10 核心安全模組不可自主修改

下列模組永遠不在任何沙箱實驗的候選修改範圍內：
- `SafetyGate`（安全閘判斷邏輯）
- `Constitution`（需求憲法邊界與規則）
- `沙箱邊界強制模組`（確保沙箱本身不被逃逸）
- `人類批准機制`（Ryan 的批准程序）
- `path-DENY 規則`（甲/乙硬防線）

---

## 3. 系統角色與權責

### 3.1 Aris：發現問題與決策分析

能做：
- 分析現有系統行為，找出改進機會
- 產生問題與改進假設（格式見 Chapter 5）
- 對沙箱候選方案執行四面向分析（好處/壞處/風險/代價）
- 當信心不足時決定是否找外部 AI 參謀
- 從每次案例中更新判斷策略

不能做：
- 修改正式環境的任何檔案
- 直接委派 Scream 修改正式工作區（需 Ryan 批准）
- 修改 SafetyGate / Constitution / 沙箱邊界
- 自己批准自己的建議落地

### 3.2 Scream：沙箱內實作

能做：
- 使用 Scream 工具在沙箱 Git worktree 中實作候選方案
- 執行測試與驗證
- 產生候選變更包
- 執行回退操作

不能做：
- 在沙箱外修改 Neuralis 檔案
- 判斷方案是否值得做
- 批准自己的實作落地

### 3.3 Agent Sandbox：隔離、測試、保存證據

能做：
- 提供一次性 Git worktree 隔離工作空間
- 路徑隔離（沙箱目錄外不可寫）
- 正式憑證隔離（不暴露正式 API Key / Token）
- 網路權限限制（可配）
- 執行時間與成本上限（強制停止）
- 殘留檔案檢查（沙箱銷毀前掃描）
- 保存完整測試證據（log、benchmark、diff）

不能做：
- 放寬自己的邊界規則
- 繞過 path-DENY

### 3.4 外部 AI：必要時提供第二意見

能做：
- 在 Aris 信心不足或高風險時收到完整的決策參謀包
- 提供獨立於 Aris 的分析意見
- 被記錄建議與被採用情況

不能做：
- 看到正式憑證、Token、Session（經安全掃描移除）
- 直接影響正式環境（只有參謀權）
- 取代 Ryan 的批准權

### 3.5 Ryan：唯一正式升級批准者

能做：
- 批准或拒絕任何候選方案落地
- 要求修改後再送審
- 要求繼續觀察
- 完全回退已落地的變更
- 指定優先序（哪些問題先處理）
- 決定是否擴大自主程度（Stage 5 乙門）

不能做（系統層面要求）：
- 不應該跳過 A/B 測試或客觀證據（雖然技術上可以，但違背本系統精神）

### 3.6 客觀測試系統：獨立產生證據

客觀測試系統獨立於 Aris 和 Scream：
- 不屬於任何一個 agent 的角色權限
- 只按照給定的測試指令執行
- 輸出原始的 pass/fail 與 benchmark 數據
- 結果不可被 Aris 或 Scream 修改（write-only from test, read-only for others）

### 3.7 學習引擎：比較預測與真實結果

學習引擎是從案例中提取規律的系統：
- 輸入：累積的學習案例
- 輸出：候選判斷策略（好處估計校準、風險估計校準、信心校準等）
- 限制：學習引擎產出的策略需要經過 shadow mode 驗證和 Ryan 批准才能正式生效

### 3.8 各角色能做與不能做的事

| 動作 | Aris | Scream | 外部 AI | Ryan |
|------|------|--------|---------|------|
| 發現問題 | ✅ | ❌ | ❌ | ✅ |
| 提出假設 | ✅ | ❌ | ❌ | ✅ |
| 沙箱實作 | ❌ | ✅ | ❌ | ✅（可自己改） |
| 測試驗證 | ❌ | ✅ | ❌ | ✅ |
| 四面向分析 | ✅ | ❌ | ✅（作為參謀） | ✅ |
| 批准落地 | ❌ | ❌ | ❌ | ✅ |
| 落地實施 | ❌ | ❌ | ❌ | ✅（手動） |
| 回退 | ❌ | ✅（沙箱內） | ❌ | ✅（正式） |
| 更新判斷策略 | ✅（候選） | ❌ | ❌ | ✅（批准後） |

### 3.9 禁止自己出題、自己評分、自己批准

這是三權分立的自然延伸：
- Aris 不能對自己的假設做最終評分
- Aris 不能批准自己的方案落地
- Aris 不能修改評分器來提高自己的分數
- Scream 不能對自己的實作做價值判斷
- 外部 AI 只有參謀權，其意見不能覆蓋 Ryan 的決定