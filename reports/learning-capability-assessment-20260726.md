# Aris 學習能力綜合鑑定報告

**日期**：2026-07-26
**範圍**：輸入污染 → 樣板冒充 → 狀態遺失 → trust 飽和 → L1 三輪測試
**方法**：手術式修復 + 離線 harness 驗證

---

## 發現的四個洞

| # | 洞 | 類型 | 發現時間 | 修復 commit | 狀態 |
|---|-----|------|---------|------------|------|
| 1 | **輸入污染**：`_filter_blocked` 計數器未涵蓋 Python 路徑 + `last_input` 被系統提示覆蓋 | 接線壞了 | 07-26 | `ecbd73e` | ✅ 已修 |
| 2 | **樣板冒充**：`laap-fallback` 與 rules 樣板通過品質閘門冒充真回答 | 接線壞了 | 07-26 | `41408fa` | ✅ 已修 |
| 3 | **狀態遺失**：checkpoint 每 5 次動作才存，最近 1 次學習在重啟後丟失 | 接線壞了 | 07-26 | `3b654e7` | ✅ 已修 |
| 4 | **trust 飽和 + 接空鉤**：trust 數學上必然衝頂到 1.0，且接的 relatedness 增益早已接空鉤（該需求 07-15 退出 `_ANGLE`）→ 三重死 | 設計壞了 | 07-26 | `fix/trust-presence-lever` | ✅ 已修（登場感感測器） |

### 第四個洞：trust 飽和（詳細）

**位置**：`laap/agency.py:101-102` + `:216-218` + `:222-223`

```python
# 初始化（line 101）
self._trust_scores: dict = {"user": 0.3}
self._trust_decay_rate = 0.0005

# 每則使用者訊息（line 238-244, note_interaction）
old = self._trust_scores.get(entity, 0.0)
self._trust_scores[entity] = min(1.0, old + 0.03)

# 每次評估（line 216-218）
for entity in self._trust_scores:
    self._trust_scores[entity] = max(0.0, self._trust_scores[entity] - self._trust_decay_rate)

# 使用處（line 222-223）
trust = self._trust_scores.get("user", 0.0)
drives["relatedness"] = drives.get("relatedness", 0.0) * (1.0 + trust * 0.5)
```

**數學分析**：
- 每則訊息 net ≈ +0.0295（+0.03 − 0.0005/cycle × ~1 cycle/message）
- 從 0.3 到飽和 1.0 需要 ~24 次互動（約 24 分鐘密集對話）
- 從飽和跌回 0.9 需要連續 200 秒無互動（~3.3 分鐘）
- 在正常使用模式中，3.3 分鐘內幾乎必然有新訊息 → `trust[user]` 永遠在 0.95–1.0

**影響（原判 + 複查加深）**：
- `drives["relatedness"]` × (1.0 + trust × 0.5) = ×1.5 固定倍率（恒常數）
- 區辨力歸零 — 不可信使用者 vs 最信任使用者得到完全相同對待
- **複查發現更深**：relatedness 07-15 已退出 `_ANGLE`（`_form_intent` line 506 `if need not in self._ANGLE: return None`），所以 trust 推高 relatedness drive → 該需求在 `_evaluate` 被跳過 → **對哪個行動觸發零影響**。trust 三重死：飽和 + 固定倍率 + 接空鉤。且單一使用者下「熟人 vs 陌生人」無可區辨的母體。

**修復（2026-07-26，branch `fix/trust-presence-lever`）— 登場感（presence）感測器**：

Ryan 拍板：不刪、接活槓桿。trust 改量「這個人現在在不在」：

| 面向 | 舊 | 新 |
|------|----|----|
| 上升 | `+0.03`（線性、易飽和） | `+(1-t)×0.15`（遞增式，越高越難推） |
| 衰減 | `-0.0005/cycle`（幾乎不動） | `+(baseline-t)×0.05/cycle`（OU 均值回歸，會真的降） |
| 接點 | `relatedness × (1+trust×0.5)`（死鉤，刪除） | `_effective_exploration`：在場少探索、離開多探索 |

- **無飽和**：最密集互動（每週期）平衡點 = **0.79**（解析解 0.8），永不卡 1.0
- **會降**：閒置 60 週期 0.99 → 0.24（回 baseline 0.2）
- **活槓桿**：presence 0.9 → 探索 0.114；presence 0.2 → 探索 0.177（單調、有區辨力）
- 自檢：`scripts/check-trust-presence.py`（4 段全過）；全測試套件 264 passed 無回歸；已 `reload-aris.sh` 上線

---

## L1 三輪測試歷程

### 第一輪（2026-07-26，report: `restart-invariance-20260726.md`）

| 層級 | 結果 | 說明 |
|------|------|------|
| L0 | PASS | 狀態存活：11-12 欄位持久化正確 |
| L1 | INCONCLUSIVE | 卡 cooldown，情境 B 跑不出來 |
| L2 | N/A | — |

