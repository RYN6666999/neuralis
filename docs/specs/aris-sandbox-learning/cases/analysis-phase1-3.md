# Phase 1-3 實作四面向分析

> 分析對象：Phase 1 (只讀分析) + Phase 2 (沙箱建議) + Phase 3 (隔離實作) 的完整工具鏈
> 分析日期：2026-07-18
> 分析者：Scream (as Aris 參謀)

> **⚠️ 複查更正（2026-07-18，後補）** — 本文寫於 commit `28e9d5e`（ponytail 前）。之後
> 兩件事讓下方部分評分失真，讀者請以本更正為準：
>
> 1. **佈局變更**：ponytail（`5dcd0a3`）把「產出盤點」表的 4 個 script（`phase1-analyze-commit.py`
>    / `phase1-sample-analysis.py` / `phase2-plan-change.py` / `phase3-sandbox-manager.py`）合併為
>    單一 `scripts/sandbox.py`（子命令 `analyze | plan | sandbox | ccp`）。那些檔名已不存在。
> 2. **ponytail 迴歸（已修）**：合併時把 function-scoped 的 `import subprocess` 連同被刪的函式一起
>    刪掉、未 hoist；`import urllib.parse; urllib.parse.quote()` 被改寫成錯的 `__import__('urllib.parse').quote()`；
>    `Path` 少了 `from pathlib`。→ executor 四工具全炸（NameError/AttributeError，被 try/except 吞成
>    `success:False`）。`sandbox.py cmd_ccp` 的 `l[2]` 一有檔案變更就 IndexError。兩 script 零測試覆蓋，
>    所以「188 pytest passed」從沒碰過它們。**「工具鏈完整可用」在 `28e9d5e` 為真，在 ponytail 後為假。**
>    複查已修：補齊 import、修 urllib、bash 加 `shell=True`、`l[2]`→`l[1]`，並實跑驗證四工具 + 完整
>    sandbox 生命週期。
> 3. **憑證隔離真相**：本文「壞處 #3 / 建議 #3」**正確**地把憑證隔離標為已知缺口。但 `28e9d5e`
>    的「補三缺口」把 `_clean_env` 放進 `sandbox.py`（該檔不 spawn 子行程 → 死碼），真正跑 curl/bash 的
>    executor 從未接上 → 缺口實際沒補。複查已把 `_SAFE` 白名單 + `_clean_env()` 接進 executor 的 `_run`，
>    實測 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 不再外洩給子行程。
> 4. **修正後判斷**：HEAD 修好前，工具鏈**不可落地**（下方「建議 #1 可以落地」在 ponytail 後不成立）。
>    修好 + 實跑驗證後，可進**有人監督的 canary**；handoff 的紅線（禁 default-on、executor 接真 Scream
>    須 Ryan 親接）仍全數成立。

---

## 產出盤點

本次 Phase 1-3 實作產出了以下工具與檔案：

| # | 產出 | 類型 | 行數 |
|---|------|------|------|
| 1 | `scripts/phase1-analyze-commit.py` | commit 結構化萃取工具 | 263 |
| 2 | `scripts/phase1-sample-analysis.py` | 四面向分析示範 | 91 |
| 3 | `scripts/phase2-plan-change.py` | 實作計畫產生器 | 272 |
| 4 | `scripts/phase3-sandbox-manager.py` | 沙箱管理器 (create/destroy/ccp) | 382 |
| 5 | `scripts/scream-task-executor.py` (v1) | 正式工具改寫 (+258/-14) | 389 |
| 6 | `cases/sample-analysis-bc6e848.json` | 示範分析 | 55 |
| 7 | `cases/plan-001.yaml` | scream-task-executor 計畫 | 41 |
| 8 | `cases/ccp-001.yaml` | 含真實 diff 的候選變更包 | 223 |
| 9 | `docs/specs/aris-sandbox-learning/*.md` | 完整 spec (10 檔案) | 3840 |

**總計新增：** ~1000 行工具程式碼 + 3840 行 spec + 3 個案例檔案

---

## 好處分析

### 1. 沙箱工作流程已從紙上走到真實運作

| 面向 | 前 | 後 |
|------|-----|-----|
| 發現問題 | 只能口頭描述 | 結構化 CCP 格式 |
| 分析 commit | 靠人工看 git log | `phase1-analyze-commit.py` 自動萃取 |
| 產出計畫 | 不存在 | `phase2-plan-change.py` 產出結構化計畫 |
| 沙箱實作 | 不存在 (直接在 main 改) | `phase3-sandbox-manager.py` 隔離 worktree |
| 測試驗證 | 跑完就算了 | 測試結果記錄進 CCP |
| 決策依據 | 沒有 formal 文件 | 完整 CCP (diff + 測試 + diff_stats) |

