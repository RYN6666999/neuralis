# Aris 認知架構完整地圖 — 2026-08-28 收斂終版

> 從 Aris 記憶系統收斂（18 來源→3 管線）、情緒橋接、18428 審計、
> 領域樹成長、自我審計閉環——這整趟 debug 循環的完整認知架構。
> 未來任何新對話或新領域的接入，先讀這份。

---

## 一、核心架構：四層 + 三管線

```
┌─────────────────────────────────────────────────────────┐
│  L1 認知層（tulpa engine）  — 六種思考模式              │
│    本我理性/本我感性/自我理性/自我感性/超我理性/超我感性  │
│    不變的六個 thinking 原型，weight 可學習遷移            │
├─────────────────────────────────────────────────────────┤
│  L2 領域層（domain tree）    — 專家的專業知識            │
│    一棵樹=一個專家領域（房仲、教練、軟體⋯⋯）             │
│    節點含 keywords / context_text / orientation 映射     │
│    從 interaction 長大，不是從檔案讀取                    │
├─────────────────────────────────────────────────────────┤
│  L3 橋接層（判斷力/Debug Expert）— 認知與領域的適配     │
│    哪個領域+哪個情境 → 該用哪種 thinking                 │
│    從校正歷史中學習（domain_learned_orientation）         │
│    校正率 > 40% → 🟡 提醒，> 60% → 🔴 高風險            │
├─────────────────────────────────────────────────────────┤
│  L4 自我審計層（self-audit）— 系統的自檢機制             │
│    compete 結束後自動檢查 domain_optimization            │
│    高校正率 → 寫入 observer_insights                    │
│    下一輪 hook 讀取 → 注入 system prompt                 │
│    不需要你開口說「你錯了」，系統自己會先報               │
└─────────────────────────────────────────────────────────┘

三條管線（不重疊，各有生命週期）：

身份記憶（M0·熱層）：
  ARIS.md → :11547 _read_aris_digest() → cognitive_context
  規則 + 身份 + 情感地標，永不衰減

經驗記憶（M1-M7·暖/冷層）：
  每輪對話 → post_llm_call hook → :11551/store
  下一輪 pre_llm_call hook → :11551/wake → system prompt
  τ 加權排序（有用記憶衰減慢）

情緒引擎（PSI·即時）：
  Rust daemon (2000Hz) → latest.json → :11547 + 18428
  五需求：certainty / competence / autonomy / relatedness / growth
  影響 tulpa 競爭的 urgency/importance 基線
```

---

## 二、完整學習循環（歷史→反思→回饋→執行→復盤→壓縮→迭代）

```
每輪對話：

  1. 輸入（用戶說了一句話）
     │
  2. 領域樹匹配（route_domain）
     │  → 找到最深匹配節點（L2）
     │  → 檢查校正歷史（L3）
     │  → 如果校正率 > 40% → 標注 🟡/🔴
     │
  3. tulpa 競爭（compete）
     │  → 六個 thinking 模式打分（L1）
     │  → PSI 情緒調節（valence/arousal/competence/certainty）
     │  → 認知上下文調節（identity_boost）
     │  → 最高分勝出
     │
  4. 校正記錄（_track_domain_perf）
     │  → 如果 winner 違反 domain_orientation
     │  → 記錄 correction++
     │  → 更新 domain_learned_orientation（L3 學習）
     │
  5. 權重遷移（_log_migration）
     │  → winner weight +0.02
     │  → 輸家 weight × 0.998
     │  → 記錄到 migration_log
     │
  6. 自我審計（_self_audit）
     │  → 查 domain_optimization
     │  → 校正率 > 40% → 寫入 observer_insights
     │
  7. Hook 注入（下一輪開頭）
     │  → 讀 18428 /cognitive（領域視角+校正提醒）
     │  → 讀 18428 /observer（自我審計提醒）
     │  → 讀 :11551/wake（經驗記憶+τ 排序）
     │  → 讀 :11547/v1/cognitive（身份+情緒）
     │  → 全部注入 system prompt
     │
  8. τ 學習（每輪結束後）
     │  → 如果記憶被成功召回
     │  → discovered_salience += 0.1
     │  → τ 常數變長 → 有用記憶衰減更慢
     │
  9. 夜間固化（做夢模組，pending）
     → 重複合併
     → 矛盾檢測
     → 語意提煉
     → 噪聲過濾
     → 過期降權
     → L0 摘要生成
```

