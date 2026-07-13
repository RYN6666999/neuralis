# neuralis

**LAAP-AGI 之上的認知擴充層** — 我們自己創造的程式碼，獨立於原始作者 repo。

## 這是什麼

`neuralis` 是我們在 `laap-AGI` 之上獨立開發的認知擴充層。

### 核心實作
- **`laap/psi_core.py`** — PSI 認知引擎（五維需求驅動 + 情緒梯度場 + 背景心跳執行緒）
- **`laap/agi/cognitive_bus.py`** — 認知事件總線（publish/subscribe 模式）
- **`laap/agi/causal.py`** — 因果推理引擎（dict-based）
- **`laap/agi/world_model.py`** — 世界模型（實體/關係管理）
- **`laap/agi/analogical.py`** — 類比推理引擎（跨域映射）
- **`laap/startup.py`** — PsiCore 自動啟動器

### 與 laap-AGI 的關係
- laap-AGI 是上游開源專案（Apache 2.0）
- neuralis 只包含我們自己創作的程式碼（MIT）
- 透過 PYTHONPATH 疊加執行，不需修改作者原始碼

## 使用方式

```bash
# 一鍵啟動
source ~/neuralis/scripts/start.sh

# 或分步
source ~/neuralis/scripts/activate.sh
cd ~/laap-AGI && source .venv/bin/activate
python aris_brain/laap_brain_api.py --port 11530
```

## 目錄結構

```
neuralis/
├── laap/
│   ├── psi_core.py              ← PSI 認知引擎（🔥 新建）
│   ├── startup.py                ← 自動啟動器
│   ├── agi/
│   │   ├── cognitive_bus.py      ← 事件總線（實作）
│   │   ├── causal.py             ← 因果引擎（升級）
│   │   ├── world_model.py        ← 世界模型（升級）
│   │   ├── analogical.py         ← 類比引擎（升級）
│   │   └── ...                   ← 其他 stub
│   ├── evolution/
│   └── laap_tools/
├── aris_brain/
│   ├── memory_store.py
│   └── memory_bridge.py
├── docs/
│   ├── research/
│   │   └── laap-ecosystem-report.md  ← PyPI 生態系研究
│   └── specs/
│       ├── core-architecture.md       ← 論文提煉
│       ├── fable5-minimal-design.md   ← 極簡設計
│       └── neuralis-handoff.md
└── scripts/
    ├── activate.sh
    └── start.sh                       ← 一鍵啟動
```