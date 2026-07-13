# neuralis

**LAAP-AGI 之上的認知擴充層** — 我們自己創造的程式碼，獨立於原始作者 repo。

## 這是什麼

`neuralis` 是我們在 `laap-AGI`（Lorry Jovens 的 Lifeform Architecture for Autonomous Psyche）之上獨立開發的擴充層。包含：

- **`laap/agi/cognitive_bus.py`** — 認知事件總線實作（非 stub），提供 publish/subscribe 模式讓所有 AGI 模組通訊
- **`laap/agi/*.py`** — AGI 認知模組（world_model, causal, analogical, meta_learning 等），目前為 stub，逐步升級為實作
- **`laap/evolution/`** — 自我演化與 RSI 引擎
- **`laap/laap_tools/`** — LLM 馴服器、引導生成、自我模型工具
- **`aris_brain/`** — 階層記憶儲存（MemoryStore + MemoryBridge）

## 設計原則

1. **獨立版本控制** — neuralis 有自己的 git history，不受 laap-AGI upstream 影響
2. **非侵入** — 所有 stub 模組在作者端都有 try/except fallback，不會導致 laap-AGI 啟動失敗
3. **逐步實作** — 從 stub 開始，逐步注入真正實作
4. **Overlay 架構** — 透過 PYTHONPATH 疊加在 laap-AGI 之上，不需修改作者原始碼

## 使用方式

```bash
# 將 neuralis 疊加到 laap-AGI 環境
source ~/neuralis/scripts/activate.sh

# 啟動 laap-AGI
cd ~/laap-AGI && source .venv/bin/activate && python aris_brain/laap_brain_api.py
```

## 目錄結構

```
neuralis/
├── laap/
│   ├── __init__.py
│   ├── agi/
│   │   ├── cognitive_bus.py    ← 事件總線（實作）
│   │   ├── world_model.py       ← 世界模型（stub）
│   │   ├── causal.py            ← 因果引擎（stub）
│   │   ├── analogical.py        ← 類比引擎（stub）
│   │   └── ...                  ← 其他 AGI 模組
│   ├── evolution/
│   └── laap_tools/
├── aris_brain/
│   ├── memory_store.py
│   └── memory_bridge.py
├── docs/specs/
└── scripts/
    └── activate.sh
```