---

## 三、debug 審計方法論（可復用）

### 3.1 Ponytail 最小骨架（先列清單再給結論）

```
Step 1 — 全面清查 所有來源（檔案/DB/API/行程/config）
Step 2 — 依賴圖映射 誰 import 誰？誰寫入？誰讀取？
Step 3 — 風險分級 🔴會炸 / 🟡需留 stub / 🟢直接砍
Step 4 — 分批執行 先綠、再黃、最後才碰紅
Step 5 — 建立單一權威管線 選一個儲存層為主
Step 6 — 加真實警報 不靜默降級
Step 7 — 驗證 每步操作後檢查所有 health 端點
```

### 3.2 紅軍攻擊框架（攻自己的方案）

```
攻擊點 ①：「這跟誰綁在一起？」
  表的壽命 = 哪個子系統的壽命？
  如果 DB 砍掉重建，資料會消失嗎？

攻擊點 ②：「誰會讀它？」
  寫了但沒人讀 = 空島
  誰是消費者？在哪個 pipe 裡？

攻擊點 ③：「誰觸發它？」
  如果是被動觸發，誰來觸發？
  有沒有自動觸發機制？還是要人踹？

攻擊點 ④：「我是不是在蓋第四座島？」
  現有 3 條路不通 → 不該繞過它們建第 4 條
  應該先打通已存在的路
```

### 3.3 驗證清單（不只是 compile 過）

```
□ 單點測試（python3 -c import + 回傳正確）
□ 路徑覆蓋（所有 return 路徑都有 domain_optimization？）
□ 消費者檢查（誰讀這個結果？）
□ 斷線檢查（服務掛了 → 不擋主流程？）
□ 空數據檢查（DB 沒資料 → 不亂報？）
□ 邊界檢查（session_id 空？domain_path 空？）
```

---

## 四、領域樹成長節點（哪些東西會從 interaction 長大）

| 節點 | 存在位置 | 目前狀態 | 長大方式 |
|------|---------|---------|---------|
| **domain_learned_orientation** | `tulpa_memory.db` 表 | ✅ 已實作，數據空 | 校正發生時自動加分/減分 |
| **domain_optimization** | `tulpa_memory.db` 表 | ✅ 有數據（2節點） | 每輪 compete 自動記錄 |
| **migration_log** | `tulpa_memory.db` 表 | ✅ 剛開始有數據 | weight 遷移記錄 |
| **observer_insights** | `tulpa_memory.db` 表 | ✅ 已實作，數據空 | self-audit 自動寫入 |
| **ontology** | `tulpa_memory.db` 表 | ✅ 12 rows | 輸入模式→tulpa 映射學習 |
| **object_facets** | `tulpa_memory.db` 表 | ✅ 4 rows | 物件→tulpa 視角記錄 |
| **keyword_stats** | `tulpa_memory.db` 表 | ✅ 80 rows | 關鍵字活躍度追蹤 |
| **domain_keyword_candidates** | `tulpa_memory.db` 表 | ✅ 實作，空 | 新詞觀察→核准→加入 |
| **context_text** | `tulpa_domain.py` 硬編碼 | ❌ 未動 | 需從校正數據學習更新 |
| **ALL_DOMAINS** | `tulpa_domain.py` 列表 | ❌ 只有房仲樹 | 可擴充多棵樹 |

### 閾值規則（證據閘門）

```
🟢 校正率 < 30%：
  自由輸出，不提醒

🟡 校正率 30%-60% 且 samples >= 3：
  注入【領域校正提醒】到 system prompt
  LLM 知道「這個話題過去有歷史」

🔴 校正率 > 60% 且 samples >= 5：
  注入【自我審計提醒】
  系統說「這個話題我過去幾次都說不準」
```

