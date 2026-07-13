# neuralis — AGENTS.md

## 專案概述

neuralis 是 laap-AGI（Lorry Jovens）之上的獨立認知擴充層。
由 Scream Code agent 與使用者共同維護，與原始 repo 完全獨立版本控制。

## 與 laap-AGI 的關係

- laap-AGI 是上游專案（Apache 2.0），neuralis 是獨立 overlay（MIT）
- 透過 PYTHONPATH 疊加，不修改作者原始碼
- `laap/` 套件中的所有模組都被 laap-AGI 透過 try/except import

## 當前進度（2026-07-14）

### 已完成
- [x] `laap/agi/cognitive_bus.py` — 完整事件總線實作
- [x] `laap/psi_core.py` — PSI 認知引擎（五維需求 + 情緒梯度 + 背景心跳）
- [x] `laap/tool_executor.py` — 工具執行層 (42 工具: gbrain/qmd/rg/httpx + AgentOS 38)
- [x] `laap/startup.py` — startup_all(): PsiCore + ToolExecutor 一次啟動
- [x] `laap/psilang_v2.py` — PsiLang v2 語言管線 (Lexer→Parser→Compiler→QuantumVM)
- [x] `laap/agi/causal.py` — 因果引擎 (dict-based, 維持現狀)
- [x] `laap/agi/world_model.py` — 世界模型 (dict-based, 維持現狀)
- [x] `laap/agi/analogical.py` — 類比引擎 (dict-based, 維持現狀)
- [x] 研究報告: PyPI 生態系 + Harness 論文提煉 + 外部 feedback 記錄

### 已知限制（誠實標記）
- `causal/world_model/analogical` 是 dict-based 非真 AGI → 策略性維持現狀，不深挖
- PsiCore 心跳未接到 `/v1/chat/completions` → 對話中需求不影響回應
- 無記憶固化循環 → 記憶有存取、缺睡眠
- Phase 4 安全閘未部署 → RSI 能力尚未開放

### 待完成（優先順序）
- [ ] P5: 記憶固化循環（consolidation + 情緒權重）
- [ ] P0: PsiCore 接對話流 (`/v1/chat/completions`)
- [ ] 4a: AgentOS 安全閘 (safety gate)
- [ ] 4b: Obscura 瀏覽器眼睛
- [ ] 4c: RSI 自我改進 (沙箱限定)

## 開發指令

```bash
# 一鍵啟動
source ~/neuralis/scripts/start.sh

# 或分步
source ~/neuralis/scripts/activate.sh
cd ~/laap-AGI && source .venv/bin/activate
python -c "from laap.startup import startup_all; startup_all()"
python aris_brain/laap_brain_api.py --port 11530
```