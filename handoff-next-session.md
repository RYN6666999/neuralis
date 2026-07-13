# 線頭 — 給下一手

> 最後更新: 2026-07-14 | 最新 commit: `fb101c1`
> 當前 Phase: **Phase 5（記憶固化循環）** — 剛從 Phase 3 推進至此

---

## 已驗證的現況（不是宣稱，是實跑過）

### 心臟：PsiCore
- `laap/psi_core.py` — 五維需求 (competence/autonomy/relatedness/certainty/growth) + 情緒梯度場
- 背景心跳執行緒 (1s tick) — 需求衰減 + 雜訊 + 情緒平滑更新
- 關鍵詞偵測 → 需求滿足 → CognitiveBus 事件發布
- 啟動: `from laap.startup import startup_all` → 回傳 (bus, psi, tools)

### 手腳：ToolExecutor (42 工具)
- `laap/tool_executor.py` — CognitiveBus → AgentOS executor_registry 橋接
- 4 內建: gbrain (hybrid search)、qmd (本地知識)、file-search (rg)、http-get (httpx)
- 38 from AgentOS: web-search、agnes-analyze、claude-code、33 skill executors
- 驗證：`from laap.startup import startup_all; startup_all()` → 42 tools

### 大腦：AGIKernel（Phase 3 — 2026-07-14 新解鎖）
- `laap/psilang_v2.py` — Lexer → Parser → Compiler → QuantumVM 管線 (dict-based)
- AGIKernel 四層引擎：PsiLangCore(1024D) + SelfHeal + SelfEvolve + Autonomy
- 驗證：`from aris_brain.agi_kernel import AGIKernel; AGIKernel()` ✅
- 注意：agi_memory + .psi 核心定義檔為作者端缺失，不影響架構

### 記憶：gbrain（Phase 1 — 已完成）
- 1870 頁真實記憶 + hybrid search
- 跨 session 不遺忘（kill server → restart → 仍撈回同一頁）
- `gbrain_client.py` — 持久 gbrain subprocess (MCP stdio)
- `semantic_memory_gbrain.py` — duck-typed 替身接作者 `/v1/recall_memory`
- 誠實限制：hash embedding 天花板、recall 同步阻塞 ~1s、無 retention policy

### 理論基礎（Phase 1.5 — 2026-07-14）
- 論文: `docs/specs/core-architecture.md` — Harness Consciousness Engineering 提煉
- 設計: `docs/specs/fable5-minimal-design.md` — 極簡化策略
- 生態: `docs/research/laap-ecosystem-report.md` — PyPI laap v0.3.2 發現
- feedback: `docs/research/external-feedback.md` — 外部架構審查記錄

### 已知限制（誠實）
- `laap/agi/causal/world_model/analogical` = dict-based，非真 AGI → 策略性維持現狀
- PsiCore 心跳未接到 `/v1/chat/completions` → 對話中需求不影響回應
- 無記憶固化循環 → 記憶有存取、缺睡眠（Phase 5 的內容）
- Phase 4 安全閘未部署 → RSI 能力尚未開放

---

## 立即要抓的線頭 = Phase 5（記憶固化循環）

見 ROADMAP §Phase 5。純 overlay，不碰作者碼。

### 要做的事
1. **背景排程**：在 PsiCore 心跳執行緒中加 consolidation step
2. **摘要壓縮**：取 session 記憶 → 去重 → 摘要 → 標重要度
3. **情緒權重**：PsiCore 的 valence × arousal 作為記憶重要性指標
4. **寫回 gbrain**：固化後的記憶存入 gbrain 長期區

### 環境啟動
```bash
cd ~/laap-AGI && source .venv/bin/activate
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python -c "
from laap.startup import startup_all
bus, psi, tools = startup_all()
"
```

### Phase 5 完成條件
- [ ] 背景 consolidation 排程已註冊（與 PsiCore 心跳同生命週期）
- [ ] 情緒強度作為記憶權重已實作
- [ ] gbrain 寫回驗證：固化前 → 固化後 → 檢索有差
- [ ] handoff 更新 + push

---

## 環境重建
```bash
cd ~/laap-AGI && source .venv/bin/activate
PYTHONPATH="$HOME/neuralis:$PYTHONPATH" python aris_brain/laap_brain_api.py --port 11530
```

⚠️ gbrain vec 檢索需要 `OPENAI_API_KEY` 環境變數（zshrc 有）。
無 key 退化 lex-only（CJK/多詞 query 品質差很多）。