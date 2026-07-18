# 第六部附加：第 18 章 — 單次學習案例格式

> 對應章節：Ch 18（第六部核心）
> 撰寫狀態：✅ 已完成（2026-07-18）
>
> 🎯 **這個格式是整套自主學習系統的核心。沒有它，後面的學習都只會變成 Aris 自己講故事。**
>
> 每個沙箱實驗 + 決策 + 結果必須用此格式記錄。所有學習（好處校準、風險校準、信心校準、Ryan 偏好學習）
> 都依賴此格式的一致性。

---

## 18. 單次學習案例格式

### 18.1 當時情境

```yaml
case_id: "LRN-<NNN>"                          # 唯一編號，遞增
created_at: "2026-07-18T15:30:00Z"            # 案例建立時間
source: "aris-autodiscovery" | "ryan-request" | "incident" | "upstream-sync"
sandbox_id: "sandbox/<NNN>-<slug>"            # 對應的沙箱編號（如有）
```

### 18.2 發現的問題

```yaml
problem_statement: "<一句話描述問題>"
problem_category:                              # 從下列分類選一個
  - performance        # 效能/benchmark
  - safety             # 安全漏洞
  - reliability        # 穩定性/當機
  - usability          # 使用者體驗
  - maintainability    # 維護性/程式碼品質
  - cost               # 成本
  - integration        # 整合/相容性
  - correctness        # 邏輯錯誤
  - observability      # 可觀測性
  - other
```

### 18.3 問題分類

```yaml
domain:                                        # 技術領域
  - safety-gate       # safety_gate.py
  - agency            # agency.py
  - psi-core          # psi_core.py
  - tool-executor     # tool_executor.py
  - constitution      # constitution.py
  - cost-ledger       # cost_ledger.py
  - snapshot          # snapshot.py
  - s-span            # s_span bench/cognitive light cone
  - scream-channel    # scream-ask/task 通道
  - infrastructure    # watchdog/launchd/deployment
  - documentation     # docs/specs
  - upstream-agi      # aris_brain modules from lorry
  - other
evidence_type:                                # 證據類型
  - log               # log 檔中有證據
  - test-failure      # 測試失敗
  - crash             # crash/重啟
  - benchmark         # benchmark 衰減
  - ryan-report       # Ryan 親眼看到
  - code-analysis     # 靜態分析
evidence_ref: "<log路徑 / commit hash / issue 連結>"
severity: 1-5                                  # 1=最低, 5=最高
```

### 18.4 執行前預測

```yaml
prediction:
  benefit:
    expected_improvement: "<預期改善的描述>"
    measurable_criterion: "<客觀可量的改善標準>"
    predicted_magnitude: "<small / medium / large>"
    confidence: 0.0-1.0                       # Aris 對此預測的信心
  harm:
    expected_side_effects: "<預期副作用>"
    increased_complexity: "<新增多少複雜度>"
    confidence: 0.0-1.0
  risk:
    worst_case: "<最壞情況描述>"
    probability: 0.0-1.0                      # Aris 估計的發生機率
    recoverable: true | false                 # 最壞情況是否可回退
    confidence: 0.0-1.0
  cost:
    dev_time_hours: <預估開發時數>
    api_cost_usd: <預估 API 成本>
    ryan_attention: "<low / medium / high>"  # 預估需要 Ryan 多少注意力
    confidence: 0.0-1.0
```

### 18.5 候選路線

```yaml
candidates:
  - route: "A"                                # 方案代號
    description: "<方案 A 的描述>"
    approach: "<實作方式>"
    files_changed: ["<檔案路徑>"]
    estimated_effort: "<small / medium / large>"
  - route: "B"
    description: "<方案 B 的描述>"
    approach: "<實作方式>"
    files_changed: ["<檔案路徑>"]
    estimated_effort: "<small / medium / large>"
```

### 18.6 最終選擇

```yaml
chosen_route: "A" | "B" | null               # null = 全不選（不進沙箱）
selection_reason: "<為什麼選這個路線的理由>"
```

### 18.7 沙箱執行結果

```yaml
sandbox_result:
  status: "completed" | "failed" | "aborted" | "not-applicable"
  commits:                                     # 沙箱中的 commits
    - hash: "<commit hash>"
      message: "<commit message>"
  base_commit: "<main 的 base commit hash>"
  diff_stats:                                  # 修改統計
    files_changed: <N>
    insertions: <N>
    deletions: <N>
```

