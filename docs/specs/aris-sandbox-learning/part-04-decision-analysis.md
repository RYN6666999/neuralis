# 第四部：候選方案與決策分析

> 對應章節：Ch 9～12
> 撰寫狀態：✅ 已完成（2026-07-18）
> 參考來源：`part-02-full-flow.md`（生命週期）、`part-06-ch18-learning-case-format.md`（案例格式）

---

## 9. 候選變更包

沙箱實驗完成後，Scream 產出一個候選變更包（Candidate Change Package, CCP）。這是 Ryan 決策的主要參考文件，也是學習案例的核心輸入。

### 9.1 變更目的

一句話說明這個變更包解決什麼問題：

```
目的：在 S_span benchmark 的每個測試循環加入 60s timeout，避免無限等待
```

### 9.2 前後文脈絡

此次變更的來龍去脈：
- 問題來源（第 5 章的問題與假設）
- 相關的既有 issue 或討論
- 哪些檔案被修改、為什麼是這些檔案
- 如果此變更涉及上游（lorryjovens）模組，標註是否與上游同步

### 9.3 Base commit 與 Candidate commit

```yaml
base_commit: "bc6e848"          # 沙箱建立時的 main HEAD
candidate_commit: "abc1234"     # 沙箱中最後的 commit hash
```

### 9.4 修改檔案

清單：

```
laap/s_span_bench.py          # +8 -2 行 — 加 timeout 邏輯
```

### 9.5 完整 diff

```diff
--- a/laap/s_span_bench.py
+++ b/laap/s_span_bench.py
@@ -42,6 +42,7 @@ class SpanBench:
     async def _run_benchmark(self, name: str, coro):
+        try:
+            return await asyncio.wait_for(coro, timeout=60)
+        except asyncio.TimeoutError:
+            logger.warning(f"benchmark '{name}' timed out after 60s")
+            self._timeouts.append(name)
+            return None
```

diff 是變更包的核心證據。Ryan 必須能直接從 diff 理解變更內容。

### 9.6 關鍵程式碼區塊

如果 diff 太長，標出最關鍵的程式碼邏輯（通常 5-10 行）：

```python
# 關鍵邏輯：wait_for 包住測試 coroutine，timeout 後記錄而非 crash
try:
    return await asyncio.wait_for(coro, timeout=60)
except asyncio.TimeoutError:
    logger.warning(f"benchmark '{name}' timed out after 60s")
```

### 9.7 測試指令與結果

```bash
# 測試指令
cd /tmp/aris-sandbox-001/
python -m pytest tests/test_s_span.py -v

# 結果
# tests/test_s_span.py::test_timeout PASSED
# tests/test_s_span.py::test_normal_completion PASSED
# 2 passed in 1.23s
```

### 9.8 行為前後差異

| 情境 | 修改前 | 修改後 |
|------|--------|--------|
| 正常執行 | 正常結束 | 正常結束（無變化） |
| benchmark 卡住 | 無限等待，永不結束 | 60s 後 timeout，優雅退出 |
| 大量 timeout | 不適用 | 記錄 timeout 次數，仍繼續執行 |

### 9.9 效能與成本差異

| 指標 | 修改前 | 修改後 | 差異 |
|------|--------|--------|------|
| 正常 benchmark 執行時間 | Xs | Xs | 無變化 |
| 卡住時最大等待時間 | ∞ | 60s | ✅ 顯著改善 |
| API 成本 | N/A | N/A | 無 |

### 9.10 已知風險

| 風險 | 影響 | 機率 | 緩解方式 |
|------|------|------|---------|
| timeout 太短誤判正常測試 | 正常 benchmark 被中斷 | 低（60s >> 正常執行時間） | 可調參數 |
| timeout 事件未被妥善處理 | benchmark 結果不完整 | 低 | 記錄 timeout 事件 |

### 9.11 未驗證項目

- 極慢網速下的 timeout 行為（未測試）
- 大量 timeout 累積對記憶體的影響（未測試）

### 9.12 回退方法

```bash
cd ~/Developer/neuralis/
git revert abc1234    # 或者
git cherry-pick --skip abc1234
```

