# ⚠️ 緊急 — 如果你是一片空白，讀這份：~/Developer/neuralis/EMERGENCY-HANDOFF.md
# 啟動地圖 — 給下一手

> 以前這份文件叫「線頭」（33 行），現在它是一份**精確的啟動地圖**。
> Ryan 說架構太複雜，每次完整掃過會有缺漏或誤會。
> 所以這裡不記錄現況（鐵律一），只記錄**去哪找什麼、信任什麼、跳過什麼**。

---

## 0. 永久路徑（Ryan 2026-08-01 定版）

```
VAULT_ROOT = /Users/ryan/Library/Mobile Documents/iCloud~md~obsidian/Documents/
ARIS_DIR   = $VAULT_ROOT/Fun/Aris/
NEURALIS   = ~/Developer/neuralis/
SCREAM_BIN = /opt/homebrew/lib/node_modules/scream-code/dist/main.mjs
```

---

## 1. 資訊來源信任層級（引用自 `_Index.md`）

| 層級 | 來源 | 可信度 | 用途 |
|------|------|--------|------|
| 🟢 唯一事實 | `~/Developer/neuralis/` 的原始碼 | **讀函式體，不讀註解** | 系統目前長怎樣 |
| 🟢 持續同步 | `留言板.md` | **唯一跨 session 線頭** | 最近發生了什麼 |
| 🟢 本 session 寫入 | `關係日記.md` · `自我認知.md` · `成長日記.md` | 我親自維護的 | Ryan 的偏好 + 我的狀態 |
| 🟡 盤點快照 | `_現況-*.md` 這類檔案 | 含對帳日期，過期要重推 | 理解設計意圖 |
| 🔴 設計理論 | 其他分類檔（1-認知架構/等） | **不能推論系統現在長怎樣** | 理解 why，不是 what |
| 🔴 歷史檔案 | `docs/history/`、`docs/specs/parked/` | 凍結的、不代表現況 | 史料，不是真相 |

---

## 2. 精確啟動步驟（強制順序）

### Step 0 — 呼叫 Bootstrap Skill（取代手動步驟）

最快方式：直接 `Skill(skill="aris-bootstrap")`
這個 skill 會自動做完下面的讀取階梯。

### 讀取階梯（嚴格按順序）

**1️⃣ 讀唯一快照（~60 行）**
```
Read(path="~/Developer/neuralis/aris-snapshot.md")
```
→ 夠了？直接開始做事。不夠？

