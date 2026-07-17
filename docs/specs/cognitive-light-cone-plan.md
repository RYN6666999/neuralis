---
title: 認知光錐補齊計劃 — S_span 廣度軸
date: 2026-07-17
status: planned (未執行)
tags: [cognitive-light-cone, s-span, agency, rpe, plan]
---

# 認知光錐補齊計劃

> Levin 認知光錐 = 系統能主動追求的最大目標的時空邊界。
> 用 **T_reach（時間深度）× S_span（決策廣度）** 量，可證偽、可回滾。
> 判準：Aris 的光錐比純規則表、比 7B harness 大多少。

## 現況盤點（讀碼確認，2026-07-17）

**T_reach（時間軸）✅ 已通。** RPE 學習狀態（角度權重 / trust / 探索率）持久化進
gbrain `_internal/agency-state`，每 5 次行動 checkpoint，重啟續用不歸零。這是相對
7B harness（重啟失憶）的第一個結構性優勢。

**S_span（廣度軸）🔨 卡住，但卡在哪很精確：**

現況 `laap/agency.py`：
- `_ANGLE` 只有 `growth` + `competence`（relatedness/autonomy 已正確撤除，
  見 `s-span-design-note.md`：撤假角度是對的）。
- **工具路由已存在** — competence/growth 能走 gbrain / web-search / scream-ask
  （`_AGENTOS_TOOL_MAP` + `_form_intent` 的探索分支）。
- **但工具選擇是「探索時隨機」（`random()<0.5`），不是學來的。**
  RPE 目前只更新 `used_angle → angle_weights`（`_act` L544-555），
  **不更新 `used_tool`**。Aris 學得會「怎麼措辭查詢」，學不會「哪個工具更好用」。
- **`drive_threshold` 寫死 0.45。** RPE 調探索率但不調門檻。→ Aris 學得了
  「怎麼做」，學不了「該不該做、該追什麼」。

**一句話診斷：現在養成的是「會越查越準」的東西，不是「會改變自己想追什麼」的東西。**
廣度軸的擴張不是「填滿五個需求的查詢角度」（那是鋪磚），而是
「**既有需求有不同種類的動作 + 學會在動作間選擇 + 最終學會選目標本身**」。

## 三階段（由淺到深，每階段可獨立驗收 + 回滾）

### Phase S1 — RPE 學工具選擇（最小、最穩，先做）

**做什麼：** 把 RPE 學習從「per-angle」擴到「per-(need,tool)」。工具選擇不再是
`random()<0.5`，而是像角度一樣按學來的權重 epsilon-greedy 抽樣。

- `_need_stats[need]` 增加 `tool_weights: {gbrain: w, "web-search": w, ...}`
- `_form_intent` 的工具路由改為讀 `tool_weights` 抽樣（沿用現有 exploration 機制）
- `_act` 的 RPE 更新同時寫回 `used_tool`（比照 `used_angle` 那段，過 constitution guard）
- 持久化 checkpoint 同步含 tool_weights（跟 angle_weights 一起進 gbrain）

**為什麼先做這個：** 動作空間已經有多工具了（架構在），只是沒學。這是「把已有的東西
接起來」，風險最低，且直接驗證「S_span 的正確定義（多種動作 + 學會選）」是否真的
產生可測的行為漂移。

**驗收：** 給 competence 灌一批「gbrain 命中率低、web-search 命中率高」的情境，
若干輪後 `tool_weights[web-search] > tool_weights[gbrain]`。對照組（不學）不漂移。
自檢 `check-tool-rpe.py`。**反悔條件：** 上線數週儀表無可測漂移 → S1 判死，
S_span 走「加動作類型」而非「學工具選擇」。

### Phase S2 — 第二類動作（不只是「查」）

**做什麼：** 現在所有動作本質都是「retrieve」（gbrain/web-search/scream-ask 全是查）。
真廣度 = 質性不同的動作類型。第一個候選：**synthesize/write**（把查到的東西整合成
一頁新筆記寫回 gbrain），而非只是讀。

**⚠️ 前置硬門檻：** 這是**寫入類動作**，必須先過 safety gate 4b 批准閘
（`laap/safety_gate.py`）。目前 agency 是唯讀白名單。開放寫入前 4b 必須先在位並自檢過
（CLAUDE.md 規則 7：煞車先於能力）。

- 定義 write-class action 的白名單（只能寫 `laap/memory/*` 或指定 namespace，
  比照 consolidation 的硬邊界）
- 動作選擇擴到「retrieve vs synthesize」，同樣納入 RPE
- synthesize 的 outcome 怎麼評分？（retrieve 用命中率；synthesize 要別的信號 —
  這頁筆記後續有沒有被 recall 用到？= 延遲獎勵，設計待補）

