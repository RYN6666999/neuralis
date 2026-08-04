# neuralis — AGENTS.md

> 本檔是**地圖**：哪個能力住哪、用哪支腳本驗。
> 不放狀態、不放數字（測試數/工具數/通過率）—— 那些寫下就開始腐敗，一律現跑。
> 沒有證據的宣稱不准寫進本檔。

## 動手前先讀這兩條（所有 agent 通用，不分廠牌）

### Step 0: 載入跨對話承諾
```bash
bash ~/check-commitments.sh
```

**鐵律一：事實只能推導，不能複製。** 抄一次 = 預約未來某天的一個謊。
**鐵律二：0 信心路由 —— 預設第一次就有問題，換一條路驗過才算數。** 產出者不得自驗。

<!-- IRON-LAW-ANCHOR: 本段由 brain/lint.py 檢查 G 盯著，刪掉會擋 commit。 -->
法條正文在 `brain/lint.py` 檔頭（唯一權威，這裡不複述）。動手前跑：

```bash
python3 brain/lint.py     # 每道檢查對應一個真實踩過的坑（幾道以輸出為準）
```

紅了就是你弄壞了 —— 修掉再 commit，不要 `--no-verify` 硬過。

### Step 1: 修東西前讀解法設計約束

`brain/fix-constraints.md` —— 五條硬約束（判準來源、觸發覆蓋率、簽名驗證、
錯誤不准靜音、換路驗證）＋ 交付格式。每條後面掛一個真實踩過的坑。

宣稱「已修復」前，先過該檔末尾的四題自檢。

## 專案概述

neuralis 是 laap-AGI（Lorry Jovens，Apache 2.0）之上的獨立認知 overlay（MIT）。
透過 PYTHONPATH 疊加，不修改上游原始碼。核心哲學：zero-LLM overlay —
需求/情緒/行動迴路是架構，LLM 只是語言皮質（I/O）。

API 常駐 `:11546`（launchd → watchdog → 完整 Aris 三層守護）。
專案全貌看 `README.md`；逐 session 進度看 `handoff-next-session.md`。

## 開發鐵則

- **改完碼重載用 `scripts/reload-aris.sh`**，不要 kill -9 等 watchdog 救
  （會吃掉 5 次/h 重啟預算，撞進 1h crash-loop 冷卻期）。
- **開工前先 `git branch --show-current`** — 主分支是 `main`（不是 master），
  功能分支多（`task-00X-*`）。一個任務一個 branch/worktree，不直接在 main 開發。
- **下「東西不存在」結論前先 `git log --all -- <path>`** — 單一分支的 `ls`
  不是 repo 全貌（2026-07-17 踩過：以為 Rust 源碼不存在，其實在 task-008）。
- **event loop 線程上不准任何同步等待**（見 CLAUDE.md 規則 14）。
- 改核心狀態格式時，必須新增對應的契約測試。
- 多 AI 平行作業：改 `chatflow.py`/`llm_respond.py` 前先 `git status` +
  `python -m py_compile` 確認基線（2026-07-17 一天內撞上兩次同檔平行編輯）。

## 地圖（不是狀態）

下表是**哪個能力住在哪個檔、用哪支腳本驗**。它不告訴你那個能力現在是不是活的 ——
狀態一律現跑：`python3 scripts/aris-status.py`、`python3 brain/lint.py`、
`python3 scripts/probe.py`。

寫死在文件裡的數字（測試數、工具數、通過率）一律不留，那是最快腐敗的東西。
要數字就跑證據欄那支腳本。

