---
title: 認知光錐補齊計劃 — S_span × T_reach
date: 2026-07-17
updated: 2026-07-17（整合外部研究報告）
status: planned (未執行 · 含待拍板的戰略分岔)
tags: [cognitive-light-cone, s-span, t-reach, agency, rpe, plan]
---

# 認知光錐補齊計劃

> Levin 認知光錐 = 系統能主動追求的最大目標的時空邊界。
> 用 **T_reach（時間深度）× S_span（決策廣度）** 量，可證偽、可回滾。
> 判準：Aris 的光錐比純規則表、比 7B harness 大多少。

> **本文整合了兩個來源：**（1）讀碼確認的現況與 S1/S2/S3 漸進路線（zero-LLM 取向）；
> （2）外部研究報告（2026-07-17）帶來的論文地圖 + LLM 樹搜索取向 + 程式碼對應。
> 兩者在「T_reach 定義」與「LLM 是否進 agency」上有真衝突，本文不默默合併，
> 把分岔攤在 §4 讓人拍板。

---

## 1. 現況盤點（讀碼確認，2026-07-17）

### T_reach 是兩條軸，不是一條（研究報告揭露的有用糾正）

專案一直把 T_reach 當「時間持久性」，研究報告當「規劃前瞻深度」。這是**兩條不同的軸**，
過去混用一個詞造成矛盾。拆開：

| T_reach 子軸 | 定義 | 狀態 |
|---|---|---|
| **T_persist（持久性）** | 跨 session 記住學到的傾向，重啟不歸零 | ✅ 已通（`_internal/agency-state`，權重重啟續用） |
| **T_lookahead（前瞻）** | 做決定前展開「做了 A 之後會怎樣」的多步預測 | ❌ = 0（agency 是單步反應：intent → act → RPE） |

研究報告說「T_reach = 0」——就 T_lookahead 而言是對的；就 T_persist 而言是錯的。
持久性是 neuralis 相對 7B harness（重啟失憶）的真結構性優勢，不容抹掉。

### S_span 卡點（精確位置）

`laap/agency.py`：
- `_ANGLE` 只有 `growth` + `competence`（relatedness/autonomy 已正確撤除，見 `s-span-design-note.md`）
- **工具路由已存在** — competence/growth 能走 gbrain / web-search / scream-ask
- **但工具選擇是「探索時隨機」（`random()<0.5`），不是學來的。** RPE 只更新
  `used_angle → angle_weights`，**不更新 `used_tool`**。Aris 學得會「怎麼措辭」，
  學不會「哪個工具好用」。
- `drive_threshold` 寫死 0.45 → 學得了「怎麼做」，學不了「該不該做、該追什麼」。

### 對研究報告「光錐 ≈ 0 / 跟規則表差不多」的校正

單步 + 無前瞻 + 無反事實——**這個批評公平**，且對上專案自己的誠實標註
（「現在養成的是會越查越準的東西，不是會改變自己想追什麼的東西」）。
但「跟純規則表差距不大」**過頭了**：一個跨 session 持久 + RPE 自適應的 bandit
比靜態規則表多了 T_persist 這條軸。批評收下，overstatement 不收。

---

## 2. 論文地圖（研究報告貢獻，已篩過）

### S_span / 決策廣度（樹搜索系）

| 論文 | 出處 | 對 Aris 的借力點 |
|---|---|---|
| **Tree of Thoughts (ToT)** — Yao 2023 | arXiv 2305.10601, NeurIPS'23，repo ⭐3.5k | 最接近 S_span 的實作。propose→value→search 三段可直接映射到 `_form_intent`/`_score_result`/`_evaluate`。Game of 24: CoT 4%→ToT 74% |
| **Strategist（雙層樹搜索）** — Light 2024 | arXiv 2408.15707 | 上層選策略、下層 rollout。對上我們既有的 need→drive（上層）/ tool→action（下層） |
| **ToolTree（MCTS + 雙回饋剪枝）** — Yang 2026 | arXiv 2026 | 工具選擇的 MCTS，對上 ToolExecutor 多工具場景 |
| **ReAcTree（階層 Agent 樹）** — Choi 2025 | arXiv 2025 | 對上 scream-task 任務委派，任務樹展開 |

### T_lookahead / 時間前瞻（world model 系）

| 論文 | 出處 | 對 Aris 的借力點 |
|---|---|---|
| **LLM-Based World Models** — Yang 2024 | arXiv 2024 | 用 LLM 現有世界知識預測行動結果，不需訓練專用 world model |
| **PriorZero** — Xiong 2026 | arXiv 2026 | gbrain 檢索結果 = language prior，引導 world model 預測 |
| **SGA-MCTS（經驗取代 rollout）** — Xie 2026 | arXiv 2026 | **gbrain 當世界模型快取**：hit 直接用經驗，miss 才叫 LLM。降 LLM 依賴 |

