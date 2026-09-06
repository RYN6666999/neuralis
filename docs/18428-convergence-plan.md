# 18428 收斂情報 — Ponytail 規格

> 方法論繼承自 Aris 記憶管線收斂（18 來源→3 管線）。同一套：
> Step 1 全面清查 → Step 2 依賴圖映射 → Step 3 風險分級 → Step 4 分批執行 → Step 5 建立單一權威管線 → Step 6 加真實警報 → Step 7 驗證

---

## Step 1：全面清查 — 18428 的所有接觸點

### 程式碼

| 檔案 | 行數 | 角色 |
|------|------|------|
| `scripts/aris_tulpa_api.py` | 2597 | 主體 — 六個 tulpa 競爭引擎 + HTTP API |
| `scripts/aris_tulpa_api.py.snapshot-20260826` | 快照 | 備份，可刪 |
| `data/tulpa_memory.db` | ❌ 不存在 | 自己的 SQLite（獨立於 `~/.aris-memory.db`） |
| `data/` 目錄 | ✅ 存在 | 已有 `memory_evidence.db` + `skill-audit-log.md` |

### 依賴

| 依賴 | 狀態 |
|------|------|
| `aiohttp` | ⚠️ 裝在 laapenv（Python 3.12），**不在預設 python3** |
| 自己的 DB schema | ✅ 在程式碼內建（`_init_db()`），啟動時自動建立 |
| 外部記憶系統 | ❌ 無任何 import 或 HTTP 呼叫到 :11551 |
| 外部情緒系統 | ❌ 無任何讀取 latest.json 的程式碼 |

### 外部介面（該從哪裡讀，該寫到哪裡）

| 介面 | 目前狀態 | 風險 |
|------|---------|------|
| 讀取「用戶輸入」 | 透過 HTTP POST 傳入 | ✅ 正常（`POST /cognitive`） |
| 讀取「上一輪認知上下文」 | ❌ 不存在 | 🔴 孤立 — 不知道上一輪發生什麼 |
| 讀取「PSI 情緒狀態」 | ❌ 不存在 | 🔴 孤立 — 不知道當前情緒 |
| 讀取「記憶召回結果」 | ❌ 不存在 | 🔴 孤立 — 不知道過去經驗 |
| 寫入「競爭結果」到記憶 DB | ❌ 不存在 | 🔴 輸出孤立 — 競爭結果無人消費 |
| 輸出到 system prompt | ❌ 不存在 | 🔴 輸出孤立 — 從未進過對話 |

### launchd / 排程

| 項目 | 狀態 |
|------|------|
| launchd plist | ❌ 不存在 |
| 任何 cron | ❌ 不存在 |

---

## Step 2：依賴圖映射

```
18428 目前的網路圖（簡化版）：

POST /cognitive ←── 外部輸入（誰送？沒定義）
        │
        ├── 六個 tulpa 競爭
        │       └── 自有 SQLite（data/tulpa_memory.db）
        │
        └──→ JSON response（誰接？沒定義）

真實世界應該有的：

:11551/wake ──→ 18428 ──→ 競爭結果 → Hermes system prompt
                ↑                     ↑
           latest.json            :11551/store
           （PSI 狀態）           （寫入記憶）
```

18428 現在是一個**漂浮的函式庫** — 功能完整，但沒有輸入端也沒有輸出端。

---

## Step 3：風險分級

### 🔴 紅燈（會炸 / 已斷）

| # | 問題 | 說明 |
|---|------|------|
| 1 | **aiohttp 不在預設 Python** | `python3 -c "import aiohttp"` 失敗。啟動即 crash |
| 2 | **無介面接收認知上下文** | 不知道上一輪的記憶、規則、PSI 狀態 |
| 3 | **無介面輸出到對話** | 競爭結果寫入自己的 DB 但沒人讀 |
| 4 | **兩個 DB 系統** | `tulpa_memory.db` vs `~/.aris-memory.db`，資料分裂 |

### 🟡 黃燈（功能不完整，但不會 crash）

| # | 問題 | 說明 |
|---|------|------|
| 5 | **2597 行無型別檢查** | 全部裸 dict/list，無 pydantic/dataclass 驗證 |
| 6 | **獨立於新記憶系統** | 不知道記憶控制器、7 路徑召回、證據閘門的存在 |
| 7 | **24 個端點無消費者** | `/audit`、`/blindspot`、`/convergence` 等全部寫好但沒人 call |

### 🟢 綠燈（可忽略 / 已正常）

| # | 問題 | 說明 |
|---|------|------|
| 8 | 自有 DB schema | ✅ 程式碼內建，啟動自動建立 |
| 9 | tulpa 競爭邏輯 | ✅ 獨立完整 |
| 10 | 觀察者 + 時間軸 + prune cycle | ✅ 全部實作 |

---

## Step 4：分批執行

### 第一批（🟢 立即做，零風險）

1. **寫這份收斂情報到 `docs/18428-convergence-plan.md`** — 讓下一輪的你知道從哪裡開始
2. **隔離標記** — 在 `aris_tulpa_api.py` 檔頭加醒目註解 `⚠️ UNTIL INTEGRATED WITH :11551`
3. **裝 aiohttp 到預設 python3** — `pip3 install aiohttp`，讓它至少能啟動但不註冊 launchd
4. **驗證啟動** — `python3 scripts/aris_tulpa_api.py &` → port 18428 活著 → 立刻關掉

### 第二批（🟡 下一步，有討論空間）

5. **定義輸入合約** — 18428 需要從 `:11551` 讀什麼？從 `latest.json` 讀什麼？
6. **定義輸出合約** — 競爭結果寫回 `:11551/store` 還是保留自有 DB？
7. **兩個 DB 的去留** — 合併到 `~/.aris-memory.db` 還是保持獨立？

### 第三批（🔴 等架構決策）

8. **整合到 pre_llm_call hook** — 18428 結果注入 system prompt
9. **註冊 launchd** — 自動重啟

---

## Step 5：建立單一權威管線（目標架構）

```
最終架構（建議）：

:11551/wake ──────────────────┐
                              ├──→ 18428 Cognitive API
latest.json（PSI 情緒）──────┘      │
                                    ├── 自有 tulpa_memory.db（競爭權重、path_log）
                                    ├── POST :11551/store（競爭結果寫入記憶）
                                    └── JSON response → Hermes system prompt 注入
```

兩條管線：
- **18428 讀取**：`wake`（記憶）+ `latest.json`（情緒）→ 競爭判斷
- **18428 寫入**：競爭結果 → 記憶 DB（供未來召回用）

---

## Step 6：加真實警報

整合後 18428 需要的警報：
- Health check → SYSTEM ALERT（與 :11547/:11551 同級）
- 六個 tulpa 權重收斂異常 → `migration_log delta 變異數 > 0.01` 警報
- 自有 DB 連線失敗 → 不擋主流程

---

## Step 7：驗證（整合後）

- `GET /health` → 200
- POST 模擬輸入 → 回傳非空認知上下文
- 競爭結果寫入 `:11551/store` → 搜得到
- 關閉自有 DB → 18428 降級但主流程不中斷

---

## 當前執行的第一階段

```
□ 寫完這份收斂情報 ✅
□ 隔離標記（檔頭加 ⚠️）
□ 裝 aiohttp（pip3 install）
□ 驗證啟動（啟動→檢查→關閉）
□ 下一步：定義輸入/輸出合約
```