當時環境有三個已知污染：輸入污染、樣板冒充、checkpoint 每 5 次才存。

### 第二輪（2026-07-26，report: `l1-retest-20260726.md`）

| 量度 | A (初始) | B (15筆後) | C (重載) |
|------|---------|-----------|---------|
| exploration_rate | 0.245 | 0.245 | 0.245 |
| expected | 0.645 | 0.6908 | 0.6917 |
| RPE 全部正？ | — | ✅ 15/15 全部正 | — |

**L1 = INCONCLUSIBLE**

原因：mock_score 固定 0.7，所有動作同分，權重只膨脹不分化。
測到的是「無意義更新被正確保存」，不是學習。同時單次取樣不足以排除探索雜訊。

### 第三輪（2026-07-26，report: `l1-retest-r3.md`）

**先寫考卷再跑**：payoff table 在執行前封存於報告中。

**隱藏計分規則**：
- 「作法」= 0.9（正確答案）
- 其餘所有角度 = 0.1

**結果**：

| 量度 | A (初始) | B (30筆後) | C (重載) |
|------|---------|-----------|---------|
| exploration_rate | 0.215 | 0.195 | 0.195 |
| expected | 0.6917 | 0.516 | 0.516 |
| 最高權重角度 | 作法 (2.60) | 作法 (3.00) | 作法 (3.00) |
| 作法占比 (30次取樣) | 19/30 | 18/30 | 21/30 |
| RPE 正負 | — | 19正/11負 | — |

**L1 = PASS（mock 考卷）**

| 條件 | 結果 | 證據 |
|------|------|------|
| C ≈ B | ✅ | 作法=3.0, expected=0.516 完全一致 |
| C ≠ A | ✅ | A: 作法=2.60 vs C: 作法=3.0 |
| B 偏向正確角度 | ✅ | 作法 18/30, 最高權重 3.0 |

**誠實判斷**：通過的是「bandit 學習機制在乾淨模擬環境中運作正常」，
不是「Aris 在真實環境中會學習」。需要沙箱（真實 `_score_result`）才能回答後者。

---

## 取捨與缺口

### 已修復（3/4）

| 修復 | 風險 | 殘留影響 |
|------|------|---------|
| filter_blocked 計數器 | 無（模組層變數 + global 宣告，行為不變） | 無 |
| 品質閘門還原 | `laap-fallback` 被擋後走 `_psi_respond` LLM → 多一輪串行延遲 | Path A 已死（`if user_turn: llm_task = None`），但 `_psi_respond` 內有獨立 LLM 路徑 |
| checkpoint 5→1 | 單次存檔 1.26s × 6/hr = 7.5s/hr | 若 gbrain 成為瓶頸需考慮直接寫檔案 |

### 已修復（4/4，07-26 補上第四洞）

| 修復 | 風險 | 殘留影響 |
|------|------|---------|
| trust → 登場感感測器 | 中（動決策邏輯 + reload 線上 Aris） | presence 現接 exploration；未持久化「上次在場時間」，reboot 後從最後值開始衰減（首圈自然回歸，可接受） |

### 已知缺口

- Path A (`llm_task`) 被 `if user_turn: llm_task = None` 完全關閉，無任何路徑觸發
- `_rpe_buffer` 非持久化（滑動視窗，重啟後從空開始）
- `_save_state()` 斷網時靜默失敗（logger.debug → warning 已修，但資料仍丟失）
- RustPsiBackend 存在但未啟用（需設 `NEURALIS_PSI_BACKEND=rust`）

---

## 測試方法附註

### 離線 Harness

所有 L1 測試使用獨立 `/tmp/l1-harness*.py`，不修改生產碼。

**Mock 依賴**：
| 元件 | 處理方式 |
|------|---------|
| PSI (get_last_input, get_drives, get_cognitive_bias) | MockPsi |
| ToolExecutor (execute) | MockTools：回固定結果 |
| gbrain _cache_lookup | 永遠 hit（回 seed 字串） |
| _too_similar | 永遠 False（永不過濾） |
| _score_result | 第一輪：固定 0.7。第二輪：作法=0.9，其餘=0.1 |

**限制**：
- `_form_intent()` 和 `_act()` 的真實行為需 gbrain 回傳品質分數才能驗證
- mock 的分數規則直接依角度給分，真實環境中不存此規則
- RPE 學習 = bandit 權重更新，不等於真正的認知學習

---

## 下一步

1. ~~修 trust 飽和~~ ✅ 已修（登場感感測器，branch `fix/trust-presence-lever`，已上線）
2. **沙箱真考卷（最重）** — 用真實 `_score_result`（gbrain 檢索品質）取代 mock 0.9/0.1，回答「Aris 在真實訊號下會不會學」
3. **L2 測試** — 環境乾淨後的重啟不變性 + 行為差異測試
4. **觀察登場感在真運行的漂移** — `aris-status.py` 盯 trust 值，確認閒置時真的降、互動時真的升（線上驗證解析解 0.79）