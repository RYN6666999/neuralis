---
title: 評分路由 + 沙箱 canary + 信任 ratchet — 甲的「人類最小決策」機制
date: 2026-07-24
status: design-intent（本檔只描述設計意圖；落地狀態一律查 git log / probe / scripts/aris-status.py，不看這行）
tags: [self-evolution, safety, routing, canary, sandbox, ratchet, plan]
---

# 評分路由 + 沙箱 canary

> 這是 `safe-self-evolution-route.md` 的 **Stage 3.5**（在「委派通道」與「分工學習」之間）。
> 回答一個問題：Aris 怎麼**在安全範圍內學會判斷，讓 Ryan 每次都要拍板的比例慢慢降下來**，
> 而不是一次把自主權全給、也不是永遠每件事都問人。

## 一句話

每個 Aris 想做的動作，先**打分**，分數決定它走四條路的哪一條：硬拒 / 問人 / 沙箱跑 / 直接做。
一類任務在沙箱裡**被客觀驗證做對夠多次**，門檻才往下移一格（問人→沙箱→自動）。
Ryan 的注意力佔比 = 還卡在「問人」的動作比例，它隨各任務類畢業自然下降。

---

## 0. 北極星與一條紅字警告

**北極星：** 只在「不可驗證」或「不可回退」的動作上要 Ryan 介入；可真跑驗收 + 可回退的，全自動放行/打回。

**🔴 紅字：不准把「降低 Ryan 佔比」設成 Aris 要優化的目標。**
一旦獎勵它「讓人少管」，它就有動機把動作硬塞進自動放行去衝數字 —— 與 `len/500` 刷分同一個坑。
佔比下降是**量出來給人看的輸出**，不是它去追的靶。Aris 追的永遠是「這動作可回退嗎、驗證過嗎」。

---

## 1. 第三扇門：沙箱 canary（解掉 stub 死結）

原本卡在二選一：
- 假的手（executor = stub）→ 回假數據 → 學歪 ❌（禁）
- 真的手（直接接 Scream）→ RCE 面 → 未證泛化就開 = 賭 ❌

**第三條：executor 在沙箱裡真跑一遍，結果先不算數，裁判判合不合法，合法落地、非法撤回。**

關鍵：沙箱裡「**真跑**」拿到的是**真結果**，不是假數據 → 解掉「學歪」紅線。
「預判」的定義**必須是「真跑、可撤」**，不是「用猜的」（猜=又變假數據，回原點）。

## 2. 任務分類（沙箱關不住外部世界）

沙箱只關得住**檔案 / 純計算**。收不回來的副作用（網路請求、花錢、發訊息、動外部 API）
潑出去撤不掉。所以動作先分兩類，這是**可回退性的硬地板**：

| 類別 | 例子 | 沙箱能保護？ | 預設路由上限 |
|---|---|---|---|
| **關得住** | 寫檔、算數、產草稿、本地重構 | ✅ 可撤回 | 可畢業到自動 |
| **潑得出去** | 發網路/API、花錢、發訊息、改外部狀態 | ❌ 撤不掉 | **永遠封頂在「問人」** |

分類表由人維護，新任務類預設歸「潑得出去 / 問人」直到證明可關得住。

**初版分類表（2026-07-24 Ryan 拍）：**

🟢 關得住（沙箱可撤，有履歷後可畢業自動）
- 本地檔案寫入/編輯（sandbox workspace 內）· 純計算/分析/草稿生成 · 本地程式碼重構
- gbrain 讀取（query/get/search）· 產 morning brief 草稿（只產不發）· 跑本地測試（pytest）

🟠 潑得出去（撤不掉，永遠封頂問人）
- 發網路請求/呼叫外部 API · 花錢/觸發大量付費 token · 發訊息（LINE/TG/email）
- git push/動遠端 repo · 動 launchd/系統設定/改 gbrain 之外的外部狀態

