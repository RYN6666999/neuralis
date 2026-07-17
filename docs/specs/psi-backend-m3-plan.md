---
title: PSI backend M3 — Rust core 接管計劃
date: 2026-07-17
status: planned
tags: [psi, rust, backend, roadmap]
---

# PSI backend M3 — Rust core 接管

M1（`laap/psi_backend.py` 介面抽象，行為不變）與 M2（生產呼叫點遷移到 backend）
已完成（commits `bc3b690`…`ab14499`）。M3 = Rust core 真正接管。

## 前置盤點（2026-07-17 掃描結果）

- `rust/` 只有 `target/` 建置產物（`libpsi_engine.rlib` + `psi-bench` release，
  2026-07-16 建），**源碼不在 repo** — M3 第一步是找回源碼位置或從 bench 二進位
  對應的 commit 重建。`rust/target/` 已入 .gitignore。
- 2000Hz runtime 規格與 PSI borrowing matrix 見最近 docs commits
  （`13776ab`、`5cacc56`、`aef87f4`、`c0a576a`、`7ebcf82`）。
- 作者檔案契約：`aris_brain/state/latest.json` 本該由 Rust psi core 每 100ms 寫，
  現由 `chatflow._write_author_state` 在 chat 時間點代寫（workaround）。

## M3 步驟

1. **源碼歸位**：找回 psi_engine Rust 源碼（或重建），入 `rust/src` + `Cargo.toml`
   進 git。CI 至少 `cargo build --release + cargo test`。
2. **RustPsiBackend**：實作與 `PythonPsiBackend` 同介面（`get_state` /
   `process_input` / `post_affective_event` / `start` / `stop`），FFI 走
   PyO3 或 subprocess+IPC（傾向 PyO3 — psi-bench 已證明可編）。
   `NEURALIS_PSI_BACKEND=python|rust` 切換，預設 python（煞車先於能力）。
3. **狀態檔契約**：Rust core 內建每 100ms 寫 `state/latest.json`（原子寫，
   schema 與 `_write_author_state` 現行輸出一致）。切 rust backend 後
   chatflow workaround 自動退役（偵測檔案新鮮度 < 1s 就不代寫）。
4. **對拍驗證**：同輸入序列餵兩個 backend，需求/情緒軌跡差異在容忍帶內
   （OU 過程有噪聲 — 對拍比分佈不比逐點）。`scripts/check-psi-backend.py`。
5. **效能閘**：psi-bench 2000Hz 目標達標才切預設；未達標 rust backend 停留 opt-in。

## 不做（邊界）

- 不動五維需求結構與持久化煞車邏輯（養成期鐵則）
- 不在 M3 引入新行為 — 純執行引擎替換，行為漂移 = 回退訊號

## 完成條件

- [ ] rust 源碼在 repo、CI 綠
- [ ] `NEURALIS_PSI_BACKEND=rust` 全自檢綠（check-psi-response / check-agency /
      check-affective / 新 check-psi-backend）
- [ ] state/latest.json 100ms 節奏由 Rust 寫、chatflow workaround 退役
- [ ] 對拍 + 2000Hz bench 報告落 docs/benchmarks/
