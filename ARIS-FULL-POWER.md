---
name: aris-full-power
description: Aris「功率全開」接線圖——怎麼把 Aris 所有真實可運行的子系統接起來（LLM 散文、量子層、潛意識、演化閘門、狀態觀測），以及最容易誤會的地方與坑。任何要在 Aris 上開能力/接線/查狀態的 agent 先讀這份（本檔案已備份到：~/.agents/skills、~/.hermes/skills、~/.config/opencode/skills、~/Developer/ecc/skills、neuralis 與 laap-AGI repo 根）。
---

# Aris 功率全開接線圖（2026-08-12 實測版）

> 目標：Aris 每個「真實存在」的子系統都接通；不裝死引擎、不造假輸出。
> 口訣：**仕樣不是引擎——code path 才是；mtime≥boot 才是活的。**

## 0. 身分地圖（先對作者再動線）

| 名稱 | 是什麼 |
|---|---|
| Hermes | Ryan 的 agent gateway（~/.hermes，launchd ai.hermes.gateway）——**狀態報告的作者**；讀它回覆用 `sqlite3 ~/.hermes/state.db` 的 messages 表 |
| Aris | 被檢驗的系統。口語通道已在 11546（見 §1） |

## 1. Port 地圖（2026-08-11 覆核版，勿再標錯）

| port | 身份 | PID 型態 | log | 模組權威 |
|---|---|---|---|---|
| 11547 | aris_cognitive_api（neuralis overlay） | 81765 級 | /tmp/com.neuralis.aris-cognitive-api.log | **唯一**（/health 13/21；/v1/cognitive） |
| 11546 | **LAAP Brain API**（laap_brain_api，start.sh 起） | 被 watchdog 換 | ~/Developer/neuralis/laap-api.log | 無（health 是泛用 echo） |
| 11550 | aris-relay（launchd，forward 給 11546） | 1429 | /tmp/com.neuralis.aris-relay.log | 無 |
| 11551 | aris-memory | 1434 | — | 無 |
| 11530 | 純上游（死） | — | — | 無 |

- module 狀態只問 11547。11546 只跑 chat/LLM 管線。
- 重啟 11546 用 `scripts/reload-aris.sh 11546`（不燒 watchdog 5 次/h 預算；避免 crashloop lock）。
- **注意：start-laap-api.sh 用 `>`，重啟會截斷 laap-api.log**——要留證據先 `cp`。

## 2. 功率全開的六條線（已接好的）

1. **LLM 散文**：chatflow gate——狀態關鍵字（_STATUS_QUERY：状态/情況/你在干嘛/status/health/心跳/psi状态/qre状态…）→ 收 rules 讀數（T2 讀數）；**一般對話 → 放行 LLM 散文**（psi-llm，deepseek via openrouter，key 在 ~/.hermes/.env）。gate 在 neuralis/laap/chatflow.py「author results」處。
2. **量子層（真引擎）**：`aris_v12_dense_kernel.py`（ArisLMv12/V12DenseKernel，「Deep Quantum Kernel Layer」）。**`aris_v12_5_engine` 這個名字從未存在過**（git 全史無）——aris_subconscious 舊 import 要靠它所以自廢；已改真名。
3. **潛意識**：aris_subconscious 用 **get_subconscious() singleton**（integrator 也改用 singleton，避免雙實例雙 21s init）；chatflow `_feed` 喚醒（start_subconscious + feed user_msg）；V12 engine init 首次約 21s。
4. **quantum_output.json 生產者**：`neuralis/laap/quantum_output.py`——事件驅動（input_queue.json 有新輸入→ **真 V12 kernel**＋gbrain 召回＋PSI 兜底 → 寫 state/quantum_output.json；引擎名/延遲如實標記）。**成功才快取、失敗重試**（boot 競態：startup_all 時 aris_brain 還沒進 sys.path，runpy 之後才行）。啟動掛在 startup.py ensure_quantum。
5. **狀態觀測**：StatusWriter（neuralis/status.json，每 30s）。**tuple bug 已修**：agency `_need_stats` 的 key 是 (need,tool) tuple，直接 json.dumps 會週期性失敗——status.py 已 stringify。
6. **演化閘門**：`laap.evolve_gate`——AGI kernel 的 birth/heal/evolve 提案**只入票佇列不落地**（~/Developer/neuralis/evolve-gate/tickets.jsonl）；審查：
   `~/Developer/neuralis/scripts/evolve-gate-review.py list|show|approve|reject <id>`
   approve **只改狀態**，不自動套用——落地永遠由人（走 git 可回退）。

