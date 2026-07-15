# PSI Backend Contract v1

> 狀態：M0（契約定義）。本文件記錄的是「可驗證的邊界提案」——
> PsiBackend v1 是 proposed boundary，**不是已完成的程式碼**。
> 目前沒有任何非 Python backend 存在，也沒有 adapter。
> 可執行驗證：`tests/test_psi_schema.py`（schema 契約）+
> `tests/test_psi_contract.py`（characterization 快照）。

---

## 1. Scope / Non-goals

**Scope**

- 定義未來 PSI backend（如 Rust）必須滿足的可觀察行為邊界。
- 區分三種介面：公開 API（§4）、相容性表面（§12）、私有實作（不入契約）。
- 以 JSON Schema（Draft 2020-12）固定 state 輸出與 canonical input 形狀：
  - `docs/contracts/psi-state.schema.json`
  - `docs/contracts/psi-input.schema.json`
- 誠實記錄現有耦合：**目前不能直接替換 backend**（§3、§12）。

**Non-goals（本版不做）**

- 不寫 Rust、不寫 adapter、不寫 backend factory（M1–M4 的事）。
- 不修 KNOWN-ISSUE-1（`AttentionFocus.SOCIAL`）與 KNOWN-ISSUE-2（`stop()` 不 join）。
- 不宣稱任何效能數字（無 benchmark 不談效能，CLAUDE.md 規則 5）。
- 不宣稱 Rust 與 Python 相容——沒有 Rust backend，無從相容。
- characterization tests 是行為快照，**不是完整正式規格**；本契約以它為
  基線，但規格判斷以本文件為準。

## 2. Python reference implementation

參考實作：`laap/psi_core.py`（基準 commit `129a711` + Gate 0 測試修正）。

組成：

| 元件 | 檔案 | 角色 |
|---|---|---|
| `PsiCore` | `laap/psi_core.py` | 門面：生命週期、輸入處理、狀態輸出、bus 同步 |
| `NeedDriveSystem` | `laap/psi_core.py` | 五維需求：值/目標/靜息值/衰減/雜訊/重要性 |
| `EmotionGradient` | `laap/psi_core.py` | valence/arousal/dominance + 內啡肽緩釋 |
| `AffectiveState` | `laap/affective.py` | 5 維情緒引擎（PAD+Social+Stress），numpy |
| constitution | `laap/constitution.py` | `satisfy` 的邊界/單次上限/來源預算 guard |
| `CognitiveBus` | `laap/agi/cognitive_bus.py` | 事件總線；PsiCore 每 tick 同步狀態進去 |

行為基線由 `tests/test_psi_contract.py` 鎖定（69 passed + 2 strict xfailed）。

## 3. Call-site inventory

全 repo PSI 使用點（`rg` 掃描 laap/、scripts/、tests/、根目錄模組）。
層級：**A** = 公開 API、**B** = 相容性表面（直接摸內部物件）、**C** = 私有。

| 檔案 | 存取 | 層級 |
|---|---|---|
| `laap/startup.py` | `PsiCore(bus, interval=1.0)`、`psi.start()` | A |
| `laap/chatflow.py` `_feed` | `get_state()` ×2、`process_input(text)` | A |
| `laap/chatflow.py` `_psi_respond`/`_tool_chat` | `get_state()` | A |
| `laap/chatflow.py` `_post_tool_outcomes` | `psi.affective.post_event()` | **B** |
| `laap/status.py` `snapshot()` | `get_state()`；`getattr(psi, "last_input")` | A + **B** |
| `laap/agency.py` | `psi.needs.get_drives()`、`psi.needs.satisfy_all(..., source="agency")`、`psi.emotion.arousal`、`psi.emotion.to_dict()`、`psi.affective.compute_cognitive_bias()`、`psi.affective.post_event()`、`psi.last_input` | **B**（最重耦合點） |
| `laap/consolidation.py` `_asleep` | `psi.emotion.to_dict()["arousal"]` | **B** |
| `memory_bridge.py` `_feed_psi` | `process_input(text)` | A |
| `memory_store.py` `emotion_intensity` | `psi.emotion.to_dict()` | **B** |
| `laap/llm_respond.py`、`laap/psi_response.py` | 消費 `get_state()` 回傳的 dict（由 caller 傳入，不直接摸 psi 物件） | A（間接） |
| `scripts/start.sh`（inline python） | `get_state()` | A |
| `scripts/check-agency.py`、`check-agency-intent.py`、`check-chatflow.py`、`check-constitution.py` | `psi.needs.values` 直接寫、`psi.last_input` 直接寫 | **B**（測試 harness） |
| `scripts/check-affective.py` | `psi.affective.update(dt)` | **B**（測試 harness） |
| `tests/test_psi_contract.py` | `psi.needs.values`/`satisfy`、`psi.last_input`（B）；`_thread`/`_running`/`_tick_count`（C，明文標註為 private observation point） | **B** + C |

