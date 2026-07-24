---
title: PSI backend M3 — Rust core 接管計劃
date: 2026-07-17
status: planned
tags: [psi, rust, backend, roadmap]
---

# PSI backend M3 — Rust core 接管

M1（`laap/psi_backend.py` 介面抽象，行為不變）與 M2（生產呼叫點遷移到 backend）
已完成（commits `bc3b690`…`ab14499`）。**引擎本體也已完成**（task-008，見下）。
M3 剩下的是「把已經跑得很好的 Rust 引擎接到 Python 這一側」。

## 前置盤點（2026-07-17，merge 後實測）

**Rust PsiEngine v2 已實作完成並達標** — `rust/psi-engine/`（task-008 分支
`a04af00`…`c70a669`，已 merge 進 main `19a12fe`）：

```
PsiEngine
├─ NeedDynamics      needs.rs      5-need OU process, serotonin, drives
├─ AffectDynamics    affect.rs     5D PAD+S+St, coupling, 1/f noise, endorphin
├─ AttentionGate     attention.rs  IDLE/TASK/LEARNING/PLANNING, hysteresis
├─ EventReducer      events.rs     18 affective events, pure fold, no I/O
├─ SnapshotPublisher snapshot.rs   atomic snapshot cell, 100Hz publish
├─ TickMetrics       metrics.rs    hdrhistogram, deadline miss, drift
└─ 2000Hz runtime    runtime.rs    spin-sleep, catch-up, circuit breaker
```

本機實測（2026-07-17 於 merge 後重跑，非引用 README）：

| 指標 | 閾值 | 實測 60s smoke |
|---|---|---|
| Sustained tick rate | ≥ 2000/s | **2000.0/s**（120,008 ticks） |
| Deadline miss ratio | < 1% | **0.0000%** |
| Peak compute | < 500µs | **44µs** |
| p99 compute | < 200µs | **4µs** |
| Accumulated drift | < 10ms/60s | **0µs** |
| Snapshot 新鮮度 | (info) | 5092 reads, 0 stale |

`cargo test --release` 45 passed（4 suites）。`psi-bench` exit=0（全閾值通過）。
⚠️ 閾值是 spec §4 起始估計值，仍待目標硬體校準；60min soak 未跑。

**還沒有的**：Rust ↔ Python 的橋。`SnapshotPublisher` 已在 Rust 端以 100Hz 發佈
快照，但沒有任何 Python 消費者；`laap/psi_backend.py` 目前只有 `PythonPsiBackend`。

作者檔案契約：`aris_brain/state/latest.json` 本該由 psi core 每 100ms 寫，
現由 `chatflow._write_author_state` 在 chat 時間點代寫（workaround）。

## M3 步驟（源碼已在，從第 2 步開始）

1. ~~源碼歸位~~ ✅ 已完成（task-008 merge 進 main，`cargo test` + psi-bench 實測綠）。
   待補：CI 加 `cargo test --release` job。
2. **RustPsiBackend**：實作與 `PythonPsiBackend` 同介面（v1 十法 + presentation +
   B-surface）。

   **裝法拍板（2026-07-24 Ryan）：subprocess + 檔案 IPC，不用 PyO3。**
   - 理由一（原架構）：`state/latest.json` 本來就是作者設計「Rust psi core 每 100ms 寫、
     整個 aris_brain 讀」的契約（chatflow `_write_author_state` 只是暫代寫的 workaround）。
     subprocess/檔案 IPC = 回到原設計；PyO3 才是偏離。07-14 也已判「Rust 走檔案 IPC 解耦，
     不需 FFI/PyO3」。
   - 理由二（崩潰隔離）：PyO3 同行程 → Rust panic/segfault 帶走整個 Aris API
     （event-loop 凍結那三次坑的同型風險）。subprocess → Rust 崩了 Python 不死，
     watchdog 重啟 daemon，代價僅 ~100ms 延遲 + 一份序列化。
   - `NEURALIS_PSI_BACKEND=python|rust` 切換，**預設 python**（煞車先於能力）。

   **drift-safety 拆分（關鍵）：Rust 只服務「生理原始態」，presentation 留 Python。**
   - Rust daemon 寫的 snapshot 只含**原始生理量**：5 needs + drives、5 affect 維
     （P/A/D/S/St）、attention 模式、dominant_need、endorphin、tick、ts。
   - Python `RustPsiBackend` 的 `get_state`/`get_drives`/`get_dominant_need` → 讀 snapshot。
   - `get_state_label`/`format_state_injection`/`get_cognitive_bias` → **在 Python 端用
     現有 presentation 碼從 snapshot 算**（保 QUIRK-1，零漂移；不讓 Rust 複製 quirk）。
   - `process_input`/`post_affective_event`/`satisfy` → append 到 input 通道（Rust drain）。
   - B-surface（`needs`/`emotion`/`affective`）production 呼叫點極少（實測多在 core 內部），
     用 snapshot 唯讀代理頂；若有 live-mutation 呼叫點先遷移到 v1 方法。

   **state/latest.json schema（與現行 `_write_author_state` 一致）：**
   `{cycle, needs:{name:current}, attention, emotion, daemon_uptime, ts, source}`
   （Rust 版 `source="neuralis-rust-psi"`；原子寫 tmp→replace 同現行）。
