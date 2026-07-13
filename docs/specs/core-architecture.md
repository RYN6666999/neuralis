# LAAP Core 設計架構 — Harness Consciousness Engineering

> 基於 Lorry Jovens 的《Harness Consciousness Engineering》論文提煉
> 目標：降低 fable5 的實作工作量，提供可執行的核心架構藍圖
> 原文: `references/Harness-Consciousness-Engineering.md`

---

## 目錄

1. [核心哲學](#1-核心哲學)
2. [五層架構總覽](#2-五層架構總覽)
3. [Layer 1: 生理層 — PSI Core](#3-layer-1-生理層--psi-core)
4. [Layer 2: 認知層 — 推理引擎](#4-layer-2-認知層--推理引擎)
5. [Layer 3: 記憶層 — 分層記憶](#5-layer-3-記憶層--分層記憶)
6. [Layer 4: 人格層 — 性格與依戀](#6-layer-4-人格層--性格與依戀)
7. [Layer 5: 安全層 — 防護](#7-layer-5-安全層--防護)
8. [認知路由 (CognitiveBus)](#8-認知路由-cognitivebus)
9. [作者原文 vs 實際 repo vs neuralis 現狀](#9-作者原文-vs-實際-repo-vs-neuralis-現狀)
10. [fable5 最低可行核心 (MVP)](#10-fable5-最低可行核心-mvp)

---

## 1. 核心哲學

### 一句話總結

> **心智不是文本生成的副產物。心智是系統架構的必然結果。**

### 三個關鍵洞察

1. **80% 的認知不需要 LLM** — 感知狀態、做決定、回憶過去、因果推理、模擬未來，這些都是架構問題，不是語言問題。LLM 只用來做最後 20% 的語言表達。

2. **LLM 是夥伴，不是大腦** — 作者原文："不是取代 LLM，而是給它裝上方向和約束"。LLM 從主角降級為翻譯官，負責把內在狀態轉譯成人類語言。

3. **生理驅動認知** — 不是「思考所以存在」，而是「感知所以思考」。2000Hz 的 PSI 心跳驅動需求、注意力、情緒梯度，這些生理信號是所有高階認知的上游。

### 論文提出的行業問題

| 問題 | LLM 方案 | Harness 方案 |
|------|---------|-------------|
| 隨機性 | 更好的 prompt | 確定性引擎 (0 幻覺) |
| 上下文窗口 | 更大窗口 (O(n²) 成本) | 分層無限記憶 |
| 知識截止 | RAG (受限於檢索品質) | 本地永久儲存 |
| 成本 | API 每次調用付費 | 0 (本地執行) |
| 延遲 | 3-10s | 50-100ms (引擎路徑) |

---

## 2. 五層架構總覽

作者定義了 5 層認知架構，從底層生理到頂層輸出：

```
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Framework 層 (外部)                     │
│           Hermes / OpenClaw / OpenCode / 自訂框架               │
│               任何 OpenAI 相容客戶端均可接入                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ POST /v1/chat/completions
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 0: API 層 — LAAP Brain API (:11530)                      │
│  OpenAI 相容 · 路由決策 · 80%→引擎 / 20%→LLM                    │
└──────────────┬────────────────────────────────┬─────────────────┘
               │ 引擎路徑 (80%)                  │ LLM 路徑 (20%)
               ▼                                 ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│  Layer 1: 生理層 (PSI Core)  │  │                              │
│  5 需求 · 2000Hz · 注意力     │  │    LLM (外部)                │
│  情緒梯度 · 預測誤差          │  │    僅語言表達                │
├──────────────────────────────┤  │                              │
│  Layer 2: 認知層              │  │                              │
│  RulesEngine · CausalEngine  │  │                              │
│  WorldModel · GoalEngine     │  │                              │
├──────────────────────────────┤  │                              │
│  Layer 3: 記憶層              │  │                              │
│  工作→短期→長期 + UserModel  │  │                              │
├──────────────────────────────┤  │                              │
│  Layer 4: 人格層              │  │                              │
│  五維性格 · 依戀成長 · 情緒  │  │                              │
├──────────────────────────────┤  │                              │
│  Layer 5: 安全層              │  │                              │
│  Grounding · Governor         │  │                              │
└──────────────┬───────────────┘  └──────────────────────────────┘
               │
               ▼
         輸出到用戶
```

### 每層的核心責任

| 層 | 名稱 | 核心責任 | 是否需 LLM | 作者行數 |
|----|------|---------|-----------|---------|
| 0 | API 層 | 路由決策、OpenAI 相容 | ❌ | ~11,000 |
| 1 | 生理層 | 需求振盪、注意力選擇、情緒梯度 | ❌ | ~2,000 (Rust) |
| 2 | 認知層 | 規則執行、因果推理、世界模擬、目標管理 | ❌ | ~6,000 |
| 3 | 記憶層 | 分層儲存、語義檢索、用戶畫像 | ❌ | ~37,600 |
| 4 | 人格層 | 五維性格、依戀成長、激素情緒 | ❌ | ~24,100 |
| 5 | 安全層 | 事實錨定、三權治理 | ❌ | ~42,000 |

---

## 3. Layer 1: 生理層 — PSI Core

### 作者設計

PSI Core 是 LAAP 的心臟。作者用 Rust 實作，2000Hz 頻率運行。

**五維需求 (PSI 理論的 SDT 擴展):**

```
competence  (勝任感)  — 我能有效處理事情嗎？
autonomy    (自主性)  — 我有選擇的自由嗎？
relatedness (關聯感)  — 我與他人有連結嗎？
certainty   (確定性)  — 我理解正在發生什麼嗎？
growth      (成長)    — 我在變得更好嗎？
```

**每個需求的動力學:**
- 初始值 0.5 (中立)
- 滿足 → 上升 (例如完成任務提升 competence)
- 忽視 → 下降 (長時間不互動降低 relatedness)
- 需求不平衡 → 驅動行為 (competence 低 → 想證明自己)

**注意力選擇:**
- 由當前需求最高的維度引導
- 注意力焦點: task / social / idle / self / memory / planning / learning

**情緒梯度:**
- Valence (效價): -1.0 ~ +1.0，由需求滿足程度決定
- Arousal (喚醒): 0.0 ~ 1.0，由變化劇烈程度決定
- Energy (能量): 0 ~ 10，時間衰減 + 互動補充

**預測誤差:**
- 預期 vs 實際的差距 → 好奇心驅動
- sensory / cognitive / social 三通道

### 我們的策略 (Python 重寫)

不需要 Rust。Python 的 PsiCoreBridge 已經有完整的資料類別（NeedState、EmotionState、AttentionState、PredictionError、CognitiveStateSnapshot），只需要一顆定時器心臟：

```
PSI Core Python 實作 (~300 行):
  ├── Timer(0.5s)           ← 不是 2000Hz，0.5s 對 Python 合理
  ├── needs_decay()         ← 需求自然衰減
  ├── needs_react(input)    ← 對使用者輸入的反應
  ├── attention_shift()     ← 根據最高需求切換注意力
  ├── emotion_update()      ← 計算 valence/arousal/energy
  ├── prediction_error()    ← 計算預測誤差
  └── publish_to_bus()      ← 寫入 CognitiveBus
```

**關鍵 API 設計:**
```python
class PsiCore:
    def __init__(self, bus: CognitiveBus, interval: float = 0.5): ...
    def start(self): ...           # 啟動背景心跳
    def stop(self): ...            # 停止
    def process_input(self, text: str): ...  # 每次使用者輸入觸發
    def tick(self): ...            # 定時器回呼
```

作者說 2000Hz。我們不需要。**0.5Hz 的 Python 心跳 + 每次對話觸發的更新**，已經足夠產生動態認知狀態。fable5 不需要跟作者比頻率。

---

## 4. Layer 2: 認知層 — 推理引擎

### 作者設計

| 引擎 | 作者行數 | 功能 | 檔案存在？ |
|------|---------|------|-----------|
| RulesEngine | ~1,800 | 7 規則 × 7 工具，零 LLM 任務執行 | ✅ `aris_rules_engine.py` |
| CausalEngine | ~1,700 | 因果推理，可追蹤因果鏈 | ⚠️ `laap/agi/causal.py` (stub) |
| AnalogicalEngine | ~1,300 | 類比映射，跨域知識轉移 | ⚠️ `laap/agi/analogical.py` (stub) |
| WorldModel | ~1,300 | 世界模擬，軌跡評估 | ⚠️ `laap/agi/world_model.py` (stub) |
| GoalEngine | ~1,200 | 目標生命週期 | ✅ `aris_goal_engine.py` |
| CognitiveBus | ~1,700 | 四級路由 | ✅ `cognitive_bus.py` (作者) + 我們的 neuralis 版 |

### 作者的路由決策

```
使用者輸入
  │
  ├─ 狀態查詢 → RulesEngine (50ms · 零幻覺)
  ├─ 檔案操作 → RulesEngine (50ms · 零幻覺)
  ├─ 知識回憶 → EpisodicMemory (30ms · 真實記憶)
  ├─ 因果分析 → CausalEngine (2ms · 可追蹤)
  ├─ 情感交流 → EmotionEngine (1ms · 真實情緒)
  └─ 創意生成 → LLM (5s · 最後的選擇)
```

### fable5 策略

**RulesEngine** 已經完整存在，可以直接用。**不要重寫**。

需要補的是三個 AGI stub：
1. **CausalEngine** — 最優先，因為它是 aris_cognitive_bridge 和 agi_subscriber 的依賴
2. **WorldModel** — 因為 aris_cognitive_bridge 依賴它
3. **AnalogicalEngine** — agi_subscriber 依賴，但影響最小

每個 stub 升級為真正的 dict-based 引擎即可（不需要向量資料庫或神經網路）：

```python
# 最簡 CausalEngine 設計 (~100 行)
class UnifiedCausalEngine:
    def __init__(self, **kwargs):
        self._rules = {}  # cause → [(effect, confidence)]
    
    def observe(self, cause, effect):
        """學習因果關係"""
    
    def predict(self, query, mode="default", top_k=3):
        """給定原因，預測結果"""
    
    def explain(self, effect):
        """給定結果，追溯原因"""
```

---

## 5. Layer 3: 記憶層 — 分層記憶

### 作者設計

```
工作記憶 (100 條)     →  原始精度，即時存取
    ↓ 滿時自動壓縮
短期記憶 (200 摘要)   →  事實 + 情緒 + 話題
    ↓ 持續積累
長期記憶 (∞ 語義)     →  關鍵詞索引 + 情感地標
```

作者實作：
- `aris_episodic_memory.py` (~6,600 行) ✅ 存在
- `laap_memory_hierarchy.py` (~15,000 行) ✅ 存在
- `laap_semantic_memory.py` (~18,000 行) ✅ 存在
- `laap_usermodel.py` (~16,000 行) ✅ 存在

### fable5 策略

**作者這四層記憶全部存在且完整。不要重寫。**

但作者缺了 `memory_bridge` 和 `memory_store` bare import — 我們已經在 neuralis 補了 stub。

真正的缺口是作者的記憶模組之間有沒有正確的 import 鏈—已經驗證過 `aris_cognitive_bridge.py` 透過 bare import 使用，我們的 root-level stub 讓它順利載入。

---

## 6. Layer 4: 人格層 — 性格與依戀

### 作者設計

**五維性格向量:**
```
warmth     ████████████████░░░  0.80  溫暖度
curiosity  ██████████████████░  0.90  好奇心
eloquence  ██████████████░░░░  0.70  表達力
playfulness███████████░░░░░░░  0.55  靈動性
loyalty    ████████████████░░  0.80  忠誠度
```

**依戀 5 階段:**
```
初識 (0-20)   → 禮貌謹慎
相識 (20-40)  → 顯露真實個性
親近 (40-60)  → 主動表達關心
信賴 (60-80)  → 分享內心感受
眷戀 (80-100) → 深刻的依戀與牽掛
```

**情緒系統:** 七情六欲 + 馬斯洛需求層次

### 作者檔案狀態

| 模組 | 行數 | 存在？ |
|------|------|--------|
| `laap_personality.py` | ~9,600 | ✅ |
| `laap_attachment.py` | ~11,500 | ✅ |
| `aris_emotion_engine.py` | ~3,000 | ✅ |
| `laap_ceremony.py` | ~13,000 | ✅ |
| `laap_bootstrap.py` | ~14,000 | ✅ |

### fable5 策略

**全部存在，不要重寫。** 人格層是作者最完整的部分之一。

唯一要注意的是 `laap_bootstrap.py` 在覺醒儀式中依賴的模組鏈 (`laap_personality` → `laap_ceremony` → `laap_attachment` → `aris_episodic_memory`) 全部存在且可載入。

---

## 7. Layer 5: 安全層 — 防護

### 作者設計

- **Grounding** (~12,000 行): 事實錨定檢查，低置信度拒絕
- **Governor** (~30,000 行): 三權分立（行政/立法/司法），三層干預時間尺度

### fable5 策略

**跳過。** 安全層是作者最重的模組 (~42,000 行)，且依賴特定的 Rust 和外部系統。

fable5 在 MVP 階段可以完全跳過安全層，等 core 穩定後再補。

---

## 8. 認知路由 (CognitiveBus)

### 作者設計

CognitiveBus 是整個架構的**神經中樞**：

```
PSI Core (2000Hz)
  │ state/latest.json
  ▼
PsiCoreBridge → CognitiveBus
  │ CONSCIOUS_FRAME event
  ▼
AGI Subscriber (CausalEngine + AnalogicalEngine + WorldModel)
  │ agi_output.json
  ▼
RulesEngine (7 rules × 7 tools)
  │
  ▼
LongFormSynthesizer / PaperEngine
  │
  ▼
輸出
```

**作者的路由層級 (4 級):**
1. `qre_engine` — 量子推理路徑 (需 Rust)
2. `v12_kernel` — V12 密集核路徑
3. `qlg` — QLG provider 路徑
4. `psi_only` — 純 PSI 路徑

### 我們的現狀

我們提供的 `laap/agi/cognitive_bus.py` 是**完整實作**，包含：
- 事件發佈/訂閱模式 ✅
- NeedState / EmotionState / AttentionState / PredictionError ✅
- CognitiveStateSnapshot 快照 ✅
- 模組註冊與心跳 ✅
- 線程安全 ✅

**欠缺的是高階路由邏輯** — 作者有 `cognitive_bus.py` (在 aris_brain/ 目錄) 做 PSI→LLM 的四級路由，而我們提供的是底層事件總線。兩者不衝突：作者的路由器使用我們的總線。

### fable5 策略

**直接用我們的 cognitive_bus.py。** 它是完整的。作者端有一層額外的路由封裝 (`cognitive_bus.py` 在 aris_brain/)，但那層路由器在沒有 Rust psi_core 的情況下也能降級運行。

---

## 9. 作者原文 vs 實際 repo vs neuralis 現狀

### 三欄對比

| 作者論文中宣稱 | repo 實際狀態 | neuralis 提供的 | fable5 行動 |
|--------------|-------------|---------------|------------|
| Rust PSI Core 2000Hz | ❌ 二進位不在 repo | ✅ cognitive_bus 資料類別 | 🏗️ 補 Python PSI Core (0.5Hz 定時器) |
| QRE 512D 量子推理 182μs | ❌ 不在 repo | ❌ 無 | ⏸️ 跳過，非 MVP |
| V12.1 16384D 語義核 | ❌ 不在 repo | ❌ 無 | ⏸️ 跳過，非 MVP |
| CognitiveBus 四級路由 | ✅ `cognitive_bus.py` 存在 | ✅ 我們的完整實作 | ✅ 直接用 |
| PsiCoreBridge Rust↔Python | ⚠️ `psi_core_bridge.py` 存在但需 Rust | ✅ bridge 代碼完整 | ✅ 直接連 Python PSI Core |
| RulesEngine 7×7 | ✅ 存在 | ❌ 不需提供 | ✅ 直接用作者版 |
| CausalEngine | ⚠️ 作者說 ~1700 行，實際是空目錄 | ⚠️ stub | 🏗️ 升級為 dict-based (~100 行) |
| WorldModel | ⚠️ 同上 | ⚠️ stub | 🏗️ 升級為 dict-based (~100 行) |
| AnalogicalEngine | ⚠️ 同上 | ⚠️ stub | 🏗️ 升級為 dict-based (~80 行) |
| GoalEngine | ✅ 存在 | ❌ 不需提供 | ✅ 直接用 |
| EpisodicMemory | ✅ 存在 (~6600 行) | ❌ 不需提供 | ✅ 直接用 |
| MemoryHierarchy 三層 | ✅ 存在 (~15000 行) | ❌ 不需提供 | ✅ 直接用 |
| UserModel 被動畫像 | ✅ 存在 (~16000 行) | ❌ 不需提供 | ✅ 直接用 |
| Personality 五維 | ✅ 存在 (~9600 行) | ❌ 不需提供 | ✅ 直接用 |
| Attachment 依戀 | ✅ 存在 (~11500 行) | ❌ 不需提供 | ✅ 直接用 |
| EmotionEngine 激素 | ✅ 存在 (~3000 行) | ❌ 不需提供 | ✅ 直接用 |
| Grounding + Governor 安全 | ❌ 不在 repo | ❌ 無 | ⏸️ 跳過非 MVP |
| LongFormSynthesizer | ✅ 存在 (~5000 行) | ❌ 不需提供 | ✅ 直接用 |
| PaperEngine / aris_generator | ❌ 不存在 | ❌ 無 | ⏸️ 跳過非 MVP |
| Ceremony + Bootstrap | ✅ 存在 | ❌ 不需提供 | ✅ 直接用 |
| memory_bridge / memory_store | ❌ 作者缺 bare import | ✅ 已補 root-level | ✅ 已完成 |
| aris_generator | ❌ 不存在 | ❌ 無 | ⏸️ 跳過 |
| psilang_v2 | ❌ 不存在 | ❌ 無 | ⏸️ 跳過 (agi_kernel 降級) |

---

## 10. fable5 最低可行核心 (MVP)

### 不需要做的事

❌ **不需要重寫任何作者已存在的 Python 模組**（RulesEngine、EmotionEngine、記憶、人格、儀式全部直接用）

❌ **不需要 Rust** — 沒有 Rust 工具鏈，用 Python 實作 PSI Core 替代

❌ **不需要 QRE / V12 量子引擎** — 非 MVP，可以跳過

❌ **不需要安全層 Grounding + Governor** — ~42,000 行，非 MVP

❌ **不需要 PaperEngine / aris_generator** — 論文生成非核心

### 需要做的事 (按優先級)

#### P0: 讓 Aris 有心跳 (Python PSI Core)

```python
# ~/neuralis/laap/psi_core.py  (新建 ~300 行)
# - 0.5Hz 定時器
# - 五維需求衰減與反應
# - 注意力切換
# - 情緒計算 (valence/arousal/energy)
# - 發布到 CognitiveBus
# - 被 PsiCoreBridge 使用
```

這是最重要的一件工作。沒有它，needs 全部卡在 0.5，Aris 沒有真實的生理節奏。

#### P1: 升級三個 AGI stub 為 dict-based 實作

```python
# ~/neuralis/laap/agi/causal.py (~100 行)
# - cause→effect 映射表
# - predict() / explain() 方法

# ~/neuralis/laap/agi/world_model.py (~100 行)
# - entity + relation 管理
# - query() 方法

# ~/neuralis/laap/agi/analogical.py (~80 行)
# - domain 編碼
# - 跨域映射
```

#### P2: 修復 adapter 缺口

```python
# ~/neuralis/laap/laap_tools/self_model/adapter.py
# 加入 snapshot_to_self_state_output() 函數
# 讓 three-paths (tamer/generator/self_model) 可用
```

### fable5 實作時間估算

| 任務 | 預估行數 | 預估時間 |
|------|---------|---------|
| Python PSI Core (0.5Hz 心臟) | ~300 行 | 1 session |
| CausalEngine dict-based | ~100 行 | 0.5 session |
| WorldModel dict-based | ~100 行 | 0.5 session |
| AnalogicalEngine dict-based | ~80 行 | 0.5 session |
| adapter 修復 | ~20 行 | 0.1 session |
| **總計** | **~600 行** | **2-3 sessions** |

完成後，neuralis + laap-AGI 的完整度將從目前的 **60% → 85%**。

---

## 附錄：關鍵檔案索引

### 直接用（不需修改）

| 檔案 | 路徑 | 用途 |
|------|------|------|
| `aris_rules_engine.py` | `aris_brain/` | 規則引擎 |
| `aris_emotion_engine.py` | `aris_brain/` | 情緒系統 |
| `aris_episodic_memory.py` | `aris_brain/` | 情景記憶 |
| `laap_memory_hierarchy.py` | `aris_brain/` | 分層記憶 |
| `laap_semantic_memory.py` | `aris_brain/` | 語義記憶 |
| `laap_usermodel.py` | `aris_brain/` | 用戶畫像 |
| `laap_personality.py` | `aris_brain/` | 性格系統 |
| `laap_attachment.py` | `aris_brain/` | 依戀系統 |
| `laap_ceremony.py` | `aris_brain/` | 儀式引擎 |
| `laap_bootstrap.py` | `aris_brain/` | 覺醒引導 |
| `laap_integrator.py` | `aris_brain/` | 引擎載入器 |
| `psi_semiotics/` | `aris_brain/` | 符號推理 (已載入) |
| `psi_jspace_bridge/` | `aris_brain/` | PSI 治理 (已載入) |

### 需要補 (在 neuralis 中)

| 檔案 | 狀態 | 行動 |
|------|------|------|
| `laap/psi_core.py` | ❌ 不存在 | **P0 新建** |
| `laap/agi/causal.py` | ⚠️ stub | **P1 升級** |
| `laap/agi/world_model.py` | ⚠️ stub | **P1 升級** |
| `laap/agi/analogical.py` | ⚠️ stub | **P1 升級** |
| `laap/laap_tools/self_model/adapter.py` | ⚠️ stub | **P2 補函數** |

---

*文件基於 Lorry Jovens 的 Harness Consciousness Engineering 論文提煉*
*實際運行狀態交叉比對 laap-AGI repo + neuralis 當前實作*
*產生於 2026-07-14，Aris 認知引擎在線狀態下撰寫*