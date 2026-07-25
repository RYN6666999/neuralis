#!/usr/bin/env python3
"""Aris Message Relay — P0 生存層。
envelope + idempotency + 狀態機 + 收訊/推理拆分。
"""
import json, os, uuid, time, hashlib, sqlite3, threading, queue as q
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import unquote
from datetime import datetime, timezone

ARIS_API = os.environ.get("ARIS_API", "http://localhost:11546/v1/chat/completions")
PORT = int(os.environ.get("PORT", "11550"))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_FALLBACK_HTML = "<!DOCTYPE html><meta charset=utf-8><title>Aris</title><body style='font-family:sans-serif;background:#0b0b12;color:#eee;padding:2rem'>aris-chat.html 未找到。</body>"

def read_asset(name, fallback=""):
    """讀取與本檔同目錄的前端資源（HTML / manifest / sw）。每次請求讀，改前端免重啟。"""
    try:
        with open(os.path.join(SCRIPT_DIR, name), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return fallback

DB_PATH = os.environ.get(
    "ARIS_RELAY_DB",
    os.path.expanduser("~/Library/Application Support/neuralis/aris-relay.db"),
)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    source TEXT, conversation_id TEXT, user_id TEXT,
    message_id TEXT, ts REAL, type TEXT,
    payload TEXT, trace_id TEXT, schema_version TEXT,
    status TEXT DEFAULT 'received',
    receive_ts REAL, process_ts REAL, deliver_ts REAL,
    retry_count INTEGER DEFAULT 0, error TEXT,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_conv ON events(conversation_id);
"""

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn

ENVELOPE_KEYS = {"event_id","idempotency_key","source","conversation_id",
    "user_id","message_id","ts","type","payload","trace_id","schema_version"}

def make_envelope(source, conv_id, user_id, msg_type, payload, msg_id=""):
    ts = time.time()
    eid = uuid.uuid4().hex[:12]
    return {
        "event_id": eid,
        "idempotency_key": f"{source}:{msg_id or eid}",
        "source": source, "conversation_id": conv_id,
        "user_id": user_id, "message_id": msg_id or eid,
        "ts": ts, "type": msg_type,
        "payload": payload,
        "trace_id": uuid.uuid4().hex[:16],
        "schema_version": "v1"
    }

# ── 處理佇列 ──
process_queue = q.Queue()

def process_worker():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    while True:
        env = process_queue.get()
        if env is None: break
        event_id = env["event_id"]
        conn.execute("UPDATE events SET status=?, process_ts=? WHERE event_id=?",
                     ("processing", time.time(), event_id))
        conn.commit()
        try:
            messages = [{"role":"user","content": env["payload"].get("text","")}]
            body = json.dumps({"model":"laap-core","messages":messages}).encode()
            req = Request(ARIS_API, data=body, headers={"Content-Type":"application/json"})
            resp = urlopen(req, timeout=120)
            result = json.loads(resp.read())
            reply_text = (
                (result.get("choices") or [{}])[0].get("message",{}).get("content","")
                or result.get("response","")
            )
            # 回寫 reply 到 payload（順序：先改 payload，再更新 DB）
            env["payload"]["reply"] = reply_text
            # 如果回覆為空，補 fallback
            if not reply_text.strip():
                reply_text = "嗯，我在聽。你繼續說。"
                env["payload"]["reply"] = reply_text
            conn.execute("UPDATE events SET status=?, deliver_ts=?, error=?, payload=? WHERE event_id=?",
                         ("delivered", time.time(), None, json.dumps(env["payload"]), event_id))
            conn.commit()
            print(f"[relay] {event_id} → delivered ({len(reply_text)} chars)")
        except Exception as e:
            retry = env.get("_retry_count", 0)
            env["_retry_count"] = retry + 1
            if retry >= 3:
                conn.execute("UPDATE events SET status=?, error=? WHERE event_id=?",
                             ("dead_letter", str(e), event_id))
                conn.commit()
                print(f"[relay] {event_id} → DEAD LETTER: {e}")
            else:
                conn.execute("UPDATE events SET status=?, error=?, retry_count=? WHERE event_id=?",
                             ("failed", str(e), retry+1, event_id))
                conn.commit()
                time.sleep(2 ** retry)  # exponential backoff
                process_queue.put(env)

# ── 前端資源由外部檔案提供（見 read_asset）：aris-chat.html / aris-manifest.json / aris-sw.js ──

class RelayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self._ok(read_asset("aris-chat.html", _FALLBACK_HTML), 'text/html; charset=utf-8')
        elif self.path == '/manifest.json':
            self._ok(read_asset("aris-manifest.json", "{}"), 'application/manifest+json; charset=utf-8')
        elif self.path == '/sw.js':
            self._ok(read_asset("aris-sw.js", ""), 'application/javascript; charset=utf-8')
        elif self.path == '/health':
            self._ok(json.dumps({"status":"ok","port":PORT}), 'application/json')
        elif self.path == '/conversations':
            conn = db
            rows = conn.execute("""
                SELECT e.conversation_id, g.cnt, g.last_ts, e.payload
                FROM events e
                JOIN (SELECT conversation_id, COUNT(*) cnt, MAX(ts) last_ts
                      FROM events GROUP BY conversation_id) g
                  ON e.conversation_id=g.conversation_id AND e.ts=g.last_ts
                GROUP BY e.conversation_id
                ORDER BY g.last_ts DESC LIMIT 100
            """).fetchall()
            convs = []
            for r in rows:
                try: p = json.loads(r[3] or "{}")
                except Exception: p = {}
                preview = (p.get("reply") or p.get("text") or "").strip().replace("\n", " ")
                convs.append({"conversation_id": r[0], "count": r[1], "last_ts": r[2], "preview": preview[:80]})
            self._ok(json.dumps({"conversations": convs}, ensure_ascii=False), 'application/json')
        elif self.path.startswith('/events/'):
            conv = self.path.split('/events/')[-1].split('?')[0]
            conn = db
            rows = conn.execute("SELECT event_id,source,type,status,ts,error,payload FROM events WHERE conversation_id=? ORDER BY ts ASC LIMIT 100", (conv,)).fetchall()
            events = [{"event_id":r[0],"source":r[1],"type":r[2],"status":r[3],"ts":r[4],"error":r[5],"payload":json.loads(r[6] or "{}")} for r in rows]
            self._ok(json.dumps({"conversation_id":conv,"count":len(events),"events":events}, ensure_ascii=False), 'application/json')
        elif self.path == '/admin/status':
            conn = db
            total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            by_status = conn.execute("SELECT status, COUNT(*) FROM events GROUP BY status").fetchall()
            by_source = conn.execute("SELECT source, COUNT(*) FROM events GROUP BY source").fetchall()
            self._ok(json.dumps({
                "total_events": total,
                "by_status": {r[0]:r[1] for r in by_status},
                "by_source": {r[0]:r[1] for r in by_source},
                "uptime": time.time() - _START
            }, ensure_ascii=False), 'application/json')
        else:
            self._err(404, "not found")

    def do_POST(self):
        if self.path == '/c':
            try:
                length = int(self.headers.get('Content-Length', 0) or 0)
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode('utf-8', errors='replace'))
            except Exception:
                self._err_json(400, {"error": "invalid_json"})
                return
            text = body.get("text","")
            conv = body.get("conv","web")
            uid = body.get("uid","ryan")
            if not isinstance(text, str) or text.strip() == "":
                self._err_json(400, {"error": "text_required"})
                return
            env = make_envelope("web", conv, uid, "text", {"text": text},
                                msg_id=hashlib.md5(f"{conv}:{text}".encode()).hexdigest()[:12])
            conn = db
            # idempotency check
            existing = conn.execute("SELECT status FROM events WHERE idempotency_key=?",(env["idempotency_key"],)).fetchone()
            if existing:
                self._ok(json.dumps({"event_id":env["event_id"],"dedup":True,"status":existing[0]}), 'application/json')
                return
            conn.execute("""INSERT OR IGNORE INTO events
                (event_id,idempotency_key,source,conversation_id,user_id,message_id,ts,type,payload,trace_id,schema_version,status,receive_ts,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (env["event_id"],env["idempotency_key"],env["source"],env["conversation_id"],
                 env["user_id"],env["message_id"],env["ts"],env["type"],
                 json.dumps(env["payload"]),env["trace_id"],env["schema_version"],
                 "received",time.time(),time.time()))
            conn.commit()
            process_queue.put(env)
            # wait for reply (同步等待，未來換 queue)
            deadline = time.time() + 60
            replied = False
            while time.time() < deadline:
                row = conn.execute("SELECT status,payload FROM events WHERE event_id=?",(env["event_id"],)).fetchone()
                if row and row[0] in ("delivered","dead_letter"):
                    p = json.loads(row[1] or "{}")
                    reply = p.get("reply","")
                    if not reply and row[0] == "dead_letter":
                        reply = "(處理失敗)"
                    self._ok(json.dumps({"event_id":env["event_id"],"reply":reply,"status":row[0]}), 'application/json')
                    replied = True
                    break
                time.sleep(0.5)
            if not replied:
                self._ok(json.dumps({"event_id":env["event_id"],"reply":"","status":"timeout"}), 'application/json')
        else:
            self._err(404, "not found")

    def do_DELETE(self):
        if self.path.startswith('/conversations/'):
            conv = unquote(self.path.split('/conversations/', 1)[-1].split('?')[0])
            if not conv:
                self._err_json(400, {"error": "conversation_required"})
                return
            conn = db
            cur = conn.execute("DELETE FROM events WHERE conversation_id=?", (conv,))
            conn.commit()
            self._ok(json.dumps({"conversation_id": conv, "deleted": cur.rowcount}), 'application/json')
        else:
            self._err(404, "not found")

    def _ok(self, data, ctype='text/html'):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        if isinstance(data, str): data = data.encode()
        self.wfile.write(data)
    def _err(self, code, msg):
        self.send_response(code); self.end_headers(); self.wfile.write(msg.encode())
    def _err_json(self, code, payload):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    def log_message(self, *a): pass

if __name__ == '__main__':
    _START = time.time()
    db = init_db()
    t = threading.Thread(target=process_worker, daemon=True)
    t.start()
    srv = HTTPServer(("", PORT), RelayHandler)
    print(f"[relay] Aris P0 Relay → http://localhost:{PORT}")
    print(f"[relay] API → {ARIS_API}")
    srv.serve_forever()