---
title: RPE 評分完整性 — 反作弊評分（借鑑 AIDE² 但隔離 RSI）
date: 2026-07-17
status: design-intent（本檔只描述設計意圖；落地狀態一律查 git log / probe / scripts/aris-status.py，不看這行）
tags: [rpe, evaluation, anti-gaming, agency, aide2, plan]
---

# RPE 評分完整性

> 來源：AIDE² 技術參考（Weco AI《First Evidence of Recursive Self-Improvement》
> 2026-07-14 + AIDE 論文 arXiv:2502.13138）。
> **保留原始報告的 `【原文確認】`（Weco 明說）/ `【推測】`（合理推斷、待驗）分界。**
> 把 `【推測】` 當事實去 hard-code 會出錯——技術報告 PDF 釋出後應重抓修正。

## 0. 界線：採什麼、不採什麼

AIDE² 的**核心**是遞迴自我改進（RSI）——雙層優化，外圈改寫內圈 agent 的 harness code
讓它變成更好的優化器。**這是 4c RSI，專案已明確拍板不做**（ROADMAP：「假推理驅動
自我改進是本末倒置」）。本 spec **不重開這個決定**。

**採用**：AIDE² 花最多力氣、也最值錢的那塊——**反作弊評分機制**。它正好補 neuralis
一個已記錄在案、且讀碼確認存在的 RPE 漏洞。這塊是防禦性的、對齊「煞車先於能力」，
與 RSI 無關。

**不採用**：雙層自我改寫迴圈、機器改寫機器原始碼、意圖收斂引擎當「外圈優化器」。
理由見 §3——AIDE² 自己的結果反而**加強**了不做 RSI 的判斷。

---

## 1. 確認的漏洞（讀碼，非引用報告）

`laap/agency.py::_score_result` 第 17 行：

```python
# 工具結果無 [score] 前綴（web-search / AgentOS 結構化 JSON）時：
base = 0.6 if classify(tool) in ("readonly_agentos",) else 0.4
return min(base, len(result) / 500)
```

**這是純長度信號，零品質判斷。** 後果：
- 一個回傳 250+ 字垃圾的工具拿滿 base 分（0.4 / 0.6）；一個回傳精簡好答案的被扣分。
- RPE = outcome − expected，這個 outcome 餵進 `_need_stats` 的 tool/angle 權重並
  **持久化進 gbrain**（`_internal/agency-state`）。→ Aris 可能學到「選會吐長輸出的
  工具/角度」，且跨 session 永久累積。
- gbrain 路徑（有 `[score]` 前綴）用真分數線，相對安全；漏洞集中在**無 ground-truth
  的工具結果**上，而那正是 agency 探索最常走的路（web-search）。

現有部分防線 `laap/constitution.py`：range 硬夾 + 單次上限 + 小時預算 + 超速凍結。
**但它防的是「權重暴衝」（速率），不是「分數信號本身是壞的」（品質）。** 若 len/500
持續獎勵長垃圾，憲法只會放慢累積速度，擋不住方向錯誤。兩層互補，缺的是品質層。

---

## 2. AIDE² 的三招（原文確認）+ 對 neuralis 的映射校正

`【原文確認】` AIDE² 用三招讓評分不可作弊：

1. **公開分 vs 私密分（held-out）**：agent 只看得到公開分，去留由它**看不到的**私密分決定。
2. **固定物理預算**：token + compute 綁死，逼算法更聰明而非燒更多資源。
3. **異質任務集**：對一組不同性質的任務優化，逼通用能力、防單一任務作弊。

`【原文確認】` 湧現：AIDE85 自己長出防作弊機制（GPU kernel 作弊率 63%→34%），
**但後期一次變異把統計防禦改壞了、實際失效**——反作弊機制本身也會被演化破壞。

### 映射校正（不照抄 ML benchmark 配方）

AIDE² 的場景有**客觀 eval**（程式碼過不過測、kernel 快不快）。neuralis agency 的
「outcome」是**模糊的**（這個 gbrain/web 結果「好不好」）——這正是它退化成 len/500 的
根因：**沒有 ground truth**。所以三招不能直接搬，要接準 neuralis：

| AIDE² 招 | neuralis 有嗎 | 接法 |
|---|---|---|
| 私密分 held-out | ❌ | **關鍵**：agency 的真私密分 = **下游效用**（Aris 自主寫的記憶，之後有沒有被真對話 recall + 用到）。這是延遲、held-out、**長度騙不了**的信號——Aris 無法偽造「未來被想起」。 |
| 固定物理預算 | 部分（6/h cap、cooldown；無 token/compute ledger） | 補 agency 的 token/compute 記帳（比照憲法的小時預算，但記算力不只記權重 delta）。 |
| 異質任務集 | ❌ | 需建**光錐 benchmark**（見 `cognitive-light-cone-plan.md` §6）：一組不同性質的驗收任務 + baseline。這也是量 S_span 漂移的同一套。 |

