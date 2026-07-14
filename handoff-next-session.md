# 線頭 — 給下一手

> 最後更新: 2026-07-14 | 最新 commit: `a1359c9`（全面檢查修復波）
> 當前 Phase: **Phase 5（記憶固化循環）** — 剛從 Phase 3 推進至此

## ⚠️ 2026-07-14 全面檢查結果（fable5 review，commit `a1359c9`）
實跑審查 Phase 1.5/3 的 code 後修掉 6 個 bug — **最重要的一個：在修復前，
PsiCore 心臟從來沒有真的接上過**：
1. `aris_brain/` 死碼目錄 shadow 掉作者 namespace package → `ensure_psi_core`
   在文檔宣稱的 PYTHONPATH 布局下必敗（`psi_core_bridge` ImportError）。已刪。
2. 舊 start.sh 把 PsiCore 起在獨立短命 `python -c` 行程，印完 banner 就死 —
   API server 裡沒有心跳。已改：同一 process 內 `startup_all()` → runpy 起作者 API。
3. ToolExecutor 在 psi 失敗時拿到 bus=None 直接炸（工具全滅）→ 裸 bus 頂上。
4. 心跳執行緒無護欄，單次 tick 異常 = 靜默腦死 → try/except。
5. psilang_v2 Parser 殘缺輸入 IndexError → EOF token。
6. gbrain_client respawn 世代污染 race + 非 GbrainError 逃逸 → 修。
perf: hybrid_hits 20s TTL 快取；tool_executor 的 gbrain 走持久 client（省 ~3s/次）。

修復後實測（本機 `~/Developer/{neuralis,laap-AGI,laapenv}` 布局）：
`scripts/start.sh` → PsiCore 心跳 tick 走 + 42 工具 + engines_loaded=true +
recall_memory 迴歸過 + 記憶自檢 4/4。

**遺留（review 發現但未動）：**
- AGIKernel 在 API boot 路徑仍卡 `core_identity.psi` 缺檔（author data file）—
  「Phase 3 解鎖」只解鎖了直接建構，boot 路徑沒解。別合成假身份檔，等作者端。
- PsiCore 需求 decay（~0.008/s）對常駐 daemon 太快：閒置 2-3 分鐘全需求見底、
  效價 → -1（「醒來就憂鬱」）。要嘛接受、要嘛改 decay-toward-baseline，設計決策留給下手。
- `process_input()` 還沒有任何呼叫者 — 心跳活了，但對話還沒餵進需求偵測。
  Phase 5 接 consolidation 時順手接這條（`/v1/chat/completions` 或 reflect handler）。

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

### 環境啟動（修正版 — 舊指令的 ~/laap-AGI + .venv + :11530 在本機不存在）
```bash
# 一鍵：PsiCore 心跳 + API 同 process（前景，port 預設 11546）
~/Developer/neuralis/scripts/start.sh
# 或只驗 startup_all（任意 cwd 都可，shadow bug 已修）
PYTHONPATH="$HOME/Developer/neuralis:$HOME/Developer/laap-AGI" \
  ~/Developer/laapenv/bin/python -c "from laap.startup import startup_all; print(startup_all())"
```

### Phase 5 完成條件
- [ ] 背景 consolidation 排程已註冊（與 PsiCore 心跳同生命週期）
- [ ] 情緒強度作為記憶權重已實作
- [ ] gbrain 寫回驗證：固化前 → 固化後 → 檢索有差
- [ ] handoff 更新 + push

---

## 環境重建（本機實際布局：~/Developer/{neuralis,laap-AGI,laapenv}）
```bash
uv venv ~/Developer/laapenv --python 3.12
uv pip install --python ~/Developer/laapenv/bin/python -r ~/Developer/neuralis/requirements.txt
~/Developer/neuralis/scripts/start.sh              # 前景，含 PsiCore 心跳，:11546
# 或背景（無 PsiCore，純 API）: ~/Developer/neuralis/scripts/start-laap-api.sh
```

⚠️ gbrain vec 檢索需要 `OPENAI_API_KEY` 環境變數（zshrc 有）。
無 key 退化 lex-only（CJK/多詞 query 品質差很多）。