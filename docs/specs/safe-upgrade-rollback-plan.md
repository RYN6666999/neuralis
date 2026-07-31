---
title: 出事能兜的升級護欄 — 三層快照 + 熔斷 + canary
date: 2026-07-19
status: plan
tags: [safety, rollback, snapshot, kill-switch, canary, upgrade]
---

# 出事能兜的升級護欄

> 前提糾正：「開分支、出事再 pull 舊版」只兜得住 **code**。Aris 的傷害有三層，
> 另外兩層在 git 之外，git 回滾救不了。本計劃補齊那兩層 + 一個能立刻叫停的開關。

## 為什麼 `git pull` 不夠

| 傷害層 | 落在哪 | git 回滾救得了？ |
|---|---|---|
| code 邏輯壞 | git tree | ✅ |
| 記憶 / RPE 權重學歪 | gbrain(Postgres, MCP 端) + neuralis 本地 `*.jsonl` / `aris_brain` / `data` | ❌ 不在 git |
| 不可逆副作用（寫檔/刪/發 LINE/打外部 API） | 已發生的行動 | ❌ 發生了就發生了 |

原則：**每層傷害都要有對應復原點，再加一個熔斷兜「來不及反應」。**

---

## 層 1｜Code（git，已有）

動手前打 tag 當回滾錨點：
```bash
git checkout -b aris/upgrade-<name>
git tag pre-upgrade-<name>-$(date +%Y%m%d)
```
出事：`git reset --hard pre-upgrade-<name>-YYYYMMDD`

## 層 2｜State 快照（新增 `scripts/snapshot.sh` + `rollback.sh`）

git 之外的狀態，動手**前**全快照。

**gbrain 記憶** — 走 MCP client、無直連 DATABASE_URL → 用官方 export（已確認 CLI 有）：
```bash
gbrain export --dir ~/aris-snapshots/gbrain-$(date +%s)/
```

**neuralis 本地狀態** — 實際存在的檔：
```bash
tar czf ~/aris-snapshots/state-$(date +%s).tgz \
  status.json *.jsonl aris_brain data
# 即 agency-audit / consolidation-audit / constitution-audit /
#    safety-audit / approvals-pending / watchdog-audit + aris_brain/ + data/
```

**rollback.sh**：停 daemon → 還原 tar → (需要時) 用 gbrain import/sync 回灌 export → 重啟。
→ 記憶學歪、權重養歪跟著回滾，不只 code。

## 層 3｜不可逆副作用（不靠回滾，靠先擋）

git + DB 都救不了「已經做的事」。這層只能事前擋：

- **executor 維持 `NEURALIS_EXECUTOR_MODE=propose`**（現預設）— 真自主委派每筆要人批准，不裸走。
- **path-DENY 保持** — Scream 永不碰 `laap/**`（Stage 0 硬邊界）。
- **dry-run 先行** — 真接 Scream 前，executor 回模擬 diff 不落盤，人看過才放行。
- **配額硬閘** — E2 成本閘（200k tokens/hr）+ `NEURALIS_AGENCY_MAX_PER_HOUR`，異常自動降頻。
- **舊批准清乾淨** — approved-tools.txt 不留 scream-task 全域批准（07-18 已撤；會被其他呼叫路徑搭便車）。

## 熔斷｜kill switch（現在沒有，必補）

一個檔案 = 全停，比 `git pull`、比等人發現都快。塞進 `watchdog.sh` 迴圈開頭：

```bash
# watchdog.sh，probe 之前先看拉閘檔
HALT="$HOME/.aris-halt"
if [[ -f "$HALT" ]]; then
    echo "[watchdog] 🛑 halt 檔存在 → 停 agency/executor + daemon（解除: rm $HALT）"
    audit halt
    kill_stale          # 收 :PORT listener + 子進程
    # 額外收背景 agency loop（若獨立行程）
    exit 0
fi
```
拉閘：`touch ~/.aris-halt` · 解除：`rm ~/.aris-halt`
**出事第一動作是拉閘，不是回滾。**

---

## 上線順序（canary，不全開）

1. `snapshot.sh`（層 1 tag + 層 2 export/tar）
2. feature branch 開發，`propose` 模式跑
3. 只放**一個** canary 委派，人看 diff
4. kill switch + watchdog 就位；盯 E3 度量漂移（選擇-outcome 相關、多樣性熵、探索率邊界）
5. 度量正常 N 輪 → 才擴大

---

## 7 項升級 × 需要哪幾層

| 升級項 | 現有 spec | code | state 快照 | 副作用擋 | kill switch |
|---|---|---|---|---|---|
| 多模態收尾（圖片路徑） | `parked/real-path-plan.md` A1 | ✅ | — | — | — |
| 導入 openspace repo（外部） | 無 | ✅ | — | 供應鏈：先讀碼不直跑 | — |
| 學白龍馬 agent（外部 repo） | 無 | ✅ | — | 同上 | — |
| LINE / TG 接入 | `parked/line-private-terminal-plan.md` | ✅ | — | webhook 簽章必驗 | 建議 |
| 分工路由 | `ecosystem-architecture.md` + 光錐 S2 | ✅ | ✅ | propose | ✅ |
| 量子推理引擎 | `parked/quantum-engine-spec.md` | ✅ | — | ⚠️ 撞 ROADMAP「不投推理層」 | — |
| 完全體認知光錐（S3 真自主） | `cognitive-light-cone-plan.md` | ✅ | ✅ | **四樣全上** | ✅ 必須 |

**判準線：** 只碰 code 的（前三項）branch 就夠。碰 state / 真自主的（分工路由、光錐 S3）
四層全要，`git pull` 兜不住。量子推理層另有戰略張力（§ROADMAP 不做清單），先過 benchmark 判決再說。

---

## 待建（純新增，不動核心碼，零風險）

- [ ] `scripts/snapshot.sh` — git tag + gbrain export + neuralis state tar
- [ ] `scripts/rollback.sh` — 停 daemon → 還原 → 重啟
- [ ] `watchdog.sh` +12 行 — `~/.aris-halt` 熔斷檢查
- [ ] `~/aris-snapshots/` 目錄 + 保留輪替（留最近 N 份）