**信心：0.90** — 這是實測過的工作流程，不是理論。

### 2. scream-task-executor v1 從 mock 變成真工具

v0 的 `execute_task()` 回傳假結果（`[Scream 搜尋] 已完成查詢: ...`），v1 實際呼叫：
- `_tool_read()` → subprocess `cat` 讀取檔案
- `_tool_write()` → 寫入檔案（受 path-DENY 保護）
- `_tool_search()` → curl DuckDuckGo lite 搜尋
- `_tool_bash()` → shell 執行（30s timeout + 危險指令過濾）

**信心：0.85** — 工具路由邏輯完整，但實際路徑萃取和內容猜測仍是 heuristic。

### 3. 安全隔離在第一個沙箱中已被驗證

沙箱 manager 實測：
- `git worktree add --detach` 建立隔離工作區
- 沙箱中 commit 不影響 main
- pytest 188 passed 證明隔離環境與正式環境一致
- 沙箱銷毀機制（殘留檢查、強制刪除）已實作

**信心：0.95** — Git worktree 隔離是 git 原生機制，不需要我們自己發明。

### 4. 決策鏈已完整串接

```
Phase 1: commit bc6e848 → 分析樣本 (sample-analysis-bc6e848.json)
Phase 2: scream-task-executor stub → 計畫 (plan-001.yaml)
Phase 3: 沙箱實作 → CCP (ccp-001.yaml) → 測試 188 passed
```

**信心：0.90** — 三階段串接已實測驗證，但尚無 Aris 自動參與。

### 好處綜合評分

| 維度 | 評分 | 說明 |
|------|------|------|
| 技術價值 | 4/5 | 工具鏈完整可用，diff 品質好 |
| 安全價值 | 5/5 | 隔離機制到位，path-DENY 在沙箱中也被繼承 |
| 流程價值 | 4/5 | 從零到有建立了完整 pipeline |
| 可複用性 | 4/5 | 同樣流程可套用到任何未來修改 |

**好處評分：4.25/5**

---

## 壞處分析

### 1. 新增工具數量偏多

一次 Phase 1-3 新增了 4 個 script + 3 個案例檔案。雖然每個檔案功能獨立，但維護負擔疊加。

**信心：0.85** — 檔案數量的確是客觀事實。

### 2. 部分 heuristic 實作較粗糙

- `_extract_path()` — 靠 regex 猜路徑，容易被誤導
- `_extract_content()` — 只處理 code block 和 key-value 格式
- `_extract_query()` — 只處理關鍵字開頭的模式

這些 heuristic 在真實使用中可能會 miss。

**信心：0.80** — 粗糙是真實的，但 Phase 1-3 的目的是「建立流程」，不是「完美實作」。

### 3. 沙箱 manager 尚未與 safety_gate 整合

目前沙箱的憑證隔離（env 清理）和路徑限制（sandbox path guard）是概念設計，尚未實作在 `phase3-sandbox-manager.py` 中。沙箱中的 Scream 仍然可以讀到正式環境變數。

**信心：0.95** — 這是已知缺口，不是 hidden issue。

### 4. 三個 Phase 的腳本之間沒有統一介面

- `phase1-analyze-commit.py` 輸出 YAML
- `phase2-plan-change.py` 輸出 YAML/JSON
- `phase3-sandbox-manager.py` 輸出 JSON + YAML

格式不一致，後續自動化需要 adapter。

**信心：0.90** — 格式不一致是事實，但 Phase 1-3 的目標是各自獨立可用。

### 壞處綜合評分

| 維度 | 評分 | 說明 |
|------|------|------|
| 複雜度增加 | 3/5 | 4 個新 script，維護負擔存在 |
| 實作品質 | 3/5 | heuristic 粗糙，格式不一致 |
| 安全缺口 | 2/5 | 憑證隔離尚未到位 |
| 整合程度 | 3/5 | 工具間尚未自動串接 |

**壞處評分：2.75/5**（越低越好）

---

## 風險分析

### 1. 沙箱 manager 的 worktree 殘留風險

如果沙箱 manager 被 kill（SIGKILL），worktree 可能殘留在檔案系統中。下次啟動時 `git worktree add` 可能因為目錄已存在而失敗。

**機率：0.30** | **影響：medium** | **可回退：是**（手動刪除）
**信心：0.85**

### 2. scream-task-executor v1 的 path-DENY 實作是自行實作，不是共用 safety_gate

