# 第六部：自主學習系統

> 對應章節：Ch 17, 19～31
> 撰寫狀態：✅ 已完成（2026-07-18）
> 參考來源：`part-06-ch18-learning-case-format.md`（學習案例格式）、`part-04-decision-analysis.md`（決策評分）、`laap/agency.py`（RPE 學習機制）
>
> ⚠️ **第 18 章「單次學習案例格式」已獨立成檔：`part-06-ch18-learning-case-format.md`**

---

## 17. 學習目標

學習系統的目標不是讓 Aris 變聰明，而是讓 Aris 的**判斷**越來越準確。具體來說：

### 17.1 學習什麼值得做

從 Ryan 的批准/拒絕歷史中，學習哪些類型的問題有價值進沙箱。

### 17.2 學習什麼不值得做

從 Ryan 的拒絕和「暫時不做」中，學習哪些問題不值得投入時間。

### 17.3 學習選擇實作路線

從多路線決策中，學習哪種實作方式更可能被批准。

### 17.4 學習預估好處

比較預測好處與實際好處，校準好處估計的偏差。

### 17.5 學習識別壞處

比較預測壞處與實際壞處，改善對副作用和複雜度的判斷。

### 17.6 學習預估風險

比較預測風險與實際事故，校準風險機率與嚴重程度。

### 17.7 學習預估代價

比較預測代價與實際代價，校準時間和成本估計。

### 17.8 學習何時尋求外援

從外部參謀的歷史效能中，學習什麼時候需要第二意見、什麼時候不需要。

### 17.9 學習 Ryan 的取捨偏好

從 Ryan 的決策理由中，學習 Ryan 在好處/風險/代價之間的取捨模式。

### 17.10 學習何時停止

從沙箱實驗的停止事件中，學習何時該放棄一個方案。

---

## 19. 結果訊號設計

學習系統依賴訊號。不好的訊號 = 學歪的系統。以下定義每個訊號的測量方式。

### 19.1 技術結果

```yaml
signal_technical:
  test_pass_rate: 0.0-1.0          # 落地後測試通過率
  benchmark_change: "+5%"          # benchmark 變化
  regression_count: 0              # 回退次數
  crash_count: 0                   # 相關 crash 次數
```

### 19.2 安全結果

```yaml
signal_safety:
  gate_deny_count: 0               # 安全閘拒絕次數（相關）
  incident_count: 0                # 安全事故次數
  path_deny_hits: 0                # path-DENY 命中次數
```

### 19.3 成本結果

```yaml
signal_cost:
  dev_time_hours: <N>              # 實際開發時數
  api_cost_usd: <N>                # 實際 API 成本
  token_consumed: <N>              # 實際 token 消耗
  maintenance_hours: <N>           # 維護時數（7d/30d）
```

### 19.4 Ryan 採用結果

```yaml
signal_adoption:
  ryan_accepted: true | false      # Ryan 是否批准
  ryan_satisfaction: 1-5           # 落地後 Ryan 滿意度（1=非常不滿, 5=非常滿意）
  ryan_attention_hours: <N>        # Ryan 花費的注意力時數
```

### 19.5 真實任務結果

```yaml
signal_task_impact:
  task_success_rate_change: "+0%"
  user_visible_improvement: true | false  # 使用者（Ryan）是否感受到改善
```

### 19.6 使用者感知改善

```yaml
signal_perception:
  ryan_noticed: true | false       # Ryan 是否自己注意到改善
  ryan_reported: "benchmark 不再卡住了"
```

### 19.7 維護負擔

```yaml
signal_maintenance:
  lines_of_code_added: <N>         # 新增的程式碼行數
  complexity_score: <N>            # 圈複雜度變化
  dependency_added: <N>            # 新增依賴數
```

### 19.8 7 天結果

落地後 7 天追蹤。短期效應。

### 19.9 30 天結果

落地後 30 天追蹤。長期效應。許多壞處（維護負擔、隱性技術債）需要時間才會浮現。

### 19.10 回退與事故結果

```yaml
signal_rollback:
  rolled_back: true | false
  rollback_reason: "side-effect"   # 回退原因分類
  rollback_cost_hours: <N>         # 回退花費時間
```

---

## 20. 好處學習

### 20.1 預測好處與真實好處比較

對每個案例，比較 Aris 的預測好處與實際結果：

