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
# 一鍵啟動（前景，PsiCore 心跳 + 全部迴路 + API :11546）
~/Developer/neuralis/scripts/start.sh

# 背景（冪等，已在跑就不重複起）
~/Developer/neuralis/scripts/start-laap-api.sh

# 看狀態
python3 scripts/aris-status.py            # 一頁式儀表
watch -n5 python3 scripts/aris-status.py  # 即時盯
```

### 韌性：watchdog

API 崩了（OOM）或假死（行程活著但不回應）時自動救回：

```bash
nohup scripts/watchdog.sh > watchdog.log 2>&1 &
```

每 30s 探 `/health`，連續 3 次失敗 → 殺殘進程（含子進程）→ 重跑 `start-laap-api.sh`。
1 小時內重啟超過 5 次視為 crash-loop，停手並吼出來（繼續重啟只會刷 log 蓋掉真因）。
調參見腳本開頭 env；審計走 `watchdog-audit.jsonl`。

刻意不用 launchd KeepAlive：它只在「行程退出」時重啟，抓不到假死。

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
    ├── start.sh                       ← 一鍵啟動（心跳 + API 同 process）
    ├── start-laap-api.sh              ← 背景啟動（冪等）
    ├── watchdog.sh                    ← 韌性：health 探測 + 自動重啟
    ├── aris-status.py                 ← 一頁式狀態儀表
    ├── approve-tool.sh                ← 工具批准閘
    └── check-*.py                     ← 各層自檢（改到哪跑哪）
```