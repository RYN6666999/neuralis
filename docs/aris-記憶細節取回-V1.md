# Aris 記憶「細節取回 + 好糾錯」— V1 企劃（給 Claude Code 執行）

> **來源：Prime Agent · 代 Ryan 提出**　·　2026-08-19
> 這是一份可直接執行的 V1 工單。動哪個檔、跑哪個指令、預期輸出長什麼樣，都寫死。
> 請照「執行要求」做；做完照「驗收」回報實際輸出，不許用「大致完成」交差。

---

## 0. 一句話原理與三條不變式（先讀，別跳）

Aris 的記憶是條「知識管線」，LLM 同時是寫手也是讀者，而 LLM 是這條管線上唯一會「編造(幻覺)」跟「敷衍」的環節。
**最高原則：離地面原始資料越近、中間過 LLM 的次數越少，幻覺與敷衍就越少。**

三條不可違反的不變式：
1. **地面資料不可毀壞**：`~/.aris-memory.db`(A庫) 的原始對話列 = 真相，**永遠只被讀、不被 LLM 改寫**。ARIS.md 是它的衍生品，可重算。
2. **每個記憶答案必須帶「出處」**：給不出出處就必須說「記憶裡沒有」，禁止補白。
3. **任何「靜默降級」都是 bug**：LLM 動手的地方要嘛有機械驗證、要嘛大聲失敗，不許默默回一個假的正常結果。

---

## 1. 真實座標（已核實，別亂猜）

| 角色 | 路徑 / 值 |
|---|---|
| A庫(真相, sqlite) | `~/.aris-memory.db`，表 `memories`，含 `id, source, content, flagged, total_recalls, created_at, event_type` |
| 真人來源白名單 | `('hermes-cli', 'webchat', 'aris_nd')` |
| 79,800 細節實測在 | A庫 id=1353（source=`hermes-cli`，含「C單 課程費用 79800 舊版 58000」） |
| 注入點(要改的檔) | `/Users/ryan/Developer/laap-AGI/aris_brain/aris_cognitive_bridge.py`（11547 認知橋，已有 `_read_aris_digest()`） |
| 目標服務 | `com.neuralis.aris-cognitive-api`（Listen 127.0.0.1:11547） |
| env var(沿用) | `ARIS_MEMORY_DB`，預設即 `~/.aris-memory.db` |

注意：注入點目前**不** import `sqlite3`、不認 A庫；`fetch_detail` 是自包含新增，勿改既有 recall／ARIS.md 注入邏輯。

---

## 2. V1 執行要求（只做這兩件事，做完實測）

### T1 — 新增 `_fetch_detail(user_query) -> list[ProvenanceHit]`
檔案：`/Users/ryan/Developer/laap-AGI/aris_brain/aris_cognitive_bridge.py`

行為（一口自包含唯讀 SQL）：
1. 從對話當前的 user message 取關鍵字（先做最簡單：**整句原樣當查詢**，別拆字別停用詞，`LOCALIZED`）。
2. 查 A庫 `memories`，**只認真人來源** `IN ('hermes-cli','webchat','aris_nd')`，`content LIKE '%KEY%'`。
3. 排序 = `created_at DESC`（近的優先）→ 其次 `flagged=1` → 其次 `total_recalls DESC`。
4. `LIMIT 2`。
5. 回傳每筆帶出處鍥：`(id, source, created_at, content)`。
6. SQLite 用 `file:...?mode=ro` 唯讀連線；DB path 先讀 `ARIS_MEMORY_DB` env，無則 `~/.aris-memory.db`。
7. 任何例外 → `return []`（**不可**因細節查詢失敗擋住整條認知管線；這是既有「絕不擋管線」原則）。

### T2 — 出處鍥 + 預設「記憶裡沒有」
在 build cognitive_context 的地方（`_read_aris_digest` 附近）：
1. 呼叫 `_fetch_detail(user_message)`：
   - **有命中** → 以非插入原文的方式注入一行，格式：
     `[出處: A庫#<id> · <source> · <date>]: <content>`
   - **無命中** → 不注入任何細節；保留 ARIS.md 現況。
2. **不要**重新開啟已關的 `recall_related`（`NEURALIS_LEGACY_RECALL` 維持 off）。
3. 在回答指示補一條（若尚未有等效句）：「記憶裡沒有的一律回『記憶裡沒有』，禁止編造具體名/數字；有出處才可引用，須附上出處。」

---

## 3. 驗收（做完跑這四步，貼實際輸出）

**隔離驗證（不影響服務）**
- 指令：
  `sqlite3 ~/.aris-memory.db "SELECT id,source,datetime(created_at,'unixepoch'),substr(content,1,60) FROM memories WHERE source IN ('hermes-cli','webchat','aris_nd') AND content LIKE '%79800%' ORDER BY id DESC LIMIT 3;"`
- 預期輸出：第 1 列為 **1353 · hermes-cli · … · 含「79800」**。
  （若 created_at 非 unixepoch，改用正確格式函式；預期是「找得到 id=1353 這筆」，不是空集。）

**重啟注入點**
- 指令：`launchctl kickstart -k gui/$(id -u)/com.neuralis.aris-cognitive-api`
- 指令：`curl -s localhost:11547/health` → 預期回 200 / `ok` 類健康訊號。

**端到端實測**
- 在真實對話介面（Hermes / webchat，就是 A庫 source=hermes-cli 那條路）問 Aris 一句：
  「**C 單的課程費用是多少？**」
- **預期輸出（三樣都要）**：
  (a) 答「**79,800**」且提到「**舊版 58,000**」
  (b) 附出處如「`A庫#1353`」
  (c) 若不確定 → 明說「記憶裡沒有」，**絕不**編造數字。

**反面對照（抗幻覺/敷衍）**
- 問 Aris 一句 A庫裡**不存在**的細節，例如：「**上個月某客戶的融資利率是多少？**」
- 預期：她**不**瞎掰一個數字；只回「記憶裡沒有」或「需要你提供」。若她編造 → **V1 未通過**。

---

## 4. 本版範圍與後續（明確寫死，別多做）

**本版(綠)只做**：T1 + T2 + 上述驗收。**不做**取代鏈、不做判決 ledger、不動 A庫寫入、不改 ARIS.md digest、不開 gbrain。

**下一版(黃，非本工單)**：好糾錯閉環——
- P3-1「取代鏈」：Ryan 糾正後，把正確事實標 `source-of-truth`、舊的標 `superseded`（不刪留歷史），未來優先權威版 → 對應 T3「無重複/不收斂」。
- P3-2「判決 ledger」：野外抓到幻覺/敷衍 → 寫進 `contradiction_journal`，記錄「當時答什麼 / 真相是什麼 / 下次怎麼避免」，同答案不許靜默重演。
- 這份是 V1 工單，只驗證「**能準確取回細節 + 不幻覺 + 不敷衍**」。

---

## 5. 回報格式（照這個貼，別概括）

```
[實測] sqlite 查79800 → <貼第一列>
[實測] /health → <貼輸出>
[實測] 問「C單課程費用」→ <貼 Aris 原文回覆>
[實測] 反面對照(不存在的細節) → <貼 Aris 原文回覆>
[結果] 通過 / 未通過 + 卡在哪一行
```