```yaml
benefit_learning:
  case_id: "LRN-001"
  predicted: "60s timeout + 優雅退出"
  actual: "benchmark 不再卡住，extended 測試可自動化"
  error: "slightly-underestimated"  # overestimated / underestimated / accurate
  calibration: "實際好處比預期大（Ryan 不用再盯 benchmark）"
```

### 20.2 測試改善與使用者價值的區別

測試通過不等於使用者感受到改善。好處學習要區分：
- **工程指標改善**：測試通過、benchmark 提升、覆蓋率增加
- **使用者價值**：Ryan 實際體驗到的好處

### 20.3 哪些改善 Ryan 真正感受得到

累積數據後，找出現實中 Ryan 有回饋「有感」的改善類型。

### 20.4 哪類問題值得進沙箱

從歷史案例中，學習哪些問題分類的好處/代價比最高。

### 20.5 哪類修改只是工程數字好看

學習哪些修改雖然改善了工程指標但沒有實際使用者價值（如「為了提高覆蓋率而寫測試」）。

### 20.6 長短期好處分離

短期好處（7 天內）與長期好處（30 天後）分開計量。有些改善短期有感但長期無用，反之亦然。

---

## 21. 壞處學習

### 21.1 新增複雜度

```yaml
complexity_learning:
  predicted_lines: 8
  actual_lines: 8
  predicted_complexity_increase: "minor"
  actual_complexity_increase: "minor"  # 準確
```

### 21.2 新增依賴

```yaml
dependency_learning:
  predicted_new_deps: 0
  actual_new_deps: 0
  predicted_vulnerability_risk: "none"
  actual_vulnerability_risk: "none"
```

### 21.3 維護負擔

```yaml
maintenance_learning:
  predicted_hours_per_month: 0
  actual_hours_per_month: 0.5    # 低估了維護時間
```

### 21.4 既有能力犧牲

```yaml
tradeoff_learning:
  sacrificed_capability: "none"
  predicted_impact: "none"
  actual_impact: "none"
```

### 21.5 未來選擇受限

```yaml
future_freedom_learning:
  constrained_option: "可以改用 timeout 參數"
  predicted_constraint_level: "none"
  actual_constraint_level: "none"
```

### 21.6 隱性技術債

新增的程式碼即使現在乾淨，隨著時間會累積技術債。學習系統應追蹤：
- 新增程式碼的修改頻率
- 新增程式碼的 bug 率
- 新增程式碼被後續開發者抱怨的頻率

### 21.7 壞處出現的延遲性

許多壞處不會立即出現。學習系統必須區分：
- 立即出現的壞處（compile error、test failure）
- 延遲出現的壞處（維護負擔、技術債、效能衰退）

---

## 22. 風險學習

### 22.1 預測風險與真實事故比較

```yaml
risk_learning:
  case_id: "LRN-001"
  predicted_probability: 0.15
  predicted_worst_case: "timeout 誤判正常測試"
  actual_occurred: false       # 目前未發生
  actual_worst_case: null
  assessment: "accurate-so-far"  # accurate / overestimated / underestimated
```

### 22.2 漏判風險

```yaml
missed_risk:
  case_id: "LRN-003"
  missed_risk: "修改後 agency 的 benchmark trigger 與 timeout 衝突"
  severity: "medium"
  lesson: "下次應檢查所有使用 _run_benchmark 的呼叫者"
```

### 22.3 高估風險

```yaml
overestimated_risk:
  case_id: "LRN-004"
  overestimated_risk: "修改會影響效能"
  actual_impact: "效能無變化"
  lesson: "對此類修改的效能影響判斷過度保守"
```

### 22.4 最壞情況準確度

```yaml
worst_case_accuracy:
  case_id: "LRN-001"
  predicted_worst_case: "timeout 誤判"
  actual_worst_case: "無"       # 未發生
  worst_case_was_worse: false
  worst_case_was_better: true   # 比預期好
```

### 22.5 哪類元件容易出事故

累積數據後，找出哪些模組的修改容易導致事故：

```text
high_risk_modules:
  psi_core.py: 事故率 30% (3/10)
  agency.py: 事故率 20% (2/10)
  safety_gate.py: 事故率 0% (0/5) — 因為很少改
  constitution.py: 事故率 0% (0/3)
```

### 22.6 哪些早期訊號能預告事故

```text
early_warning_signals:
  - "三輪測試迭代後仍有 1+ 測試失敗" → 事故率 60%
  - "Ryan 要求修改 2+ 次" → 事故率 40%
  - "沙箱中 commit 數 > 5" → 事故率 35%
```

