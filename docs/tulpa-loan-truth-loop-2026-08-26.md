# 18428 瘦身執行清單 + 真循環機制設計（2026-08-26）

> 依據 ponytail(first-principles) 診斷 + Hermes 剃刀分析彙整。
> 目標：把「自轉的日誌螺旋」砍掉，把剩下的核心接成「有真值、有消費者、誤差回灌」的真循環。
> 判準對齊 Ryan 量尺：T2(感覺讀數可校正、誤差逐日降)、T3(無重複鬼打牆)。

---

## Part 1 — 瘦身執行清單（砍完系統不斷功能，反而更優雅）

### A. 死碼（定義了但 0 caller）— 直接砍
| 目標 | 行號 | 理由 |
|---|---|---|
| `_suggest_split()` | 1791–1816 | 0 caller；分裂建議另有硬塞路徑走 |
| `prediction_accuracy` 表 | _init_db | CREATE 後 0 次 SELECT（無人讀） |

### B. 被呼叫但產出沒人吃 — 砍函式 + 砍表
| 目標 | 行號 | 理由 |
|---|---|---|
| `_track_tulpa_keyword_candidates()` | 1098–1150 | 只 INSERT `tulpa_keyword_candidates` 表，全 codebase 無人讀（domain 有 `_apply_domain_keyword_additions` 對稱，tulpa 沒有）|
| `tulpa_keyword_candidates` 表 | — | 上者專用，砍 |
| `_psi_feedback()` | 1646–1663 | 單向寫 FIFO、無回讀；接收端可能在線也可能不在線，沒閉環 |
| `_suggest_cross_domain()` | 1846–1876 | 自己標注的 Bug#3「永遠不觸發」，死路徑 |

### C. 每輪重複的無效寫入 → 改 on-demand（不砍端點，砍 side-effect）
| 目標 | 行號 | 改法 |
|---|---|---|
| `_run_experiment_cycle()` 的 merge 建議 | 1951–1962 | 每輪 INSERT merge_suggestion→observer_insights（37 筆沒人看）。砍掉每輪寫入，改只在 `GET /experiment` lazy 計算 |
| `_suggest_merge()` 每輪呼叫 | 1951 | 改只在 on-demand 端點呼叫 |
| `_suggest_merge()` | 1819–1843 | 保留 for GET 使用 |

### D. 心理狀態（漂亮的假連接）→ 誠實化，不砍
| 目標 | 改法 |
|---|---|
| `_psi_state()` | 離線時回傳 `{'available':False}`，`_future_tulpa_score` 見到後打 warning，不靜默用中性值 |

**瘦身小結**：約 −250 行、−3~4 表。核心 `compete()` 管線、端點、記憶表全保留。

---

## Part 2 — 構成「真循環」的機制設計

### 真循環的定義（對齊 T2/T3）
**輸出 → 給「不是自己」的消費者執行 → 外部判成敗 → 誤差逐日降 → 回灌成唯一可調參數。**

現在斷在哪：缺「外部消費者」+「外部真值」。所以補機制要補這兩格，不是補更多寫入。

### 機制一：單一預測錨（最小第一環）
挑一個「外部能判對錯」的輸出當錨，先接這個：
- **預測「這句該召回哪段記憶 / 該叫哪支工具」** → 執行 → 對失敗
- 誤差 = 預測命中/滑空
- **唯一可調參數**：`_future_*` 或 ontology strength +0.1 / −0.1
- 目標：T2 誤差逐日降、T3 不重複

### 機制二：寫入閘門（把「自我反饋」變成「有消費者的反饋」）
新加一條硬規則（對齊 ponytail「question whether the write should exist」）：
> 每寫入一筆表，必須能回答 3 問：
> ① 誰會讀這行？② 讀後做什麼？③ 怎麼知道做對了？
> 答不上 → **不寫**。

直接把 `_observe_third_position` 那 40 筆 conflict 從「unconditional INSERT」改成「過此閘」——沒有對應消費者處理，就不寫。

### 機制三：預測→校正真正閉環
現在 `_time_axis_compete → _settle_prediction → prediction_accuracy 表`，但結果沒回饋到 `_future_tulpa_score`。
改：`_settle_prediction` 的命中/失誤**直接回寫** `_future_tulpa_score` 的 path 頻率權重（錯一次調一次）。這是「真的會因錯誤而改」的關鍵—目前只記錄不改。

### 機制四：contradiction 真正驅動行為
現在矛盾（贏家但 weight 降）只被記錄。改：達閾值自動觸發 weight 校正 / 進入 prune，不是再來一趟 pending_suggestions。

---

## Part 3 — 新計劃（三階段）

### Phase 0 瘦身（對齊 Part 1）
動手砍 A/B/C，core 不觸、端點全留。

### Phase 1 接第一個真循環（單一錨）
- 選「記憶召回預測」當錨
- 搭「外部消費者 + 真值 + 誤差回灌」（機制一/三）
- 用 T2/T3 量尺驗證：誤差逐日降？
- 規模：≤300 行最小單環 prototype，2757 行凍在旁，**不走原線路**，先跑通再看要不要併。

### Phase 2 循環固化 + 對外表接消費者
- 循環驗證收斂後，才開始把 `/cognitive` 真正接到一個**真心會執行**的消費者（某 agent / 工作流），不是手動 curl。
- 消費者收到的 context 不再只是「樣板字串」，而是真「地面資料約束」結果。

---

## 驗收（怎麼證明真而不是假）
1. **今天上線 59 行的真正監控**：`誤差值 X → 明天誤差 X−Δ`，逐日降。
2. **無重複**：同類錯不再犯（T3）。
3. **有人消費**：至少 1 個非 `/cognitive` curl 的外部 consumer 在讀真循環輸出。

> 一句話：真循環 = 裡面只有一個真值 + 一個能動的消費者 + 誤差回灌；其餘全是自轉。
