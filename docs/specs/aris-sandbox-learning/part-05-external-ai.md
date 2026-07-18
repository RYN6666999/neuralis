# 第五部：外部 AI 參謀

> 對應章節：Ch 13～16
> 撰寫狀態：✅ 已完成（2026-07-18）
> 參考來源：`part-01-principles.md`（角色定義）、`part-04-decision-analysis.md`（四面向分析格式）

---

## 13. 外部 AI 升級條件

外部 AI 參謀（External AI Advisor）是在 Aris 的判斷能力不足時，提供第二意見的機制。它不是常規步驟，而是在特定條件下才觸發。

### 13.1 Aris 信心低於門檻

當 Aris 對自己四面向分析的整體信心低於 0.6 時，自動觸發外部參謀。

### 13.2 高風險或高影響

以下情況無論 Aris 信心多高，都應觸發外部參謀：
- 風險評分為 high 或 critical
- 好處或壞處評分為 large
- 影響整個 Aris 生態系統的變更

### 13.3 涉及核心架構

修改以下範圍時觸發外部參謀：
- PsiCore（`laap/psi_core.py`）
- AgencyLoop 核心邏輯（`laap/agency.py` 中的 drive 計算、意圖形成）
- ToolExecutor 框架（`laap/tool_executor.py`）
- gbrain 整合層

### 13.4 涉及安全邊界

任何觸及安全邊界的變更（即使只是提案），必須有外部參謀：
- SafetyGate 的行為變化
- Constitution 新規則
- path-DENY 路徑調整
- 新的委派工具加入

### 13.5 無法完整回退

如果候選方案無法一鍵回退（git revert），外部參謀是 mandatory。

### 13.6 測試結果矛盾

當測試結果不一致或難以解釋時：
- 新測試與既有測試衝突
- benchmark 數據波動大，無法判斷改善
- 同一測試在不同環境結果不同

### 13.7 好處與代價都高

當好處和代價都被評為 large 時，需要外部視角來驗證判斷：
- 大型架構重構
- 新功能整合
- 上游模組替換

### 13.8 Aris 與 Scream 判斷不同

如果 Aris 和 Scream 對方案有不同的評估，觸發外部參謀做仲裁。

### 13.9 過去同類判斷錯誤率高

學習引擎發現 Aris 在特定問題分類上的歷史判斷錯誤率高於 30% 時，同一分類的新問題自動觸發外部參謀。

### 13.10 Ryan 主動要求第二意見

Ryan 可以在任何時候手動要求外部 AI 參謀。

---

## 14. 外部 AI 決策參謀包

當觸發外部參謀時，Aris 組裝一個完整的參謀包，包含以下內容：

### 14.1 核心問題

```
CORE_QUESTION:
「是否應在 S_span benchmark 的每個測試循環加入 60s timeout？」
```

### 14.2 系統背景

```yaml
system_context:
  project: "neuralis — Ryan 的 Aris overlay"
  upstream: "laap-AGI v1.0.0 (lorryjovens)"
  current_phase: "甲（安全自主階段）"
  stack: "Python 3.12, asyncio, AgentOS, Scream"
```

### 14.3 前後文脈絡

```text
S_span benchmark 當前沒有 timeout 機制，卡住時永遠不會結束。
這使得 extended benchmark 無法自動化執行。
Ryan 在手動執行時碰到 347s 卡住才發現這個問題。
```

### 14.4 問題來源

```yaml
problem_source: "incident"
evidence: "2026-07-18 手動執行 extended bench, 347s 未結束, 手動 kill"
severity: 3  # moderate
```

### 14.5 變更前後差異

```text
修改前：asyncio.gather(coro) → 無限等待
修改後：asyncio.wait_for(coro, timeout=60) → 60s 超時優雅退出
```

### 14.6 相關技術細節

```yaml
tech_details:
  files: ["laap/s_span_bench.py"]
  diff_stats: "+8 -2"
  key_class: "SpanBench"
  key_method: "_run_benchmark"
  use_asyncio: true
```

