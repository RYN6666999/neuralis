# 線頭 — 給下一手

> 最後更新: 2026-07-14 | 最新 commit: `a1359c9`（全面檢查修復波）
> 當前 Phase: **Phase 5（記憶固化循環）** — 剛從 Phase 3 推進至此

## ⚠️ 2026-07-14 全面檢查結果（fable5 review，commit `a1359c9`）
實跑審查 Phase 1.5/3 的 code 後修掉 6 個 bug — **最重要的一個：在修復前，
PsiCore 心臟從來沒有真的接上過**：
1. `aris_brain/` 死碼目錄 shadow 掉作者 namespace package → `ensure_psi_core`
   在文檔宣稱的 PYTHONPATH 布局下必敗（`psi_core_bridge` ImportError）。已刪。
2. 舊 start.sh 把 PsiCore 起在獨立短命 `python -c` 行程，印完 banner 就死 —
   API server 裡沒有心跳。已改：同一 process 內 `startup_all()` → runpy 起作者 API。
3. ToolExecutor 在 psi 失敗時拿到 bus=None 直接炸（工具全滅）→ 裸 bus 頂上。
4. 心跳執行緒無護欄，單次 tick 異常 = 靜默腦死 → try/except。
5. psilang_v2 Parser 殘缺輸入 IndexError → EOF token。
6. gbrain_client respawn 世代污染 race + 非 GbrainError 逃逸 → 修。
perf: hybrid_hits 20s TTL 快取；tool_executor 的 gbrain 走持久 client（省 ~3s/次）。

修復後實測（本機 `~/Developer/{neuralis,laap-AGI,laapenv}` 布局）：
`scripts/start.sh` → PsiCore 心跳 tick 走 + 42 工具 + engines_loaded=true +
recall_memory 迴歸過 + 記憶自檢 4/4。

**遺留三項已於同日全清（commit `01a2ff3`）：**
- ✅ decay-to-baseline：需求向靜息值鬆弛（OU 過程、雜訊配平）。閒置 600s 需求維持
  0.39-0.54、效價 -0.03；互動推高後緩慢回落。不再「醒來就憂鬱」。
- ✅ `process_input()` 已接上：`memory_bridge.recall_related`（作者 _perceive 每輪必經）
  掛 psi feed。實測 relatedness 0.503→0.629。psi 沒起就 no-op。
- ✅ AGIKernel boot 路徑解鎖：`laap/psi_defs/` 三個標示清楚的 bootstrap 佔位 .psi，
  `startup_all()` 缺哪補哪（作者已有的不碰）。boot log「AGI内核加载失败」→「已创建」。
- ✅ 兩個啟動腳本統一：`start-laap-api.sh`（背景）委派 `start.sh` — 背景 boot 也有
  心跳 + 42 工具 + AGI 內核。