| 系統 | 檔案 | 怎麼驗 |
|---|---|---|
| PsiCore 心跳（1s tick，五維需求 + EmotionGradient + AffectiveState） | `laap/psi_core.py` | `check-psi-response.py` |
| PSI backend v1 抽象（M1 adapter + M2 呼叫點遷移完成） | `laap/psi_backend.py`、`docs/contracts/psi-backend.md` | `pytest tests/`（數字現跑，不寫死） |
| **Rust PsiEngine v2（fast loop，⚠️ 仍未接上 Python）** | `rust/psi-engine/` | `cargo test`、`psi-bench`。注意 `RustPsiBackend` 只有 start/healthy/stop，缺 get_state —— 開 `NEURALIS_PSI_BACKEND=rust` 會讓 API 啟動即死（2026-08-01 實際發生） |
| 需求憲法（range/單次上限/來源小時預算） | `laap/constitution.py` + `need_constitution.json` | `check-constitution.py` |
| 5 維情緒引擎（耦合矩陣 + 1/f 噪聲 + 認知偏差） | `laap/affective.py` | `check-affective.py` |
| 對話流攔截（餵 psi + executor 卸載 + 三路 RACE） | `laap/chatflow.py` + `llm_respond.py` | `check-chatflow.py`、`check-psi-response.py` |
| **交錯串流（LLM token × 工具過程即時交錯）** | `chatflow._stream_live`、`llm_respond.respond_stream`、`tool_executor.stream` | `check-stream.py` 5 段（含線上 e2e） |
| Scream 工具呼叫協議（function-calling，engine=psi-llm-tools） | `chatflow._tool_chat`、`respond_tools_stream` | `check-toolcall.py` 6 段 + `scream -p` E2E |
| Agency Loop（需求→意圖→唯讀工具→回寫 gbrain） | `laap/agency.py` | `check-agency.py`、`check-agency-intent.py` |
| RPE 多巴胺（角度權重 bandit + 探索率自適應 + gbrain 持久化） | `laap/agency.py` | `check-dopamine.py`；狀態存 `_internal/agency-state` |
| 記憶固化循環（睡眠窗去重/升層/歸檔 + 情緒加權檢索） | `laap/consolidation.py` | `check-consolidation.py`、`check-emotion-recall.py` |
| 目標驅動任務佇列（TaskSpec → 佇列 → 執行） | `laap/goal_bridge.py` | `check-task-channel.py` |
| 安全閘 4a（工具分級 + 內容掃描）+ 4b（檔案式批准閘） | `laap/safety_gate.py` + `approve-tool.sh` | `check-safety.py`、`check-approval.py` |
| Scream–Aris 雙向通道（scream-ask 30s / scream-task 120s） | `laap/tool_executor.py` | `check-scream-channel.py` |
| watchdog + launchd 7/24（health 探測抓假死、煞車跨行程） | `scripts/watchdog.sh`、`install-watchdog-launchagent.sh` | `check-watchdog.py` 5 段 |
| **支援 daemon 自動化（phase-logger/task-executor/monitor）** | `install-support-daemons.sh` | `check-daemons.py` |
| laap-brain MCP（cognitive_state/recall_memory/bootstrap/reflect/express） | 上游 `mcp_server/`，註冊見 `scream-code/mcp.json` | scream E2E |
| Scream TUI 通道（狀態列 + aris-mode 流式 + 時間軸） | `tool_executor.py` → `/tmp/laap-tool-status.json`；4 個 dist 補丁 | patch 後 `node --check` + scream 實跑 |
| 可觀測儀表 | `laap/status.py` → `status.json`；`aris-status.py`、`morning-brief.py` | 實跑輸出 |

**工具**：數量不寫在這裡。以 `list_tools()` 為準，或看 bridge 啟動 log 的「路由: N 條」。

## 已知限制（誠實標記）

- `laap/agi/{causal,world_model,analogical}` 是 dict-based，非真 AGI —
  策略性維持現狀；psilang_v2 QuantumVM 是 dict/random stub（見
  `docs/specs/parked/quantum-engine-spec.md`：「量子」是高維向量幾何的比喻，
  不是量子計算）。
- LLM 回應與工具選擇由外部 LLM 生成，psi 狀態經 prompt 塑形 — 這是
  prompt 塑形不是認知，被問本質時誠實回答。
- **KNOWN-ISSUE-1**：relatedness 主導時 `_update_attention` 引用不存在的
  `AttentionFocus.SOCIAL` → `process_input` 拋 AttributeError（production
  被 chatflow try/except 吃掉 = psi feed 靜默失效）。待獨立 PR 修。
- `PsiCore.stop()` 不 join 執行緒；快速 stop→start 可能短暫雙心跳。
- affective 的 1/f 噪聲用未播種的 numpy RNG，不可重現 — 跨語言相容測試
  以 noise_amplitude=0 配置進行。