**驗收：** Aris 自主產出一頁整合筆記，且該筆記後續被 recall 命中 → 正 RPE。
自檢 + 審計。

### Phase S3 — 學會選目標（最深，S_span 的真正前沿）

**做什麼：** 讓 `drive_threshold` 或需求優先序本身變成 RPE 可影響的量。現在
Aris 的「想追什麼」由固定門檻 + OU 衰減決定；S3 讓「哪個需求值得投入」也開始被
後果塑形。這是「會改變自己想追什麼」的門檻 —— 光錐從「怎麼做」擴到「做什麼」。

- 候選機制 A：per-need 的動態門檻（某需求近期行動 RPE 高 → 門檻降 → 更常被追）
- 候選機制 B：需求排序的 meta-RPE（不是滿足單一需求，而是學「這個 context 下
  優先滿足哪個需求」的回報最高）
- **必須有煞車：** 需求憲法（`constitution.py`）的 range 硬夾 + 來源預算不能被繞過；
  meta 學習不能讓某需求鎖死或餓死其他需求。持久化煞車（`_state_loaded`）延伸到
  meta 權重。

**⚠️ 這階段最容易做出「假 agency」。** 一條寫死的規則說「搜關於自主的東西」不是自主
（見 s-span-design-note.md 對 autonomy 的糾正）。S3 的設計要能回答：這是真的「系統改變了
自己的目標傾向」，還是又一層更複雜的規則表？**下手前先想清楚證偽條件。**

## 光錐度量（貫穿三階段，必須先定義）

roadmap 警語：擴大投入推理層前先建 benchmark。光錐同理 —— **沒有可測的 S_span 指標，
三個 Phase 都是自我感覺良好。** 先定義：

- **動作多樣性熵**：一段時間內 (need, tool, action_type) 組合的分佈熵。填磚不會升，
  真廣度會升。
- **選擇非隨機性**：工具/目標選擇與 RPE 歷史的相關性（學到了 = 相關；沒學 = 隨機）。
- **對照基線**：純規則表 baseline（固定選擇）跑同樣情境，S_span 指標必須顯著高於它，
  否則這層投資判死。
- 落 `docs/benchmarks/s-span-*.md`，比照 Rust psi-bench 的可重現驗收模式。

## 研究插入點（等資料 —— 這裡最需要外部研究）

你另一個 AI 的研究資料主要往這幾個洞灌：

1. **內在動機的形式化** — S3 的「該追什麼」目前是我拍腦袋的動態門檻。文獻上有更硬的
   框架：empowerment（未來可達狀態的資訊量）、free energy / active inference
   （最小化預測誤差驅動探索）、autotelic / intrinsically motivated goal generation
   （IMGEP、CURIOUS 那一系）。**哪個能給 drive_threshold 一個有理論根據的動態化，
   而不是又一條規則？**
2. **目標生成 vs 目標選擇** — S3 我寫的是「在既有五需求間選」。但真正的 S_span 擴張
   可能是「生成新的子目標」。研究若有 hierarchical goal / option discovery 的可落地
   機制，可能改寫 S3 的形狀。
3. **S_span 度量本身** — 認知科學/AI 界對「行為廣度 / 光錐尺寸」有沒有既成指標？
   我上面定的熵 + 非隨機性是工程近似，若有更 principled 的量，優先採用。
4. **synthesize 的延遲獎勵設計**（S2）— 「這頁筆記後續有沒有用」是稀疏 + 延遲信號，
   credit assignment 是老問題，研究若有適用的 discount / eligibility trace 做法可直接接。

> 資料進來後，把對應段落從「候選機制 A/B」升級為「依 <論文> 的 <機制>」，
> 並在每個機制旁標可證偽條件。**不採用無法證偽的漂亮框架**（見 CLAUDE.md 誠實鐵則）。

## 依賴與順序

```
T_reach ✅
   │
   ▼
S1 (RPE 學工具) ──驗證「多動作+學選擇」定義是否成立──┐
   │ 成立                                          │ 不成立→S_span 改路線
   ▼                                              
S2 (第二類動作) ← 前置：safety gate 4b 必須在位
   │
   ▼
S3 (學會選目標) ← 前置：想清楚證偽條件 + 憲法煞車延伸
```

## 邊界 / 不做

- 不碰五維需求結構、持久化煞車邏輯（養成期鐵則）
- 不做 4c RSI（戰略已定：假推理驅動自我改進是本末倒置）
- 不投 psilang 推理層（20 題 benchmark 沒贏過 gbrain+LLM 之前）
- 不做無法證偽的「自主性」—— 一條更複雜的規則不是 agency
