# neuralis 開發 Roadmap

三層架構：**LAAP（心 / 情緒·欲望·目標）· gbrain（記憶 / pgvector）· AgentOS（執行腦 + 煞車）**。
neuralis 是疊在 `lorryjovens-hub/laap-AGI` 之上的 overlay。此檔是總圖；每階段的入口線頭見
[`handoff-next-session.md`](handoff-next-session.md)。

## 誠實定位
修好後能看到的是「system prompt 被注入會演化的情緒/需求/目標向量」的 agent。**不是 AGI。**
記憶目前 in-process（重啟即忘）、`laap.agi.*` 是 stub。Roadmap 就是把這些從「像活的」推向「真的記得、真的推理、真的會停」。

---

## Phase 0 — 底座校正 + scream-code 整合 ✅ 已完成（commit `be4d3b0`）
- 5 個 overlay 缺陷修復（adapter / rsi / memory_store / memory_bridge / requirements）
- scream-code MCP 整合**實測打通**（stdio handshake + 5 tools + 活的 cognitive_state）
- 量子引擎描述彙整 → [`docs/specs/quantum-engine-spec.md`](docs/specs/quantum-engine-spec.md)
- 啟動：`scripts/start-laap-api.sh` + `scream-code/mcp.json` 模板

---

## Phase 1 — gbrain 記憶後端 ⭐ 下一步（最高 ROI）
把 `memory_store.py` / `memory_bridge.py` 從 in-process 換成 gbrain（Postgres+pgvector，
1868 頁真實記憶 + 語意檢索）。**seam 已留在 `memory_store.py` 檔尾。**
- 改 4 個方法：`store`→gbrain put_page、`recall`→gbrain search/query、`get_stats`、`get_memory_embedding`→gbrain 向量檢索
- 作者端零改動（介面不變）
- 驗收：`laap_recall_memory` 從回空 → 回檢索到的真實記憶片段；重啟後記憶仍在
- **這是「假記憶→真記憶」的單點跳躍，先做這個。**

## Phase 2 — PSI Core（Rust 2000Hz 生理引擎）
把 `psi_bridge.py` 的 6 步認知循環移植成 Rust binary，每 500μs 寫 `state/latest.json`。
- 規格：[`docs/specs/quantum-engine-spec.md`](docs/specs/quantum-engine-spec.md) §1
- 起點：`laap-AGI/aris_brain/psi_jspace_bridge/psi_bridge.py`（0-dep numpy 參考）
- golden test：同輸入下 Rust 輸出 == Python 輸出
- 依賴：`serde_json`；原子寫（tmp→rename）；`psi_core_bridge.py` 已在讀那個檔，drop-in
- **這是唯一合理的 Rust 元件**（latency-critical，Python 做不好）。不要把整個 LAAP 改 Rust。

## Phase 3 — QRE / Ψ-Semiotics（幾何符號推理，解鎖 agi_kernel）
補作者缺的 `psilang_v2`（`Lexer/Parser/Compiler/QuantumVM`），解開 `agi_kernel` 的
`and False` 停用。
- 規格：[`docs/specs/quantum-engine-spec.md`](docs/specs/quantum-engine-spec.md) §2 + 作者 §8 路線圖（~1750 行）
- 起點：移植 `laap-AGI/aris_brain/psi_semiotics/psilang_hott.py`（PsiLang v3 HoTT，可跑）
- ⚠️ 研究級工程 + 作者「快幾個數量級」是未驗證聲稱 → 先做小 benchmark 再全投
- QuantumVM 介面合約見 spec §2

## Phase 4 — AgentOS 執行/安全層
用 `RYN6666999/agent-sandbox`（AgentOS）填 LAAP 的執行類 stub。
- `ASISafetyEngine` stub → AgentOS `orchestrator/safety.py`（規則先攔 rm -rf/DROP TABLE）
- `AutonomousEngine` stub → AgentOS `loop.py`/`runner.py` + `executor_registry`
- `RSIEngine` stub → AgentOS `maker/checker/repair/reflect`（真跑 pytest 驗收）
- 讓 LAAP 從「有情緒的狀態機」→「會執行、有煞車、可追溯的自主體」

---

## 依賴序
```
Phase 0 ✅ ── Phase 1 (gbrain 記憶) ── Phase 4 (AgentOS 執行)
             └─ Phase 2 (Rust PSI Core) ── Phase 3 (QRE 推理)
```
Phase 1 與 Phase 2 可並行。Phase 3 依賴 Phase 2 的底座穩定。Phase 4 依賴 Phase 1 的記憶。