**核心判斷：backend 目前不可替換。** AgencyLoop、ConsolidationLoop、
StatusWriter、memory_store、chatflow 的工具結果路徑、全部 check scripts
都直接存取 `psi.needs` / `psi.emotion` / `psi.affective` / `psi.last_input`
內部物件。把 PsiCore 換成任何不暴露這些 Python 物件的實作，上述模組立即
壞掉。這個耦合是事實，契約如實記錄；解耦是 M2 的工作（§15）。

事實澄清（避免常見誤讀）：

- `process_input()` 的 production 呼叫端是 **chatflow 與
  memory_bridge**；**AgencyLoop 不呼叫 `process_input()`**——它直接
  使用 `needs`/`emotion`/`affective`/`last_input`，是 B 類耦合的
  最大風險點。
- **status.py 對 PsiCore 只用 `get_state()` + `last_input`**
  （A + B），不碰 PsiCore 的 private thread 欄位。
  `_thread`/`_running`/`_tick_count` 的直接存取主要在 tests
  （已標註 private observation point）。status.py 另有對 AgencyLoop /
  ConsolidationLoop private 成員的存取（`_effective_interval`、
  `_action_ts` 等），但那些不屬於 PsiBackend v1 的邊界。

## 4. Observed Python API（現有公開行為）

| 方法 | 簽名 | 觀察到的語意 |
|---|---|---|
| `start()` | `() -> None` | 冪等；起 daemon 心跳執行緒 |
| `stop()` | `() -> None` | 只設 flag，**不 join**（KNOWN-ISSUE-2） |
| `process_input(text)` | `(str) -> None` | 關鍵詞需求偵測 + relatedness +0.02 + affective 事件 + 情緒/注意力更新 + bus 事件；relatedness 主導時拋 AttributeError（KNOWN-ISSUE-1） |
| `get_state()` | `() -> dict` | 見 §6；JSON-serializable |
| `get_dominant_need()` | `() -> str` | 五需求名或 `"none"` |
| `get_state_label()` | `() -> str` | 調性標籤，如 `"humble.learning"` |
| `format_state_injection()` | `() -> dict` | `{state_label, state_snippet, state_tuple}` |
| `__repr__()` | `() -> str` | `<PsiCore dominant=... drive=... valence=...>` |

## 5. Proposed PsiBackend v1 API

最小契約。原則：backend 只暴露數值/狀態表面，不暴露 Python 類別
（`NeedDriveSystem` / `EmotionGradient` / `AffectiveState` 不得出現在
backend 邊界上）。

```
start() -> None
stop() -> None
process_input(text: str, source: str = "user") -> None
get_state() -> mapping                      # 符合 psi-state.schema.json
get_dominant_need() -> str
get_drives() -> mapping[str, float]         # {need_name: drive}
satisfy(need: str, amount: float, source: str) -> None
post_affective_event(event: str, intensity: float = 1.0) -> bool
get_cognitive_bias() -> mapping[str, float]
get_last_input() -> str
```

簽名注記（依可觀察行為最小化）：

- **`start()` 不帶參數。** `interval` 是建構子配置
  （`PsiCore(bus, interval=...)`），不是 `start()` 的參數。
- **`stop()` 不帶 `timeout_s`。** 現有 `PsiCore.stop() -> None`，
  沒有任何 production caller 傳 timeout；KNOWN-ISSUE-2 是「不 join」，
  不是「缺 timeout 參數」。M5 修復可以在不改簽名下讓 `stop()` 返回前
  完成 bounded join；若未來真有 caller-controlled timeout 的 call-site
  需求，再升契約版本。不提前加沒有 call-site 的參數。
