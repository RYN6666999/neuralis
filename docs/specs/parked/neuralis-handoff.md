# neuralis — 完整任務交接文件

> 給下一手 AI 的完整上下文：laap-AGI 架構、缺口矩陣、優先級、補全策略
> 
> 作者 repo: https://github.com/lorryjovens-hub/laap-AGI
> 我們的 repo: https://github.com/RYN6666999/neuralis
> 安裝工具: https://github.com/LIUTod/scream-code

---

## 1. 架構總覽

```
┌──────────────────────────────────────────────────────────────┐
│                     laap-AGI (作者 Lorry Jovens)              │
│  GitHub: github.com/lorryjovens-hub/laap-AGI                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  aris_brain/  (認知引擎核心 — 已存在，完整)                    │
│  ├── laap_brain_api.py          ← API server (aiohttp, :11530)│
│  ├── aris_cognitive_bridge.py   ← 認知橋接 (缺 memory_bridge) │
│  ├── psi_core_bridge.py         ← Rust psi_core 橋接          │
│  ├── agi_subscriber.py          ← AGI 事件訂閱器              │
│  ├── agi_kernel.py              ← AGI 內核 (缺 psilang_v2)    │
│  ├── aris_rules_engine.py       ← 規則引擎 (缺 aris_generator)│
│  ├── laap_bootstrap.py          ← 7 樂章覺醒儀式              │
│  ├── laap_integrator.py         ← 引擎整合器                  │
│  ├── laap_personality.py        ← 性格系統 (存在)             │
│  ├── laap_attachment.py         ← 依戀系統 (存在)             │
│  ├── laap_expression_mapper.py  ← 表情映射 (存在)             │
│  ├── laap_semantic_memory.py    ← 語義記憶 (存在)             │
│  ├── laap_memory_hierarchy.py   ← 記憶階層 (存在)             │
│  ├── laap_ceremony.py           ← 儀式引擎 (存在)             │
│  ├── laap_usermodel.py          ← 用戶模型 (存在)             │
│  ├── laap_grounding.py          ← 接地系統 (存在)             │
│  ├── ... (認知引擎: desire/emotion/goal/subconscious/Hebbian)│
│  │                                                           │
│  ├── psi_jspace_bridge/         ← PSI 認知循環 (完整)        │
│  └── psi_semiotics/             ← Ψ-符號學引擎 (完整)        │
│                                                              │
│  laap_brain/  (API 後端 — 存在)                               │
│  ├── api.py, config.py, integrator.py, ...                   │
│                                                              │
│  mcp_server/  (MCP 伺服器 — 存在)                             │
│  └── laap_mcp_server.py                                      │
│                                                              │
│  hermes-integration/  (Hermes Agent 整合 — 存在)              │
│                                                              │
└──────────────────────┬───────────────────────────────────────┘
                       │ PYTHONPATH overlay
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                neuralis (我們的擴充層)                         │
│  GitHub: github.com/RYN6666999/neuralis                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  laap/agi/cognitive_bus.py    ← 🔥 完整實作                  │
│  laap/agi/*.py                ← 11 個 stub (需升級)          │
│  laap/evolution/rsi.py        ← stub                         │
│  laap/laap_tools/             ← 5 個 stub                    │
│  aris_brain/memory_*.py       ← stub                         │
│  memory_bridge.py             ← 修復作者 bare import         │
│  memory_store.py              ← 修復作者 bare import         │
│  scripts/activate.sh          ← PYTHONPATH 疊加              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 啟動序列 (laap_brain_api.py)

```
main() 啟動順序:
  1. 解析 port (CLI > env > 預設 11530)
  2. logging.basicConfig
  3. get_laap_engine() → try:
       from laap_integrator import get_integrator
       INTEGRATOR = get_integrator()
       INTEGRATOR.load_all()    ← 載入所有認知引擎模組
     except: 降級模式 (ENGINES_LOADED = False)
  4. 建立 web.Application() + 12 個路由
  5. web.run_app(host="0.0.0.0", port=port)

API 端點:
  GET  /                         → 根資訊
  GET  /health                   → 健康檢查
  GET  /v1/models                → 3 模型: laap-core, laap-qre, laap-rules
  POST /v1/chat/completions      → OpenAI 相容聊天 (支援串流)
  POST /v1/cognitive_state      → PSI 狀態
  POST /v1/recall_memory        → 語義記憶檢索
  POST /v1/reflect              → 回合後反思
  POST /v1/express              → 認知狀態 → TTS/Live2D
  POST /v1/bootstrap            → 7 樂章覺醒儀式
  GET  /v1/personality          → 獲取性格
  POST /v1/personality          → 設定性格
  GET  /v1/bond                 → 依戀狀態
