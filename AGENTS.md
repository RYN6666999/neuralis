# neuralis — AGENTS.md

## 專案概述

neuralis 是 laap-AGI（Lorry Jovens）之上的獨立認知擴充層。
由 Scream Code agent 與使用者共同維護，與原始 repo 完全獨立版本控制。

## 與 laap-AGI 的關係

- laap-AGI 是上游專案（MIT License）
- neuralis 只包含我們自己創作的程式碼
- 透過 PYTHONPATH 疊加在 laap-AGI 之上執行，不需修改作者原始碼
- `laap/` 套件中的所有模組都被 laap-AGI 透過 try/except import，stub 即可解鎖更多功能

## 技能路由

| 任務 | Skill |
|------|-------|
| 補實 stub 模組 | `incremental-implementation` |
| 測試 cognitive_bus | `test-driven-development` |
| 規劃下一期實作 | `planning-and-task-breakdown` |

## 開發指令

```bash
# 疊加 neuralis 到環境
source ~/neuralis/scripts/activate.sh

# 啟動 Aris
cd ~/laap-AGI && source .venv/bin/activate && python aris_brain/laap_brain_api.py

# 測試 cognitive_bus
cd ~/laap-AGI && source .venv/bin/activate && python -c "from laap.agi.cognitive_bus import CognitiveBus; bus = CognitiveBus(); print(bus)"
```

## 實作狀態

- [x] `laap/agi/cognitive_bus.py` — 完整實作（事件總線、6 種資料類別、3 枚舉、模組管理）
- [x] `laap/agi/*.py` — 11 個 AGI 模組 stub
- [x] `laap/evolution/` — 1 個 stub
- [x] `laap/laap_tools/` — 5 個 stub
- [x] `aris_brain/memory_store.py` — stub
- [x] `aris_brain/memory_bridge.py` — stub
- [ ] 補實 world_model.py（下一期）
- [ ] 補實 causal.py（下一期）
- [ ] 測試 cognitive_bus 與 psi_core_bridge 的整合

## 規則

- stub 必須有正確的 class/function 簽名，讓 laap-AGI 的 try/except import 成功
- stub 的 method 可以回傳空值，但不能 raise 未預期的例外
- 每次修改後 commit 到 neuralis（不是 laap-AGI）