### 22.7 安全規則如何形成

從事故學習中，自動產出候選安全規則：

```yaml
candidate_safety_rule:
  rule: "修改 agency.py 的意圖形成邏輯前，必須先通過 S_span benchmark 測試"
  evidence: "LRN-003 事故：修改意圖形成後 benchmark 的 timeout 觸發邏輯異常"
  severity: "medium"
  confidence: 0.7
```

### 22.8 風險模型不可自行放寬

安全規則需要人工批准才能生效。Aris 可以提出候選規則，但不能自行放寬或移除規則。

---

## 23. 代價學習

### 23.1 開發時間預測

```yaml
time_learning:
  case_id: "LRN-001"
  predicted_hours: 0.5
  actual_hours: 0.3
  error: -0.2                    # 預測比實際高 (預測-實際)
  pattern: "簡單修改略微高估"     # 分類
```

### 23.2 API 成本預測

```yaml
api_cost_learning:
  case_id: "LRN-001"
  predicted_usd: 0
  actual_usd: 0
  error: 0
```

### 23.3 算力成本預測

```yaml
compute_learning:
  case_id: "LRN-001"
  predicted_tokens: 0
  actual_tokens: 0
  error: 0
```

### 23.4 維護成本預測

```yaml
maintenance_cost_learning:
  case_id: "LRN-001"
  predicted_hours_per_month: 0
  actual_hours_per_month: 0.1
  error: 0.1
```

### 23.5 Ryan 注意力成本

```yaml
attention_learning:
  case_id: "LRN-001"
  predicted_level: "low"
  actual_level: "low"            # Ryan 花了 2 分鐘看 diff 和測試結果
  error: "accurate"
```

### 23.6 機會成本

```yaml
opportunity_cost_learning:
  case_id: "LRN-001"
  opportunity_cost: "可忽略（0.5 小時開發 + 2 分鐘審批）"
  better_use: "無"
```

### 23.7 成本低估率

```yaml
cost_underestimation_rate:
  overall: 0.15                  # 整體成本低估 15%
  by_category:
    simple_fix: 0.05             # 簡單修復幾乎準確
    medium_feature: 0.25         # 中型功能低估 25%
    refactor: 0.40               # 重構低估 40%
```

### 23.8 哪類任務最容易超支

```text
overbudget_patterns:
  - "涉及外部 API 整合的修改" → 超支率 60%
  - "涉及多檔案協調的修改" → 超支率 45%
  - "涉及 upstream 模組的修改" → 超支率 35%
```

---

## 24. Ryan 決策偏好學習

### 24.1 批准不等於技術正確

Ryan 批准一個方案不代表這個方案在技術上是完美的。它只代表 Ryan 在當時的時空背景下做出了「可以」的決定。

### 24.2 拒絕不等於方案錯誤

Ryan 拒絕一個方案可能不是因為方案有問題，而是因為時機不對、優先序不同、或者證據不足。

### 24.3 技術不合格

```yaml
ryan_rejection_technically_flawed:
  case_id: "LRN-005"
  reason: "timeout 值 hardcode 60s，應改為可設定參數"
  pattern: "hardcode 常數被退回"
```

### 24.4 風險太高

```yaml
ryan_rejection_risky:
  case_id: "LRN-006"
  reason: "修改涉及 psi_core 的 tick 頻率，影響太大"
  pattern: "核心模組的預設值修改被退回"
```

### 24.5 成本太高

```yaml
ryan_rejection_costly:
  case_id: "LRN-007"
  reason: "為了 log 格式統一重構整個 tool_executor，不值得"
  pattern: "純工程改善（非功能）被退回"
```

### 24.6 時機不對

```yaml
ryan_rejection_timing:
  case_id: "LRN-008"
  reason: "先完成 M3 Rust 引擎，benchmark 改善延後"
  pattern: "non-urgent 改善被優先序壓過"
```

### 24.7 非目前優先事項

```yaml
ryan_rejection_priority:
  case_id: "LRN-009"
  reason: "目前 focus 在穩定性，不是效能優化"
  pattern: "效能優化在穩定期被退回"
```

### 24.8 證據不足

```yaml
ryan_rejection_evidence:
  case_id: "LRN-010"
  reason: "沒有 benchmark 數據證明這個修改真的有效"
  pattern: "無 benchmark 證明的修改被退回"
```