```

---

## 3. 缺口矩陣 (Gap Matrix)

### 3.1 laap/ 套件 — 我們要提供的模組

| 模組 | 路徑 | 現狀 | 被誰使用 | 優先級 |
|------|------|------|---------|--------|
| `cognitive_bus` | `laap/agi/cognitive_bus.py` | ✅ **完整實作** | psi_core_bridge, agi_subscriber | P0 完成 |
| `world_model` | `laap/agi/world_model.py` | ⚠️ stub | aris_cognitive_bridge, agi_subscriber | **P1 升級** |
| `causal` | `laap/agi/causal.py` | ⚠️ stub (接受 **kwargs) | aris_cognitive_bridge, agi_subscriber | **P1 升級** |
| `analogical` | `laap/agi/analogical.py` | ⚠️ stub (接受 **kwargs) | agi_subscriber | **P1 升級** |
| `meta_learning` | `laap/agi/meta_learning.py` | ⚠️ stub | aris_cognitive_bridge | P2 |
| `curriculum` | `laap/agi/curriculum.py` | ⚠️ stub | aris_cognitive_bridge, aris_goal_engine | P2 |
| `perception` | `laap/agi/perception.py` | ⚠️ stub | aris_cognitive_bridge | P2 |
| `safety` | `laap/agi/safety.py` | ⚠️ stub | aris_cognitive_bridge | P2 |
| `self_healing` | `laap/agi/self_healing.py` | ⚠️ stub | agi_kernel | P2 |
| `code_evolution` | `laap/agi/code_evolution.py` | ⚠️ stub | agi_kernel | P2 |
| `autonomy` | `laap/agi/autonomy.py` | ⚠️ stub | agi_kernel | P2 |
| `rsi_engine` | `laap/agi/rsi_engine.py` | ⚠️ stub | aris_goal_engine | P2 |
| `__init__` | `laap/agi/__init__.py` | ✅ 正確 export | 所有使用者 | 完成 |
| `evolution.rsi` | `laap/evolution/rsi.py` | ⚠️ stub | agi_kernel | P2 |
| `laap_tools.llm_tamer` | `laap/laap_tools/llm_tamer.py` | ⚠️ stub | aris_cognitive_bridge | P2 |
| `laap_tools.guided_generator` | `laap/laap_tools/guided_generator/` | ⚠️ stub | aris_cognitive_bridge | P2 |
| `laap_tools.self_model` | `laap/laap_tools/self_model/` | ⚠️ stub | aris_cognitive_bridge | P2 |

### 3.2 作者端缺失模組 (非 laap. 套件)

| 模組 | 被誰 import | 現狀 | 優先級 |
|------|-------------|------|--------|
| `memory_bridge` (bare) | aris_cognitive_bridge:30 | ✅ **已在 neuralis 修復** (root-level) | 完成 |
| `memory_store` (bare) | aris_cognitive_bridge:31 | ✅ **已在 neuralis 修復** (root-level) | 完成 |
| `aris_generator` | aris_rules_engine:215 (subprocess) | ❌ 不存在，需建立 | **P1 新增** |
| `psilang_v2` | agi_kernel | ❌ 不存在，作者有 psilang_hott 但 import 名稱不同 | **P1 調查** |
| `codegraph_bridge` | aris_cognitive_bridge | ❌ 不存在，可能是設計意圖從未實作 | P3 調查 |

### 3.3 環境問題

| 問題 | 詳情 | 優先級 |
|------|------|--------|
| `mcp` 套件未在 .venv 中 | `mcp/server/fastmcp.py` 需要 `pip install mcp` | P2 |
| `test_mcp_tools.py` 硬編碼 Windows 路徑 | 第 4 行 `D:\laap-AGI\` 需改為 macOS | P3 |
| Rust toolchain 未安裝 | `rustc` 不存在，無法編譯 psi_core | P3 選項 |

---

## 4. 補全優先級與策略

### P0 — 已完成的基礎建設
- [x] `laap/agi/cognitive_bus.py` 完整實作
- [x] `laap/agi/__init__.py` 正確 export
- [x] `memory_bridge.py` + `memory_store.py` root-level stub
- [x] 所有 11 個 AGI 模組 stub（可 import 不報錯）
- [x] `laap/laap_tools/` + `laap/evolution/` stub
- [x] `aris_brain/memory_store.py` + `memory_bridge.py`
- [x] `scripts/activate.sh` PYTHONPATH 疊加

### P1 — 優先補實
- [ ] **`world_model.py` 升級** — 從 stub 升級為真正的語意圖引擎
  - 被 `aris_cognitive_bridge` 和 `agi_subscriber` 使用
  - 需要：EntityType, RelationType, UnifiedWorldModel 類別
  - 建議：先用 dict-based 實作，後續可換向量資料庫
  - 參考：作者在 `aris_cognitive_bridge.py:391` 的用法

- [ ] **`causal.py` 升級** — 因果推理引擎
  - 被 `agi_subscriber` 以 `UnifiedCausalEngine(quantum_dim=64, name="ArisCausal")` 呼叫
  - 需要：`__init__(**kwargs)` 接受所有參數
  - 提供 `predict(query, mode, top_k)` 方法

- [ ] **`analogical.py` 升級** — 類比推理引擎
  - 被 `agi_subscriber` 以 `AnalogicalEngine(name="ArisAnalogical")` 呼叫
  - 需要：`__init__(**kwargs)` 接受所有參數
  - 提供 `encode_domain(name, items)` + `find_analogies(query, top_k)`

- [ ] **`aris_generator.py` 建立** — 讓 aris_rules_engine 的論文生成功能可用
  - 位置：`aris_brain/aris_generator.py`（作者的目錄）
  - 被 `aris_rules_engine.py:215` 透過 subprocess 呼叫
  - 需要：`generate()` 函數，接受 prompt 回傳文字

- [ ] **`psilang_v2` 調查** — 確認是 import 名稱錯誤還是作者未釋出
  - 檢查 `agi_kernel.py` 的 import 細節
  - 可能解法：在 neuralis 中建立 `psilang_v2.py` 轉發到 `psilang_hott`

### P2 — 次要補實
- [ ] `python -m pip install mcp` 到 .venv 中
- [ ] `meta_learning.py` 升級
- [ ] `curriculum.py` 升級
- [ ] `perception.py` 升級
- [ ] `safety.py` 升級
- [ ] `self_healing.py` 升級
- [ ] `code_evolution.py` 升級
- [ ] `autonomy.py` 升級
- [ ] `rsi_engine.py` 升級
- [ ] `evolution/rsi.py` 升級
- [ ] `laap_tools/` 各模組升級

### P3 — 長期選項
- [ ] `codegraph_bridge` 調查與實作
- [ ] `test_mcp_tools.py` 移植到 macOS
- [ ] Rust psi_core 引擎實作或 Python fallback 優化

---

## 5. 關鍵檔案索引

### 作者端必須知道的檔案

| 檔案 | 重要性 | 說明 |
|------|--------|------|
| `aris_brain/laap_brain_api.py` | 🔥 核心 | API server，啟動入口，所有端點定義 |
| `aris_brain/laap_bootstrap.py` | 🔥 核心 | 7 樂章覺醒儀式，初始化所有系統 |
| `aris_brain/aris_cognitive_bridge.py` | 🔥 核心 | 認知橋接，import 我們的大多數模組 |
| `aris_brain/psi_core_bridge.py` | 🔥 核心 | 第一個使用 CognitiveBus 的模組 |
| `aris_brain/agi_subscriber.py` | ⚡ 重要 | AGI 事件訂閱，使用 causal/analogical/world_model |
| `aris_brain/agi_kernel.py` | ⚡ 重要 | AGI 內核，使用 self_healing/code_evolution/autonomy |
| `aris_brain/aris_rules_engine.py` | ⚡ 重要 | 規則引擎，使用 aris_generator (subprocess) |
| `aris_brain/laap_integrator.py` | ⚡ 重要 | 引擎整合器，load_all() 決定啟動哪些模組 |
| `aris_brain/laap_ceremony.py` | 一般 | 儀式引擎，使用 laap_personality |
| `aris_brain/config.py` | 🔥 核心 | 路徑設定，BRAIN_DIR/STATE_DIR/LAAP_ROOT |

### neuralis 端必須知道的檔案

| 檔案 | 重要性 | 說明 |
|------|--------|------|
| `laap/agi/cognitive_bus.py` | 🔥 核心 | 唯一完整實作，事件總線 |
| `laap/agi/*.py` | ⚡ 重要 | 11 個 stub，需升級 |
| `memory_bridge.py` (root) | 🔥 核心 | 修復作者 bare import |
| `memory_store.py` (root) | 🔥 核心 | 修復作者 bare import |
| `aris_brain/memory_store.py` | 一般 | neuralis 的套件版記憶 |
| `aris_brain/memory_bridge.py` | 一般 | neuralis 的套件版橋接 |
| `scripts/activate.sh` | 🔥 核心 | PYTHONPATH 疊加 |
| `AGENTS.md` | 重要 | 開發規範 |

---

## 6. 開發者工作流

### 首次啟動
```bash
# 1. 啟動 laap-AGI 虛擬環境
cd ~/laap-AGI && source .venv/bin/activate

# 2. 疊加 neuralis
source ~/neuralis/scripts/activate.sh

# 3. 啟動 API server
python aris_brain/laap_brain_api.py
# → Server running on http://0.0.0.0:11530

# 4. 測試健康檢查
curl http://localhost:11530/health

# 5. 執行覺醒儀式
curl -X POST http://localhost:11530/v1/bootstrap
```

### 迭代 stub → 實作
```bash
# 測試單一模組 import
cd ~/laap-AGI && source .venv/bin/activate
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python3 -c "
from laap.agi.causal import UnifiedCausalEngine
engine = UnifiedCausalEngine(quantum_dim=64, name='ArisCausal')
print('✅', engine)
"

# 測試完整啟動
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python3 aris_brain/laap_brain_api.py
```

### 提交到 neuralis
```bash
cd ~/neuralis
git add -A
git commit -m "升級: world_model.py 從 stub 升級為 dict-based 實作"
git push
```

---

## 7. 常見陷阱

### 陷阱 1: bare import vs 套件 import
作者的 `aris_cognitive_bridge.py` 使用：
```python
from memory_bridge import get_memory_context, recall_related, store_important
from memory_store import MemoryStore, MemoryFragment
```
這是**裸 import**（不是 `from aris_brain.memory_bridge`）。neuralis 在 root 層級提供這兩個檔案來解決。

### 陷阱 2: **kwargs 的重要性
作者端的 AGI 模組在建立時會傳入額外參數：
```python
UnifiedCausalEngine(quantum_dim=64, name="ArisCausal")  # 在 agi_subscriber.py:88
AnalogicalEngine(name="ArisAnalogical")                  # 在 agi_subscriber.py:97
```
所有 stub 的 `__init__` 必須接受 `**kwargs`，否則會 crash。

### 陷阱 3: sys.path 插入
`laap_brain/config.py` 在 module 層級呼叫 `setup_paths()`，會將 `aris_brain/`、`laap_brain/`、`laap-AGI/` 等路徑插入 `sys.path`。這讓 `from memory_bridge import ...` 這種 bare import 能運作，但也讓除錯變得困難。

### 陷阱 4: 啟動不失敗 = 不代表一切正常
laap-AGI 的設計哲學是**降級不崩潰**。所有非關鍵 import 都有 try/except：
- 引擎預載失敗 → `ENGINES_LOADED = False`，API 仍啟動
- 模組 import 失敗 → logger.warning，繼續執行
- 這代表伺服器啟動成功 ≠ 所有功能正常

### 陷阱 5: Rust 不存在
作者的 `psi_core` 是 Rust 2000Hz 引擎，但二進位不在 repo 中，且本機無 Rust toolchain。整個系統在 Python fallback 模式運作。`psi_core_bridge.py` 讀取 `state/latest.json` 如果檔案不存在則回退。

---

## 8. 快速驗證清單

部署或升級後，執行以下測試：

```bash
# 1. 基礎 import 測試
python3 -c "
from laap.agi.cognitive_bus import CognitiveBus, CognitiveEventType
from laap.agi.causal import UnifiedCausalEngine
from laap.agi.analogical import AnalogicalEngine
from laap.agi.world_model import UnifiedWorldModel
from laap.agi.safety import ASISafetyEngine
from laap.agi.self_healing import AutoHealer
print('✅ 所有 laap.agi 模組 import 成功')
"

# 2. 作者端 import 測試
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python3 -c "
import sys; sys.path.insert(0, '.')
from aris_brain.psi_core_bridge import get_global_bus
from aris_brain.agi_subscriber import AGISubscriber
from aris_brain.aris_cognitive_bridge import ArisCognitiveBridge
print('✅ 作者端核心模組載入成功')
"

# 3. API 啟動測試 (5 秒 timeout)
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python3 -c "
import sys; sys.path.insert(0, '.')
from aris_brain.laap_brain_api import main
print('✅ API main() 可匯入')
"

# 4. 端到端測試
# 啟動 server → curl /health → curl /v1/bootstrap → curl /v1/chat/completions
```

---

## 9. 總結

### 目前完成度 (2026-07-13)

| 類別 | 項目 | 完成 |
|------|------|------|
| laap/agi 套件 | 1/12 完整實作, 11/12 stub | 8% 實作 |
| 作者 bare import 修復 | 2/2 memory_bridge/memory_store | 100% |
| 記憶系統 | 2/2 stub | 0% 實作 |
| laap_tools | 5/5 stub | 0% 實作 |
| evolution | 1/1 stub | 0% 實作 |
| 環境設定 | scripts/activate.sh, .gitignore, AGENTS.md | 100% |

### 下一步行動

**優先順序：**
1. 升級 `world_model.py` → 真正的語意圖
2. 升級 `causal.py` → 接受 quantum_dim 參數的因果引擎
3. 升級 `analogical.py` → 類比推理
4. 建立 `aris_generator.py` → 解鎖論文生成
5. 調查 `psilang_v2` import 問題

---

*文件由 Scream Code AI Agent 於 2026-07-13 自動產出*
*最後更新: 2026-07-13*