3. **狀態檔契約**：讓 Rust `SnapshotPublisher` 直接每 100ms 原子寫
   `state/latest.json`（schema 與 `_write_author_state` 現行輸出一致）。
   切 rust backend 後 chatflow workaround 退役（偵測檔案新鮮度 < 1s 就不代寫）。
4. **對拍驗證**：同輸入序列餵兩個 backend，需求/情緒軌跡差異在容忍帶內
   （OU 過程有噪聲 — 對拍比分佈不比逐點）。`scripts/check-psi-backend.py`。
5. **效能閘**：切預設前跑 60min soak + 目標硬體閾值校準。

## Schema 決策 + 進度（2026-07-24）

**A/B 拍板：B 路（Ryan「信任一下」）。** Rust 寫**原生** schema
（`neuralis-rust-psi/v1`），Python readers 遷移去讀它，不做 A 路的「模擬 Python 舊
schema + 複製 attention 邏輯」。理由：兩引擎詞彙本就不同（attention：Rust
Idle/Task/Learning/Planning + 遲滯 vs Python IDLE/SOCIAL/TASK + 需求映射；emotion/affect
結構亦異），A 路要 Rust 旁路自己的模型去假裝 Python，不誠實且脆。B 路 blast radius 大
（aris_brain / cognitive_bus / integration / status.py readers 要跟），但長期乾淨，
attention 差異用對拍容忍帶（比分佈不比逐點）接受。

**進度：**
- ✅ **B1 daemon publish**：`rust/psi-engine/src/statefile.rs`（純序列化 + 原子寫，
  5 單元測試）+ `src/bin/psi_daemon.rs`（2000Hz loop + 每 100ms 原子寫 latest.json）。
  `cargo test --release` 50 passed（45→50）。端到端煙測：2s → tick 3960（2000Hz 實跑）、
  原生 schema 合法、miss=0 drift=0。B1 scope 只 publish；Python→Rust input 通道 = B2。
- ⬜ B2 input 通道（daemon drain input.jsonl：process_input / event / satisfy）
- ⬜ B3 RustPsiBackend（Python 讀 snapshot + presentation 在 Python 算 + 寫 input +
  spawn/stop daemon；`NEURALIS_PSI_BACKEND` 切換，預設 python）
- ⬜ B3.5 Python readers 遷移到原生 schema（B 路 blast radius）
- ⬜ B4 退役 chatflow workaround（新鮮度閘）
- ⬜ B5 驗收：對拍（OU baseline 分佈）+ 60min soak（跑中）+ CI cargo job

## 不做（邊界）

- 不動五維需求結構與持久化煞車邏輯（養成期鐵則）
- 不在 M3 引入新行為 — 純執行引擎替換，行為漂移 = 回退訊號

## 完成條件

- [x] rust 源碼在 repo（main `19a12fe`）、45 tests + psi-bench 驗收綠
- [ ] CI 有 `cargo test --release` job
- [ ] `NEURALIS_PSI_BACKEND=rust` 全自檢綠（check-psi-response / check-agency /
      check-affective / 新 check-psi-backend）
- [ ] state/latest.json 100ms 節奏由 Rust 寫、chatflow workaround 退役
- [ ] 對拍 + 60min soak 報告落 docs/benchmarks/