- **`process_input` 的 `source` 是 provenance 標記，不是 constitution
  key。** 四層區分：
  1. canonical event envelope（`psi-input.schema.json`）帶 `source`；
  2. 現有 Python method `PsiCore.process_input(text: str)` **沒有**
     `source`/`metadata` 參數，無法接收或轉送它；
  3. 未來 backend method 可接受 `source`，但 M1 零行為 wrapper
     不得假裝 `source` 已影響 constitution；
  4. 具有已觀察到 constitution per-source 預算語意的，只有
     `satisfy(need, amount, source)`（→ `NeedDriveSystem.satisfy` →
     `constitution.guard_need`）。
  不得宣稱 `process_input` 的 `source` 已是 constitution budget key；
  也不為此修改 production code。
- **`post_affective_event` 回傳 `bool` 是可觀察契約。** 現有
  `AffectiveState.post_event()`：已知事件成功排入 queue → `True`；
  未知事件 → `False`。adapter 必須原樣轉回此結果，不得吞掉 `False`
  或改成 `None`。

現有 B 表面 → v1 方法對應：

| 現有存取（B） | v1 對應 | 呼叫端 |
|---|---|---|
| `psi.needs.get_drives()` | `get_drives()` | agency |
| `psi.needs.satisfy()` / `satisfy_all()` | `satisfy()`（批次由 adapter 迴圈） | agency、psi_core 內部 |
| `psi.emotion.arousal`、`psi.emotion.to_dict()` | `get_state()["emotion"]` | agency、consolidation、memory_store |
| `psi.affective.post_event()` | `post_affective_event()` | agency、chatflow |
| `psi.affective.compute_cognitive_bias()` | `get_cognitive_bias()` | agency |
| `psi.last_input` 讀 | `get_last_input()` | agency、status |
| `psi.needs.values` 直接寫 | 不入契約——check scripts/tests 專用；M2 改走 `satisfy()` 或 test-only seam | scripts、tests |

**`get_state_label()` / `format_state_injection()` 的歸屬判斷：
adapter / presentation layer，不是 backend 必要能力。**

理由：

1. 兩者是 `get_state()` 輸出的純函式——label 需要 dominant need + valence
   正負，injection 需要整份 state dict，全部可從快照推導，不需要額外的
   backend 狀態存取。
2. 它們是英文模板字串（`"I'm feeling ..."`、`"humble.learning"`），
   迭代節奏跟產品文案走，不跟 backend 走。塞進 Rust 意味著改一句文案要
   重編譯 backend，並要求跨語言 f-string 格式化逐字元相等——沒有價值的
   相容性負擔。
3. 微妙處（誠實記錄）：Python 的 `get_state_label()` 用的是
   `self.emotion.valence`（平滑原始值，= state dict 的 `raw_valence`），
   而 `format_state_injection()` 用 state dict 的 `valence`
   （內啡肽緩釋值）。兩個方法走不同 valence 通道。Adapter 從快照重算
   label 時必須用 `emotion.raw_valence`，不是 `emotion.valence`。
4. **M1 不得動這兩個方法的行為。** M1 是零行為 compatibility adapter：
   `get_state_label()` / `format_state_injection()` 原樣委派給
   `PsiCore` 同名方法——保留 QUIRK-1（label 用 raw valence、injection
   用 endorphin valence）、不從單一快照重新計算、不改文案、不修通道
   差異。parity tests 必須驗證 adapter 與直呼 `PsiCore` 完全一致。
   若要統一 valence 通道：另立 behavioral change 任務，先定 desired
   behavior、更新 characterization tests——不屬於 M1。
5. `__repr__()` 是 Python debug convenience，不進 backend contract。

## 6. State contract

正式形狀見 `docs/contracts/psi-state.schema.json`。語意補充：

- `needs`：五個名稱固定——`certainty`、`competence`、`autonomy`、
  `relatedness`、`growth`，且為 **closed set**
  （`additionalProperties: false`，第六需求名會被 validator 拒絕；
  增刪改名 = breaking，見 §13）。每項 `current`/`target` ∈ [0,1]、
  `drive = max(0, target - current) × importance ≥ 0`；needEntry 內部
  新增欄位屬 non-breaking。
- `dominant_need`：drive 最高者；平手時依宣告序
  certainty > competence > autonomy > relatedness > growth
  （characterized 行為，記錄非強制）。
- `emotion`：`valence`（內啡肽緩釋回報值）、`raw_valence`（平滑原始值）
  ∈ [-1,1]；`arousal`、`dominance` ∈ [0,1]。
