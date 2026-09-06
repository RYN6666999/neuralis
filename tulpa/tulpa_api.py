#!/usr/bin/env python3
"""tulpa_api — HTTP API 處理器（最薄層）。

僅含 aiohttp handlers + route setup。
所有業務邏輯在 tulpa_engine / tulpa_evolution / tulpa_domain / tulpa_search 中。
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from aiohttp import web

from tulpa.tulpa_db import _db, _init_db, load_tulpa_state, save_tulpa_state, save_session_delta
from tulpa.tulpa_engine import (
    TULPAS, _turn_counter, _session_id, _session_deltas, _session_start,
    compete, _apply_persisted, _init_keyword_stats, _apply_domain_keyword_additions,
    _log_migration, _track_keyword_miss, _log_path,
)
from tulpa.tulpa_domain import ALL_DOMAINS
from tulpa.tulpa_evolution import (
    _active_alerts, _suggest_merge, _execute_merge, _execute_split,
    _aris_memory_failures, _time_axis_compete,
    _settle_prediction, _detect_isomorphism,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "tulpa_memory.db"


# ═══════════════════════════════════════════════════════════
# Handlers
# ═══════════════════════════════════════════════════════════

async def handle_cognitive(request):
    try:
        body = await request.json() if request.method == "POST" else {}
        text = body.get("text", "") or request.query.get("text", "")
        if not text:
            return web.json_response({"error": "text required"}, status=400)
        # 接受選用 PSI 狀態（Aris → 18428 方向）
        psi_state = body.get("psi_state")
        cognitive_context = body.get("cognitive_context")
        result = compete(text, psi_state=psi_state, cognitive_context=cognitive_context)
        # ── A(2026-09-06, 三層分離後補最缺的一環)：把長期記憶長進對話 ──
        # 原本記憶「只寫入不讀取」，Ryan 教過的事存在 DB 但對話時從不想起 → 用起來沒感覺。
        # 現在：回應前查 aris-memory(:11551) 相關記憶，把「記得」帶進 context。
        # 抽詞法：整句查常命中不了（記憶是長對話），改成切短 chunk 當查詢詞。
        try:
            import re as _re
            from urllib.parse import urlencode
            from urllib.request import urlopen
            # 切短 chunk（標點+常見語氣詞切開，取 2-4 字候選）
            _chunks = [p for p in _re.split(
                r'[，。！？、,.!? ]|(?:怎麼|什麼|的|了|嗎|呢|我|你|他|她|想|要|跟|在|對|最近|一下|更好|做|談|幫|看)',
                text) if 2 <= len(p) <= 4][:8]
            _mem_ref = []
            for _cw in _chunks:
                _murl = "http://127.0.0.1:11551/memories/query?" + urlencode({"q": _cw, "limit": 1})
                try:
                    with urlopen(_murl, timeout=2.5) as _resp:
                        _md = json.loads(_resp.read().decode("utf-8"))
                    _hits = _md.get("results") or []
                    if _hits:
                        _mem_ref.append("【記得你之前說】" + str(_hits[0].get("content", ""))[:120].replace("\n", " "))
                        break  # 取第一個命中的就夠，別塞太多
                except Exception:
                    continue
            if _mem_ref:
                result["context"] = (result.get("context") or "") + f"\n\n📌 記憶參考(上次你教過/聊過的):\n" + "\n".join(_mem_ref)
        except Exception:
            pass  # 記憶查詢失敗不擋主回應（後端降級）
        # ── 教訓觸發（A2，2026-09-06）：掃 data/lessons/*.json，trigger 命中 → 帶入 context ──
        # 可拔插教訓（同 gb 基因/skill 骨架）。能不能被用上 = 觸發命中；用上能不能更好 = 一秒驗證(outcome)。
        try:
            from tulpa.tulpa_lesson import load_all as _la, save as _save
            lesson_ref = []
            for _ls in _la():
                if _ls.get("active", True) is not True:
                    continue
                if any(_t in text for _t in (_ls.get("trigger") or [])):
                    _ls["inject_count"] = _ls.get("inject_count", 0) + 1
                    _save(_ls)  # 寫回 inject_count：可觀測「這條教訓被用過幾次」
                    lesson_ref.append(f"【教訓】{_ls.get('body','')}"
                                      f"（預測會錯：{_ls.get('predicted_failure','')}；一秒驗證：{_ls.get('one_sec_verify','')}）")
            if lesson_ref:
                result["context"] = (result.get("context") or "") + "\n\n📋 教訓參考(可拔插,trigger命中):\n" + "\n".join(lesson_ref[:2])
        except Exception:
            pass  # 教訓查詢失敗不擋主回應（後端降級）
        # ── 接活「路徑學習 + 時間軸預測」觀測管線（旁路，不影響 winner 決策）──
        # 原本 _log_path / _time_axis_compete 從未被主循環調用 → path_log 永遠 0
        # → future tulpa 無預測輸入 → prediction_events 永遠空。這裡補上調度：
        # 1) 記錄本輪實際走的領域路徑（prediction 的輸入源）
        # 2) 觸發時間軸競爭 → 產生 time_axis_log + prediction_events
        # 純寫入，包 try/except 保護，壞了不擋主回應。
        try:
            dp = result.get("domain_path") or []
            actual_path = "/".join(dp) if dp else ""
            if dp:
                _log_path(actual_path)
                # 用本輪實際走的 path 結算「過往預測」→ prediction_events 出結果（settled）
                _settle_prediction(actual_path)
            # 觸發時間軸競爭 → 產生 time_axis_log + prediction_events（未來預測）
            _time_axis_compete(text)
            # 結構同構：從 path_log 找相似路徑 → structure_isomorphism（自帶 5 輪節流）
            _detect_isomorphism()
        except Exception:
            pass
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request):
    db = _db()
    sleeping = db.execute("SELECT name FROM tulpa_state WHERE sleep_until IS NOT NULL").fetchall()
    inactive_kw = db.execute("SELECT COUNT(*) FROM keyword_stats WHERE active=0").fetchone()[0]
    conflict = db.execute("SELECT COUNT(*) FROM observer_insights WHERE insight_type='conflict' AND addressed=0").fetchone()[0]
    motw = db.execute("SELECT COUNT(*) FROM observer_insights WHERE insight_type='motw_mismatch' AND addressed=0").fetchone()[0]
    contradict = db.execute("SELECT COUNT(*) FROM observer_insights WHERE insight_type='contradiction' AND addressed=0").fetchone()[0]
    db.close()
    warnings = []
    if sleeping: warnings.append(f"{len(sleeping)} 休眠")
    if inactive_kw: warnings.append(f"{inactive_kw} kw 不活躍")
    if conflict: warnings.append(f"{conflict} 衝突")
    if motw: warnings.append(f"{motw} 預測不一致")
    if contradict: warnings.append(f"{contradict} 矛盾")
    if _aris_memory_failures > 0:
        warnings.append(f":11551 記憶寫入失敗 {_aris_memory_failures} 次")
    # 檢查 :11551 是否 alive
    aris_memory_alive = False
    try:
        import urllib.request as _req
        resp = _req.urlopen("http://127.0.0.1:11551/health", timeout=2)
        aris_memory_alive = resp.status == 200
    except Exception:
        pass
    active = _active_alerts()
    has_crit = any(a["level"] == "crit" for a in active)
    status = "crit" if has_crit else ("warn" if active or _aris_memory_failures > 0 else ("ok" if not sleeping else "degraded"))
    if not aris_memory_alive:
        warnings.append(":11551 離線（18428→Aris 回饋環中斷）")
    return web.json_response({
        "status": status, "port": 18428, "tulpas": len(TULPAS),
        "session_id": _session_id,
        "warnings": warnings, "active_alerts": active,
        "aris_memory": {"alive": aris_memory_alive, "failures": _aris_memory_failures},
    })


async def handle_state(request):
    return web.json_response({
        "tulpas": [{"name": t.name, "weight": round(t.base_weight, 4),
                     "urgency": t.base_urgency, "importance": t.base_importance,
                     "sleeping": t._sleeping, "hits_20": sum(t.recent_hits[-20:])}
                    for t in TULPAS],
        "session_id": _session_id,
    })


async def handle_audit(request):
    db = _db()
    sleeping = [r["name"] for r in db.execute("SELECT name FROM tulpa_state WHERE sleep_until IS NOT NULL").fetchall()]
    iso_pending = [dict(r) for r in db.execute("SELECT path_a, path_b, ROUND(similarity,2) sim, hits FROM structure_isomorphism WHERE merged=0 AND hits>=3 ORDER BY hits DESC").fetchall()]
    conflicts = [dict(r) for r in db.execute("SELECT id, turn, description, confidence FROM observer_insights WHERE insight_type='conflict' AND addressed=0 ORDER BY turn DESC LIMIT 10").fetchall()]
    contradictions = [dict(r) for r in db.execute("SELECT id, turn, description, confidence FROM observer_insights WHERE insight_type='contradiction' AND addressed=0 ORDER BY turn DESC LIMIT 10").fetchall()]
    inactive = [dict(r) for r in db.execute("SELECT keyword, tulpa_name, lifetime_misses FROM keyword_stats WHERE active=0 ORDER BY lifetime_misses DESC LIMIT 20").fetchall()]
    db.close()
    return web.json_response({"sleeping": sleeping, "inactive_keywords": inactive,
                               "pending_merges": iso_pending, "conflicts": conflicts,
                               "contradictions": contradictions})


async def handle_migration(request):
    db = _db()
    rows = db.execute("SELECT * FROM migration_log ORDER BY id DESC LIMIT 50").fetchall()
    db.close()
    return web.json_response({"migrations": [dict(r) for r in rows]})


async def handle_observer(request):
    db = _db()
    rows = db.execute("SELECT * FROM observer_insights ORDER BY id DESC LIMIT 20").fetchall()
    db.close()
    return web.json_response({"insights": [dict(r) for r in rows]})


async def handle_timeaxis(request):
    db = _db()
    rows = db.execute("SELECT * FROM time_axis_log ORDER BY turn DESC LIMIT 20").fetchall()
    db.close()
    return web.json_response({"time_axis": [dict(r) for r in rows]})


async def handle_convergence(request):
    db = _db()
    result = {}
    for t in TULPAS:
        rows = db.execute("SELECT delta FROM migration_log WHERE tulpa_name=? ORDER BY id DESC LIMIT 20", (t.name,)).fetchall()
        if len(rows) >= 5:
            deltas = [r["delta"] for r in rows]
            avg = sum(deltas) / len(deltas)
            variance = sum((d - avg) ** 2 for d in deltas) / len(deltas)
            result[t.name] = {"variance": round(variance, 4), "avg_delta": round(avg, 4),
                              "status": "發散" if variance > 0.01 else "收斂" if variance < 0.005 else "震盪"}
    db.close()
    return web.json_response(result)


async def handle_experiment(request):
    if request.method == "GET":
        return web.json_response(_suggest_merge())
    body = await request.json()
    decision = body.get("decision")
    if decision == "merge":
        parent = _execute_merge(body["path_a"], body["path_b"])
        return web.json_response({"status": "merged", "parent": parent})
    if decision == "split":
        ok = _execute_split(body["name"], body["new_name"], body.get("keywords", []))
        return web.json_response({"status": "split" if ok else "failed"})
    return web.json_response({"error": "unknown decision"}, status=400)


async def handle_predictions(request):
    db = _db()
    rows = db.execute("SELECT * FROM prediction_events ORDER BY id DESC LIMIT 20").fetchall()
    db.close()
    return web.json_response({"predictions": [dict(r) for r in rows]})


async def handle_label(request):
    """POST /label — 餵真值（避免/再犯）進 mistake_outcome，打通「你回饋 → 判斷力權重」最短閉環。

    Body: {mistake_id: int, outcome: "avoided"|"recurred"|"unverifiable", evidence?: str}
    消費端已活：apply_gene_adjustments() 每輪 compete 吃 avoided(獎)/recurred(懲) → tulpa 權重變厚。
    不 self-判斷對錯——outcome 由呼叫端(真人/外部真值)給，這支只負責寫入，防止污染真值源。
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)
    mistake_id = body.get("mistake_id")
    outcome = body.get("outcome")
    evidence = body.get("evidence", "")
    # T3: label 來源。預設 human（真人/外部 → 進權重）；AI 自標可傳 source='self'（不進權重）。
    source = body.get("source", "human")
    if source not in ("human", "self", "tool"):
        return web.json_response({"error": "source 只能是 human/self/tool"}, status=400)
    if not isinstance(mistake_id, int) or outcome not in ("avoided", "recurred", "unverifiable"):
        return web.json_response({"error": "mistake_id(int) + outcome(avoided/recurred/unverifiable) required"}, status=400)
    db = _db()
    m = db.execute("SELECT id, error_type, tulpa_name FROM mistake_catalog WHERE id=?", (mistake_id,)).fetchone()
    if not m:
        db.close()
        return web.json_response({"error": f"mistake {mistake_id} 不存在"}, status=404)
    db.execute(
        "INSERT INTO mistake_outcome (mistake_id, outcome, evidence, source, created_at) VALUES (?,?,?,?,?)",
        (mistake_id, outcome, evidence, source, datetime.utcnow().isoformat()))
    db.commit()
    db.close()
    return web.json_response({
        "status": "ok",
        "mistake_id": mistake_id,
        "tulpa_name": m["tulpa_name"],
        "outcome": outcome,
        "note": "已寫進 mistake_outcome；下輪 apply_gene_adjustments 會依此調整 tulpa 權重",
    })


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/state", handle_state)
    app.router.add_get("/audit", handle_audit)
    app.router.add_get("/migration", handle_migration)
    app.router.add_get("/observer", handle_observer)
    app.router.add_get("/timeaxis", handle_timeaxis)
    app.router.add_get("/convergence", handle_convergence)
    app.router.add_get("/predictions", handle_predictions)
    app.router.add_get("/experiment", handle_experiment)
    app.router.add_post("/experiment", handle_experiment)
    app.router.add_get("/cognitive", handle_cognitive)
    app.router.add_post("/cognitive", handle_cognitive)
    app.router.add_post("/label", handle_label)
    return app


def main():
    _init_db()
    _init_keyword_stats()
    _apply_domain_keyword_additions()
    persisted = load_tulpa_state()
    for t in TULPAS:
        _apply_persisted(t, persisted)

    import tulpa.tulpa_engine as eng
    eng._session_id = datetime.utcnow().strftime("s%Y%m%d_%H%M%S")
    eng._session_start = time.time()

    db = _db()
    db.execute("UPDATE prediction_events SET state='expired' WHERE state='pending' AND session_id != ?", (eng._session_id,))
    db.commit(); db.close()

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18428
    app = build_app()
    print(f"[tulpa] 🎤 on :{port} | session: {eng._session_id}")
    try:
        web.run_app(app, port=port)
    finally:
        save_tulpa_state(TULPAS)
        save_session_delta()


if __name__ == "__main__":
    main()