---

## 五、記憶類型（M0-M7）與溫度層

| 類型 | 內容 | 溫度 | 儲存位置 |
|------|------|------|---------|
| M0 憲法 | 身份、規則、紅線 | 🔥 熱層 | ARIS.md |
| M1 人物 | Ryan 偏好、習慣 | 🔥 暖層 | :11551/store |
| M2 工作 | 當前任務、卡點 | 🔥 熱層 | :11551/store |
| M3 情節 | 完整事件 | ❄️ 冷層 | :11551/store |
| M4 語義 | 穩定事實、概念 | ❄️ 暖層 | :11551/store |
| M5 因果 | X→Y 機制 | ❄️ 冷層 | :11551/store |
| M6 程序 | SOP、方法 | ❄️ 暖層 | :11551/store + skills |
| M7 反思 | 跨事件規律 | ❄️ 暖層 | :11551/store |

### 調用規則

```
需要「知道怎麼做」→ Skill（M6）
需要「碰外部世界」→ 工具（MCP/terminal）
需要「做完再看、看完再做」→ 循環（Loop）
需要「時間到了自動開始」→ 排程（Cron）
需要「事件發生立刻開始」→ 鉤子（Hook）
```

---

## 六、子系統埠口與健康檢查

| 服務 | 埠口 | 健康端點 | 注入方式 |
|------|------|---------|---------|
| Aris 認知橋接器 | 11547 | GET /health | pre_llm_call hook |
| 記憶服務 | 11551 | GET /health | pre_llm_call hook |
| 18428 tulpa 引擎 | 18428 | GET /health | pre_llm_call hook |
| Rust PSI 引擎 | — | latest.json 新鮮度 | pre_llm_call hook |

### 警報系統

```
╔═══════════════════════════════════════════════╗
║  ⚠️  SYSTEM ALERT                              ║
║  ──────────────────────────────────────────────║
║  ✓ 所有系統正常                                  ║
╚═══════════════════════════════════════════════╝

[11547] 離線 → 無認知上下文
[11551] 離線 → 無經驗記憶注入
[RUST] PSI 引擎過時 → 情緒調節失效
[18428] 離線 → 無領域視角/無自我審計
```

---

## 七、已知尚未收斂的缺口

| # | 缺口 | 優先級 | 阻礙 |
|---|------|--------|------|
| 1 | 做夢模組（記憶固化）Levenshtein 瓶頸 | 🟡 | 需改 Jaccard 或批次化 |
| 2 | 領域樹 context_text 硬寫死 | 🟡 | 等校正數據夠了再動 |
| 3 | 18428 launchd 註冊（自動重啟） | 🟢 | 手動啟動，重啟後消失 |
| 4 | 多重領域樹（不只房仲一棵） | 🟢 | 可慢慢養，不急著建 |
| 5 | Prime Agent 評估 | 🟢 | 排程靠後 |
| 6 | 來斯特九情緒表應用 | 🟢 | 排程靠後 |
| 7 | 人格模板抽換（4 套） | 🟢 | 尚在設計階段 |

---

## 八、這份文件怎麼用

```
新對話開始時：
  1. 讀這份文件 → 知道整個架構長什麼樣
  2. 查 18428 /health → 18428 活著嗎？
  3. 查 :11551 /health/detailed → 記憶庫狀態？
  4. 查 18428 /observer → 有自我審計提醒嗎？
  5. 查 domain_optimization → 哪個節點校正率高？

需要 debug 時：
  1. 套用 Ponytail 框架（第三章 3.1）
  2. 紅軍攻擊自己的方案（第三章 3.2）
  3. 跑驗證清單（第三章 3.3）

需要新增領域時：
  1. 在 tulpa_domain.py 加第二棵樹
  2. 定義 DOMAIN_ORIENTATION 映射
  3. 系統會自動從校正中學習

需要接入新記憶時：
  1. POST :11551/store（寫入）
  2. GET :11551/wake（讀取）
  3. τ 學習會自動強化有用記憶
```