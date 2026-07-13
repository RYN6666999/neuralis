# 線頭 — 給下一手

> 上上手（Opus 4.8, 2026-07-14）完成 Phase 0。上一手（Fable 5, 2026-07-14）完成
> **Phase 1：gbrain 記憶後端**，commits `0d46b04` + `3586990`。**先讀 [`ROADMAP.md`](ROADMAP.md)。**

## 已驗證的現況（不是宣稱，是實跑過）
- Phase 0 全部維持：Python 3.12 venv boot 乾淨、`engines_loaded: true`、
  scream-code MCP 5 tools 通、cognitive_state 會演化
- **Phase 1 驗收全過（2026-07-14 實測）：**
  - `POST /v1/recall_memory {"query":"LAAP 情緒 記憶"}` 從回空 → 回 3 條真實腦庫記憶
  - reflect 存入 token → recall top-hit 撈回 → **kill API 重啟 → 仍撈回同一頁**
    （`laap/memory/episodic/mem-*` 存進 gbrain Postgres，真持久）
  - `scripts/check-memory-gbrain.py` 自檢 4/4 過（local + gbrain 雙後端）
  - `MemoryStore().recall('LAAP 情緒引擎')` 回全腦 1870 頁的真實記憶（core 層）

## Phase 1 架構（兩個記憶縫，不是一個）
上上手的 handoff 只講了 memory_store 縫；實際有兩條：
1. **memory_store.py**（內部認知：aris_cognitive_bridge 每輪 recall/store、PSI embedding）
   → 4 方法接 gbrain，`NEURALIS_MEMORY_BACKEND=auto|gbrain|local`，失敗自動 fallback in-process
2. **laap_semantic_memory**（`/v1/recall_memory` + reflect 持久化 — 作者檔，不可改）
   → `semantic_memory_gbrain.py` duck-typed 替身換 lazy singleton，掛載點在
   memory_store.py 檔尾（boot 必經）。作者端零改動。

共用 `gbrain_client.py`：持久 `gbrain serve`（MCP stdio）子行程，lazy spawn +
死亡重啟。實測延遲：init 1.8s（一次）、search/query ~1-1.3s、put_page ~5s（含 embed）。

## 環境重建（不變）
```bash
uv venv laapenv --python 3.12    # 與 neuralis、laap-AGI 同層
uv pip install --python laapenv/bin/python -r neuralis/requirements.txt
neuralis/scripts/start-laap-api.sh   # 起 :11546，冪等
```
⚠️ 從有 `OPENAI_API_KEY` 的 shell 起（zshrc 有）— gbrain vec 檢索靠它，
無 key 退化 lex-only（CJK/多詞 query 品質差很多，見下面踩坑）。

## 立即要抓的線頭 = Phase 2（Rust PSI Core）
見 ROADMAP §Phase 2 + `docs/specs/quantum-engine-spec.md` §1。
起點：`laap-AGI/aris_brain/psi_jspace_bridge/psi_bridge.py`（0-dep numpy 參考實作）。
golden test：同輸入 Rust 輸出 == Python 輸出。與 Phase 4（AgentOS）可並行。

## Phase 1 known gaps（何時補）
- **hash embedding 天花板**：`get_memory_embedding` 用 deterministic feature hashing
  （384-dim 契約保留、空召回=零向量降級契約保留），語意=詞袋級。
  升級路徑：gbrain 曝露原生 3072-dim 向量後做投影。影響低（作者端只拿去做注意力偏置）。
- **recall 是同步阻塞 ~1s**，跑在 aiohttp handler 裡會卡 event loop。單人本地用可接受；
  多併發時改 run_in_executor。
- **semantic add 的 meta 只存 meta_type**，完整 meta dict 沒進 frontmatter（YAML-lite 限制）。
- **laap/memory/* 頁只增不減**，沒 retention policy。量大後考慮 gbrain 端清理或降 importance 歸檔。
- **gbrain lex quirk**（上游）：多詞 AND + stemming 不對稱 — `search "neuralis"` 全空但
  頁面存在（doc 端沒 stem、query 端有）。vec 正常時無感；無 key 時明顯。可回報 gbrain repo。

## 誠實定位（不變）
有情緒狀態機 + 真持久記憶了；`laap.agi.*` 推理仍是 stub。不是 AGI。
Phase 2/3 才開始碰推理層。
