# fable5 極簡 LAAP Core 設計

> 基於 PyPI laap v0.3.2 的架構提煉，去除所有非核心複雜性
> 目標：以最少程式碼獲得可運行的 PSI 認知系統

---

## 設計原則

1. **極簡** — 能不寫就不寫，能 50 行就不要 500 行
2. **無外部依賴** — 不需要 numpy/scipy，只需要 Python 標準庫
3. **與 laap-AGI 共存** — 透過 neuralis PYTHONPATH overlay 疊加
4. **可演化** — 現在是 stub，未來可以逐步升級

---

## 核心模組設計

### Module 1: PSI 需求系統 (~60 行)

直接從 PyPI 版 `needs.py` (119 行) 濃縮，去掉 numpy 依賴：

```
neuralis/laap/psi_core.py      ← 新檔案
  NeedStatus: 五維需求數值
  PsiCore:    定時器 + 需求演算 + 情緒計算
```

**關鍵 API：**
```python
class PsiCore:
    def __init__(self, bus: CognitiveBus, interval: float = 1.0)
    def start(self)                   # 啟動背景心跳執行緒
    def stop(self)                    # 停止
    def process_input(self, text: str)  # 每次使用者輸入觸發
    def get_dominant_need(self) -> str  # 回傳最高需求名稱
    def get_state(self) -> dict        # 完整狀態快照
```

### Module 2: 情緒梯度系統 (~50 行)

從 PyPI 版 `emotion.py` (84 行) 濃縮，去掉 numpy 依賴：

```python
# 嵌入在 psi_core.py 中
class EmotionGradient:
    def __init__(self)
    def update(self, satisfactions: dict) -> EmotionalState
    def compute_intrinsic_reward(self) -> float
```

### Module 3: AGI 引擎升級 (~120 行總計)

將三個 stub 升級為 dict-based 實作：

```python
# neuralis/laap/agi/causal.py      ← 升級 (~40 行)
class UnifiedCausalEngine:
    def __init__(self, **kwargs)
    def observe(self, cause, effect, confidence=0.5)
    def predict(self, query, mode="default", top_k=3)
    def explain(self, effect)

# neuralis/laap/agi/world_model.py  ← 升級 (~40 行)
class UnifiedWorldModel:
    def __init__(self, capacity=1024, **kwargs)
    def add_entity(self, name, entity_type, properties)
    def add_relation(self, source, target, rel_type, weight)
    def query(self, query, top_k=5)

# neuralis/laap/agi/analogical.py   ← 升級 (~40 行)
class AnalogicalEngine:
    def __init__(self, **kwargs)
    def encode_domain(self, name, items)
    def find_analogies(self, query, top_k=3)
```

---

## 資料流 (極簡版)

```
每次使用者對話:
  1. PsiCore.process_input(text)
      → 根據內容調整五維需求
      → EmotionGradient.update(needs)
      → CognitiveBus.publish(CONSCIOUS_FRAME)
  
  2. AGI Subscriber 收到事件
      → CausalEngine.predict()    (可選)
      → WorldModel.query()        (可選)
      → AnalogicalEngine.find_analogies() (可選)
  
  3. 背景: 定時器每 1 秒 tick
      → 需求自然衰減 + 雜訊
      → 情緒平滑更新
      → 更新 CognitiveBus 狀態
```

---

## File Change Plan

### 新建檔案

| 檔案 | 行數 | 說明 |
|------|------|------|
| `neuralis/laap/psi_core.py` | ~110 | PSI Core: NeedDriveSystem + EmotionGradient + 心跳執行緒 |

### 升級檔案

| 檔案 | 從 → 到 | 說明 |
|------|---------|------|
| `neuralis/laap/agi/causal.py` | 20 → ~50 行 | stub → dict-based 實作 |
| `neuralis/laap/agi/world_model.py` | 40 → ~80 行 | stub → dict-based 實作 |
| `neuralis/laap/agi/analogical.py` | 20 → ~50 行 | stub → dict-based 實作 |

### 不需修改

| 檔案 | 原因 |
|------|------|
| `laap/agi/cognitive_bus.py` | 已完整，不需動 |
| `memory_bridge.py` / `memory_store.py` | 已完整 |
| `aris_brain/memory_*.py` | stub 夠用 |
| `laap/laap_tools/` | 非 MVP，維持 stub |

---

## 實作順序

### Step 1: PSI Core (110 行)
最優先，因為它是整個認知系統的心臟。

### Step 2: CausalEngine (50 行)
因為被 agi_subscriber 和 aris_cognitive_bridge 同時使用。

### Step 3: WorldModel (80 行)
被 aris_cognitive_bridge 和 agi_subscriber 使用。

### Step 4: AnalogicalEngine (50 行)
只被 agi_subscriber 使用，影響最小。

---

## 驗證方式

```bash
# 1. PSI Core 測試
cd ~/laap-AGI && source .venv/bin/activate
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python3 -c "
from laap.psi_core import PsiCore
from laap.agi.cognitive_bus import CognitiveBus
bus = CognitiveBus(agent_name='Aris')
psi = PsiCore(bus=bus)
psi.process_input('你好，今天過得怎麼樣？')
state = psi.get_state()
print('Dominant need:', state['dominant_need'])
print('Needs:', state['needs'])
print('Emotion:', state['emotion'])
"

# 2. 完整 API 啟動測試
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python3 aris_brain/laap_brain_api.py
```

---

## 與 PyPI 版的差距

| 功能 | PyPI laap v0.3.2 | 我們的極簡版 | 備註 |
|------|-----------------|------------|------|
| Need System | 119 行 + numpy | ~60 行, 純 Python | 功能等價 |
| Emotion Gradient | 84 行 + numpy | ~50 行, 純 Python | 功能等價 |
| RSI Engine | 410 行 | ❌ 跳過 | 非 MVP |
| LLM Factory | 27 提供商 | ❌ 跳過 | 非 MVP |
| 14 平台閘道 | Telegram/Discord/... | ❌ 跳過 | 非 MVP |
| 五層記憶 | 工作→情景→語義→程序→向量 | ❌ 跳過 | 現有 laap-AGI 三層夠用 |
| Swarm | 多 Agent | ❌ 跳過 | 非 MVP |
| Rust 加速 | PyO3 | ❌ 跳過 | 非 MVP |

**我們的極簡版目標：用 ~300 行 Python 獲得 PyPI 版核心認知功能的 70%。**

---

## 結論

要開始實作嗎？第一步是建立 `neuralis/laap/psi_core.py` (~110 行)。

需要的元素已經全在我們手上：
1. ✅ 我們自己的 `CognitiveBus` — 事件總線已就緒
2. ✅ PyPI 版的 `needs.py` 設計模式 — 已理解
3. ✅ PyPI 版的 `emotion.py` 設計模式 — 已理解
4. ✅ laap-AGI 的 `PsiCoreBridge` — 可以接收我們的新 PSI Core
5. ✅ 作者論文的理論基礎 — 已文件化