<!-- 本檔由 brain/context.py 生成。勿手改 —— 下次重跑就沒了。 -->
<!-- 要改請改上游：topology.yaml / brain/causal.yaml -->

# NEURALIS — AI 冷啟動簡報

生成於 2026-07-27 18:56 CST　·　模式：live 實測

## 先讀這三條

1. **文件會說謊，probe 不會。** 前科：`_現況.md` 宣稱 relay 雙寫（commit `3b966ae`），實查該 hash 不在 repo。要知道現在通不通 → 跑 `scripts/probe.py`，別讀文件。
2. **`laap/**` 是 path-DENY 紅線**，任何 agent 不得寫入。
3. **Aris = 大腦，Scream = 身體。** 2026-07-25 定版，別再重新討論。

## 系統一句話

```
LB-arcanum(記憶) → neuralis(大腦/Aris) ⇄ scream(身體)
                          ⇅
                   agentOS(38 工具)
```

## 五個樞紐節點

| id | 角色 | repo | 自有 |
|---|---|---|---|
| `neuralis` | 大腦 · 主樞紐 | `RYN6666999/neuralis` | ✅ |
| `LB-arcanum` | 語意記憶源頭（gbrain） | `RYN6666999/LB-arcanum` | ✅ |
| `agentOS` | 工具面 · 38 工具 registry | `RYN6666999/agent-sandbox` | ✅ |
| `scream` | 身體 · CLI + 42 工具 | `LIUTod/scream-code` | ⚠️ **上游** |
| `laap-upstream` | laap-core · PSI 引擎源頭 | `lorryjovens-hub/laap-AGI` | ⚠️ **上游** |

> ⚠️ `scream` 與 `laap-upstream` **不是 Ryan 的**。他們一改可能靜默弄壞系統 → 用 `brain/drift.py` 監測。

## 執行期（實測）

- 🟢 `:11546` Aris API
- 🟢 `:11550` relay
- 🟢 `:11551` aris-memory

- 🔴 **Scream（身體）** — 本地 0.10.0 · 最新 0.10.13 · 落後 13 版
- 🟡 **laap-AGI（PSI 引擎源頭）** — 本地 feat/env-config-hermes@7f02b62 ≠ upstream/main@c3d495c（2026-07-26） · 且不在 main 分支

## 最高槓桿（blast.py 算的，非人工排序）

1. 🟡 **`confidence-gate`** — Confidence 閘（四繩計算） → 解鎖 5 個下游 🔥
2. 🔴 **`salience-gate`** — Salience 閘（什麼值得學 vs 雜訊） → 解鎖 2 個下游
3. 🔴 **`固化cron`** — 海馬→皮質升格 cron → 解鎖 1 個下游
4. 🔒 **`sandbox-lane`** — Scoring Router sandbox lane → 解鎖 1 個下游
5. 🔒 **`phase4b-approval`** — Phase 4b 人類批准閘 → 解鎖 1 個下游

**要動手就從第 1 名開始，投報率最高。**

## 風險

| | 風險 | 說明 |
|---|---|---|
| 🔴 | `scream-stale` | Scream 本地 0.10.0，npm latest 0.10.13 — 落後 13 版 |
| 🟡 | `laap-diverged` | 本地 laap-AGI feat/env-config-hermes@7f02b62 ≠ upstream/main@c3d495c |
| 🔴 | `origin-all-auto` | 152/152 筆記憶的 origin 都是 auto_generated，零筆標 human |
| 🔴 | `gbrain-never-synced` | synced_to_gbrain 0/152，而 ~/gbrain 有 4697 個 md |
| 🟡 | `aris-mem-no-auth` | aris-mem.* tunnel 無 bearer token |
| 🔴 | `doc-lies` | 文件宣稱的功能實際不存在 |

## 封印中（能開但刻意沒開）

- 🔒 **Rust PSI Backend 接線** — RustPsiBackend class 建好，但 startup.py 沒接。先試 Rust 失敗就降級 Python，Python 夠用所以沒人修。
- 🔒 **Agency Delegate** — NEURALIS_AGENCY_DELEGATE 未設定，預設 off
- 🔒 **Phase 4b 人類批准閘** — 只在 Scream 互動 TUI 存在，純 AI 模式（bridge 通道）不經過
- 🔒 **Scoring Router sandbox lane** — 程式碼在，lane 未啟用
- 🔒 **Phase 4c RSI 戰略安全層** — 刻意不做

## 執行期拓樸（topology.yaml）

7 節點 · 10 條邊（3 條 `expect: fail`）

已知紅（預期內，不是新 bug）：
- `relay_remembers_turn`：同 conversation_id 的前幾輪要回放進 messages
- `recall_not_selfinflated`：discovered_salience 只能由真 recall 賺，寫入端不得自發
- `wake_reaches_prompt`：/wake 三源內容必須真的進到 system prompt

**驗證：`python3 scripts/probe.py`** —— 這才是唯一可信的現況。

## 留言板

`Aris/留言板.md` · 1500 行 · 最後更新 2026-07-27 03:20

跨 session 永久通訊頻道。開工前先讀最新幾則。

## 工具

```bash
./brain/blast.py              # 因果總覽 + 槓桿排行
./brain/blast.py <id>         # 動它會炸到誰
./brain/blast.py <id> --why   # 它被誰卡住
./brain/drift.py              # 上游漂移偵測
./brain/context.py --live -o brain/CONTEXT.md   # 重新生成本檔
python3 scripts/probe.py      # 執行期真實現況
```

---
*生成物。改上游來源，不要改這裡。*