## 3. 未接線（誠實清單）

- **AGI Kernel daemon（agi_kernel.AGIKernel）**：2026-08-12 實測——在 chatflow 首請求同步啟動會 **hang 住第一個請求**（watchdog ~90s 換進程）。**已回退**。若要再接：不要在請求路徑同步啟動；用背景 thread + 啟動後觀察 2 分鐘（health/首 chat 不卡），並確認 5 個 loop 的記憶寫入不擋主流程。接到後其 evolve/heal/birth 提案自動進閘門（agi_kernel.py 已埋好 gate 掛鉤）。
- self_evolve/autonomy「自動改碼/自動發訊」：**設計上不開**——閘門外零落地權。Feishu bridge（DirectFeishuBridge）無 SDK 時靜默。
- agi-kernel 的 heal `diagnose()`：AutoHealer 沒有 diagnose 方法（閘門票已顯示此 error）——已知小瑕疵，不影響運行。

## 4. 容易誤會的地方（踩過的全記）

1. **11546 ≠ relay**（relay=11550）；11546=LAAP Brain API。模組權威只在 **11547**。
2. **stale 檔會騙人**：`state/laap_integrator.log`（12:37 死檔）跟活 state 混在同一目錄。鐵律：**讀任何 log 先驗 mtime ≥ 目標進程 boot time（`ps -o lstart=`）＋ lsof 確認有人開著**。
3. **UTC 陷阱**：`.aris-evaluator/psi_state.json` 的 timestamp 是 UTC——`08-10T21:51Z` = 本地 **08-11 05:51**。它是 evaluator 自帶模擬狀態（**不打任何 API**），別拿來跟 runtime 比。
4. **兩個 repo 兩個世界**：`~/Developer/neuralis`（overlay，實際改這裡）vs `~/Developer/laap-AGI/aris_brain`（上游 fork，真程式碼）vs `~/laap-AGI`（純上游鏡像，別動）。改前先確認在哪一層；runpy 從 laap-AGI/aris_brain 起才把 aris_brain 加進 sys.path。
5. **交接頁也會錯**：「rust daemon 沒在跑／無 rust-latest.json」是舊誤記——psi-daemon（PID 1481 級）每 100ms 寫 `laap-AGI/aris_brain/state/rust-latest.json`。引用任何「狀態宣稱」先驗實機。
6. **counter 三套別混**：integrator（殘留 log 最高 117）／API per-request（95~107）／python-psi cycle（43081+，latest.json）——跨套引用必鬼打牆。
7. **QRE gate 行為**：狀態題得讀數、一般題得散文——要改判定只看 chatflow `_STATUS_QUERY`。
8. **watchdog**：11546 由 watchdog 守，3 次 health 失敗 ~90s 換進程、5 次/h 預算；crash-loop 會有 lock 檔。開發重載一律 `reload-aris.sh`。
9. **報告作者是 Hermes**：任何「Aris 狀態報告」先確認誰寫的（~/.hermes/logs/agent.log），數字要附來源（檔+行+時間戳），查無來源標 UNSOURCED。

## 5. 每日量尺（三布林）

`~/aris-yards.txt`。T1 跨對話記憶、T2 感覺讀數（可校正）、T3 無重複/不收斂。
2026-08-11 已記：T1=. T2=. **T3=F**（同類「死的當活的／假狀態報告」再犯）。


## 記憶系統（T1）
**完整地圖見獨立 skill：`aris-memory-system`**（~/.agents/skills 等 6 處備份，覆蓋版 2026-08-12）。
三句核心：寫入 gbrain `laap/memory/*` 正常；讀取已修（token 化＋hybrid_hits_any＋**live 解析層是 laap-AGI 作者版不是 overlay**）；端到端「全新對話答對」仍未閉環（會幻覺）——工單＋驗證法在該 skill §5。
