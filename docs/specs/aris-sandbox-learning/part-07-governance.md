# 第七部：人類治理與正式落地

> 對應章節：Ch 32～35
> 撰寫狀態：✅ 已完成（2026-07-18）
> 參考來源：`part-02-full-flow.md`（生命週期）、`part-04-decision-analysis.md`（決策路線）、`laap/snapshot.py`（快照）

---

## 32. Ryan 決策介面

Ryan 需要一個能快速理解候選方案並做出決策的介面。以下是介面設計概念。

### 32.1 一頁式摘要

```text
┌─────────────────────────────────────────────────────┐
│  候選變更包 #001                                    │
│  目的：S_span benchmark 加 60s timeout              │
│                                                     │
│  好處：medium  │  風險：low  │  代價：0.5h / $0    │
│  Aris 建議：✅ 批准  (信心 0.85)                    │
│                                                     │
│  diff: laap/s_span_bench.py  (+8 -2)                │
│  測試: 8 passed, 0 failed                           │
│                                                     │
│  [落地] [修改] [繼續觀察] [回退]                     │
└─────────────────────────────────────────────────────┘
```

### 32.2 查看前後脈絡

展開摘要後，看到：
- 問題描述（Chapter 5 的問題與假設）
- 問題分類、證據來源
- 如果不做的後果

### 32.3 查看完整技術細節

展開後看到：
- 修改的完整 diff
- 修改的檔案清單
- 沙箱中每個 commit 的 message

### 32.4 查看 diff

使用 Scream 的 `Read` 工具直接在終端機中顯示 diff，或寫入臨時檔案供 Ryan 審閱。

### 32.5 查看測試證據

```text
測試結果：
  ┌ existing: 6 passed, 0 failed ───── 無 regression
  ┌ new:      2 passed, 0 failed ───── timeout 行為正常
  ┌ benchmark: 0.82 → 0.82 ────────── 無效能變化
```

### 32.6 查看 Aris 建議

四面向分析的完整內容（好處、壞處、風險、代價、替代方案、證據強度、信心）。

### 32.7 查看外部 AI 意見

如有呼叫外部參謀，顯示其意見和與 Aris 建議的比較。

### 32.8 落地

Ryan 選擇落地後的流程：
1. 系統記錄 Ryan 的批准證明（timestamp + 決策理由）
2. Ryan 手動執行 cherry-pick（系統不自動合併）
3. 合併後自動跑健康檢查
4. 建立追蹤排程（7 天、30 天）

### 32.9 修改

Ryan 退回修改時，需提供修改要求（`revision_request`）。

### 32.10 繼續觀察

Ryan 選擇繼續觀察時，需指定觀察期間和觀察重點。

### 32.11 回退

Ryan 選擇回退時，需選擇回退原因分類。

### 32.12 保存決策理由

每次決策後，決策理由被保存到學習案例中。Ryan 的原文理由最優先保存（不經過 Aris 重新詮釋）。

---

## 33. 正式落地機制

### 33.1 人類批准證明

每次正式落地前，必須有可驗證的批准證明：

```yaml
approval_proof:
  approved_by: "Ryan"
  approved_at: "2026-07-18T16:00:00Z"
  approved_commit: "abc1234"
  approval_method: "manual-cherry-pick"  # 手動 cherry-pick
  decision_record: "LRN-001"             # 對應的學習案例
```

### 33.2 Cherry-pick 優先

正式落地優先使用 git cherry-pick，而不是 merge 沙箱分支：

```bash
cd ~/Developer/neuralis/
git cherry-pick <candidate-commit>
```

理由：
- cherry-pick 只帶入目標 commit 的變更
- 不會帶入沙箱中無關的 commit 或實驗遺留
- commit 歷史乾淨

### 33.3 禁止直接推送 `main`

沙箱中的任何 commit 不可直接 push 到 main。所有落地必須經過 Ryan 手動操作。

### 33.4 合併前重新跑測試

在 Ryan 執行 cherry-pick 後，落地前應重新跑一次測試，確保沙箱環境與正式環境一致：

```bash
cd ~/Developer/neuralis/
python -m pytest tests/ -v
```

### 33.5 合併後健康檢查

合併後立即執行健康檢查：

