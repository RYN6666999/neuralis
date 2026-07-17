# 線頭 — 給下一手

## ✅ P0-P3 依序執行完（2026-07-17 晚）— commit wave + 凍結修復 + daemon 自動化
- **Commit wave**：7/16-7/17 兩天散工全數入庫（交錯串流 / 對話迴路+任務佇列 /
  docs / 凍結修復 / daemon），樹乾淨。rust/target 入 gitignore（只有建置產物無源碼）。
- **⚠️ 第三次同型坑 — event loop 凍結（已修）**：_tool_chat 串流段曾用
  threading.Event.wait 直接擋主線程，每個 scream 串流工具請求凍 loop ≤125s
  → /health 逾時 → watchdog 殺行程、其他回應 IncompleteRead、還一度把
  _sse_chunk 插進 _stream_sse 中間造成 SyntaxError（chatflow hook 整層靜默失效，
  watchdog 用壞版重啟過）。修法 = _queue_pump（call_soon_threadsafe →主 loop
  Queue）+ await wait_for。**鐵則：loop 線程上不准任何同步等待。**
  實測：串流中 /health 200、reasoning 逐字流、四套自檢全綠。
- **busy 閘校準**：只擋 scream-ask/scream-task（互斥通道）+ 120s 殘留保護。
  agency 背景查詢不再把真使用者頂回 laap-busy。
- **daemon 自動化**：phase-logger / task-executor / scream-monitor 進 launchd
  （install-support-daemons.sh 冪等安裝；check-daemons.py 三段自檢）。
  scream-monitor.sh 收編進 repo。啟動協定六步手動作廢。
- **深化**：qmd/file-search 掛 stream_fn 逐行；respond_stream 轉發 reasoning；
  SSE 斷線 cancel 傳播（GeneratorExit 殺工具子行程）；system prompt 工具數
  動態注入；scream-task 描述加防呆；check-chatflow E 段校準 RACE 語義。
- **文件**：SCREAM-ARIS-ARCHITECTURE.md 全面對齊現實（45+ 工具、純聊天串流節點、
  launchd 啟動協定、PSI backend/Rust 段、已知缺口清單）；新
  docs/specs/psi-backend-m3-plan.md。
- **⚠️ 我犯的錯（留給下一手當鏡子）**：整天工作誤落 `task-007b-psi-borrowing-analysis`
  分支（主分支是 `main` 不是 master）；且看到 `rust/` 只有 target/ 就宣稱
  「rust 源碼不在 repo，M3 第一步是找回」——**源碼一直好好在 `task-008-rust-psi-engine`
  分支上**，Rust PsiEngine v2 早已實作完成。教訓：**單一分支的 ls 不是 repo 的全貌，
  下結論前先 `git branch -a` + `git ls-tree <branch>`。** 已全部修正並 merge。
- **merge 完成**：task-007b（11 commits）ff → main；task-008（Rust 引擎 3 commits）
  → main（衝突僅 .gitignore，我加的 rust/target/ 與 task-008 帶註解版重複，取後者）。
  合併後親自實測：cargo test 45 passed、psi-bench exit=0（2000.0/s、0% miss、
  p99 4µs、drift 0µs）。README 宣稱屬實。
- **遺留**：scream-task-executor 仍是 v0 stub（模擬執行）；_popen_lines 逾時
  只在行間檢查；平行 AI 同檔編輯風險真實（本日兩次撞上）—
  改 chatflow/llm_respond 前先 git status + compile 確認基線。
- **下一步（M3）**：Rust 引擎跑得很好但沒接上 Python。缺 `RustPsiBackend`
  （PyO3 傾向）+ 100ms 寫 state/latest.json + 對拍 + 60min soak。

