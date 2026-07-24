---
title: brain-memory-architecture — 三層記憶（海馬/皮質/連結）＋ 固化修剪離線程序
date: 2026-07-24
status: designing (未實作)
tags: [gbrain, memory, consolidation, hippocampus, cortex, reconstructive, canary, spec]
---

# brain-memory-architecture · 三層記憶

> 骨架定於 2026-07-20 對話，2026-07-24 落檔搶救（先前只在對話中，未進 docs/specs/）。
> 把腦庫從「圖書館」（頁面獨立、靠 slug + BM25 連通）升級成「大腦」：
> 記憶分層、離線固化、查詢即重建。

## 0. 定位

GBrain 現況：頁面（神經元本體 ✅）+ slug + BM25。突觸（`add_link` 12 type）端點已上線但
回填率低；激發迴路（traverse 子圖）、髓鞘化/遺忘（access_count/decay）未實作。

本 spec 補的不是「再加一個功能」，是**把記憶當成有生命週期的東西**：寫進海馬 → 夜間固化進皮質
→ 查詢時從碎片重建 → 沒用到的連結被修剪。對映神經科學的 memory consolidation。

**與 [[gbrain-aris-loop]] 的分工：** 那份管「多可信」（L1 證據台帳 + L2 校準）；
本份管「怎麼存、怎麼固化、怎麼取」（儲存側生命週期）。台帳的節點就住在這三層裡。

---

## 1. 三層記憶

| 層 | 神經對映 | 職責 | 現有落點 | 特性 |
|----|---------|------|---------|------|
| **海馬層** | 海馬迴（情節記憶） | 快速寫入、短期、原始事件、高可塑 | `mem/*`、laap episodic `laap/memory/episodic/*` | 寫得快、易變、未固化 |
| **皮質層** | 大腦皮層（語義記憶） | 固化後的長期知識、穩定、去情節化 | `wiki/concepts/`、`wiki/decisions/` | 寫得慢、穩定、抽象 |
| **連結層** | 突觸 | 頁與頁之間的顯式邊，帶 type + weight | `add_link`（12 type） | 激發迴路的線路 |

**海馬 → 皮質固化**是核心動作：情節記憶（「某天談了 X」）反覆出現、被 recall、彼此印證後，
抽出穩定的語義知識（「X 是 Y」）沉澱進皮質。**固化不是複製，是抽取 + 去情節化。**

連結層 12 type（已上線）：`derives_from / supersedes / relates_to / example_of /
contradicts / mentions / attended / founded / works_at / invested_in / advises / source`。

腦區分區（現有自然形成）：

| 路徑 | 腦區 |
|------|------|
| `gbrain/*` | 前額葉（執行控制）|
| `wiki/concepts/*` | 顳葉（語義記憶）|
| `wiki/decisions/*` | 海馬迴→皮層（情節記憶）|
| `mem/*` | 工作記憶（短期）|
| `people/`、`wiki/projects/*` | 關聯區 |

---

## 2. 固化 + 修剪離線程序（夜班 · circadian）

沿用 [[gbrain-circadian]] 骨架：人腦睡眠時整理記憶，腦庫也該有日夜節律。
**固化與修剪走冷路徑（夜間批次），不進白天閉環熱路徑。**

### 固化（consolidation）

夜班（00:00–06:00）：

1. 撈待掃描清單（新頁 + 輪到的孤兒頁）
2. 每頁：讀內文 → 搜相鄰 5–10 頁 → 判斷關聯
3. **信心分級**（不盲建）：
   - 高信心 → 直接 `add_link` + 記 `mem/YYYY-MM-DD/night-shift`
   - 中信心 → 寫進 `gbrain/inbox-pending`（待人審）
   - 低信心 → 丟掉，不記錄
4. 海馬→皮質：反覆被 recall 的情節記憶群，抽語義沉澱進 `wiki/concepts/`

**分桶排程：** 新頁優先（當天/昨天建改）· 孤兒頁巡查（引用 0 次，每週一輪）·
熱頁回訪（近期讀取多，每月複查）。

### 修剪（pruning）

- 用最新證據重算連結 confidence（接 [[gbrain-aris-loop]] §3 `nightly_recheck`）。
- 掉破門檻 → **凍結 + 緩慢衰減連結（`weight *= 0.9`），不刪頁。**
- 鐵律：**剪連結，不刪頁。** decay/access_count 最後做，先確定不誤刪有價值舊筆記
  （neural-arch-v2：先觀察 1–2 個月）。

### 日班回報（晨醒 · 人類審核疲勞防護）