補充 pattern：Chain-of-Verification（自我校驗）、ToolChain\*（A\* 搜工具空間，評估函數可靠時比 MCTS 省）。

### 程式碼對應表（研究報告 §3.3，直接可用）

```
現有函式              論文角色                整合方式
────────────────────────────────────────────────────
_form_intent()        ToT prompter agent      候選生成（規則表 or LLM，見 §4 分岔）
_score_result()       ToT checker module      加 self-evaluate 預測
gbrain 記憶           SGA-MCTS experience     經驗取代 rollout（zero-LLM 友善）
_recent_queries       ToT memory module       搜索歷史去重
scream-task           ReAcTree 葉節點          任務樹層級分解
_AGENTOS_TOOL_MAP     ToolTree 工具空間        MCTS/RPE 搜工具選擇
_evaluate()           ToT controller          單步 → 樹展開控制器
```

---

## 3. 現況 → 前沿的兩條互補維度

研究報告加了一條我原計劃低估的維度。攤開兩者關係：

- **我的 S1/S2/S3（縱深：讓選擇變聰明）** — 單步決策從「隨機/寫死」變「學來的」：
  學工具選擇 → 加動作類型 → 學選目標。**zero-LLM**。
- **研究的 ToT/World Model（橫展：讓決策變多步）** — 從「單步反應」變「展開樹 + 預測 + 搜索」。
  **LLM-in-loop**（除非走 SGA-MCTS 的 gbrain 快取路徑）。

兩者不互斥：可以先把單步選擇學好（S1），再在其上加前瞻（ToT-lite）。但**橫展這條踩到
zero-LLM 紅線**，是 §4 的分岔。

---

## 4. ⚠️ 戰略分岔（待 Ryan 拍板）：LLM 要不要進 agency？

研究報告的整個藥方是把 LLM 放進 agency 當候選生成器 + 評估器 + world model。
但 agency **現在是真的 zero-LLM**（讀碼確認：純規則表 + RPE，零 LLM 呼叫），
而 CLAUDE.md 鐵則寫「認知在 psi/agency/gbrain，LLM 是 I/O」、ROADMAP 寫「不投推理層」。
這不是能默默合併的技術細節，是專案身份的選擇。三條路：

### 路 A — 守 zero-LLM 純度
agency 維持規則表 + RPE。S_span 走我的 S1→S2→S3（學工具選擇 → 動作類型 → 學選目標），
**不引入 LLM 規劃**。研究報告當「參考 / 暫不採用的方向」。
- 優點：身份一致；agency 24/7 跑不燒 LLM 錢；「自主」不是 LLM 規劃偽裝的
- 缺點：T_lookahead 仍為 0；S_span 天花板較低（學得比較準，但不會前瞻）

### 路 B — 全面採用 LLM 樹搜索（研究報告的方向）
`_form_intent` 改 LLM 生成候選，`_evaluate` 改 ToT 控制器，加 World Model。
最快拿到可見的 S_span + T_lookahead。
- 優點：光錐擴張最大最快；論文對應乾淨；ToT-lite 約 1 天可出雛型
- 缺點：**認知搬進 LLM**，違反 zero-LLM 身份；agency 24/7 × LLM calls = 持續燒錢；
  「Aris 的自主」變成「LLM 的規劃」，誠實標註問題（這是 prompt 塑形不是內生認知）

### 路 C — 混合（我的建議）：gbrain-first，LLM-on-miss
採 SGA-MCTS 精神。**gbrain 經驗快取是主規劃器（zero-LLM）**；只有在 cache-miss
且 exploration 高（現況 ~15%）時，才叫 LLM 做一次前瞻。
- 優點：保住大部分 zero-LLM 精神（多數決策不碰 LLM）；拿到有界的 T_lookahead；
  成本受 15% × miss-rate 兩層閘限制；與專案「gbrain+LLM 是 baseline」一致
- 缺點：實作最複雜（要經驗快取命中判定 + LLM fallback 兩套）；仍需誠實標註
  「前瞻是 LLM 輔助的」
- **證偽條件**：若快取命中率長期太低（多數還是叫 LLM），路 C 退化成路 B 的貴版本 → 回退

> **這格拍板前，S2/S3 的寫入類動作與 world model 都不動手。** 先定方向再落地。

---

## 5. 分階段（路線依 §4 選擇而定）

### Phase S1 — RPE 學工具選擇（三條路都先做，最小最穩）

> ⚠️ **前提：先過 `rpe-evaluation-integrity.md` 的 E1（下游效用信號）。**
> 現在的 `_score_result` 有 len/500 刷分漏洞（讀碼確認）。在 gameable 的分數上讓
> RPE 學工具選擇，只會更快、更持久地學會刷分。評分完整性先於學習擴張。

把 RPE 從「per-angle」擴到「per-(need,tool)」。工具選擇不再 `random()<0.5`，
而是按學來的權重 epsilon-greedy 抽樣。

