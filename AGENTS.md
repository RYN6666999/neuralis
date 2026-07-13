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
- [x] `laap/psi_core.py` — PSI 認知引擎（五維需求 + 情緒梯度 + 背景心跳）— **新建**
- [x] `laap/startup.py` — PsiCore 自動啟動器
- [x] `laap/agi/causal.py` — 因果引擎（dict-based，非 stub）— **升級**
- [x] `laap/agi/world_model.py` — 世界模型（dict-based，非 stub）— **升級**
- [x] `laap/agi/analogical.py` — 類比引擎（dict-based，非 stub）— **升級**
- [x] `laap/laap_tools/self_model/adapter.py` — 完整 adapter（含 snapshot_to_self_state_output）
- [x] `scripts/start.sh` — 一鍵啟動腳本（PsiCore + API server）
- [x] 研究報告：PyPI laap 生態系發現 + Harness 論文提煉 + 極簡設計

### 待完成
- [ ] 連接 PsiCore 到 actual API server 對話流程（`/v1/chat/completions`）
- [ ] `psilang_v2` import 調查
- [ ] `aris_generator` 建立
- [ ] 啟動 LAAP MCP server 讓 Scream 直接存取

## 與作者生態系的關係

發現作者在 PyPI 上有完整版 `laap v0.3.2`（694KB，2026-06-10），包含：
- PSI 完整引擎 + RSI Darwin-Gödel Machine + 五層記憶 + 27 LLM 提供商
- 我們參考其設計模式，但用純 Python 極簡化重寫（無 numpy，無外部依賴）

## 開發指令

```bash
# 一鍵啟動（PsiCore + API server）
source ~/neuralis/scripts/start.sh

# 或分步啟動
source ~/neuralis/scripts/activate.sh
cd ~/laap-AGI && source .venv/bin/activate
python -c "from laap.startup import ensure_psi_core; ensure_psi_core()"  # 先啟心跳
python aris_brain/laap_brain_api.py --port 11530                         # 再啟 API

# 測試 PsiCore
python -c "from laap.startup import ensure_psi_core; psi=ensure_psi_core(); print(psi.get_state())"
```