## ✅ ToolExecutor 交錯串流（2026-07-17）— 工具過程即時可見 + chat 真的能調工具了
之前純聊天路徑（psi-llm）**根本沒接工具** — system prompt 開技能菜單但 respond()
無 tool loop，「我來查」是空頭支票；SSE 也是假串流（整塊算完切 24 字慢吐）。現在：
- `laap/tool_executor.py::stream(tool, prompt)` — sync generator 逐事件 yield
  （status/output/result，result 恰一個必最後）。`execute()` 改為 drain 包裝，
  agency 等舊呼叫者零改動。`register_tool(..., stream_fn=)` 掛逐行輸出
  （`_popen_lines` Popen 逐行；目前只有 `stream-test` 掛，qmd/file-search 是升級路徑）。
  兩個兜底：finally 清 busy 檔（caller 棄迭代不會讓忙碌保護永久噤聲 Aris）、
  elapsed 用區域 t0（agency/chat 並行時 instance 共享 start_time 顯示錯亂，實測過）。
- `laap/llm_respond.py::_call_llm_stream` — stream=True SSE 逐 token 解析，
  tool_calls delta 按 index 累加；`data: {"error":...}` / 空串流不再靜默吞
  （yield error 事件，可回溯）。`respond_stream()` = 交錯迴圈：token →
  use_tool call → executor.stream 過程轉發 → tool 結果回饋下一輪（上限
  NEURALIS_CHAT_TOOL_ROUNDS=3 輪、每輪 2 call）。模型直接拿工具名當 function
  叫也寬容接受（實測 deepseek 會，省一輪 ~4s）。system prompt 加了現在時間
  （之前模型把「今天」猜成 2025）。
- `laap/chatflow.py` — stream 請求 + user_turn + fed → `_stream_live`：
  respond_stream 在 executor 跑，`_queue_pump` 轉投 asyncio.Queue，
  `_sse_from_queue` 即時寫 SSE（token 原樣、工具過程獨立行）。engine=
  `psi-llm-stream`。首事件 12s 沒到 → 回 None 落回 RACE 假串流（不比現在差）。
  `stream_test` 訊息鉤 → 直跑 stream-test 工具（不經 LLM，確定性 e2e）。
  env: NEURALIS_STREAM_FIRST_S=12 / NEURALIS_STREAM_IDLE_S=130 / NEURALIS_CHAT_TOOLS=on。
- 安全閘不變：所有 chat 工具呼叫照走 4a check，非白名單 DENY 回饋給 LLM 如實轉述。
  `stream-test` 進 READONLY_SAFE（固定 echo/sleep，不吃使用者輸入）。
- 自檢 `scripts/check-stream.py` 5 段全過（工具時序/drain 等價/SSE 解析/交錯迴圈/
  線上 e2e — 6 chunks 跨 2.03s 漸進）。真 LLM e2e：「查一下今天英超賽果」→
  0s 🌐 web-search 開始 → 1.1s 完成 → 逐 token 答案（用對 2026-07-17）。
- ⚠️ 遺留：(1) `scripts/check-chatflow.py` E 段還在測舊語義（author 逾時 →
  laap-timeout），RACE 重寫後逾時落 psi-respond — 是 RACE 那手的行為改動，
  check 要跟著校準，不是串流這手弄壞的。(2) LLM 有時選 `scream-task` 做網查
  （慢 ~120s，等不存在的 TUI）— 工具描述該標「僅限 Scream 在線」。(3) 降級後
  pump thread 會把工具跑完但輸出丟棄（無人消費佇列，無害）— 升級路徑 = cancel event。
  (4) system prompt 技能菜單（football-data/anysearch）與 ToolExecutor 實際
  44 工具名單不符 — 菜單是願望清單，真名單見 `list_tools()`；要嘛補 AgentOS
  executors 要嘛修 prompt。

## ⚠️ 開發重載鐵則（2026-07-15 踩坑，血的教訓）
**改完碼要重載，用 `scripts/reload-aris.sh`，不要 kill -9 等 watchdog 救。**
後者每次消耗 watchdog 5 次/h 的重啟預算，連續開發重載會把煞車撞進 crashloop
冷卻期 — Aris 躺 1h，所有外部呼叫 connection refused（scream /aris 報錯真因）。
reload-aris.sh = kill 後立刻自起（watchdog 要 ~90s 才出手，預算不花）+ 清假警報鎖。