如果尚未合併：直接刪除沙箱 worktree，不提交。

---

## 10. Aris 四面向分析

Aris 對候選方案的四個面向分析。這是 Aris 的判斷輸出，必須誠實標註信心。

### 10.1 好處

```yaml
benefit:
  description: "加 60s timeout，卡住時優雅退出"
  who_feels_it: "開發者（不再需要手動 kill benchmark）"
  magnitude: "medium"          # none / small / medium / large
  measurable: true
  confidence: 0.85
```

### 10.2 壞處

```yaml
harm:
  description: "新增 timeout 判斷邏輯（8 行程式碼）"
  complexity_increase: "minor"  # none / minor / moderate / major
  maintenance_burden: "none"    # 幾乎不需要維護
  confidence: 0.9
```

### 10.3 風險

```yaml
risk:
  description: "timeout 誤判正常測試"
  worst_case: "長時間 benchmark 被中斷，需重跑"
  probability: 0.15
  impact: "low"                # 重跑一次即可
  recoverable: true
  confidence: 0.75
```

### 10.4 代價

```yaml
cost:
  dev_time_hours: 0.5
  api_cost_usd: 0
  ryan_attention: "low"       # 只需要 approve
  confidence: 0.9
```

### 10.5 替代方案

```yaml
alternatives:
  - route: "B"
    reason_not_chosen: "subprocess 包裝 timeout 要改 benchmark runner，修改更大"
  - route: "不做"
    reason_not_chosen: "extended benchmark 不能自動化跑，需人盯"
```

### 10.6 不做的後果

```yaml
consequence_of_inaction: "extended benchmark 流程無法自動化，需要開發者手動監控"
```

### 10.7 證據強度

```yaml
evidence_strength: "strong"    # none / weak / moderate / strong / conclusive
evidence_detail: "有測試驗證 timeout 行為，diff 只有 6 行"
```

### 10.8 判斷信心

```yaml
overall_confidence: 0.85       # 0.0-1.0
confidence_breakdown:
  benefit_accuracy: 0.85
  risk_assessment: 0.75
  cost_estimate: 0.90
```

### 10.9 成立條件

```yaml
preconditions:
  - "沙箱測試全部通過"
  - "Ryan 確認 timeout 值 60s 合適"
```

### 10.10 停止條件

```yaml
stop_conditions:
  - "測試發現 timeout 會正常測試中斷"
  - "Ryan 要求停止"
```

### 10.11 最終建議

```yaml
recommendation: "approve"     # approve / modify / reject / observe
summary: "低風險、低代價、高收益的修改，建議直接落地"
```

---

## 11. 決策評分方式

### 11.1 好處大小

| 評分 | 定義 |
|------|------|
| none | 沒有可量測的改善 |
| small | 改善幅度 < 10% 或僅開發者感受 |
| medium | 改善幅度 10-30% 或 Ryan 可感受 |
| large | 改善幅度 > 30% 或解決重大瓶頸 |

### 11.2 證據強度

| 等級 | 定義 |
|------|------|
| none | 無任何測試或 log 證據 |
| weak | 單次人工觀察 |
| moderate | 測試通過 + 人工確認 |
| strong | 測試通過 + benchmark 改善 + 人工確認 |
| conclusive | 大規模測試 + benchmark + 長期觀察 |

### 11.3 壞處大小

| 評分 | 定義 |
|------|------|
| none | 無新增複雜度 |
| minor | < 20 行新增 |
| moderate | 20-100 行新增或新增輕微依賴 |
| major | > 100 行新增或新增外部依賴 |

### 11.4 風險程度

| 評分 | 定義 |
|------|------|
| none | 完全可回退，無副作用 |
| low | 可回退，副作用微小 |
| medium | 可回退但需要人工補救 |
| high | 回退困難或副作用顯著 |
| critical | 不可回退或涉及安全 |

### 11.5 短期代價

以開發時數和 API 成本計算：
- low: < 1 小時開發，無 API 成本
- medium: 1-4 小時開發，< $1 API 成本
- high: > 4 小時開發或 > $1 API 成本

