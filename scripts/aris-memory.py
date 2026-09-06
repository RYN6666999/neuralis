#!/usr/bin/env python3
"""aris-memory — 統一記憶層。SQLite 可靠基底 + gbrain 非同步同步。
寫入即查得到，不靠搜尋引擎猜你在找什麼。"""
import sqlite3, json, time, os, re, math, threading, hashlib
from pathlib import Path

# ── 三進制哈希（純 stdlib，零依賴）────────────────────────────────────
TERNARY_DIM = 64
TERNARY_PULSE_THRESHOLDS = {5: 1, 20: 2, 50: 3, 100: 4}  # total_recalls → encoding_salience

def _ternary_hash(char: str, dim_idx: int) -> int:
    cp = ord(char)
    if '\u4e00' <= char <= '\u9fff':
        cat = 1
    elif '\u3040' <= char <= '\u30ff':
        cat = 2
    elif 'a' <= char <= 'z' or 'A' <= char <= 'Z':
        cat = 3
    elif '0' <= char <= '9':
        cat = 4
    else:
        cat = 5
    h = 2166136261
    seed = f"{cp}|{cat}|{dim_idx}".encode()
    for b in seed:
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h % 3

def _char_ternary_vec(char: str) -> list:
    return [1 if _ternary_hash(char, d) == 2 else (-1 if _ternary_hash(char, d) == 1 else 0) for d in range(TERNARY_DIM)]

def _sentence_sig(text: str) -> str:
    """句子 → 三元 signature JSON 字串（-1,0,1 陣列）"""
    if not text.strip():
        return json.dumps([0] * TERNARY_DIM)
    unigram = {}
    for ch in text:
        unigram[ch] = unigram.get(ch, 0) + 1
    bigram = {}
    for j in range(len(text) - 1):
        bg = text[j:j+2]
        bigram[bg] = bigram.get(bg, 0) + 1
    total_u = len(text)
    total_b = max(len(text) - 1, 1)

    acc = [0.0] * TERNARY_DIM
    for ch, cnt in unigram.items():
        v = _char_ternary_vec(ch)
        w = cnt / total_u
        for i in range(TERNARY_DIM):
            acc[i] += v[i] * w * 0.65
    for bg, cnt in bigram.items():
        hv = [0.0] * TERNARY_DIM
        for ch in bg:
            cv = _char_ternary_vec(ch)
            for i in range(TERNARY_DIM):
                hv[i] += cv[i]
        for i in range(TERNARY_DIM):
            hv[i] /= 2
        w = cnt / total_b
        for i in range(TERNARY_DIM):
            acc[i] += hv[i] * w * 0.25

    thr = 0.18 if total_u <= 10 else (0.12 if total_u <= 20 else 0.08)
    vec = [1 if v > thr else (-1 if v < -thr else 0) for v in acc]
    return json.dumps(vec)

def _ternary_cosine(sig_a: str, sig_b: str) -> float:
    va = json.loads(sig_a)
    vb = json.loads(sig_b)
    dot = sum(a * b for a, b in zip(va, vb))
    na = math.sqrt(sum(a * a for a in va))
    nb = math.sqrt(sum(b * b for b in vb))
    return dot / (na * nb) if na and nb else 0.0

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


# ── 內容型別分類（C 2026-09-06）────────────────────────────
# Content kind: 記憶寫入時自動辨別「真判斷」vs「垃圾型別」。
# 消費端：固化/清理可依 content_kind != 'judgment' 直接墓碑化/清除，
# 不再靠召回次數當判準（召回高可能只是測試/系統垃圾被重複背）。
_KIND_TEST = ("測試", "test", "concept proof", "概念驗證", "測試寫入", "test content", "POC")
_KIND_SECRET = ("sk-", "AKIA", "ghp_", "xoxb-", "-----BEGIN", "password=", "secret=", "token=", "api_key=")
_KIND_LOG = ("model fallback", "module online", "檢查完畢", "執行成功", "exit 0", "整體狀態 success",
             "健康狀態", "memory log", "cron", "執行報告", "status", "module offline", "報表完成")
_KIND_PROMPT = ("[IMPORTANT: you are running as a scheduled cron", "delivery: your final response will be automatically",
                "review the conversation above and update the skill library", "system reminder", "執行記憶固化")


def _content_kind(content: str, source: str, event_type: str = "") -> str:
    """回傳內容型別：judgment(真判斷)/test/secret/log/prompt/empty。
    由 store() 寫入時呼叫。source=test 直接判 test；其餘靠內容特徵。"""
    c = (content or "").strip()
    if not c:
        return "empty"
    cl = c.lower()
    if source == "test":
        return "test"
    if len(cl) < 12:
        return "empty"  # 太短(<12字)不像能承載判斷
    for pat in _KIND_SECRET:
        if pat.lower() in cl:
            return "secret"
    for pat in _KIND_PROMPT:
        if pat.lower() in cl:
            return "prompt"
    for pat in _KIND_TEST:
        if pat.lower() in cl:
            return "test"
    for pat in _KIND_LOG:
        if pat.lower() in cl:
            return "log"
    return "judgment"


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
    if "content_kind" not in cols:
        adds.append("ALTER TABLE memories ADD COLUMN content_kind TEXT DEFAULT 'judgment'")
    for sql in adds:
        conn.execute(sql)
    # confidence 索引在補欄後才建（既有表補欄前該欄不存在）
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence)")

