# 第2條 — recall 記分歸位（outcome-tied）

**日期**：2026-07-27
**起因**：砍掉 relay 寫入端自賺分（`799cd4e`）後，`discovered_salience` 沒有任何
地方在真 recall 時記分 → 死欄位（恒 0）→ `/wake` 的 τ 加權退化成 salience×時間衰減。

---

## 為什麼不能用直覺修法

| 直覺修法 | 問題 |
|----------|------|
| 在 `_wake_attention` 對被撈記憶記分 | wake 依 `_tau_score(salience, discovered, age)` 選，**選擇依據裡就含 discovered_salience** → 撈到就加分 = 自我墊高，違反 `recall_not_selfinflated` 契約 |
| 在 `query()` 對命中記憶記分 | query 按 recency 排（不含 discovered，安全），但**生產端沒人 content-query aris-memory**（唯一 recall 是 /wake）→ 空砲，永遠 0 |

當前架構唯一的 recall 路徑（wake）就是按「要獎勵的量」在選 → 任何撈取即記分都自賺分。

## 修法：選擇與獎勵脫鉤（outcome-tied，同 memory_utility E1.2 思路）

- **aris-memory**（`scripts/aris-memory.py`）：`_wake_attention` / `wake_context`
  回 `(text, ids)`；`/wake` 多回 `recalled_ids`；`/memories/recall_hit` 支援 `ids` 批次。
  **撈取當下不記分。**
- **chatflow**（`laap/chatflow.py`）：wake ids 進 `_bootstrap_cache["wake_ids"]`；
  在 `_maybe_session_bootstrap` **真注入暖啟動塊時**（= 真使用者開新 session、
  MIN_GAP 120s 限速）fire-and-forget POST 批次 recall_hit。只在真使用者 bootstrap
  觸發——Aris 無人值守自主醒來走別的 /wake 路徑（bridge/agency），不經此 → 不記分。
- **不擋 loop**：credit 走 daemon thread POST（handoff 鐵則：loop 線程不同步等待）。

### ⚠️ 重驗抓到的 bug（Ryan「預判有 bug」— 屬實，已修）

初版把 credit 綁在 deferred 的 `_pending_recall_ids` 全域 + 設值放在**被 TTL 快取的**
`_session_bootstrap_memories` 裡（快取早退在 id 賦值之前）。後果：
- **快取命中（300s TTL 內）→ id 不更新** → 該 session 的撈取不被 credit。
- 裸全域跨 session 殘留 → 陳舊 id 可能被誤記到別的 session。

初版 e2e 之所以綠是剛好碰上快取 miss。修法：id 存進快取（命中/未命中都可讀），
credit 綁在**真注入事件**（`_maybe_session_bootstrap`），移除 deferred 全域。
重驗 e2e：reload 後單一新 session turn，total_recalls 47→52（+5），快取路徑不再漏。

## 驗證

- 單元 `scripts/check-recall-scoring.py` 4 段全過：wake 回 ids、recall_hit +0.1、
  **撈取 100 次 discovered_salience 完全不動（無自賺分）**、τ 對 discovered 有反應。
- 全套件 264 passed；兩檔 compile OK。
- **live e2e**（修正後）：reload 後單一新 session turn，`total_recalls` sum 47→52，
  +5 = 暖啟動撈進的 5 筆記憶在真注入當下被 credit。選擇（wake τ）與獎勵（真使用者
  在場 bootstrap）脫鉤，實測成立。

## 誠實界線（ponytail 天花板）

被 credit 的「是哪些記憶」仍由 wake τ 選（τ 含 discovered_salience），所以跨多個
**都被續談**的 session 仍有殘餘富者越富。但比兩個直覺修法都好：
- vs 死欄位：現在有真信號。
- vs 撈取即記分：credit 只在**使用者真的在場續談**時流動（Aris 7/24 大量無人值守
  的自主醒來/重啟 bootstrap 一律不記分），且 cap 1.0 + τ 上限 8 天 + age 衰減有界。

**升級路徑**：把 credit 從「暖啟動塊成員」收緊成「與續談內容真的相關的那幾筆」
（relevance-gated），才完全斷開 τ→選擇→credit→τ 迴路。v1 先到這，界線寫明。

## 仍開著（獨立，未動）

- relay 直譯器來源（python@3.14 自啟 vs launchd laapenv）— 運維，已確認 aris-memory
  service 跑在 python@3.14（我的 stdlib-only 改動相容）。
- relay 回放歷史（`relay_remembers_turn`）、`wake_reaches_prompt` — 那個 AI 那邊的紅燈。