### 18.8 測試證據

```yaml
test_evidence:
  existing_tests:                             # 既有測試結果
    passed: <N>
    failed: <N>                               # 0 = 沒有 regress
  new_tests:                                   # 新測試結果
    passed: <N>
    failed: <N>
  benchmark_before_after:                      # benchmark 前後比較（如有）
    before: {"score": <N>, "detail": "<..." >}
    after: {"score": <N>, "detail": "<...">}
  test_output_path: "<測試輸出檔案路徑>"
```

### 18.9 Aris 建議

```yaml
aris_recommendation:                          # Ch 10 四面向分析的摘要
  benefit_score: 1-5
  harm_score: 1-5
  risk_score: 1-5
  cost_score: 1-5
  overall_recommendation: "approve" | "modify" | "reject" | "observe"
  confidence: 0.0-1.0
```

### 18.10 外部 AI 意見

```yaml
external_advisor:                              # 如有呼叫外部 AI
  called: true | false
  reason: "<為什麼需要外援>"
  advisor_model: "<使用的模型>"
  recommendation: "<外部 AI 的意見摘要>"
  recommendation_aligned: true | false | partial  # 與 Aris 意見是否一致
  ryan_followed_advisor: true | false | partial   # Ryan 採用了多少
```

### 18.11 Ryan 決策與理由

```yaml
ryan_decision:
  decision:                                    # Ch 12 的決策路線
    - approve-as-is        # 直接落地
    - approve-shrunk       # 縮小範圍後落地
    - continue-observe     # 沙箱繼續觀察
    - return-for-revision  # 退回修改
    - reject               # 完全回退/拒絕
    - adopt-alternative    # 採用替代方案
    - defer                # 暫時不做
    - gather-evidence      # 蒐集更多證據
  reason_category:                              # Ryan 的拒絕/修改理由分類
    - technically-flawed   # 技術不合格
    - too-risky           # 風險太高
    - too-costly          # 成本太高
    - bad-timing          # 時機不對
    - not-priority        # 非目前優先事項
    - insufficient-evidence # 證據不足
    - personal-preference  # Ryan 個人偏好
    - other
  reason_detail: "<Ryan 的實際理由，原文最優>"
  decision_timestamp: "2026-07-18T16:00:00Z"
```

### 18.12 落地後真實結果

```yaml
actual_result:
  deployed_commit: "<正式合併後的 commit hash>"   # 如有落地
  deployed_at: "2026-07-18T17:00:00Z"           # 落地時間
  
  # 7 天追蹤（落地後 7 天填寫）
  day_7:
    benefit_realized: true | false | partial
    benefit_detail: "<實際改善證據>"
    harm_appeared: true | false
    harm_detail: "<實際副作用>"
    incidents: <N>                               # 相關事故次數
    maintenance_hours: <N>                       # 維護花費時數
  
  # 30 天追蹤（落地後 30 天填寫）
  day_30:
    benefit_realized: true | false | partial
    benefit_detail: "<長期改善證據>"
    harm_appeared: true | false
    harm_detail: "<長期副作用>"
    incidents: <N>
    maintenance_hours: <N>
```

### 18.13 預測誤差

```yaml
prediction_error:
  benefit:
    predicted: "<預期改善>"
    actual: "<實際改善>"
    error: "overestimated" | "underestimated" | "accurate"
    magnitude: "<small / medium / large>"
  harm:
    predicted: "<預期副作用>"
    actual: "<實際副作用>"
    error: "overestimated" | "underestimated" | "accurate"
  risk:
    predicted_probability: <N>                 # 預測機率
    actual_occurred: true | false
    worst_case_accuracy: "<accurate / worse-than-predicted / better-than-predicted>"
  cost:
    predicted_dev_hours: <N>
    actual_dev_hours: <N>
    predicted_api_cost: <N>
    actual_api_cost: <N>
```

### 18.14 最終學習結論