### 14.7 執行流程與資料流

```text
main → SpanBench.run_all()
         → _run_benchmark("extended", ...)
              → asyncio.wait_for(coro, timeout=60)
                   → 正常完成 → 回傳結果
                   → timeout → 記錄事件 → 回傳 None
```

### 14.8 安全邊界

```yaml
safety_boundary:
  touches_safety_gate: false
  touches_constitution: false
  touches_path_deny: false
  touches_agency_core: false
  touches_production_data: false
```

### 14.9 參考檔案永久連結

```yaml
refs:
  - "neuralis/laap/s_span_bench.py (main @ bc6e848)"
  - "neuralis/docs/specs/aris-sandbox-learning/part-06-ch18-learning-case-format.md"
```

### 14.10 關鍵程式碼區塊

```python
try:
    return await asyncio.wait_for(coro, timeout=60)
except asyncio.TimeoutError:
    logger.warning(f"benchmark '{name}' timed out after 60s")
    self._timeouts.append(name)
    return None
```

### 14.11 完整 diff

（完整 diff 內嵌或引用）

### 14.12 測試與驗證證據

```yaml
test_results:
  existing_tests: {passed: 6, failed: 0}
  new_tests: {passed: 2, failed: 0}
```

### 14.13 尚未驗證項目

```yaml
unverified:
  - "極慢網速下的 timeout 行為"
  - "大量 timeout 累積對記憶體影響"
```

### 14.14 Aris 四面向分析

（從 part-04 Chapter 10 複製摘要）

```yaml
aris_analysis:
  benefit: {magnitude: "medium", confidence: 0.85}
  harm: {complexity: "minor", confidence: 0.9}
  risk: {probability: 0.15, recoverable: true, confidence: 0.75}
  cost: {hours: 0.5, usd: 0, confidence: 0.9}
  recommendation: "approve"
  confidence: 0.85
```

### 14.15 已考慮的決策路線

```yaml
considered_routes:
  - route: "A — 直接在源頭加 timeout"
    pro: "最小修改，6 行 diff"
    con: "timeout hardcode 60s"
  - route: "B — benchmark runner 層加 timeout"
    pro: "不修改內部邏輯"
    con: "修改範圍更大"
  - route: "C — 不做"
    pro: "不增加任何程式碼"
    con: "extended benchmark 無法自動化"
```

### 14.16 外部 AI 固定回答格式

外部 AI 必須使用以下固定格式回答，確保輸出結構化：

```yaml
advisor_review:
  overall_assessment: "approve" | "modify" | "reject" | "need-more-info"
  
  agreement_with_aris: true | false | partial
  agreement_detail: "<與 Aris 分析的一致或差異點>"
  
  benefit: "<外部 AI 對好處的評估>"
  harm: "<外部 AI 對壞處的評估>"
  risk: "<外部 AI 對風險的評估>"
  cost: "<外部 AI 對代價的評估>"
  
  concerns: ["<關注點 1>", "<關注點 2>"]
  
  suggestions: ["<建議 1>", "<建議 2>"]
  
  overall_rationale: "<完整的判斷理由>"
  
  confidence: 0.0-1.0
```

---

## 15. 外部 AI 的評價與學習

### 15.1 外部 AI 意見不是正確答案

外部 AI 的意見不等於正確答案。它只是一個來自不同模型/視角的第二意見。最終判斷仍然是 Ryan 的責任。

### 15.2 記錄參謀被呼叫的原因

每個外部參謀呼叫都要記錄觸發原因，用於後續分析：

```yaml
advisor_call_log:
  case_id: "LRN-003"
  call_reason: "high-risk"     # low-confidence / high-risk / high-impact / core-architecture / etc.
  aris_confidence: 0.55        # 當時 Aris 的信心值
  advisor_model: "gpt-4o"      # 使用的模型
```

### 15.3 記錄採用與未採用建議

```yaml
adoption:
  ryan_followed_advisor: true | false | partial
  if_not_followed: "<Ryan 不採用的理由>"
```

