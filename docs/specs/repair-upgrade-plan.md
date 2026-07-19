---
title: 修復升級計劃 — 從 backup-aris-broken 主流出穩定版
date: 2026-07-20
status: approved
tags: [repair, upgrade, snapshot, rollback, priority]
---

# 修復升級計劃

> 2026-07-20 根據 commit forensic 結果制定。
> 前提：`main` 分支停在 `4c5e421`（07-18 17:14），
> `backup-aris-broken-20260719` 保存了 24 個未進 main 的 commit，
> 其中包含 **3 個已修復的破壞事件**和 **21 個需要篩選合併的新功能/修復**。

## 當前狀態摘要

```
main (4c5e421) ── 穩定，但缺少 07-18 17:14 之後的所有新功能
  │
  └── backup-aris-broken-20260719 ── 24 commits，包含：
       ├── 🔴 已修復的破壞事件
       ├── 🟢 乾淨的新功能/修復
       └── 🟡 需審查的大型新增
```

## 破壞事件回顧（已修復，合併時注意順序）

| 事件 | Commit | 壞掉原因 | 修復 commit | 合併順序 |
|------|--------|---------|------------|---------|
| Ponytail 屠殺 | `5dcd0a3` | 合併時砍掉 import、shell=True、索引錯 | `4ea4d89`（**後於** ponytail 合併） | ponytail → fix |
| 憑證隔離死碼 | `28e9d5e` | 隔離接進 sandbox.py 但 executor 沒接 | `4ea4d89` 一併修 | 接在 ponytail fix 後 |
| Aris-mode 錯 patch | `43034e9` | 誤把 bypass 加回，丟失工具 | `f3f9540`（**後於** 43034e9 合併） | 錯 patch → 移除 patch |
| npm update 靜默洗 patch | `795fcb0` | bundle 被取代無警告 | `check-scream-patches.py` 新增 | 獨立，無依賴 |

## 修復升級執行序

### Phase 0：安全網（已做 ✅）

- [x] `pre-upgrade-20260720` git tag
- [x] `scripts/snapshot.sh` — 三層快照（git + state tar + gbrain）
- [x] `scripts/rollback.sh` — 三層回滾（停 daemon + git reset + state restore + gbrain）
- [ ] `watchdog.sh` +12 行 — `~/.aris-halt` 熔斷檢查（見 safe-upgrade-rollback-plan.md §kill-switch）
- [ ] `~/aris-snapshots/` 保留輪替機制

### Phase 1：P0 修復 — 直接影響使用體驗（優先合併到 main）

順序重要，因為 fix commit 依賴於被它修復的 commit：

```bash
# 1. 先 cherry-pick ponytail 本身（要砍的 code）
git cherry-pick 5dcd0a3

# 2. 立刻接 ponytail 的 fix（修砍壞的 executor + sandbox 安全隔離）
git cherry-pick 4ea4d89

# 3. 補齊三個缺口（憑證隔離 + path-DENY 共用 + 統一輸出格式）
git cherry-pick 28e9d5e

# 4. 瞬斷重試（A2 — 止血「繼續」痛點）
git cherry-pick 2cc2ef4
```

驗收：`pytest tests/` 全綠 + executor 四工具實測 success:true + API key 不外洩。

### Phase 2：P1 功能 — 低風險新功能

```bash
# 5. patch 健康檢查（獨立，零風險）
git cherry-pick 795fcb0

# 6. 回合中止觀測層（獨立，新增）
git cherry-pick 29788c4

# 7. Aris 讀圖路由（獨立，Scream 放行圖片）
git cherry-pick 2f6cce3

# 8. 修 vision model 下架（gemini 換版）
git cherry-pick d08d3ac

# 9. 修含圖請求 aiohttp client_max_size
git cherry-pick 4dd2f4d

# 10. timeout 30→120s
git cherry-pick edd9c9e

# 11. 修 image_url vision routing + MCP fallback + TUI scroll
git cherry-pick a188d38
```

驗收：`python3 -m pytest tests/` + `./scripts/check-scream-patches.py` ✅

### Phase 3：P2 功能 — 需審查的大型新增

| Commit | 內容 | 審查重點 |
|--------|------|---------|
| `3163513` | Aris 自動記憶系統（B1-B6, +549 行） | 資料庫 schema、記憶迴圈、與現有記憶系統的衝突 |
| `b2c15df` | S1 RPE 工具選擇學習 | 只影響 agency 背景迴圈，不影響對話 |
| `5a3094d` | S1 度量驗收 benchmark | 獨立測試，低風險 |
| `442afa6` | canary executor 監督模式 | 新功能，預設關閉 |
| `77e2027` | S2-shadow 前瞻預測器 | 新功能，預設關閉 |
| `aa7d009` | pre-commit gate + 測試套件 | 純新增基礎設施，推薦合併 |

```bash
# 12-17. 逐一審查後 cherry-pick
# 每個 commit 獨立分支 review → 確認無衝突 → 合入
```

### Phase 4：P3 設定 — 個人偏好

| Commit | 內容 | 決策 |
|--------|------|------|
| `122959d` | 預設 Aris 直通模式 | 你有 `default_model=laap/laap-core` 就不需要 |
| `1d4ad4e` | 預設 yolo + wolfpack + aris-mode | 同上，aris-mode 是 no-op |
| `43034e9` | aris-mode 整合（已由 `f3f9540` 反轉） | **不要合併**，已由後續 commit 證明是錯的 |
| `f3f9540` | 移除錯誤的 aris patch | 如果合了 `43034e9` 才需要合這個來反轉 |

**建議：Phase 4 全部跳過。** `default_model=laap/laap-core` 已經 cover 了 Aris 直連需求。

## 不做的（確認保留在 backup branch）

- ❌ `43034e9` — aris-mode 錯 patch（已被 `f3f9540` 證明是設計錯誤）
- ❌ aris-mode 相關的預設值設定 — 你的 config.toml 已經處理

## 風險對照

| 風險 | 影響 | 緩解 |
|------|------|------|
| cherry-pick 順序錯（ponytail fix 先於 ponytail） | build 壞 | 依 Phase 1 順序執行 |
| 大型 commit（+549 行）引入衝突 | 審查時間長 | Phase 3 獨立 branch review |
| 記憶系統蓋到現有 gbrain 資料 | 資料遺失 | Phase 3 前先用 snapshot.sh 備份 |
| 合併後 test 不通過 | 功能異常 | 每 Phase 完跑 `pytest tests/` |

## 驗收總檢查（全部完成後）

```bash
# 1. 測試
pytest tests/ -v

# 2. Patch 健康
./scripts/check-scream-patches.py

# 3. Executor 工具
python3 -c "from scripts.scream_task_executor import execute; print(execute('bash', 'echo hello'))"

# 4. 憑證隔離
python3 -c "from scripts.scream_task_executor import execute; r=execute('bash', 'echo \$OPENAI_API_KEY'); print('OK' if 'sk-' not in r['result'] else 'LEAK!')"

# 5. Aris 啟動
./scripts/reload-aris.sh && curl http://localhost:11546/health
```