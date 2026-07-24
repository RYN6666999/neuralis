---
title: 安全自我進化路線 — 甲的完整脊椎（防護欄先於能力）
date: 2026-07-17
status: planned (第二組規劃 · 未執行，Stage 0 TaskSpec #1 已建於 branch task-009)
tags: [self-evolution, safety, roadmap, spine, plan]
---

# 安全自我進化路線

> 這是「意圖收斂引擎 v3.1 + 安全自我進化基座」的**脊椎**：把三份既有 spec
> （`cognitive-light-cone-plan` / `rpe-evaluation-integrity` / `line-private-terminal`）
> 依**安全順序**串起來。不重複內容，只定「先做什麼、為什麼是這個順序、哪裡要人拍板」。

## 一條鐵原則：防護欄先於能力

每一個「讓 Aris 能做更多」的能力，前面都必須先站一道對應的防護欄。**順序不可逆。**
沒有防護欄的能力 = 賭。這條原則凌駕進度壓力。

## 三個判準（開任何一階段的能力前，問這三題）

對照協定三柱：
1. **可回退嗎？** 這個動作壞了，能不能一鍵還原、零成本丟掉？
2. **可驗證嗎？** 有沒有客觀信號（pytest 過、任務達成、預算用量）證明它真的好？
3. **不作弊嗎？** 評分權是不是物理隔離在 Aris 碰不到的地方？

三題不全是「能」→ 該動作交人類拍板，不自動放行。

## 北極星：人類最小決策

只在「不可驗證」或「不可回退」的動作上要你介入。可真跑驗收 + 可回退的，全自動
放行/打回，不打擾你。這是目標，不是起點 —— 前期防護欄還沒建齊時，人類閘門會多。

---

## 路線（六階段，每站都能安全停）

### Stage 0 — 甲/乙 硬邊界（進行中）

**防護欄：** Scream 永不得改 Aris 自己的腦；任何自動改動都能還原。

- ✅ **TaskSpec #1**：safety_gate 委派 path-DENY（branch `task-009`，6 測試綠）。
  委派指向 `neuralis/laap/**` 一律 DENY，fail-closed，不可 env/批准繞過。
- ⬜ **TaskSpec #2**：`scream-task` 從 `READONLY_SAFE` 重分類為 write。
  現況它被當唯讀，通道一開會繞過寫入批准閘（潛在 bypass，見 safety_gate 註記）。
- ⬜ **TaskSpec #3**：commit 級快照機制（協定鐵律 2）。委派/自動改動前自動建
  還原點，一鍵 revert。不動 neuralis 持久化層（重快照留到真開乙門）。

**這站的意義：** 就算後面全不做，這三道也讓「Scream 改 Aris 腦」變成物理不可能 +
「任何自動改動可還原」。獨立有值。

### Stage 1 — 評分完整性（任何學習擴張前必修）

**防護欄：** Aris 學習的分數不可作弊，否則越學越壞且永久累積。

- ⬜ **E1**：下游效用信號取代 len/500（`rpe-evaluation-integrity.md`）。
  修掉「寫長垃圾換高分」漏洞。**這是 Stage 4 學習的前提**。
- ⬜ **柱①落地**：評分權物理隔離在 AgentOS，Aris 看不到也改不了 held-out 標準。

**為什麼在能力前：** 在 gameable 分數上讓 Aris 自主做更多 = 更快更持久地學會刷分。

### Stage 2 — 成本閘（委派通道開通前必建）

**防護欄：** 便宜的 Aris 不可無限觸發昂貴的 Scream，否則成本反轉、帳單失控。

- ⬜ **E2**：agency 的 token/compute ledger（`rpe-evaluation-integrity.md`）。
  超預算 → agency 降頻。這是「成本更低分工」不變成「成本爆炸」的唯一保險。

### Stage 3 — 委派通道（先接通，寫入每次過閘）

**能力（第一個真能力，但被 Stage 0-2 防護欄包住）：**

- ⬜ `scream-task-executor`：stub → 真的呼叫 Scream。
- 唯讀/淺委派可自動；**write-capable 委派每次過 4b 批准閘**（不自動）。
- path-DENY（Stage 0）+ 成本閘（Stage 2）+ 快照（Stage 0）此時全在位。

### Stage 3.5 — 評分路由 + 沙箱 canary（讓 Ryan 佔比可控下降）

**能力：** 每個動作先打分 → 四條路（硬拒 / 問人 / 沙箱跑 / 自動）。一類任務在沙箱被
客觀驗證做對夠多次，門檻才往下移一格（問人→沙箱→自動）。Ryan 注意力佔比 = 還卡在
「問人」的比例，隨各任務類畢業自然下降。

**防護欄：** 裁判/評分規則/門檻物理隔離在 Aris 碰不到處（柱①）；可回退性是硬地板
（「潑得出去」的動作永遠封頂在問人）；鑰匙永遠在 Ryan（一鍵停 + 信任歸零）。
🔴 不准把「降低 Ryan 佔比」設成 Aris 的優化目標（衝數字 = 通往不安全，同 len/500 坑）。

**這站解掉 stub 死結：** executor 在沙箱**真跑**（真結果非假數據）→ 合法落地、非法撤回。
「預判」= 真跑可撤，不是用猜的。詳見 `scoring-router-canary.md`。

---

### Stage 4 — 分工學習 + 前瞻（甲的核心，走 §4 路 C）

**能力：** Aris 學會「什麼時候委派 Scream 划算」+ 有界前瞻。光錐 §4 已拍板 **路 C**
（gbrain-first，LLM-on-miss，終態 c2=委派 Scream 做前瞻，agency 維持 zero-LLM）。

- ⬜ **C-a（zero-LLM，可先做，不需 E1/E2）**：gbrain 經驗快取當主規劃器 + 量
  cache-hit 率。這是 C 的證偽測試，也是平行 agent S_span Phase 2 的**正確方向**
  （取代原路 B）。
- ⬜ 光錐 **S1** 延伸：Aris 學「自己查 vs 委派 Scream 深做」，用 **E1 不可作弊信號**。
- ⬜ **C-b（有界 LLM-on-miss，prefer c2）**：命中率過關才加；前置 **E1 + E2**。
- ⬜ **E3 / 柱②**：異質任務集 + baseline，量 S_span/前瞻是否真的 > 純規則表。
- 此站達成 = 你設想的「Aris×Scream 成本更低分工」，agency 全程 zero-LLM
  （LLM 深工作外包 Scream = c2，繞過 §4 zero-LLM 難題）。

**這站是甲的終點。** 到這裡系統已經很強且全程安全可逆。**預設就停在這。**

### Stage 5 — 乙門（若真要開，人類專屬鑰匙）

**⚠️ 這站預設不做。** 開門 = 讓另一個 agent 有權改 Aris 的認知碼。前提：

- 三柱**全部有證據**在位（不是宣稱）：Stage 0-4 的快照 + 客觀驗收 + 評分隔離都跑過。
- **人類一次性明確授權**，鑰匙永遠在 Ryan，系統不准自跨門（協定結論 2/3）。
- Aris 自身狀態/權重的**重快照**（不只 commit 級）。
- 即使開，也只在**人類監督下、對特定有界改動**選擇性解除 path-DENY，事後立即復原。

Weco AIDE² 的教訓（`rpe-evaluation-integrity.md` §3）：連手工調兩年 + 客觀 ML eval
都只到 Level 1、產物難維護。neuralis 沒那前提，**這站更像「永遠備而不用」的理論終點**，
不是進度目標。

---

## 人類閘門一覽（哪裡自動、哪裡要你）

| 階段 | 自動放行 | 要 Ryan 拍板 |
|---|---|---|
| Stage 0-2（防護欄） | 通過 pytest 的實作 | 每個 TaskSpec 收斂後的 □通過 |
| Stage 3 委派通道 | 唯讀/淺委派 | **每次 write-capable 委派**（4b） |
| Stage 3.5 評分路由 | 沙箱可回退類（已畢業） | 潑得出去的類 + 未畢業類 + 首次畢業到自動(policy b) |
| Stage 4 分工學習 | RPE 權重調整（可回退） | 動 agency 核心（_ANGLE/psi_core）= 獨立審批 |
| Stage 5 乙門 | 無 | **全部**（一次性人類授權，不可自動） |

## 依賴序（防護欄→能力）

```
Stage 0 硬邊界（path-DENY ✅ / 重分類 / 快照）
   │
   ▼
Stage 1 評分完整性（E1 + 柱①）──┐ 前提於所有學習
   │                          │
   ▼                          │
Stage 2 成本閘（E2）───────────┤ 前提於委派通道
   │                          │
   ▼                          │
Stage 3 委派通道（4b 每次）◄────┘
   │
   ▼
Stage 3.5 評分路由 + 沙箱 canary + 信任 ratchet（哪些自動、哪些問人）
   │
   ▼
Stage 4 分工學習（S1 + E3）= 甲的終點，預設停這
   │
   ▼（僅人類一次性授權）
Stage 5 乙門（備而不用）
```

## 邊界 / 不做

- 預設路線到 Stage 4 為止（甲）。Stage 5 是理論終點，非進度目標。
- 每階段能力開通前，對應防護欄必須先通過自檢。順序不可為了進度跳過。
- 任何「系統自己決定開下一階段」都是紅線 —— 階段推進永遠是人類拍板。
- 不把評分器/憲法/safety_gate 納入任何未來自我改寫範圍（它們是裁判，裁判不下場）。

## 相關

- `cognitive-light-cone-plan.md` — S1/S2/S3 + zero-LLM §4 分岔（Stage 4 主體）
- `rpe-evaluation-integrity.md` — E1-E4 + AIDE² 反作弊（Stage 1-2 主體）
- `line-private-terminal-plan.md` — 獨立 I/O 擴展，不在本脊椎依賴鏈上，隨時可做
- `scoring-router-canary.md` — 評分路由 + 沙箱 canary + 信任 ratchet（Stage 3.5 主體）
