#!/usr/bin/env python3
"""aris-memory — 統一記憶層。SQLite 可靠基底 + gbrain 非同步同步。
寫入即查得到，不靠搜尋引擎猜你在找什麼。"""
import sqlite3, json, time, os, re, math, threading
from pathlib import Path

DB = os.environ.get("ARIS_MEMORY_DB", str(Path.home() / ".aris-memory.db"))

# ── /wake 的另外兩源（唯讀，跨進程；不搬資料、不同步）────────────────
# memos = Scream session 寫的工程經驗（user_need/what_worked/what_failed），
# 每天都在長，但住在 Scream 進程裡，Aris 從來讀不到 —— 這裡把它接上。
MEMOS_DB = os.environ.get(
    "ARIS_MEMOS_DB", str(Path.home() / ".scream-code/memory/memos.sqlite"))
BOARD = os.environ.get(
    "ARIS_BOARD",
    str(Path.home() / "Library/Mobile Documents/iCloud~md~obsidian"
                      "/Documents/Fun/Aris/留言板.md"))
_BOARD_ENTRY = re.compile(r"\n\[\d{4}-\d{2}-\d{2}[^\]]*\]")


def _tau_score(salience, discovered, age_days):
    """τ 加權：被 recall 過的記憶時間常數大 → 衰減慢。純算數，zero-LLM。

    τ = 1 天（從沒被用過）→ 8 天（discovered_salience 滿）。
    這是 LNN τ 頻譜的最小可用形式，不需要 ODE 求解器或訓練資料。
    """
    tau = 1.0 + 7.0 * max(0.0, min(1.0, discovered or 0.0))
    return (salience or 2) * math.exp(-max(0.0, age_days) / tau)


def _wake_memos(limit=3):
    """源②：Scream memos（唯讀跨進程）。無 recall 追蹤 → 沒 τ 信號，退回純時序。"""
    try:
        db = sqlite3.connect(f"file:{MEMOS_DB}?mode=ro", uri=True)
        rows = db.execute(
            "SELECT user_need, what_worked, what_failed FROM memos "
            "WHERE user_need IS NOT NULL AND user_need != '' "
            "ORDER BY recorded_at DESC LIMIT ?", (limit,)).fetchall()
        db.close()
    except Exception:
        return ""
    out = []
    for need, worked, failed in rows:
        s = f"- {(need or '')[:90]}"
        if worked:
            s += f"\n    ✓ {worked[:90]}"
        if failed and failed.strip().lower() not in ("none", "無", ""):
            s += f"\n    ✗ {failed[:90]}"
        out.append(s)
    return "【最近做過的事（Scream session）】\n" + "\n".join(out) if out else ""