⚪ 邊界（預設歸問人，未談清前不放寬）
- **gbrain 寫入（put_page）**：改的是 Aris 自己的記憶。雖有 page_versions 可回退，但動自己的腦敏感 → 暫歸問人。放寬與否待 Ryan 拍。

---

## 3. 評分四維

每個動作打分，看四個維度：

| 維度 | 問什麼 | 高分 = |
|---|---|---|
| **可回退性** | 壞了收得回嗎？ | 「關得住」類（沙箱可撤） |
| **可驗證性** | 有客觀訊號證明它對嗎？ | 有 pytest / 任務達標 / held-out 分 |
| **信心 × 歷史** | Aris 多確定 + 這類**以前被驗證對過幾次** | 同類驗證成功累積多 |
| **成本** | 燒多少 token/算力（接 E2 ledger） | 在預算內 |

## 4. 四條路由 lane

```
🔴 硬拒       碰 Aris 自己的腦 / 碰裁判 / 碰憲法 / 爆硬預算 → 永遠不准，分數再高也不行
🟠 問人(4b)   收不回 或 沒法驗 或 信心低 或 全新沒做過 → Ryan 拍板
🟡 沙箱canary 收得回 + 可驗，但歷史不夠厚 → 沙箱真跑，裁判判：過=落地+記帳，敗=撤回+記帳（不煩人）
🟢 自動放行   收得回 + 可驗 + 歷史夠厚 → 直接做（不煩人）
```

沙箱 canary 是**斜坡**：它不煩人，但每跑一次就在替該任務類**攢履歷**。

---

## 5. 信任 ratchet（Ryan 佔比怎麼降）

每一類任務有一個**信任等級**，只靠**客觀驗證成功**往上爬——
不是 Aris 自報，不是「Ryan 以前批准過一次」（舊批准搭便車是延遲安全洞，見 07-18 撤 approved-tools 教訓）。

```
一個新任務類：問人 →（沙箱累積驗證成功）→ 沙箱canary →（夠厚）→ 自動放行
              人每次都管         人不管單次、它在攢履歷        人完全不用管
```

**ratchet 規則：**
- **難爬易崩（不對稱）：** 做對慢慢加；出一次錯/一次 divergence → 大扣或直接降級。防手氣好連過幾次誤畢業。
- **最小樣本閘：** 畢業要過樣本數下限 + 信賴區間，不是「連過 3 次就升」。
  （E3 目前只 102 樣本 → 現階段沒有一類該畢業到自動，先全走沙箱累積。）
- **首次畢業到「自動」由誰放行？→ Ryan 2026-07-24 拍 (b)：** 每類**第一次**進「自動」
  要 Ryan 一次性簽核，ratchet 自己絕不自動升 auto（發 `needs_ryan_signoff` 事件）。

## 6. 硬不變量（路由器自己碰不到）

1. **裁判 + 評分規則 + 門檻**擺在 Aris 碰不到的地方（AgentOS 側，柱①）。否則它學會「專門生產能自動放行的動作」= 作弊。
2. **可回退性是硬地板，不是分數。** 「潑得出去」類永遠封頂在問人，履歷再厚不自動畢業。
3. **鑰匙永遠在 Ryan。** 一鍵停 + 任一類信任**歸零重來**。
4. **裁判/憲法/safety_gate 不納入任何自我改寫範圍**（裁判不下場）。

## 7. 零件盤點：已有 vs 新蓋

| 需要 | 現況 | 來源 |
|---|---|---|
| 可回退（沙箱 checkpoint/rollback） | ✅ 已有 | agent-sandbox（07-22/23，TOCTOU 已修） |
| 裁判在外（gate_verdict） | ✅ 已有 | agent-sandbox |
| 成本閘（token/compute ledger） | ✅ 已有 | E2 |
| 碰腦硬拒（path-DENY） | ✅ 已有 | safety_gate（Stage 0，task-009） |
| 雙路徑跑+比對管路 | 🟡 半成品，**用途要改** | shadow 比對層（07-23）：現用途=驗沙箱橋，要轉成「判動作 verdict」 |
| 信心/歷史（RPE 權重 + 憲法夾值） | 🟡 部分 | 缺「每任務類的信任履歷 + 畢業門檻」 |
| **評分路由器本體 + 信任 ratchet** | ⬜ **要新蓋** | 本 spec 的主體 |

