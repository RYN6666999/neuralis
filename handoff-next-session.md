# 線頭 — 給下一手

> 最後更新: 2026-07-14 | 最新: 行為豐富度戰略拍板（功能性多巴胺 RPE 優先）+ RLock
> 當前 Phase: 產品向 — 心跳/記憶/自主/睡眠/煞車/對話流/韌性/**7/24** 全上線

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
- ~~PsiCore 心跳未接到 `/v1/chat/completions`~~ → 已解（psi-respond，2026-07-14）：
  回應報實測 delta。剩餘天花板：v0 規則表組句非認知，等接真 LLM
- ~~無記憶固化循環~~ → 已解（Phase 5 ConsolidationLoop）
- ~~Phase 4 安全閘未部署~~ → 4a/4b 已上線；RSI（4c）戰略決定不做

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

## 戰略方向已定：做可用的 agent（產品向，2026-07-14 使用者拍板）
4c RSI / Phase 3 推理層都**不做** — 判斷：RSI 靠假推理驅動是本末倒置，
Phase 3 psilang 是研究向。產品向沿「可見 → 有價值產出 → 韌性」走。

### ✅ 可觀測儀表（commit `dc4eb5a`）
`laap/status.py` StatusWriter 每 30s 寫 status.json；`scripts/aris-status.py` 一頁式儀表
（心跳/自主行動/固化/記憶分層 + 最近動作 + 安全閘 DENY）。`watch -n5 python3 scripts/aris-status.py` 即時盯。

### ✅ agency 意圖品質 v1（commit `6520399`）
種子優先序（真對話 > 記憶聯想 > 不硬查）+ 查詢去重（token Jaccard ≥0.7）+ 聯想鏈
（上次結果摘要當下次種子）。移除固定模板 fallback → 無新鮮種子就閒著（skipped_stale
接進儀表）。徹底砍掉「反覆刷同一模板」的重複垃圾記憶。起點 `laap/agency.py` `_form_intent`。

### ✅ 對話流接上心臟（commit `88a0fee`）
`laap/chatflow.py` monkey-patch aiohttp add_post 包住 `/v1/chat/completions`，請求進入
第一時間餵 psi（作者 handler 前、不阻塞、不管作者管線成敗）。實測 E2E：發 chat →
`psi.last_input` = chat 輸入。agency 現在有真對話種子，聯想鏈不自我循環。
⚠️ 踩到：作者的 chat 管線很重、曾一次 HTTP 000 崩整個 process（無 traceback，疑似卡死/OOM）—
psi 餵食獨立於它是刻意設計。

### ✅ chat 管線凍結 event loop 隱患已修（commit `9b904a3`）
根因：作者 handler 裡 `result = process_with_laap(...)` 同步阻塞跑在 async handler，
慢輸入凍結整個 event loop（連 health 都不回）。修：chatflow 把非 streaming 的
process_with_laap 卸載到 executor + timeout 降級。實測 2 個 1.5s 慢 chat 併發僅 1.51s
（非 3s 序列化）；真 API 3 chat 併發 + health 全 200。⚠️ 那次 HTTP 000 崩潰的確切根因
（OOM vs 假死）未穩定復現；此修解 event loop 阻塞隱患。

### ✅ watchdog 韌性層（2026-07-14）
`scripts/watchdog.sh` — 每 30s 探 `/health`，連續 3 次失敗 → 殺 port listener（含子進程，
gbrain MCP subprocess 會被 reparent 到 init 續佔記憶體）→ 重跑 `start-laap-api.sh`。
1h 內重啟 > 5 次 = crash-loop，停手 exit 1（繼續重啟只會刷 log 蓋掉真因）。
審計 `watchdog-audit.jsonl`，儀表有「重啟 N 次」一行。全 env 可調（見腳本開頭）。

啟動：`nohup scripts/watchdog.sh > watchdog.log 2>&1 &`

- **刻意不用 launchd KeepAlive**：它只在行程「退出」時重啟，抓不到假死（行程活著、
  event loop 凍結、health 不回）。那正是我們觀察到的崩法之一。health 探測兩種都抓。
- **認 port 不認 cmdline**：start.sh 是 heredoc python，cmdline 認不出來 → `lsof -ti tcp:PORT`。
- 實跑證據：`scripts/check-watchdog.py` 4/4（健康不動 / 死了重起 / **假死**重起 /
  crash-loop 停手，用假 server + `NEURALIS_WATCHDOG_START_CMD` 覆寫，不碰線上那隻）；
  真 API E2E：`kill -9` 線上 pid 94266 → watchdog 重啟 → 新 pid 健康 + boot log 有
  心跳 tick / 42 工具 / AgencyLoop / ConsolidationLoop（救回的是完整 Aris，不是空殼 API）。
### ✅ 7/24 自啟動完成（2026-07-14，Ryan 拍板執行）
三層守護鏈上線：**launchd → watchdog → 完整 Aris**。
- `scripts/install-watchdog-launchagent.sh`：生成 + 安裝 `com.neuralis.watchdog`
  LaunchAgent（RunAtLoad + KeepAlive），已在本機安裝運行。
- 煞車跨行程持久：crash-loop 落地 `watchdog-crashloop-<PORT>.lock`，launchd 重啟
  watchdog 會先睡完冷卻期（1h）才恢復 — KeepAlive 不會繞過煞車、不會無限刷。
- env 關鍵：plist 用 `zsh -c 'source ~/.zshrc'`（key 在 zshrc L114）。漏了的話
  重啟的 Aris silent 退化 lex-only。已用 psutil 驗過復活行程 env 帶 key + .bun PATH。
- 實跑證據：check-watchdog 5/5（新增 E 段煞車持久）；真三殺 E2E — kill -9 watchdog
  → launchd 3s 拉回（16554→16684）；kill -9 API → 95s 救回（14153→16928），boot log
  心跳+42工具+Agency+Consolidation 全在。
- ⚠️ 內省陷阱（learn）：macOS `ps eww` 不顯示 env、psutil environ() 對部分行程回空
  （KERN_PROCARGS2 截斷）— 驗 env 要看「child 行程實際拿到什麼」，別信 parent 讀數。

### ✅ scream AI 舊世界誤報處理（2026-07-14）
scream 產出的 `~/laap-AGI/debug-handoff-prompt.md` 基於過時布局（port 11530、無
overlay），5 個 defect 在真系統全部已解。已改寫該檔為指路牌（逐條實證對照 + 指向
`~/Developer/neuralis`），防止下一個 debug AI 掉進幻影 bug 地獄。

### 🧹 已清理
`~/neuralis` 舊 checkout → `~/.Trash/neuralis-old-checkout-20260714`（Ryan 確認後執行）。
獨有內容已救回：`docs/research/what-lives-brainstorm.md`（六帽分析）。staged 的
tick_callbacks 方案判定為 Phase 5 廢案（Developer 版用 ConsolidationLoop 實作），未救。

### ✅ 情緒真的影響回應了（2026-07-14）— 舊限制「需求不影響回應」已解
改動只在 `laap/chatflow.py`（+新自檢），兩個縫一次縫上：
1. **圓作者的檔案契約**：作者整個 aris_brain 都讀 `state/latest.json`（Rust psi core
   本該每 100ms 寫，但 Rust 版缺失 → 檔案從未存在 → process_with_laap Step 3 的
   psi_context 永遠空、fallback 回應結尾才會是懸空的「through .」）。現在 chatflow
   在每次 chat 餵 psi 後寫入（chat 時間點最新鮮），schema 取讀端聯集。
2. **psi-respond**：作者管線落到 canned fallback 時，改用真實狀態組回應 —
   `_feed` 現在量測「這句話造成的實際 delta」（餵前後 state diff），回應報出
   實測數字：「你這句話碰到了我 — relatedness +0.14…現在主導我的是 competence…」。
   每個數字可回溯，不演。`NEURALIS_PSI_RESPOND=off` 可關。
   ponytail 註記：v0 規則表組句不是認知；升級路徑 = LAAP 管線接上真 LLM 後，
   把 st/delta 塞 system prompt 走 LLM。
- 實跑：`scripts/check-psi-response.py` 5 段全過 — E2E 情感句 relatedness +0.14 vs
  中性句 +0.02，回應內容隨狀態不同；作者契約檔 cycle 隨 chat 遞增（7→49）。
  check-chatflow 回歸過（feed/executor 卸載/逾時降級）。
3. **psi_response.py**（新增）— 英文狀態感知回應模組，`generate_response()` 作為
   `_compose_psi_reply` 降級選項（中文模板失敗時自動接英文通用模板）。
4. **RLock 執行緒安全**（psi_core.py）— NeedDriveSystem 和 EmotionGradient 所有
   公開方法加 `threading.RLock`，防止心跳 tick() 與 process_input() 並行資料競爭。
5. **format_state_injection()**（psi_core.py）— 狀態序列化為三層輸出
   （state_label / state_snippet / state_tuple），供外部消費。

## 戰略拍板：行為豐富度路線（2026-07-14 Ryan 與 Opus 4.8 討論定案）

**核心判準：一個狀態變數的價值 = 它會不會「改變系統的計算方式」，不是它會不會
被報告出來。** 加五種神經傳導物質當純浮點數 + 句子裡多報幾個數字 = 裝飾性 cosplay，
幾天就被看穿是模板 — 這條**禁止走**。功能性版本才做（生物神經調節物質的本職是
全局參數控制器：改學習率、探索溫度、時間視野）。

湧現的誠實定位：認知湧現只發生在租來的 LLM 權重裡，overlay 層能做到的是**行為
湧現** — 條件三個：簡單規則 ✅、閉環迴路 ✅、後果塑形 ❌（Aris 做任何事都不改變
自己未來的傾向 — 沒有 stakes 就沒有養成）。補第三個 = 下面的第一優先。

### ✅ 功能性多巴胺（RPE）已實作（2026-07-14）— 靜態規則表變會學的 bandit
改動只在 `laap/agency.py`（+自檢+儀表）：
1. **_score_result(result) → 0-1**：拆 gbrain 結果的分數線 hit 數 + 平均分數 +
   內容長度三個訊號。無結果 = 0，高品質 = ~0.9。
2. **RPE = outcome - expected**：每行動後量結果品質 vs EMA 預期值（α=0.1），
   誤差 = 功能性多巴胺訊號。存入 `_need_stats[need]` 的 rpes buffer。
3. **角度權重更新**：正 RPE → 該查詢角度權重升（×0.5）；負 RPE → 降。
   權重 clamp 0.1-3.0。`_form_intent` 依權重 epsilon-greedy 選角度。
4. **探索率自適應**：滑動 20 窗 RPE 均值 > 0.05 → 探索率升 0.005（上限 0.30）；
   < -0.05 → 降 0.005（下限 0.05）。
5. **儀表：`aris-status.py`** 顯示 RPE avg + exploration rate。
   **審計：`agency-audit.jsonl`** 每行含 outcome/expected/rpe/exploration，
   可回溯每步的學習訊號。
6. **自檢：`scripts/check-dopamine.py`** — 4 段全過。
ponytail：簡化 bandit（epsilon-greedy + EMA），不是 Thompson sampling。
天花板：結果品質只量分數線，不考慮語義。升級路徑 = semantic score。

### ✅ LLM 進 psi-respond（2026-07-14）— 聊天感覺活了
`format_state_injection()` 已備好（57eb976），新增 `laap/llm_respond.py`：
1. **system prompt 自動生成**：`_build_system_prompt()` 將 PsiCore 的
   dominant_need/valence/arousal/attention 映射為自然語言描述，注入 LLM 的
   system message。Aris 的「感受」真實影響 LLM 的語氣和內容。
2. **OpenAI-compatible**：支援任何 OpenAI API（預設 gpt-4o-mini），API key
   從 macOS Keychain 讀取（與 zshrc 同一來源），不 hardcode、不寫入檔案。
3. **三層降級**：LLM 失敗 → `_compose_psi_reply` 中文模板 → `psi_response.py` 英文模板。
   任何異常不退化成空白回應。
4. **開關**：`NEURALIS_LLM_RESPOND=on` 啟用（預設 off），
   `NEURALIS_LLM_MODEL`（預設 gpt-4o-mini）、`NEURALIS_LLM_BASE_URL` 可自訂。
5. **engine 標籤**：LLM 模式回應標 `psi-llm`，儀表可直接區分。
ponytail：這是 prompt 塑形不是認知。升級路徑 = Aris 自己的對話管線接上 LLM 後，
這層自然消失（被原生管線取代）。

### 下一線頭（依優先序，已完成=RPE+LLM）
1. **功能性多巴胺（RPE）— 單點投報率最高**：agency 行動後量「結果 vs 預期」
   （檢索命中率、寫回的記憶是否被後續 recall 用到）→ 誤差回頭調規則表權重 +
   drive 閾值/探索率。靜態規則表變會學的系統（bandit，誠實不裝認知）。
   起點：`laap/agency.py` 的 `_form_intent` + 行動結果處。
   **反悔條件**：上線數週後儀表行為指標（行動多樣性/種子新穎度）無可測漂移 →
   overlay 學習路線判死，人格投資全轉「記憶 + LLM prompt 塑形」。
2. **LLM 進 psi-respond（體感最快）**：`format_state_injection()` 已備好（57eb976），
   把 state/delta 塞 system prompt 走真 LLM。它讓聊天「感覺活」，但不產生養成。
3. **催產素 = 對人信任權重**：per-entity trust 進記憶 frontmatter，熟人 relatedness
   增益更大。腎上腺素 = 高 arousal 縮 agency interval/收窄注意力。血清素 = decay
   速率與 valence 基線。內啡肽 = 負 valence 尖峰緩釋。每個都必須接到真實計算參數。
4. **有價值產出**：跑整晚留什麼給 Ryan 早上看（morning brief / 記憶整理報告）
- 次要：psi-respond 織入記憶聯想（recall ~1s 阻塞要走 executor）；consolidation
  跨 pass 去重；agency↔gbrain injection 防護
- 不做：裝飾性神經傳導物質、4c RSI、Phase 3 psilang（戰略已定）

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