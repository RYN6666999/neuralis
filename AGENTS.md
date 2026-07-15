# neuralis — AGENTS.md

> 最後校準：2026-07-15（TASK-001）。每個「已完成」都指向實際檔案與自檢腳本。
> 沒有證據的宣稱不准寫進本檔。

## 專案概述

neuralis 是 laap-AGI（Lorry Jovens，Apache 2.0）之上的獨立認知 overlay（MIT）。
透過 PYTHONPATH 疊加，不修改上游原始碼。核心哲學：zero-LLM overlay —
需求/情緒/行動迴路是架構，LLM 只是語言皮質（I/O）。

本機布局：`~/Developer/{neuralis, laap-AGI, laapenv}`。
API 常駐 `:11546`（launchd → watchdog → 完整 Aris 三層守護）。

## 開發鐵則

- **改完碼重載用 `scripts/reload-aris.sh`**，不要 kill -9 等 watchdog 救
  （會吃掉 5 次/h 重啟預算，撞進 1h crash-loop 冷卻期）。
- 一個任務一個 branch/worktree，不直接在 main 上開發。
- PSI 契約見 `docs/contracts/psi-backend.md`；改核心狀態格式必須同步更新
  契約與 `tests/`。

## 現況（2026-07-15，逐項可驗證）

| 系統 | 檔案 | 證據 |
|---|---|---|
| PsiCore 心跳（1s tick，五維需求 + EmotionGradient + AffectiveState） | `laap/psi_core.py` | `scripts/check-psi-response.py`（契約見 `docs/contracts/psi-backend.md`） |
| 需求憲法（range/單次上限/來源小時預算） | `laap/constitution.py` + `laap/need_constitution.json` | `scripts/check-constitution.py` |
| 5 維情緒引擎（耦合矩陣 + 1/f 噪聲 + 認知偏差） | `laap/affective.py` | `scripts/check-affective.py` |
| 對話流攔截（餵 psi + executor 卸載 + psi-llm 回應） | `laap/chatflow.py` + `laap/llm_respond.py` | `scripts/check-chatflow.py`、`check-psi-response.py` |
| Scream 工具呼叫協議（OpenAI function-calling，engine=psi-llm-tools） | `laap/chatflow.py::_tool_chat`、`llm_respond.py::respond_tools` | `scripts/check-toolcall.py`（6 段）+ `scream -p` E2E |
| Agency Loop（需求→意圖→唯讀工具→回寫 gbrain） | `laap/agency.py` | `scripts/check-agency.py`、`check-agency-intent.py` |
| RPE 功能性多巴胺（角度權重 bandit + 探索率自適應 + gbrain 持久化） | `laap/agency.py` | `scripts/check-dopamine.py`；狀態存 gbrain `_internal/agency-state` |
| 記憶固化循環（睡眠窗去重/升層/歸檔 + 情緒加權檢索） | `laap/consolidation.py` | `scripts/check-consolidation.py`、`check-emotion-recall.py` |
| 安全閘 4a（工具分級 + 內容掃描）+ 4b（檔案式批准閘） | `laap/safety_gate.py` + `scripts/approve-tool.sh` | `scripts/check-safety.py`、`check-approval.py` |
| watchdog + launchd 7/24（health 探測抓假死、crash-loop 煞車跨行程） | `scripts/watchdog.sh`、`install-watchdog-launchagent.sh` | `scripts/check-watchdog.py`（5 段） |
| laap-brain MCP（cognitive_state/recall_memory/bootstrap/reflect/express） | 上游 `mcp_server/laap_mcp_server.py`，已註冊 `~/.scream-code/mcp.json` | scream E2E（Aris 用 laap_cognitive_state 內省） |
| Scream TUI 狀態列通道 | `laap/tool_executor.py` 寫 `/tmp/laap-tool-status.json`；`scripts/patch-scream-tui.py` v2 | patch 後 `node --check` + scream 0.9.7 實跑 |
| 可觀測儀表 | `laap/status.py` → `status.json`；`scripts/aris-status.py`、`morning-brief.py` | 實跑輸出 |

## 已知限制（誠實標記）

- `laap/agi/{causal,world_model,analogical}` 是 dict-based，非真 AGI —
  策略性維持現狀；psilang_v2 QuantumVM 是 dict/random stub（見
  `docs/specs/quantum-engine-spec.md`：「量子」是高維向量幾何的比喻，
  不是量子計算）。
- LLM 回應與工具選擇由外部 LLM 生成，psi 狀態經 prompt 塑形 — 這是
  prompt 塑形不是認知，被問本質時誠實回答。
- **KNOWN-ISSUE-1**：relatedness 主導時 `_update_attention` 引用不存在的
  `AttentionFocus.SOCIAL` → `process_input` 拋 AttributeError（production
  被 chatflow try/except 吃掉 = psi feed 靜默失效）。已由
  `docs/contracts/psi-backend.md` 契約鎖住現狀，待獨立 PR 修。
- `PsiCore.stop()` 不 join 執行緒；快速 stop→start 可能短暫雙心跳
  （契約 KNOWN-ISSUE-2）。
- affective 的 1/f 噪聲用未播種的 numpy RNG，不可重現 — 跨語言相容測試
  以 noise_amplitude=0 配置進行（見契約〈時鐘與亂數〉）。
- gbrain recall 同步阻塞 ~1s；RPE 品質依賴 embedding（無 key 退化 lex-only）。
- `scream -p` 非互動模式寫入無審批 — agency 若要用 scream 當執行體，
  必須先過 4b 批准閘。
- drive_threshold 固定；多用戶 trust 只有單一 `"user"`。

## 當前優先順序

1. **T4**：Scream 全 TUI 互動驗收矩陣（審批面板/goal/wolfpack/memory/
   knowledge/cc-connect，需人在鍵盤前）。
2. **TASK-001 後續**：Rust PSI M0 — 以 `docs/contracts/` 契約為
   相容基線（先契約後實作，不猜上游私有 Rust binary）。
3. **T5**：scream 上游 PR（狀態列 hook）+ agency→scream 執行體（4b 前提）。

## 驗證

```bash
# 自檢腳本（部分需要 :11546 在線）
PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-<name>.py
```

契約測試 `tests/` 目錄規劃中（見 `docs/contracts/psi-backend.md` §15）。
自動化 pytest 套件與 golden fixtures 為 TASK-001 後續項目。

## 啟動

```bash
~/Developer/neuralis/scripts/start.sh          # 前景，PsiCore 心跳 + API :11546
~/Developer/neuralis/scripts/start-laap-api.sh # 背景（委派 start.sh）
~/Developer/neuralis/scripts/reload-aris.sh    # 開發重載（正規路徑）
```