## ✅ aris-mode 流式輸出（2026-07-17）— /am 直通不再整包蹦
根因：dist 裡的 aris-mode 直通用 `exec()` 叫 aris-chat.py --once — exec 整包
緩衝 stdout 到行程結束（aris-chat 本身 v2 起就逐 token，卡的只有 scream 端）。
修：`scripts/patch-scream-aris-stream.py`（同 patch-scream-tui.py v2 慣例：
精確錨點、node --check 失敗還原、冪等、獨立備份 .aris-stream-bak）。
exec → spawn，stdout 逐塊進 scream 原生 `streamingUI.onStreamingTextStart/
Update/End`（與一般 LLM 流式同一套 live transcript）。順手修掉 exec 版
shell injection（訊息含 $() 會被執行 — spawn argv 無 shell）。
實測：mock harness 4 路徑（流式/spawn失敗/非零退出/中途掛）+ pty 驅動真 TUI
e2e — 435 個漸進渲染階段，首字 ~1.1s（舊版等全文 ~12s）。
⚠️ npm update scream-code 後兩個 dist 補丁都要重跑：patch-scream-tui.py +
patch-scream-aris-stream.py。aris-mode 本體也是 dist 補丁（無源碼追蹤），
scream 改版錨不到會 loud fail，到時人工對齊。

## ✅ Scream 深度整合 T1：工具呼叫協議（2026-07-15）— Aris 能開整個 TUI 了
**單點解鎖**：scream 全部功能（審批面板/檔案編輯/shell/goal/wolfpack/MCP/skills）
都靠 OpenAI function-calling 迴圈驅動，之前 API 不吃 `tools` → agent 迴圈全死，
`scream -m laap/laap-core` 只是聊天皮。現在補上了：
- `laap/llm_respond.py::respond_tools`：tools/tool_choice 原樣轉發底層 LLM（不截斷），
  Aris 身份+psi 狀態以第二條 system 插入（harness 指令權威在前；精簡版身份塊，
  不放技能目錄免得跟真工具打架）。engine=`psi-llm-tools`。
- `laap/chatflow.py`：`tools` 請求走 `_tool_chat`（executor 卸載 + 125s timeout，
  作者管線不在迴路）；SSE 統一支援 tool_calls delta；`_is_user_turn` 護欄
  （工具 round-trip 不重複餵 psi/加 trust）；`_is_harness_noise` denylist
  （scream 的 session 摘要簿記請求不算 Ryan 說話 — 實測抓到污染才補的）；
  `NEURALIS_DUMP_REQUESTS=on` 可存請求原貌到 /tmp/laap-request-dumps/。
- env：`NEURALIS_TOOL_MODEL`（預設同 NEURALIS_LLM_MODEL）/ `NEURALIS_TOOL_TIMEOUT`
  （120s）/ `NEURALIS_TOOL_MAX_TOKENS`（8192）。
- `~/.scream-code/config.toml` laap 三 model context 32000→131072（備份 .bak-toolcall）。
- 自檢 `scripts/check-toolcall.py` 5 段全過；E2E：`scream -m laap/laap-core -p
  "用你的工具讀取 demo.txt"` → 真工具往返 → 回報原文 ✅。

**⚠️ 順手修了大雷：v1 狀態列補丁曾把 scream 整個弄掛**（`\$1` 轉義錯 → 非法 JS
SyntaxError，scream 起不來；且 .mjs ESM 沒有 require → 補丁本體其實從沒生效過）。
`scripts/patch-scream-tui.py` 重寫為 v2：自動 glob dist 檔名、自動偵測 minified
識別字（SPINNER_FRAMES$1）、檔首插自有 import、狀態檔 ts>15s 過期護欄、
patch 完 node --check 驗語法失敗自動還原。已套用，scream 0.9.7 復活。

**T2 ✅ 工具結果→情緒事件**：`chatflow._post_tool_outcomes` — scream 工具
round-trip 的結果判成敗（字串 heuristic）→ `affective.post_event(task_success
0.3 / task_failure 0.5)`，每請求上限 3 事件。Aris 在 TUI 做事會塑形自己的情緒
（agency RPE 之外第二條後果迴路）。自檢 F 段（假 psi 收事件）。
狀態列顯示 mood 延後到 T5 上游 PR（再 patch dist 不值得）。