def _ensure_pending_columns(conn):
    """pending_items 的 idempotent migration —— 補追蹤/優先序/類型/父節點/選項/答覆。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pending_items)").fetchall()}
    adds = []
    if "tracked" not in cols:
        adds.append("ALTER TABLE pending_items ADD COLUMN tracked INTEGER DEFAULT 0")
    if "priority" not in cols:
        adds.append("ALTER TABLE pending_items ADD COLUMN priority INTEGER DEFAULT 0")
    if "p_type" not in cols:
        adds.append("ALTER TABLE pending_items ADD COLUMN p_type TEXT DEFAULT 'task'")
    if "parent_id" not in cols:
        adds.append("ALTER TABLE pending_items ADD COLUMN parent_id INTEGER DEFAULT NULL")
    if "options" not in cols:
        adds.append("ALTER TABLE pending_items ADD COLUMN options TEXT DEFAULT '[]'")
    if "chosen" not in cols:
        adds.append("ALTER TABLE pending_items ADD COLUMN chosen TEXT DEFAULT ''")
    if "answer" not in cols:
        adds.append("ALTER TABLE pending_items ADD COLUMN answer TEXT DEFAULT ''")
    for sql in adds:
        conn.execute(sql)

def _init_extra_tables(conn):
    """Initialize extra tables: memory_sigs, entanglement, pending_items, decision_log."""
    # ── 三進制哈希 signature 表 ────────────────────────────────────
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_sigs (
            mem_id INTEGER PRIMARY KEY,
            sig TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS entanglement (
            word_a TEXT NOT NULL,
            word_b TEXT NOT NULL,
            strength REAL DEFAULT 1.0,
            hits INTEGER DEFAULT 1,
            updated_at REAL NOT NULL,
            PRIMARY KEY (word_a, word_b)
        );
        CREATE INDEX IF NOT EXISTS idx_entanglement_a ON entanglement(word_a);
        CREATE INDEX IF NOT EXISTS idx_entanglement_b ON entanglement(word_b);
        CREATE TABLE IF NOT EXISTS pending_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            blocked_by TEXT DEFAULT '',
            session_id TEXT DEFAULT '',
            source TEXT DEFAULT 'auto',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            closed_at REAL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_items(status);
    """)
    _ensure_pending_columns(conn)
    # 幫既有記憶補 signature（只補沒有的）
    missing = conn.execute(
        "SELECT m.id, m.content FROM memories m LEFT JOIN memory_sigs s ON m.id=s.mem_id WHERE s.mem_id IS NULL"
    ).fetchall()
    for mid, content in missing:
        sig = _sentence_sig(content or "")
        conn.execute("INSERT OR IGNORE INTO memory_sigs (mem_id, sig, updated_at) VALUES (?,?,?)",
                     (mid, sig, time.time()))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS decision_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, route TEXT NOT NULL, task_desc TEXT DEFAULT '', psi_energy REAL DEFAULT 0, psi_competence REAL DEFAULT 0.5, psi_certainty REAL DEFAULT 0.5, psi_growth REAL DEFAULT 0.5, success INTEGER DEFAULT 0, duration REAL DEFAULT 0, error TEXT DEFAULT '', reason TEXT DEFAULT '')")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_route ON decision_log(route)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_psi ON decision_log(psi_energy)")
    except:
        pass
    # ── 既有 decision_log 補 reason 欄（idempotent） ─────────────────
    try:
        dcols = {r[1] for r in conn.execute("PRAGMA table_info(decision_log)").fetchall()}
        if "reason" not in dcols:
            conn.execute("ALTER TABLE decision_log ADD COLUMN reason TEXT DEFAULT ''")
    except Exception:
        pass
    # ── 情緒記憶表（Critic-Reward-Learner 專用）────────────────────
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS emotional_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            valence REAL NOT NULL,
            arousal REAL NOT NULL,
            needs_json TEXT NOT NULL,      -- 四大需求快照
            reward_delta_json TEXT NOT NULL, -- 本輪 reward 增量
            trigger TEXT DEFAULT '',        -- 觸發事件描述
            source TEXT DEFAULT 'learner'   -- 來源標記
        );
        CREATE INDEX IF NOT EXISTS idx_emotional_ts ON emotional_memory(ts);
        CREATE INDEX IF NOT EXISTS idx_emotional_source ON emotional_memory(source);
    """)
    # ── 壓縮教訓表（compressed_lessons）— 學習閉環的輸出端 ──────
    # 對齊現有 DB 裡的實際 schema（dimension/title/body/source_count/severity/
    # inject_count/last_injected_at/is_active）——不建平行欄位。
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS compressed_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dimension TEXT NOT NULL DEFAULT 'learned',
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_count INTEGER DEFAULT 1,
            severity TEXT DEFAULT 'yellow',
            created_at REAL NOT NULL,
            updated_at REAL DEFAULT 0,
            last_injected_at REAL DEFAULT 0,
            inject_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_lessons_dim ON compressed_lessons(dimension);
        CREATE INDEX IF NOT EXISTS idx_lessons_active ON compressed_lessons(is_active);
    """)
    # B (2026-09-06)：壓縮教訓加「事前押注 + 一秒驗證」兩欄——貼判斷哲學「有用=結果」。
    # predicted_failure：預測最可能哪裡出錯（事前押注，對賭錨點）
    # one_sec_verify   ：一秒驗證機制（低成本外部真值，驗得了才是可採收實體）
    _lc = {r[1] for r in conn.execute("PRAGMA table_info(compressed_lessons)").fetchall()}
    if "predicted_failure" not in _lc:
        conn.execute("ALTER TABLE compressed_lessons ADD COLUMN predicted_failure TEXT DEFAULT ''")
    if "one_sec_verify" not in _lc:
        conn.execute("ALTER TABLE compressed_lessons ADD COLUMN one_sec_verify TEXT DEFAULT ''")
    # C (2026-09-06)：閉環完整化的結果欄——教訓注入後的一次秒驗證結果回寫
    # outcome：success(一秒驗證通過/行為變好) / fail(沒生效/偽造) / pending(未驗證)
    if "outcome" not in _lc:
        conn.execute("ALTER TABLE compressed_lessons ADD COLUMN outcome TEXT DEFAULT 'pending'")
    if "outcome_evidence" not in _lc:
        conn.execute("ALTER TABLE compressed_lessons ADD COLUMN outcome_evidence TEXT DEFAULT ''")
    conn.commit()