- `attention`：目前合法值只有 `IDLE`、`TASK`、`LEARNING`、`PLANNING`。
  對應：competence→TASK、growth→LEARNING、certainty→PLANNING、
  autonomy/none→IDLE。relatedness 的分支引用不存在的 `SOCIAL`
  （KNOWN-ISSUE-1）——**`SOCIAL` 不是 v1 合法值**，schema 會拒絕它。
- `tick`：整數 ≥ 0；未 `start()` 時為 0。
- `affective`：選填，相容性輸出（§12）。
- `schema_version` / `backend` / `timestamp`：選填的前向欄位；目前
  Python 實作不輸出，未來 backend 應輸出。
- 小數位：Python 把數值 round 到 3 位。這是實作細節，契約只要求範圍
  正確；消費端不得依賴精確小數位。

## 7. Input contract

正式形狀見 `docs/contracts/psi-input.schema.json`。

- 必填 `text: string`（空字串合法，characterized：不 crash）。
- 選填 `schema_version`（const `"1"`）、`source`（provenance 標記，
  預設語意 `"user"`；**不是** constitution 預算 key——見 §5 四層區分，
  constitution 語意只存在於 `satisfy(..., source)`）、`timestamp`
  （**Unix seconds**，UTC，可含小數；v1 明確不收 RFC3339——選 Unix
  seconds 是因為整個 codebase 都用 `time.time()`）、`metadata`
  （JSON object，值可為任意 JSON-compatible value；backend 不得依賴
  特定 key 才能運作）。
- **現況誠實聲明**：目前 Python 只接受 `process_input(text: str)`——
  沒有 `source`、沒有 `metadata`，無法接收或轉送這些欄位。canonical
  input object（event envelope）由未來 adapter 負責組裝與拆解；目前
  沒有任何程式碼直接接受這個 JSON object，M1 零行為 wrapper 也不會
  讓 `source` 影響 constitution。
- 處理語意（v1 backend 必須重現）：關鍵詞需求偵測（`NEED_KEYWORDS`
  substring 比對，單需求增量 `min(0.15, 匹配數 × 0.03)`）、無條件
  relatedness +0.02、affective `user_engagement` 事件（intensity 0.5）、
  情緒更新、注意力更新。bus 事件發布屬 Python 端整合，不是 backend
  必要能力（adapter 負責）。

## 8. Lifecycle semantics

- `start()`：冪等（重複呼叫 no-op）。啟動心跳：每 `interval` 秒執行
  needs 鬆弛（valence 調節 decay：>0.3 → ×0.7，<-0.3 → ×1.3）→
  emotion 更新 → affective 更新 → 注意力更新 → bus 同步。單次 tick
  例外吞掉並 log，心跳不得因此停止（「停跳 = 靜默腦死」）。
- `stop()`：v1 只要求「發出停止訊號」。現行 Python `stop()` 只設 flag
  不 join（KNOWN-ISSUE-2）——**不保證返回時 worker 已終止**；執行緒在
  下一次 `sleep(interval)` 醒來後退出。M5 修復後，`stop()` 可在不改
  簽名下於返回前完成 bounded join；caller-controlled timeout 若未來
  真有 call-site 需求，屬契約升版。`stop()` 先於 `start()` 呼叫 =
  no-op，不得拋錯。
- stop → start 快速重啟：現行 Python 可能短暫雙心跳（KNOWN-ISSUE-2 的
  後果）。v1 backend 在 M5 後不得雙心跳。

## 9. Clock / RNG semantics

- 時鐘：心跳用 wall-clock `sleep(interval)`；`dt = interval` 是約定值，
  不是實測經過時間。backend 可用更精確的排程，但 `dt` 語意必須相同。
- RNG 兩處：
  1. needs 雜訊：`random.gauss(0, volatility × dt)`（Python 全域 RNG，
     測試靠 monkeypatch 歸零）。
  2. affective 1/f 粉紅噪聲：未播種的 numpy `default_rng`。
- **跨 backend 不要求 bit-identical 隨機流。** 等價性驗證一律在
  零噪聲配置下進行。但零噪聲的取得方式兩處不對稱（誠實記錄）：
  - affective 有正式配置旋鈕：`PersonalityProfile(noise_amplitude=0.0)`。
  - needs 的 `random.gauss` **沒有**配置旋鈕——現行測試靠 monkeypatch
    Python 全域 `random.gauss` 歸零（conftest 做法）。這在跨語言
    backend 上不可行；v1 backend MUST 提供正式的零噪聲/RNG 注入點，
    Python 參考實作的注入點是未來工作（不在 M0/M1 動 production）。
  - clock 同樣沒有正式注入點（心跳直接 `time.sleep(interval)`）；
    backend 的 conformance 測試需以固定 `dt` 腳本驅動，而非實時心跳。