- `_need_stats[need]` 加 `tool_weights`
- `_form_intent` 工具路由讀 `tool_weights` 抽樣
- `_act` RPE 更新同時寫回 `used_tool`（比照 `used_angle`，過 constitution guard）
- checkpoint 同步含 tool_weights

**為什麼三條路都先做**：這是「把已有多工具接上學習」，zero-LLM，風險最低，且驗證
「S_span 正確定義（多動作 + 學選擇）」是否真產生可測漂移。是後續一切的地基。
自檢 `check-tool-rpe.py`。反悔條件：數週無漂移 → S_span 定義再議。

### Phase S2 — 前瞻 / 第二類動作（形狀依 §4）

- **若路 A**：加「第二類動作」（synthesize/write，非只 retrieve）。⚠️ 寫入類，
  前置 safety gate 4b 必須在位（CLAUDE.md 規則 7）。
- **若路 B/C**：加 T_lookahead。ToT-lite = `_form_intent` 生成 2-3 候選 →
  self-evaluate 預測 outcome → 選最佳 → 執行後 RPE 校正評估器。路 C 額外加
  gbrain 經驗快取，miss 才叫 LLM。

### Phase S3 — 學會選目標（最深，S_span 真前沿，zero-LLM 也能做）

讓 `drive_threshold` / 需求優先序變成 RPE 可影響的量。這是「會改變自己想追什麼」的門檻。
- 候選機制 A：per-need 動態門檻（近期 RPE 高 → 門檻降 → 更常被追）
- 候選機制 B：需求排序的 meta-RPE（學「此 context 優先滿足哪個需求」回報最高）
- **煞車**：憲法 range 硬夾 + 來源預算不可繞過；meta 學習不能讓某需求鎖死/餓死其他。
  持久化煞車延伸到 meta 權重。
- ⚠️ 最容易做出「假 agency」——一條更複雜的規則不是自主。下手前先想清楚證偽條件。

---

## 6. 光錐度量（貫穿全程，必須先定義）

沒有可測指標 = 自我感覺良好。先定義，落 `docs/benchmarks/`：

- **動作多樣性熵**：(need, tool, action_type) 組合的分佈熵。填磚不升，真廣度升。
- **選擇非隨機性**：工具/目標選擇與 RPE 歷史的相關性（學到了=相關；隨機=沒學）。
- **前瞻準確率**（若走 B/C）：預測 outcome vs 實際 RPE 的相關。
- **對照基線**：純規則表 baseline 跑同情境，光錐指標必須顯著高於它，否則該層投資判死。
- 比照 Rust psi-bench 的可重現驗收模式。

---

## 7. 研究報告未觸及的洞（仍需外部研究）

研究報告主打「怎麼搜索 / 怎麼前瞻」（S1/S2 territory + T_lookahead），**幾乎沒碰
S3 的「該追什麼」**（內在動機 / 目標生成）。以下仍開放：

1. **內在動機的形式化**（S3 核心）— drive_threshold 動態化需要理論根據，不是又一條規則。
   候選框架：empowerment、active inference / free energy、autotelic IMGEP / CURIOUS。
2. **目標生成 vs 目標選擇** — 研究只給「在既有選項間選更好」；真 S_span 可能要「生成新子目標」。
   hierarchical goal / option discovery 若有可落地機制，改寫 S3 形狀。
3. **synthesize 的延遲/稀疏獎勵**（S2 路 A）— 「這頁筆記後續有沒有被 recall 用到」是
   延遲信號，credit assignment（discount / eligibility trace）待補。

> 資料進來後，把對應段落升級為「依 <論文> 的 <機制>」，每個機制標可證偽條件。
> **不採用無法證偽的漂亮框架**（CLAUDE.md 誠實鐵則）。

---

## 8. 依賴與順序

```
T_persist ✅
   │
   ▼
S1 (RPE 學工具，zero-LLM) ──驗證「多動作+學選擇」定義──┐
   │ 成立                                            │ 不成立→重議
   ▼
【§4 拍板：路 A / B / C】← 現在卡這裡
   │
   ├─ 路 A → S2(第二類動作,前置 4b) → S3(學選目標)
   └─ 路 B/C → S2(ToT-lite 前瞻) → S3
```

## 9. 邊界 / 不做

- 不碰五維需求結構、持久化煞車邏輯（養成期鐵則）
- 不做 4c RSI（假推理驅動自我改進是本末倒置）
- **⚠️ 與 ROADMAP「不投推理層」的張力**：研究報告的路 B 直接是推理層投資。
  ROADMAP 的警語（20 題 benchmark 沒贏過 gbrain+LLM 就不投）**仍有效** —
  走 B/C 前，§6 的光錐度量要先證明樹搜索版顯著贏過現況 bandit，否則不投。
- 不做無法證偽的「自主性」——一條更複雜的規則不是 agency