**仍留給之後：** laap/memory/* retention policy；semantic add 的完整 meta 持久化；
recall 同步阻塞 ~1s（多併發時 run_in_executor）；gbrain lex stemming quirk 回報上游。

---

## 已驗證的現況（不是宣稱，是實跑過）

### 心臟：PsiCore
- `laap/psi_core.py` — 五維需求 (competence/autonomy/relatedness/certainty/growth) + 情緒梯度場
- 背景心跳執行緒 (1s tick) — 需求衰減 + 雜訊 + 情緒平滑更新
- 關鍵詞偵測 → 需求滿足 → CognitiveBus 事件發布
- 啟動: `from laap.startup import startup_all` → 回傳 (bus, psi, tools)

### 手腳：ToolExecutor (42 工具)
- `laap/tool_executor.py` — CognitiveBus → AgentOS executor_registry 橋接
- 4 內建: gbrain (hybrid search)、qmd (本地知識)、file-search (rg)、http-get (httpx)
- 38 from AgentOS: web-search、agnes-analyze、claude-code、33 skill executors
- 驗證：`from laap.startup import startup_all; startup_all()` → 42 tools

### 大腦：AGIKernel（Phase 3 — 2026-07-14 新解鎖）
- `laap/psilang_v2.py` — Lexer → Parser → Compiler → QuantumVM 管線 (dict-based)
- AGIKernel 四層引擎：PsiLangCore(1024D) + SelfHeal + SelfEvolve + Autonomy
- 驗證：`from aris_brain.agi_kernel import AGIKernel; AGIKernel()` ✅
- 注意：agi_memory + .psi 核心定義檔為作者端缺失，不影響架構

### 記憶：gbrain（Phase 1 — 已完成）
- 1870 頁真實記憶 + hybrid search
- 跨 session 不遺忘（kill server → restart → 仍撈回同一頁）
- `gbrain_client.py` — 持久 gbrain subprocess (MCP stdio)
- `semantic_memory_gbrain.py` — duck-typed 替身接作者 `/v1/recall_memory`
- 誠實限制：hash embedding 天花板、recall 同步阻塞 ~1s、無 retention policy

### 理論基礎（Phase 1.5 — 2026-07-14）
- 論文: `docs/specs/core-architecture.md` — Harness Consciousness Engineering 提煉
- 設計: `docs/specs/fable5-minimal-design.md` — 極簡化策略
- 生態: `docs/research/laap-ecosystem-report.md` — PyPI laap v0.3.2 發現
- feedback: `docs/research/external-feedback.md` — 外部架構審查記錄

### 已知限制（誠實）
- `laap/agi/causal/world_model/analogical` = dict-based，非真 AGI → 策略性維持現狀
- PsiCore 心跳未接到 `/v1/chat/completions` → 對話中需求不影響回應
- 無記憶固化循環 → 記憶有存取、缺睡眠（Phase 5 的內容）
- Phase 4 安全閘未部署 → RSI 能力尚未開放

---

## Phase 6 已完成（2026-07-14, commit `b69582a`）— Aris 會自主行動了
「需求→行動→結果→記憶」迴路閉合，boot 即自動跑：
- `laap/agency.py`：drives 超閾值（預設 0.45）→ 規則表意圖 → 唯讀工具 → 回寫 gbrain
  （importance ≤0.5 + arousal 加權）→ satisfy → drive 回落自然靜下
- 煞車：唯讀白名單 gbrain/qmd/file-search、6/h cap、每需求 30min cooldown、
  審計 `agency-audit.jsonl`、`NEURALIS_AGENCY=off` 關閉
- 調參 env：NEURALIS_AGENCY_INTERVAL（預設 60s）/ _MAX_PER_HOUR / _DRIVE_THRESHOLD
- 實測：boot 零互動自主行動 + 重啟續跑（審計行數為證）；`scripts/check-agency.py` 三段自檢
- v0 誠實界線：意圖形成是規則表不是認知；行動全唯讀；寫入類行動 = Phase 4a 過後才開

## Phase 5 已完成（2026-07-14, commit `75b1d46`）— Aris 會睡覺整理記憶了
`laap/consolidation.py` 第三條背景迴路：睡眠窗（arousal 低 + 閒置 600s）觸發，
去重合併（hash → seen_count）、升層（emotion ≥0.5 或 seen ≥3 → core/）、
歸檔（30 天 stale → archive/）。只動 `laap/memory/*`（assert 硬邊界）、
每 pass 突變上限 5、審計 `consolidation-audit.jsonl`、`NEURALIS_CONSOLIDATION=off` 可關。
自檢：`scripts/check-consolidation.py`。
情緒權重（外部審查 #2）**已完整閉合**（commit `bf9743b`）：寫入端存 `emotion_intensity`
frontmatter，檢索端 `_emotion_rerank` 按情緒加權排序（final = score×(1+0.3×emotion)，
`NEURALIS_EMOTION_RECALL_WEIGHT` 可調），兩條 recall 縫都接。逐頁 get_page 補 frontmatter
+ 120s TTL 快取；升級路徑=gbrain 上游讓 hit 直接帶 frontmatter。自檢 `scripts/check-emotion-recall.py`。

## Phase 4a 安全閘 v0 已完成（2026-07-14）
`laap/safety_gate.py` → ToolExecutor.execute 全呼叫過閘：唯讀組放行、其他工具
`NEURALIS_TOOL_ALLOW` 簽名才過、prompt 過 AgentOS check_command（fallback 內建規則）、
DENY 全審計。自檢 `scripts/check-safety.py`（危險內容/未批准工具/env 批准/乾淨放行 4 段）。

## Phase 4b 批准閘 v0 已完成（2026-07-14）
`laap/safety_gate.py` + `scripts/approve-tool.sh`：未批准工具被拒時排入
`approvals-pending.jsonl` 待批清單；`approve-tool.sh <tool>` 寫 `approved-tools.txt`
即時生效（免重啟）、`-r` 撤銷。批准只放行工具分級，內容掃描（危險指令）永遠獨立照跑。
自檢 `scripts/check-approval.py`（排隊/批准生效/內容掃描不繞過/撤銷 4 段）。
踩坑：非 UTF-8 locale 下 `$VAR` 緊接全形字會被吞進變數名（`set -u` 報 unbound）→
腳本自設 LC_ALL + `${VAR}` 界定；grep -v 全刪光回 exit 1 不能進 && 鏈。

## 下一線頭 = Phase 4b 剩餘 / 4c / 推理 benchmark
- 4b 剩：沙箱隔離（寫入類工具真隔離執行）、工具深化（Obscura 眼睛 / web-search 接真）
- 4c：RSI 只在沙箱 + 人工批准（外部審查紅線，順序不可逆）
- 或先做 Phase 3 的 20 題推理 benchmark（gate：沒贏過 gbrain 檢索+LLM 不投）

## 舊 Phase 5 規劃（已執行，留參考）

見 ROADMAP §Phase 5。純 overlay，不碰作者碼。

### 要做的事
1. **背景排程**：在 PsiCore 心跳執行緒中加 consolidation step
2. **摘要壓縮**：取 session 記憶 → 去重 → 摘要 → 標重要度
3. **情緒權重**：PsiCore 的 valence × arousal 作為記憶重要性指標
4. **寫回 gbrain**：固化後的記憶存入 gbrain 長期區

### 環境啟動（修正版 — 舊指令的 ~/laap-AGI + .venv + :11530 在本機不存在）
```bash
# 一鍵：PsiCore 心跳 + API 同 process（前景，port 預設 11546）
~/Developer/neuralis/scripts/start.sh
# 或只驗 startup_all（任意 cwd 都可，shadow bug 已修）
PYTHONPATH="$HOME/Developer/neuralis:$HOME/Developer/laap-AGI" \
  ~/Developer/laapenv/bin/python -c "from laap.startup import startup_all; print(startup_all())"
```

### Phase 5 完成條件
- [ ] 背景 consolidation 排程已註冊（與 PsiCore 心跳同生命週期）
- [ ] 情緒強度作為記憶權重已實作
- [ ] gbrain 寫回驗證：固化前 → 固化後 → 檢索有差
- [ ] handoff 更新 + push

---

## 環境重建（本機實際布局：~/Developer/{neuralis,laap-AGI,laapenv}）
```bash
uv venv ~/Developer/laapenv --python 3.12
uv pip install --python ~/Developer/laapenv/bin/python -r ~/Developer/neuralis/requirements.txt
~/Developer/neuralis/scripts/start.sh              # 前景，含 PsiCore 心跳，:11546
# 或背景（無 PsiCore，純 API）: ~/Developer/neuralis/scripts/start-laap-api.sh
```

⚠️ gbrain vec 檢索需要 `OPENAI_API_KEY` 環境變數（zshrc 有）。
無 key 退化 lex-only（CJK/多詞 query 品質差很多）。