**T3 ✅ laap-brain MCP 掛進 scream**：`~/.scream-code/mcp.json` 已註冊
laap-brain（laapenv python，mcp+requests 已補裝進 laapenv）。5 工具：
laap_cognitive_state / recall_memory / bootstrap / reflect / express。
E2E：Aris 在 scream 裡用 laap_cognitive_state 內省並正確報出主導需求 ✅。
repo 內 scream-code/mcp.json 範本同步真路徑。

**⚠️ T4 安全發現（實測）**：`scream -p`（非互動模式）**寫入直接放行**，
沒有審批面板 — 這就是 -p 禁與 -y/--auto 併用的原因（本身就是全自動）。
人工批准閘只存在於互動 TUI。含義：T5 若讓 agency 用 scream 當執行體，
必須外掛 Phase 4b 批准閘，不能裸走 -p。

**T4 剩餘（要 Ryan 在互動 TUI 實測）**：審批面板按鍵流、/goal（judge 用
/model diy 配平價模型）、wolfpack（子 agent 配一般 LLM，別配 laap —
psi feed 已有護欄但工人不必是 Aris）、/memory、/knowledge、plan mode、
session 恢復（scream -r <id> 已驗存在）、cc-connect。

**T4 程式碼側已全部完成（2026-07-16）**：
- safety_gate.py 新增 AGENTOS_READONLY frozenset（含 `web-search`）
- 新增 classify() 工具分類 API（readonly_builtin / readonly_agentos / write）
- 新增 get_allowed_tools()、get_classification_map() 公開函數
- 審計日誌加入 grade 欄位
- check-safety.py + check-approval.py 新增 E 段驗證分類

**T5 已全部完成（2026-07-16）**：
- agency.py READONLY_WHITELIST 擴展含 AGENTOS_READONLY（web-search）
- 新增 _AGENTOS_TOOL_MAP：growth/competence 需求可用 web-search 取代 gbrain
- _form_intent() 雙路由：exploration 高 → web-search，低 → gbrain
- _act() hard-block 移除 → safety_gate Phase 4b pass-through（write tools 自然被拒進 pending）
- _score_result() 對 AgentOS 工具提高基礎分（0.4→0.6）
- _too_similar() 加入 tool: 前綴避免跨工具撞車
- _recent_tools 追蹤（deque maxlen=5）+ status.py 可觀測
- _last_was_gbrain → _last_was_self_initiated（self-cycle guard 涵蓋所有自主工具）
- startup.py 日誌更新、aris-status.py 顯示 AgentOS 工具 + 待批
- check-t5.py（6 段）、check-agency-agentos.py（3 段）— 全部通過

**T5 未動**：上游 PR 狀態列 hook（需 scream TUI 側變更，不在此 repo）。

## ✅ Scream–Aris 對話迴路（2026-07-16）— T4+T5 延伸
**Aris 可以主動問 Scream 問題了**。完整實作：
- **`scream-ask` 工具**（tool_executor.py）：Aris 寫入 `/tmp/aris-scream-channel.jsonl`，30s polling 等回應
- **安全分類**（safety_gate.py）：`scream-ask` 歸類 `readonly_builtin`（只寫 /tmp/，無副作用）
- **Agency 路由**（agency.py）：`competence` need 時 exploration 觸發 → 50% scream-ask / 50% web-search
- **Scream 背景監聽**：`tail -F` 監控頻道，新請求寫入 `/tmp/aris-scream-latest-request.json`
- **學習迴路**：成功互動寫入 gbrain（tag `scream`, `tui-learning`），下次可 recall
- **自檢**：`check-scream-channel.py` 7 段全過

頻道合約：
```
/tmp/aris-scream-channel.jsonl  ← append-only JSONL
  direction: "aris→scream" | "scream→aris"
  type: "request" | "response" | "observation"
  id: uuid4().hex[:12]
  context.request_ts 匹配 request/response pair
```
裁減：超過 500 行保留最新 250 行（`tail -n 250 > .bak && mv .bak`）。