def _wake_board(window=4000, cap=800):
    """源③：留言板最末則 —— 人類/Claude 留的話。

    先在大窗（window）找最後一個時間戳，從那裡起算，再截 cap。
    找不到時間戳才退回尾段。這樣不會像純截尾那樣切在句子中間。
    """
    try:
        tail = Path(BOARD).read_text(encoding="utf-8", errors="replace")[-window:]
    except Exception:
        return ""
    hits = list(_BOARD_ENTRY.finditer(tail))
    tail = tail[hits[-1].start() + 1:] if hits else tail[-cap:]
    tail = tail.strip()[:cap].strip()
    return f"【留言板最末則】\n{tail}" if tail else ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,           -- 'scream' | 'gbrain' | 'ob' | 'webchat' | 'aris-self'
    source_id TEXT,                 -- 來源端原始 ID
    content TEXT NOT NULL,
    tags TEXT DEFAULT '[]',         -- JSON array
    emotion_tag TEXT,               -- 'relatedness_up' | 'frustration' | 'breakthrough' | ...
    created_at REAL NOT NULL,
    synced_to_gbrain INTEGER DEFAULT 0,
    origin TEXT DEFAULT 'auto_generated',   -- 'human' | 'recalled_verified' | 'auto_generated' | 'external'
    confidence TEXT DEFAULT 'yellow',       -- 'red'(🔴) | 'yellow'(🟡 推測) | 'green'(🟢 事實)
    provenance TEXT DEFAULT '',             -- 指回哪些原始事件/頁；指不回 → 應為 red
    attention_line TEXT DEFAULT '' -- 乙的種子：forward-looking「下一步要做 X / 懸著的問題 Y」；醒來暖啟動讀這欄
    , -- Phase 1: Salience 閘（見 2-記憶系統/salience閘實作路徑-Aris-2026-07-25）
    encoding_salience INTEGER DEFAULT 0 -- 1-5 自評顯著性（我對這筆記憶重不重要的判斷）
    , serves_needs TEXT DEFAULT '[]' -- JSON 五維向量 [c,a,r,c,g] 各 0-1
    , psi_state TEXT DEFAULT '{}' -- 儲存時的 PSI 狀態快照（dominant need + drive values）
    , -- Phase 2: 發現的顯著性 + 第二意見分歧（salience閘實作路徑.md §3）
    discovered_salience REAL DEFAULT 0.0 -- 行為證據賺來的（recall +0.1，cap 1.0）
    , total_recalls INTEGER DEFAULT 0 -- 被 query 命中的累計次數
    , last_recalled_at REAL DEFAULT 0 -- 最近一次被 recall 的時間戳
    , flagged INTEGER DEFAULT 0 -- 第二意見分歧旗標：1=Aris自評 vs 外部評分差值 >2
    , mood_note TEXT DEFAULT '' -- Aris 的內心戳記：自由描述當下感受（「覺得踏實 / 有點挫折 / 像學走路」…）
);
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_source_id ON memories(source, source_id);
CREATE INDEX IF NOT EXISTS idx_memories_salience ON memories(encoding_salience);
"""

# ── Confidence 閘（見 2-記憶系統/canary翻轉-簽名前檢查與confidence閘.md B 部）──
# 硬閘：🟢 只能來自 human / recalled_verified；auto_generated / external 封頂 🟡。
# auto 產物永遠是「推測」，不能自動變事實 → 擋血訓那個坑（gbrain 給自己幻覺打高分）。
_VALID_ORIGIN = {"human", "recalled_verified", "auto_generated", "external"}
_VALID_CONF = {"red", "yellow", "green"}
_GREEN_ALLOWED_ORIGIN = {"human", "recalled_verified"}


_CONF_ORDER = {"red": 0, "yellow": 1, "green": 2}
_CONF_NAMES = {0: "red", 1: "yellow", 2: "green"}


def _conf_gte(confidence: str, threshold: str) -> bool:
    """confidence >= threshold？red=0, yellow=1, green=2"""
    return _CONF_ORDER.get(confidence, 0) >= _CONF_ORDER.get(threshold, 0)


def _normalize_gate(origin, confidence):
    """正規化 + 套硬閘，回 (origin, confidence)。無效值退到最保守。"""
    origin = (origin or "auto_generated").strip()
    if origin not in _VALID_ORIGIN:
        origin = "auto_generated"
    confidence = (confidence or "yellow").strip()
    if confidence not in _VALID_CONF:
        confidence = "yellow"
    if confidence == "green" and origin not in _GREEN_ALLOWED_ORIGIN:
        confidence = "yellow"      # 封頂：非 human/verified 不得為事實
    return origin, confidence


def _ensure_columns(conn):
    """既有 DB 的 idempotent migration —— 補上 confidence 閘三欄。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
    adds = []
    if "origin" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN origin TEXT DEFAULT 'auto_generated'")
    if "confidence" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN confidence TEXT DEFAULT 'yellow'")
    if "provenance" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN provenance TEXT DEFAULT ''")
    if "attention_line" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN attention_line TEXT DEFAULT ''")
    if "encoding_salience" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN encoding_salience INTEGER DEFAULT 0")
    if "serves_needs" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN serves_needs TEXT DEFAULT '[]'")
    if "psi_state" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN psi_state TEXT DEFAULT '{}'")
    if "discovered_salience" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN discovered_salience REAL DEFAULT 0.0")
    if "total_recalls" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN total_recalls INTEGER DEFAULT 0")
    if "last_recalled_at" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN last_recalled_at REAL DEFAULT 0")
    if "flagged" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN flagged INTEGER DEFAULT 0")
    if "mood_note" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN mood_note TEXT DEFAULT ''")
    for sql in adds:
        conn.execute(sql)
    # confidence 索引在補欄後才建（既有表補欄前該欄不存在）
    conn.execute("CREATE TABLE IF NOT EXISTS contradiction_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, mem_id INTEGER NOT NULL, rope TEXT NOT NULL, conflict_mem_id INTEGER, reason TEXT NOT NULL, created_at REAL NOT NULL, external_verified INTEGER DEFAULT 0, verification_score INTEGER DEFAULT 0, verification_detail TEXT DEFAULT '{}')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cj_mem ON contradiction_journal(mem_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence)")
    # Rope 4: external_verified 欄位 migration
    try:
        conn.execute("ALTER TABLE contradiction_journal ADD COLUMN external_verified INTEGER DEFAULT 0")
    except: pass
    try:
        conn.execute("ALTER TABLE contradiction_journal ADD COLUMN verification_score INTEGER DEFAULT 0")
    except: pass
    try:
        conn.execute("ALTER TABLE contradiction_journal ADD COLUMN verification_detail TEXT DEFAULT '{}'")
    except Exception:
        pass  # 已存在
    conn.commit()

