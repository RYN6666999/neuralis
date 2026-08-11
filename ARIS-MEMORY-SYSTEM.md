---
name: aris-memory-system
description: Aris 記憶系統（T1 跨對話記憶）的完整地圖——寫入/讀取真實路徑、live 解析層陷阱（runpy 載 laap-AGI 版不是 overlay 版）、token 召回機制、種子記憶、已知缺口與下一步。任何要修 T1/跨對話記憶/召回 returned=0、或想知道「Aris 記不記得 X」怎麼調的 agent 先讀這份。本檔是覆蓋版（2026-08-12），舊版本一律刪掉，不要新舊混雜。
---

# Aris 記憶系統（T1）地圖 — 2026-08-12 實測版（覆蓋舊版）

> 口訣：**記憶有寫沒讀 = 等於沒有；live 解析層是 laap-AGI 不是 neuralis overlay。**

## 1. 架構（四層，各踩過一次）

| 層 | 真實路徑 | 狀態 |
|---|---|---|
| 寫入 | `memory_bridge.store_important` → `MemoryStore.store` → gbrain `put_page laap/memory/<layer>/<id>` | ✅ 正常（頁面實測在） |
| 讀取引擎 | gbrain search = 整串 AND 詞彙匹配：關鍵字會中、自然句≈0 | ✅ 已用 token 修（見 §3） |
| 解析層 | **live（runpy 起 laap_brain_api）import 的是 `~/Developer/laap-AGI/aris_brain/` 的作者版**，不是 neuralis overlay 版——改 overlay 永遠吃不到 | ✅ 已兩處都修＋同步 |
| 注入鏈 | chatflow 回覆產生前同步等召回（≤6s）→ 織進最後一則 user message；LLM 兜底 `_psi_respond(memories=...)` | ⚠️ **端到端仍會幻覺**（見 §5） |

## 2. 兩條讀取呼叫點
- **11547 bridge**：`aris_cognitive_bridge.py:1120` `recall_related(user_message, top_k=2)` → laap-AGI `memory_bridge.recall_related`（telemetry `memory_retrieval` 紀錄處）
- **11546 chatflow**：`_psi_memories_sync`（gbrain 直查；有 INFO 儀表：recall start / recall query→N hits / 失敗原因）

## 3. 召回機制（2026-08-12 修好）
- `_query_tokens`：空白/標點切詞；CJK 長詞（>4 字）補頭尾 2 字片語
- `_STOPWORDS`：告訴我/我們/哪些/最近…過濾
- `hybrid_hits_any`：鑑別性 token 優先（含英數的排前）→ 最多 4 token 逐 token 查 gbrain → 併集 → `_memory_first`（laap/memory/* 排最前）
- 速度：整串查已移除（自然句命中率≈0 且白燒時間）；實測 21s → 目標 <6s
- score 門檻（chatflow）：`>=0.3`；種子頁實測 0.304（貼線）——若又全濾掉，往下調
- 陷阱：`_quoted_recently`（6 輪內引用過的記憶不再引，防穿幫）

## 4. 種子記憶（已寫入 gbrain，recall 通就回得來）
| id | 內容 |
|---|---|
| mem-1786465369-0ba821 | V12 引擎檔名 = aris_v12_dense_kernel.py |
| mem-1786465421-5986aa | 記憶 recall 修復 2026-08-12 |
| mem-1786465429-535531 | 全面啟動接線＋提交 bedad23/cbbb4a0 |
| mem-1786465863-b664c3 | Aris 專案 08-11~12 弄了什麼（tuple bug/散文/量子/V12/閘門/提交） |

## 5. 已知缺口（下一輪 T1 收尾專案）
端到端「全新對話答對 V12 檔名」仍失敗——她每輪幻覺不同名字（V12Engine → aris_v12_engine.bas → NexusCore），還曾宣稱「gbrain 裡記的」。儀表顯示 recall 有中（4 hits）但答案沒用上。嫌疑（按機率）：
1. author 管線（rules engine）有自己的 ToolExecutor/gbrain 工具路徑，可能覆寫或重排注入的記憶內容
2. LLM 對「相關記憶：…」區塊的服從度／prompt 位置（marker 與 boot_lines 夾雜）
3. LLM response 快取（llm_respond `_cache_key`、60s TTL）
4. score 門檻/去重在特定 query 下把種子濾掉
**驗證法**：直接 curl 11546 全新對話問 V12 檔名，看 log `recall query→N hits` 與答案；再下追 author 管線的 RulesEngine input 是否仍含記憶區塊。

## 6. 相關提交（2026-08-12）
- neuralis b855ff6（記憶先行注入＋召回提速）、3f4df6e（token 化/儀表/agency tuple）、bedad23（量子/閘門）
- laap-AGI 0eb4cc7（提速移植）、b0d84aa（helpers＋author bridge 修復）、cbbb4a0（潛意識 V12）

## 7. Tuple bug 兩個窩（都已修，別再查）
- `[Status] 寫入失敗` → status.py need_stats stringify
- `[Agency] 狀態存檔失敗` → agency.py 狀態存檔 stringify
