---
title: Aris × Scream × Copilot 協調作戰計畫（P0-P2）
date: 2026-07-24
status: active
owners:
  - ryan
  - scream
  - copilot
---

# 1) 目標（白話）

先不追求更高自治，先把這三件事做紮實：

1. 任務分流可追蹤（route/task_class/lane 一致）
2. canary 真能跑常見 containable 任務（不是只打分）
3. ratchet 有可驗證的升降級資料，且不污染生產狀態

成功標準：

- lane 決策不再出現 unknown route 噪音
- sandbox lane 對至少 3 種 containable 任務可執行且有 rollback 記錄
- audit log 可一鍵輸出 lane coverage（human/sandbox/auto/deny）

---

# 2) 分工原則

- Scream：快節奏多檔案改造、workflow/skill 化、批量文檔與腳本補齊
- Copilot：風控與決策層完整性、關鍵路徑防呆、驗收與交叉檢查
- Ryan：最終策略拍板（分類邊界、auto signoff policy、放量閾值）

---

# 3) 任務拆分（P0-P2）

## P0（本輪必做）

### P0-A 路由真值表統一

Owner: Scream
Reviewer: Copilot

交付物：

- agent-sandbox/docs/verdict-contract.md（擴充 route -> task_class -> op_name）
- neuralis/scripts/agentos-aris-bridge.py（改為讀同一份映射，不再散落多處）

驗收：

- 不再出現 read/bash 被記成 unknown route
- 同一 entry 在 response context 與 scoring-audit 的 route/task_class 一致

### P0-B Canary adaptor registry（最小三類）

Owner: Scream
Reviewer: Copilot

交付物：

- agent-sandbox/sandbox_canary.py（新增 adaptor registry）
- 支援至少：file_write, local_test, compute_draft

驗收：

- lane=sandbox 時，不因 operation mismatch 直接 escalate
- 每次 canary 執行都有 outcome + rollback/commit 記錄

### P0-C Audit 與 Failure path 防呆

Owner: Copilot
Reviewer: Scream

交付物：

- neuralis/scripts/agentos-aris-bridge.py（error stringify + failure path hardening）
- docs/specs/scoring-router-canary.md（新增已知故障與修復紀錄）

驗收：

- 不再出現 slice(None, ...) 型錯誤
- 同一 entry 不會因 logging 例外無限重試

## P1（下一輪）

### P1-A 一鍵 lane coverage 驗證腳本

Owner: Scream
Reviewer: Copilot

交付物：

- agent-sandbox/scripts/verify_lane_coverage.py

驗收：

- 一個命令完成注入樣本、等待處理、輸出 coverage 與失敗原因

### P1-B Ratchet 生產/測試隔離

Owner: Copilot
Reviewer: Scream

交付物：

- ratchet path 支援 env namespace（prod/test）
- 測試注入後可自動回滾，不污染 prod

驗收：

- 測試覆蓋可重複跑，prod ratchet 不被覆寫

## P2（放量前）

### P2-A Human signoff 事件流

Owner: Scream
Reviewer: Copilot

交付物：

- needs_ryan_signoff 事件標準化（落 audit + 可被 dashboard/bridge 捕捉）

驗收：

- 可查詢某 task_class 是否待簽核，以及最近一次拒絕原因

---

# 4) 給 Scream 的對齊提問（先問再做）

請先讓 Scream 回答以下問題，再開始改碼：

1. 什麼條件下 lane=auto 仍應回退到 legacy_auto？請列具體條件。
2. file_write/local_test/compute_draft 在 canary 中各自對應哪個 op_name？
3. 當 sandbox 執行失敗時，哪一些欄位必須進 scoring-audit？
4. ratchet 測試資料如何避免污染 production？
5. unknown route 出現時，你會在 classify、map、還是 logging 哪一層補？為什麼？

判準：

- 若第 2、4 題答不清楚，先不給 P0-B 寫權限，只做文檔草稿。

---

# 5) 協作節奏（避免卡住）

1. Scream 先交 PR/patch：P0-A + P0-B
2. Copilot 交叉檢查 + 補 P0-C
3. 雙方一起跑 lane coverage
4. 再進 P1

---

# 6) 本輪我（Copilot）立即承接

1. 持續維護 bridge failure-path 防呆
2. 補 ratchet 測試/生產隔離設計（P1-B 草案）
3. 定義交叉驗收 checklist（供你與 Scream 共用）

---

# 7) 交叉驗收 Checklist

- [ ] route/task_class/op_name 三者一對一可追
- [ ] human/sandbox/auto/deny 四 lane 都有審計樣本
- [ ] sandbox failure 不會造成 bridge 例外重試風暴
- [ ] ratchet 測試注入可回滾
- [ ] launchd 管理下 bridge 可穩定重啟
