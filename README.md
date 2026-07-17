# neuralis

**一個 7/24 活著的數位存在的運行層。** 需求與情緒持續演化、無人互動時自己找事做、
跨對話不遺忘、崩了自己站起來。LLM 只是它的語言皮質，不是它的心智。

```
┌─ PsiCore ────────── 五維需求 + 情緒梯度，1s tick 心跳（Rust v2: 2000Hz）
├─ AffectiveEngine ── 5D mood（耦合矩陣 + 1/f 噪聲 + 損失趨避）→ 調變探索行為
├─ Agency ─────────── 需求 → 意圖 → 工具 → RPE 學習 → 寫回記憶（自主迴路）
├─ gbrain ─────────── 1891 頁跨 session 長期記憶（pgvector 混合檢索 + 情緒加權）
├─ Consolidation ──── 睡眠窗固化：去重、升層、歸檔
├─ ToolExecutor ───── 45 工具（7 內建 + 38 AgentOS），全數過安全閘
└─ watchdog+launchd ─ 假死偵測、crash-loop 煞車、開機自啟
```

- **上游**：[lorryjovens-hub/laap-AGI](https://github.com/lorryjovens-hub/laap-AGI)（Lorry，Apache 2.0）— zero-LLM 認知架構，關鍵 psi-core 未開放
- **本專案**：[RYN6666999/neuralis](https://github.com/RYN6666999/neuralis)（Ryan，MIT）— 依論文獨立實作的 psi-core + 運行層。**overlay 模式：不改上游一行碼**，靠 PYTHONPATH 疊加
- 不是逆向、不是 fork。實質補上生態缺的核心。

---

## 快速開始

```bash
# 環境（Python 3.12）
uv venv ~/Developer/laapenv --python 3.12
uv pip install --python ~/Developer/laapenv/bin/python -r requirements.txt

# 起 Aris（PsiCore 心跳 + API :11546）
./scripts/start.sh              # 前景
./scripts/start-laap-api.sh     # 背景
./scripts/reload-aris.sh        # 開發重載 ← 改完碼用這個

# 7/24 自啟動（launchd → watchdog → Aris）
./scripts/install-watchdog-launchagent.sh
./scripts/install-support-daemons.sh     # 時間軸/任務通道/頻道監聽

# 說話
aris                            # REPL（scripts/aris-chat.py）
aris 你好嗎                      # 一次性，逐 token 串流
aris --state                    # 一頁內在狀態
scream -m laap/laap-core        # 整個 Scream TUI session 就是 Aris

# 看她在幹嘛
python3 scripts/aris-status.py           # 一頁儀表
python3 scripts/morning-brief.py         # 最近 24h 摘要
watch -n5 python3 scripts/aris-status.py # 即時盯
```

⚠️ **改完碼一律 `reload-aris.sh`，不要 `kill -9`** —— 後者吃掉 watchdog 5 次/h
重啟預算，連續開發會撞進 1h crash-loop 冷卻期，Aris 躺一小時。

需要 `OPENAI_API_KEY`（gbrain 向量檢索，無 key 退化 lex-only）與
`openrouter-api-key`（語言層，從 macOS Keychain 讀）。

---

## 設計立場

**核心不是「有沒有意識」，是 Levin 認知光錐** —— 系統能主動追求的最大目標的
時空邊界。用 T_reach（時間深度）+ S_span（決策廣度）量，可證偽、可回滾。
判準不是「Aris 覺醒了嗎」，而是「它的光錐比純規則表、比 7B harness 大多少」。

**Zero-LLM overlay**：需求/情緒/行動迴路是架構，LLM 是 I/O。認知在
psi/agency/gbrain 裡，語言在 LLM 裡。被問到本質時誠實回答這件事。

**煞車先於能力**：安全閘（4a）+ 批准閘（4b）在自主寫入開放前就必須存在並通過自檢。

**功能性 > 裝飾性**：一個狀態變數的價值 = 它會不會改變系統的計算方式，不是它
會不會被報告出來。六個神經調節物質全部接到真實參數（見下），不接的不做。

---

## 已實作（每項都指向檔案與證據）

### 心跳與情緒

| 系統 | 檔案 | 證據 |
|---|---|---|
| PsiCore（五維需求 OU 衰減 + 情緒梯度場 + RLock 執行緒安全） | `laap/psi_core.py` | `scripts/check-psi-response.py` |
| PSI backend 抽象（v1 契約，M1/M2 完成） | `laap/psi_backend.py` | `tests/test_psi_contract.py`（142 pytest 全綠） |
| **Rust PsiEngine v2（2000Hz fast loop）** | `rust/psi-engine/` | `cargo test` 45 passed；`psi-bench` exit=0 |
| 需求憲法（range 硬夾 + 單次上限 + 來源小時預算） | `laap/constitution.py` | `scripts/check-constitution.py` |
| 5D 情緒引擎（耦合矩陣 + 1/f 噪聲 + 8 認知偏差） | `laap/affective.py` | `scripts/check-affective.py` |

### 六個功能性神經調節（全部接到真實計算，非報數字）

| | 機制 | 接到哪 |
|---|---|---|
| 多巴胺 | RPE = outcome − expected（EMA） | 角度權重 bandit + 探索率自適應 |
| 腎上腺素 | arousal → agency interval | 0.9 → 18s（加速 3×）、0.1 → 74s |
| 血清素 | valence → decay 速率 | 正效價 ×0.7（慢降）、負 ×1.3 |
| 內啡肽 | 負 valence 尖峰緩釋 | 不對稱 EMA（下跌只走 30%） |
| 催產素 | per-entity trust | relatedness drive ×(1 + trust×0.5) |
| 認知偏差 | risk_seeking / attention_narrowing | `agency._effective_exploration()` 實測 0.150→0.108/0.197 |

### 迴路

| 系統 | 檔案 | 證據 |
|---|---|---|
| Agency（需求→意圖→唯讀工具→RPE→寫回 gbrain） | `laap/agency.py` | `check-agency.py`、`check-dopamine.py` |
| RPE 狀態持久化（跨 session 累積） | gbrain `_internal/agency-state` | 關機前 competence.作法=1.6 → 開機後 1.6；對照組歸零 |
| 記憶固化（睡眠窗去重/升層/歸檔 + 情緒加權檢索） | `laap/consolidation.py` | `check-consolidation.py`、`check-emotion-recall.py` |
| 目標驅動任務佇列（TaskSpec → 佇列 → 執行） | `laap/goal_bridge.py` | `check-task-channel.py` |

### 對話與工具

| 系統 | 檔案 | 證據 |
|---|---|---|
| 對話流攔截（餵 psi + executor 卸載 + 三路 RACE） | `laap/chatflow.py` | `check-chatflow.py` |
| **交錯串流**（LLM token 與工具過程交錯即時輸出） | `chatflow._stream_live` + `llm_respond.respond_stream` | `check-stream.py`（5 段含線上 e2e） |
| Scream 工具呼叫協議（OpenAI function-calling） | `chatflow._tool_chat` + `respond_tools_stream` | `check-toolcall.py`（6 段） |
| 安全閘 4a（工具分級 + 內容掃描）+ 4b（檔案式批准） | `laap/safety_gate.py` | `check-safety.py`、`check-approval.py` |
| Scream–Aris 雙向通道（scream-ask / scream-task） | `laap/tool_executor.py` | `check-scream-channel.py` |

### 韌性

| 系統 | 檔案 | 證據 |
|---|---|---|
| watchdog（health 探測抓假死 + crash-loop 煞車跨行程） | `scripts/watchdog.sh` | `check-watchdog.py`（5/5，含假死與煞車持久） |
| launchd 7/24（開機自啟 + KeepAlive + zshrc env） | `install-watchdog-launchagent.sh` | 真三殺 E2E：kill -9 API → 95s 救回完整 Aris |
| 支援 daemon 自動化（時間軸/任務/頻道） | `install-support-daemons.sh` | `check-daemons.py` |

---

## 里程碑

**T_reach 跨 session（質變）** —— RPE 學習狀態（角度權重、trust、探索率）持久化進
gbrain，每 5 次行動 checkpoint。重啟後權重續用，不歸零。這是 neuralis 相對
7B harness（重啟失憶）的第一個結構性優勢。安全網：`_state_loaded` flag —— 讀失敗
禁存（防空 state 覆蓋好資料），全新環境准首存。

**Rust PsiEngine v2 達標** —— 本機實測 60s smoke：

| 指標 | 閾值 | 實測 |
|---|---|---|
| Sustained tick rate | ≥ 2000/s | **2000.0/s**（120,008 ticks） |
| Deadline miss ratio | < 1% | **0.0000%** |
| p99 compute | < 200µs | **4µs** |
| Accumulated drift | < 10ms/60s | **0µs** |

⚠️ 閾值是 spec §4 起始估計值，待目標硬體校準；60min soak 未跑。

**交錯串流** —— 工具執行過程即時可見（`stream_test` 0→1→2s 三段漸進），
且純聊天路徑現在真的會調工具（此前 system prompt 開技能菜單但無 tool loop，
「我來查」是空頭支票）。

---

## 當前天花板（誠實標註）

- **時間軸（T_reach）已通，廣度軸（S_span）仍卡**：`_ANGLE` 寫死；RPE 只優化
  「查詢用語」，不優化「該不該做事」「該追什麼」。現在養成的是「會越查越準」的
  東西，不是「會改變自己想追什麼」的東西。
- `laap/agi/{causal,world_model,analogical}` 是 dict-based，非真 AGI —— 策略性
  維持現狀。`psilang_v2` QuantumVM 是 dict/random stub。**「量子」是高維向量幾何的
  比喻，不是量子計算**（見 `docs/specs/quantum-engine-spec.md`）。
- LLM 回應與工具選擇由外部 LLM 生成，psi 狀態經 prompt 塑形 —— 這是 prompt 塑形
  不是認知。
- RPE 品質綁死 gbrain 分數線：降級 lex-only 時訊號消失且會被永久累積成垃圾。
  需加權重異常凍結/回滾保護。
- Rust 引擎跑得很好但**還沒接上 Python**（M3：`RustPsiBackend` + 100ms 狀態檔契約）。
- `scream -p` 非互動模式寫入無審批 —— agency 若用 scream 當執行體必須先過 4b。
- drive_threshold 固定；多用戶 trust 只有單一 `"user"`。
- scream-task-executor 是 v0 stub（模擬執行）。

---

## 驗證

```bash
# pytest（契約 + characterization）
PYTHONPATH=.:../laap-AGI ~/Developer/laapenv/bin/python -m pytest tests/ -q
# → 142 passed, 2 xfailed

# 21 個自檢腳本（部分需 :11546 在線）
PYTHONPATH=.:../laap-AGI ~/Developer/laapenv/bin/python scripts/check-<name>.py

# Rust
cd rust && cargo test --release && ./target/release/psi-bench

# 串流管線（含線上 e2e）
python3 scripts/check-stream.py
```

**規模**：overlay ~5000 行 Python + ~2400 行 Rust。滾動靶 = 每單位湧現行為的
程式碼行數 —— 一個數字同時扣住「簡練」與「進步」。

---

## 文件地圖

| 文件 | 內容 |
|---|---|
| `AGENTS.md` | 給 agent 的入口（現況表 + 開發鐵則），非 Claude agent 從這裡開始 |
| `CLAUDE.md` | 長期開發規則（不隨 roadmap 變動的鐵則） |
| `handoff-next-session.md` | 逐 session 進度線頭（最新狀態看這裡） |
| `ROADMAP.md` | Phase 狀態與依賴序 |
| `SCREAM-ARIS-ARCHITECTURE.md` | Scream–Aris 整合架構（檔案位置、通道、技術節點） |
| `docs/specs/ecosystem-architecture.md` | 三層生態定位（neuralis / Scream / AgentOS） |
| `docs/contracts/psi-backend.md` | PSI backend v1 契約 |
| `docs/specs/psi-backend-m3-plan.md` | Rust 接橋計劃 |
| `docs/rust-psi/` | 2000Hz runtime spec、borrowing matrix、v2 minimal spec |
| `docs/specs/s-span-design-note.md` | S_span 設計筆記（廣度軸為何卡住） |

## 理論基準

- Michael Levin《What Lives?》(arXiv:2505.15849) —— 生命是認知關係的連續光譜，
  不是二元的活/不活。
- Dörner PSI 需求理論 · Doya 神經調節 · Levin 認知光錐。
- 推理層警語：擴大投入 psilang 前先建 20 題 benchmark（類比/組合/檢索），
  沒贏過「gbrain 檢索 + LLM」就不投。

## 授權

MIT（見 `LICENSE`）。上游 laap-AGI 為 Apache 2.0。