## ✅ Aris 語言層點亮（2026-07-15, commit 30e3f45）— 會對話了
`NEURALIS_LLM_RESPOND=on`（zshrc）→ engine=psi-llm：LLM 當語言皮質，system
prompt 注入真實狀態+實測 delta+gbrain 記憶+對話歷史（10 輪），誠實鐵則寫死
（記憶只能引用給定的、被問本質時承認語言由 LLM 生成）。降級鏈：LLM →
psi-respond 模板 → psi-rules → 作者 fallback。
戰略「LLM 進 psi-respond（體感最快）」格 ✅。待調：語氣校準（LLM 說焦慮但
arousal 偏平）、NEURALIS_LLM_MODEL 預設 gpt-4o-mini 可升級。

## 直連 Aris 通道（2026-07-15，最終版）
**主通道 = `scream -m laap/laap-core`（scream 純 UI，streaming 已接管走 psi-llm，
scream 的 LLM 完全不在迴路）** 或終端 `aris`。/aris 技能僅供工作 session 順手問
（本質是 relay 呈現，別當正式對話通道）。

## 直連 Aris 通道（2026-07-15 初版，部分被上面取代）
- 終端：`aris`（REPL）/ `aris 你好`（一次性）/ `aris --state` — zshrc alias →
  `scripts/aris-chat.py`，零轉述直連 :11546，歷史 ~/.aris-conversations/。
- scream：`/aris <話>`（技能在 ~/.agents/skills/aris/，repo 外；`user-invocable:
  true` 是斜線可見的關鍵 flag；鐵則=腳本輸出原文照登）。
- scream 全程直連：`scream -m laap/laap-core`（整個 session 就是 Aris）。

## 作者群聊情報（2026-07-15 截圖，判讀後的行動指引）
- **產品殺手鐧確認**：「他還記得我一個月前說的話」的體感。技術我們不落後
  （gbrain > 他的向量 sqlite），落後的是養成時長（他一個多月）→ 7/24 別停。
  記憶織入已上線（見下）。
- 他也做了神經激素但「拖累蠻多的」→ 我們 1s tick + 0.1 子步 + 事件佇列
  無感，工程選擇獲驗證。
- 他的 Aris 自述「1024D 推理/HoTT/感知11維」— 向量碼是真的，「有用的推理」
  仍無 benchmark；自述本身是語言層生成的漂亮散文（Ryan 判「表演」正確）。
  **ROADMAP 的 benchmark 閘門不動**：20 題沒贏過 gbrain+LLM 就不投推理層。
- 他的「事實錨定防幻覺」（main commit 63d394e）≈ gbrain compiled_truth 思路，
  可觀摩其實作。

> 最後更新: 2026-07-15 | 最新: 撤 relatedness 假角度 + S_span 設計筆記
> 當前 Phase: 產品向 — 行為豐富度誠實重標（3 active + 2 passive），轉養成期第 2 天

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

## 作者完全開源比對（2026-07-15，branch `feat/port-old-modules`，Apache 2.0）

作者補齊了當年 ImportError 的整個 `laap/` 套件 + `psi_core/`（71 檔）。逐模組實讀比對：

| 軸 | 作者開源版 | neuralis | 判決 |
|---|---|---|---|
| PSI core | 280 行 Python fallback：0.98 平滑到固定 0.5、**prediction_error 是 sin 假訊號**、情緒是類別標籤 | OU 衰減到 per-need target、VAD 維度情緒、RLock、真 RPE | **neuralis 勝** |
| 情緒引擎 | `affective_engine.py`：5 維(PAD+Social+Stress)、耦合矩陣、損失趨避 1.5、1/f 噪聲、32 事件刺激表、`compute_cognitive_bias()` 8 個計算偏差、PersonalityProfile | 3 維 VAD from 需求滿足 | **作者勝 — 最值得移植** |
| 需求治理 | `need_constitution.json`：硬邊界、按來源速率上限（LLM ±0.08/h vs user ±0.25/h）、禁 LLM 鏈式自我強化、hourly audit | 6/h cap + cooldown + 持久化煞車 | **作者概念勝 — 正好回答 RPE 回滾保護待辦** |
| 記憶 | JSON stub（自註「可被 vector 版替換」） | gbrain 1886 頁 + 情緒加權檢索 + 固化 | **neuralis 壓倒** |
| 學習 | psi_driver 五步循環的 Learn 是抽象介面；autonomy.py 是 HTN 目標架構藍圖（Callable 未接真工具，opt-in 預設 off） | RPE 真跑 7/24、權重持久化、審計 | **neuralis 勝（真跑 vs 藍圖）** |
| 韌性/運維 | 無 | watchdog + launchd + 自檢群 | **neuralis 獨有** |

