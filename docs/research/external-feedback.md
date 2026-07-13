# 外部 feedback 記錄 — 2026-07-14

> 來源：第三方 AI 專家對 neuralis 架構的深度審查
> 定位：作為未來開發方向的參考北極星，不是指令

---

## 核心肯定

1. **理論歸屬正確** — Dörner PSI、Darwin-Gödel Machine、Prigogine 耗散結構的標註是對的。造假（如果有）是上游作者的問題，不是 neuralis 的。
2. **gbrain 是真正的護城河** — 1870 頁真實記憶、跨 session 不遺忘，這是上游沒有、PyPI laap 沒有、LangChain 也沒有的資產。
3. **overlay 策略正確** — 不動作者碼，只在 neuralis 補好料強化。

## 最高投報建議

### 1. 記憶固化循環 (Memory Consolidation) — 🔥 建議優先
> 記憶有存取、缺睡眠。
- 背景排程（跟 PsiCore 心跳同機制）
- 定期對 session 記憶做摘要、去重、標重要度
- 寫回 gbrain 長期區
- 結合情緒權重：valance × arousal 作為重要性指標

### 2. 情緒作為記憶權重
- 20 行程式碼
- 在寫入記憶時多存 `emotion_intensity = abs(valence) * arousal`
- 檢索時依情緒強度加權排序
- 學理基礎：Damasio 的 somatic marker hypothesis

### 3. 自我敘事層 (Self-Narrative) — ⚠️ 建議暫緩
- 讓 Aris 用自己的記憶生成第一人稱敘事
- 需要 LLM 調用，與「零 LLM」路線衝突
- 等到記憶固化做完、對話流接上後再評估

### 4. 生命向量儀表板 — ❌ 建議跳過
- 對外講故事有用，對系統能力無幫助

## 安全紅線

**Phase 4 的執行順序不可逆：**
```
安全閘 (safety/checker) → 工具深度整合 → RSI 自我改進
```
RSI 的沙箱測試必須在隔離環境執行，且必須有人工批准閘門。
這不是可選的。

## 架構診斷摘要

| 層級 | 強度 | 建議 |
|------|------|------|
| 心臟 (PSI Core) | ✅ 扎實 | 接到對話流 |
| 記憶 (gbrain) | ✅ 護城河 | 補固化循環 |
| 執行 (ToolExecutor) | ✅ 夠用 | 補安全閘 |
| 推理 (causal/world/analogical) | ⚠️ 維持現狀 | 別深挖 |
| 敘事 (self-narrative) | ❌ 不存在 | 暫緩