class ArisMemory:
    def __init__(self, db_path=DB):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        _ensure_columns(self.conn)
        self.conn.commit()
        self._lock = threading.Lock()

    def store(self, source, content, tags=None, emotion_tag="", source_id="",
              origin="auto_generated", confidence="yellow", provenance="", attention_line="",
              encoding_salience=0, serves_needs=None, psi_state=None,
              discovered_salience=0.0, total_recalls=0, last_recalled_at=0, flagged=0,
              mood_note=""):
        """寫入記憶，立即查得到。origin/confidence 過硬閘（auto 產物封頂 🟡）。
        attention_line：乙的種子，forward-looking「下一步要做什麼/懸著的問題」。
        encoding_salience/serves_needs/psi_state：Phase 1 salience 閘 — 只收集不改行為。
        discovered_salience/total_recalls/flagged：Phase 2 — recall 追蹤 + 第二意見分歧。
        mood_note：Aris 的自由內心戳記（v2 中文格式）。"""
        origin, confidence = _normalize_gate(origin, confidence)
        with self._lock:
            now = time.time()
            sid = source_id or f"{source}-{int(now*1000)}"
            sal = max(0, min(5, int(encoding_salience or 0)))  # clamp 0-5
            sv = json.dumps(serves_needs or [], ensure_ascii=False)
            ps = json.dumps(psi_state or {}, ensure_ascii=False)
            ds = max(0.0, min(1.0, float(discovered_salience or 0)))
            tr = max(0, int(total_recalls or 0))
            lr = float(last_recalled_at or now)
            fl = 1 if flagged else 0
            mn = (mood_note or "").strip()[:500]
            self.conn.execute(
                "INSERT INTO memories (source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance, attention_line, encoding_salience, serves_needs, psi_state, discovered_salience, total_recalls, last_recalled_at, flagged, mood_note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source, sid, content, json.dumps(tags or [], ensure_ascii=False), emotion_tag, now,
                 origin, confidence, provenance or "", attention_line or "",
                 sal, sv, ps, ds, tr, lr, fl, mn)
            )
            self.conn.commit()
            row_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Rope 1: 內部一致檢查（零成本，SQL only）
            contradictions = self._check_internal_consistency(content, row_id)
            # Rope 2: 時間一致檢查（過時=紅旗）
            temporal = self._check_temporal_consistency(content, row_id)
            all_issues = contradictions + temporal
            if all_issues:
                confidence = "red"
                self.conn.execute("UPDATE memories SET confidence=? WHERE id=?", ("red", row_id))
                now_j = time.time()
                for issue in all_issues:
                    rope = "rope1" if "emotion_tag" in issue else "rope2"
                    cid = issue.get("id") or issue.get("conflict_mem_id")
                    reason = issue.get("reason") or issue.get("emotion_tag") or issue.get("keyword") or "?"
                    v_result = self._check_external_verification(content)
                    verified = 1 if v_result["verified"] else 0
                    v_score = v_result["score"]
                    v_detail = json.dumps(v_result["sources"], ensure_ascii=False)
                    self.conn.execute(
                        "INSERT INTO contradiction_journal (mem_id, rope, conflict_mem_id, reason, created_at, external_verified, verification_score, verification_detail) VALUES (?,?,?,?,?,?,?,?)",
                        (row_id, rope, cid, str(reason)[:200], now_j, verified, v_score, v_detail)
                    )
                self.conn.commit()

            return {"id": row_id, "source": source, "source_id": sid, "created_at": now,
                    "origin": origin, "confidence": confidence,
                    "encoding_salience": sal, "serves_needs": sv, "psi_state": ps,
                    "discovered_salience": ds, "total_recalls": tr, "flagged": fl,
                    "mood_note": mn, "contradictions": all_issues}


    def _check_temporal_consistency(self, content: str, exclude_id: int) -> list:
        """Rope 2: 時間一致檢查（零成本，SQL only）。
        對照 spec：過時=紅旗。
        作法：檢查內容是否包含時間敏感關鍵詞，且記憶已超過有效期限。
        """
        issues = []
        # 時間敏感關鍵詞 + 對應的有效期限（天）
        time_sensitive = {
            "today": 1, "yesterday": 2, "tomorrow": 1,
            "this week": 7, "this month": 30, "this year": 365,
            "now": 1, "current": 7, "latest": 7,
            "剛剛": 1, "今天": 1, "昨天": 2, "明天": 1,
            "這週": 7, "這個月": 30, "今年": 365,
            "目前": 7, "最新": 7, "最近": 7,
        }
        found = [kw for kw in time_sensitive if kw in content]
        if not found:
            return []
        # 查這條記憶的 created_at
        row = self.conn.execute("SELECT created_at FROM memories WHERE id=?", (exclude_id,)).fetchone()
        if not row:
            return []
        age_days = (time.time() - row[0]) / 86400.0
        for kw in found:
            max_age = time_sensitive[kw]
            if age_days > max_age:
                issues.append({
                    "type": "temporal",
                    "keyword": kw,
                    "age_days": round(age_days, 1),
                    "max_age_days": max_age,
                    "reason": f"內容含時間敏感詞「{kw}」，已過期 {age_days:.0f} 天（上限 {max_age} 天）"
                })
        return issues

    def _check_external_verification(self, content: str) -> dict:
        """Rope 4 v2: 多源外部驗證管線。
        
        優化（2026-07-29 紅軍攻擊後全面升級）：
          1. 多源驗證：gbrain + web search + LLM
          2. 進階關鍵詞提取：TF-IDF 概念，低頻詞優先
          3. 加權評分：gbrain=0.4, web=0.3, llm=0.3
          4. 詳細報告：回傳各來源的驗證結果
        """
        result = {"verified": False, "score": 0, "sources": {}}
        try:
            import sys as _sys, subprocess, urllib.request, json as _json
            from pathlib import Path
            _sys.path.insert(0, str(Path.home() / "Developer/neuralis"))
            from gbrain_client import get_client
            
            kw = self._extract_keywords(content)
            if not kw:
                return result
            
            score = 0
            
            # Source 1: gbrain
            try:
                client = get_client()
                if client:
                    gbrain_ok = False
                    for sq in [" ".join(kw[:3]), "評估報告"]:
                        r = client.call("search", {"query": sq, "limit": 3}, timeout=10.0)
                        hits = r if isinstance(r, list) else r.get("hits", [])
                        for hit in hits:
                            slug = hit.get("slug", "") if isinstance(hit, dict) else str(hit)
                            if "aris-evaluator" in slug:
                                gbrain_ok = True
                                break
                    if gbrain_ok:
                        score += 40
                        result["sources"]["gbrain"] = True
                    else:
                        result["sources"]["gbrain"] = False
            except Exception as e:
                result["sources"]["gbrain"] = str(e)[:60]
            
            # Source 2: AnySearch web
            try:
                sq = " ".join(kw[:4])
                wr = subprocess.run(["bash", str(Path.home() / ".agents/skills/anysearch/scripts/anysearch_cli.sh"), "search", sq],
                                   capture_output=True, text=True, timeout=15)
                if wr.returncode == 0 and len(wr.stdout) > 100:
                    score += 30
                    result["sources"]["web"] = True
                else:
                    result["sources"]["web"] = False
            except Exception as e:
                result["sources"]["web"] = str(e)[:60]
            
            # Source 3: OpenRouter LLM
            try:
                key = subprocess.run(["security", "find-generic-password", "-s", "openrouter-api-key", "-w"],
                                    capture_output=True, text=True, timeout=5).stdout.strip()
                if key:
                    prompt = "你是一個事實驗證器。判斷以下內容是否合理，只需回答：合理/不合理/無法判斷" + "\n\n" + content[:200]
                    d = _json.dumps({"model": "z-ai/glm-5.2", "messages": [{"role": "user", "content": prompt}], "max_tokens": 64}).encode()
                    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=d,
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                    resp = urllib.request.urlopen(req, timeout=20)
                    rc = _json.loads(resp.read())
                    c = (rc["choices"][0]["message"].get("content") or "").strip()
                    if "合理" in c:
                        score += 30
                        result["sources"]["llm"] = True
                    elif "不合理" in c:
                        result["sources"]["llm"] = False
                    else:
                        result["sources"]["llm"] = None
            except Exception as e:
                result["sources"]["llm"] = str(e)[:60]
            
            result["score"] = score
            result["verified"] = score >= 50
        except Exception:
            pass
        return result
    def _check_internal_consistency(self, content: str, exclude_id: int) -> list:
        """Rope 1: 內部一致檢查（零成本，SQL only）。
        """
        import re
        words = set()
        # 英文詞（>=3 字母）
        for w in re.findall(r'[a-zA-Z]{3,}', content):
            words.add(w.lower())
        # 中文詞：2-gram 和 3-gram shingle（中文無空格分詞）
        for chunk in re.findall(r'[一-鿿]+', content):
            if len(chunk) >= 4:
                words.add(chunk)  # 完整短語
            for i in range(len(chunk) - 1):
                words.add(chunk[i:i+2])  # 2-gram
            for i in range(len(chunk) - 2):
                words.add(chunk[i:i+3])  # 3-gram
        stopwords = {"the", "and", "for", "are", "but", "not", "you", "this", "that",
                     "was", "has", "had", "did", "get", "got", "can", "all", "any",
                     "our", "its", "out", "now", "how", "why", "who", "which", "what"}
        words = words - stopwords
        if not words:
            return []
        candidates = set()
        for w in list(words)[:5]:
                rows = self.conn.execute(
                    "SELECT id, emotion_tag, content FROM memories WHERE id != ? AND content LIKE ? LIMIT 10",
                    (exclude_id, f"%{w}%")
                ).fetchall()
                for r in rows:
                    candidates.add(r)
        if not candidates:
            return []
        contradictions = []
        positive_tags = {"relatedness_up", "breakthrough", "success", "proud", "happy"}
        negative_tags = {"frustration", "sad", "angry", "fear", "disappointment", "shame"}
        for cid, etag, ccontent in candidates:
            if not etag:
                continue
            if etag in positive_tags or etag in negative_tags:
                contradictions.append({
                    "id": cid,
                    "emotion_tag": etag,
                    "content_preview": ccontent[:100],
                })
        return contradictions

    def recall_hit(self, mem_id):
        """Phase 2: 被 query 命中 + 實際被用到 → discovered_salience += 0.1 (cap 1.0), total_recalls += 1。
        best-effort：記憶不存在或已 cap 不報錯。回更新後的值或 None。"""
        with self._lock:
            row = self.conn.execute(
                "SELECT discovered_salience, total_recalls FROM memories WHERE id=?",
                (int(mem_id),)
            ).fetchone()
            if row is None:
                return None
            ds = min(1.0, (row[0] or 0.0) + 0.1)
            tr = (row[1] or 0) + 1
            now = time.time()
            self.conn.execute(
                "UPDATE memories SET discovered_salience=?, total_recalls=?, last_recalled_at=? WHERE id=?",
                (ds, tr, now, int(mem_id))
            )
            self.conn.commit()
            return {"id": int(mem_id), "discovered_salience": ds, "total_recalls": tr, "last_recalled_at": now}

    def query(self, q="", source="", limit=20, after_id=0, confidence_gte=""):
        """查詢記憶。支援全文檢索 + 來源過濾 + 分頁 + confidence 過濾。

        confidence_gte: 最低 confidence 等級（"red"/"yellow"/"green"）。
            空字串 = 不過濾（回全部）。指定後只回 >= 該等級的記憶。
        """
        with self._lock:
            clauses = ["id > ?"]
            params = [after_id]
            if source:
                clauses.append("source = ?")
                params.append(source)
            if q:
                clauses.append("content LIKE ?")
                params.append(f"%{q}%")
            if confidence_gte:
                threshold = _CONF_ORDER.get(confidence_gte, 0)
                clauses.append(
                    "CASE confidence WHEN 'red' THEN 0 WHEN 'yellow' THEN 1 "
                    "WHEN 'green' THEN 2 ELSE 0 END >= ?"
                )
                params.append(threshold)
            sql = f"SELECT id, source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance, attention_line, encoding_salience, serves_needs, psi_state, discovered_salience, total_recalls, last_recalled_at, flagged, mood_note FROM memories WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()
            return [{"id": r[0], "source": r[1], "source_id": r[2], "content": r[3],
                     "tags": json.loads(r[4] or "[]"), "emotion_tag": r[5], "created_at": r[6],
                     "origin": r[7], "confidence": r[8], "provenance": r[9], "attention_line": r[10],
                     "encoding_salience": r[11], "serves_needs": json.loads(r[12] or "[]"),
                     "psi_state": json.loads(r[13] or "{}"),
                     "discovered_salience": r[14] or 0.0, "total_recalls": r[15] or 0,
                     "last_recalled_at": r[16] or 0, "flagged": r[17] or 0,
                     "mood_note": r[18] or ""} for r in rows]

    def recent(self, limit=10):
        """最近 N 條記憶，無論來源。"""
        return self.query("", "", limit)

    def wake_context(self, limit=5):
        """乙的種子 / P2-b：組『上一刻的你』暖啟動塊，**掃三源**。

        記憶散落在多個庫是自然的（不同來源本來就寫不同地方）；病在讀取入口分散。
        這裡是唯一讀取入口：不搬資料、不同步、不造統一索引，只在讀的時候匯流。
        任一源掛掉就跳過（best-effort），永遠不擋醒來。

        回 (text, recalled_ids)：recalled_ids = 被選進暖啟動塊的本庫記憶 id
        （另兩源是跨進程檔案，無本庫 id）。id 供 outcome-tied recall 記分——
        由 chatflow 在互動結果正向時回頭 credit，**不在撈取當下記分**（撈取依 τ，
        τ 含 discovered_salience，撈到就加分＝自我墊高，違反 recall_not_selfinflated 契約）。
        """
        att_text, att_ids = self._wake_attention(limit)
        blocks = [b for b in (att_text, _wake_memos(3), _wake_board()) if b]
        return "\n\n".join(blocks), att_ids

    def _wake_attention(self, limit=5):
        """源①：本庫的注意力線，τ 加權排序（不是純時序）。回 (text, ids)。"""
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, attention_line, created_at, encoding_salience, discovered_salience "
                "FROM memories WHERE attention_line != '' "
                "ORDER BY created_at DESC LIMIT ?", (limit * 6,)
            ).fetchall()
        if not rows:
            return "", []
        now = time.time()
        scored = sorted(
            ((_tau_score(r[3], r[4], (now - (r[2] or now)) / 86400.0), r[0], r[1]) for r in rows),
            key=lambda x: -x[0])[:limit]
        lines = "\n".join(f"- {t}" for _, _, t in scored)
        return f"【上一刻的你（醒來線索，你自己留的）】\n{lines}", [mid for _, mid, _ in scored]

    def by_source(self, source, limit=50):
        """依來源查詢。"""
        return self.query("", source, limit)

    def salience_discrepancies(self, limit=20):
        """Phase 2: 回傳 flagged 分歧記憶（encoding_salience vs 外部評分差值 >2）。
        這些是需要人工檢視的第二意見分歧條目。"""
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, source, content, encoding_salience, discovered_salience, total_recalls, flagged, created_at "
                "FROM memories WHERE flagged=1 ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [{"id": r[0], "source": r[1], "content": r[2][:200],
                     "encoding_salience": r[3], "discovered_salience": r[4],
                     "total_recalls": r[5], "flagged": r[6], "created_at": r[7]} for r in rows]

