# neuralis 開發 Roadmap

三層架構：**LAAP（心 / 情緒·欲望·目標）· gbrain（記憶 / pgvector）· AgentOS（執行腦 + 煞車）**。
neuralis 是疊在 `lorryjovens-hub/laap-AGI` 之上的 overlay。

## 誠實定位
目前 Aris 有動態需求（PsiCore 心跳）、真實記憶（gbrain 1870 頁）、AGI 四層引擎（AGIKernel）、42 工具（ToolExecutor）。推理引擎是 dict-based（非真 AGI），但這不是我們的核心競爭力——記憶才是。

---

## Phase 0 — 底座校正 ✅
- laap-AGI overlay 缺陷修復
- scream-code MCP 整合打通
- 量子引擎規格文件

## Phase 1 — gbrain 記憶後端 ✅
- 1870 頁真實記憶 + 語意檢索
- 持久化跨 session 不遺忘
- `/v1/recall_memory` 接作者系統

## Phase 1.5 — fable5 研究 + 極簡化 ✅
- 生態系研究: PyPI laap v0.3.2 發現
- 理論基礎溯源: Dörner PSI / Darwin-Gödel / Prigogine
- PSI Core 實作 (純 Python, 無外部依賴)
- AGI 引擎 stub → dict-based 升級
- 80/20 槓桿: ToolExecutor + AgentOS 整合 (42 工具)

## Phase 2 — PSI Core 深度化 ✅
Python 版 PsiCore 已運作，五維需求 + 情緒梯度 + 背景心跳。

## Phase 3 — psilang_v2 + AGIKernel ✅
- 補作者缺的 `psilang_v2` Lexer/Parser/Compiler/QuantumVM 管線
- 解鎖 AGIKernel 四層引擎：PsiLangCore + SelfHeal + SelfEvolve + Autonomy

## Phase 6 — Agency Loop v0 ✅（commit `b69582a`, 2026-07-14）
> 「需求 → 行動 → 結果 → 記憶」迴路閉合。零件（心跳/記憶/工具）接成會自己跑的整體。

- `laap/agency.py`：drives 超閾值 → 規則表形成意圖（v0 誠實標註：不是認知）→
  唯讀工具執行 → 結果回寫 gbrain（importance ≤0.5 + 情緒加權）→ satisfy 需求
- 煞車先行：唯讀白名單、6/h cap、每需求 30min cooldown、審計 JSONL、
  `NEURALIS_AGENCY=off` 總開關
- 實測：boot 後零互動自主行動 + 回寫 + 審計；kill 重啟迴路續跑；
  `scripts/check-agency.py` 三段自檢

## Phase 5 — 記憶固化循環 ✅（commit `75b1d46`, 2026-07-14）
> 記憶有存取、缺睡眠 → 補上了。零 LLM。

- `laap/consolidation.py`：睡眠窗（arousal 低 + 閒置）觸發 — 去重合併（hash）、
  升層（emotion ≥0.5 或 seen ≥3 → core/）、歸檔（30 天 stale → archive/）
- 情緒權重：寫入端 `emotion_intensity = |valence|×arousal` 進 frontmatter（兩縫都補）；
  檢索端 re-rank 留 ponytail 註記（hit 不帶 frontmatter）
- 安全硬邊界：只動 `laap/memory/*`、每 pass 突變上限 5、審計 JSONL、可一鍵關
- 實測：3 重複 → 1 頁 core/（seen_count=3）；高情緒升層；三迴路同框 boot

## Phase 4 — AgentOS 執行/安全層（⚠️ 順序：煞車先於能力）
**重要：此階段的執行順序不可逆。**

### Phase 4a — 安全閘 (Safeguard) ✅ v0（2026-07-14）
`laap/safety_gate.py` 接進 ToolExecutor.execute — 所有工具呼叫先過閘：
- 工具分級：唯讀組直接過；其他預設拒絕，`NEURALIS_TOOL_ALLOW` 明確簽名才放
  （v0 人工批准 = env 簽名；互動式批准留 4b）
- 內容掃描：AgentOS `orchestrator/safety.py` check_command（rm -rf / DROP TABLE /
  restricted paths），載不到用內建縮小版
- DENY 全審計（safety-audit.jsonl）；自檢 `scripts/check-safety.py` 四段
- 未做（升級路徑）：沙箱隔離、互動式批准閘門 — 開放寫入類工具前必補

### Phase 4b — 批准閘 + 工具深度整合（🔄 進行中）
- ✅ 檔案式人工批准閘（`approve-tool.sh` + `approved-tools.txt` 待批清單，免重啟生效）
- 未做：沙箱隔離、接 Obscura 瀏覽器眼睛、接 Web 搜尋、PyPI laap 21 工具層

### Phase 4c — RSI 自我改進 🥉
- RSIEngine maker/checker/repair 只在沙箱內執行
- 每次改進提案需通過安全審查
- 最低權限原則：只改自己的 overlay 程式碼

---

## 依賴序
```
Phase 0 ✅ → Phase 1 ✅ → Phase 1.5 ✅ → Phase 2 ✅ → Phase 3 ✅ → Phase 6 ✅ → Phase 5 ✅
                                                     ↓
                                              Phase 4a (安全閘) ← 現在這裡
                                              （迴路開放寫入類行動前的硬前提）→ 4b → 4c
```

推理層警語：Phase 3 的 QuantumVM 是 dict/random stub — 擴大投入前先建 20 題
benchmark（類比/組合/檢索），沒贏過「gbrain 檢索 + LLM」就不投。