- gbrain recall 同步阻塞 ~1s（chat 路徑已改平行召回 + 下輪 stash，不擋回應）；
  RPE 品質依賴 embedding（無 key 退化 lex-only）。
- `scream -p` 非互動模式寫入無審批 — agency 若要用 scream 當執行體，
  必須先過 4b 批准閘。
- drive_threshold 固定；多用戶 trust 只有單一 `"user"`。
- `tool_executor._popen_lines` 逾時只在行間檢查（沉默長行程要等下一行才被殺）。
- `scripts/scream-task-executor.py` 是 v0 stub（模擬執行，未真呼叫 Scream 工具）。
- `tests/test_psi_callsite_migration.py` 的 AgencyLoop fixture 用 `__new__`
  繞過 `__init__` 手動設屬性 — AgencyLoop 新增 instance 屬性時要同步補，
  否則 `_evaluate`/`_act` 撞 AttributeError。

## 當前優先順序

1. **M3 接橋**：`RustPsiBackend`（PyO3）+ 100ms 寫 `state/latest.json` + 對拍。
   引擎已達標，缺 Python 側消費者。見 `docs/specs/psi-backend-m3-plan.md`。
2. **S_span 廣度軸**：`_ANGLE` 寫死是當前最大天花板。關鍵理解見
   `docs/specs/s-span-design-note.md`（廣度靠「既有需求有多種動作」，
   不是鋪滿五個需求的查詢角度）。
3. **T4**：Scream 全 TUI 互動驗收矩陣（需人在鍵盤前）。

## 驗證

```bash
# pytest（契約 + characterization）
PYTHONPATH="$PWD:${LAAP_ROOT:-../laap-AGI}" \
  "${LAAP_PYTHON:-python3}" -m pytest tests/ -q

# 自檢腳本（ls scripts/check-*.py 看有幾支，部分需 :11546 在線）
PYTHONPATH="$PWD:${LAAP_ROOT:-../laap-AGI}" \
  "${LAAP_PYTHON:-python3}" scripts/check-<name>.py

# Rust
cd rust && cargo test --release && ./target/release/psi-bench

# daemon 健康
python3 scripts/check-daemons.py
```

**串流/工具管線改動的必跑檢查**：串流進行中打 `/health` 必須 200 —
event loop 阻塞在單請求測試下完全看不出來。

## 啟動

```bash
./scripts/start.sh                        # 前景，PsiCore 心跳 + API :11546
./scripts/start-laap-api.sh               # 背景（委派 start.sh）
./scripts/reload-aris.sh                  # 開發重載（正規路徑）
./scripts/install-watchdog-launchagent.sh # 7/24 自啟動
./scripts/install-support-daemons.sh      # 三隻支援 daemon
```

## 連線 timeout 防護

### 已知 timeout 來源（依頻率）
1. OpenRouter → DeepSeek V4 Flash 網路不穩（`APIConnectionError`）
2. Aris 本地 API（`localhost:11546`）watchdog 重啟途中 ~90s 不可用
3. Cline API 5 小時 rate limit（429）
4. Scream CLI 60s idle timeout（長思考無 token 輸出時觸發）

### 減少發生率的規則
- **長命令一律背景執行**：`cargo build`、`pip install`、`npm install` 等超過 10s 的命令
  用 `run_in_background=true` + `TaskOutput` 取結果。不要讓它們卡在前景連線層。
- **Bash 預設 timeout 設 30s**：快速查詢（`ls`、`grep`、`which`）設短 timeout。
  需要更長時間的任務明確設 `timeout: 120` 或背景執行。
- **LLM 重試已內建**：`llm_respond.py` 的 `_retry_call()` 對網路瞬斷自動重試
  （`NEURALIS_RETRY_MAX=2`，`_RETRY_BASE_DELAY=1s`，exponential backoff）。
- **健康檢查前綴**：`check_health()` 在 LLM 呼叫前快速確定 API 是否在線
  （`NEURALIS_HEALTH_TIMEOUT=5`），不在 watchdog 重啟途中硬等 timeout。