```yaml
learning_conclusion:
  what_worked: "<這個 case 中什麼做對了>"
  what_didnt: "<這個 case 中什麼做錯了>"
  would_do_differently: "<下次怎麼改進>"
  
  # 策略建議：由學習引擎或 Aris 產生
  strategy_hints:
    - type: "benefit-calibration"              # 好處估計校準
      hint: "<Aris 對此類問題的好處估計應調高/調低 N%>"
    - type: "risk-calibration"                 # 風險估計校準
      hint: "<Aris 對此類風險的估計應調高/調低 N%>"
    - type: "cost-calibration"                 # 成本估計校準
      hint: "<Aris 對此類成本的估計應調高/調低 N%>"
    - type: "ryan-preference"                  # Ryan 偏好
      hint: "<Ryan 對這類問題的偏好傾向>"
    - type: "advisor-trigger"                  # 外部參謀觸發
      hint: "<這類問題何時該找外援>"
    - type: "stop-condition"                   # 停止條件
      hint: "<這類問題何時該停止>"
  
  tags: ["<tag1>", "<tag2>", "<tag3>"]        # 供搜尋用
```

---

## 18A. 學習案例範例（虛擬）

```yaml
case_id: "LRN-001"
created_at: "2026-07-18T15:30:00Z"
source: "incident"
sandbox_id: "sandbox/001-fix-s-span-timeout"

problem_statement: "S_span extended benchmark 的 timeout 機制是無限等待，導致執行卡住時永遠不會結束"
problem_category: "reliability"

domain: ["s-span"]
evidence_type: ["benchmark", "ryan-report"]
evidence_ref: "2026-07-18 手動執行 extended bench, 347s 未結束, 手動 kill"
severity: 3

prediction:
  benefit:
    expected_improvement: "加 60s timeout，卡住時優雅退出"
    measurable_criterion: "timeout 後 exit code 0 + timeout 事件 log"
    predicted_magnitude: "medium"
    confidence: 0.85
  harm:
    expected_side_effects: "無（只改 timeout 邏輯）"
    increased_complexity: "minor"
    confidence: 0.9
  risk:
    worst_case: "timeout 誤判正常執行中的長時間測試"
    probability: 0.15
    recoverable: true
    confidence: 0.75
  cost:
    dev_time_hours: 0.5
    api_cost_usd: 0
    ryan_attention: "low"
    confidence: 0.9

candidates:
  - route: "A"
    description: "在 s_span_bench.py 每個測試循環加 timeout=60"
    approach: "修改 _run_benchmark 加 asyncio.wait_for"
    files_changed: ["laap/s_span_bench.py"]
    estimated_effort: "small"
  - route: "B"
    description: "外包裝 timeout，跑所有測試時用 subprocess timeout"
    approach: "benchmark runner 層加 timeout"
    files_changed: ["scripts/benchmark-s-span.py"]
    estimated_effort: "medium"

chosen_route: "A"
selection_reason: "最小修改，直接在問題源頭加 timeout"

sandbox_result:
  status: "completed"
  commits:
    - hash: "abc1234"
      message: "fix: S_span bench 加 60s timeout"
  base_commit: "bc6e848"
  diff_stats:
    files_changed: 1
    insertions: 8
    deletions: 2

test_evidence:
  existing_tests:
    passed: 6
    failed: 0
  new_tests:
    passed: 2
    failed: 0
  benchmark_before_after:
    before: {"score": 0.82, "detail": "normal run"}
    after: {"score": 0.82, "detail": "no regression"}
  test_output_path: "/tmp/sandbox-001-test-output.log"

aris_recommendation:
  benefit_score: 4
  harm_score: 1
  risk_score: 1
  cost_score: 1
  overall_recommendation: "approve"
  confidence: 0.85

external_advisor:
  called: false
  reason: null

ryan_decision:
  decision: "approve-as-is"
  reason_category: null
  reason_detail: "diff 只有 6 行，有測試，無風險，直接合併"
  decision_timestamp: "2026-07-18T16:00:00Z"

actual_result:
  deployed_commit: "def5678"
  deployed_at: "2026-07-18T16:10:00Z"
  day_7: null
  day_30: null

prediction_error:
  benefit:
    predicted: "60s timeout + 優雅退出"
    actual: null
    error: null
  harm:
    predicted: "無"
    actual: null
    error: null
  risk:
    predicted_probability: 0.15
    actual_occurred: null
    worst_case_accuracy: null
  cost:
    predicted_dev_hours: 0.5
    actual_dev_hours: 0.3
    predicted_api_cost: 0
    actual_api_cost: 0

learning_conclusion:
  what_worked: "直接改源頭最小修改，有測試驗證"
  what_didnt: "尚未觀察到長期效果"
  would_do_differently: "尚無"
  strategy_hints: []
  tags: ["s-span", "reliability", "timeout"]
```
