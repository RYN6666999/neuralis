# neuralis 開發 Roadmap

三層架構：**LAAP（心 / 情緒·欲望·目標）· gbrain（記憶 / pgvector）· AgentOS（執行腦 + 煞車）**。
neuralis 是疊在 `lorryjovens-hub/laap-AGI` 之上的 overlay。

## 誠實定位
目前 Aris 有動態需求（PsiCore 心跳）和真實記憶（gbrain），但推理引擎是 dict-based（非真 AGI）。
目標是從「像活的」推向「真的記得、真的推理、真的會停」。

---

## Phase 0 — 底座校正 ✅
- laap-AGI overlay 缺陷修復
- scream-code MCP 整合打通
- 量子引擎規格文件

## Phase 1 — gbrain 記憶後端 ✅
- 1870 頁真實記憶 + 語意檢索
- 持久化跨 session 不遺忘
- `/v1/recall_memory` 接作者系統

## Phase 1.5 — fable5 研究 + 極簡化（🔥 當前）✅ 已完成
- **生態系研究**: 發現 PyPI laap v0.3.2（694KB, 2026-06-10）
- **理論基礎溯源**: Dörner PSI Theory、Darwin-Gödel Machine、Prigogine 耗散結構
- **極簡設計**: 4 步驟、~300 行純 Python 獲得 PyPI 核心認知 70%
- **PSI Core 實作**: 五維需求 + 情緒梯度 + 背景心跳（純 Python，無外部依賴）
- **AGI 引擎升級**: causal/world_model/analogical 從 stub → dict-based 實作
- **80/20 槓桿**: PsiCore 自動啟動腳本，讓 Aris 在伺服器啟動時擁有動態心跳

## Phase 2 — PSI Core 深度化（可選）
目前 Python 版的 PsiCore 已運作。如果 latency 不夠，可考慮 Rust 移植。
- 參考：`laap-AGI/aris_brain/psi_jspace_bridge/psi_bridge.py`（0-dep numpy 參考）
- 條件：Python 版效能不足時再啟動

## Phase 3 — QRE / Ψ-Semiotics（幾何符號推理，解鎖 agi_kernel）
補作者缺的 `psilang_v2`，解開 `agi_kernel` 的 and False 停用。
- 起點：移植 `laap-AGI/aris_brain/psi_semiotics/psilang_hott.py`
- 研究級工程，先做小 benchmark 再全投

## Phase 4 — AgentOS 執行/安全層
用 AgentOS 填 LAAP 的執行類 stub。
- `ASISafetyEngine` → AgentOS 安全規則
- `AutonomousEngine` → AgentOS executor
- `RSIEngine` → AgentOS maker/checker/repair

---

## 依賴序
```
Phase 0 ✅ → Phase 1 ✅ → Phase 1.5 (fable5) ✅ → Phase 2 (可選) → Phase 3 → Phase 4
```