```bash
# 概念：落地後健康檢查
python scripts/aris-status.py       # 確認 Aris 正常運作
curl http://localhost:11546/health  # 確認 API 正常
python -m pytest tests/ -v          # 確認測試通過
```

### 33.6 Canary 啟用

對於高風險變更，使用 Canary 模式：
- 先在特定條件下啟用（如只在 benchmark 模式）
- 一段時間後確認無問題再全面啟用
- Canary 期間有自動回退機制

### 33.7 失敗自動停用

如果 Canary 期間檢測到異常，自動回退修改：

```yaml
auto_disable:
  trigger: "連續 3 次 health check 失敗"
  action: "git revert -no-edit <commit>"
  notify: "Ryan"
```

### 33.8 正式回退點

在正式落地前，使用 `snapshot.py` 建立回退點：

```python
from laap.snapshot import create_snapshot
sha = create_snapshot("before cherry-pick LRN-001")
```

### 33.9 落地後追蹤排程

```yaml
post_deploy_tracking:
  immediate: "health check"
  day_1: "Aris 狀態檢查"
  day_7: "7 天追蹤（學習案例填寫）"
  day_30: "30 天追蹤（學習案例填寫）"
```

---

## 34. 回退機制

### 34.1 沙箱內回退

沙箱內的回退直接使用 git：

```bash
cd /tmp/aris-sandbox-<ID>/
git checkout -- .          # 捨棄未 commit 的修改
git revert HEAD            # 回退最後一個 commit
```

### 34.2 未合併候選直接銷毀

如果候選方案從未被合併到 main，直接刪除沙箱 worktree：

```bash
git worktree remove /tmp/aris-sandbox-<ID>/
```

沙箱分支（如果有的話）保留在 repo 中作為歷史記錄，但不再 active。

### 34.3 已合併程式碼回退

如果候選方案已經合併到 main：

```bash
cd ~/Developer/neuralis/
git revert <commit-hash>    # 建立反向 commit
git push origin main
```

### 34.4 設定與環境變數回退

如果修改涉及 config 或 env 變數：
- 修改前備份原始 config
- 回退時恢復備份
- 記錄 config 變更歷史

### 34.5 資料格式回退

如果修改涉及資料格式變更，必須有 migration 回退路徑。沒有 migration 回退路徑的資料格式變更不應進入沙箱。

### 34.6 外部副作用處理

如果修改涉及外部副作用（即使不應該），回退時需檢查：
- 是否有殘留的外部服務呼叫
- 是否有殘留的檔案在沙箱外
- 是否有殘留的行程或 daemon

### 34.7 Git 未追蹤檔案保護

沙箱中可能產出 git 未追蹤的檔案（測試輸出、log、暫存檔）。回退時需清理這些檔案：

```bash
git clean -fd              # 刪除未追蹤的檔案和目錄
```

### 34.8 回退演練

定期（如每月一次）進行回退演練，確認回退機制正常運作。演練在沙箱中進行，不影響正式環境。

---

## 35. 稽核與追蹤

### 35.1 保存每次候選方案

所有候選變更包（CCP）被永久保存，結構化存儲在 `docs/specs/aris-sandbox-learning/cases/` 目錄下。

### 35.2 保存執行前預測

每個沙箱實驗的預測（好處、壞處、風險、代價、信心）被保存為學習案例的一部分。

### 35.3 保存 Aris 判斷

Aris 的四面向分析被完整保存，包括信心值。

### 35.4 保存外部 AI 意見

如有呼叫外部參謀，其完整意見被保存，包括模型名稱和原始輸出。

### 35.5 保存 Ryan 決策

Ryan 的決策（路線、理由、原文）被保存。

### 35.6 保存落地後結果

7 天和 30 天的追蹤結果被保存。

### 35.7 保存策略更新歷史

所有策略升級的版本歷史被保存，包括：
- 舊策略版本
- 新策略版本
- 升級理由
- 升級前的驗證結果（歷史回測、held-out、shadow mode）

### 35.8 每個學習結論可追溯到證據

每個學習結論（「Aris 對此類問題的好處估計偏高」）必須可追溯到支持它的具體案例。

### 35.9 禁止覆寫不利歷史

稽核記錄是 append-only。不利的歷史（失敗、回退、事故）不可被刪除或覆寫。