# Tulpa 認知引擎 — 統一規格書 v0.3

> 2026-08-25
> 定義每個接點的輸入/輸出、接線方向、反饋迴路。

---

## 一、架構總覽

```
輸入
  │
  ├──→ [L0 分類器] ──→ 領域樹命中？──→ L1─L2─L3 領域樹
  │         │                    │
  │         │                    └→ context + path_log + facet
  │         │
  │         └──→ 未命中 → ontology 分類器
  │                      │
  │                      ├── 強匹配（strength > 0.6）→ 選擇性喚醒 tulpa
  │                      ├── 弱匹配 → 全量六個 tulpa 競爭
  │                      └── 完全無匹配 → 知識按需加載
  │
  ├──→ [六個 tulpa 競爭] ──→ urgency×importance×weight
  │         │                    │
  │         │                    ├── 贏家 → context（全量）
  │         │                    ├── 輸家 → gist（摘要）
  │         │                    └── 所有 → weight 調整（+0.02 / *0.998）
  │
  ├──→ [第三位置觀察者] ──→ 觀察競爭結果
  │         │                    │
  │         │                    ├── conflict 檢測（分數差 < 0.1）
  │         │                    ├── contradiction 檢測（贏家 weight 降）
  │         │                    └── → 寫入 observer_insights
  │
  ├──→ [時間軸競爭] ──→ 過去/現在/未來 三個時間 tulpa
  │         │                    │
  │         │                    └── → 寫入 time_axis_log
  │
  ├──→ [實驗/創造者] ──→ 根據 observer_insights 提出架構改變
  │         │                    │
  │         │                    ├── 分裂建議（tulpa cover 太廣）
  │         │                    ├── 合併建議（structure_isomorphism）
  │         │                    └── 跨域建議（不同領域樹同時觸發）
  │
  └──→ [Prune Cycle] ──→ 每輪執行去蕪存菁
                            │
                            ├── tulpa 休眠（winless_streak ≥ 30）
                            ├── keyword 死亡（lifetime_misses > 50）
                            ├── ontology 衰退（50 輪沒命中）
                            └── facet 壓縮（100 輪沒更新）
```

---

## 二、接點定義

### 2.1 輸入層

| 接點 | 格式 | 來源 | 去向 |
|------|------|------|------|
| `text` | string | HTTP request body | `classify()`, `route_domain()`, `passive_search()`, `score_tulpa()` |
| `_turn_counter` | int | 全局變數，每輪 +1 | `_log_migration()`, `_log_path()`, `prune_cycle()`, `_detect_isomorphism()` |

### 2.2 分類層

| 函數 | 輸入 | 輸出 | 副作用 |
|------|------|------|--------|
| `route_domain(text)` | text | `{routed, context, domain_path}` | 無 |
| `classify(text)` | text | `{domain, activate, facets, object_id, match_strength, signature}` | ontology 重啟（strength 0→0.3） |
| `passive_search(text)` | text | `{found, content, paths}` | ontology cache 寫入（keyword→file） |

### 2.3 競爭層

| 函數 | 輸入 | 輸出 | 副作用 |
|------|------|------|--------|
| `score_tulpa(tulpa, text)` | Tulpa, text | score (float) | keyword 喚醒（_removed_keywords 加回） |
| `compete(text)` | text | `{winner, score, context, runners_up, ...}` | weight 調整、facet 寫入、ontology 學習、路徑記錄、遷移記錄、prune、同構檢測、第三位置觀察、時間軸競爭 |
| `_time_axis_compete(text)` | text | `{winner, score, past, present, future}` | time_axis_log 寫入 |

### 2.4 觀察層

| 函數 | 輸入 | 輸出 | 副作用 |
|------|------|------|--------|
| `_observe_third_position(scored, winner, text)` | scored list, winner, text | None | observer_insights 寫入（conflict/contradiction） |

### 2.5 實驗/創造層

