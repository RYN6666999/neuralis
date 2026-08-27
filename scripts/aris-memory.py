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


def _tau_score(salience, discovered, age_days):
    """τ 加權：被 recall 過的記憶時間常數大 → 衰減慢。純算數，zero-LLM。

    τ = 1 天（從沒被用過）→ 8 天（discovered_salience 滿）。
    這是 LNN τ 頻譜的最小可用形式，不需要 ODE 求解器或訓練資料。
    """
    tau = 1.0 + 7.0 * max(0.0, min(1.0, discovered or 0.0))
    return (salience or 2) * math.exp(-max(0.0, age_days) / tau)


def _wake_memos(limit=3):
    """源②：Scream memos（唯讀跨進程），僅限最近 7 天。無 recall 追蹤 → 沒 τ 信號，退回純時序。"""
    try:
        db = sqlite3.connect(f"file:{MEMOS_DB}?mode=ro", uri=True)
        cutoff = (time.time() - 7 * 86400) * 1000  # Scream 用毫秒
        rows = db.execute(
            "SELECT user_need, what_worked, what_failed FROM memos "
            "WHERE user_need IS NOT NULL AND user_need != '' "
            "AND recorded_at > ? "
            "ORDER BY recorded_at DESC LIMIT ?", (cutoff, limit)).fetchall()
        db.close()
    except Exception as e:
        print(f"[aris-memory] _wake_memos 異常（不影響主流程）: {e}", file=__import__('sys').stderr, flush=True)
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
    """源③：留言板 — 已移除（檔案不存在，2026-08-27）。"""
    return ""

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
    , event_type TEXT DEFAULT 'internal_thought' -- 'user_said' | 'tool_called' | 'decision' | 'internal_thought' | 'state_change'
    , causal_parent_id INTEGER DEFAULT 0 -- 上一筆 event id，串成因果鏈（0=根節點）
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
    if "event_type" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN event_type TEXT DEFAULT 'internal_thought'")
    if "causal_parent_id" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN causal_parent_id INTEGER DEFAULT 0")
    for sql in adds:
        conn.execute(sql)
    # confidence 索引在補欄後才建（既有表補欄前該欄不存在）
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence)")
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS decision_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, route TEXT NOT NULL, task_desc TEXT DEFAULT "", psi_energy REAL DEFAULT 0, psi_competence REAL DEFAULT 0.5, psi_certainty REAL DEFAULT 0.5, psi_growth REAL DEFAULT 0.5, success INTEGER DEFAULT 0, duration REAL DEFAULT 0, error TEXT DEFAULT "")")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_route ON decision_log(route)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_psi ON decision_log(psi_energy)")
    except:
        pass
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
              mood_note="", event_type="internal_thought", causal_parent_id=0):
        """寫入記憶，立即查得到。origin/confidence 過硬閘（auto 產物封頂 🟡）。
        attention_line：乙的種子，forward-looking「下一步要做什麼/懸著的問題」。
        encoding_salience/serves_needs/psi_state：Phase 1 salience 閘 — 只收集不改行為。
        discovered_salience/total_recalls/flagged：Phase 2 — recall 追蹤 + 第二意見分歧。
        mood_note：Aris 的自由內心戳記（v2 中文格式）。
        event_type：訊號分類（user_said / tool_called / decision / internal_thought / state_change）
        causal_parent_id：上一筆 event id，串成因果鏈（0=根節點）"""
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
            et = event_type if event_type in ('user_said','tool_called','tool_result','decision','internal_thought','state_change','session_end') else 'internal_thought'
            cid = max(0, int(causal_parent_id or 0))
            self.conn.execute(
                "INSERT INTO memories (source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance, attention_line, encoding_salience, serves_needs, psi_state, discovered_salience, total_recalls, last_recalled_at, flagged, mood_note, event_type, causal_parent_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source, sid, content, json.dumps(tags or [], ensure_ascii=False), emotion_tag, now,
                 origin, confidence, provenance or "", attention_line or "",
                 sal, sv, ps, ds, tr, lr, fl, mn, et, cid)
            )
            self.conn.commit()
            row_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            return {"id": row_id, "source": source, "source_id": sid, "created_at": now,
                    "origin": origin, "confidence": confidence,
                    "encoding_salience": sal, "serves_needs": sv, "psi_state": ps,
                    "discovered_salience": ds, "total_recalls": tr, "flagged": fl,
                    "mood_note": mn, "contradictions": [],
                    "event_type": et, "causal_parent_id": cid}


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
            # 2026-07-30 修復：salience 影響排序（encoding_salience 高的優先）
            # 讓 encoding_salience 從裝飾品變成實際影響 recall 順序
            sql = f"SELECT id, source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance, attention_line, encoding_salience, serves_needs, psi_state, discovered_salience, total_recalls, last_recalled_at, flagged, mood_note FROM memories WHERE {' AND '.join(clauses)} ORDER BY encoding_salience DESC, created_at DESC LIMIT ?"
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

    def register_ontology(self, name, type_name, purpose, relationships=None):
        """登錄一個元件到本體論。"""
        import time
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO ontology (name, type, purpose, relationships, status, updated_at) VALUES (?,?,?,?,?,?)",
                (name, type_name, purpose, json.dumps(relationships or []), "active", time.time())
            )
            self.conn.commit()

    def query_ontology(self, type_name="", status=""):
        """查詢本體論。"""
        with self._lock:
            clauses = ["1=1"]
            params = []
            if type_name:
                clauses.append("type = ?")
                params.append(type_name)
            if status:
                clauses.append("status = ?")
                params.append(status)
            rows = self.conn.execute(
                f"SELECT name, type, purpose, relationships, status FROM ontology WHERE {' AND '.join(clauses)} ORDER BY type, name"
            ).fetchall()
            return [{"name": r[0], "type": r[1], "purpose": r[2], "relationships": json.loads(r[3] or "[]"), "status": r[4]} for r in rows]

    def record_causal(self, cause_type, cause_value, effect_type, effect_value, outcome=0):
        """記錄一條因果鏈：A（cause）導致 B（effect），結果是 outcome。"""
        import time
        with self._lock:
            self.conn.execute(
                "INSERT INTO causal_chain (cause_type, cause_value, effect_type, effect_value, outcome, timestamp) VALUES (?,?,?,?,?,?)",
                (cause_type, cause_value, effect_type, effect_value, outcome, time.time())
            )
            self.conn.commit()

    def query_causal(self, cause_type="", effect_type="", min_occurrences=1):
        """查詢因果鏈，找出因果模式。"""
        with self._lock:
            clauses = ["1=1"]
            params = []
            if cause_type:
                clauses.append("cause_type = ?")
                params.append(cause_type)
            if effect_type:
                clauses.append("effect_type = ?")
                params.append(effect_type)
            rows = self.conn.execute(
                f"SELECT cause_type, cause_value, effect_type, effect_value, avg(outcome) as success_rate, count(*) as cnt FROM causal_chain WHERE {' AND '.join(clauses)} GROUP BY cause_type, effect_type, effect_value HAVING cnt >= ? ORDER BY cnt DESC",
                params + [min_occurrences]
            ).fetchall()
            return [{"cause": r[0], "cause_value": r[1], "effect": r[2], "effect_value": r[3], "success_rate": round(r[4] or 0, 3), "occurrences": r[5]} for r in rows]

    def lookahead(self, route, psi_energy, psi_competence):
        """前瞻分析：查詢類似 PSI 狀態下該 route 的歷史成功率。"""
        with self._lock:
            rows = self.conn.execute(
                "SELECT route, avg(success) as success_rate, count(*) as cnt, avg(psi_energy) as avg_en, avg(psi_competence) as avg_co FROM decision_log WHERE psi_energy BETWEEN ? AND ? AND psi_competence BETWEEN ? AND ? AND route = ?",
                (max(0, psi_energy-1), min(10, psi_energy+1), max(0, psi_competence-0.2), min(1, psi_competence+0.2), route)
            ).fetchall()
            if rows and rows[0][2] > 0:
                r = rows[0]
                return {"route": r[0], "success_rate": round(r[1] or 0, 3), "samples": r[2], "avg_energy": round(r[3] or 0, 2), "avg_competence": round(r[4] or 0, 2), "recommendation": "可以執行" if (r[1] or 0) >= 0.5 else "建議暫緩"}
            return {"route": route, "success_rate": 0, "samples": 0, "recommendation": "無歷史資料"}

    def session_replay(self, session_id="", limit=20):
        """從事件日誌和決策記錄重建上下文（Session replay）。"""
        import json, time
        from pathlib import Path
        
        channel_path = Path("/tmp/aris-scream-channel.jsonl")
        replay = {"session_id": session_id or ("replay-" + str(int(time.time()))), "events": [], "decisions": [], "summary": {}}
        
        # 1. 從 channel 讀取（含例外處理）
        events = []
        try:
            if channel_path.exists():
                with open(channel_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            events = []
        
        recent = events[-limit:] if events else []
        replay["events"] = [{"type": e.get("type","?"), "tool": e.get("tool",""), "ts": e.get("ts",0)} for e in recent]
        if events:
            tc = {}
            for e in events:
                t = e.get("tool", "?")
                tc[t] = tc.get(t, 0) + 1
            replay["summary"]["channel_events"] = len(events)
            replay["summary"]["tool_usage"] = tc
            replay["summary"]["last_event_ts"] = recent[-1]["ts"] if recent else 0
        
        # 2. 從 decision_log 讀取
        with self._lock:
            rows = self.conn.execute("SELECT route,count(*),avg(success),avg(psi_energy) FROM decision_log GROUP BY route ORDER BY count(*) DESC LIMIT ?", (limit,)).fetchall()
            replay["decisions"] = [{"route":r[0],"count":r[1],"success_rate":round(r[2] or 0,3),"avg_energy":round(r[3] or 0,2)} for r in rows]
            replay["summary"]["total_decisions"] = self.conn.execute("SELECT count(*) FROM decision_log").fetchone()[0]
        
        return replay

    def log_decision(self, route, task_desc="", psi_energy=0, psi_competence=0.5,
                       psi_certainty=0.5, psi_growth=0.5, success=0, duration=0, error=""):
        """記錄一次決策及其結果，供判斷力分析使用。"""
        import time
        with self._lock:
            self.conn.execute(
                "INSERT INTO decision_log (timestamp, route, task_desc, psi_energy, psi_competence, psi_certainty, psi_growth, success, duration, error) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), route, task_desc[:200], psi_energy, psi_competence, psi_certainty, psi_growth, 1 if success else 0, duration, error[:200])
            )
            self.conn.commit()
            return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def query_decision_stats(self, min_energy=0, max_energy=10, route="", limit=20):
        """查詢決策統計，支援 PSI 狀態過濾。"""
        with self._lock:
            clauses = ["psi_energy >= ?", "psi_energy <= ?"]
            params = [min_energy, max_energy]
            if route:
                clauses.append("route = ?")
                params.append(route)
            rows = self.conn.execute(
                f"SELECT route, count(*) as cnt, avg(success) as success_rate, avg(duration) as avg_dur, avg(psi_energy) as avg_en, avg(psi_competence) as avg_co FROM decision_log WHERE {' AND '.join(clauses)} GROUP BY route ORDER BY cnt DESC LIMIT ?",
                params + [limit]
            ).fetchall()
            return [{"route": r[0], "count": r[1], "success_rate": round(r[2] or 0, 3), "avg_duration": round(r[3] or 0, 1), "avg_energy": round(r[4] or 0, 2), "avg_competence": round(r[5] or 0, 2)} for r in rows]

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
            elif u.path == "/health/detailed":
                try:
                    total = mem.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                    has_attn = mem.conn.execute("SELECT COUNT(*) FROM memories WHERE attention_line != ''").fetchone()[0]
                    rec = mem.conn.execute("SELECT created_at FROM memories ORDER BY created_at DESC LIMIT 1").fetchone()
                    last_h = (time.time() - rec[0]) / 3600 if rec else -1
                    healthy = total > 0 and last_h < 24
                    self._send(200, {
                        "status": "ok",
                        "memories": total,
                        "with_attention_lines": has_attn,
                        "last_store_hours": round(last_h, 1) if last_h >= 0 else -1,
                        "wake_ok": len(mem.wake_context(1)[0]) > 0,
                        "healthy": healthy,
                    })
                except Exception as e:
                    self._send(500, {"status": "error", "error": str(e)[:100]})
            elif u.path == "/memories/query":
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                confidence = first("confidence", "")
                self._send(200, {"results": mem.query(
                    first("q"), first("source"), limit, confidence_gte=confidence)})
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
            elif u.path == "/decision/log":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    row_id = mem.log_decision(
                        route=body.get("route", "?"),
                        task_desc=body.get("task_desc", ""),
                        psi_energy=body.get("psi_energy", 0),
                        psi_competence=body.get("psi_competence", 0.5),
                        psi_certainty=body.get("psi_certainty", 0.5),
                        psi_growth=body.get("psi_growth", 0.5),
                        success=body.get("success", 0),
                        duration=body.get("duration", 0),
                        error=body.get("error", ""),
                    )
                    self._send(200, {"id": row_id})
                except Exception as e:
                    self._send(400, {"error": str(e)})
            elif u.path == "/ontology":
                self._send(200, {"results": mem.query_ontology(first("type", ""), first("status", ""))})
            elif u.path == "/causal":
                self._send(200, {"results": mem.query_causal(first("cause", ""), first("effect", ""), int(first("min", "1") or 1))})
            elif u.path == "/lookahead":
                rt = first("route", "")
                en = float(first("energy", "5") or 5)
                co = float(first("competence", "0.5") or 0.5)
                self._send(200, mem.lookahead(rt, en, co))
            elif u.path == "/session/replay":
                self._send(200, mem.session_replay(first("session_id", ""), int(first("limit", "20") or 20)))
            elif u.path == "/session/replay":
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                self._send(200, mem.session_replay(first("session_id", ""), limit))
            elif u.path == "/decision/stats":
                try:
                    min_en = float(first("min_energy", "0") or 0)
                    max_en = float(first("max_energy", "10") or 10)
                    rt = first("route", "")
                    limit = 20
                    try:
                        limit = int(first("limit", "20") or 20)
                    except ValueError:
                        limit = 20
                    self._send(200, {"results": mem.query_decision_stats(min_en, max_en, rt, limit)})
                except Exception as e:
                    self._send(400, {"error": str(e)})
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
            if self.path.rstrip("/") == "/ontology/register":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    mem.register_ontology(body.get("name","?"), body.get("type","?"), body.get("purpose",""), body.get("relationships",[]))
                    self._send(200, {"ok": True})
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/causal/record":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    mem.record_causal(body.get("cause_type","?"), body.get("cause_value",0), body.get("effect_type","?"), body.get("effect_value",""), body.get("outcome",0))
                    self._send(200, {"ok": True})
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/decision/log":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    row_id = mem.log_decision(
                        route=body.get("route", "?"),
                        task_desc=body.get("task_desc", ""),
                        psi_energy=body.get("psi_energy", 0),
                        psi_competence=body.get("psi_competence", 0.5),
                        psi_certainty=body.get("psi_certainty", 0.5),
                        psi_growth=body.get("psi_growth", 0.5),
                        success=body.get("success", 0),
                        duration=body.get("duration", 0),
                        error=body.get("error", ""),
                    )
                    self._send(200, {"id": row_id})
                except Exception as e:
                    self._send(400, {"error": str(e)})
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
                event_type=body.get("event_type", "internal_thought"),
                causal_parent_id=body.get("causal_parent_id", 0),
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