### 15.4 比較建議與最終結果

落地後比較外部 AI 的建議與實際結果：

```yaml
advisor_accuracy:
  advisor_said: "approve"
  actual_outcome: "successful"  # successful / neutral / failure
  advisor_correct: true | false | partial
```

### 15.5 學習哪個 AI 適合哪類問題

累積數據後，建立模型 → 問題分類的效能對照表：

```text
gpt-4o:
  安全性問題: 正確率 85% (12/14)
  效能問題: 正確率 70% (7/10)
claude-opus:
  安全性問題: 正確率 90% (9/10)
  效能問題: 正確率 80% (8/10)
```

### 15.6 計算外部參謀的實際價值

```yaml
advisor_value:
  times_called: <N>
  times_prevented_bad_decision: <N>    # 外部 AI 說 reject, Ryan 也 reject
  times_enabled_good_decision: <N>     # 外部 AI 說 approve, Ryan 也 approve
  times_wrong: <N>                     # 外部 AI 的建議被證明是錯的
  net_value: "<positive / neutral / negative>"
```

### 15.7 學習什麼時候不需要外援

如果某些問題分類的歷史顯示 Aris 的判斷準確率足夠高（> 90%），可以自動降低該分類的外部參謀觸發門檻。

### 15.8 建立參謀路由策略

根據問題分類、風險等級、歷史準確率，決定呼叫哪個外部 AI 模型：

```yaml
advisor_routing:
  default: "gpt-4o"
  safety_critical: "claude-opus"
  core_architecture: "claude-opus + human-review"
  low_risk_routine: "none (aris-only)"
```

---

## 16. 外送資訊安全

當外部 AI 參謀包被送往外部模型時，必須經過安全掃描，確保敏感資訊不會洩漏。

### 16.1 Token 與 API Key 移除

自動掃描並移除以下模式：
- `sk-...`（OpenAI API Key）
- `NEURALIS_LLM_API_KEY` 的值
- 任何 `Authorization: Bearer ...` 頭
- 環境變數中的敏感值

### 16.2 Cookie 與 Session 移除

- 移除所有 Cookie 字串
- 移除 Session ID
- 移除 device_id

### 16.3 gbrain 私密記憶移除

- 不包含具體的 gbrain 記憶內容
- 只包含問題和變更的技術描述
- Ryan 的個人對話內容不移送

### 16.4 個資匿名化

- 路徑中的 username 替換為 `<user>`（如 `/Users/<user>/Developer/...`）
- 主機名稱替換為 `<hostname>`
- 不包含 Ryan 的真實姓名或任何個人資訊

### 16.5 正式資料禁止外送

- 不包含正式環境的 log
- 不包含正式環境的資料庫內容
- 不包含正式環境的 config（只包含修改的 diff）

### 16.6 敏感路徑處理

```python
# 概念：路徑匿名化
SENSITIVE_PATH_PATTERNS = [
    r"/Users/\w+/",
    r"/home/\w+/",
    r"C:\\Users\\\w+\\",
]
```

所有符合敏感路徑模式的內容在送出前替換。

### 16.7 正式環境操作指令移除

參謀包中不包含：
- 正式環境的部署指令
- 正式環境的 config 內容
- 正式 API 的 endpoint URL（只用 localhost 表示）

### 16.8 外送前自動掃描

外送前執行自動安全掃描：

```bash
# 概念：安全掃描腳本
python scripts/sanitize-advisor-package.py \
  --input /tmp/advisor-package-raw.json \
  --output /tmp/advisor-package-sanitized.json \
  --check-sensitive
```

掃描通過才能外送。掃描失敗則返回 Aris，要求 Aris 修正後重試。

### 16.9 外部 AI 只有參謀權

外部 AI 的輸出永遠被標記為「參謀意見」：
- 不直接影響系統行為
- 不自動觸發任何操作
- 不取代 Ryan 的決策權
- 不作為審計證據的唯一來源（僅為輔助參考）