| 函數 | 輸入 | 輸出 | 副作用 |
|------|------|------|--------|
| `_suggest_split(insight)` | observer_insight dict | `{suggested: bool, new_tulpa_name: str}` | 待實作 |
| `_suggest_merge(iso_record)` | structure_isomorphism dict | `{suggested: bool, merged_path: str}` | 待實作 |
| `_suggest_cross_domain(text)` | text | `{suggested: bool, domains: []}` | 待實作 |
| `_execute_split(tulpa_name, new_name)` | str, str | None | 建立新 Tulpa 實例，複製 keyword 的一半 |
| `_execute_merge(path_a, path_b)` | str, str | None | 建立上層抽象節點，合併兩個領域樹節點 |
| `_execute_cross_domain(domains)` | list | None | 建立跨域連結關係 |

### 2.6 持久化層

| 表 | 寫入點 | 讀取點 | 用途 |
|----|--------|--------|------|
| `tulpa_state` | `save_tulpa_state()`, `load_tulpa_state()` | 啟動載入 | 永久儲存 tulpa 權重 |
| `object_facets` | `save_object_facet()` | `load_object_facets()`, `classify()` | 物件多視角累積 |
| `ontology` | `learn_ontology()`, `passive_search()`, `_update_ontology_last_seen()` | `classify()`, `passive_search()` | keyword→file, pattern→tulpa |
| `path_log` | `_log_path()` | `_detect_isomorphism()`, `_past_tulpa_score()`, `_future_tulpa_score()` | 決策路徑歷史 |
| `structure_isomorphism` | `_detect_isomorphism()` | `GET /prune`, `_suggest_merge()` | 結構同構發現 |
| `observer_insights` | `_observe_third_position()` | `GET /observer`, `_suggest_split()` | 觀察者洞見 |
| `time_axis_log` | `_time_axis_compete()` | `GET /timeaxis` | 時間軸競爭記錄 |
| `session_delta` | `save_session_delta()` | 關閉時存檔 | 跨 session 遷移 |
| `migration_log` | `_log_migration()` | `GET /migration` | 參數 delta 時序 |
| `keyword_stats` | `_track_keyword_miss()`, `prune_cycle()` | `prune_cycle()`, `score_tulpa()` | keyword 生命週期 |
| `domain_hits` | `_track_domain_hit()` | `GET /prune` | 領域樹命中統計 |
| `correction_log` | 未使用（保留） | — | 用戶糾正記錄（未來） |

---

## 三、資料流（一輪的完整循環）

```
1. 接收 text
   │
2. route_domain(text)
   ├── 命中 → 跳至 7
   └── 未命中
        │
3. classify(text)
   ├── ontology 強匹配 → 設定 activate list
   └── 弱匹配/無匹配 → activate = None
        │
4. passive_search(text)
   └── 找到知識 → 注入 context
        │
5. score_tulpa() × N
   └── scored list（含有分的 tulpa）
        │
6. compete 主邏輯
   ├── 排序 → 贏家 + 輸家
   ├── weight 調整（+0.02 / *0.998）
   ├── context 組裝（贏家 + gist + facet + 知識）
   ├── facet 寫入
   ├── ontology 學習
   │
7. 後處理（不管是否領域樹命中都執行）
   ├── _log_path() → path_log
   ├── _detect_isomorphism() → 結構同構
   ├── _observe_third_position() → observer_insights
   ├── _time_axis_compete() → time_axis_log
   ├── _log_migration() → migration_log
   ├── _track_keyword_miss() → keyword_stats
   ├── _update_ontology_last_seen()
   └── prune_cycle() → 休眠/死亡/衰退/壓縮
        │
8. 回傳 JSON
```

---

## 四、反饋迴路

### 4.1 內部迴路（每輪執行）

```
競爭 → weight 調整 → 下一輪競爭（已不同）
    ↕
prune_cycle → 休眠/喚醒 → 下一輪競爭者不同
    ↕
第三位置觀察 → 發現衝突 → 實驗者提出改變 → 新的架構
    ↕
時間軸競爭 → 決定基準值 → 下一輪分數計算方式
```

