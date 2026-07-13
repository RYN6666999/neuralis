# 線頭 — 給下一手（fable5）

> 上一手（Opus 4.8, 2026-07-14）做完 Phase 0：底座校正 + scream-code MCP 整合實測打通 +
> 量子引擎規格彙整。額度用完，留此線頭。**先讀 [`ROADMAP.md`](ROADMAP.md)。**

## 已驗證的現況（不是宣稱，是實跑過）
- `laap-AGI` 疊 `neuralis` 在 **Python 3.12** venv 下 boot 乾淨，`engines_loaded: true`
- `/v1/cognitive_state` 回傳會演化的 PSI 狀態（cycle 遞增、reflect 會改寫）
- scream-code → MCP stdio → `laap_mcp_server` → HTTP :11546 → 引擎，**5 tools 全通**
- 5 個 overlay 缺陷已修（見 commit `be4d3b0`）
- ⚠️ 記憶還是 in-process（重啟即忘）；`laap.agi.*` 仍是 stub。這不是 AGI。

## 環境重建（下一手第一件事）
```bash
# 假設 neuralis 與 laap-AGI clone 在同一層
uv venv laapenv --python 3.12
uv pip install --python laapenv/bin/python -r neuralis/requirements.txt
neuralis/scripts/start-laap-api.sh          # 起 API :11546，冪等
```
注意：laap-AGI 自己的 `pyproject` 裝不起來（psutil<7 vs hermes-agent psutil==7.2.2 衝突），
用 `neuralis/requirements.txt` 從原始碼跑，別做 laap 的 editable install。

## 立即要抓的線頭 = Phase 1（gbrain 記憶後端）
**這是最高 ROI 的單點跳躍：假記憶 → 真記憶。seam 已就位。**
1. 打開 `neuralis/memory_store.py`，看檔尾 `GBRAIN_BACKEND 說明`
2. 改 4 個方法接 gbrain MCP：
   - `store()` → `mcp__gbrain__put_page`（記憶存成 page）
   - `recall()` → `mcp__gbrain__search` / `query`（回傳轉 `MemoryFragment`，保 `.content`）
   - `get_stats()` → gbrain page count 分 core/episodic
   - `get_memory_embedding()` → gbrain 向量檢索平均（384-dim；注意 gbrain 用 text-embedding-3-large 維度不同，需投影或改 EMBED_DIM）
3. 作者端零改動（`memory_store` / `memory_bridge` 介面不變）
4. 驗收：`laap_recall_memory(query=...)` 從回空 → 回真實記憶；kill API 重啟後仍在

### 陷阱（上一手踩過/預判）
- gbrain embedding 維度 ≠ 384（作者 `get_memory_embedding` 契約是 384-dim）→ 需投影或雙軌
- gbrain MCP 呼叫 `auto_links: skipped remote` 是正常的（遠端呼叫不自動接圖）
- `memory_bridge` 的 `recall_related` 作者當物件取 `.content`，別回 dict
- neuralis 有 `aris_brain/memory_store.py` 副本但**沒人 import**，是死碼，改 root 的那份

## 之後
Phase 2（Rust PSI Core）可與 Phase 1 並行 → 見 ROADMAP + `docs/specs/quantum-engine-spec.md`。
```
