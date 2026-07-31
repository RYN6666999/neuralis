# Aris 沙箱自主改進、決策學習與人類治理系統

> 安全試驗線 + 決策學習線 + 人類治理線

---

## 文件結構

```
aris-sandbox-learning/
├── index.md                           ← 本檔案：總覽、撰寫順序、狀態追蹤
├── part-01-principles.md              # 第一部：定位與原則（Ch 0～3）✅ 已寫
├── part-02-full-flow.md               # 第二部：完整運作流程（Ch 4～5）✅ 已寫
├── part-03-sandbox.md                 # 第三部：沙箱與能力邊界（Ch 6～8）✅ 已寫
├── part-04-decision-analysis.md       # 第四部：候選方案與決策分析（Ch 9～12）✅ 已寫
├── part-05-external-ai.md             # 第五部：外部 AI 參謀（Ch 13～16）✅ 已寫
├── part-06-learning.md                # 第六部：自主學習系統（Ch 17, 19～31）✅ 已寫
├── part-06-ch18-learning-case-format.md  # 第 18 章：單次學習案例格式 ✅ 已寫
├── part-07-governance.md              # 第七部：人類治理與正式落地（Ch 32～35）✅ 已寫
└── part-08-implementation.md          # 第八部：驗收與實作（Ch 36～39）✅ 已寫
```

## 建議撰寫順序

不要照章號從頭硬寫。依賴順序是：

| 順序 | 範圍 | 原因 |
|------|------|------|
| 1 | **第 0～5 章**（part-01, part-02） | 先說清楚系統要做什麼 |
| 2 | **第 17～19 章**（part-06 開頭） | 先定義 Aris 到底要學什麼資料 |
| 3 | **第 6～8 章**（part-03） | 建立安全試驗場 |
| 4 | **第 9～16 章**（part-04, part-05） | 建立決策與外部參謀輸出 |
| 5 | **第 20～31 章**（part-06 後半） | 建立學習、校準、防作弊 |
| 6 | **第 32～39 章**（part-07, part-08） | 最後補人類治理、落地與實作 |

> **最重要的是先寫第 18 章「單次學習案例格式」。**
> 沒有一致的案例資料，後面的自主學習都只會變成 Aris 自己講故事。

## 撰寫狀態

- [x] part-01 — 定位與原則（Ch 0～3）
- [x] part-02 — 完整運作流程（Ch 4～5）
- [x] part-06-ch18 — 單次學習案例格式（Ch 18）
- [x] part-03 — 沙箱與能力邊界（Ch 6～8）
- [x] part-04 — 候選方案與決策分析（Ch 9～12）
- [x] part-05 — 外部 AI 參謀（Ch 13～16）
- [x] part-06 — 自主學習系統（Ch 17, 19～31）
- [x] part-07 — 人類治理與正式落地（Ch 32～35）
- [x] part-08 — 驗收與實作（Ch 36～39）

## 相關文件

- [`safe-self-evolution-route.md`](../safe-self-evolution-route.md) — 前期安全自主演化路線
- [`core-architecture.md`](../parked/core-architecture.md) — Neuralis 核心架構
- [`ecosystem-architecture.md`](../ecosystem-architecture.md) — 生態系統架構

## 名詞對照

| 中文 | English | 說明 |
|------|---------|------|
| 沙箱 | Sandbox | 隔離的開發與測試環境，不影響正式系統 |
| 候選變更包 | Candidate Change Package | 一個完整的提議變更，含 diff、測試結果、分析 |
| 四面向分析 | Four-Facet Analysis | 好處、壞處、風險、代價 |
| 學習案例 | Learning Case | 一次完整的改進循環記錄 |
| 外部 AI 參謀 | External AI Advisor | 提供第二意見的外部 AI 模型 |
| Shadow mode | Shadow Mode | 新策略僅輸出建議，不實際執行 |
| Canary | Canary | 小範圍限時試驗，用於驗證策略 |
| Held-out 驗證 | Held-out Validation | 用未參與訓練的資料驗證策略 |