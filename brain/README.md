# brain/ — Neuralis 腦域

給 AI 看的入口。**30 秒內知道這裡有什麼、該去哪。**

## 讀我之前先知道三件事

1. **這裡的 `.md` 有兩種**：手寫的（`README.md`、`causal.yaml` 註解）和生成的。
   生成物開頭一定有「勿手改」標記。改生成物 = 白改，下次重跑就沒了。
2. **文件會說謊，probe 不會。** 本專案有前科：`_現況.md` 曾宣稱 relay 雙寫
   （commit `3b966ae`），實查該 hash 根本不在 repo。所以：
   **要知道「現在通不通」→ 跑 `probe.py`，不要讀文件。**
3. **`~/Developer/neuralis/laap/**` 是 path-DENY 紅線**，任何 agent 不得寫入。

## 三份地圖，分工是硬的

| 檔案 | 回答什麼 | 怎麼驗證 |
|---|---|---|
| `../topology.yaml` | **執行期**：邊現在通不通 | `scripts/probe.py` 真打一輪 |
| `causal.yaml` | **設計期**：誰卡著誰 | 不可探測，只能宣告 + 附 `src` |
| `blast.py` | **影響半徑**：動它會炸到誰 | 靜態走圖 |
| `drift.py` | **上游**：不是我的東西動了沒 | 查 npm / GitHub API |
| `context.py` | **合成**：一份給 AI 的簡報 | 生成 `CONTEXT.md` |

判斷該寫哪份的規則：
- 「A 呼叫 B 但斷了」→ `topology.yaml`
- 「A 沒做，因為 B 還沒建好」→ `causal.yaml`

## 快速上手

```bash
./brain/blast.py                    # 總覽：樞紐 + 槓桿排行 + 風險
./brain/blast.py confidence-gate    # 動它會炸到誰
./brain/blast.py 修剪cron --why      # 它被誰卡住
./brain/blast.py --risks            # 只看風險
./brain/blast.py --json             # 機器讀
./brain/drift.py                    # 上游漂移偵測
./brain/context.py --live -o brain/CONTEXT.md   # 生成 AI 冷啟動簡報
```

**新 session 開場只要一句**：讀 `brain/CONTEXT.md`。

## 系統一句話

```
LB-arcanum(記憶) → neuralis(大腦/Aris) ⇄ scream(身體)
                          ⇅
                   agentOS(38 工具)
```

- **Aris = 大腦**，`neuralis` repo，LAAP API `:11546`
- **Scream = 身體**，CLI + 42 工具
- 這個分工是 2026-07-25 定版的，別再重新討論

## 五個樞紐節點

| id | 角色 | repo | 自有？ |
|---|---|---|---|
| `neuralis` | 大腦 · 主樞紐 | `RYN6666999/neuralis` | ✅ |
| `LB-arcanum` | 語意記憶源頭 | 待確認 | ✅ |
| `agentOS` | 38 工具 registry | `RYN6666999/agent-sandbox` | ✅ |
| `scream` | 身體 · CLI | `LIUTod/scream-code` | ⚠️ **上游** |
| `laap-upstream` | PSI 引擎源頭 | `lorryjovens-hub/laap-AGI` | ⚠️ **上游** |

> ⚠️ **兩個上游不是 Ryan 的。** 他們一改可能靜默弄壞系統，
> 而目前**沒有任何 probe 在看這件事**。這是最大的外部風險。

## 目前最高槓桿（`blast.py` 實跑，非人工排序）

1. 🟡 **confidence-gate** — 解鎖 5 個下游 🔥（4 個直接，全 P0）
2. 🔴 **salience-gate** — 解鎖 2 個下游

**要動手，從 `confidence-gate` 開始，投報率最高。**

## 目前最高風險

| 風險 | 說明 |
|---|---|
| 🔴 `scream-stale` | Scream 本地 `0.10.0`，npm latest `0.10.13` — **落後 13 版** |
| 🔴 `doc-lies` | 文件宣稱 ≠ 實際。只信 probe |
| 🟡 `laap-diverged` | `feat/env-config-hermes@7f02b62` ≠ `upstream/main@c3d495c` |
| 🟡 `aris-mem-no-auth` | tunnel 無 bearer token |

## 給各個 AI 的用法

| AI | 怎麼用 |
|---|---|
| **Genspark**（雲端） | 貼 `CONTEXT.md`，或從 GitHub 讀 |
| **Claude Desktop** | 檔案系統 MCP 指向 `brain/` |
| **Scream / Aris** | `cat brain/CONTEXT.md`；`--json` 餵 gbrain |
| **Copilot** | `.github/copilot-instructions.md` 指過來 |

`CONTEXT.md` 開頭寫死「勿手改」——**沒有人能在裡面塞一句假話而不被下次重跑洗掉**。
這是針對 `doc-lies` 前科的結構性防禦。

## 維護

`causal.yaml` 是手寫的（設計決策無法自動偵測）。改它的規矩：

- 每個 blocker **必須有 `src`** 指回真實出處。沒 `src` = 幻覺，刪掉。
- 狀態只有四種：`done` / `partial` / `not_started` / `sealed`。不准自創。
- 一個項目只出現在一個 blocker 的 `to` 裡。
- `blocks` 和 `blocked_by` 只需寫一邊，`blast.py` 自動補反向。

## 為什麼這樣設計

- **不新增真相來源** — 只從既有的 `topology.yaml` + 管線地圖投影
- **不建 daemon / 不佔 port** — 已經有 9 個 daemon 了
- **不做 embedding** — gbrain 已經在做，兩套會打架
- **生成物可拋棄** — 刪掉重跑，永遠不會弄丟東西

---
*建立 2026-07-27。`causal.yaml` 資料源：Aris/Scream 完整管線地圖 v2 §6 §11。*