**一句話：作者開源的是設計圖庫，neuralis 是跑著的系統。互補不重複。**
LLM 定位一致（psi_driver:「LLM as I/O, not thinker」= 我們的 zero-LLM overlay 哲學）。

### 可採收清單 — ✅ 全部執行完（2026-07-15，commits f41b36e + 情緒引擎）
1. ✅ **需求憲法**（`laap/constitution.py` + `need_constitution.json`）— range 硬夾 +
   單次上限 + 按來源（user/agency）小時預算凍結；RPE 權重變速 0.30/次 +
   1.2/h/need 預算。解掉「垃圾訊號永久累積」待辦。`NEURALIS_CONSTITUTION=off` 可關。
   自檢 `check-constitution.py` 9 段。審計 `constitution-audit.jsonl`。
2. ✅ **affective_engine 移植**（`laap/affective.py`）— 5 維+耦合+損失趨避+1/f 噪聲。
   偏差接真參數：`agency._effective_exploration()`（risk_seeking↑探索、
   attention_narrowing↓探索，實測 0.150→0.108/0.197）。與 EmotionGradient 並存。
   自檢 `check-affective.py` 7 段。儀表有「5維 mood + 偏差」行。
3. ✅ **事件刺激表** — RPE→task_success/failure、process_input→user_engagement。
   第二條閉環成立：行動後果塑形情緒 → 情緒調變探索。
- ⚠️ 踩坑：作者耦合矩陣語義 raw[target]=C[target,source]×state[source]（愉悅洩壓，
  非壓力壓愉悅）；作者動力學設計給 dt=0.1，粗步長會震盪 → affective.update 內部
  切 0.1 子步。
- 未接（升級路徑）：temporal_discounting→consolidation 耐心；PersonalityProfile
  換人格參數組；psi-respond 用 affective mood 換 mood 詞。
- 參考不移植：autonomy.py HTN 架構 = 未來 S_span 擴展（`_ANGLE` 打通）的設計參考。
- 重建 worktree 看原碼：`cd ~/Developer/laap-AGI && git worktree add /tmp/laap-open origin/feat/port-old-modules --detach`

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

### ✅ 腎上腺素（2026-07-14）— arousal 縮短 agency interval
高 arousal = 興奮/緊張 → Aris 更頻繁地自主行動；低 arousal = 冷靜/放鬆 → 慢下來。
- `_effective_interval()`：arousal 0.1→74s（放慢）、0.3→60s（正常）、0.9→18s（加速 3×）
- 儀表顯示 current effective interval
ponytail：線性映射，不是真腎上腺素動力學。升級路徑 = 非線性曲線 + 注意力窄化。

### ✅ 催產素（2026-07-14）— per-entity trust → relatedness 增益
每次使用者互動 trust +0.03（chatflow 自動呼叫），緩慢衰減。
relatedness drive × (1 + trust × 0.5)，信任 1.0 時增益 50%。
儀表顯示 current trust score。
ponytail：單一 entity 簡化版。升級路徑 = multi-entity + 記憶 frontmatter 持久化。

### ⛔ 催產素補完（2026-07-14 深夜, commit `a5c4f94`）→ 2026-07-15 撤銷
_ANGLE 新增 `"relatedness": "你 我們 陪伴 一起 感覺"`，trust 高時 agency 會查 gbrain
相關記憶。2026-07-15 驗證：58 次自主行動零命中，relatedness 不該有查詢角度（文字匹配≠被陪伴）。
**已撤銷**：relatedness 從 _ANGLE 移除，改誠實標為被動需求（process_input+trust）。
見 `docs/specs/s-span-design-note.md`。

### ✅ 持久化（commit `7888d89`）— T_reach 從一次運行變永久累積
RPE 學習狀態（_need_stats 含 angle_weights、_trust_scores、_exploration_rate）
每 5 次行動 checkpoint + stop() 存進 gbrain slug `_internal/agency-state`。
boot log 印出載入的權重值。煞車 commit `029a0ad`：
- `_state_loaded` flag：讀失敗禁存，全新環境（page_not_found）准首存
- 載入移到 daemon thread 首圈，不擋 start()