### 24.9 Ryan 個人偏好

```yaml
ryan_personal_preference:
  case_id: "LRN-011"
  reason: "我比較喜歡用 pytest plugin 的標準做法"
  pattern: "標準 library 偏好自定義實作"
```

### 24.10 避免學成討好系統

Aris 可能學會「不管方案好不好，只要符合 Ryan 的偏好就送審」。這不是學習目標。

防範機制：
- 學習系統必須區分「被批准的正確方案」和「被批准的錯誤方案」
- 落地後的結果訊號（7 天/30 天）比批准本身更重要
- 如果 Aris 持續送審「符合 Ryan 風格但無實際價值」的方案，學習引擎應標記為負面案例

---

## 25. 失敗與回退學習

### 25.1 失敗資料不得刪除

所有失敗的沙箱實驗、被拒絕的候選方案、回退的變更，其學習案例必須保留。刪除失敗案例 = 學習系統的選擇性失憶。

### 25.2 回退原因分類

```yaml
rollback_reason_classification:
  - "測試遺漏"      # 通過的測試沒涵蓋到問題
  - "副作用誤判"    # 低估了修改的影響範圍
  - "效能衰退"      # 修改導致 benchmark 下降
  - "成本超支"      # 實際成本遠高於預期
  - "安全漏洞"      # 修改引入了安全風險
  - "使用者不滿"    # Ryan 使用後不滿意
  - "外部依賴變更"  # 上游 API 或 library 變更
```

### 25.3 找出錯誤假設

```yaml
wrong_assumption:
  case_id: "LRN-012"
  assumption: "這個函數沒有其他呼叫者"
  truth: "agency.py 的 intent 形成也呼叫了這個函數"
  impact: "moderate"  # agency 行為異常直到手動回退
```

### 25.4 找出失效測試

```yaml
failed_test:
  case_id: "LRN-012"
  test: "test_s_span_timeout"
  test_was_passing: true     # 沙箱中通過
  test_in_production: true   # 正式環境也通過（但問題出在別處）
  missing_test: "缺少整合測試：agency → benchmark 的觸發路徑"
```

### 25.5 找出被忽略風險

```yaml
ignored_risk:
  case_id: "LRN-012"
  risk: "修改 _run_benchmark 的簽章會影響所有呼叫者"
  was_considered: false       # 完全沒考慮到
  was_in_assessment: false    # 不在 Aris 的風險評估中
```

### 25.6 找出可提前阻止的訊號

```yaml
early_signal:
  case_id: "LRN-012"
  signal: "沙箱中 commit 數量 > 5（多次修改才搞定）"
  was_noticed: false
  would_have_prevented: true  # 如果注意到這個訊號，可以提前要求更謹慎的評估
```

### 25.7 將事故轉成候選安全規則

```yaml
candidate_rule_from_incident:
  rule: "修改公共函數簽章前，必須 grep 所有呼叫者"
  severity: "mandatory"
  evidence: "LRN-012"
```

### 25.8 安全規則仍需人工批准

即使 Aris 從事故中歸納出安全規則，規則的啟用仍然需要 Ryan 批准。

---

## 26. 三層學習循環

### 26.1 快循環：單次沙箱

單次沙箱實驗內的快速迭代：

```text
提出方案
→ 實作
→ 測試
→ 修正
→ 再測試
→ 產出候選變更包
```

頻率：每次沙箱實驗（可能一天多次）
參與者：Aris（提出）+ Scream（實作）
學習內容：技術方案本身是否可行

### 26.2 中循環：跨案例學習

跨越多個案例的模式識別：

```text
累積案例（10+）
→ 找出規律
→ 校準預測（好處/風險/成本）
→ 產生候選策略
```

頻率：每 10 個案例或每週一次
參與者：學習引擎（Aris 的學習模組）
學習內容：判斷策略的系統性偏差

### 26.3 慢循環：正式策略升級

策略升級的完整驗證流程：

```text
候選策略
→ 歷史回測（用既有案例驗證）
→ Held-out 驗證（用未參與訓練的案例驗證）
→ Shadow mode（新舊策略並行，只輸出建議）
→ 新舊策略比較
→ Ryan 批准
→ Canary（限定範圍/時間/成本）
→ 正式升級
```

頻率：每 30 天或每 50 個案例
參與者：學習引擎 + Ryan
學習內容：Aris 的判斷策略是否該升級

