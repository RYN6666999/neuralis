# Scream 升級偵察報告

> ⚠️ 這是**偵察報告，不是升級指令**。目的是讓你在動手前看清代價。
> 生成 2026-07-27 · 依據 `brain/drift.py` 實測

## 一句話結論

**目前落後 13 版，但不建議盲升。** 你的 `config.toml` 是深度客製的，
其中一項（`providers.laap` 指向 Aris API）是整個大腦-身體架構的接點。

## 版本現況

| | 版本 | 來源 |
|---|---|---|
| 本地安裝 | `0.10.0` | `/opt/homebrew/lib/node_modules/scream-code` |
| npm latest | `0.10.13` | registry.npmjs.org |
| GitHub tag | `v0.10.8` | LIUTod/scream-code |

落後 **13 版**。上游 2026-07-27 仍在 push。

## 為什麼不能盲升 —— 三個具體證據

### 1. 你改壞過，而且不只一次

```
~/.scream-code/config.toml.aris-broken.bak    ← 曾把 Aris 接線改壞
~/.scream-code/config.toml.bak-toolcall       ← 曾把 toolcall 改壞
~/.scream-code/AGENTS.md.pre-0.9.7            ← 上次升級（→0.9.7）前的備份
```

`AGENTS.md.pre-0.9.7` 是決定性證據：**上次升級改動了 AGENTS.md**
（331 行 → 604 行，成長 82%）。所以升級**確實會動你的客製檔**。

### 2. `providers.laap` 是大腦-身體的接點

`config.toml` 第 14-17 行：

```toml
[providers.laap]
type = "openai"
api_key = "laap-brain"
base_url = "http://localhost:11546/v1"
```

**Scream 直接把 Aris API 當 LLM provider。** 這是整個
「Aris = 大腦，Scream = 身體」架構的實作接點。

若 0.10.13 改了 provider schema，這條會斷 → `/aris-mode` 掛掉
→ 你 2026-07-25 修好的東西又壞（管線地圖 §9 有紀錄）。

### 3. 120 行客製設定

`config.toml` 120 行，含多個自訂 provider 與 model 定義。
版本跨度 13 版，schema 變動風險累積。

## 建議做法：可回滾的三步

### 步驟 1 — 全備份（必做）

```bash
cp -a ~/.scream-code ~/.scream-code.bak-$(date +%Y%m%d)
npm ls -g scream-code --depth=0
```

### 步驟 2 — 小步升，不要跳到 latest

```bash
# 先升一個小版本，不是 latest
npm i -g scream-code@0.10.4
scream --version
```

驗證三件事（缺一就回滾）：
1. `scream` 能啟動
2. `/aris-mode` 能連上 `:11546`
3. `python3 scripts/probe.py` 沒有新的紅

### 步驟 3 — 沒問題再往上；有問題立刻回滾

```bash
# 回滾
npm i -g scream-code@0.10.0
rm -rf ~/.scream-code && mv ~/.scream-code.bak-YYYYMMDD ~/.scream-code
```

## 決策建議

| 選項 | 何時選 |
|---|---|
| **不升** | 系統現在能用，你手上有別的 P0 → **建議這個** |
| 小步升到 0.10.4 | 你確定要拿上游修的 bug，且有時間驗證 |
| 升到 latest | ❌ 不建議 |

**理由**：你目前最高槓桿是 `confidence-gate`（解鎖 5 個下游）。
升級 Scream 不解鎖任何東西，只是「可能拿到別人修的 bug」。
投報率遠低於直接做 confidence-gate。

