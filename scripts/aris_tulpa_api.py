#!/usr/bin/env python3
"""
aris_tulpa_api — 六個 tulpa 搶麥克風（競爭式認知 API）
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

from aiohttp import web


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
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
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
            updated_at    TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS object_facets (
            object_id TEXT,
            tulpa_name TEXT,
            view      TEXT,
            count     INTEGER NOT NULL DEFAULT 1,
            last_seen TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (object_id, tulpa_name)
        );
        CREATE TABLE IF NOT EXISTS ontology (
            source   TEXT,
            relation TEXT,
            target   TEXT,
            strength REAL NOT NULL DEFAULT 1.0,
            hits     INTEGER NOT NULL DEFAULT 1,
            last_seen TEXT NOT NULL DEFAULT '',
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
    """)
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
        }
    return out

def save_tulpa_state(tulpas: list):
    """將所有 tulpa 當前狀態寫回 DB。"""
    now = datetime.utcnow().isoformat()
    db = _db()
    for t in tulpas:
        db.execute("""
            INSERT INTO tulpa_state (name, base_urgency, base_importance, base_weight,
                                     lifetime_hits, recent_hits, corrections, updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                base_urgency=excluded.base_urgency,
                base_importance=excluded.base_importance,
                base_weight=excluded.base_weight,
                lifetime_hits=excluded.lifetime_hits,
                recent_hits=excluded.recent_hits,
                corrections=excluded.corrections,
                updated_at=excluded.updated_at
        """, (
            t.name, t.base_urgency, t.base_importance, t.base_weight,
            t.lifetime_hits, json.dumps(t.recent_hits),
            getattr(t, 'corrections', 0), now,
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


# ═══════════════════════════════════════════════════════════════
# Tulpa 定義
# ═══════════════════════════════════════════════════════════════

@dataclass
class Tulpa:
    """一個 tulpa：被創造出來的思想形體，有名字、關鍵字、基線分數、加權調整、輸贏台詞。"""
    name: str
    keywords: List[str]
    base_urgency: float
    base_importance: float
    base_weight: float = 1.0
    lifetime_hits: int = 0
    recent_hits: list = field(default_factory=list)
    corrections: int = 0
    modifiers: List[Tuple[str, float, float]] = field(default_factory=list)
    context_text: str = ""
    gist_text: str = ""
    # runtime 狀態（不持久化到 DB，只在記憶體存活）
    _sleeping: bool = False
    _winless_streak: int = 0           # 連續命中但沒贏的輪數


def _apply_persisted(t: Tulpa, state: dict):
    """用 persistence 載入的值覆蓋 tulpa 的預設值。"""
    s = state.get(t.name)
    if s:
        t.base_weight = s.get("base_weight", 1.0)
        t.lifetime_hits = s.get("lifetime_hits", 0)
        t.recent_hits = s.get("recent_hits", [])
        t.corrections = s.get("corrections", 0)

TULPAS = [
    Tulpa(name="本我理性",
          keywords=["做", "寫", "改", "修", "fix", "implement", "幫我", "完成",
                    "執行", "跑", "create", "build", "deploy", "弄"],
          base_urgency=0.7, base_importance=0.6,
          modifiers=[(r'.{100,}', 0, 0.2), (r'急|快|趕|urgent|asap', 0.2, 0)],
          context_text="有任務需要完成，優先處理效率與執行。",
          gist_text="有任務待處理"),
    Tulpa(name="本我感性",
          keywords=["靠", "氣", "爽", "開心", "煩", "愛", "恨", "喜歡", "討厭",
                    "難過", "高興", "生氣", "😡", "❤️", "😂", "幹", "哭"],
          base_urgency=0.5, base_importance=0.5,
          modifiers=[(r'超[他媽]?|有夠|非常|好|太', 0.3, 0)],
          context_text="現在有情緒，先感受再說。",
          gist_text="情緒有些波動"),
    Tulpa(name="自我理性",
          keywords=["為什麼", "怎麼", "分析", "比較", "因果", "解釋", "原理",
                    "思考", "想", "邏輯", "推理", "差異", "關係", "結構"],
          base_urgency=0.3, base_importance=0.8,
          modifiers=[(r'.{150,}', 0, 0.15), (r'\?{2,}|？{2,}', 0.1, 0.1)],
          context_text="需要分析，先搞清楚因果與結構。",
          gist_text="有問題需要分析"),
    Tulpa(name="自我感性",
          keywords=["你覺得", "你認為", "如果", "萬一", "擔心", "不安",
                    "害怕", "猶豫", "不確定", "困擾", "說不準"],
          base_urgency=0.3, base_importance=0.6,
          modifiers=[(r'\?|？', 0.1, 0), (r'不確定|說不準', 0, 0.2)],
          context_text="有點不確定，先確認安全再前進。",
          gist_text="有些不安或猶豫"),
    Tulpa(name="超我理性",
          keywords=["應該", "必須", "正確", "錯", "道德", "原則", "規則",
                    "規範", "標準", "對不對", "合理", "正當"],
          base_urgency=0.3, base_importance=0.7,
          modifiers=[(r'對不對|合理嗎|正當', 0.2, 0.1)],
          context_text="有原則需要堅守，對錯很重要。",
          gist_text="有原則或規範需要考量"),
    Tulpa(name="超我感性",
          keywords=["你", "我們", "關係", "在乎", "重要", "陪伴", "孤單",
                    "感謝", "謝謝", "辛苦了", "珍惜", "信任"],
          base_urgency=0.4, base_importance=0.7,
          modifiers=[(r'感謝|謝謝|辛苦了', 0.2, 0.2)],
          context_text="你在這裡，連結與信任很重要。",
          gist_text="關係與連結有訊號"),
]


# ═══════════════════════════════════════════════════════════════
# 核心競爭邏輯
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# Ontology 分類器
# ═══════════════════════════════════════════════════════════════

def _make_signature(text: str) -> str:
    """從輸入中提取 keyword 簽名，用來查 ontology 表比對結構。

    簽名 = 哪幾個 tulpa 的 keyword 命中，依序排列。
    例如「幫我約客戶」→ "本我理性/超我感性"
    """
    hits = []
    for t in TULPAS:
        if any(kw in text for kw in t.keywords):
            hits.append(t.name)
    return "/".join(sorted(hits)) if hits else "none"


def classify(text: str) -> dict:
    """Ontology 分類器：輸入 → 簽名 → 查表 → 建議喚醒哪些 tulpa。

    回傳：
        domain: ontology 中匹配最強的 target 或 "general"
        activate: 建議喚醒的 tulpa 名稱列表 (None = 全喚醒)
        facets: 相關物件的 facet 歷史
        match_strength: 匹配強度 (0~1)
    """
    sig = _make_signature(text)
    db = _db()

    # 1. 查 ontology：這個簽名以前對應過什麼結果？
    rows = db.execute("""
        SELECT target, strength, hits FROM ontology
        WHERE source=? AND relation='pattern→tulpa'
        ORDER BY strength DESC LIMIT 3
    """, (sig,)).fetchall()

    # 2. 查物件 facet：text 中含有的已知物件
    oid = None
    for kw in ["客戶", "朋友", "廠商", "同事", "老闆", "專案", "bug", "功能",
               "這個", "那個"]:
        if kw in text:
            oid = kw
            break
    facets = []
    if oid:
        facet_rows = db.execute(
            "SELECT tulpa_name, view, count FROM object_facets WHERE object_id=? ORDER BY count DESC",
            (oid,)
        ).fetchall()
        facets = [dict(r) for r in facet_rows]

    db.close()

    # 3. 決定喚醒策略
    if rows and rows[0]["strength"] > 0.6:
        # 強匹配 → 只喚醒 ontology 建議的 tulpa
        suggested = rows[0]["target"].split("/")
        valid = {t.name for t in TULPAS}
        activate = [n for n in suggested if n in valid]
        strength = rows[0]["strength"]
    elif rows and rows[0]["strength"] <= 0.0 and rows[0]["hits"] > 0:
        # ontology 重啟：舊 pattern 在衰退後再次命中 → 恢復 0.3
        db = _db()
        db.execute("UPDATE ontology SET strength=0.3, last_turn=? WHERE source=? AND relation='pattern→tulpa' AND target=?",
                   (_turn_counter, sig, rows[0]["target"]))
        db.commit()
        db.close()
        activate = None
        strength = 0.3
    else:
        activate = None  # 全喚醒
        strength = 0.0

    return {
        "domain": rows[0]["target"] if rows else "general",
        "activate": activate,
        "facets": facets,
        "object_id": oid,
        "match_strength": strength,
        "signature": sig,
    }


def learn_ontology(text: str, winner_name: str):
    """競爭結束後自動學習：更新 ontology 表。

    輸入的簽名 + 贏家 → 強化/建立 pattern→tulpa 關係。
    """
    sig = _make_signature(text)
    target = winner_name
    db = _db()
    db.execute("""
        INSERT INTO ontology (source, relation, target, strength, hits, last_seen, last_turn)
        VALUES (?, 'pattern→tulpa', ?, 0.5, 1, '', ?)
        ON CONFLICT(source, relation, target) DO UPDATE SET
            strength=MIN(1.0, strength+0.05),
            hits=hits+1
    """, (sig, target, _turn_counter))
    db.commit()
    db.close()


# ═══════════════════════════════════════════════════════════════
# 領域樹（窄而深）
# ═══════════════════════════════════════════════════════════════

@dataclass
class DomainNode:
    """領域樹節點：L1 分類 → L2 細分 → L3 策略/記憶。"""
    name: str
    keywords: List[str]                     # 觸發此節點的關鍵字
    context_text: str = ""                  # 此節點的 context
    children: List['DomainNode'] = field(default_factory=list)
    # L3 策略可從 ontology 查詢物件 facet 動態生成
    memory_key: Optional[str] = None        # 對應 ontology 物件 ID


# ── 領域樹定義（手動註冊） ──

CLIENT_TREE = DomainNode(
    name="客戶經營",
    keywords=["客戶", "房仲", "房東", "帶看", "物件", "買方", "賣方"],
    children=[
        DomainNode(
            name="約客戶",
            keywords=["約", "拜訪", "見面", "約時間", "安排"],
            context_text="約客戶要根據關係階段選擇策略。新客戶先建立信任，老客戶直接約。",
            children=[
                DomainNode(
                    name="新客戶陌生拜訪",
                    keywords=["新客戶", "陌生", "開發", "第一次"],
                    context_text="新客戶第一次接觸，先建立信任而非直接推銷。了解他的需求再給方案。",
                ),
                DomainNode(
                    name="既有客戶跟催",
                    keywords=["跟催", "追", "後續", "上次", "那個", "再約"],
                    context_text="既有客戶跟進。先確認對方意向，不要急著丟時間選項。",
                    memory_key="客戶",
                ),
                DomainNode(
                    name="簽約/成交",
                    keywords=["簽約", "成交", "下斡", "出價", "談"],
                    context_text="接近成交階段，態度要穩。不要表現太急，讓對方感受到你的專業與信心。",
                ),
            ],
        ),
        DomainNode(
            name="追款",
            keywords=["追款", "收錢", "款項", "費用", "佣", "欠"],
            context_text="追款是敏感話題。態度要堅定但不要傷關係，先聽對方怎麼說再決定策略。",
            children=[
                DomainNode(
                    name="禮貌提醒",
                    keywords=["提醒", "催", "還沒"],
                    context_text="以關心代替催討。先確認對方是否有困難，再談時間。",
                ),
                DomainNode(
                    name="正式追討",
                    keywords=["再不", "最後", "期限", "合約"],
                    context_text="金額明確、時限清楚。保留法律途徑但不要威脅語氣。",
                ),
            ],
        ),
        DomainNode(
            name="帶看",
            keywords=["帶看", "看房子", "看屋", "參觀"],
            context_text="帶看是成交的關鍵時刻。先確認客戶需求再介紹，不要急著推銷。",
            children=[
                DomainNode(
                    name="行前準備",
                    keywords=["準備", "資料", "文件", "鑰匙"],
                    context_text="帶看前確認：物件資料齊全、鑰匙在手、路線規劃好。",
                ),
                DomainNode(
                    name="帶看中",
                    keywords=["現場", "介紹", "展示", "這裡"],
                    context_text="帶看時觀察客戶反應，不要一直講。他注意哪裡就是他的痛點。",
                ),
            ],
        ),
        DomainNode(
            name="售後",
            keywords=["售後", "交屋", "過戶", "後續", "服務"],
            context_text="交屋後才是服務的開始。主動關心入住狀況，建立長期關係。",
        ),
    ],
)

ALL_DOMAINS = [CLIENT_TREE]


def _match_tree(node: DomainNode, text: str) -> dict:
    """遞迴匹配領域樹。回傳最深匹配節點的 context + path。"""
    # 先檢查這個 node 本身的 keyword
    if not any(kw in text for kw in node.keywords):
        return {"matched": False, "depth": 0, "path": []}

    path = [node.name]
    best = node  # 至少這個 node 匹配
    best_depth = 1

    # 檢查 children
    for child in node.children:
        result = _match_tree(child, text)
        if result["matched"] and result["depth"] + 1 > best_depth:
            best = result["leaf"]
            best_depth = result["depth"] + 1
            path = [node.name] + result["path"]

    # 組裝 context：最佳節點的文字 + 路徑
    ctx = best.context_text
    if best.memory_key:
        # 查物件 facet 歷史
        facets = load_object_facets(best.memory_key)
        if facets:
            past = " | ".join(f"[{f['tulpa_name']}] {f['view']} (×{f['count']})"
                              for f in facets[:3])
            ctx = f"{ctx}\n過去記錄: {past}"

    return {
        "matched": True,
        "depth": best_depth,
        "path": path,
        "context": ctx,
        "leaf": best,
        "leaf_name": best.name,
    }


def route_domain(text: str) -> dict:
    """全域 route：輸入先走所有已註冊領域樹，最深匹配優先。

    回傳：
        routed: True/False
        context: 領域樹產出的 context（如果 routed=True）
        domain_path: 匹配路徑
    """
    best = {"matched": False, "depth": 0, "context": "", "path": []}

    for domain in ALL_DOMAINS:
        result = _match_tree(domain, text)
        if result["matched"] and result["depth"] > best["depth"]:
            best = result

    if best["matched"]:
        return {
            "routed": True,
            "context": best["context"],
            "domain_path": best["path"],
        }
    return {"routed": False, "context": "", "domain_path": []}


# ═══════════════════════════════════════════════════════════════
# 被動知識搜尋（按需加載）
# ═══════════════════════════════════════════════════════════════

KNOWLEDGE_ROOTS = [
    os.path.expanduser("~/Desktop/房多多"),
    os.path.expanduser("~/Downloads"),
]

def _search_files(keyword: str) -> list:
    """在 KNOWLEDGE_ROOTS 下找檔名包含 keyword 的檔案，回傳絕對路徑清單。"""
    found = []
    for root in KNOWLEDGE_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if keyword.lower() in f.lower() and f.endswith((".json", ".md", ".csv", ".txt")):
                    found.append(os.path.join(dirpath, f))
    return found[:5]  # 最多 5 個


def _read_head(path: str, max_chars: int = 2000) -> str:
    """讀檔案前 max_chars 字元（摘要用）。失敗時記錄錯誤。"""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        return content[:max_chars]
    except Exception as e:
        print(f"[tulpa] ⚠️ _read_head 失敗: {path} — {e}", file=sys.stderr)
        return ""


def passive_search(text: str) -> dict:
    """根據輸入文字搜尋相關知識檔案。

    先查 ontology 有沒有 cache（keyword→file 關係），
    沒有 cache 就從檔案系統搜尋，找到後建立 ontology 記錄。

    回傳：
        found: bool
        content: 檔案摘要文字
        paths: 檔案路徑清單
    """
    # 從 text 中提取可能的中文關鍵詞（2-4 字詞）
    # 簡單作法：用已知 topic 關鍵字匹配
    triggers = ["C單", "c單", "房多多", "產品", "學費", "提貨", "報名",
                "謄本", "聯徵", "客戶", "定價", "名單", "CRM"]
    matched_kw = None
    for kw in triggers:
        if kw in text:
            matched_kw = kw
            break
    if not matched_kw:
        return {"found": False, "content": "", "paths": []}

    # 查 ontology cache：這個關鍵字以前搜到過什麼檔案
    db = _db()
    rows = db.execute(
        "SELECT target, strength, hits FROM ontology "
        "WHERE source=? AND relation='keyword→file' ORDER BY strength DESC LIMIT 3",
        (matched_kw,)
    ).fetchall()

    if rows and rows[0]["strength"] > 0.5:
        # cache 命中，直接讀
        path = rows[0]["target"]
        content = _read_head(path)
        db.close()
        if content:
            return {"found": True, "content": content, "paths": [path]}
        # 檔案可能已刪除，繼續往下搜

    # 沒有 cache 或 cache 失效 → 從檔案系統搜
    paths = _search_files(matched_kw)
    if not paths:
        db.close()
        return {"found": False, "content": "", "paths": []}

    # 讀內容摘要
    content_parts = []
    for p in paths:
        head = _read_head(p)
        if head:
            content_parts.append(f"--- {p} ---\n{head}")
    content = "\n\n".join(content_parts[:2])  # 最多 2 個檔案

    # 建立 ontology cache
    now = datetime.utcnow().isoformat()
    for p in paths[:1]:  # 只 cache 第一個
        db.execute("""
            INSERT INTO ontology (source, relation, target, strength, hits, last_seen, last_turn)
            VALUES (?, 'keyword→file', ?, 0.5, 1, '', ?)
            ON CONFLICT(source, relation, target) DO UPDATE SET
                strength=MIN(1.0, strength+0.05), hits=hits+1, last_turn=excluded.last_turn
        """, (matched_kw, p, _turn_counter))
    db.commit()
    db.close()

    return {"found": True, "content": content, "paths": paths}


def score_tulpa(tulpa: Tulpa, text: str) -> float:
    """urgency × importance × base_weight。沒命中 keyword → 0。

    支援 keyword 喚醒：若 tulpa 有被移除的 keyword 且出現在輸入中，
    自動加回 keywords list。
    """
    # 檢查喚醒：休眠中被移除的 keyword 突然出現
    removed = getattr(tulpa, '_removed_keywords', [])
    for rk in list(removed):
        if rk in text:
            tulpa.keywords.append(rk)
            tulpa._removed_keywords.remove(rk)
            # 更新 DB 標記為 active
            db = _db()
            db.execute("UPDATE keyword_stats SET active=1 WHERE keyword=? AND tulpa_name=?",
                       (rk, tulpa.name))
            db.commit()
            db.close()

    if not any(kw in text for kw in tulpa.keywords):
        return 0.0
    u, i = tulpa.base_urgency, tulpa.base_importance
    for pattern, du, di in tulpa.modifiers:
        if re.search(pattern, text):
            u += du
            i += di
    u = min(1.0, u)
    i = min(1.0, i)
    return round(u, 3) * round(i, 3) * tulpa.base_weight


def compete(text: str) -> dict:
    """六個 tulpa 競爭，回傳結果 + 更新持久化狀態。

    先跑 ontology 分類器 → 決定是否限制喚醒 tulpa 數量 → 競爭。
    """
    global _session_deltas

    # ── Step 0: Ontology 分類 ──
    cl = classify(text)

    # ── Step 0.5: 領域樹 route（窄而深優先）──
    domain = route_domain(text)
    if domain["routed"]:
        # bypass 六個扁平 tulpa，直接回傳領域 context
        for t in TULPAS:
            t.recent_hits.append(0)
            if len(t.recent_hits) > 20:
                t.recent_hits.pop(0)
        oid = cl.get("object_id")
        if oid:
            save_object_facet(oid, "領域樹", domain["domain_path"][-1])
        _track_domain_hit(domain["domain_path"])
        _track_domain_candidates(text, domain["domain_path"])
        _log_path("/".join(domain["domain_path"]), "領域樹")
        # 結算上一輪的預測
        _settle_prediction("/".join(domain["domain_path"]))
        _detect_isomorphism()
        # 領域樹 bypass 時無 tulpa 競爭，跳過觀察者
        prune_cycle()
        # (A1 fix) 實驗/創造者循環每輪都跑（含領域樹 routed），才能消費已核准 conflict → split 建議
        _run_experiment_cycle(text)
        time_axis = _time_axis_compete(text)
        return {
            "winner": "領域樹",
            "score": 1.0,
            "context": domain["context"],
            "runners_up": [],
            "object_id": oid,
            "ontology": cl,
            "domain_path": domain["domain_path"],
            "time_axis": time_axis,
        }

    # ── Step 0.75: 被動知識搜尋（按需加載，僅在領域樹未命中時）──
    knowledge = None
    if not domain["routed"]:
        ks = passive_search(text)
        if ks["found"]:
            knowledge = ks

    activate = cl["activate"]  # None = 全喚醒, list = 只喚醒這些
    facets = cl["facets"]
    object_id = cl["object_id"]

    scored = []
    for t in TULPAS:
        # 跳過休眠中的 tulpa
        if t._sleeping:
            t.recent_hits.append(0)
            if len(t.recent_hits) > 20:
                t.recent_hits.pop(0)
            continue
        # 如果分類器指定只喚醒某些 tulpa，跳過不在清單內的
        if activate is not None and t.name not in activate:
            t.recent_hits.append(0)
            if len(t.recent_hits) > 20:
                t.recent_hits.pop(0)
            continue
        s = score_tulpa(t, text)
        if s > 0:
            scored.append((t, s))
            t.lifetime_hits += 1
            t.recent_hits.append(1)
            if len(t.recent_hits) > 20:
                t.recent_hits.pop(0)
        else:
            t.recent_hits.append(0)
            if len(t.recent_hits) > 20:
                t.recent_hits.pop(0)

    if not scored:
        ctx = "一般對話，沒有特別的關鍵字"
        if knowledge:
            ctx += "\n\n【參考資料】\n" + knowledge["content"][:1000]
        _log_path("知識")
        _detect_isomorphism()
        prune_cycle()
        return {"winner": "知識", "score": 0.3,
                "context": ctx, "runners_up": [],
                "object_id": None, "ontology": cl,
                "knowledge": knowledge["paths"] if knowledge else None,
                "knowledge_found": knowledge is not None}

    scored.sort(key=lambda x: -x[1])
    winner, winner_score = scored[0]

    # ── 更新 winless_streak ──
    for t, s in scored:
        if t is winner:
            t._winless_streak = 0
        else:
            t._winless_streak += 1

    # ── 贏家強化 + 輸家衰減 ──
    for t, s in scored:
        delta = 0.0
        if t is winner:
            t.base_weight = min(1.5, t.base_weight + 0.02)
            delta = +0.02
        else:
            t.base_weight = max(0.1, t.base_weight * 0.998)
            delta = (t.base_weight / 0.998) - t.base_weight if t.base_weight > 0.1 else 0
        if t.name not in _session_deltas:
            _session_deltas[t.name] = [0, 0, 0.0]
        _session_deltas[t.name][0] += 1
        if t is winner:
            _session_deltas[t.name][1] += 1
        _session_deltas[t.name][2] += round(delta, 4)

    # ── Context 組裝 ──
    runners = [{"name": t.name, "score": s, "gist": t.gist_text}
               for t, s in scored[1:]]
    context = winner.context_text

    # 如果有被動知識載入，注入 context
    if knowledge:
        ctx_lines = []
        for p in knowledge["paths"]:
            short = p.replace(os.path.expanduser("~"), "~")
            ctx_lines.append(f"📄 {short}")
        context += "\n\n【參考資料】\n" + "\n".join(ctx_lines[:2])
        # 內容摘要作為背景注入
        context += "\n\n" + knowledge["content"][:1000]

    # 如果有物件 facet 歷史，注入 context
    if facets:
        facet_lines = [f"  [{f['tulpa_name']}] {f['view']} (×{f['count']})"
                       for f in facets[:3]]
        context += "\n物件歷史:\n" + "\n".join(facet_lines)

    if runners:
        gist_notes = " | ".join(f"[{r['name']}: {r['gist']}]" for r in runners)
        context = f"{context}\n(背景: {gist_notes})"

    # ── 物件 facet ──
    if object_id:
        save_object_facet(object_id, winner.name, winner.context_text)

    # ── Ontology 自動學習 ──
    learn_ontology(text, winner.name)

    # ── 路徑記錄（tulpa fallback）──
    _log_path(winner.name, winner.name)
    # 結算上一輪的預測
    _settle_prediction(winner.name)

    # ── 認知遷移記錄 ──
    _log_migration(winner.name)
    _track_keyword_miss(text)
    _update_ontology_last_seen(text, winner.name)

    # ── Prune cycle + 結構同構檢測 ──
    prune_cycle()
    _detect_isomorphism()

    # ── 第三位置觀察 ──
    _observe_third_position(scored, winner, text)

    # ── 時間軸競爭 ──
    time_axis = _time_axis_compete(text)


    # ── 實驗/創造者循環 ──
    _run_experiment_cycle(text)

    return {"winner": winner.name, "score": winner_score,
            "context": context, "runners_up": runners,
            "object_id": object_id, "ontology": cl,
            "knowledge": knowledge["paths"] if knowledge else None,
            "knowledge_found": knowledge is not None,
            "time_axis": time_axis}


# ═══════════════════════════════════════════════════════════════
# Prune Cycle（去蕪存菁）+ 認知遷移記錄
# ═══════════════════════════════════════════════════════════════

_turn_counter = 0  # 全局輪次計數器，寫 migration_log 用

def _init_keyword_stats():
    """確保每個 tulpa 的每個 keyword 在 keyword_stats 有初始記錄。"""
    db = _db()
    for t in TULPAS:
        for kw in t.keywords:
            db.execute("""
                INSERT INTO keyword_stats (keyword, tulpa_name, lifetime_misses, active)
                VALUES (?, ?, 0, 1)
                ON CONFLICT(keyword, tulpa_name) DO NOTHING
            """, (kw, t.name))
    db.commit()
    db.close()


def _log_migration(tulpa_name: str):
    """記錄一輪的認知遷移（三個參數 vs 預設值）。"""
    t = None
    for x in TULPAS:
        if x.name == tulpa_name:
            t = x
            break
    if t is None:
        return
    # 預設值從 TULPAS 定義裡抓（第一個 match 的預設）
    defaults = {"本我理性": (0.7, 0.6), "本我感性": (0.5, 0.5),
                "自我理性": (0.3, 0.8), "自我感性": (0.3, 0.6),
                "超我理性": (0.3, 0.7), "超我感性": (0.4, 0.7)}
    du, di = defaults.get(tulpa_name, (0.5, 0.5))
    now = datetime.utcnow().isoformat()
    db = _db()
    for param, default_val, current_val in [
        ("base_urgency", du, t.base_urgency),
        ("base_importance", di, t.base_importance),
        ("base_weight", 1.0, t.base_weight),
    ]:
        delta = round(current_val - default_val, 4)
        if abs(delta) < 0.001:
            continue  # 沒變化不記錄，減少雜訊
        db.execute("""
            INSERT INTO migration_log (session_id, turn, tulpa_name, param,
                                       default_val, current_val, delta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (_session_id, _turn_counter, tulpa_name, param,
              default_val, current_val, delta, now))
    db.commit()
    db.close()


def _track_keyword_miss(text: str):
    """記錄每輪沒命中的 keyword（累計 lifetime_misses）。批次寫入。"""
    now = datetime.utcnow().isoformat()
    db = _db()
    updates = []
    for t in TULPAS:
        for kw in t.keywords:
            if kw not in text:
                updates.append((now, kw, t.name))
    if updates:
        db.executemany(
            "UPDATE keyword_stats SET lifetime_misses=lifetime_misses+1, last_miss=? WHERE keyword=? AND tulpa_name=?",
            updates
        )
        db.commit()
    db.close()




def _find_node(path: list, tree=ALL_DOMAINS) -> Optional[object]:
    """依領域路徑(names)定位 DomainNode。方便核准後把 keyword 寫入正確節點。"""
    # path 是 domain_path(names), 從每棵樹根沿 children 往下找
    for d in tree:
        if d.name != path[0]:
            continue
        node = d
        for seg in path[1:]:
            nxt = None
            for ch in node.children:
                if ch.name == seg:
                    nxt = ch; break
            if nxt is None:
                return d  # 找不到更深,回最深匹配
            node = nxt
        return node
    return None



def _path_keywords(domain_path: list) -> set:
    """收集 domain_path 從根到葉所有節點的 keywords,組成「這條路已收錄詞」集合。

    用途:觀察候選詞時,排除路徑上任何已手刻/已收錄的 keyword,
    避免把系統已知詞當成「新詞」提議。
    """
    known = set()
    def walk(node, prefix):
        p = prefix + [node.name]
        known.update(node.keywords)
        for ch in node.children:
            walk(ch, p)
    for d in ALL_DOMAINS:
        walk(d, [])
    return known



def _domain_words() -> list:
    """領域專詞白名單：行業縮寫/高頻連字詞,丟 jieba.add_word 避免被切碎。"""
    return ["斡旋","跟催","下斡","帶看","成交","簽約","出價","追款","售後",
            "過戶","交屋","陌生拜訪","既有客戶","行前準備","帶看中","客戶經營",
            "約客戶","新客戶","老客戶","房仲","房東","斡旋單","看屋"]





def _track_domain_candidates(text: str, domain_path: list):
    """領域樹「生」機制：觀察輸入中未被收錄、但常在同一領域路徑出現的詞彙。

    統計 (候選詞, domain_path) 出現次數。跨過閘門(親自準則)→ 寫入 pending_suggestions
    供人核准,核准後才真正加入該節點 keywords(完整生命週期閉環)。
    """
    if not domain_path:
        return
    path = "/".join(domain_path)
    known = _path_keywords(domain_path)
    # 排除路徑節點名本身（樹名/路名不算候選詞）
    path_names = set(domain_path) | {d.name for d in ALL_DOMAINS}
    now = datetime.utcnow().isoformat()
    db = _db()
    # 掃輸入的「詞」：用 jieba 分詞（正確切出專業詞如「斡旋」）＋ 白名單加持
    import jieba, re as _re
    for w in _domain_words():
        jieba.add_word(w)
    tokens = [w.strip() for w in jieba.cut(text) if w.strip()]
    tokens += _re.findall(r'[a-zA-Z]{2,12}', text)
    for tok in tokens:
        if tok in known:
            continue
        if tok in path_names:
            continue
        if len(tok) < 2 or tok.isdigit():
            continue
        # 候選: 該詞是否在此路徑累計
        db.execute("""
            INSERT INTO domain_keyword_candidates (candidate, domain_path, count, first_seen, last_seen, state)
            VALUES (?, ?, 1, ?, ?, 'observing')
            ON CONFLICT(candidate, domain_path) DO UPDATE SET
                count = count + 1, last_seen = excluded.last_seen
        """, (tok, path, now, now))
    db.commit()

    # 閘門一：同一路徑出現 ≥ N 次 → 提案新詞加入該節點（人核准才生效）
    N = 4
    ready = db.execute(
        "SELECT candidate, domain_path, count FROM domain_keyword_candidates "
        "WHERE state='observing' AND count >= ? AND domain_path=?",
        (N, path)).fetchall()
    for cand in ready:
        conf = min(0.9, 0.4 + 0.1 * cand["count"])
        db.execute("""
            INSERT INTO pending_suggestions (session_id, insight_type, suggested_action, description, confidence, evidence, status, created_at)
            VALUES (?, 'domain_keyword', 'add_keyword', ?, ?, ?, 'pending', ?)
        """, (_session_id, f"新增領域關鍵字「{cand['candidate']}」到 {cand['domain_path']}"
              f"（已出現 {cand['count']} 次於同一路徑）",
              round(conf,2), json.dumps({"candidate": cand["candidate"], "domain_path": cand["domain_path"], "count": cand["count"]}), now))
        db.execute(
            "UPDATE domain_keyword_candidates SET state='proposed' WHERE candidate=? AND domain_path=?",
            (cand["candidate"], cand["domain_path"]))

    # 閘門二（跨路徑湧現）：某詞在多條路徑都出現且總次數高 →
    #   提案為「跨路徑連結/潛在新節點」，符合「湧現的靈感」。
    cross = db.execute("""
        SELECT candidate, COUNT(DISTINCT domain_path) AS npaths, SUM(count) AS total
        FROM domain_keyword_candidates
        WHERE state='observing'
        GROUP BY candidate
        HAVING npaths >= 2 AND total >= ?
    """, (N,)).fetchall()
    for cr in cross:
        conf = min(0.9, 0.4 + 0.1 * cr["total"])
        db.execute("""
            INSERT INTO pending_suggestions (session_id, insight_type, suggested_action, description, confidence, evidence, status, created_at)
            VALUES (?, 'domain_crosslink', 'crosslink', ?, ?, ?, 'pending', ?)
        """, (_session_id, f"跨領域連結：詞「{cr['candidate']}」在 {cr['npaths']} 條路徑共出現 {cr['total']} 次（可能為湧現連結/新節點）",
              round(conf,2), json.dumps({"candidate": cr["candidate"], "npaths": cr["npaths"], "total": cr["total"]}), now))
        db.execute("""
            UPDATE domain_keyword_candidates SET state='proposed' WHERE candidate=? AND state='observing'
        """, (cr["candidate"],))
    db.commit()
    db.close()

def _track_domain_hit(domain_path: list):
    """記錄領域樹命中。"""
    if not domain_path:
        return
    path = "/".join(domain_path)
    now = datetime.utcnow().isoformat()
    db = _db()
    db.execute("""
        INSERT INTO domain_hits (domain_path, hits, last_seen)
        VALUES (?, 1, ?)
        ON CONFLICT(domain_path) DO UPDATE SET
            hits=hits+1, last_seen=excluded.last_seen
    """, (path, now))
    db.commit()
    db.close()


def _update_ontology_last_seen(text: str, winner_name: str):
    """更新 ontology 匹配的 last_seen 與 last_turn。"""
    sig = _make_signature(text)
    db = _db()
    db.execute("""
        UPDATE ontology SET last_seen='', last_turn=?
        WHERE source=? AND relation='pattern→tulpa' AND target=?
    """, (_turn_counter, sig, winner_name))
    db.commit()
    db.close()


# ═══════════════════════════════════════════════════════════════
# 路徑記錄 + 結構同構檢測
# ═══════════════════════════════════════════════════════════════

def _log_path(path: str, tulpa_name: str = ""):
    """記錄一輪的決策路徑到 path_log。"""
    global _turn_counter
    _turn_counter += 1
    now = datetime.utcnow().isoformat()
    depth = path.count("/") + 1 if path else 0
    db = _db()
    db.execute(
        "INSERT INTO path_log (turn, path, depth, tulpa_name, created_at) VALUES (?,?,?,?,?)",
        (_turn_counter, path, depth, tulpa_name, now))
    db.commit()
    db.close()


def _path_similarity(path_a: str, path_b: str) -> float:
    """計算兩條路徑的結構相似度 (0~1)。

    比對邏輯：
      - 同 depth → +0.3
      - 同 L1（根節點）→ +0.3
      - 同 L2（中間節點類型）→ +0.2
      - 同 L3（葉節點類型）→ +0.2
    """
    if not path_a or not path_b:
        return 0.0
    a_parts = path_a.split("/")
    b_parts = path_b.split("/")
    if a_parts == b_parts:
        return 1.0  # 完全相同的路徑

    score = 0.0
    # 深度相同
    if len(a_parts) == len(b_parts):
        score += 0.3
    # L1 相同（根節點）
    if a_parts[0] == b_parts[0]:
        score += 0.3
    # L2 相同
    if len(a_parts) > 1 and len(b_parts) > 1 and a_parts[1] == b_parts[1]:
        score += 0.2
    # L3 相同
    if len(a_parts) > 2 and len(b_parts) > 2 and a_parts[2] == b_parts[2]:
        score += 0.2
    return min(1.0, score)


_last_iso_turn = 0

def _detect_isomorphism():
    global _last_iso_turn
    # 每 5 輪跑一次，避免 O(n²)
    if _turn_counter - _last_iso_turn < 5:
        return
    _last_iso_turn = _turn_counter
    """結構同構檢測：掃描 path_log 最近 50 輪的路徑對。

    如果兩條路徑結構相似度 > 0.7 且出現 3 次以上，
    寫入 structure_isomorphism 表但**不自動合併**——
    只記錄發現，需要用戶確認才合併。
    """
    db = _db()
    cutoff = _turn_counter - 50
    rows = db.execute(
        "SELECT path, depth, COUNT(*) as cnt FROM path_log WHERE turn > ? AND path != '' GROUP BY path",
        (cutoff,)
    ).fetchall()

    if len(rows) < 2:
        db.close()
        return

    # 比對每對路徑
    now = datetime.utcnow().isoformat()
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            pa, pb = rows[i]["path"], rows[j]["path"]
            sim = _path_similarity(pa, pb)
            if sim >= 0.7:
                # 確保 path_a < path_b 按字典序（主鍵一致性）
                if pa > pb:
                    pa, pb = pb, pa
                db.execute("""
                    INSERT INTO structure_isomorphism (path_a, path_b, similarity, hits, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(path_a, path_b) DO UPDATE SET
                        similarity=excluded.similarity, hits=hits+1
                """, (pa, pb, sim, now))
    db.commit()
    db.close()


def prune_cycle():
    """每輪競爭結束後執行：去蕪存菁（turn-based，非日曆）。

    1. tulpa 陪跑：連續 30 輪命中 keyword 但從未贏 → 休眠
    2. tulpa 喚醒：休眠中有 keyword 命中 → 喚醒
    3. keyword 死亡：lifetime_misses > 50 且從未命中過 → 從 keywords list 移除
    4. keyword 喚醒：已移除的 keyword 在輸入中出現 → 重新加入
    5. ontology 衰退：pattern 連續 50 輪沒被任何輸入命中 → strength 歸零
    6. ontology 重啟：舊 pattern 突然命中 → strength 從 0.3 重新開始
    7. facet 壓縮：物件超過 100 輪沒被提及 → 壓縮為最精華的 1-2 個視角
    8. 結構同構檢測：比對 path_log 中的路徑對，發現相似結構 → 記錄
    """
    global _turn_counter

    # ── 1. 陪跑判定 + 2. 喚醒判定 ──
    for t in TULPAS:
        recent_sum = sum(t.recent_hits[-20:])

        if t._sleeping:
            # 休眠中：只要有命中就喚醒
            if recent_sum > 0:
                t._sleeping = False
                t.base_weight = max(0.3, t.base_weight)
        else:
            # 醒著：檢查是否該休眠
            # 條件：有命中（有在競爭）但累計 30 輪沒贏
            if recent_sum > 0 and t._winless_streak >= 30:
                t._sleeping = True
                t.base_weight = 0.2  # 休眠權重

    # ── 3. keyword 死亡（從 tulpa 的 keywords list 移除）──
    db = _db()
    dead_kws = db.execute(
        "SELECT keyword, tulpa_name FROM keyword_stats WHERE lifetime_misses > 50 AND active=1"
    ).fetchall()
    for dk in dead_kws:
        kw, tn = dk["keyword"], dk["tulpa_name"]
        for t in TULPAS:
            if t.name == tn and kw in t.keywords:
                t.keywords.remove(kw)
                t._removed_keywords = getattr(t, '_removed_keywords', [])
                t._removed_keywords.append(kw)
        db.execute("UPDATE keyword_stats SET active=0 WHERE keyword=? AND tulpa_name=?",
                   (kw, tn))
    db.commit()

    # ── 4. keyword 喚醒 ──
    # 發生在 score_tulpa 階段（輸入掃描時），不在 prune cycle 裡做
    # 因為 prune_cycle 執行時已經過了 keyword match 階段

    # ── 5. ontology 衰退 ──
    stale_cutoff = _turn_counter - 50
    db.execute("""
        UPDATE ontology SET strength=0.0
        WHERE relation='pattern→tulpa' AND last_turn > 0 AND last_turn < ?
    """, (stale_cutoff,))
    db.commit()

    # ── 6. ontology 重啟檢查 ──
    # 在 classify() 階段處理（發現 source 存在但 strength=0 → 設回 0.3）

    # ── 7. facet 壓縮 ──
    old_turn = _turn_counter - 100
    db.execute("""
        DELETE FROM object_facets WHERE last_turn > 0 AND last_turn < ?
    """, (old_turn,))
    db.commit()
    db.close()


# ═══════════════════════════════════════════════════════════════
# 第三位置觀察者（meta-tulpa）
# ═══════════════════════════════════════════════════════════════


def _learned_confidence(insight_type: str, base_conf: float) -> float:
    """觀察者學習回饋：根據同 insight_type 的人類審議歷史，調整建議信心。

    核心：不是所有 conflict 同樣可信。若同型一直被 reject → 降信心（優先權後移）；
    常被 approve → 升信心。無歷史則保留 base_conf。這就是「人決策 → AI 學習」的閉環。
    """
    db = _db()
    row = db.execute(
        "SELECT "
        "  COALESCE(SUM(CASE WHEN decision='approve' THEN 1 ELSE 0 END),0) AS appr, "
        "  COALESCE(SUM(CASE WHEN decision='reject' THEN 1 ELSE 0 END),0) AS rej "
        "FROM suggestion_feedback WHERE insight_type=?",
        (insight_type,)).fetchone()
    db.close()
    appr, rej = row["appr"], row["rej"]
    samples = appr + rej
    if samples == 0:
        return base_conf  # 尚無人決策 → 用原始
    rate = appr / samples
    # 信心乘 0.5~1.5：全拒→0.5x，全批→1.5x
    adj = base_conf * (0.5 + rate)
    return round(min(adj, 0.99), 2)



def _observe_third_position(scored: list, winner, text: str):
    """第三位置：不參與競爭，觀察競爭歷史，發現模式。

    檢查四種模式：
    - conflict: 兩個 tulpa 分數相差 < 0.1 且都 > 0.3
    - error: 同一個 tulpa 被糾正多次（winless_streak 高）
    - contradiction: tulpa 贏但 weight 持續下降
    - opportunity: 同一個輸入觸發了兩個不同的領域樹
    """
    if not scored:
        return

    now = datetime.utcnow().isoformat()
    scores = {t.name: s for t, s in scored}

    # 1. conflict：兩個 tulpa 分數接近
    sorted_pairs = sorted(scores.items(), key=lambda x: -x[1])
    for i in range(len(sorted_pairs)):
        for j in range(i + 1, len(sorted_pairs)):
            na, sa = sorted_pairs[i]
            nb, sb = sorted_pairs[j]
            if abs(sa - sb) < 0.1 and sa > 0.3 and sb > 0.3:
                desc = f"衝突: {na}({sa:.3f}) vs {nb}({sb:.3f}) — 分數接近，難以選擇"
                db = _db()
                cur1 = db.execute("""
                    INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, created_at)
                    VALUES (?, 'conflict', ?, ?, ?, ?)
                """, (_turn_counter, desc, json.dumps({"a": na, "b": nb, "score_a": sa, "score_b": sb}),
                      round(min(sa, sb), 2), now))
                insight_id = cur1.lastrowid
                conf = round(min(sa, sb), 2)
                # 升等：所有 conflict 全收（不靜默丟失）；信心用「學習回饋」調整排序。
                #   _learned_confidence：同型曾被 reject 會降信心、常 approved 會升。
                #   → 人長期的決策成為 observer 的學習訊號（閉環）。
                learned_conf = _learned_confidence("conflict", conf)
                db.execute("""
                    INSERT INTO pending_suggestions (session_id, source_insight_id, insight_type, suggested_action, description, confidence, evidence, status, created_at)
                    VALUES (?, ?, 'conflict', 'merge', ?, ?, ?, 'pending', ?)
                """, (_session_id, insight_id, desc, learned_conf, json.dumps({"a": na, "b": nb, "score_a": sa, "score_b": sb}), now))
                db.commit()
                db.close()

    # 2. contradiction：贏家但 weight 持續下降 → 也升等進 pending（不靜默丟失）
    for t, s in scored:
        if t is winner and t.base_weight < 0.9 and t._winless_streak > 5:
            desc = f"矛盾: {t.name} 贏了({s:.3f})但 weight 持續下降({t.base_weight:.3f})"
            db = _db()
            cur2 = db.execute("""
                INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, created_at)
                VALUES (?, 'contradiction', ?, ?, ?, ?)
            """, (_turn_counter, desc, json.dumps({"name": t.name, "weight": t.base_weight, "score": s}),
                  0.5, now))
            insight_id = cur2.lastrowid
            # 學習迴授信心：這型 contradiction 曾被駁回就降優先，常核准就升
            learned_conf = _learned_confidence("contradiction", 0.5)
            db.execute("""
                INSERT INTO pending_suggestions (session_id, source_insight_id, insight_type, suggested_action, description, confidence, evidence, status, created_at)
                VALUES (?, ?, 'contradiction', 'flag_tulpa', ?, ?, ?, 'pending', ?)
            """, (_session_id, insight_id, desc, learned_conf,
                  json.dumps({"name": t.name, "weight": t.base_weight, "score": s}), now))
            db.commit()
            db.close()


# ═══════════════════════════════════════════════════════════════
# 時間軸競爭（過去/現在/未來）
# ═══════════════════════════════════════════════════════════════

def _past_tulpa_score(text: str) -> float:
    """過去 tulpa：根據 path_log 歷史頻率算分。

    過去最常走的路徑，跟當前輸入有多像？
    """
    db = _db()
    rows = db.execute(
        "SELECT path, COUNT(*) as cnt FROM path_log GROUP BY path ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    db.close()
    if not rows:
        return 0.0
    # 取最常見路徑的頻率比例
    total = sum(r["cnt"] for r in rows)
    top_cnt = rows[0]["cnt"]
    return round(top_cnt / max(total, 1), 3)


def _present_tulpa_score(text: str) -> float:
    """現在 tulpa：當前輸入的領域樹匹配強度。"""
    domain = route_domain(text)
    if domain["routed"]:
        return 0.8  # 領域樹命中 → 高信心
    # 沒有領域樹 → 看 ontology 分類
    ontology = _make_signature(text)
    if ontology and ontology != "none":
        return 0.5
    return 0.2  # 一般對話


def _future_tulpa_score(text: str):
    """未來 tulpa：根據 path_log 條件機率預測下一步。

    如果當前輸入匹配某條歷史路徑的起點，
    預測接下來最可能的路徑。
    """
    # 看看當前輸入的領域樹分類
    domain = route_domain(text)
    current_path = "/".join(domain["domain_path"]) if domain["routed"] else ""

    if not current_path:
        return 0.15  # 沒有路徑 → 低信心預測

    # 查 path_log：只取 current_path 的「直接子路徑」當候選
    # (Bug② fix) 舊版抓所有 current||'/...' 兄弟比頻率 → 跟催被「陌生拜訪」頂替誤預測。
    #  現在限縮：predicted 只能是 current 剛好多一層的子路徑（depth = current_depth + 1），
    #  排掉更深層子樹，避免「抓整個兄弟樹」亂猜。
    db = _db()
    cur_depth = current_path.count("/") + 1          # current 深度
    target_depth = cur_depth + 1                     # 直接子路徑深度
    rows = db.execute(
        "SELECT path, COUNT(*) as cnt FROM path_log "
        "WHERE path LIKE ? || '/%' AND path != ? "
        "GROUP BY path ORDER BY cnt DESC LIMIT 3",
        (current_path, current_path)
    ).fetchall()
    # 後端過濾：只留 depth == target_depth（直接子路徑，排除兄弟與更深子樹）
    rows = [r for r in rows if r["path"].count("/") + 1 == target_depth]
    db.close()

    if not rows:
        return 0.2  # 有路徑但沒直接子路徑歷史 → 低信心（不再用兄弟頂替）

    # 如果有歷史，預測信心 = 最常見下一步的頻率比例
    total = sum(r["cnt"] for r in rows)
    top_cnt = rows[0]["cnt"]
    pred_path = rows[0]["path"]
    pred_pct = top_cnt / max(total, 1)
    # (缺口1 fix) 學習迴授：future tulpa 整體由自己的歷史準確率調節。
    #   全域準確率低 → 整個 future 降權（不再信任）；樣本不足時不動（避免過擬似）。
    g_rate, g_samples = _global_prediction_accuracy()
    score = 0.3 + 0.5 * pred_pct
    if g_samples >= 20:                 # 樣本夠才啟動學習（跨尺度穩健）
        if g_rate < 0.3:
            score *= 0.8                 # 全面猜錯 → 降權 20%
        elif g_rate < 0.5:
            score *= 0.9                 # 常錯 → 降權 10%
        # rate >= 0.5 保持原樣
    # (PSI context 注入) stress 高 → 未來預測降權（焦慮時下一步不可靠）；growth 高 → 許可探索
    psi = _psi_state()
    if psi["stress"] > 0.70:
        score *= 0.7                       # 高壓 → future 讓位給 present 動作
    if psi["attention"] == "idle":
        score *= 0.85                      # 沒在關注 → 不該高產預測
    growth_boost = max(0.0, psi["growth"] - 0.5) * 0.15  # growth 超中線 → 加分（願探索新路）
    score += growth_boost
    return {
    "score": round(score, 3),
    "predicted_path": pred_path,
    "confidence": round(pred_pct, 3),
    "total_samples": total,
    "learned": g_samples,
    }




def _active_alerts() -> list:
    """主動警報（不是被動計數）：超過閾值才亮，供健康檢查/心跳消費。

    現有 audit 是被動「有幾個」，這是主動「該不該喊」：
     - PENDING_STACK: 待審建議堆太多（>=10 未決 = 人在卡決策）
     - ACC_DROP: settled 準確率崩潰（>=8 樣本且 <0.3 = 未來預測整體失效）
     - EXPIRED_SURGE: 大量預測未結算就過期（>=15 = 預測根本沒對上）
    """
    db = _db()
    pend = db.execute("SELECT COUNT(*) FROM pending_suggestions WHERE status='pending'").fetchone()[0]
    acc_row = db.execute("SELECT COUNT(*) t, COALESCE(SUM(correct),0) ok FROM prediction_events WHERE state='settled'").fetchone()
    expired = db.execute("SELECT COUNT(*) FROM prediction_events WHERE state='expired'").fetchone()[0]
    db.close()
    alerts = []
    if pend >= 10:
        alerts.append({"type":"PENDING_STACK","level":"warn","msg":f"待審建議堆積 {pend} 筆≥10，人在卡決策","value":pend})
    s_t, s_ok = acc_row["t"], acc_row["ok"]
    if s_t >= 8 and (s_ok/s_t) < 0.3:
        alerts.append({"type":"ACC_CRASH","level":"crit","msg":f"預測準確率僅 {round(s_ok/s_t,2)} ({s_ok}/{s_t})，全域迴授應降權","value":round(s_ok/s_t,2)})
    if expired >= 20:
        alerts.append({"type":"EXPIRED_SURGE","level":"warn","msg":f"已過期未結算預測 {expired} 筆（預測常沒接上才會過期）","value":expired})
    return alerts



def _psi_state() -> dict:
    """读 PSI daemon 外部情境状态（rust 每秒写 10 次的 state file）。

    用途：给 future 决策注入「系统自身情境」参数——stress（克制）与 growth（探索）。
    这不是 ground truth（不校正），是 context 输入（环境变量）。
    文件不存在/读失败 → 返回中性值（不阻塞决策）。
    """
    sp = "/Users/ryan/Developer/laap-AGI/aris_brain/state/rust-latest.json"
    try:
        import json as _j
        d = _j.load(open(sp))
        needs = d.get("needs", {})
        affect = d.get("affect", {})
        det = {
            "stress": float(affect.get("stress", 0.5)),
            "growth": float(needs.get("growth", 0.5)),
            "attention": d.get("attention", "idle"),
            "available": True,
        }
    except Exception:
        det = {"stress": 0.5, "growth": 0.5, "attention": "idle", "available": False}
    return det



def _global_prediction_accuracy() -> tuple:
    """全域預測準確率：settled 預測的 correct/total + 樣本數。

    這是「宏觀自主」一條腿：future tulpa 的整體權重不再由手刻參數決定，
    而由它自己的歷史表現決定。回傳 (rate, samples)。
    樣本不足時 rate=None（避免過擬似列 4 筆髒數據）。
    """
    db = _db()
    row = db.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(correct),0) AS ok "
        "FROM prediction_events WHERE state='settled'"
    ).fetchone()
    db.close()
    total, ok = row["total"], row["ok"]
    if total == 0:
        return None, 0
    return (ok / total), total



def _settle_prediction(actual_path: str) -> None:
    """結算上一輪的 pending 預測：比對 predicted vs actual。

    用 ID 序（不用 turn 號）找最新一筆未結算的預測，避開歷史重啟汙染。
    """
    # (Bug① fix) 匹配式結算：不取「最新 pending」硬對 current，
    # 只找 predicted == actual_path 的 pending 來結（同分支才命中）。
    # 其餘 pending 留在那，等真正走那條路再結；session 結束時統一標 expired。
    db = _db()
    row = db.execute(
        "SELECT id, predicted FROM prediction_events "
        "WHERE state='pending' AND predicted = ? "
        "ORDER BY id ASC LIMIT 1",
        (actual_path,)
    ).fetchone()
    if row is None:
        db.close()
        return
    predicted = row["predicted"]
    ev_id = row["id"]
    correct = 1
    db.execute(
        "UPDATE prediction_events SET actual_turn=?, actual=?, correct=?, state='settled' WHERE id=?",
        (_turn_counter, actual_path, correct, ev_id))
    db.commit()
    db.close()


def _time_axis_compete(text: str) -> dict:
    """時間軸競爭：過去/現在/未來三個 tulpa 打架。

    贏家決定當前的基準值應該參考誰。
    """
    past = _past_tulpa_score(text)
    present = _present_tulpa_score(text)
    future_result = _future_tulpa_score(text)
    future = future_result["score"] if isinstance(future_result, dict) else future_result

    scored = [
        ("past", past),
        ("present", present),
        ("future", future),
    ]
    scored.sort(key=lambda x: -x[1])
    winner, win_score = scored[0]

    # 記錄到 time_axis_log
    now = datetime.utcnow().isoformat()
    predicted_path = future_result.get("predicted_path", "") if isinstance(future_result, dict) else ""
    db = _db()
    db.execute(
        "INSERT INTO time_axis_log (turn, winner, score, past_score, present_score, future_score, predicted_path, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (_turn_counter, winner, win_score, past, present, future, predicted_path, now))
    db.commit()
    db.close()

    # 寫入 pending 預測事件（留給下一輪結算）
    if predicted_path:
        db2 = _db()
        db2.execute(
            "INSERT INTO prediction_events (session_id, pred_turn, predicted, state, created_at) VALUES (?,?,?,'pending',?)",
            (_session_id, _turn_counter, predicted_path, now))
        db2.commit()
        db2.close()

    return {
        "winner": winner,
        "score": win_score,
        "past": past,
        "present": present,
        "future": future,
        "predicted_path": future_result.get("predicted_path", "") if isinstance(future_result, dict) else "",
    }


# ═══════════════════════════════════════════════════════════════
# 實驗/創造者（分裂、合併、跨域串連）
# ═══════════════════════════════════════════════════════════════



def _suggest_merge() -> dict:
    """根據 structure_isomorphism 表，建議合併領域樹節點。

    當兩條路徑相似度持續 > 0.7 且 hits > 5，就是合併時機。
    """
    db = _db()
    rows = db.execute(
        "SELECT path_a, path_b, similarity, hits FROM structure_isomorphism WHERE merged=0 AND similarity >= 0.7 AND hits >= 5 ORDER BY hits DESC LIMIT 3"
    ).fetchall()
    db.close()

    if not rows:
        return {"suggested": False, "reason": "沒有足夠的同構證據"}

    suggestions = []
    for r in rows:
        suggestions.append({
            "path_a": r["path_a"],
            "path_b": r["path_b"],
            "similarity": r["similarity"],
            "hits": r["hits"],
            "suggested_parent": r["path_a"].rsplit("/", 1)[0] if "/" in r["path_a"] else r["path_a"],
        })

    return {"suggested": True, "merges": suggestions}




def _execute_merge(path_a: str, path_b: str) -> str:
    """執行合併：建立一個上層抽象節點，標記兩條路徑為已合併。

    不回傳新的領域樹——只記錄合併操作，由用戶決定是否要寫入程式碼。
    """
    parent = path_a.rsplit("/", 1)[0] if "/" in path_a else path_a
    now = datetime.utcnow().isoformat()

    db = _db()
    # 標記 isomorphism 為已合併
    db.execute("UPDATE structure_isomorphism SET merged=1 WHERE path_a=? AND path_b=?",
               (path_a, path_b))
    # 記錄到 observer_insights
    desc = f"合併執行: {path_a} + {path_b} → 上層抽象 {parent}"
    db.execute("""
        INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, addressed, created_at)
        VALUES (?, 'merge', ?, ?, 0.8, 1, ?)
    """, (_turn_counter, desc, json.dumps({"path_a": path_a, "path_b": path_b, "parent": parent}), now))
    db.commit()
    db.close()

    return parent


def _execute_split(name: str, new_name: str, split_keywords: list) -> bool:
    """執行分裂：建立一個新的 Tulpa 實例，從原 tulpa 分一半 keyword。

    新 Tulpa 被註冊到 TULPAS 陣列，下次競爭就會參與。
    """
    global TULPAS
    source = None
    for t in TULPAS:
        if t.name == name:
            source = t
            break
    if not source:
        return False

    remaining_kw = [kw for kw in source.keywords if kw not in split_keywords]
    new_t = Tulpa(
        name=new_name,
        keywords=split_keywords,
        base_urgency=source.base_urgency,
        base_importance=source.base_importance,
        base_weight=0.5,
        context_text=f"專注於 {new_name} 相關的任務",
        gist_text=f"涉及 {new_name}",
    )
    TULPAS.append(new_t)
    source.keywords = remaining_kw

    # 記錄
    now = datetime.utcnow().isoformat()
    db = _db()
    desc = f"分裂: {name} → {name}({len(remaining_kw)} kw) + {new_name}({len(split_keywords)} kw)"
    db.execute("""
        INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, addressed, created_at)
        VALUES (?, 'split', ?, ?, 0.7, 1, ?)
    """, (_turn_counter, desc, json.dumps({"source": name, "new": new_name, "split_kw": split_keywords}), now))
    db.commit()
    db.close()

    return True


def _run_experiment_cycle(text: str):
    """每輪執行一次實驗/創造者循環。

    檢查所有觀察者洞見，提出架構改變建議，
    但**不自動執行**——只記錄建議，等用戶確認。
    """
    # 1. 檢查是否有可合併的結構同構
    merge_suggestion = _suggest_merge()
    if merge_suggestion["suggested"]:
        for m in merge_suggestion["merges"]:
            desc = f"建議合併: {m['path_a']} 和 {m['path_b']}（相似度 {m['similarity']}，已出現 {m['hits']} 次）"
            db = _db()
            db.execute("""
                INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, addressed, created_at)
                VALUES (?, 'merge_suggestion', ?, ?, ?, 0, ?)
            """, (_turn_counter, desc, json.dumps(m), round(m["similarity"], 2),
                  datetime.utcnow().isoformat()))
            db.commit()
            db.close()


    # 3. (A1) 分裂建議：已被核准的 conflict/contradiction → 建議把太廣的 tulpa 拆開
    db = _db()
    stubs = db.execute("""
        SELECT ps.id, ps.insight_type, ps.evidence, ps.description
        FROM pending_suggestions ps
        WHERE ps.status='approve' AND ps.insight_type IN ('conflict','contradiction')
          AND NOT EXISTS (SELECT 1 FROM pending_suggestions x WHERE x.insight_type='split' AND x.status='pending')
        ORDER BY ps.id DESC LIMIT 1
    """).fetchall()
    for st in stubs:
        ev = json.loads(st["evidence"] or "{}")
        names = []
        if "a" in ev: names.append(ev["a"])
        if "b" in ev: names.append(ev["b"])
        if "name" in ev: names.append(ev["name"])
        if not names:
            continue
        desc = f"分裂建議: {','.join(names)} 長期衝突/矛盾，建議拆成更專注的子人格"
        db.execute("""
            INSERT INTO pending_suggestions (session_id, insight_type, suggested_action, description, confidence, evidence, status, created_at)
            VALUES (?, 'split', 'split_tulpa', ?, ?, ?, 'pending', ?)
        """, (_session_id, desc, 0.5, json.dumps({"names": names, "from_approved": st["id"]}),
              datetime.utcnow().isoformat()))
    db.commit()
    db.close()


# ═══════════════════════════════════════════════════════════════
# HTTP 服務
# ═══════════════════════════════════════════════════════════════

async def handle_cognitive(request):
    try:
        if request.method == "POST":
            body = await request.json()
            text = (body or {}).get("text", "")
        else:
            text = request.query.get("text", "")
        if not text:
            return web.json_response({"error": "text required"}, status=400)

        result = compete(text)

        # 如果需要查詢物件的 facet 歷史
        oid = result.get("object_id")
        if oid:
            facets = load_object_facets(oid)
            if facets:
                result["object_facets"] = facets

        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request):
    """系統健康狀態 + 即時警報。"""
    db = _db()
    sleeping = db.execute("SELECT name FROM tulpa_state WHERE sleep_until IS NOT NULL").fetchall()
    inactive_kw = db.execute("SELECT COUNT(*) as cnt FROM keyword_stats WHERE active=0").fetchone()["cnt"]
    iso_pending = db.execute("SELECT COUNT(*) as cnt FROM structure_isomorphism WHERE merged=0 AND hits>=5").fetchone()["cnt"]
    conflict_count = db.execute("SELECT COUNT(*) as cnt FROM observer_insights WHERE insight_type='conflict' AND addressed=0").fetchone()["cnt"]
    motw_count = db.execute("SELECT COUNT(*) as cnt FROM observer_insights WHERE insight_type='motw_mismatch' AND addressed=0").fetchone()["cnt"]
    contradiction_count = db.execute("SELECT COUNT(*) as cnt FROM observer_insights WHERE insight_type='contradiction' AND addressed=0").fetchone()["cnt"]
    db.close()

    warnings = []
    if sleeping:
        warnings.append(f"{len(sleeping)} 個 tulpa 休眠中: {', '.join(r['name'] for r in sleeping)}")
    if inactive_kw > 0:
        warnings.append(f"{inactive_kw} 個 keyword 已標記為不活躍")
    if iso_pending > 0:
        warnings.append(f"{iso_pending} 組結構同構待合併建議")
    if conflict_count > 0:
        warnings.append(f"{conflict_count} 組未解決的 tulpa 衝突")
    if motw_count > 0:
        warnings.append(f"{motw_count} 次預測與實際路徑不一致")
    if contradiction_count > 0:
        warnings.append(f"{contradiction_count} 個矛盾（贏家權重持續下降）")

    # (D) 主動警報：超過閾值才亮，供心跳/外部 epoll 消費（非被動計數）
    active = _active_alerts()
    has_crit = any(a["level"] == "crit" for a in active)
    return web.json_response({
        "status": "crit" if has_crit else ("warn" if active else ("ok" if not sleeping else "degraded")),
        "port": 18428,
        "tulpas": len(TULPAS),
        "engine": "competition (urgency×importance×weight)",
        "session_id": _session_id,
        "session_turns": sum(v[0] for v in _session_deltas.values()),
        "warnings_count": len(warnings),
        "warnings": warnings,
        "active_alerts": active,
    })


async def handle_audit(request):
    """完整稽核報告：所有異常、警告、風險、盲點、預測失敗——不隱瞞。
    
    這是給「找到進化的路」用的——不是給機器看的，是給人看的。
    """
    db = _db()

    # 1. 休眠 tulpa
    sleeping = [r["name"] for r in
                db.execute("SELECT name FROM tulpa_state WHERE sleep_until IS NOT NULL").fetchall()]

    # 2. 不活躍 keyword
    inactive_kw = [dict(r) for r in
                   db.execute("SELECT keyword, tulpa_name, lifetime_misses FROM keyword_stats WHERE active=0 ORDER BY lifetime_misses DESC LIMIT 20").fetchall()]

    # 3. 未合併的同構建議
    iso_pending = [dict(r) for r in
                   db.execute("SELECT path_a, path_b, ROUND(similarity,2) as sim, hits FROM structure_isomorphism WHERE merged=0 AND hits>=3 ORDER BY hits DESC").fetchall()]

    # 4. MOTW 預測失敗
    motw_fails = [dict(r) for r in
                  db.execute("SELECT id, turn, description, confidence FROM observer_insights WHERE insight_type='motw_mismatch' AND addressed=0 ORDER BY turn DESC LIMIT 10").fetchall()]

    # 5. 未解決衝突
    conflicts = [dict(r) for r in
                 db.execute("SELECT id, turn, description, confidence FROM observer_insights WHERE insight_type='conflict' AND addressed=0 ORDER BY turn DESC LIMIT 10").fetchall()]

    # 6. 矛盾（贏家 weight 降）
    contradictions = [dict(r) for r in
                      db.execute("SELECT id, turn, description, confidence FROM observer_insights WHERE insight_type='contradiction' AND addressed=0 ORDER BY turn DESC LIMIT 10").fetchall()]

    db.close()

    # 7. 收斂風險：migration_log 中 delta 是否在收斂
    # 如果 delta 震盪幅度大（發散）→ 警告
    conv_risk = []
    db = _db()
    for t in TULPAS:
        rows = db.execute(
            "SELECT delta FROM migration_log WHERE tulpa_name=? ORDER BY id DESC LIMIT 20",
            (t.name,)
        ).fetchall()
        if len(rows) >= 5:
            deltas = [r["delta"] for r in rows]
            avg = sum(deltas) / len(deltas)
            variance = sum((d - avg) ** 2 for d in deltas) / len(deltas)
            if variance > 0.01:
                conv_risk.append({
                    "tulpa": t.name,
                    "variance": round(variance, 4),
                    "avg_delta": round(avg, 4),
                    "risk": "發散中 — 認知遷移未收斂，可能與用戶默契未建立",
                })
    db.close()

    # 8. 時間軸風險：預測信心長期偏低
    time_risk = []
    db = _db()
    rows = db.execute(
        "SELECT winner, past_score, present_score, future_score FROM time_axis_log ORDER BY turn DESC LIMIT 20"
    ).fetchall()
    if rows:
        future_wins = sum(1 for r in rows if r["winner"] == "future")
        total = len(rows)
        if total > 5 and future_wins / total < 0.1:
            time_risk.append(f"未來 tulpa 勝率僅 {future_wins}/{total}（{round(future_wins/total*100)}%），預測能力不足")
    db.close()

    # 9. 領域樹覆蓋率
    domain_risk = []
    db = _db()
    for domain in ALL_DOMAINS:
        cnt = db.execute(
            "SELECT COUNT(*) as cnt FROM path_log WHERE path LIKE ? || '%'",
            (domain.name,)
        ).fetchone()["cnt"]
        if cnt == 0:
            domain_risk.append(f"領域樹「{domain.name}」從未被觸發過")
    db.close()

    # 10. 預測結算健康指標：pending(待驗證) / expired(session 結束未結) 為資訊，非錯誤
    db = _db()
    n_pending = db.execute("SELECT COUNT(*) FROM prediction_events WHERE state='pending'").fetchone()[0]
    n_expired = db.execute("SELECT COUNT(*) FROM prediction_events WHERE state='expired'").fetchone()[0]
    n_settled = db.execute("SELECT COUNT(*) FROM prediction_events WHERE state='settled'").fetchone()[0]
    n_pend_sugg = db.execute("SELECT COUNT(*) FROM pending_suggestions WHERE status='pending'").fetchone()[0]
    acc = db.execute("SELECT COUNT(*) t, COALESCE(SUM(correct),0) ok FROM prediction_events WHERE state='settled'").fetchone()
    db.close()
    s_t, s_ok = acc["t"], acc["ok"]
    learn_rate = (s_ok/s_t) if s_t else None
    learn_state = "active" if s_t >= 20 else "waiting"

    return web.json_response({
        "summary": {
            "sleeping_tulpas": len(sleeping),
            "inactive_keywords": len(inactive_kw),
            "pending_merges": len(iso_pending),
            "motw_failures": len(motw_fails),
            "unresolved_conflicts": len(conflicts),
            "contradictions": len(contradictions),
            "convergence_risks": len(conv_risk),
            "time_axis_risks": len(time_risk),
            "domain_risks": len(domain_risk),
            "unsettled_predictions": n_pending,
            "expired_predictions": n_expired,
            "settled_predictions": n_settled,
            "pending_suggestions": n_pend_sugg,
            "learning_loop": {
                "state": learn_state,
                "settled_samples": s_t,
                "accuracy": learn_rate,
                "target": 20,
                "remaining_to_active": max(0, 20 - s_t),
                "note": ("迴授進入調節" if learn_state=="active" else f"迴授等待中（樣本 {s_t}/20 才啟動降權，避免過擬似）"),
            },
            "total_alerts": len(sleeping) + len(inactive_kw) + len(iso_pending) + len(motw_fails) + len(conflicts) + len(contradictions) + len(conv_risk) + len(time_risk) + len(domain_risk),
        },
        "alerts": {
            "sleeping_tulpas": sleeping,
            "inactive_keywords": inactive_kw,
            "pending_merges": iso_pending,
            "motw_failures": motw_fails,
            "conflicts": conflicts,
            "contradictions": contradictions,
            "convergence_risks": conv_risk,
            "time_axis_risks": time_risk,
            "domain_risks": domain_risk,
        },
    })


async def handle_state(request):
    """回傳所有 tulpa 的當前持久化狀態。"""
    rows = []
    for t in TULPAS:
        rows.append({
            "name": t.name,
            "base_urgency": t.base_urgency,
            "base_importance": t.base_importance,
            "base_weight": round(t.base_weight, 4),
            "lifetime_hits": t.lifetime_hits,
            "recent_hits_20": sum(t.recent_hits[-20:]),
            "corrections": t.corrections,
        })
    return web.json_response({"tulpas": rows, "session_id": _session_id})


async def handle_migration(request):
    """回傳認知遷移記錄。可選 query param: tulpa=名稱 過濾單個。"""
    db = _db()
    tulpa_filter = request.query.get("tulpa", "")
    if tulpa_filter:
        rows = db.execute(
            "SELECT * FROM migration_log WHERE tulpa_name=? ORDER BY turn DESC LIMIT 100",
            (tulpa_filter,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM migration_log ORDER BY turn DESC LIMIT 200"
        ).fetchall()
    db.close()
    result = []
    for r in rows:
        result.append({
            "session_id": r["session_id"],
            "turn": r["turn"],
            "tulpa_name": r["tulpa_name"],
            "param": r["param"],
            "default_val": r["default_val"],
            "current_val": r["current_val"],
            "delta": r["delta"],
            "created_at": r["created_at"],
        })
    return web.json_response({"migrations": result, "count": len(result)})


async def handle_prune_status(request):
    """回傳 prune 狀態 + 同構發現。"""
    db = _db()
    sleeping = [r["name"] for r in
                db.execute("SELECT name FROM tulpa_state WHERE sleep_until IS NOT NULL").fetchall()]
    inactive_kw = [dict(r) for r in
                   db.execute("SELECT keyword, tulpa_name, lifetime_misses FROM keyword_stats WHERE active=0").fetchall()]
    domain_rows = [dict(r) for r in
                   db.execute("SELECT domain_path, hits, last_seen FROM domain_hits ORDER BY hits DESC").fetchall()]
    # 結構同構發現
    iso_rows = [dict(r) for r in
                db.execute("SELECT path_a, path_b, ROUND(similarity,2) as sim, hits, merged FROM structure_isomorphism ORDER BY similarity DESC, hits DESC LIMIT 20").fetchall()]
    # 路徑統計
    path_counts = [dict(r) for r in
                   db.execute("SELECT path, COUNT(*) as cnt FROM path_log WHERE turn > ? GROUP BY path ORDER BY cnt DESC LIMIT 10",
                              (_turn_counter - 50,)).fetchall()]
    db.close()
    return web.json_response({
        "sleeping_tulpas": sleeping,
        "inactive_keywords": inactive_kw,
        "domain_hits": domain_rows,
        "isomorphisms": iso_rows,
        "recent_paths": path_counts,
    })


async def handle_observer(request):
    """回傳第三位置觀察者的洞見。"""
    db = _db()
    insight_type = request.query.get("type", "")
    limit = min(int(request.query.get("limit", 20)), 100)
    if insight_type:
        rows = db.execute(
            "SELECT * FROM observer_insights WHERE insight_type=? ORDER BY turn DESC LIMIT ?",
            (insight_type, limit)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM observer_insights ORDER BY turn DESC LIMIT ?",
            (limit,)
        ).fetchall()
    db.close()
    insights = []
    for r in rows:
        insights.append({
            "id": r["id"],
            "turn": r["turn"],
            "type": r["insight_type"],
            "description": r["description"],
            "evidence": json.loads(r["evidence"]) if r["evidence"] else {},
            "confidence": r["confidence"],
            "addressed": r["addressed"],
        })
    return web.json_response({"insights": insights, "count": len(insights)})


async def handle_time_axis(request):
    """回傳時間軸競爭記錄。"""
    db = _db()
    rows = db.execute(
        "SELECT * FROM time_axis_log ORDER BY turn DESC LIMIT 50"
    ).fetchall()
    db.close()
    records = []
    for r in rows:
        records.append({
            "turn": r["turn"],
            "winner": r["winner"],
            "score": r["score"],
            "past": r["past_score"],
            "present": r["present_score"],
            "future": r["future_score"],
            "predicted_path": r["predicted_path"],
        })
    return web.json_response({"records": records, "count": len(records)})



async def handle_sessionperf(request):
    """跨 session 消費 session_delta：每支 tulpa 在每次 session 的績效軌跡。

    這是「宏觀自主」素材：weight drift 是每 session 累積的，跨 session 看
    是否穩定學習（W% 升 / delta 收斂）而非震盪。讓原本死掉的 session_delta 成為分析依據。
    """
    db = _db()
    rows = db.execute("""
        SELECT tulpa_name, session_id, turns, wins, delta_weight, created_at
        FROM session_delta ORDER BY created_at ASC
    """).fetchall()
    db.close()
    # 每 tulpa 聚合：跨 session 軌跡
    by_tulpa = {}
    for r in rows:
        b = by_tulpa.setdefault(r["tulpa_name"], {"sessions": [], "total_turns": 0, "total_wins": 0, "total_delta": 0.0})
        b["sessions"].append({
            "session_id": r["session_id"], "turns": r["turns"], "wins": r["wins"],
            "win_rate": round(r["wins"]/r["turns"],3) if r["turns"] else 0,
            "delta_weight": r["delta_weight"]
        })
        b["total_turns"] += r["turns"]; b["total_wins"] += r["wins"]; b["total_delta"] += r["delta_weight"]
    out = []
    for name, b in by_tulpa.items():
        out.append({
            "tulpa": name,
            "sessions_count": len(b["sessions"]),
            "total_turns": b["total_turns"],
            "total_wins": b["total_wins"],
            "overall_win_rate": round(b["total_wins"]/b["total_turns"],3) if b["total_turns"] else 0,
            "total_delta_weight": round(b["total_delta"],3),
            "sessions": b["sessions"],
        })
    return web.json_response({"per_tulpa": out, "count": len(out),
                              "note": "session_delta 死表已活化為跨 session 績效分析"})


async def handle_feedback(request):
    """決策回饋分析：observer 建議被審議的歷史 → AI 學了什麼。

    每個 insight_type 的人類 approve/reject 統計 + 信心修正係數，
    供檢視「AI 的判斷品質」與「該調哪個門檻」。
    """
    db = _db()
    rows = db.execute("""
        SELECT insight_type,
               COALESCE(SUM(decision='approve'),0) AS approved,
               COALESCE(SUM(decision='reject'),0)  AS rejected,
               COUNT(*) AS total
        FROM suggestion_feedback GROUP BY insight_type ORDER BY total DESC
    """).fetchall()
    # 未決的 pending 數（還等人審）
    pend = db.execute("SELECT COUNT(*) FROM pending_suggestions WHERE status='pending'").fetchone()[0]
    db.close()
    stats = []
    for r in rows:
        appr, rej = r["approved"], r["rejected"]
        rate = (appr / (appr + rej)) if (appr + rej) else 0
        stats.append({
            "insight_type": r["insight_type"],
            "approved": appr,
            "rejected": rej,
            "total": r["total"],
            "approve_rate": round(rate, 3),
            "learned_eff": round(0.5 + rate, 3),  # 信心乘數，反映學習後
        })
    return web.json_response({
        "feedback_stats": stats,
        "pending_awaiting_review": pend,
        "note": "approve_rate 越接近 1 = 人越信任該型；observer 會用 learned_effector 調整新建議信心。",
    })


async def handle_predictions(request):
    """回傳預測事件記錄（含結算結果）"""
    db = _db()
    rows = db.execute(
        "SELECT * FROM prediction_events ORDER BY id DESC LIMIT 30"
    ).fetchall()
    db.close()
    records = []
    for r in rows:
        records.append({
            "id": r["id"],
            "pred_turn": r["pred_turn"],
            "predicted": r["predicted"],
            "actual_turn": r["actual_turn"],
            "actual": r["actual"],
            "correct": r["correct"],
            "state": r["state"],
        })
    return web.json_response({"records": records, "count": len(records)})


async def handle_experiment(request):
    """回傳實驗/創造者的建議。可接受 POST 執行特定操作。"""
    if request.method == "POST":
        try:
            body = await request.json()
            action = body.get("action", "")
            if action == "merge":
                path_a = body.get("path_a", "")
                path_b = body.get("path_b", "")
                if path_a and path_b:
                    parent = _execute_merge(path_a, path_b)
                    return web.json_response({"status": "merged", "parent": parent})
            elif action == "split":
                name = body.get("name", "")
                new_name = body.get("new_name", "")
                split_kw = body.get("split_keywords", [])
                if name and new_name and split_kw:
                    ok = _execute_split(name, new_name, split_kw)
                    return web.json_response({"status": "split" if ok else "failed"})
            elif action == "review":
                # 人審議某筆待審建議：approve（採納，待執行）或 reject（否決）
                suggestion_id = body.get("suggestion_id")
                decision = body.get("decision", "")
                if suggestion_id is not None and decision in ("approve", "reject"):
                    db = _db()
                    row = db.execute(
                        "SELECT insight_type, confidence, suggested_action, evidence FROM pending_suggestions WHERE id=?",
                        (suggestion_id,)).fetchone()
                    if row is None:
                        db.close()
                        return web.json_response({"error": "suggestion not found"}, status=404)
                    # 核准生效：domain_keyword → 真正加進該節關鍵字（並持久化）
                    applied = False
                    if decision == "approve" and row["insight_type"] == "domain_keyword":
                        ev = json.loads(row["evidence"] or "{}")
                        cand, dpath = ev.get("candidate",""), ev.get("domain_path","")
                        if cand and dpath:
                            node = _find_node(dpath.split("/"))
                            if node and cand not in node.keywords:
                                node.keywords.append(cand)
                            db.execute("""
                                INSERT INTO domain_keyword_additions (candidate, domain_path, added_at) VALUES (?,?,?)
                                ON CONFLICT(candidate, domain_path) DO NOTHING
                            """, (cand, dpath, datetime.utcnow().isoformat()))
                            applied = True
                    # 核准生效：tulpa_keyword → 加進該 tulpa.keywords（持久化 overlay）
                    if decision == "approve" and row["insight_type"] == "tulpa_keyword":
                        ev = json.loads(row["evidence"] or "{}")
                        cand, tname = ev.get("candidate",""), ev.get("tulpa_name","")
                        if cand and tname:
                            tgt = next((t for t in TULPAS if t.name == tname), None)
                            if tgt and cand not in tgt.keywords:
                                tgt.keywords.append(cand)
                            db.execute("""
                                INSERT INTO tulpa_keyword_addition (candidate, tulpa_name, added_at) VALUES (?,?,?)
                                ON CONFLICT(candidate, tulpa_name) DO NOTHING
                            """, (cand, tname, datetime.utcnow().isoformat()))
                            applied = True
                    # 核准生效：domain_crosslink → 把這詞加入它出現過的所有路徑節點（跨分支生效）
                    if decision == "approve" and row["insight_type"] == "domain_crosslink":
                        ev = json.loads(row["evidence"] or "{}")
                        cand = ev.get("candidate","")
                        if cand:
                            paths = db.execute(
                                "SELECT domain_path FROM domain_keyword_candidates WHERE candidate=?",
                                (cand,)).fetchall()
                            for p in paths:
                                node = _find_node(p["domain_path"].split("/"))
                                if node and cand not in node.keywords:
                                    node.keywords.append(cand)
                                db.execute("""
                                    INSERT INTO domain_keyword_additions (candidate, domain_path, added_at) VALUES (?,?,?)
                                    ON CONFLICT(candidate, domain_path) DO NOTHING
                                """, (cand, p["domain_path"], datetime.utcnow().isoformat()))
                            applied = True
                    # 更新建議狀態
                    db.execute(
                        "UPDATE pending_suggestions SET status=? WHERE id=?",
                        (decision, suggestion_id))
                    # (A2) insight 生命週期閉合：審議後，源頭 observer_insights 標 addressed
                    db.execute(
                        "UPDATE observer_insights SET addressed=1 WHERE id IN "
                        "(SELECT source_insight_id FROM pending_suggestions WHERE id=?)",
                        (suggestion_id,))
                    # 記錄決策回饋（供 observer 學習）
                    db.execute(
                        "INSERT INTO suggestion_feedback (suggestion_id, insight_type, decision, confidence, decided_at) VALUES (?,?,?,?,?)",
                        (suggestion_id, row["insight_type"], decision, row["confidence"],
                         datetime.utcnow().isoformat()))
                    db.commit()
                    db.close()
                    return web.json_response({"status": "reviewed", "suggestion_id": suggestion_id, "decision": decision,
                                              "applied": applied})
                return web.json_response({"error": "review needs suggestion_id + decision"}, status=400)
            return web.json_response({"error": "unknown action"}, status=400)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # GET: 回傳建議（含 observer 升等的待審建議）
    merge_sugg = _suggest_merge()
    db = _db()
    pend = db.execute(
        "SELECT id, insight_type, suggested_action, description, confidence, evidence, status "
        "FROM pending_suggestions WHERE status='pending' ORDER BY confidence DESC LIMIT 30"
    ).fetchall()
    db.close()
    pend_records = [dict(r) for r in pend]
    return web.json_response({
        "merge_suggestions": merge_sugg.get("merges", []),
        "merge_suggested": merge_sugg["suggested"],
        "pending_suggestions": pend_records,
        "pending_count": len(pend_records),
    })


async def handle_blindspot(request):
    """周哈里窗盲點報告：系統的三大盲點。

    1. 最大的遺漏是什麼？
    2. 沒有意識到什麼？
    3. 最沒把握的是什麼？

    這是給人看的，不是給機器看的。每個答案附來源。
    """
    db = _db()

    # ── 1. 最大的遺漏 ──
    # 已發現但未合併的結構同構
    iso_pending = db.execute(
        "SELECT path_a, path_b, hits, ROUND(similarity,2) as sim FROM structure_isomorphism WHERE merged=0 AND hits>=3 ORDER BY hits DESC LIMIT 5"
    ).fetchall()
    # 觀察者已記錄但未處理的 conflict
    unaddressed_conflicts = db.execute(
        "SELECT description FROM observer_insights WHERE insight_type IN ('conflict','contradiction','motw_mismatch') AND addressed=0 ORDER BY turn DESC LIMIT 5"
    ).fetchall()

    biggest_miss = []
    for r in iso_pending:
        biggest_miss.append(f"結構同構待合併: {r['path_a']} 和 {r['path_b']}（相似度 {r['sim']}，已出現 {r['hits']} 次）")
    for r in unaddressed_conflicts:
        biggest_miss.append(r["description"])

    # ── 2. 沒有意識到什麼 ──
    # 出現次數少於 3 次的路徑（系統走過但沒形成模式）
    rare_paths = db.execute(
        "SELECT path, COUNT(*) as cnt FROM path_log GROUP BY path HAVING cnt < 3 ORDER BY cnt ASC LIMIT 5"
    ).fetchall()
    # 從未被觸發過的領域樹
    unused_domains = []
    for domain in ALL_DOMAINS:
        cnt = db.execute(
            "SELECT COUNT(*) as cnt FROM path_log WHERE path LIKE ? || '%'",
            (domain.name,)
        ).fetchone()["cnt"]
        if cnt == 0:
            unused_domains.append(domain.name)
    # 從未被命中的 keyword
    never_hit = db.execute(
        "SELECT keyword, tulpa_name FROM keyword_stats WHERE lifetime_misses > 50 AND active=1 LIMIT 5"
    ).fetchall()

    unaware = []
    for r in rare_paths:
        unaware.append(f"低頻路徑: 「{r['path']}」只出現過 {r['cnt']} 次，可能代表新習慣的起點")
    for d in unused_domains:
        unaware.append(f"領域樹「{d}」從未被觸發過，可能無效或需調整 keyword")
    for r in never_hit:
        unaware.append(f"keyword 「{r['keyword']}」（{r['tulpa_name']}）從未命中過，待 prune 機制處理")

    # ── 3. 最沒把握的是什麼 ──
    # ontology 中 strength 在 0.3~0.6 之間的（有證據但不夠多）
    weak_ontology = db.execute(
        "SELECT source, target, ROUND(strength,2) as str, hits FROM ontology WHERE strength BETWEEN 0.3 AND 0.6 ORDER BY strength ASC LIMIT 5"
    ).fetchall()
    # 時間軸中未來 tulpa 的勝率（預測能力）
    future_wins = db.execute(
        "SELECT COUNT(*) as cnt FROM time_axis_log WHERE winner='future'"
    ).fetchone()["cnt"]
    total_time = db.execute(
        "SELECT COUNT(*) as cnt FROM time_axis_log"
    ).fetchone()["cnt"]
    # migration_log 中 delta 還在震盪的 tulpa
    unstable = []
    for t in TULPAS:
        rows = db.execute(
            "SELECT delta FROM migration_log WHERE tulpa_name=? ORDER BY id DESC LIMIT 15",
            (t.name,)
        ).fetchall()
        if len(rows) >= 5:
            deltas = [r["delta"] for r in rows]
            avg = sum(deltas) / len(deltas)
            variance = sum((d - avg) ** 2 for d in deltas) / len(deltas)
            if variance > 0.005:
                unstable.append(f"{t.name}: delta 變異數 {variance:.4f}，認知遷移未收斂")

    db.close()

    unsure = []
    for r in weak_ontology:
        unsure.append(f"ontology 弱信號: 「{r['source']}」→「{r['target']}」強度僅 {r['str']}（命 {r['hits']} 次）")
    if total_time > 0:
        future_pct = round(future_wins / total_time * 100)
        if future_pct < 30:
            unsure.append(f"預測能力不足: 未來 tulpa 僅勝 {future_wins}/{total_time} 次（{future_pct}%）")
    for u in unstable[:3]:
        unsure.append(u)

    return web.json_response({
        "最大的遺漏": biggest_miss if biggest_miss else ["目前無重大遺漏"],
        "沒有意識到的事": unaware if unaware else ["目前無明顯盲點"],
        "最沒把握的事": unsure if unsure else ["目前無弱信號"],
        "summary": {
            "遺漏數": len(biggest_miss),
            "盲點數": len(unaware),
            "弱信號數": len(unsure),
            "總計": len(biggest_miss) + len(unaware) + len(unsure),
        },
    })


async def handle_convergence(request):
    """習慣收斂曲線：每個 tulpa 的認知遷移 delta 趨勢。

    收斂 = 參數趨近穩定，習慣建立
    發散 = 參數持續震盪，習慣未建立
    """
    db = _db()
    result = []
    for t in TULPAS:
        rows = db.execute(
            "SELECT delta, created_at FROM migration_log WHERE tulpa_name=? ORDER BY id ASC LIMIT 50",
            (t.name,)
        ).fetchall()
        if len(rows) < 3:
            continue
        deltas = [r["delta"] for r in rows]
        recent = deltas[-10:]
        avg = sum(deltas) / len(deltas)
        recent_avg = sum(recent) / len(recent)
        variance = sum((d - avg) ** 2 for d in deltas) / len(deltas)
        direction = "收斂" if variance < 0.005 else ("發散" if variance > 0.01 else "震盪")
        result.append({
            "tulpa": t.name,
            "weight": round(t.base_weight, 3),
            "delta_avg": round(avg, 4),
            "delta_recent_avg": round(recent_avg, 4),
            "variance": round(variance, 6),
            "direction": direction,
            "samples": len(deltas),
        })
    db.close()
    result.sort(key=lambda x: x["variance"], reverse=True)
    return web.json_response({
        "convergence": result,
        "summary": {
            "收斂": sum(1 for r in result if r["direction"] == "收斂"),
            "震盪": sum(1 for r in result if r["direction"] == "震盪"),
            "發散": sum(1 for r in result if r["direction"] == "發散"),
            "總計": len(result),
        },
    })


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def _apply_domain_keyword_additions():
    """啟動時把已核准的新詞 overlay 回領域樹節點＋tulpa keywords（持久化生效）。"""
    db = _db()
    rows = db.execute("SELECT candidate, domain_path FROM domain_keyword_additions").fetchall()
    db.close()
    for r in rows:
        node = _find_node(r["domain_path"].split("/"))
        if node and r["candidate"] not in node.keywords:
            node.keywords.append(r["candidate"])
    # tulpa overlay：核准的 tulpa keyword 寫回對應 tulpa.keywords
    db = _db()
    trows = db.execute("SELECT candidate, tulpa_name FROM tulpa_keyword_addition").fetchall()
    db.close()
    for r in trows:
        tgt = next((t for t in TULPAS if t.name == r["tulpa_name"]), None)
        if tgt and r["candidate"] not in tgt.keywords:
            tgt.keywords.append(r["candidate"])
    return len(rows) + len(trows)



def main():
    global _session_id, _session_start

    _init_db()
    _init_keyword_stats()
    _apply_domain_keyword_additions()
    persisted = load_tulpa_state()
    for t in TULPAS:
        _apply_persisted(t, persisted)

    _session_id = datetime.utcnow().strftime("s%Y%m%d_%H%M%S")
    _session_start = time.time()

    # session 起動：把上一 session 仍 pending 的預測標 expired（自然死亡，非 timeout）
    db = _db()
    db.execute(
        "UPDATE prediction_events SET state='expired' WHERE state='pending' AND session_id != ?",
        (_session_id,))
    db.commit()
    db.close()

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18428
    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)
    app.router.add_get("/audit", handle_audit)
    app.router.add_get("/blindspot", handle_blindspot)
    app.router.add_get("/convergence", handle_convergence)
    app.router.add_get("/state", handle_state)
    app.router.add_get("/migration", handle_migration)
    app.router.add_get("/prune", handle_prune_status)
    app.router.add_get("/observer", handle_observer)
    app.router.add_get("/timeaxis", handle_time_axis)
    app.router.add_get("/predictions", handle_predictions)
    app.router.add_get("/feedback", handle_feedback)
    app.router.add_get("/sessionperf", handle_sessionperf)
    app.router.add_get("/experiment", handle_experiment)
    app.router.add_post("/experiment", handle_experiment)
    app.router.add_get("/cognitive", handle_cognitive)
    app.router.add_post("/cognitive", handle_cognitive)

    print(f"[tulpa] 🎤 六個 tulpa 搶麥克風 on :{port}")
    print(f"[tulpa] 💾 記憶: {DB_PATH}")
    print(f"[tulpa] 🆔 session: {_session_id}")

    # 註冊 session 結束時的存檔
    import atexit
    def _shutdown():
        save_tulpa_state(TULPAS)
        save_session_delta()
        print(f"[tulpa] 💾 session {_session_id} 已存檔")
    atexit.register(_shutdown)

    web.run_app(app, port=port)


if __name__ == "__main__":
    main()
