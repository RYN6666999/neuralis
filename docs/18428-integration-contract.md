# 18428 整合合約 — 輸入/輸出定義

> 目的：定義 18428 與 Aris 主系統（:11551 / :11547 / latest.json）之間的介面。
> 合約鎖定後，18428 從隔離狀態逐步開放到生產。

---

## 輸入合約（18428 從主系統讀什麼）

### I1：用戶輸入（已實作）
```
POST /cognitive 的 body.text
```
來源：外部呼叫端（Hermes hook 或 chatflow）
格式：純文字字串
時機：每輪對話
狀態：✅ 已實作

### I2：記憶上下文（待整合）
```
GET :11551/wake?limit=5
```
18428 需要知道「上一輪的注意力線索 + 相關記憶」
回傳格式：`{"context": "...", "recalled_ids": [...]}`
整合方式：compete() 內部在每輪開始前 fetch_wake()
狀態：❌ 未實作，隔離中

### I3：PSI 情緒狀態（待整合）
```
GET :11547/v1/cognitive 的 PSI 區塊
或直接讀 state/latest.json
```
18428 需要知道「當前情緒來調節 urgency/importance」
回傳格式：emotion dict（valence, arousal, dominance, needs）
整合方式：compete() 內部在每輪開始前 fetch_psi()
狀態：❌ 未實作，隔離中

### I4：記憶查詢（可選）
```
GET :11551/memories/query?q=xxx
```
當 tulpa 需要查證某件事時，可以叫記憶系統
整合方式：被動搜尋，僅在 passive_search() 內使用
狀態：❌ 未實作

---

## 輸出合約（18428 寫什麼/輸出什麼）

### O1：競爭結果（已完成）
```
POST /cognitive 的 response body
```
回傳格式：
```json
{
  "winner": "explore",
  "score": 0.85,
  "gist": "...",
  "runners_up": [...],
  "object_id": "..."
}
```
狀態：✅ 已實作
消費端：⚠️ 目前無人消費（只輸出到 HTTP response）

### O2：競爭結果寫入記憶（待整合）
```
POST :11551/memories/store
```
18428 每輪決定 winner 後，把競爭結果寫回記憶 DB
包含：content=winner gist, attention_line=next focus, tags=["tulpa"]
狀態：❌ 未實作

### O3：System prompt 注入（待整合）
```
18428 → pre_llm_call hook → system prompt
```
18428 的競爭結果（winner gist + 觀察者洞見）應注入 system prompt
格式：`【Tulpa 視角】winner:explore | gist:...`
狀態：❌ 未實作

---

## 資料合約（DB 架構決策）

### 當前狀態
- 18428 自有 DB: `data/tulpa_memory.db`
- 主系統 DB: `~/.aris-memory.db`

### 決策：⚠️ 暫不合併，保持獨立
理由（Ponytail 經驗）：
1. 兩者的 schema 完全不同（競爭權重 vs 記憶條目）
2. 18428 的 DB 寫入頻率高（每輪多筆 migration/observation）
3. 合併會增加主系統 DB 的鎖競爭
4. 等 18428 穩定運作一段時間後再評估

### 替代方案
18428 的 I/O 全部透過 HTTP API，不直接存取主系統 DB。
兩者資料交換透過 `:11551/store` 和 `:11551/wake` 進行。

---

## API 路由合約（端點狀態）

| 端點 | 當前狀態 | 整合後狀態 |
|------|---------|-----------|
| `GET /health` | ✅ 正常 | ✅ 不變 |
| `GET /audit` | ✅ 正常 | ✅ 不變 |
| `GET /blindspot` | ✅ 正常 | ✅ 不變 |
| `GET /state` | ✅ 正常 | ✅ 不變 |
| `GET /migration` | ✅ 正常 | ✅ 不變 |
| `GET /prune` | ✅ 正常 | ✅ 不變 |
| `GET /observer` | ✅ 正常 | ✅ 不變 |
| `GET /timeaxis` | ✅ 正常 | ✅ 不變 |
| `GET /convergence` | ✅ 正常 | ✅ 不變 |
| `POST /cognitive` | ✅ 正常 | ✅ 加入記憶+情緒上下文 |
| `POST /feedback` | ✅ 正常 | ✅ 不變 |
| `GET /experiment` | ✅ 正常 | ✅ 不變 |
| `POST /experiment` | ✅ 正常 | ✅ 不變 |
| `GET /predictions` | ✅ 正常 | ✅ 不變 |
| `GET /sessionperf` | ✅ 正常 | ✅ 不變 |

---

## 切割計畫

### 第 1 刀 ─── 抽出 DB 層（~300 行）
```
aris_tulpa_api.py → tulpa_db.py
```
抽出：`_db()`, `_init_db()`, `load_tulpa_state()`, `save_tulpa_state()`,
`save_session_delta()`, `load_object_facets()`, `save_object_facet()`
以及所有純 DB 查詢輔助函數

### 第 2 刀 ─── 抽出核心引擎（~900 行）
```
aris_tulpa_api.py → tulpa_engine.py
```
抽出：`Tulpa` class, `classify()`, `learn_ontology()`, `DomainNode`,
`score_tulpa()`, `compete()`, `_track_*` 函數
以及 `TULPAS`, `ALL_DOMAINS` 全域變數

### 第 3 刀 ─── 抽出演化層（~500 行）
```
aris_tulpa_api.py → tulpa_evolution.py
```
抽出：`prune_cycle()`, `_detect_isomorphism()`, `_observe_third_position()`,
`_time_axis_compete()`, `_suggest_merge/split()`, `_execute_merge/split()`,
`_run_experiment_cycle()` 以及所有 `_past/present/future_tulpa_score` 函數

### 第 4 刀 ─── 只剩 API 層（~500 行）
```
aris_tulpa_api.py → 變薄的 tulpa_api.py
```
保留：所有 `handle_*` async handlers + `main()` + route setup

### 驗證
每刀後：`python3 -m py_compile scripts/aris_tulpa_api.py` + `import` 測試
三刀完成後：啟動 18428 → `GET /health` → `POST /cognitive` → `GET /state`