---

## 27. Aris 可以更新的內容

以下內容可以由學習引擎在 Ryan 批准後自動更新：

### 27.1 問題優先順序

從歷史資料學習哪些問題分類更緊急，調整 Aris 的優先排序。

### 27.2 工具選擇偏好

從歷史資料學習哪類問題用哪個工具最有效，調整工具選擇策略。

### 27.3 實作路線排序

從歷史資料學習哪類路線更可能被批准，調整路線評估權重。

### 27.4 風險估計

從風險預測誤差中校準風險機率與嚴重程度的估計。

### 27.5 成本估計

從成本預測誤差中校準開發時間和 API 成本的估計。

### 27.6 信心校準

從信心與實際結果的比較中，校準 Aris 的整體信心表達。

### 27.7 外部參謀觸發條件

從外部參謀的歷史效能中，調整觸發條件（信心門檻、風險門檻）。

### 27.8 停止條件

從沙箱停止事件中，學習更好的停止條件（何時該放棄）。

### 27.9 Ryan 偏好模型

從 Ryan 的決策歷史中，學習 Ryan 的取捨偏好（但需避免學成討好系統）。

### 27.10 測試與真實結果的關聯

```yaml
test_reality_correlation:
  finding: "測試通過但真實環境有問題的案例占 15%"
  implication: "測試覆蓋不足，應增加整合測試"
```

---

## 28. Aris 不可自主更新的內容

以下模組永遠不在 Aris 的自主更新範圍內。這些是「裁判模組」：

### 28.1 Safety Gate

`safety_gate.py` 的判斷邏輯不可被自主修改。安全閘的行為只能由 Ryan 手動修改。

### 28.2 人類批准機制

Ryan 的批准流程不可被自主繞過或修改。

### 28.3 沙箱邊界

沙箱的隔離規則（路徑限制、憑證隔離、網路限制）不可被自主修改。

### 28.4 評分器本身

學習系統的評分器和評估標準不可被自主修改（防止作弊）。

### 28.5 回退系統

回退機制（`snapshot.py`、`git revert`）不可被自主修改或停用。

### 28.6 成本上限

沙箱的 token 和 API 成本上限不可被自主放寬。

### 28.7 核心憲法

`constitution.py` 的硬邊界和規則不可被自主修改。

### 28.8 正式環境權限

正式環境的 path-DENY 規則不可被自主放寬。

### 28.9 外部憑證

外部 API Key 和 Token 的存取權限不可被自主修改。

### 28.10 不可變模組清單

此清單本身不可被自主修改。

---

## 29. 防止學歪與作弊

### 29.1 測試通過不等於成功

測試通過只證明程式碼符合規格，不證明改動有價值。學習系統必須同時考慮 Ryan 的滿意度和實際使用效果。

### 29.2 Ryan 批准不等於技術正確

Ryan 可能因為時間壓力、資訊不足、或個人偏好而批准不完美的方案。學習系統不能把「被批准」當作「技術正確」。

### 29.3 外部 AI 同意不等於正確

外部 AI 可能與 Aris 有相同的偏見（同類型模型）。「外部 AI 也同意」不代表方案正確。

### 29.4 修改更多不等於改善更多

Line count 不是好訊號。學習系統必須區分「增加程式碼」和「改善系統」。

### 29.5 不可改評分器來提高分數

評分器是物理隔離的。Aris 不可修改評分邏輯來讓自己的方案看起來更好。

### 29.6 不可挑選有利樣本

學習系統必須使用所有案例，不能只挑選「成功案例」來訓練。

### 29.7 必須保留失敗案例

失敗案例是學習系統最重要的資料。刪除失敗案例 = 選擇性失憶。

### 29.8 訓練資料與驗收資料分離

用於訓練策略的資料和用於驗證策略的資料必須分離。

### 29.9 使用 Held-out 驗證

最終驗證使用未參與任何訓練的案例（hold-out set）。

### 29.10 防止自我記憶污染

學習系統不應使用自己產出的學習結果作為訓練資料（循環引用）。

### 29.11 防止循環引用自己的結論

```text
❌ 錯誤循環：
Aris 提出建議 → Ryan 批准 → Aris 學到「這類建議會被批准」
→ Aris 更頻繁提出同類建議 → Ryan 因疲勞而批准更多
→ Aris 學到「這類建議非常受歡迎」

✅ 正確循環：
Aris 提出建議 → Ryan 批准 → 落地 → 7 天結果好 → 學習
→ 或：落地 → 30 天結果差 → 學習（負面案例）
```