1. AI 開機讀 `gbrain/now` + `gbrain/inbox-pending`
2. 主動報告：「昨晚做了 X 件，有 Y 件需你決定，要看嗎？」
3. 防護：每日報告上限 5 條（超過累積）· 高信心不報只報中信心待審 ·
   格式極簡「A ↔ B，理由一句，[同意/否決/晚點]」

---

## 3. 重建式查詢 = 推理（reconstructive memory）

**核心洞見：查詢不是撈原文，是從碎片重建，而重建過程本身就是推理。**

人腦記憶不是錄影回放，是每次從碎片 + schema 重新組裝（reconstructive memory）。
腦庫查詢照此設計：

- 一個查詢不回單頁原文，而是**激發相鄰子圖**（traverse），把散在多頁的碎片拉齊。
- 重建時做的事——碎片對齊、矛盾檢查、時間排序、缺口補全——**就是推理**。
- 這正好接 [[gbrain-aris-loop]] §2 第三繩「內部一致性交叉」：重建時撞見的矛盾 = 現成的紅旗。

激發迴路（traverse 子圖）因此從「錦上添花」升為「查詢即推理」的必要件——
沒有子圖激發，查詢退回單頁撈原文，重建/推理無從發生。

---

## 4. 效用信號驅動固化（借甲）

哪些記憶該固化進皮質、哪些連結該修剪，**不靠拍腦袋，靠效用信號**。

沿用甲（認知光錐）E1.2「下游效用信號」：**記憶被 recall 到、且事後證明有用，才有獎。**

- `on_recall`（見 [[gbrain-aris-loop]] §3）：連結被用 → weight +1；事後對 → 再 +1。
- 固化優先序 = 高 recall × 高事後正確的情節群先抽語義。
- 修剪對象 = 長期零 recall + confidence 掉破門檻的連結。
- 抗刷分：沿用甲 E1.1 de-game，避免「多寫幾筆長內容」偽造效用（堵 `len/500` 舊漏洞）。

**關鍵：固化/修剪的信號是延遲真實效用，不是寫入當下的自我感覺**（對映 aris-loop 公理三）。

---

## 5. 安全：canary-first（漸進落地）

沿用 circadian 三週計劃 + 甲脊椎「防護欄先於能力」：

| 階段 | 做什麼 | 閘 |
|------|--------|----|
| 第一週 · 手動模擬 | 選 10 頁手動跑一輪固化，觀察中信心審核比例 | 全人工 |
| 第二週 · 半自動 | 腳本掃頁產 `inbox-pending`，**不自動建連結** | 人審每條 |
| 第三週起 · 夜班 | 品質夠好才開高信心自動 `add_link` | 高信心自動、中信心人審 |
| 修剪（最後） | confidence 重算 → 凍結衰減 | 只剪連結不刪頁，先觀察 1–2 月 |

**紅線：**
- 修剪永不刪頁（可逆：凍結 + 衰減）。
- 海馬→皮質固化前，抽取結果先過 [[gbrain-aris-loop]] L2 三繩驗證——
  **抽取本身可能幻覺，不能繞過驗證閘直接寫回皮質。**
- 自動 `add_link` 只在高信心 + 品質實測達標後開。

---

## 6. 驗收標準

- 從 `gbrain/0` 出發，不靠 search 一跳到達四個子頁（連結層通）。
- 誠實規則、寫入 SOP 有雙向連結；DEPRECATED 頁有 `supersedes` 指向新頁。
- 夜班固化：中信心審核比例可測、每日報告 ≤5 條。
- 重建式查詢：traverse 子圖回傳相鄰碎片，重建時能標出內部矛盾。
- 修剪：零 recall + 低 confidence 連結被凍結，**且無有價值舊頁被誤刪**（可逆驗證）。

---

## 7. 開放問題

- 海馬→皮質「抽語義」具體怎麼做（LLM 抽取？規則？）— 抽取幻覺風險高，需先過三繩，方法待設計。
- `access_count` / `decay` 何時開（neural-arch-v2 主張先觀察 1–2 月）。
- OpenViking 的 session 自迭代（User/Agent memory）可否直接當海馬→皮質固化的下層機制
  （見 [[gbrain-aris-loop]] §5 L0）— 但抽出的長期記憶須先進 L2 過驗證，不直接寫回。
- 「重建即推理」要不要接 LLM，還是純 traverse + 確定性碎片對齊起步（傾向後者，canary-first）。

## 相關

- `docs/specs/gbrain-aris-loop.md`（L1 台帳 + L2 校準，本份的可信度側）
- `docs/specs/safe-self-evolution-route.md`（甲脊椎、E1.1/E1.2 效用信號）
- gbrain: `wiki/projects/gbrain-neural-arch-v2`、`wiki-from-ai/projects/gbrain-circadian`、
  `ai記憶優化專案`、`gbrain/now`