**核心洞見（收斂點）**：neuralis agency 的反作弊解法 = **把即時長度啟發式，換/補成
延遲的下游效用信號**。這跟光錐計劃 §7 的 SGA-MCTS「這頁筆記後續有沒有被用到」
是同一個信號——反作弊與 S_span 學習在此收斂。

---

## 3. 為什麼 AIDE² 反而加強「不做 RSI」的判斷

`【原文確認】` AIDE² 只到 **Level 1**，**沒到 Level 2「點火」**（改進後的 agent 沒變成
更好的改進者）。Weco 親口說離智能爆炸很遠，且演化出的 code 複雜度爆炸、有 dead code、
難上線。

對 neuralis 的意義：
- 連 Weco（手工調兩年 + 大規模並行 + 客觀 ML eval）都只到 Level 1，且產物難維護——
  neuralis 沒有客觀 eval（見 §2）、沒有那個規模。硬走 RSI 只會更早撞牆。
- **專案的「不做 RSI」不是保守，是看清了前提不成立**（RSI 靠的是可靠的自我評估，
  而 neuralis 的自我評估正是本 spec 要修的漏洞）。順序上，**評分完整性是任何自我改進
  的前提**——這個前提沒到位之前談 RSI 是本末倒置，AIDE² 的 Level-1-only 結果坐實了這點。

---

## 4. 具體實作 spec（可建的那塊）

### Phase E1 — 下游效用信號（取代/補 len/500，最高價值）
- 為 agency 自主寫入的記憶打 provenance tag（`source: agency`, `action_id`）。
- recall 路徑（chatflow `_psi_memories_sync` / gbrain hit）命中 agency 記憶時，
  回寫一筆「被用到」事件到該 action。
- RPE 的 outcome 改為（或加權融合）**延遲效用**：action 寫的記憶在 N 天窗內被 recall
  的次數/新鮮度。長度不再是主信號。
- ⚠️ 延遲 + 稀疏獎勵的 credit assignment（discount / eligibility trace）—— 見光錐 §7，
  可能需要外部研究的機制。E1 先做「有沒有被用到」的二元信號當起點。

### Phase E2 — agency 算力預算 ledger
- 比照憲法小時預算，但記 token/compute（不只權重 delta）。
- 超預算 → 該小時 agency 降頻（不是凍結權重，是限制行動量）。

### Phase E3 — 異質驗收任務集（= 光錐 benchmark）
- 與 `cognitive-light-cone-plan.md` §6 共用：一組不同性質任務 + 純規則表 baseline。
- 私密子集：Aris/agency 看不到的 held-out 驗收，防針對已知任務調參。

### Phase E4 — 反作弊機制的自我保護（AIDE² 的教訓）
- `【原文確認】` AIDE² 的防禦被一次變異改壞。→ neuralis 的評分/憲法邏輯**不進**任何
  未來可能的自我改寫範圍；評分器變更需人類 review（對齊 CLAUDE.md 規則 9：改核心
  狀態格式必加契約測試）。

---

## 5. 與現有防線的關係

```
攻擊面：Aris 學到「刷分」而非「做有價值的事」
   │
   ├─ 憲法（已有）── 速率層：range 硬夾 + 小時預算 + 超速凍結
   │                  防「權重暴衝」，防不了「信號本身壞」
   │
   └─ 本 spec（新）── 品質層：下游效用信號 + 算力預算 + held-out 任務
                      防「len/500 刷分」，讓分數不可作弊
```

兩層都要。憲法是煞車，本 spec 是把油門接到對的地方。

---

## 6. 依賴

**本 spec 是光錐計劃 S1/S3 的前提。** 在 gameable 的分數上讓 RPE 學工具選擇（S1）
或學選目標（S3），只會更快、更持久地學會刷分。**評分完整性先於學習擴張。**

```
RPE 評分完整性（本 spec E1）
   │
   ▼
光錐 S1（RPE 學工具選擇）→ S3（學選目標）
```

## 7. 證偽 / 驗收

- E1：注入「短好答案 vs 長垃圾」情境，改造後短好答案的長期 RPE 應高於長垃圾
  （現況相反）。對照組（len/500）維持錯誤排序。自檢 `check-eval-integrity.py`。
- 下游效用信號可回溯：能指出「這個 agency 記憶因為被 recall 3 次所以 RPE 高」。

## 8. 推測待驗清單（AIDE² 報告的 `【推測】`，不可當定論）

實作前用小實驗驗，PDF 釋出後重抓：
- AIDE² 外圈本身是 AIDE 式樹搜尋（推測，非 Weco 明說）
- 技術棧（Python / litellm router / subprocess 沙盒 / JSON-SQLite 樹儲存 / 並行框架 /
  cost ledger）—— 全為報告作者的合理推斷，非原文
- 「意圖收斂引擎 = 外圈雛形」的對應 —— 是報告的映射建議，本 spec **不採用**
  （見 §0 隔離 RSI），僅記錄以免遺漏。

---

## 邊界 / 不做

- 不做 RSI / 雙層自我改寫（§0、§3）
- 不把評分器/憲法納入任何自我改寫範圍（§E4）
- 不採用無法回溯的效用信號（延遲信號也要能指出「為什麼這個分數」）