## 10. Thread-safety expectations

- 所有 v1 方法必須可從任意執行緒併發呼叫，且與心跳併發安全。
- 現行 Python 用子系統各自的鎖（`NeedDriveSystem`/`EmotionGradient`
  RLock、`AffectiveState` Lock），**沒有全域快照鎖**——`get_state()`
  的各欄位可能取自略有時差的瞬間，不是原子快照。v1 沿用此弱保證
  （composite read，欄位各自一致）；要求原子快照屬未來加強，不在 v1。
- 可執行驗證：`tests/test_psi_contract.py::TestThreadSafety::`
  `test_concurrent_read_write`——Gate 0 之後它會真正斷言 reader 執行緒
  已停、錯誤清單為空（修正前收集了錯誤卻從不斷言，錯誤靜默通過）。

## 11. Error handling

- `get_state()` / `get_dominant_need()` / `get_drives()` /
  `get_cognitive_bias()` / `get_last_input()`：正常運作下不得拋錯。
- `process_input()`：現行 Python 在 relatedness 主導時拋
  `AttributeError`（KNOWN-ISSUE-1）；production 呼叫端（chatflow）
  以 try/except 吞掉 → psi feed 靜默失效。M5 修復後不得對任意文字拋錯。
- `post_affective_event()`：未知事件名——現行 Python 回 `False` 不拋錯；
  v1 沿用：回傳 `bool`（已知事件排入 queue → `True`、未知 → `False`）
  是可觀察契約，不得吞掉 `False` 或改回 `None`（§5）。
- `satisfy()`：未知需求名是呼叫端錯誤，backend 應拋明確錯誤
  （Python `NeedType(name)` 拋 `ValueError`），不得靜默寫錯需求。
- 心跳內部錯誤：吞掉 + log（§8），不得讓心跳死掉，也不得污染狀態範圍
  （needs 永遠 clamp [0,1]）。

## 12. Backward compatibility

現有相容性表面（B）——**過渡期必須繼續可用，但不得寫進永久 backend API**：

- `psi.needs.get_drives()`、`psi.needs.satisfy()` / `satisfy_all()`、
  `psi.needs.values`（check scripts 直接寫）
- `psi.emotion.arousal`、`psi.emotion.to_dict()`
- `psi.affective.compute_cognitive_bias()`、`psi.affective.post_event()`、
  `psi.affective.update()`（check-affective 直接呼叫）
- `psi.last_input`（agency/status 讀、check scripts 寫）
- `psi.attention_focus`（psi_core 內部；外部消費走 `get_state()["attention"]`）

規則：M1 的 Python adapter 必須原樣保留這些屬性（直接代理到既有物件），
M2 逐一把呼叫端遷到 §5 的 v1 方法。過渡期間**不得新增**對 B 表面的依賴。
私有成員（`_thread`、`_running`、`_tick_count`、`_heartbeat()` 等底線
開頭）不屬於任何契約層；`tests/test_psi_contract.py` 對 `_tick_count` 的
觀察已明文標註為 private observation point，不構成 API 承諾。

## 13. Versioning

- 本契約與兩份 schema 同步版號：目前 `1`（schema `$id`
  `urn:neuralis:contracts:psi-{state,input}:1`，`schema_version` const `"1"`）。
- **非破壞性（不升版）**：state root 新增選填欄位（root
  `additionalProperties: true` 已預留）；needEntry / emotion 內部新增
  欄位；input 新增 `metadata` 內容。
- **破壞性（升 v2，新 schema 檔）**：**新增、刪除、重新命名 need key**
  （`needs` 是 closed schema，`additionalProperties: false`，第六需求
  會被 v1 validator 拒絕——這是刻意的）、改數值範圍、改必填集合、
  `attention` enum 增減值（含未來把 SOCIAL/相容值加入）、
  input top-level 新增欄位（input 也是 closed schema，top-level 加欄位
  = 舊 validator 拒絕新輸入）。
- 版本歷史記在本檔；schema 檔一版一檔，不原地改語意。

## 14. Known issues