### 4.2 外部迴路（跨 session）

```
用戶輸入 → tulpa 競爭 → 輸出 context → LLM 生成回應
                ↓
用戶糾正 → weight 調整 → 下一輪不同
                ↓
session 結束 → save 到 DB → 下次啟動載入 → 延續上次的權重
```

### 4.3 MOTW 迴路（待實作）

```
預測（時間軸未來 tulpa 勝出）
  → 提前準備 context
  → 用戶實際行為
  → 比對「預測 vs 實際」
  → 不一致 → 更新 path_log 條件機率
  → 一致 → 強化時間軸未來 tulpa 的權重
```

---

## 五、錯誤處理原則

| 情況 | 處理方式 |
|------|---------|
| DB 檔案不存在 | 自動建立所有表（`_init_db()`） |
| ontology cache 的檔案已刪除 | strength 衰退，下次重新搜尋 |
| keyword 在移除後重新出現 | `score_tulpa()` 自動喚醒 |
| 休眠 tulpa 有 keyword 命中 | `score_tulpa()` 跳過（不移除因素），`prune_cycle()` 喚醒 |
| domain tree 對不上 | 回退六個 tulpa 競爭 |
| 所有 tulpa 都休眠 | `compete()` 輸出的 `winner` = 自我理性，score=0.15 |

---

## 六、待辦清單（依優先序）

1. ✅ 第三位置觀察者（conflict/contradiction 檢測）
2. ✅ 時間軸競爭（過去/現在/未來）
3. ❌ 實驗/創造者（分裂/合併/跨域建議與執行）
4. ❌ MOTW 循環（預測→比對→更新）
5. ❌ 周哈里窗盲點報告（GET /blindspot）
6. ❌ 習慣收斂曲線可視化（GET /convergence）
7. ❌ 更多領域樹分支
8. ❌ 接 Hermes MCP 取代 11547

---

## 七、命名規範

| 前綴 | 用途 |
|------|------|
| `_`（底線前綴） | 內部函數，不直接暴露 HTTP |
| `handle_` | HTTP handler |
| `Tulpa` | 認知競爭者類別 |
| `DomainNode` | 領域樹節點類別 |
| 大寫常量 | `TULPAS`, `ALL_DOMAINS`, `KNOWLEDGE_ROOTS` |
| 資料庫表 | snake_case 全部小寫 |

## 八、端點一覽（v0.3 完整版）

| 端點 | 用途 | 狀態 |
|------|------|------|
| `GET /health` | 系統健康 + 即時警報 | ✅ |
| `GET /audit` | 完整稽核報告（9 類警報） | ✅ |
| `GET /blindspot` | 周哈里窗盲點報告（三大盲點） | ✅ |
| `GET /convergence` | 習慣收斂曲線（收斂/震盪/發散） | ✅ |
| `GET /state` | tulpa 即時權重 | ✅ |
| `GET /migration` | 認知遷移時序 | ✅ |
| `GET /prune` | 去蕪存菁 + 結構同構 | ✅ |
| `GET /observer` | 第三位置觀察者洞見 | ✅ |
| `GET /timeaxis` | 時間軸競爭記錄 | ✅ |
| `GET,POST /experiment` | 實驗/創造者建議與執行 | ✅ |
| `GET,POST /cognitive` | 主認知 API | ✅ |

## 九、修正記錄（2026-08-25）

1. `_read_head` 靜默吞錯誤 → print stderr
2. `_execute_split` 幽靈 Tulpa → 註冊到 TULPAS
3. `_suggest_cross_domain` 單領域永遠不觸發 → 誠實 reason
4. 領域樹 bypass 觀察者空資料 → 明確跳過說明
5. `_future_tulpa_score` 回傳型別混亂 → 移除 `-> float` 註解
6. `_detect_isomorphism` 每輪 O(n²) → 每 5 輪限頻
7. 預測 LIKE 匹配 → 改 `'/%'` 精確匹配
8. `_track_keyword_miss` 每輪 90 次 DB 寫 → executemany 批次
