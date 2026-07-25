#!/usr/bin/env python3
"""aris-memory — 統一記憶層。SQLite 可靠基底 + gbrain 非同步同步。
寫入即查得到，不靠搜尋引擎猜你在找什麼。"""
import sqlite3, json, time, os, threading
from pathlib import Path

DB = os.environ.get("ARIS_MEMORY_DB", str(Path.home() / ".aris-memory.db"))

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
    provenance TEXT DEFAULT ''              -- 指回哪些原始事件/頁；指不回 → 應為 red
);
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_source_id ON memories(source, source_id);
"""

# ── Confidence 閘（見 2-記憶系統/canary翻轉-簽名前檢查與confidence閘.md B 部）──
# 硬閘：🟢 只能來自 human / recalled_verified；auto_generated / external 封頂 🟡。
# auto 產物永遠是「推測」，不能自動變事實 → 擋血訓那個坑（gbrain 給自己幻覺打高分）。
_VALID_ORIGIN = {"human", "recalled_verified", "auto_generated", "external"}
_VALID_CONF = {"red", "yellow", "green"}
_GREEN_ALLOWED_ORIGIN = {"human", "recalled_verified"}


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
    for sql in adds:
        conn.execute(sql)
    # confidence 索引在補欄後才建（既有表補欄前該欄不存在）
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence)")
    conn.commit()

class ArisMemory:
    def __init__(self, db_path=DB):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        _ensure_columns(self.conn)
        self.conn.commit()
        self._lock = threading.Lock()

    def store(self, source, content, tags=None, emotion_tag="", source_id="",
              origin="auto_generated", confidence="yellow", provenance=""):
        """寫入記憶，立即查得到。origin/confidence 過硬閘（auto 產物封頂 🟡）。"""
        origin, confidence = _normalize_gate(origin, confidence)
        with self._lock:
            now = time.time()
            sid = source_id or f"{source}-{int(now*1000)}"
            self.conn.execute(
                "INSERT INTO memories (source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (source, sid, content, json.dumps(tags or [], ensure_ascii=False), emotion_tag, now,
                 origin, confidence, provenance or "")
            )
            self.conn.commit()
            row_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return {"id": row_id, "source": source, "source_id": sid, "created_at": now,
                    "origin": origin, "confidence": confidence}

    def query(self, q="", source="", limit=20, after_id=0):
        """查詢記憶。支援全文檢索 + 來源過濾 + 分頁。"""
        with self._lock:
            clauses = ["id > ?"]
            params = [after_id]
            if source:
                clauses.append("source = ?")
                params.append(source)
            if q:
                clauses.append("content LIKE ?")
                params.append(f"%{q}%")
            sql = f"SELECT id, source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance FROM memories WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()
            return [{"id": r[0], "source": r[1], "source_id": r[2], "content": r[3],
                     "tags": json.loads(r[4] or "[]"), "emotion_tag": r[5], "created_at": r[6],
                     "origin": r[7], "confidence": r[8], "provenance": r[9]} for r in rows]

    def recent(self, limit=10):
        """最近 N 條記憶，無論來源。"""
        return self.query("", "", limit)

    def by_source(self, source, limit=50):
        """依來源查詢。"""
        return self.query("", source, limit)

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
                self._send(200, {"results": mem.query(first("q"), first("source"), limit)})
            elif u.path == "/memories/recent":
                try:
                    limit = int(first("limit", "10") or 10)
                except ValueError:
                    limit = 10
                self._send(200, {"results": mem.recent(limit)})
            else:
                self._send(404, {"error": "not_found"})

        def do_POST(self):
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