#!/usr/bin/env python3
"""
aris_tulpa_api — 六個 tulpa 搶麥克風（競爭式認知 API）

⚠️ ⚠️ ⚠️  尚未整合到 Aris 主系統  ⚠️ ⚠️ ⚠️
隔離狀態 — 功能完整但無輸入/輸出端點：
- 不讀 :11551/wake（無記憶召回）
- 不讀 latest.json（無 PSI 情緒）
- 不寫 :11551/store（競爭結果無人消費）
- 不注入 system prompt
整合計畫：docs/18428-convergence-plan.md
⚠️ ⚠️ ⚠️

===================================================
port 18428

靈感：CTM Global Workspace（Blum & Blum）、本我-自我-超我（Freud）、
理性/感性雙軸。六個 tulpa 各自對輸入打分（urgency×importance），
最高分贏家進 context，輸家壓 gist 摘要。

v2 — 加入 persistence：tulpa 權重、物件 facet、session 遷移記錄
"""

import json, os, re, sys, time, sqlite3, threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

# 全局輪次計數器（定義在 DB 層避免 circular import）
_turn_counter: int = 0
_turn_lock = threading.Lock()

def _incr_turn() -> int:
    """線程安全 incr turn counter"""
    global _turn_counter
    with _turn_lock:
        _turn_counter += 1
        return _turn_counter

# ═══════════════════════════════════════════════════════════════
# 路徑
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "tulpa_memory.db"

_lock = threading.Lock()
_session_id: str = ""
_session_start: float = 0.0
_session_deltas: dict = {}     # tulpa_name -> delta_weight accum

# ═══════════════════════════════════════════════════════════════
# DB 初始化
# ═══════════════════════════════════════════════════════════════

def _db() -> sqlite3.Connection:
    """每次呼叫開新連線。WAL + busy_timeout 避免並發鎖定。"""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    return db