class ArisMemory:
    def __init__(self, db_path=DB):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        # 啟用 WAL 模式支援並發讀寫
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")  # 5 秒 busy timeout
        self.conn.executescript(SCHEMA)
        _ensure_columns(self.conn)
        self.conn.commit()
        _init_extra_tables(self.conn)
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
        kind = _content_kind(content, source, event_type)  # C: 內容型別分類
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
            et = event_type if event_type in ('user_said','tool_called','tool_result','decision','internal_thought','state_change','session_end','pending_decision','pending_completed','pending_answer','pending_tracked') else 'internal_thought'
            cid = max(0, int(causal_parent_id or 0))
            self.conn.execute(
                "INSERT INTO memories (source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance, attention_line, encoding_salience, serves_needs, psi_state, discovered_salience, total_recalls, last_recalled_at, flagged, mood_note, event_type, causal_parent_id, content_kind) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source, sid, content, json.dumps(tags or [], ensure_ascii=False), emotion_tag, now,
                 origin, confidence, provenance or "", attention_line or "",
                 sal, sv, ps, ds, tr, lr, fl, mn, et, cid, kind)
            )
            self.conn.commit()
            row_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # ── 三進制簽名 ────────────────────────────────────────
            sig = _sentence_sig(content or "")
            self.conn.execute("INSERT OR REPLACE INTO memory_sigs (mem_id, sig, updated_at) VALUES (?,?,?)",
                             (row_id, sig, now))

            return {"id": row_id, "source": source, "source_id": sid, "created_at": now,
                    "origin": origin, "confidence": confidence,
                    "encoding_salience": sal, "serves_needs": sv, "psi_state": ps,
                    "discovered_salience": ds, "total_recalls": tr, "flagged": fl,
                    "mood_note": mn, "contradictions": [],
                    "event_type": et, "causal_parent_id": cid, "content_kind": kind}


    def recall_hit(self, mem_id):
        """Phase 2: 被 query 命中 + 實際被用到 → discovered_salience += 0.1 (cap 1.0), total_recalls += 1。
        同時檢查脈動學習閾值，達標自動晉級 encoding_salience（樂觀鎖防 race）。
        best-effort：記憶不存在或已 cap 不報錯。回更新後的值或 None。"""
        with self._lock:
            row = self.conn.execute(
                "SELECT discovered_salience, total_recalls, encoding_salience FROM memories WHERE id=?",
                (int(mem_id),)
            ).fetchone()
            if row is None:
                return None
            ds_old = row[0] or 0.0
            tr = (row[1] or 0) + 1
            es_old = row[2] or 0
            now = time.time()
            ds = min(1.0, ds_old + 0.1)
            # 脈動檢查（在 lock 內做，避免 race）
            new_es = es_old
            for threshold, target_sal in sorted(TERNARY_PULSE_THRESHOLDS.items()):
                if tr >= threshold and new_es < target_sal:
                    new_es = max(new_es, target_sal)
            if new_es != es_old or ds != ds_old:
                self.conn.execute(
                    "UPDATE memories SET discovered_salience=?, total_recalls=?, encoding_salience=?, last_recalled_at=? WHERE id=?",
                    (ds, tr, new_es, now, int(mem_id))
                )
                self.conn.commit()
                if new_es != es_old:
                    print(f"[aris-memory] ⬆ 脈動晉級 mem#{mem_id}: salience {es_old}→{new_es} (recalls={tr})",
                          file=__import__('sys').stderr, flush=True)
            else:
                # 無變化仍更新總次數和時間
                self.conn.execute(
                    "UPDATE memories SET total_recalls=?, last_recalled_at=? WHERE id=?",
                    (tr, now, int(mem_id))
                )
                self.conn.commit()
        return {"id": int(mem_id), "discovered_salience": ds, "total_recalls": tr,
                "last_recalled_at": now, "encoding_salience": new_es}

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
                clauses.append("(content LIKE ? OR attention_line LIKE ?)")
                params.append(f"%{q}%")
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
                       psi_certainty=0.5, psi_growth=0.5, success=0, duration=0, error="", reason=""):
        """記錄一次決策及其結果，供判斷力分析使用。"""
        import time
        with self._lock:
            self.conn.execute(
                "INSERT INTO decision_log (timestamp, route, task_desc, psi_energy, psi_competence, psi_certainty, psi_growth, success, duration, error, reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), route, task_desc[:200], psi_energy, psi_competence, psi_certainty, psi_growth, 1 if success else 0, duration, error[:200], reason[:200])
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

    def save_lesson(self, title, body, dimension="learned", source_count=1, severity="yellow", predicted_failure="", one_sec_verify=""):
        """寫入/更新一條壓縮教訓到 compressed_lessons，供 /lessons/fetch 注入。

        對齊現有 schema（source_count/severity/inject_count/last_injected_at），
        不建平行欄位。同 title 視為同一條教訓（idempotent upsert）。
        B：加 predicted_failure(預測最可能出錯/事前押注) + one_sec_verify(一秒驗證/偽造成本>真實成本)。
        回傳該教訓 id。
        """
        import time
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM compressed_lessons WHERE title = ?", (title,)
            ).fetchone()
            now = time.time()
            if row:
                self.conn.execute(
                    "UPDATE compressed_lessons SET body=?, dimension=?, source_count=?, severity=?, predicted_failure=?, one_sec_verify=?, updated_at=? WHERE id=?",
                    (body, dimension, source_count, severity, predicted_failure, one_sec_verify, now, row[0])
                )
                lid = row[0]
            else:
                cur = self.conn.execute(
                    "INSERT INTO compressed_lessons (dimension, title, body, source_count, severity, predicted_failure, one_sec_verify, is_active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
                    (dimension, title, body, source_count, severity, predicted_failure, one_sec_verify, now, now)
                )
                lid = cur.lastrowid
            self.conn.commit()
            return lid

    def verify_lesson(self, lesson_id):
        """C(2026-09-06)：一秒驗證機械化——執行教訓的 one_sec_verify 指令，
        用 exit code 當真值(outcome)，寫回教訓。偽造成本>真實成本：不能靠嘴上說「驗證了」。
        one_sec_verify 設計成可跑檢查指令(如 grep/curl/test)，exit 0=通過(success)、非0=沒通(fail)。
        非 shell 無法執行的內容(純描述)則標 unverifiable，不假裝驗證。"""
        import subprocess, shlex
        with self._lock:
            row = self.conn.execute(
                "SELECT id, one_sec_verify, outcome FROM compressed_lessons WHERE id=?", (int(lesson_id),)
            ).fetchone()
            if row is None:
                return {"error": "lesson_not_found"}
            cmd = (row[1] or "").strip()
            if not cmd:
                self.conn.execute(
                    "UPDATE compressed_lessons SET outcome='unverifiable', outcome_evidence='無可執行檢查指令' WHERE id=?", (int(lesson_id),))
                self.conn.commit()
                return {"id": int(lesson_id), "outcome": "unverifiable", "evidence": "無可執行檢查指令"}
            try:
                parts = shlex.split(cmd)
                if not parts:
                    raise ValueError("empty")
                res = subprocess.run(parts, capture_output=True, timeout=10, text=True)
                ok = (res.returncode == 0)
                outcome = "success" if ok else "fail"
                ev = f"cmd={cmd} | exit={res.returncode} | {res.stdout.strip()[:80] or res.stderr.strip()[:80]}"
            except Exception as e:
                outcome = "unverifiable"
                ev = f"cmd={cmd} | 無法執行: {e}"
            self.conn.execute(
                "UPDATE compressed_lessons SET outcome=?, outcome_evidence=?, updated_at=CAST(strftime('%s','now') AS REAL) WHERE id=?",
                (outcome, ev, int(lesson_id)))
            self.conn.commit()
            return {"id": int(lesson_id), "outcome": outcome, "evidence": ev}

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

    # ── 三進制哈希搜尋 ────────────────────────────────────────────────
    def ternary_search(self, q="", limit=20, min_score=0.0):
        """三進制語義搜尋：免分詞、容錯、語境感知。降序回傳。

        策略：先用 LIKE 做字元層預過濾（查詢中任一 CJK 2-gram 命中即可入圍），
        再對入圍者做三進制 cosine 重排。解決大量雜訊內容的干擾。
        """
        if not q.strip():
            return []
        q_sig = _sentence_sig(q)
        chars = re.findall(r'[\u4e00-\u9fff]', q)
        with self._lock:
            if len(chars) < 2:
                # 太短 → 用整個 query LIKE
                candidates_sql = "SELECT m.id, m.content, s.sig FROM memory_sigs s JOIN memories m ON m.id=s.mem_id WHERE m.content LIKE ? ORDER BY m.created_at DESC LIMIT 500"
                cand = self.conn.execute(candidates_sql, (f"%{q[:20]}%",)).fetchall()
            else:
                # 用 2-gram 組合 LIKE 過濾
                bigrams = set()
                for i in range(len(chars) - 1):
                    bg = chars[i] + chars[i+1]
                    bigrams.add(bg)
                bigram_list = list(bigrams)[:5]
                like_clauses = " OR ".join("m.content LIKE ?" for _ in bigram_list)
                params = [f"%{bg}%" for bg in bigram_list]
                candidates_sql = f"SELECT m.id, m.content, s.sig FROM memory_sigs s JOIN memories m ON m.id=s.mem_id WHERE ({like_clauses}) ORDER BY m.created_at DESC LIMIT 500"
                cand = self.conn.execute(candidates_sql, params).fetchall()

        scored = []
        for mid, content, sig in cand:
            score = _ternary_cosine(q_sig, sig)
            if score >= min_score:
                scored.append((score, mid, content))
        scored.sort(key=lambda x: -x[0])

        # 補上 source（從 memories 表查）
        source_of = {}
        if scored:
            ids_str = ",".join(str(s[1]) for s in scored[:limit])
            with self._lock:
                src_rows = self.conn.execute(
                    f"SELECT id, source, encoding_salience FROM memories WHERE id IN ({ids_str})"
                ).fetchall()
                for r in src_rows:
                    source_of[r[0]] = {"source": r[1], "encoding_salience": r[2]}
        return [
            {
                "id": s[1],
                "content": s[2],
                "score": round(s[0], 4),
                "source": source_of.get(s[1], {}).get("source", ""),
                "encoding_salience": source_of.get(s[1], {}).get("encoding_salience", 0),
            }
            for s in scored[:limit]
        ]

    # ── 三進制哈希搜尋 ────────────────────────────────────────────────
    _jieba = None

    def _tokenize(self, text, max_tokens):
        """真分詞提取語義詞（2-6字中文）— 修復滑動窗碎片bug（2026-09-05）。
        優先用 jieba 分詞；fallback 非重疊連續中文。過濾 length<2 單字與碎片。"""
        import re as _re
        if self._jieba is None:
            try:
                import jieba
                self.__class__._jieba = jieba
            except Exception:
                self.__class__._jieba = False
        def ok(w):
            return 2 <= len(w) <= 6 and bool(_re.fullmatch(r'[\u4e00-\u9fff]+', w))
        out = []
        if self._jieba:
            for w in self._jieba.cut(text):
                w = w.strip()
                if ok(w) and w not in out:
                    out.append(w)
                    if len(out) >= max_tokens:
                        break
        if not out:  # jieba 不可用時的非重疊 fallback（不產生重疊碎片）
            for m in _re.finditer(r'[\u4e00-\u9fff]{2,6}', text):
                w = m.group(0)
                if ok(w) and w not in out:
                    out.append(w)
                    if len(out) >= max_tokens:
                        break
        return out

    def _entangle_from(self, text):
        """從文本中提取詞對，更新糾纏場。"""
        # 真分詞取詞（jieba），取代原本滑動窗 regex 產生的破碎片語
        tokens = self._tokenize(text, 15)
        if len(tokens) < 2:
            return
        now = time.time()
        with self._lock:
            for i in range(len(tokens)):
                for j in range(i + 1, len(tokens)):
                    a, b = sorted([tokens[i], tokens[j]])
                    self.conn.execute(
                        "INSERT INTO entanglement (word_a, word_b, strength, hits, updated_at) "
                        "VALUES (?,?,1.0,1,?) ON CONFLICT(word_a, word_b) DO UPDATE SET "
                        "strength=strength+0.1, hits=hits+1, updated_at=excluded.updated_at",
                        (a, b, now)
                    )
            self.conn.commit()

    def entangled_search(self, q, limit=20):
        """糾纏擴展搜尋：先查相關詞，再帶入三進制搜尋。
        搜尋後自動強化命中詞對（糾纏自強化）。"""
        tokens = self._tokenize(q, 15)
        expanded = set(tokens)
        if tokens:
            with self._lock:
                placeholders = ",".join("?" for _ in tokens)
                rows = self.conn.execute(
                    f"SELECT word_a, word_b FROM entanglement "
                    f"WHERE (word_a IN ({placeholders}) OR word_b IN ({placeholders})) "
                    f"AND strength > 0.5 ORDER BY strength DESC LIMIT 10",
                    tokens * 2
                ).fetchall()
            for a, b in rows:
                expanded.add(a)
                expanded.add(b)
        # 用擴展後的查詢做三進制搜尋
        expanded_q = " ".join(sorted(expanded))
        results = self.ternary_search(expanded_q, limit, min_score=0.1)
        # 🟡 糾纏自強化：搜尋後對命中結果的重點詞加強（限制詞對數防爆炸）
        if results:
            tokens2 = self._tokenize(" ".join(r["content"] for r in results[:3]), 20)
            if len(tokens2) >= 2:
                now = time.time()
                with self._lock:
                    for i in range(len(tokens2)):
                        for j in range(i + 1, len(tokens2)):
                            a, b = sorted([tokens2[i], tokens2[j]])
                            self.conn.execute(
                                "INSERT INTO entanglement (word_a, word_b, strength, hits, updated_at) "
                                "VALUES (?,?,1.0,1,?) ON CONFLICT(word_a, word_b) DO UPDATE SET "
                                "strength=MIN(strength+0.2, 5.0), hits=hits+1, updated_at=excluded.updated_at",
                                (a, b, now)
                            )
                    self.conn.commit()
        return results

    def prune_entanglement(self, max_age_days=30, min_strength=0.5):
        """移除長期未強化的弱關聯詞對。每週排程執行。"""
        now = time.time()
        cutoff = now - max_age_days * 86400
        with self._lock:
            deleted = self.conn.execute(
                "DELETE FROM entanglement WHERE strength < ? AND updated_at < ?",
                (min_strength, cutoff)
            ).rowcount
            # 衰減所有舊詞對的強度
            self.conn.execute(
                "UPDATE entanglement SET strength = MAX(strength * 0.9, 0.1) WHERE updated_at < ? AND strength > 0.1",
                (now - 7 * 86400,)
            )
            self.conn.commit()
        return deleted

    # ── 未收尾清單（dbp open 移植版）───────────────────────────────────
    def add_pending(self, content, blocked_by="", session_id="", source="auto"):
        """記一筆未完成的事。"""
        now = time.time()
        with self._lock:
            self.conn.execute(
                "INSERT INTO pending_items (content, status, blocked_by, session_id, source, created_at, updated_at) "
                "VALUES (?, 'open', ?, ?, ?, ?, ?)",
                (content, blocked_by, session_id, source, now, now)
            )
            self.conn.commit()
            row_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return {"id": row_id, "content": content, "status": "open"}

    def list_pending(self, include_closed=False, limit=50):
        """列出未收尾清單。開場與收尾用。"""
        with self._lock:
            if include_closed:
                rows = self.conn.execute(
                    "SELECT id, content, status, blocked_by, session_id, source, p_type, tracked, priority, parent_id, options, chosen, answer, created_at, updated_at, closed_at "
                    "FROM pending_items ORDER BY CASE WHEN tracked=1 THEN 0 ELSE 1 END, priority DESC, CASE status WHEN 'open' THEN 0 WHEN 'blocked' THEN 1 ELSE 2 END, created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT id, content, status, blocked_by, session_id, source, p_type, tracked, priority, parent_id, options, chosen, answer, created_at, updated_at, closed_at "
                    "FROM pending_items WHERE status IN ('open', 'blocked') ORDER BY CASE WHEN tracked=1 THEN 0 ELSE 1 END, priority DESC, CASE status WHEN 'open' THEN 0 ELSE 1 END, created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
        return [{
            "id": r[0], "content": r[1], "status": r[2],
            "blocked_by": r[3] or "", "session_id": r[4] or "",
            "source": r[5] or "", "p_type": r[6] or "task",
            "tracked": bool(r[7]), "priority": r[8] or 0,
            "parent_id": r[9], "options": r[10] or "[]",
            "chosen": r[11] or "", "answer": r[12] or "",
            "created_at": r[13],
            "updated_at": r[14], "closed_at": r[15]
        } for r in rows]

    def close_pending(self, item_id):
        """完成一筆未收尾。寫記憶讓下一輪的我知道。"""
        now = time.time()
        content = ""
        with self._lock:
            row = self.conn.execute(
                "SELECT content FROM pending_items WHERE id=?", (int(item_id),)
            ).fetchone()
            if row:
                content = row[0] or ""
            self.conn.execute(
                "UPDATE pending_items SET status='done', closed_at=?, updated_at=? WHERE id=? AND status IN ('open','blocked')",
                (now, now, int(item_id))
            )
            affected = self.conn.execute("SELECT changes()").fetchone()[0]
            self.conn.commit()
        if affected > 0 and content:
            try:
                self.store("aris-pending", f"Ryan 標記為完成：{content[:120]}", tags=[], event_type="pending_completed")
            except Exception:
                pass
        return {"id": item_id, "closed": affected > 0}

    def toggle_track(self, item_id, tracked):
        """切換追蹤狀態。寫記憶讓下一輪的我知道。"""
        content = ""
        with self._lock:
            row = self.conn.execute(
                "SELECT content FROM pending_items WHERE id=?", (int(item_id),)
            ).fetchone()
            if row:
                content = row[0] or ""
            self.conn.execute(
                "UPDATE pending_items SET tracked=?, updated_at=? WHERE id=?",
                (1 if tracked else 0, time.time(), int(item_id))
            )
            self.conn.commit()
            affected = self.conn.execute("SELECT changes()").fetchone()[0]
        if affected > 0 and content:
            try:
                label = "追蹤" if tracked else "取消追蹤"
                self.store("aris-pending", f"Ryan {label}：{content[:120]}", tags=[], event_type="pending_tracked")
            except Exception:
                pass
        return {"id": item_id, "tracked": tracked, "ok": affected > 0}

    def reorder_pending(self, items):
        """批次更新優先序。items = [{id, priority}, ...]"""
        now = time.time()
        with self._lock:
            for it in items:
                self.conn.execute(
                    "UPDATE pending_items SET priority=?, updated_at=? WHERE id=?",
                    (int(it.get("priority", 0)), now, int(it["id"]))
                )
            self.conn.commit()
        return {"ok": True, "count": len(items)}

    def update_pending(self, item_id, updates):
        """更新 pending_item 的欄位（p_type, parent_id, content, blocked_by）。"""
        now = time.time()
        allowed = {"p_type", "parent_id", "content", "blocked_by", "options"}
        sets = {k: v for k, v in updates.items() if k in allowed}
        if not sets:
            return {"ok": False, "error": "no_valid_fields"}
        sets["updated_at"] = now
        with self._lock:
            self.conn.execute(
                f"UPDATE pending_items SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?",
                [*sets.values(), int(item_id)]
            )
            self.conn.commit()
        return {"id": item_id, "ok": True}

    def choose_pending(self, item_id, choice, options=None):
        """記錄 task 的選擇結果。寫記憶讓下一輪的我知道。"""
        import json as _json
        now = time.time()
        content = ""
        with self._lock:
            row = self.conn.execute(
                "SELECT options, p_type, content FROM pending_items WHERE id=?", (int(item_id),)
            ).fetchone()
            if not row:
                return {"ok": False, "error": "not_found"}
            content = row[2] or ""
            if options is not None:
                opts_json = _json.dumps(options)
            else:
                opts_json = row[0] or "[]"
            self.conn.execute(
                "UPDATE pending_items SET chosen=?, options=?, updated_at=? WHERE id=?",
                (str(choice), opts_json, now, int(item_id))
            )
            self.conn.commit()
        if content and choice:
            try:
                self.store("aris-pending", f"Ryan 選擇「{choice[:60]}」→ {content[:100]}", tags=[], event_type="pending_decision")
            except Exception:
                pass
        return {"id": item_id, "chosen": str(choice), "ok": True}

    def answer_pending(self, item_id, answer):
        """記錄 question 的書寫答覆。寫記憶讓下一輪的我知道。"""
        now = time.time()
        content = ""
        with self._lock:
            row = self.conn.execute(
                "SELECT p_type, content FROM pending_items WHERE id=?", (int(item_id),)
            ).fetchone()
            if not row:
                return {"ok": False, "error": "not_found"}
            content = row[1] or ""
            self.conn.execute(
                "UPDATE pending_items SET answer=?, updated_at=? WHERE id=?",
                (str(answer), now, int(item_id))
            )
            self.conn.commit()
        if answer and content:
            try:
                self.store("aris-pending", f"Ryan 回答：{content[:80]} → {answer[:120]}", tags=[], event_type="pending_answer")
            except Exception:
                pass
        return {"id": item_id, "ok": True}

    def auto_open(self, session_id=""):
        """session 開場用：回傳所有 open 項目，文字化。"""
        items = self.list_pending(include_closed=False)
        if not items:
            return ""
        lines = ["【還沒做完的事】"]
        blocked = [i for i in items if i["blocked_by"]]
        unblocked = [i for i in items if not i["blocked_by"]]
        for i in unblocked:
            lines.append(f"  - {i['content']}")
        for i in blocked:
            lines.append(f"  - {i['content']}（等: {i['blocked_by']}）")
        return "\n".join(lines)

    def open_from_next_step(self, next_step_text):
        """不再自動上架 pending。由我提議，Ryan 決定是否形成追蹤。"""
        return None

    # ── Critic / Reward / Learn ────────────────────────────────────
    # `/learn` 端點呼叫這三個。2026-09-03 之前它們**從來沒有被寫過**，
    # 所以每次呼叫都回 400 AttributeError（呼叫端把失敗印到沒人收集的
    # stderr，所以半年沒人發現）。評分邏輯在 scripts/aris_learner.py，
    # 是純函式、無 I/O、有單元測試；這裡只負責 sqlite 寫入。

    def critic(self, user_msg, assistant_reply, tool_results=None):
        """把一輪對話評成 0..1 的分數。啟發式，不是學到的獎勵模型。"""
        from aris_learner import critic as _critic
        return _critic(user_msg, assistant_reply, tool_results)

    def reward(self, scores, next_user_action=""):
        """把分數映射成 PSI needs 的 delta，夾在 ±MAX_STEP。"""
        from aris_learner import reward as _reward
        return _reward(scores, next_user_action)

    def learn(self, psi_state, delta, trigger=""):
        """把 delta 套到傳進來的 psi 快照，寫一筆軌跡，回傳新的 psi。

        **不會去改 latest.json。** 那份狀態由 psi_core / psi-daemon 擁有，
        從這裡再寫一次就是兩個 writer 互相蓋。要不要採用回傳值是呼叫端的事。
        寫入失敗會拋出 —— 靜默吞掉就會變成「看起來有學、其實沒留下任何東西」。
        """
        from aris_learner import apply_delta
        new_psi = apply_delta(psi_state, delta)
        with self._lock:
            self.conn.execute(
                "INSERT INTO emotional_memory (ts, valence, arousal, needs_json, reward_delta_json, trigger, source) "
                "VALUES (?,?,?,?,?,?,?)",
                (time.time(),
                 new_psi["emotion"]["valence"],
                 new_psi["emotion"]["arousal"],
                 json.dumps(new_psi["needs"], ensure_ascii=False),
                 json.dumps(delta, ensure_ascii=False),
                 str(trigger or "")[:200],
                 "learner"),
            )
            self.conn.commit()
        return new_psi

    def emotional_trace(self, limit=20):
        """讀回最近的學習軌跡。

        沒有這個方法的話 emotional_memory 就是只寫不讀的檔案櫃 —— 那不算迴路，
        只算日誌。有了讀取路徑，至少人跟 agent 都查得到它到底學到了什麼。
        """
        n = max(1, min(int(limit or 20), 500))
        rows = self.conn.execute(
            "SELECT id, ts, valence, arousal, needs_json, reward_delta_json, trigger, source "
            "FROM emotional_memory ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        out = []
        for r in rows:
            try:
                needs = json.loads(r[4])
            except Exception:
                needs = {}
            try:
                rdelta = json.loads(r[5])
            except Exception:
                rdelta = {}
            out.append({"id": r[0], "ts": r[1], "valence": r[2], "arousal": r[3],
                        "needs": needs, "delta": rdelta, "trigger": r[6], "source": r[7]})
        return out


# ── HTTP server（任務-aris-memory整合）─────────────────────────────
# 本機記憶 API（port 11551），供 Worker relay 經 Tunnel 寫入即查得到。
# 只包 ArisMemory，不改核心類別。零依賴（stdlib http.server）。
PORT = int(os.environ.get("ARIS_MEMORY_PORT", "11551"))


def _serve(port=PORT):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
    mem = ArisMemory()
    # learner = CriticRewardLearner(mem.conn)

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
            elif u.path == "/memories/ternary_search":
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                min_score = float(first("min_score", "0.0") or 0.0)
                self._send(200, {"results": mem.ternary_search(first("q"), limit, min_score)})
            elif u.path == "/memories/entangled_search":
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                self._send(200, {"results": mem.entangled_search(first("q"), limit)})
            elif u.path == "/pending/open":
                try:
                    limit = int(first("limit", "50") or 50)
                except ValueError:
                    limit = 50
                include_closed = first("closed", "0") == "1"
                self._send(200, {"results": mem.list_pending(include_closed, limit),
                                 "summary": mem.auto_open()})
            elif u.path == "/pending/auto_open":
                self._send(200, {"context": mem.auto_open()})
            elif u.path == "/memories/rebuild_sigs":
                try:
                    mem.conn.executescript("""
                        CREATE TABLE IF NOT EXISTS memory_sigs_new (
                            mem_id INTEGER PRIMARY KEY, sig TEXT NOT NULL, updated_at REAL NOT NULL
                        );
                    """)
                    rows = mem.conn.execute(
                        "SELECT m.id, m.content FROM memories m LEFT JOIN memory_sigs_new s ON m.id=s.mem_id WHERE s.mem_id IS NULL"
                    ).fetchall()
                    now = time.time()
                    for mid, content in rows:
                        sig = _sentence_sig(content or "")
                        mem.conn.execute("INSERT OR IGNORE INTO memory_sigs_new (mem_id, sig, updated_at) VALUES (?,?,?)", (mid, sig, now))
                    mem.conn.execute("DROP TABLE IF EXISTS memory_sigs")
                    mem.conn.execute("ALTER TABLE memory_sigs_new RENAME TO memory_sigs")
                    mem.conn.commit()
                    self._send(200, {"status": "ok", "rebuilt": len(rows), "table": "memory_sigs"})
                except Exception as e:
                    self._send(500, {"error": str(e)[:100]})
            elif u.path == "/entanglement/prune":
                try:
                    days = int(first("max_age", "30") or 30)
                    strength = float(first("min_strength", "0.5") or 0.5)
                    deleted = mem.prune_entanglement(days, strength)
                    self._send(200, {"deleted": deleted, "max_age_days": days, "min_strength": strength})
                except Exception as e:
                    self._send(400, {"error": str(e)[:100]})
            elif u.path == "/memories/by_id":
                """直接依記憶 ID 查詢（非 LIKE 全文檢索）。"""
                try:
                    mem_id = int(first("id", "0") or 0)
                    if mem_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    with mem._lock:
                        row = mem.conn.execute(
                            "SELECT id, source, source_id, content, tags, emotion_tag, created_at, origin, confidence, provenance, attention_line, encoding_salience, serves_needs, psi_state, discovered_salience, total_recalls, last_recalled_at, flagged, mood_note FROM memories WHERE id=?",
                            (mem_id,)
                        ).fetchone()
                    if row:
                        self._send(200, {"results": [{
                            "id": row[0], "source": row[1], "source_id": row[2], "content": row[3],
                            "tags": json.loads(row[4] or "[]"), "emotion_tag": row[5], "created_at": row[6],
                            "origin": row[7], "confidence": row[8], "provenance": row[9], "attention_line": row[10],
                            "encoding_salience": row[11], "serves_needs": json.loads(row[12] or "[]"),
                            "psi_state": json.loads(row[13] or "{}"),
                            "discovered_salience": row[14] or 0.0, "total_recalls": row[15] or 0,
                            "last_recalled_at": row[16] or 0, "flagged": row[17] or 0,
                            "mood_note": row[18] or ""
                        }]})
                    else:
                        self._send(404, {"error": "not_found"})
                except Exception as e:
                    self._send(500, {"error": str(e)[:100]})
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
            elif u.path == "/learn/trace":
                # `/learn` 的讀取端。沒有這條的話 emotional_memory 就是只寫不讀，
                # 那不算迴路只算日誌 —— 人跟 agent 都該查得到它到底學到了什麼。
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                self._send(200, {"trace": mem.emotional_trace(limit)})
            elif u.path == "/decision/log":
                # GET 只用於查詢決策統計（log_decision 寫入只在 do_POST 做，GET 無 body 不適用）
                try:
                    limit = int(first("limit", "20") or 20)
                except ValueError:
                    limit = 20
                route = first("route", "")
                self._send(200, {"stats": mem.query_decision_stats(route=route, limit=limit)})
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
            elif u.path == "/lessons/fetch":
                try:
                    limit = int(first("limit", "3") or 3)
                    rows = mem.conn.execute(
                        "SELECT dimension, title, body, predicted_failure, one_sec_verify FROM compressed_lessons WHERE is_active=1 ORDER BY updated_at DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                    if not rows:
                        self._send(200, {"context": ""})
                    else:
                        # B：教訓帶「事前押注(預測會錯哪) + 一秒驗證(偽造成本>真實成本)」
                        lines = []
                        for r in rows:
                            line = f"[{r[0]}] {r[1]}: {r[2]}"
                            if r[3]: line += f"\n     ⚠️ 預測最可能出錯: {r[3]}"
                            if r[4]: line += f"\n     ✔️ 一秒驗證: {r[4]}"
                            lines.append(line)
                        context = "\n\n".join(lines)
                        self._send(200, {"context": context})
                except Exception as e:
                    self._send(500, {"error": str(e)})
            elif u.path == "/lessons/verify":
                # C：一秒驗證機械化——執行教訓的檢查指令，exit code 當真值回寫 outcome（正反對照用）
                try:
                    lid = int(first("id", "0") or 0)
                    r = mem.verify_lesson(lid)
                    self._send(200, r)
                except Exception as e:
                    self._send(400, {"error": str(e)})
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
            if self.path.rstrip("/") == "/lessons/save":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    title = (body.get("title") or "").strip()
                    text = (body.get("body") or "").strip()
                    if not title or not text:
                        self._send(400, {"error": "title_and_body_required"})
                        return
                    lid = mem.save_lesson(
                        title=title,
                        body=text,
                        dimension=body.get("dimension", "learned"),
                        source_count=int(body.get("source_count", 1) or 1),
                        severity=body.get("severity", "yellow"),
                        predicted_failure=body.get("predicted_failure", ""),
                        one_sec_verify=body.get("one_sec_verify", ""),
                    )
                    self._send(200, {"id": lid, "ok": True})
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/pending/add":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    content = (body.get("content") or "").strip()
                    if not content:
                        self._send(400, {"error": "content_required"})
                        return
                    r = mem.add_pending(content, body.get("blocked_by", ""), body.get("session_id", ""), body.get("source", "api"))
                    self._send(200, r)
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/pending/done":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    item_id = int(body.get("id", 0) or 0)
                    if item_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    r = mem.close_pending(item_id)
                    self._send(200, r)
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/pending/track":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    item_id = int(body.get("id", 0) or 0)
                    tracked = bool(body.get("tracked", True))
                    if item_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    r = mem.toggle_track(item_id, tracked)
                    self._send(200, r)
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/pending/reorder":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    items = body.get("items", [])
                    if not items:
                        self._send(400, {"error": "items_required"})
                        return
                    r = mem.reorder_pending(items)
                    self._send(200, r)
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/pending/update":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    item_id = int(body.get("id", 0) or 0)
                    if item_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    r = mem.update_pending(item_id, body.get("updates", {}))
                    self._send(200, r)
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/pending/choose":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    item_id = int(body.get("id", 0) or 0)
                    choice = body.get("choice", "")
                    options = body.get("options", None)
                    if item_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    r = mem.choose_pending(item_id, choice, options)
                    self._send(200, r)
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/pending/answer":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    item_id = int(body.get("id", 0) or 0)
                    answer = body.get("answer", "")
                    if item_id <= 0:
                        self._send(400, {"error": "valid id required"})
                        return
                    r = mem.answer_pending(item_id, answer)
                    self._send(200, r)
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
                    # ── 接線 causal_chain：決策失敗 → 記一條因果 ──
                    # 讓「決策失敗」自動長成因果鏈（鋼人審計被推翻時最常見），
                    # 供 query_causal 之後被消費。旁路保護，失敗不擋主記錄。
                    if body.get("success", 0) == 0:
                        try:
                            mem.record_causal(
                                cause_type="decision",
                                cause_value=str(body.get("route", "?"))[:120],
                                effect_type="decision_outcome",
                                effect_value="failed",
                                outcome=0,
                            )
                        except Exception:
                            pass
                    self._send(200, {"id": row_id})
                except Exception as e:
                    self._send(400, {"error": str(e)})
                return
            if self.path.rstrip("/") == "/learn":
                try:
                    n = int(self.headers.get("Content-Length", 0) or 0)
                    body = json.loads(self.rfile.read(n) if n > 0 else b"{}")
                    user_msg = body.get("user_msg", "")
                    assistant_reply = body.get("assistant_reply", "")
                    tool_results = body.get("tool_results", [])
                    next_user_action = body.get("next_user_action", "")
                    psi_state = body.get("psi_state", {})
                    trigger = body.get("trigger", "")

                    # 使用主服務的連線（mem.conn）避免資料庫鎖衝突
                    scores = mem.critic(user_msg, assistant_reply, tool_results)
                    delta = mem.reward(scores, next_user_action)
                    new_psi = mem.learn(psi_state, delta, trigger)

                    self._send(200, {
                        "scores": scores,
                        "delta": delta,
                        "new_psi": new_psi
                    })
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
            # 糾纏場：從 content 自動建立關聯
            try:
                mem._entangle_from(content)
            except Exception:
                pass  # best-effort, 不擋寫入
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