| 編號 | 內容 | 鎖定測試 | 修復點 |
|---|---|---|---|
| KNOWN-ISSUE-1 | relatedness 主導時 `_update_attention` 引用不存在的 `AttentionFocus.SOCIAL` → `process_input` 拋 AttributeError；production 被 chatflow try/except 吞掉 = psi feed 靜默失效 | `test_relatedness_does_not_crash`（strict xfail） | M5 |
| KNOWN-ISSUE-2 | `PsiCore.stop()` 不 join 心跳執行緒；快速 stop→start 可能短暫雙心跳 | `test_stop_joins_thread`（strict xfail） | M5 |
| Gate 0（已修） | `test_concurrent_read_write` 收集 errors 但從不斷言 → 併發錯誤靜默通過 | 本 branch Commit A 已補斷言 | 已修 |
| QUIRK-1（記錄） | `get_state_label()` 用 raw valence、`format_state_injection()` 用內啡肽 valence——兩方法 valence 通道不同（§5 理由 3） | 無（行為記錄） | 不修；M1 必須原樣保留（§5 理由 4）；統一通道屬另立 behavioral change 任務 |
| QUIRK-2（記錄） | `get_state()` 非原子快照（§10） | 無 | v1 接受此弱保證 |

## 15. Migration sequence

- **M0（本任務，已完成）**：本契約 + 兩份 JSON Schema +
  `tests/test_psi_schema.py` 可執行契約測試 + call-site inventory。
- **M1**：新增 Python `PsiBackend` adapter（包住現有 `PsiCore`），
  **零行為改變**：十個 v1 方法全委派；B 表面原樣代理；
  `get_state_label()` / `format_state_injection()` 原樣委派、保留
  QUIRK-1、不從快照重算、不改文案；`source` 只做 provenance 記錄，
  不接 constitution；parity tests 驗證 adapter 與直呼 `PsiCore`
  完全一致。
- **M2**：Agency / Consolidation / Status / memory_store /
  chatflow `_post_tool_outcomes` 改走 §5 v1 方法，不再直接存取
  `needs` / `emotion` / `affective` 內部物件。
- **M3**：backend factory——`NEURALIS_PSI_BACKEND=python|rust`。
- **M4**：Rust backend。先過語意相容（§16 gates），再談效能
  （沒 benchmark 不宣稱數字）。
- **M5**：修 KNOWN-ISSUE-1、KNOWN-ISSUE-2；把對應 strict xfail 轉正式
  passing tests；重新檢視 `attention` enum 的版本策略（§13）。

M1–M5 全部尚未開始。

## 16. Rust backend acceptance gates

Rust（或任何非 Python）backend 合格條件，全部可機器驗證：

- **G1 — State schema 合規**：初始狀態、任意輸入序列後、任意 tick 數後
  的 `get_state()` 輸出全部通過 `psi-state.schema.json` 驗證。
- **G2 — 零噪聲語意等價**：零噪聲配置（§9）下，對同一腳本化輸入序列
  （固定 `dt`、固定 satisfy/事件序列），needs/drive/emotion 軌跡與
  Python 參考實作逐步一致（建議容差 |Δ| ≤ 1e-6；公式相同、IEEE-754
  double 下通常可到 1e-9，容差最終在 M4 定案並寫進 conformance 測試）。
- **G3 — Lifecycle**：`start()` 冪等（`interval` 是建構配置，不是
  `start()` 參數）；`stop()` 發出停止訊號且不拋錯（M5 後：返回前完成
  bounded join、stop→start 無雙心跳）；stop-before-start 不拋錯。
- **G4 — 併發**：`test_concurrent_read_write` 的移植版在 Rust backend
  上跑，零錯誤（reader 全程讀到五需求齊全、範圍合法的 state）。
- **G5 — Characterization 套件**：`tests/test_psi_contract.py` 經
  adapter 對 Rust backend 執行，結果與 Python 基線一致
  （M5 前：69 passed + 2 strict xfailed；M5 後：xfail 轉 passed）。
- **G6 — Input contract**：接受 `psi-input.schema.json` 合法 object、
  拒絕非法 object；`text`-only 與 full-field 輸入語意一致。
- **G7 — 效能另立門**：任何效能宣稱必須附可重現 benchmark
  （CLAUDE.md 規則 5）；語意 gates（G1–G6）全過之前不進行效能比較。

---

*版本歷史：v1 — 2026-07-15，F5-004 / M0 初版。*