**真正要蓋的只有兩塊：** 路由器本體（打分→分路）+ 信任 ratchet（按履歷移門檻）。其餘是串接既有零件。

## 8. 未解 / 誠實邊界

- **下游效用訊號（E1.2）在沙箱測不到。** 沙箱跑完就撤的成果沒真被下游用到 → 那個「被 recall 才有獎」的獎不會完整觸發。
  結論：**沙箱 canary 驗得了「這任務成/敗」（客觀），驗不了「長期有沒有用」**。後者要等真落地才測得到。
- **任務分類的邊界案例**：一個動作先寫檔（關得住）再觸發外部同步（潑得出去）→ 算哪類？預設取最嚴（潑得出去 / 問人），除非能拆成兩步分別過閘。
- **泛化證據仍薄**：E3 只 102 樣本。ratchet 的最小樣本閘要先設好，否則等於在薄證據上自動畢業 = 賭。

## 9. 落地順序（2026-07-24 排期：只做前置低風險塊，executor 暫不接真）

平行分工（Ryan 手動驅動 Scream，非 Aris 自主委派，不過甲的閘）：

**Scream → `~/agent-sandbox`**（裁判層，物理隔離在 Aris 外）
- B1 Verdict v2（`contracts/`）· B2 評分函式（`router/`）· B3 分類表 loader ·
  B4 信任 ratchet（policy b：畢業 auto 必過 Ryan 簽）· B5 內部串接。
- brief：`~/agent-sandbox/SCREAM-TASK-scoring-router.md`

**另一手 → `~/Developer/neuralis`**（bridge）
- shadow 比對層轉用途：「驗沙箱橋」→「輸出動作 verdict」（複用既有雙路徑管路）。

**接縫：** `~/agent-sandbox/docs/verdict-contract.md`（ActionRequest / Verdict v2）。
兩邊只跟契約，不改對方檔。

**暫不做（等 Ryan 親自把關）：** executor 接真 Scream（Stage 3 stub→真，RCE 面）。
本階段全是休眠鷹架，review 後才算數。

**預設仍停在甲。** 本層不開乙門，不動 Aris 認知碼。全程 zero-LLM agency。

## 10. 2026-07-24 執行層事故與修復（bridge-connected 後）

### 事故 A：sandbox lane 觸發後 bridge 重試風暴

- 症狀：同一 entry 持續重跑，log 重複出現 `slice(None, 120, None)`。
- 根因：`result.error` 在 sandbox path 是 dict，failure path 直接做字串切片。
- 修復：bridge 端新增通用字串化 helper，所有 error/audit/failure path 先 stringify 再截斷。

### 事故 B：審計寫檔路徑對非字串 error 不穩定

- 症狀：`result.error[:200]` 遇 dict 崩潰，導致審計與主流程互相拖累。
- 修復：audit payload 改為 `_stringify_for_log()` 統一處理。

### 現在的硬規則（新增）

1. 任何進 audit/failure 的欄位都必須先 normalize 成字串。
2. logging 失敗不得影響 lane 主流程（fail-open logging）。
3. 測試樣本（ratchet 注入）必須與生產狀態隔離，驗證後回滾。

## 相關

- `safe-self-evolution-route.md` — 脊椎，本 spec = 其 Stage 3.5
- `cognitive-light-cone-plan.md` — §4 路 C（Stage 4 主體）
- `rpe-evaluation-integrity.md` — E1-E4 + AIDE² 反作弊（評分完整性 = ratchet 的前提）
- agent-sandbox — 沙箱 checkpoint/rollback + gate_verdict + shadow 比對層（零件來源）