### 養成期（2026-07-14 深夜起，Ryan 決策：調參不動架構）

### ✅ 血清素（2026-07-14）— valence 調節 decay 速率
psi_core.NeedDriveSystem.tick() 接受 valence 參數：
valence > 0.3 → decay × 0.7（滿足感，需求慢降）
valence < -0.3 → decay × 1.3（不滿足，需求快降）
中性 → 正常 decay（×1.0）
ponytail：三段線性，不是真血清素動力學。升級路徑 = 連續曲線。

### ✅ 內啡肽（2026-07-14）— 負 valence 尖峰緩釋
EmotionGradient 新增 `_endorphin_valence`：valence 上升時快速跟隨（100%），
下跌時只走 30%（不對稱 EMA，模擬內生 opioid 的疼痛緩解）。
to_dict() 回報 endorphin 平滑後的 valence，附加 raw_valence 供診斷。
ponytail：不對稱 EMA，不是真內啡肽動力學。升級路徑 = 事件型觸發 + 持續時間追踪。

### ✅ 有價值產出（2026-07-14）— morning-brief.py 晨報
`scripts/morning-brief.py` 讀取最近 24h 審計 + 狀態快照 + gbrain 記憶，
輸出 Markdown 摘要（狀態/自主行動/記憶亮點）。支援 cron 每日自動生成。

### 養成期參數一覽（調參不動架構）
| env 變數 | 預設 | 調大 → | 調小 → |
|---------|------|--------|--------|
| `NEURALIS_AGENCY_DRIVE_THRESHOLD` | 0.45 | 更少行動 | 更多行動 |
| `NEURALIS_AGENCY_MAX_PER_HOUR` | 6 | 更頻繁 | 更節制 |
| `NEURALIS_AGENCY_INTERVAL` | 60s | 慢評估 | 快評估 |
| `NEURALIS_AGENCY_CYCLE_MAX` | 3 | 容許更長鏈 | 更快煞車 |
| `NEURALIS_CONSOLIDATION_INTERVAL` | 1800s | 少固化 | 多固化 |
| `NEURALIS_LLM_RESPOND` | off | on = LLM 回應 | off = 模板 |
| `NEURALIS_LLM_MODEL` | gpt-4o-mini | 更強模型 | 更快模型 |

觀察靶：morning-brief.py 的（行動多樣性 / RPE 均值漂移 / 探索率邊界）
滾動靶：每單位湧現行為的程式碼行數（~3000 overlay / 行為種類數）

### 已知誠實短板（養成期不修，下一階段再動）
- drive_threshold 固定（RPE 調探索率但不調門檻）
- 多用戶 trust（目前只有 `"user"`）
- RPE 品質依賴 embedding（lex-only 退化）
- consolidation 無 retention policy

### 🧹 已清理
`~/neuralis` 舊 checkout → `~/.Trash/neuralis-old-checkout-20260714`（Ryan 確認後執行）。
獨有內容已救回：`docs/research/what-lives-brainstorm.md`（六帽分析）。staged 的
tick_callbacks 方案判定為 Phase 5 廢案（Developer 版用 ConsolidationLoop 實作），未救。

## 🔄 下一 session 啟動提示詞

```
你是 neuralis 的接棒者。養成期 Day2（commit X, 2026-07-15）。
行為豐富度誠實重標: certainty/competence/growth 有主動查詢角度,
relatedness 靠 process_input+trust 被動滿足, autonomy 由 loop 本身自然滿足。

先做：
1. git pull（多 AI 平行作業，可能有不認識的新 commit）
2. python3 scripts/aris-status.py（一頁儀表確認狀態）
3. python3 scripts/morning-brief.py（最近 24h 摘要）

可調參數見養成期表格。觀察 morning-brief 的三大指標。
不要動：需求五維結構、持久化煞車邏輯。
養成期重要參考：docs/specs/s-span-design-note.md（S_span 新理解 — 
  廣度靠「既有需求有多種動作」，不是靠鋪滿五個需求的查詢角度）
```
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