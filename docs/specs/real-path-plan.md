---
title: 剝去妄想後的兩條真路 — A（對話+串流穩定）+ B（學習真的碰到對話）
status: plan
date: 2026-07-19
---

# 先講清楚現實（不裝）

三層，之前被混在一起：

1. **你在 Scream 打字** → Scream 的 agent 框架在跑（Claude 能力 + 工具/WolfPack/skills）。
2. **每步 LLM completion** → 送到 `:11546`，走 `chatflow → deepseek`（或含圖 → gemini）。
   有 psi 餵食，但**不經 agency.py 的 S_span 決策**。
3. **S_span / RPE 學習** → 只在 agency.py 的**背景自主迴圈**（log 的 `[Agency] 行動#N`）跑。
   跟你的對話**零關係**。就算直連 :11546，你的**聊天**也不走 S_span——S_span 是背景動作用的。

**所以現況：所謂「認知光錐」= 一個背景 bandit 在學「Aris 自主查資料時哪個工具好用」。
它不在你的對話裡生效，過去被包裝成「在 Aris 身上運作」是灌水。**

以下兩條路把這件事拆成「能對話」（A）和「學習真的碰對話」（B），都不裝。

---

# Plan A — 讓「對話 + 串流」穩定可用

## A0 決策：放棄 aris-mode bypass（那是我這 session 的錯）

`patch-scream-aris.py`（spawn `aris-chat.py --once` 直通）會**繞過 Scream agent loop、丟失
tools/skills/plan mode**，且在 0.10.0 是脆弱的 dispatch 手術。**不要它。**

正解 = `config.toml` 已有的 `default_model = "laap/laap-core"`：每則訊息走 Scream agent
loop，用 laap-core 當 LLM，psi/工具整合在 :11546 server 端。**串流走 Scream 原生 SSE，本來就通。**
這個「Aris」= Scream agent + deepseek + psi，**不是** agency-loop Aris——但這是唯一不脆弱、
不丟工具的路。

## A 要修的三個真 blocker

| # | 問題 | 狀態 | 修法 | 風險 |
|---|---|---|---|---|
| A1 | 圖片路徑 | 幾乎好（`gemini-2.5-flash` 實測能 image+tools+stream） | 開新 session 端到端確認一次 | 低 |
| A2 | **transient timeout → 回合中止 → 要手動「繼續」** | 未做 | `_call_llm_stream` 在 504/timeout 且**還沒吐 token** 時自動重試（≤2 次），不要 yield error 就 return。已吐 token 的不重試（避免重複輸出） | 低（在既有 retry 骨架上加） |
| A3 | **抖動（畫面跳頂）** | 補丁對不上 0.10.0（`viewportTop`/`firstChanged` 在 bundle 是 0），永遠套不上 | 這是 **scream-code 0.10.0 的 render bug**。① 回報上游 ② 開新 session 減渲染量 ③（最後手段）逆向 `doRender`/`fullRender` 重寫補丁 | ③ **極高**（改終端渲染主迴圈，曾把 scream 弄到開不起來） |

**A 的順序**：A2（真痛點、低風險、我來做）→ A1（你開新 session 測圖）→ A3 先走 ①②，③ 別碰。

---

# Plan B — 讓學到的東西真的碰到你的對話

## 現況缺口（讀碼確認）

- agency.py 的 `tool_weights`（S1 bandit）**只從背景自主動作學**（`_act` 裡 `_bump_tool_weight`）。
- 對話的工具選擇在 `respond_stream` 的工具迴圈——**LLM 自己挑 `tool_calls`，完全不看 `tool_weights`**。
- 兩邊是斷的。所以你對話再多次，那個 bandit 也學不到、也不影響你。

## B 要做的兩件事（這才是「讓光錐碰到你」的唯一真路，且它現在不存在）

**B1 — 統一學習信號：對話的工具結果餵回同一個 bandit。**
- `respond_stream` 執行工具拿到 result 後，算一個 outcome（成敗/長度/是否被 recall），呼叫
  `agency._bump_tool_weight(need, tool, rpe)`。
- 障礙（要誠實面對）：對話**沒有 agency 的 `need` 概念**。解法：給對話一個固定 bucket
  `need="chat"`，或用 psi 當下主導 need。先用 `"chat"` 最簡單。
- 效果：你每次對話用工具，都在教這個 bandit。**這是唯一能讓「學習從真實使用累積」的接法。**

**B2 — 把學到的偏好注入對話。**
- 在 `respond_stream` 組 system prompt 時，讀 `agency._get_tool_weights("chat")`，加一句
  提示：「歷史上這類請求，`web-search` 回報最高、`X` 常無效」。LLM 據此傾向選好工具。
- 或更硬：依權重 re-rank / 過濾提供給 LLM 的 tools 清單。先用 prompt 提示（可逆、低風險）。

## B 的誠實定位（不裝）

- 這是 **prompt 提示 + bandit 累積**。效果 modest：它會讓工具選擇隨使用**慢慢變準**，
  不會讓它「思考」、不會有意識、不是 AGI。
- 但它是**真的**：學習訊號來自你的真實對話，偏好真的回饋到下次選工具。跟現在「背景學一套、
  對話用另一套」的斷裂比，這是實打實的接通。
- 度量：沿用 `s_span_bench.tool_learning`（已存在），但餵 `need="chat"` 的 audit。
  數週後 corr > 0 = 真在學；~0 = 這條路也判死，別自欺。

---

# 不做的（把灌水釘死）

- **不再叫它「認知光錐」在你身上運作。** 它是 tool-preference bandit。
- **不再讓 Scream cosplay 報假 PSI 數字**當成「量出來的」。模板值就標模板值。
- **不碰 scream 渲染主迴圈**（A3③），除非 ①② 都無效且你明確要賭。
- **不做 S2/S3 真前瞻 / 選目標**，直到 B 證明「對話學習」corr > 0——沒證據不往上疊。

---

# 建議執行序

1. **A2**（自動重試，止血你的「繼續」痛點）— 我來，guard + 走閘。
2. **A1**（你開新 session 測圖）+ **A3①②**（回報上游 / 新 session）。
3. **B1 → B2**（讓學習碰到對話）— 我來，各自 guard + 度量，做完誠實看 corr。
4. B 的 corr 若 ~0 → 收手，承認這套對「變聰明」幫助有限，別再投。