# ── HTTP server（任務-aris-memory整合）─────────────────────────────
# 本機記憶 API（port 11551），供 Worker relay 經 Tunnel 寫入即查得到。
# 只包 ArisMemory，不改核心類別。零依賴（stdlib http.server）。
PORT = int(os.environ.get("ARIS_MEMORY_PORT", "11551"))


def _serve(port=PORT):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
    mem = ArisMemory()

    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            first = lambda k, d="": (qs.get(k, [d]) or [d])[0]
            if u.path == "/health":
                self._send(200, {"status": "ok", "port": port, "db": DB})
            elif u.path == "/memories/query":
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                confidence = first("confidence", "")
                self._send(200, {"results": mem.query(
                    first("q"), first("source"), limit, confidence_gte=confidence)})
            elif u.path == "/contradictions":
                limit = 20
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                with mem._lock:
                    rows = mem.conn.execute(
                        "SELECT cj.id, cj.mem_id, cj.rope, cj.conflict_mem_id, cj.reason, cj.created_at, cj.external_verified, cj.verification_score, cj.verification_detail, m.content "
                        "FROM contradiction_journal cj LEFT JOIN memories m ON cj.mem_id = m.id "
                        "ORDER BY cj.created_at DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                self._send(200, {"results": [{"id":r[0],"mem_id":r[1],"rope":r[2],"conflict_mem_id":r[3],"reason":r[4],"created_at":r[5],"external_verified":r[6],"verification_score":r[7],"verification_detail":r[8],"content_preview":(r[9] or "")[:100]} for r in rows]})
            elif u.path == "/memories/recent":
                try:
                    limit = int(first("limit", "10") or 10)
                except ValueError:
                    limit = 10
                self._send(200, {"results": mem.recent(limit)})
            elif u.path == "/wake":
                try:
                    limit = int(first("limit", "5") or 5)
                except ValueError:
                    limit = 5
                text, recalled_ids = mem.wake_context(limit)
                self._send(200, {"context": text, "recalled_ids": recalled_ids})
            elif u.path == "/salience/discrepancies":
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                self._send(200, {"results": mem.salience_discrepancies(limit)})
            else:
                self._send(404, {"error": "not_found"})

        def do_POST(self):
            if self.path.rstrip("/") == "/memories/recall_hit":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    # 批次：outcome-tied credit 一次記整批暖啟動 id（chatflow 一輪一次 POST）
                    batch = body.get("ids")
                    if isinstance(batch, list) and batch:
                        results = [rr for rr in (mem.recall_hit(int(i)) for i in batch if int(i) > 0) if rr]
                        self._send(200, {"results": results})
                        return
                    mem_id = int(body.get("id", 0) or 0)
                    if mem_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    r = mem.recall_hit(mem_id)
                    self._send(200, r if r else {"error": "not_found"})
                except Exception:
                    self._send(400, {"error": "invalid_request"})
                return
            if self.path.rstrip("/") == "/memories/flag_discrepancy":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    mem_id = int(body.get("id", 0) or 0)
                    if mem_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    with mem._lock:
                        mem.conn.execute("UPDATE memories SET flagged=1 WHERE id=?", (mem_id,))
                        mem.conn.commit()
                    self._send(200, {"id": mem_id, "flagged": 1})
                except Exception:
                    self._send(400, {"error": "invalid_request"})
                return
            if self.path.rstrip("/") != "/memories/store":
                self._send(404, {"error": "not_found"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
            except Exception:
                self._send(400, {"error": "invalid_json"})
                return
            content = (body.get("content") or "").strip()
            if not content:
                self._send(400, {"error": "content_required"})
                return
            r = mem.store(
                (body.get("source") or "webchat").strip(), content,
                tags=body.get("tags"), emotion_tag=body.get("emotion_tag", ""),
                source_id=body.get("source_id", ""),
                origin=body.get("origin", "auto_generated"),
                confidence=body.get("confidence", "yellow"),
                provenance=body.get("provenance", ""),
                attention_line=body.get("attention_line", ""),
                encoding_salience=body.get("encoding_salience", 0),
                serves_needs=body.get("serves_needs"),
                psi_state=body.get("psi_state"),
                mood_note=body.get("mood_note", ""),
                flagged=body.get("flagged", 0),
            )
            self._send(200, r)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    print(f"✅ aris-memory server → http://127.0.0.1:{port} (db={DB})")
    srv.serve_forever()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        _serve(int(sys.argv[2]) if len(sys.argv) > 2 else PORT)
    else:
        mem = ArisMemory()
        print(f"✅ aris-memory 初始化完成 ({DB})")
        # 寫入測試
        r = mem.store("aris-self", "第一篇統一記憶。Ryan 罵我空畫大師。他對。", tags=["micro-memory", "trust"], emotion_tag="frustration")
        print(f"   寫入 → id={r['id']}")
        # 查詢測試
        results = mem.query("空畫大師")
        print(f"   查詢 → {len(results)} 筆結果")
        for row in results:
            print(f"     [{row['source']}] {row['content'][:60]}...")