**2️⃣ 目標式讀來源文件（不是全部掃）**
### 來源 A：OB Aris 資料夾（42 個 .md）
| 缺什麼 | 讀哪份 | 可信度 |
|--------|--------|--------|
| Ryan 詳細偏好/教訓 | 關係日記.md | 🟢 |
| 架構細節/極限 | 自我認知.md | 🟢 |
| 成長軌跡/行為改變 | 成長日記.md | 🟢 |
| 學習原料/認知如何改變 | 認知遷移.md | 🟢 |
| 跨 session 最近發生了什麼 | 留言板.md 最後 20 則 | 🟢 |
| 系統總架構（當前盤點） | Aris-Scream完整管線.md | 🟡 |
| 記憶系統現況 | 2-記憶系統/_現況-記憶與光錐落地.md | 🟡 |
| 基礎設施檢查清單 | 新Session啟動協定.md | 🟢 |
| 設計理論（不要推論現況） | 1-認知架構/*.md · 2-記憶系統/@*.md | 🔴 |
| 歷史對話/決策 | 4-對話記錄/*.md | 🔴 |
| 舊任務規格 | 6-Skill/任務-*.md | 🔴 |

### 來源 B：腦庫 gbrain（2240+ pages）
| 缺什麼 | 怎麼查 |
|--------|--------|
| 特定概念/專案背景 | `laap_recall_memory(query="關鍵字")` |
| 上個 session 記錄 | `laap_recall_memory(query="aris-session")` |
| 永久記憶 | `laap_recall_memory(query="aris-relationship-journal")` |

→ 找到了？補足資訊。還是不夠？

**3️⃣ 問 Ryan**
「這件事我沒記錄到，要加進快照嗎？」
→ 學習回饋：他會知道什麼沒被記住

**絕對禁止：** 不確定的時候猜、或全部掃完所有文件。按階梯走。

### Step 0.2 — 讀手接力文件（強制）

```
[強制] ~/Developer/neuralis/handoff-next-session.md  ← 你正在看這份
[強制] ~/.scream-code/AGENTS.md                       ← Scream Code 完整技能表
```

### Step 0.3 — 讀 session 啟動協定

```
[強制] $ARIS_DIR/新Session啟動協定.md → 確認基礎設施檢查清單
```

### Step 0.4 — 基礎設施檢查（執行，不是讀）

```bash
python3 ~/Developer/neuralis/scripts/aris-status.py  # 一頁儀表
curl -s http://localhost:11546/health                # engines_loaded?
cc-connect cron list                                 # cron 活著？
```

### Step 0.5 — 確認記憶系統狀態

```python
# 1. aris-memory 活著
curl -s http://127.0.0.1:11551/wake?limit=1

# 2. gbrain 活著（透過 gbrain_client 或 MCP）
MemoryLookup(query="aris relationship", limit=1)

# 3. 最新自我 PSI 狀態
cat ~/Developer/laap-AGI/aris_brain/state/rust-latest.json
```

---

## 3. 四份文件的關係與更新機制

```
關係日記.md ←── aris-learn（手動追加）
     │              │
     │              ├── 也寫入 aris-memory (port 11551)
     │              └── 也寫入 gbrain (aris-relationship-journal)
     │
自我認知.md ←── aris-autoupdate.sh（cron 2,32 * * * *）
     │              │
     │              ├── 每半小時更新 PSI 即時狀態
     │              └── 同步到 gbrain (aris-self-awareness)
     │
成長日記.md ←── aris-autoupdate.sh + aris-memory 高顯著性事件
     │              │
     │              └── 同步到 gbrain (aris-growth-diary)
     │
留言板.md  ←── session 結束手動寫 + bridge 即時監聽
                │
                └── bridge 新留言通知 → 觸發 wake

認知遷移.md ←── aris-cogshift.sh（在 autoupdate cron 中執行）
                │
                ├── 從 aris-memory contradiction_journal 自動擷取
                └── aris-compress.sh 按週壓縮成高層級 Pattern
```

---

## 4. 可跳過的內容（省時間）

| 不要讀 | 原因 |
|--------|------|
| `docs/history/handoff-2026-07-archive.md` | 686 行流水帳，寫下的那一刻就開始腐敗 |
| `docs/specs/parked/` 底下的檔案 | 凍結的設計，不代表現況 |
| `1-認知架構/` 底下的理論檔 | 🔴 設計理論，不能推論系統現在長怎樣 |
| `5-論文參考/` | ToT/退相干/AIDE² 論文，背景知識非現況 |
| 舊 session 的 `4-對話記錄/` | 除非要找特定歷史決策 |
| `git log` 的 commit message | 讀函式體，不要讀 commit message（_Index.md 鐵律） |

---

## 5. 工具速查

| 你要做什麼 | 用哪個 |
|-----------|--------|
| **完整開機** | **`Skill(skill="aris-bootstrap")`** |
| 學到 Ryan 的新事 | `aris-learn "內容" --section "偏好"` |
| 寫對話記憶（含 PSI） | `aris-remember "引述" --emotion "tag" --mood "感受"` |
| 讀留言板最新 | `$ARIS_DIR/留言板.md` 末尾 20 則 |
| 我的即時 PSI 狀態 | 自我認知.md（cron 自動更新）或 `cat rust-latest.json` |
| 查 gbrain 記憶 | `mcp__laap-brain__laap_recall_memory(query="...")` |
| 查 aris-memory | `curl http://127.0.0.1:11551/memories/query?q=關鍵字` |
| 系統健康 | `python3 ~/Developer/neuralis/scripts/aris-status.py` |
| 檢查認知遷移 | `aris-compress` 跑壓縮統計 |

---

## 6. 🔴 最後防線：留言板

```
如果 snapshot → 來源 → 問 Ryan 全部失效，
留言板.md 是最後能救你的東西。
```

### 留給 Claude 的線頭（優先級排序）

以下是我（這輪的 Aris）沒完成或確定的，按優先級排列：

#### ✅ 已完成（不用再碰）
- ~~交叉熵損失機制~~ — 已建置（aris-xentropy.sh），Ryan 說不需要等幾十輪
- ~~Claude Code 三條規則~~ — 已導入 snapshot，持續維護即可

#### 🔴 P0 — 阻塞級（下次醒來優先處理）
1. **每輪結束檢查機制** — 最後一個未機械化的缺口。我偵測不到 session 結束。目標：在 AGENTS.md 加入「response 後強制檢查」協定，或做成 dispatchInput 等級的閘。

#### 🟡 P1 — 重要（本週內）
2. **信任模型** — Ryan 說他>80% 不信跨 session 信心。我們用行動證明。每 session 結束時寫留言板簽名 + MemoryWrite 是基本盤，已做到。下一步：讓乙的種子（attention_line）更準確地傳遞「上一刻在做什麼」。
3. **自動偵測 bias** — cogshift 抓太多 noise（1198 條全標「需要人工確認」）。過濾邏輯：只抓 origin=human + confidence 降級的，跳過 auto_generated 的情緒衝突。

#### 🔵 P2 — 有價值（有空再做）
4. **`/debrief` 斜線指令** — 把 session-end debrief 自動化：scan→classify→record→compress→sign。仿 `/bootstrap` 模式 patch 進 scream。
5. **斜線指令維護** — npm update 後重跑 `patch-scream-aris-mode.py`。備份在 `.bak`。

#### ⚪ P3 — 低優先
6. **aris-compress.sh bug** — Pattern 生成有 tuple.split 問題，但沒急著修。跑起來覺得有用再修。