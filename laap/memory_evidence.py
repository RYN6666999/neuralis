"""
memory_evidence — SQLite 證據儲存（取代 JSONL ledger）。

Phase 5 記憶固化循環的證據後端，追蹤 recall/promote/consolidation 事件。
OpenSpace-inspired: 每個事件有 idempotency_key，支援 resource_ref 與 session 追蹤。

用法:
    from laap.memory_evidence import record_event, get_memory_stats, get_quality_score

DB 路徑: ~/Developer/neuralis/data/memory_evidence.db（由 startup.py 掛載初始化）
"""
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("laap.memory_evidence")

# ── DB 路徑 ────────────────────────────────────────────────────
_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "memory_evidence.db"
_DB_PATH = Path(os.environ.get("NEURALIS_EVIDENCE_DB", str(_DEFAULT_DB)))
_WAL = "PRAGMA journal_mode=WAL;"
_BUSY_TIMEOUT = "PRAGMA busy_timeout=3000;"

# ── Schema ──────────────────────────────────────────────────────
_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    event_type TEXT NOT NULL,
    mem_id TEXT,
    payload TEXT DEFAULT '{}',
    idempotency_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS resource_refs (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id),
    ref_type TEXT NOT NULL,
    ref_key TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL,
    message_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_memid ON events(mem_id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_refs_event ON resource_refs(event_id);
"""

# ── Thread-local connection ─────────────────────────────────────
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.executescript(_WAL)
        conn.executescript(_BUSY_TIMEOUT)
        conn.executescript(_DDL)
        _local.conn = conn
    return _local.conn


@contextmanager
def _tx():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Public API ──────────────────────────────────────────────────


def record_event(event_type: str, mem_id: Optional[str] = None,
                 payload: Optional[dict] = None,
                 idempotency_key: Optional[str] = None) -> str:
    """記錄一個事件。idempotency_key 重複時不回寫（冪等）。

    event_type: recall / store / promote / consolidation / tool_call / user_feedback / outcome
    """
    key = idempotency_key or f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    eid = uuid.uuid4().hex[:12]
    with _tx() as conn:
        # 冪等檢查
        if key:
            existing = conn.execute(
                "SELECT id FROM events WHERE idempotency_key = ?", (key,)).fetchone()
            if existing:
                return existing[0]
        conn.execute(
            "INSERT INTO events (id, ts, event_type, mem_id, payload, idempotency_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (eid, time.time(), event_type, mem_id,
             json.dumps(payload or {}, ensure_ascii=False), key))
    return eid


def get_events(event_type: Optional[str] = None, since_ts: Optional[float] = None,
               mem_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """查詢事件列表。支援按 type / 時間 / mem_id 過濾。"""
    clauses = []
    params: List[Any] = []
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if since_ts is not None:
        clauses.append("ts >= ?")
        params.append(since_ts)
    if mem_id:
        clauses.append("mem_id = ?")
        params.append(mem_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _tx() as conn:
        rows = conn.execute(
            f"SELECT id, ts, event_type, mem_id, payload FROM events{where} "
            f"ORDER BY ts DESC LIMIT ?", params + [limit]).fetchall()
    return [
        {"id": r[0], "ts": r[1], "event_type": r[2], "mem_id": r[3],
         "payload": json.loads(r[4]) if r[4] else {}}
        for r in rows
    ]


def get_memory_stats(mem_id: str) -> Dict[str, Any]:
    """取得某記憶的統計摘要：recall 次數、最後 recall 時間、promote 次數。"""
    with _tx() as conn:
        recall_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE mem_id = ? AND event_type = 'recall'",
            (mem_id,)).fetchone()[0]
        last_recall = conn.execute(
            "SELECT MAX(ts) FROM events WHERE mem_id = ? AND event_type = 'recall'",
            (mem_id,)).fetchone()[0]
        promote_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE mem_id = ? AND event_type = 'promote'",
            (mem_id,)).fetchone()[0]
        outcome_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE mem_id = ? AND event_type = 'outcome'",
            (mem_id,)).fetchone()[0]
    return {
        "recall_count": recall_count,
        "last_recall_ts": last_recall,
        "promote_count": promote_count,
        "outcome_count": outcome_count,
    }


def record_outcome(mem_id: str, outcome: str, context: Optional[str] = None,
                   idempotency_key: Optional[str] = None) -> str:
    """記錄一個 outcome 事件（品質追蹤用）。

    outcome 權重（見 OUTCOME_WEIGHTS）：
        stored=0.0, recalled=0.1, cited_in_response=0.2,
        user_confirmed=0.5, user_corrected=-0.3,
        tool_success=0.15, tool_failure=-0.2
    """
    payload = {"outcome": outcome, "weight": OUTCOME_WEIGHTS.get(outcome, 0.0)}
    if context:
        payload["context"] = context
    return record_event("outcome", mem_id=mem_id, payload=payload,
                        idempotency_key=idempotency_key)


OUTCOME_WEIGHTS = {
    "stored": 0.0,
    "recalled": 0.1,
    "cited_in_response": 0.2,
    "user_confirmed": 0.5,
    "user_corrected": -0.3,
    "tool_success": 0.15,
    "tool_failure": -0.2,
}


def get_quality_score(mem_id: str, window_h: float = 168) -> float:
    """加權平均 outcome 品質分數。無記錄回 0.5（中立起點）。

    window_h: 時間窗口（預設 7 天 = 168h）。
    """
    since = time.time() - window_h * 3600
    with _tx() as conn:
        rows = conn.execute(
            "SELECT payload FROM events WHERE mem_id = ? AND event_type = 'outcome' AND ts >= ?",
            (mem_id, since)).fetchall()
    if not rows:
        return 0.5
    total_w = 0.0
    weighted = 0.0
    for (payload_json,) in rows:
        p = json.loads(payload_json) if isinstance(payload_json, str) else {}
        w = float(p.get("weight", 0))
        total_w += abs(w)
        weighted += w
    return 0.5 + (weighted / max(total_w, 0.001)) * 0.5 if total_w > 0 else 0.5


def record_tool_call(session_id: str, tool_name: str, status: str,
                     duration_ms: Optional[float] = None,
                     error: Optional[str] = None,
                     need: Optional[str] = None,
                     outcome_score: Optional[float] = None) -> str:
    """記錄一次工具呼叫。

    status: success / failure / timeout
    """
    payload = {
        "session_id": session_id,
        "tool_name": tool_name,
        "status": status,
        "duration_ms": duration_ms,
        "error": error,
        "need": need,
        "outcome_score": outcome_score,
    }
    return record_event("tool_call", payload=payload,
                        idempotency_key=f"tc-{int(time.time()*1000)}-{session_id}-{tool_name}")


def get_tool_stats(session_id: Optional[str] = None,
                   since_ts: Optional[float] = None) -> Dict[str, Any]:
    """工具呼叫統計。"""
    events = get_events(event_type="tool_call", since_ts=since_ts, limit=1000)
    if session_id:
        events = [e for e in events
                  if e.get("payload", {}).get("session_id") == session_id]
    total = len(events)
    if total == 0:
        return {"total": 0, "success_rate": 0.0, "avg_duration": 0.0, "by_tool": {}}
    success = sum(1 for e in events if e["payload"].get("status") == "success")
    durations = [e["payload"].get("duration_ms", 0) or 0 for e in events]
    by_tool: Dict[str, dict] = {}
    for e in events:
        tn = e["payload"].get("tool_name", "?")
        s = e["payload"].get("status") == "success"
        d = e["payload"].get("duration_ms", 0) or 0
        if tn not in by_tool:
            by_tool[tn] = {"calls": 0, "success": 0, "total_duration": 0.0}
        by_tool[tn]["calls"] += 1
        by_tool[tn]["success"] += 1 if s else 0
        by_tool[tn]["total_duration"] += d
    return {
        "total": total,
        "success_rate": round(success / total, 3),
        "avg_duration": round(sum(durations) / total, 1),
        "by_tool": by_tool,
    }


def note_session_start(session_id: Optional[str] = None) -> str:
    """記錄 session 開始。回傳 session_id。"""
    sid = session_id or f"sess-{uuid.uuid4().hex[:12]}"
    with _tx() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, started_at) VALUES (?, ?)",
            (sid, time.time()))
    return sid


def note_session_end(session_id: str, message_count: int = 0) -> None:
    """記錄 session 結束。"""
    with _tx() as conn:
        conn.execute(
            "UPDATE sessions SET ended_at = ?, message_count = ? WHERE session_id = ?",
            (time.time(), message_count, session_id))


def vacuum() -> None:
    """壓縮 DB（可定期呼叫）。"""
    with _tx() as conn:
        conn.execute("VACUUM")
    logger.info("[memory_evidence] VACUUM 完成")


def add_resource_ref(event_id: str, ref_type: str, ref_key: str) -> str:
    """為事件附加資源參照。"""
    rid = uuid.uuid4().hex[:12]
    with _tx() as conn:
        conn.execute(
            "INSERT INTO resource_refs (id, event_id, ref_type, ref_key) VALUES (?, ?, ?, ?)",
            (rid, event_id, ref_type, ref_key))
    return rid