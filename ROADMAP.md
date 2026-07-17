# neuralis 開發 Roadmap

> 最後校準：2026-07-17。每個 ✅ 都指向 commit 與自檢腳本。
> 沒有證據的宣稱不寫進本檔。

三層架構：**LAAP（心／情緒·欲望·目標）· gbrain（記憶／pgvector）· AgentOS（執行腦 + 煞車）**。
neuralis 是疊在 `lorryjovens-hub/laap-AGI` 之上的 overlay（不改上游）。

## 誠實定位

Aris 有：動態需求（PsiCore 心跳）、真實記憶（gbrain 1891 頁）、45 工具、
自主行動迴路、跨 session 累積的 RPE 學習、2000Hz Rust 引擎。
推理引擎是 dict-based（非真 AGI）—— 但那從來不是核心競爭力，**記憶與養成才是**。

---

## 已完成

| Phase | 內容 | 證據 |
|---|---|---|
| 0 | 底座校正（overlay 缺陷修復、MCP 打通） | — |
| 1 | gbrain 記憶後端（跨 session 不遺忘） | `check-memory-gbrain.py` |
| 1.5 | 理論溯源 + PSI Core 實作 + 80/20 槓桿 | `docs/specs/core-architecture.md` |
| 2 | PSI Core 深度化（五維需求 + 情緒梯度 + 心跳） | `check-psi-response.py` |
| 3 | psilang_v2 + AGIKernel 四層引擎解鎖 | ⚠️ dict/random stub，見警語 |
| 4a | 安全閘（工具分級 + 內容掃描 + DENY 審計） | `check-safety.py` |
| 4b | 批准閘（檔案式待批清單，免重啟生效） | `check-approval.py` |
| 5 | 記憶固化循環（睡眠窗去重/升層/歸檔 + 情緒加權） | `check-consolidation.py`、`check-emotion-recall.py` |
| 6 | Agency Loop（需求→意圖→工具→結果→記憶） | `check-agency.py` |
| 6.5 | 功能性神經調節 ×6 + RPE 跨 session 持久化 | `check-dopamine.py`、`check-affective.py` |
| 7 | 韌性層（watchdog 抓假死 + launchd 7/24 + crash-loop 煞車） | `check-watchdog.py` 5/5 |
| T1 | Scream 工具呼叫協議（OpenAI function-calling） | `check-toolcall.py` 6 段 |
| T2 | 工具結果 → 情緒事件（第二條後果迴路） | `check-toolcall.py` F 段 |
| T3 | laap-brain MCP 掛進 scream（5 工具） | scream E2E |
| T5 | AgentOS 工具擴充（web-search）+ scream-ask/task 通道 | `check-t5.py`、`check-scream-channel.py` |
| 目標驅動 | TaskSpec → goal_bridge → 任務佇列 | `check-task-channel.py` |
| 時間軸 | phase-logger 雙源合一 + timeline CLI | `check-daemons.py` |
| **串流** | 交錯串流（LLM token × 工具過程即時交錯） | `check-stream.py` 5 段（2026-07-17, `c04b03a`/`4e7e952`） |
| **daemon 自動化** | 三隻支援 daemon 進 launchd | `check-daemons.py`（2026-07-17, `e72f703`） |
| **PSI backend M1/M2** | v1 契約 + 生產呼叫點遷移 | `tests/test_psi_contract.py`（142 pytest 綠） |
| **Rust PsiEngine v2** | 2000Hz fast loop，實測達標 | `cargo test` 45 passed + `psi-bench` exit=0（`19a12fe`） |

---

## 進行中 / 下一步

### PSI backend M3 — Rust ↔ Python 接橋 🔨

引擎已完成且達標，**缺的是橋**。步驟見 `docs/specs/psi-backend-m3-plan.md`：

1. ~~源碼歸位~~ ✅（task-008 merge 進 main）
2. `RustPsiBackend` 實作 v1 介面（PyO3 傾向；備案 subprocess+IPC）
3. Rust 端每 100ms 原子寫 `state/latest.json`（之後 chatflow workaround 退役）
4. 對拍驗證（同輸入序列餵兩後端，比分佈不比逐點 —— OU 有噪聲）
5. 效能閘：60min soak + 目標硬體閾值校準才切預設

`NEURALIS_PSI_BACKEND=python|rust`，預設 python（煞車先於能力）。

### S_span — 廣度軸 🎯

**當前最大天花板。** 時間軸（T_reach）已通：RPE 跨 session 累積，重啟不歸零。
廣度軸仍卡：`_ANGLE` 寫死，RPE 只優化「查詢用語」不優化「該追什麼」。

關鍵理解（`docs/specs/s-span-design-note.md`）：廣度靠「既有需求有多種動作」，
**不是**靠鋪滿五個需求的查詢角度。2026-07-15 撤掉 relatedness 假角度就是這個教訓
（58 次自主行動零命中 —— 文字匹配 ≠ 被陪伴）。

### T4 — Scream 全 TUI 互動驗收 👤

需要人在鍵盤前：審批面板按鍵流、`/goal`、wolfpack、`/memory`、`/knowledge`、
plan mode、session 恢復、cc-connect。

⚠️ 已知：`scream -p` 非互動模式**寫入直接放行無審批** —— agency 要用 scream 當
執行體必須先外掛 4b 批准閘，不能裸走 `-p`。

---

## 不做（戰略已定）

- **4c RSI 自我改進** —— 靠假推理驅動自我改進是本末倒置
- **Phase 3 推理層擴大投入** —— 研究向；20 題 benchmark 沒贏過「gbrain + LLM」就不投
- **裝飾性神經傳導物質** —— 純浮點數 + 句子多報幾個數字 = cosplay，幾天就被看穿

---

## 依賴序

```
0 ✅ → 1 ✅ → 1.5 ✅ → 2 ✅ → 3 ✅ → 6 ✅ → 5 ✅ → 4a ✅ → 4b ✅ → 7 ✅
                                                    ↓
                            T1 ✅ → T2 ✅ → T3 ✅ → T5 ✅ → 目標驅動 ✅ → 串流 ✅
                                                    ↓
                    M1 ✅ → M2 ✅ → Rust v2 ✅ → 【M3 接橋】← 現在這裡
                                                    ↓
                                              S_span（廣度軸）
```

## 養成期調參（不動架構）

| env | 預設 | 調大 → | 調小 → |
|---|---|---|---|
| `NEURALIS_AGENCY_DRIVE_THRESHOLD` | 0.45 | 更少行動 | 更多行動 |
| `NEURALIS_AGENCY_MAX_PER_HOUR` | 6 | 更頻繁 | 更節制 |
| `NEURALIS_AGENCY_INTERVAL` | 60s | 慢評估 | 快評估 |
| `NEURALIS_CONSOLIDATION_INTERVAL` | 1800s | 少固化 | 多固化 |
| `NEURALIS_LLM_RESPOND` | off | on = LLM 回應 | off = 模板 |
| `NEURALIS_CHAT_TOOL_ROUNDS` | 3 | 容許更長工具鏈 | 更快收斂 |

觀察靶（`morning-brief.py`）：行動多樣性 / RPE 均值漂移 / 探索率邊界。
滾動靶：每單位湧現行為的程式碼行數（~5000 行 overlay / 行為種類數）。