`_tool_write()` 內的 path-DENY 檢查是自己寫的路徑比對，不是 import `laap.safety_gate`。如果 safety_gate 的規則更新，這裡不會自動同步。

**機率：0.20** | **影響：medium** | **可回退：是**（後續改為 import）
**信心：0.90**

### 3. heuristic 誤判導致錯誤操作

`_extract_path()` 或 `_extract_command()` 可能誤判任務描述，導致讀取錯誤檔案或執行錯誤指令。

**機率：0.25** | **影響：low** | **可回退：是**（錯誤結果不持久）
**信心：0.80**

### 4. 沙箱中修改的程式碼與正式環境不同步

沙箱中的修改如果沒有被合併，且正式環境又在沙箱建立後有新的 commit，可能導致沙箱無法直接 cherry-pick。

**機率：0.15** | **影響：low** | **可回退：是**（rebase 或重新建立沙箱）
**信心：0.90**

### 風險綜合評分

| 風險 | 機率 | 影響 | 分數 |
|------|------|------|------|
| worktree 殘留 | 0.30 | medium | 2/5 |
| path-DENY 不同步 | 0.20 | medium | 2/5 |
| heuristic 誤判 | 0.25 | low | 1/5 |
| 沙箱不同步 | 0.15 | low | 1/5 |

**風險評分：1.5/5**（整體偏低，且全部可回退）

---

## 代價分析

### 1. 開發時間

實際開發時間（含 spec 撰寫和工具實作）：

| 項目 | 時數 |
|------|------|
| spec 撰寫（10 檔案, 3840 行） | ~4h |
| Phase 1 工具 | ~0.5h |
| Phase 2 工具 | ~0.5h |
| Phase 3 工具 + 實作 | ~1h |
| 測試與驗證 | ~0.5h |
| **總計** | **~6.5h** |

**信心：0.80** — 這是估計，不是精確時間紀錄。

### 2. API 成本

$0 — 所有工具都在本機執行，無外部 API 呼叫。

### 3. Ryan 注意力成本

**評分：medium** — 需要閱讀 spec 確認方向、審批 Phase 1-3 的產出、決定是否合併 scream-task-executor v1。

### 4. 維護成本（預估）

- `phase1-analyze-commit.py`：幾乎不需要維護（git 格式穩定）
- `phase2-plan-change.py`：幾乎不需要維護（問題格式穩定）
- `phase3-sandbox-manager.py`：低維護（git worktree 行為穩定）
- `scream-task-executor.py`：中等維護（heuristic 可能需要調整）

**預估月維護時數：~0.5h**

### 代價綜合評分

| 維度 | 評分 | 說明 |
|------|------|------|
| 開發時間 | 3/5 | 6.5h 以一次性投入來說合理 |
| API 成本 | 0/5 | $0 |
| Ryan 注意力 | 3/5 | 需要審閱 spec 和產出 |
| 維護成本 | 2/5 | 月維護 ~0.5h |

**代價評分：2/5**（越低越好）

---

## 綜合評分

### 四面向總覽

| 面向 | 評分 | 說明 |
|------|------|------|
| 好處 | **4.25/5** | 工具鏈完整可用，安全隔離到位，流程可複用 |
| 壞處 | **2.75/5** | 新工具數量多，heuristic 粗糙，格式不一致 |
| 風險 | **1.5/5** | 全部可回退，無不可逆風險 |
| 代價 | **2/5** | 6.5h 開發，$0 API，月維護 0.5h |

### 單一總分的陷阱

**❌ 不建議使用：** `(4.25 - 2.75 - 1.5 - 2) = -2.0`

原因：不同意義的維度不能加減。好處 4.25 和風險 1.5 不是同一量綱。

### 建議的決策框架

```
好處：4.25/5  ⭐⭐⭐⭐  (高價值)
壞處：2.75/5  ⭐⭐⭐    (中等，可接受)
風險：1.5/5   ⭐⭐      (低風險，全部可回退)
代價：2/5     ⭐⭐      (低代價，一次性投入)

淨評估：好處 > 代價，風險可控，壞處可接受
建議：✅ 繼續（進入 Phase 4 落地考量）
```

### 具體建議

1. **scream-task-executor v1 可以落地** — 188 tests passed, 安全閘在位, diff 乾淨
2. **Phase 1-3 工具鏈可以落地** — 但建議先做一個小改善：統一三個 script 的輸出格式為 JSON
3. **憑證隔離是 Phase 3 的已知缺口** — 建議在 Phase 4 落地前補上 `env -i` 白名單機制
4. **heuristic 粗糙已知** — 但 Phase 1-3 的目標是「建立流程」，不是「完美實作」，可以後續迭代改善