def _init_db():
    db = _db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tulpa_state (
            name          TEXT PRIMARY KEY,
            base_urgency  REAL NOT NULL DEFAULT 0.5,
            base_importance REAL NOT NULL DEFAULT 0.5,
            base_weight   REAL NOT NULL DEFAULT 1.0,
            lifetime_hits INTEGER NOT NULL DEFAULT 0,
            recent_hits   TEXT NOT NULL DEFAULT '[]',
            corrections   INTEGER NOT NULL DEFAULT 0,
            sleep_until   TEXT,              -- 休眠到期時間，NULL=醒著
            sleeping      INTEGER NOT NULL DEFAULT 0,  -- 上次休眠狀態
            winless_streak INTEGER NOT NULL DEFAULT 0, -- 上次連敗次數
            updated_at    TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS object_facets (
            object_id TEXT,
            tulpa_name TEXT,
            view      TEXT,
            count     INTEGER NOT NULL DEFAULT 1,
            last_seen TEXT NOT NULL DEFAULT '',
            last_turn INTEGER DEFAULT 0,
            PRIMARY KEY (object_id, tulpa_name)
        );
        CREATE TABLE IF NOT EXISTS ontology (
            source   TEXT,
            relation TEXT,
            target   TEXT,
            strength REAL NOT NULL DEFAULT 1.0,
            hits     INTEGER NOT NULL DEFAULT 1,
            last_seen TEXT NOT NULL DEFAULT '',
            last_turn INTEGER DEFAULT 0,
            PRIMARY KEY (source, relation, target)
        );
        CREATE TABLE IF NOT EXISTS session_delta (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            tulpa_name TEXT NOT NULL,
            turns      INTEGER NOT NULL DEFAULT 0,
            wins       INTEGER NOT NULL DEFAULT 0,
            delta_weight REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL DEFAULT ''
        );
        -- 認知遷移記錄：每輪的參數變動 vs 預設值
        CREATE TABLE IF NOT EXISTS migration_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn       INTEGER NOT NULL DEFAULT 0,
            tulpa_name TEXT NOT NULL,
            param      TEXT NOT NULL,        -- base_urgency / base_importance / base_weight
            default_val REAL NOT NULL,
            current_val REAL NOT NULL,
            delta      REAL NOT NULL,        -- current - default
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS keyword_stats (
            keyword    TEXT NOT NULL,
            tulpa_name TEXT NOT NULL,
            lifetime_misses INTEGER NOT NULL DEFAULT 0,
            last_miss  TEXT,
            active     INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (keyword, tulpa_name)
        );
        CREATE TABLE IF NOT EXISTS domain_hits (
            domain_path TEXT NOT NULL,
            hits        INTEGER NOT NULL DEFAULT 0,
            last_seen   TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (domain_path)
        );
        -- 路徑日誌：每輪領域樹匹配的路徑記錄
        CREATE TABLE IF NOT EXISTS path_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            turn       INTEGER NOT NULL,
            path       TEXT NOT NULL,        -- "L1/L2/L3"
            depth      INTEGER NOT NULL,
            tulpa_name TEXT DEFAULT '',       -- 若走 tulpa fallback 則記錄贏家
            created_at TEXT NOT NULL DEFAULT ''
        );
        -- 結構同構：兩條路徑的結構相似度
                CREATE TABLE IF NOT EXISTS structure_isomorphism (
                    path_a     TEXT NOT NULL,
                    path_b     TEXT NOT NULL,
                    similarity REAL NOT NULL DEFAULT 0.0,
                    hits       INTEGER NOT NULL DEFAULT 0,
                    merged     INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (path_a, path_b)
                );
                -- 第三位置觀察記錄
                CREATE TABLE IF NOT EXISTS observer_insights (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn       INTEGER NOT NULL,
                    insight_type TEXT NOT NULL,    -- conflict / error / contradiction / opportunity
                    description TEXT NOT NULL,
                    evidence   TEXT NOT NULL DEFAULT '',   -- JSON 證據
                    confidence REAL NOT NULL DEFAULT 0.0,
                    addressed  INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT ''
                );
                -- 時間軸競爭記錄
                CREATE TABLE IF NOT EXISTS time_axis_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn       INTEGER NOT NULL,
                    winner     TEXT NOT NULL,      -- past / present / future
                    score      REAL NOT NULL,
                    past_score REAL NOT NULL,
                    present_score REAL NOT NULL,
                    future_score REAL NOT NULL,
                    predicted_path TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT ''
                );
                -- 預測事件：逐輪記錄未來 tulpa 的預測與結算結果
                CREATE TABLE IF NOT EXISTS prediction_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    pred_turn  INTEGER NOT NULL,
                    predicted  TEXT NOT NULL DEFAULT '',
                    actual_turn INTEGER,
                    actual     TEXT,
                    correct    INTEGER,
                    state      TEXT DEFAULT 'pending',
                    created_at TEXT
                );
                -- 待審建議：由 observer 高信心 insight 升等，供人決策（非自動執行）
                CREATE TABLE IF NOT EXISTS pending_suggestions (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    source_insight_id INTEGER,
                    insight_type TEXT NOT NULL,
                    suggested_action TEXT DEFAULT '',   -- merge / split / cross_domain / flag
                    description TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    evidence TEXT,                        -- JSON
                    status     TEXT DEFAULT 'pending',    -- pending / approved / rejected / executed
                    created_at TEXT
                );
                -- 建議決策回饋：人審議每個 suggestion 的 approve/reject → observer 學習訊號
                CREATE TABLE IF NOT EXISTS suggestion_feedback (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    suggestion_id INTEGER NOT NULL,
                    insight_type  TEXT NOT NULL,
                    decision      TEXT NOT NULL,   -- approve / reject
                    confidence    REAL DEFAULT 0.0,
                    decided_at    TEXT
                );
                -- 領域樹候選詞：未被收錄但常在特定領域路徑出現的詞彙（觀察期）
                CREATE TABLE IF NOT EXISTS domain_keyword_candidates (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate  TEXT NOT NULL,       -- 候選詞
                    domain_path TEXT NOT NULL,      -- 唯一指向同一路徑（跨樹 cross-branch 基準）
                    count      INTEGER NOT NULL DEFAULT 0,
                    first_seen TEXT,
                    last_seen  TEXT,
                    last_proposed INTEGER NOT NULL DEFAULT 0,
                    state      TEXT DEFAULT 'observing',  -- observing / proposed / approved / rejected
                    UNIQUE(candidate, domain_path)
                );
                -- 已核准的領域關鍵字：核准後真正加進該節點 keywords（持久化 overlay）
                CREATE TABLE IF NOT EXISTS domain_keyword_additions (
                    candidate    TEXT NOT NULL,
                    domain_path  TEXT NOT NULL,
                    added_at     TEXT,
                    UNIQUE(candidate, domain_path)
                );
                -- 已核准的 tulpa 關鍵字：核准後加進該 tulpa.keywords（持久化 overlay）
                CREATE TABLE IF NOT EXISTS tulpa_keyword_addition (
                    candidate    TEXT NOT NULL,
                    tulpa_name   TEXT NOT NULL,
                    added_at     TEXT,
                    UNIQUE(candidate, tulpa_name)
                );
                -- 領域優化：每個節點的命中、校正、溫度
                CREATE TABLE IF NOT EXISTS domain_optimization (
                    path         TEXT PRIMARY KEY,
                    total_hits   INTEGER NOT NULL DEFAULT 0,
                    last_turn    INTEGER NOT NULL DEFAULT 0,
                    corrections  INTEGER NOT NULL DEFAULT 0,
                    effective_hits INTEGER NOT NULL DEFAULT 0,
                    avg_correction_trend REAL NOT NULL DEFAULT 0.0,  -- 0~1, 越高越壞
                    deprecated   INTEGER NOT NULL DEFAULT 0
                );
                -- 關鍵字成效 per domain node
                CREATE TABLE IF NOT EXISTS domain_keyword_perf (
                    path         TEXT NOT NULL,
                    keyword      TEXT NOT NULL,
                    good_hits    INTEGER NOT NULL DEFAULT 0,
                    false_pos    INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (path, keyword)
                );
                -- 領域樹學習定向：從校正歷史中自動調整 orientation
                CREATE TABLE IF NOT EXISTS domain_learned_orientation (
                    path         TEXT NOT NULL,
                    tulpa_name   TEXT NOT NULL,
                    score        REAL NOT NULL DEFAULT 0.5,
                    wins         INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (path, tulpa_name)
                );
                -- 對賭驗證日誌：記錄我宣稱「完成」後被驗證打臉/通過的歷史
                CREATE TABLE IF NOT EXISTS verification_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim      TEXT NOT NULL,               -- 我宣稱什麼完成了
                    round      INTEGER NOT NULL DEFAULT 0,   -- 第幾輪驗證
                    found      INTEGER NOT NULL DEFAULT 0,   -- 這輪又找到幾個問題
                    method     TEXT NOT NULL DEFAULT '',      -- 用什麼方法找到的
                    verdict    TEXT NOT NULL DEFAULT 'pending', -- pending / busted / confirmed
                    created_at TEXT NOT NULL DEFAULT ''
                );
                -- PSI 行為觸發日誌：記錄 PSI 觸發的行動及有效性
                CREATE TABLE IF NOT EXISTS psi_action_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger_type TEXT NOT NULL,           -- certainty_low / competence_low
                    psi_before REAL NOT NULL,              -- 觸發前的值
                    action     TEXT NOT NULL,              -- ask_clear / verify_first / self_audit
                    action_taken INTEGER NOT NULL DEFAULT 0, -- 0=未執行, 1=有執行
                    outcome    INTEGER NOT NULL DEFAULT 0,  -- 0=未改善, 1=有效
                    psi_after  REAL DEFAULT NULL,           -- 改善後的值
                    turn       INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT ''
                );
                -- 元認知錯誤目錄：記錄 LLM 犯過的錯誤模式，供未來注入提醒
                CREATE TABLE IF NOT EXISTS mistake_catalog (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    input_pattern TEXT NOT NULL,           -- 觸發錯誤的輸入模式（模糊匹配用）
                    error_type    TEXT NOT NULL,           -- wrong_domain / memory_confab / logic_jump / tulpa_win_wrong
                    domain_path   TEXT DEFAULT '',         -- 當時走的領域路徑
                    tulpa_name    TEXT DEFAULT '',         -- 當時贏家 tulpa
                    lesson        TEXT NOT NULL,           -- 這次學到的教訓（一句話）
                    triggered_count INTEGER NOT NULL DEFAULT 1,
                    last_triggered TEXT DEFAULT '',
                    created_at    TEXT NOT NULL DEFAULT ''
                );
    """)
    # T3 (2026-09-06) LUCID 去膨脹：mistake_outcome 加 label 來源欄位。
    # 只有真人/外部（source='human'）的 label 才進權重；AI 自標（source='self'）不進，
    # 讓 reward 誤差與 AI 盲點「去相關」——防 Echo Gap（AI 自標的錯會被自己背熟放大）。
    db.execute("""
        CREATE TABLE IF NOT EXISTS mistake_outcome (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mistake_id  INTEGER NOT NULL REFERENCES mistake_catalog(id),
            outcome     TEXT NOT NULL,            -- avoided / recurred / unverifiable
            evidence    TEXT DEFAULT '',
            source      TEXT NOT NULL DEFAULT 'human',  -- T3: label 來源（human-真人/外部, self-AI自標, tool-工具）
            created_at  TEXT NOT NULL DEFAULT ''
        );
    """)
    # 既有表若缺 source 欄位則補上（idempotent）
    out_cols = {r[1] for r in db.execute("PRAGMA table_info(mistake_outcome)").fetchall()}
    if "source" not in out_cols:
        db.execute("ALTER TABLE mistake_outcome ADD COLUMN source TEXT NOT NULL DEFAULT 'human'")
    # 幂等計入旗標：label 被 apply_gene_adjustments 計入一次後設 1，避免跨 call 複利
    if "consumed" not in out_cols:
        db.execute("ALTER TABLE mistake_outcome ADD COLUMN consumed INTEGER NOT NULL DEFAULT 0")
    db.commit()
    db.close()

# ═══════════════════════════════════════════════════════════════
# 載入/儲存 tulpa 狀態
# ═══════════════════════════════════════════════════════════════

def load_tulpa_state() -> dict:
    """從 DB 載入所有 tulpa 的持久化權重，回傳 {name: {field: value}}"""
    db = _db()
    rows = db.execute("SELECT * FROM tulpa_state").fetchall()
    db.close()
    out = {}
    for r in rows:
        out[r["name"]] = {
            "base_urgency": r["base_urgency"],
            "base_importance": r["base_importance"],
            "base_weight": r["base_weight"],
            "lifetime_hits": r["lifetime_hits"],
            "recent_hits": json.loads(r["recent_hits"] or "[]"),
            "corrections": r["corrections"],
            "sleeping": bool(r["sleeping"]),
            "winless_streak": r["winless_streak"],
        }
    return out

def save_tulpa_state(tulpas: list):
    """將所有 tulpa 當前狀態寫回 DB。"""
    now = datetime.utcnow().isoformat()
    db = _db()
    for t in tulpas:
        db.execute("""
            INSERT INTO tulpa_state (name, base_urgency, base_importance, base_weight,
                                     lifetime_hits, recent_hits, corrections,
                                     sleeping, winless_streak, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                base_urgency=excluded.base_urgency,
                base_importance=excluded.base_importance,
                base_weight=excluded.base_weight,
                lifetime_hits=excluded.lifetime_hits,
                recent_hits=excluded.recent_hits,
                corrections=excluded.corrections,
                sleeping=excluded.sleeping,
                winless_streak=excluded.winless_streak,
                updated_at=excluded.updated_at
        """, (
            t.name, t.base_urgency, t.base_importance, t.base_weight,
            t.lifetime_hits, json.dumps(t.recent_hits),
            getattr(t, 'corrections', 0),
            int(t._sleeping), t._winless_streak, now,
        ))
    db.commit()
    db.close()

def save_session_delta():
    """session 結束時寫入 aggregate delta。"""
    global _session_id
    if not _session_id or not _session_deltas:
        return
    now = datetime.utcnow().isoformat()
    db = _db()
    for name, (turns, wins, delta) in _session_deltas.items():
        db.execute("""
            INSERT INTO session_delta (session_id, tulpa_name, turns, wins, delta_weight, created_at)
            VALUES (?,?,?,?,?,?)
        """, (_session_id, name, turns, wins, round(delta, 4), now))
    db.commit()
    db.close()

    # ── 消費者：把本 session 的權重演化摘要寫進 claim_chain（審計鏈，append-only）──
    # 這是 session_delta 的讀取端（原本 0 消費者）：讓「本 session 哪個 tulpa
    # 因權重變化而長大/衰退」成為可復盤、可外部驗證的紀錄。接了才知道有沒有用。
    try:
        import subprocess
        db2 = _db()
        rows = db2.execute(
            "SELECT tulpa_name, turns, wins, delta_weight FROM session_delta "
            "WHERE session_id=? ORDER BY delta_weight DESC", (_session_id,)
        ).fetchall()
        db2.close()
        if rows:
            top_gain = rows[0]           # delta_weight 最大 = 成長最多
            top_shrink = rows[-1] if len(rows) > 1 else None
            parts = []
            for r in rows[:3]:
                parts.append(f"{r['tulpa_name']}(Δ{r['delta_weight']:+})")
            evidence = f"session={_session_id} deltas={','.join(parts)} count={len(rows)}"
            subprocess.run(
                ["python3", str(Path.home() / "Developer/neuralis/scripts/claim-chain.py"),
                 "append", "--kind", "session_delta",
                 "--payload", f"session 權重演化: 成長最多={top_gain['tulpa_name']}(Δ{top_gain['delta_weight']:+})",
                 "--evidence", evidence],
                capture_output=True, timeout=15)
    except Exception:
        pass


def load_object_facets(object_id: str) -> list:
    """載入一個物件的所有 facet。"""
    db = _db()
    rows = db.execute(
        "SELECT tulpa_name, view, count, last_seen FROM object_facets WHERE object_id=? ORDER BY count DESC",
        (object_id,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

def save_object_facet(object_id: str, tulpa_name: str, view: str):
    """更新物件 facet + 記錄輪次。"""
    now = datetime.utcnow().isoformat()
    db = _db()
    db.execute("""
        INSERT INTO object_facets (object_id, tulpa_name, view, count, last_seen, last_turn)
        VALUES (?,?,?,1,?,?)
        ON CONFLICT(object_id, tulpa_name) DO UPDATE SET
            count=count+1, view=excluded.view,
            last_seen=excluded.last_seen, last_turn=excluded.last_turn
    """, (object_id, tulpa_name, view, now, _turn_counter))
    db.commit()
    db.close()

# _turn_counter is defined in tulpa_engine.py
