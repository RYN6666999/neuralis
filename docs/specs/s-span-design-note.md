# S_span（行為廣度）設計筆記

> 2026-07-15 | Ryan + Scream Code 共同定稿

## 問題

先前認為「行為豐富度 = 五個需求都有 _ANGLE 查詢角度」。在此認知下，certainty/competence/growth 已通，
relatedness 在 `a5c4f94` 加入五個角度（「你/我們/陪伴/一起/感覺」），autonomy 暫無。

## 糾正

經過 `a5c4f94` 驗證（58 次自主行動，relatedness 零命中），且分析發現：

**五個需求鋪滿查詢角度不是行為豐富度，是裝飾。** 原因是：

1. **relatedness 不該有查詢角度**——它的核心是「被陪伴/被回應/連結」，不是查資料。
   gbrain 查「陪伴」「感覺」只是文字匹配，沒有 relational computing。
   把它留著只讓晨報數字好看，但系統行為沒有任何改變（competence drive 永遠佔優）。

2. **autonomy 不需要獨立角度**——它是 contradiction in terms：
   `_form_intent("autonomy") → gbrain("seed 自由 選擇")` 是在執行一條寫死的規則說「搜關於自主的東西」，
   這不是自主。Autonomy 的本質是 self-determination，由 agency loop 本身自然滿足
   （每次根據內部 drive 自選下一步 = 行使自主）。

## 決定

- **relatedness**：撤掉 `_ANGLE` 假角度，改誠實註解。它的滿足途徑是被動的：
  `process_input()` +0.02/次、NEED_KEYWORDS 情感詞匹配、trust 系統、note_interaction。
  在唯讀限制（gbrain/qmd/file-search）下沒有「不是表演」的動作。
- **autonomy**：不進 `_ANGLE`。target 維持 0.7，若晨報顯示偶爾越閾再調低。
  不需要獨立動作，因為 loop 本身就是自主。

## 對 S_span 的新理解（核心糾正）

**S_span 不是「五個需求都有角度」，而是「既有需求有不同種類的動作」。**

Competence 現在只有 gbrain query 一種。真正的廣度軸擴張路徑是：

1. 給 competence 開第二種動作工具（file-search / qmd / skill executor）
2. 讓同一需求在不同工具間選擇
3. 按 RPE 學習哪種工具在當前 context 更有效

相比之下，填滿五個需求的查詢角度 = 鋪同樣的磚在不同坑裡，沒有增加行為的多樣性。

## 靶

| 順位 | 內容 | 前置條件 |
|------|------|---------|
| 1 | competence 第二工具（file-search/qmd/skill executor） | 需確認工具白名單 + safety gate 批准 |
| 2 | 工具選擇納入 RPE 學習 | 需有 ≥2 工具才需要學 |
| 3 | 若長期無互動，relatedness drive 升高到足以影響需求排序 | 被動滿足鏈驗證（無需改碼） |

## 相關檔案

- `laap/agency.py` — `_ANGLE` 定義、`_form_intent` 邏輯、`_act` 工具執行
- `scripts/morning-brief.py` — 行為豐富度報告