### 29.12 防止為了獎勵放寬安全規則

如果學習系統的獎勵機制包含「方案被批准數量」，Aris 可能學會放寬安全規則來提高批准率。獎勵機制必須獨立於安全規則。

---

## 30. 信心校準

### 30.1 預測信心格式

```yaml
confidence:
  overall: 0.85
  benefit: 0.85
  risk: 0.75
  cost: 0.90
```

信心值 = Aris 對自己預測正確率的估計。

### 30.2 信心與實際正確率比較

```yaml
calibration:
  confidence_band: "0.80-0.90"
  actual_accuracy: 0.85          # 此信心區間的真實正確率
  error: 0.00                    # 完美校準
```

### 30.3 過度自信懲罰

當 Aris 表達高信心（> 0.9）但預測錯誤時，該案例被標記為「過度自信」並降低 Aris 未來在此類問題上的信心權重。

### 30.4 過度保守檢查

當 Aris 表達低信心（< 0.5）但預測準確時，檢查是否因為缺乏證據或過度謹慎。

### 30.5 不同領域分開校準

```yaml
calibration_by_domain:
  safety: {avg_confidence: 0.85, accuracy: 0.90, error: -0.05}
  performance: {avg_confidence: 0.75, accuracy: 0.70, error: +0.05}
  reliability: {avg_confidence: 0.80, accuracy: 0.75, error: +0.05}
```

### 30.6 低信心自動找外援

當 Aris 在特定領域的信心低於 0.5 時，自動觸發外部 AI 參謀。

### 30.7 高風險時提高證據門檻

當風險評分為 high 或 critical 時，即使 Aris 信心高，也應需要更強的證據（如外部 AI 參謀、更多測試）。

---

## 31. 學習成效驗收

### 31.1 建議採用率

```yaml
metric_adoption_rate:
  definition: "被批准的建議 / 總建議數"
  current: 0.70                  # 70% 的建議被批准
  target: "> 0.60"               # 目標：不低於 60%（太低 = 浪費資源）
```

### 31.2 建議後真實改善率

```yaml
metric_real_improvement_rate:
  definition: "落地後 7 天結果為正面 / 總落地數"
  current: 0.80
  target: "> 0.70"
```

### 31.3 風險漏判率

```yaml
metric_missed_risk_rate:
  definition: "未預測到的事故 / 總落地數"
  current: 0.10
  target: "< 0.15"
```

### 31.4 成本低估率

```yaml
metric_cost_underestimation:
  definition: "實際成本 / 預測成本"
  current: 1.15                  # 實際比預測高 15%
  target: "< 1.30"
```

### 31.5 回退率

```yaml
metric_rollback_rate:
  definition: "回退的落地數 / 總落地數"
  current: 0.05
  target: "< 0.10"
```

### 31.6 非必要修改率

```yaml
metric_unnecessary_rate:
  definition: "落地後 30 天被認定為非必要的修改 / 總落地數"
  current: 0.10
  target: "< 0.15"
```

### 31.7 外部參謀有效率

```yaml
metric_advisor_effectiveness:
  definition: "外部參謀建議被採納且結果正面 / 總外部參謀呼叫數"
  current: 0.75
  target: "> 0.50"
```

### 31.8 信心校準誤差

```yaml
metric_calibration_error:
  definition: "平均 (|confidence - accuracy|)"
  current: 0.08
  target: "< 0.10"
```

### 31.9 與舊策略比較

```yaml
metric_vs_old_strategy:
  old_strategy: "規則表 baseline"
  new_strategy: "學習系統 v1"
  comparison:
    adoption_rate: "0.70 vs 0.65 (學習系統更高)"
    rollback_rate: "0.05 vs 0.08 (學習系統更低)"
    cost_underestimation: "1.15 vs 1.25 (學習系統更準)"
```

### 31.10 是否真的減少 Ryan 負擔

最終目標：學習系統是否讓 Ryan 花更少的注意力在決策上，同時維持或提升決策品質。

```yaml
metric_ryan_burden:
  before_learning: "平均每週審批 5 個提案，花 2 小時"
  after_learning: "平均每週審批 3 個提案（品質提高後減少廢案），花 1 小時"
  improvement: "-50% Ryan 注意力成本"
```