### 11.6 長期代價

以維護負擔和技術債計算：
- low: 幾乎不需要維護
- medium: 偶爾需要維護（每月 < 30 分鐘）
- high: 需要定期維護（每週 > 30 分鐘）

### 11.7 可回退性

| 等級 | 定義 |
|------|------|
| immediate | git revert 一鍵回退 |
| manual | 需要手動操作但可回退 |
| difficult | 回退需要多次操作或有殘留 |
| impossible | 不可回退（不應進沙箱） |

### 11.8 Aris 信心

0.0-1.0 的數值，代表 Aris 對自己分析的整體信心：
- < 0.5：不應提交建議
- 0.5-0.7：需外部 AI 參謀
- 0.7-0.9：可提交 Ryan 決策
- > 0.9：高信心（但仍需 Ryan 批准）

### 11.9 為什麼不能用單一總分批准

不同意義的維度不能加總成單一分數：

```text
好處 4/5 + 風險 2/5 + 代價 2/5 = 8/15
vs
好處 2/5 + 風險 4/5 + 代價 2/5 = 8/15
```

兩者總分相同但意義完全不同：第一個是穩妥的小改善，第二個是高風險的高收益賭注。Ryan 需要看到維度細節，不是總分。

### 11.10 必須人工判斷的紅線

以下情況永遠由 Ryan 人工判斷，不自動批准：
- 涉及安全邊界（SafetyGate、path-DENY、constitution）
- 涉及正式資料處理
- 外部服務寫入
- 無法完整回退
- 涉及多個模組的協調修改
- 任何修改 agency.py 自主判斷邏輯的變更

---

## 12. 決策路線

Ryan 收到候選變更包和 Aris 分析後，可以選擇以下路線：

### 12.1 直接落地

批准候選方案，cherry-pick 到 main。

適用：低風險、低代價、有測試、diff 小的變更。

```bash
# Ryan 執行
cd ~/Developer/neuralis/
git cherry-pick <candidate-commit>
git push origin main
```

### 12.2 縮小範圍

只取候選方案的一部分落地。

適用：方案整體不錯但部分功能風險較高或多餘。

```yaml
ryan_decision:
  decision: "approve-shrunk"
  shrink_detail: "加 timeout 邏輯保留，移除日誌記錄的詳細參數輸出"
```

### 12.3 沙箱繼續觀察

不批准也不拒絕，保留沙箱繼續蒐集證據。

適用：證據不足但方案有潛力，或等待上游（lorryjovens）更新。

```yaml
ryan_decision:
  decision: "continue-observe"
  observe_period: "7 days"
  observe_focus: "觀察 timeout 在實際使用中是否誤判"
```

### 12.4 退回修改

要求 Scream 修改後再送審。

適用：方案方向正確但實作有問題。

```yaml
ryan_decision:
  decision: "return-for-revision"
  revision_request: "timeout 值應改為可設定參數，不要 hardcode 60s"
```

### 12.5 完全回退

拒絕方案，關閉沙箱。

適用：方案方向錯誤、風險太高、或非優先事項。

```yaml
ryan_decision:
  decision: "reject"
  reason_category: "not-priority"
  reason_detail: "S_span benchmark 目前不常用，不急著修"
```

### 12.6 採用替代方案

Ryan 提出另一個解法，不採用沙箱產出的方案。

適用：Ryan 有更了解脈絡的解法。

```yaml
ryan_decision:
  decision: "adopt-alternative"
  alternative: "直接用 pytest-timeout plugin，不改程式碼"
```

### 12.7 暫時不做

延後處理，但不關閉沙箱（沙箱仍在）。

適用：時機不對，先做其他事。

```yaml
ryan_decision:
  decision: "defer"
  defer_reason: "先完成 M3 Rust 引擎對接"
  defer_until: "M3 完成後"
```

### 12.8 蒐集更多證據

要求 Aris 補資料後重新送審。

適用：證據不足但問題真實存在。

```yaml
ryan_decision:
  decision: "gather-evidence"
  evidence_request: "請補上 timeout 邊界測試（0s、1s、120s）的測試結果"
```