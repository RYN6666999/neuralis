#!/usr/bin/env python3
"""tulpa_evolution — 演化層（prune, isomorphism, observer, time-axis, experiment）。

切割自 aris_tulpa_api.py（2597 行巨獸）。
依賴：tulpa_db, tulpa_engine
"""

import json
import math
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from tulpa.tulpa_db import _db, _turn_counter, save_session_delta
from tulpa.tulpa_engine import (
    Tulpa, TULPAS,
    _session_id, _session_deltas,
    _track_domain_candidates, _track_domain_hit,
    _log_migration, _track_keyword_miss, _log_path,
    _path_similarity,
    _make_signature,
)
from tulpa.tulpa_domain import ALL_DOMAINS, _find_node, route_domain
from tulpa.tulpa_search import passive_search

__all__ = [
    "prune_cycle", "_detect_isomorphism",
    "_learned_confidence", "_observe_third_position",
    "_past_tulpa_score", "_present_tulpa_score", "_future_tulpa_score",
    "_active_alerts", "_psi_state", "_global_prediction_accuracy",
    "_settle_prediction", "_time_axis_compete",
    "_suggest_merge", "_execute_merge", "_execute_split",
    "_run_experiment_cycle",
    "_aris_memory_failures",
]

# 18428 → Aris 記憶通道狀態
_aris_memory_failures: int = 0
# PSI 快取
_psi_cache: dict = {}
_psi_cache_time: float = 0.0
_psi_cache_ttl: float = 5.0  # 秒

# ═══════════════════════════════════════════════════════════════
# 路徑記錄 + 結構同構檢測
# ═══════════════════════════════════════════════════════════════

_last_iso_turn = 0

def _detect_isomorphism():
    global _last_iso_turn
    if _turn_counter - _last_iso_turn < 5:
        return
    _last_iso_turn = _turn_counter
    db = _db()
    cutoff = _turn_counter - 50
    rows = db.execute(
        "SELECT path, depth, COUNT(*) as cnt FROM path_log WHERE turn > ? AND path != '' GROUP BY path",
        (cutoff,)
    ).fetchall()
    if len(rows) < 2:
        db.close()
        return
    now = datetime.utcnow().isoformat()
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            pa, pb = rows[i]["path"], rows[j]["path"]
            sim = _path_similarity(pa, pb)
            if sim >= 0.7:
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
    """每輪競爭結束後執行：去蕪存菁（turn-based）。"""
    global _turn_counter

    for t in TULPAS:
        recent_sum = sum(t.recent_hits[-20:])
        if t._sleeping:
            if recent_sum > 0:
                t._sleeping = False
                t.base_weight = max(0.3, t.base_weight)
        else:
            if recent_sum > 0 and t._winless_streak >= 30:
                t._sleeping = True
                t.base_weight = 0.2

    db = _db()
    dead_kws = db.execute(
        "SELECT keyword, tulpa_name FROM keyword_stats WHERE lifetime_misses > 50 AND active=1"
    ).fetchall()
    for dk in dead_kws:
        kw, tn = dk["keyword"], dk["tulpa_name"]
        for t in TULPAS:
            if t.name == tn and kw in t.keywords:
                t.keywords.remove(kw)
                if not hasattr(t, '_removed_keywords'):
                    t._removed_keywords = []
                t._removed_keywords.append(kw)
        db.execute("UPDATE keyword_stats SET active=0 WHERE keyword=? AND tulpa_name=?",
                   (kw, tn))
    db.commit()

    stale_cutoff = _turn_counter - 50
    db.execute("""
        DELETE FROM ontology
        WHERE relation='pattern→tulpa' AND last_turn > 0 AND last_turn < ?
    """, (stale_cutoff,))
    db.commit()

    old_turn = _turn_counter - 100
    db.execute("""
        DELETE FROM object_facets WHERE last_turn > 0 AND last_turn < ?
    """, (old_turn,))
    db.commit()

    # #11: 清除長久未晉升的 domain_keyword_candidates（observing > 24h）
    db.execute("""
        DELETE FROM domain_keyword_candidates
        WHERE state='observing' AND count < 3 AND last_seen != '' AND
              CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', last_seen) AS INTEGER) > 86400
    """)
    db.commit()

    # #12: 過期未結算預測（同 session 超過 50 輪）
    stale_pred_turn = _turn_counter - 50
    db.execute("""
        UPDATE prediction_events SET state='expired'
        WHERE state='pending' AND pred_turn < ?
    """, (stale_pred_turn,))
    db.commit()

    # 領域優化 prune：高校正率節點 → deprecate，noise 關鍵字 → 刪除
    for row in db.execute(
        "SELECT path, total_hits, corrections, effective_hits, deprecated FROM domain_optimization WHERE total_hits > 0"
    ).fetchall():
        path = row["path"]
        hits = row["total_hits"]
        corr = row["corrections"]
        eff = row["effective_hits"]
        dep = row["deprecated"]
        # avg_correction_trend = corrections / (corrections + effective_hits)
        total_effective = corr + eff
        trend = corr / max(total_effective, 1) if total_effective > 0 else 0.0
        # 60%+ 校正率且 hit > 3 → deprecate
        if trend > 0.6 and hits > 3 and not dep:
            db.execute("UPDATE domain_optimization SET deprecated=1 WHERE path=?", (path,))
        # 更新 trend
        db.execute("UPDATE domain_optimization SET avg_correction_trend=? WHERE path=?", (round(trend, 3), path))

    # domain_keyword_perf prune：false_pos 超過 good_hits 兩倍且 total > 3 → 噪音
    for row in db.execute(
        "SELECT path, keyword, good_hits, false_pos FROM domain_keyword_perf WHERE (good_hits+false_pos) > 3"
    ).fetchall():
        if row["false_pos"] > row["good_hits"] * 2:
            db.execute("DELETE FROM domain_keyword_perf WHERE path=? AND keyword=?", (row["path"], row["keyword"]))

    db.commit()

    # #14: 每 500 輪 VACUUM
    _pc = getattr(prune_cycle, '_vacuum_counter', 0) + 1
    prune_cycle._vacuum_counter = _pc
    if _pc >= 20:  # prune 約每 5 輪跑一次 → 20 次 ≈ 100 輪觸發一次
        db.execute("VACUUM")
        db.commit()
        prune_cycle._vacuum_counter = 0
        print("[tulpa] ✅ VACUUM completed")

    db.close()


# ═══════════════════════════════════════════════════════════════
# 第三位置觀察者（meta-tulpa）
# ═══════════════════════════════════════════════════════════════

def _learned_confidence(insight_type: str, base_conf: float) -> float:
    """觀察者學習回饋：根據同 insight_type 的人類審議歷史，調整建議信心。"""
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
        return base_conf
    rate = appr / samples
    adj = base_conf * (0.5 + rate)
    return round(min(adj, 0.99), 2)


def _observe_third_position(scored: list, winner, text: str):
    """第三位置：不參與競爭，觀察競爭歷史，發現模式。

    雙向循環 — 18428 → Aris：
    每當觀察到 conflict/contradiction，寫入 :11551/store 作為反思記憶（M7），
    讓下一輪的 Aris 可以在 /wake 中讀到自己的思辨記錄。
    """
    if not scored:
        return
    now = datetime.utcnow().isoformat()
    scores = {t.name: s for t, s in scored}

    def _store_to_aris_memory(insight_type: str, description: str, evidence: dict):
        """將 18428 的觀察寫入 Aris 記憶系統（M7 反思記憶）。"""
        global _aris_memory_failures
        try:
            import urllib.request as _req
            content = f"[18428 反思] {insight_type}: {description[:200]}"
            payload = json.dumps({
                "source": "tulpa-18428",
                "source_id": f"18428-reflect-{int(time.time())}",
                "content": content[:2000],
                "origin": "auto_generated",
                "tags": ["tulpa", "reflection", insight_type],
                "event_type": "reflection",
                "attention_line": f"⟶下一步: 注意到 {description[:80]}",
            }, ensure_ascii=False).encode()
            req = _req.Request("http://127.0.0.1:11551/memories/store",
                               data=payload,
                               headers={"Content-Type": "application/json"})
            _req.urlopen(req, timeout=2)
        except Exception:
            _aris_memory_failures += 1  # 可見警報，非靜默降級

    # 1. conflict
    sorted_pairs = sorted(scores.items(), key=lambda x: -x[1])
    for i in range(len(sorted_pairs)):
        for j in range(i + 1, len(sorted_pairs)):
            na, sa = sorted_pairs[i]
            nb, sb = sorted_pairs[j]
            if abs(sa - sb) < 0.1 and sa > 0.3 and sb > 0.3:
                desc = f"衝突: {na}({sa:.3f}) vs {nb}({sb:.3f}) — 分數接近"
                _store_to_aris_memory("conflict", desc, {"a": na, "b": nb, "score_a": sa, "score_b": sb})
                db = _db()
                cur1 = db.execute("""
                    INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, created_at)
                    VALUES (?, 'conflict', ?, ?, ?, ?)
                """, (_turn_counter, desc, json.dumps({"a": na, "b": nb, "score_a": sa, "score_b": sb}),
                      round(min(sa, sb), 2), now))
                insight_id = cur1.lastrowid
                conf = round(min(sa, sb), 2)
                learned_conf = _learned_confidence("conflict", conf)
                db.execute("""
                    INSERT INTO pending_suggestions (session_id, source_insight_id, insight_type, suggested_action, description, confidence, evidence, status, created_at)
                    VALUES (?, ?, 'conflict', 'merge', ?, ?, ?, 'pending', ?)
                """, (_session_id, insight_id, desc, learned_conf,
                      json.dumps({"a": na, "b": nb, "score_a": sa, "score_b": sb}), now))
                db.commit()
                db.close()

    # 2. contradiction
    for t, s in scored:
        if t is winner and t.base_weight < 0.9 and t._winless_streak > 5:
            desc = f"矛盾: {t.name} 贏了({s:.3f})但 weight 持續下降({t.base_weight:.3f})"
            _store_to_aris_memory("contradiction", desc, {"name": t.name, "weight": t.base_weight, "score": s})
            db = _db()
            cur2 = db.execute("""
                INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, created_at)
                VALUES (?, 'contradiction', ?, ?, ?, ?)
            """, (_turn_counter, desc, json.dumps({"name": t.name, "weight": t.base_weight, "score": s}),
                  0.5, now))
            insight_id = cur2.lastrowid
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
    """過去 tulpa：根據 path_log 歷史頻率算分。"""
    db = _db()
    rows = db.execute(
        "SELECT path, COUNT(*) as cnt FROM path_log GROUP BY path ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    db.close()
    if not rows:
        return 0.0
    total = sum(r["cnt"] for r in rows)
    top_cnt = rows[0]["cnt"]
    return round(top_cnt / max(total, 1), 3)


def _present_tulpa_score(text: str) -> float:
    """現在 tulpa：當前輸入的領域樹匹配強度。"""
    domain = route_domain(text)
    if domain["routed"]:
        return 0.8
    ontology = _make_signature(text)
    if ontology and ontology != "none":
        return 0.5
    return 0.2


def _future_tulpa_score(text: str):
    """未來 tulpa：根據 path_log 條件機率預測下一步。"""
    domain = route_domain(text)
    current_path = "/".join(domain["domain_path"]) if domain["routed"] else ""
    if not current_path:
        return {"score": 0.15, "predicted_path": "", "confidence": 0, "total_samples": 0, "learned": 0}
    db = _db()
    cur_depth = current_path.count("/") + 1
    target_depth = cur_depth + 1
    rows = db.execute(
        "SELECT path, COUNT(*) as cnt FROM path_log "
        "WHERE path LIKE ? || '/%' AND path != ? "
        "GROUP BY path ORDER BY cnt DESC LIMIT 3",
        (current_path, current_path)
    ).fetchall()
    rows = [r for r in rows if r["path"].count("/") + 1 == target_depth]
    db.close()
    if not rows:
        return {"score": 0.2, "predicted_path": "", "confidence": 0, "total_samples": 0, "learned": 0}
    total = sum(r["cnt"] for r in rows)
    top_cnt = rows[0]["cnt"]
    pred_path = rows[0]["path"]
    pred_pct = top_cnt / max(total, 1)
    g_rate, g_samples = _global_prediction_accuracy()
    score = 0.3 + 0.5 * pred_pct
    if g_samples >= 20:
        if g_rate < 0.3:
            score *= 0.8
        elif g_rate < 0.5:
            score *= 0.9
    psi = _psi_state()
    if psi["stress"] > 0.70:
        score *= 0.7
    if psi["attention"] == "idle":
        score *= 0.85
    growth_boost = max(0.0, psi["growth"] - 0.5) * 0.15
    score += growth_boost
    return {
        "score": round(score, 3),
        "predicted_path": pred_path,
        "confidence": round(pred_pct, 3),
        "total_samples": total,
        "learned": g_samples,
    }


def _active_alerts() -> list:
    """主動警報：超過閾值才亮。"""
    db = _db()
    pend = db.execute("SELECT COUNT(*) FROM pending_suggestions WHERE status='pending'").fetchone()[0]
    acc_row = db.execute("SELECT COUNT(*) t, COALESCE(SUM(correct),0) ok FROM prediction_events WHERE state='settled'").fetchone()
    expired = db.execute("SELECT COUNT(*) FROM prediction_events WHERE state='expired'").fetchone()[0]
    db.close()
    alerts = []
    if pend >= 10:
        alerts.append({"type":"PENDING_STACK","level":"warn","msg":f"待審建議堆積 {pend} 筆", "value": pend})
    s_t, s_ok = acc_row["t"], acc_row["ok"]
    if s_t >= 8 and (s_ok/s_t) < 0.3:
        alerts.append({"type":"ACC_CRASH","level":"crit","msg":f"預測準確率僅 {round(s_ok/s_t,2)}", "value": round(s_ok/s_t,2)})
    if expired >= 20:
        alerts.append({"type":"EXPIRED_SURGE","level":"warn","msg":f"已過期未結算預測 {expired} 筆", "value": expired})
    return alerts


def _psi_state() -> dict:
    """讀 PSI daemon 外部狀態（5 秒快取）。"""
    global _psi_cache, _psi_cache_time
    now = time.time()
    if _psi_cache and (now - _psi_cache_time) < _psi_cache_ttl:
        return _psi_cache
    sp = "/Users/ryan/Developer/laap-AGI/aris_brain/state/rust-latest.json"
    try:
        d = json.load(open(sp))
        needs = d.get("needs", {})
        affect = d.get("affect", {})
        det = {
            "stress": float(affect.get("stress", 0.5)),
            "growth": float(needs.get("growth", 0.5)),
            "attention": d.get("attention", "idle"),
            "available": True,
        }
        _psi_cache = det
        _psi_cache_time = now
    except Exception:
        det = {"stress": 0.5, "growth": 0.5, "attention": "idle", "available": False}
        if not _psi_cache:
            _psi_cache = det  # 首次失敗也寫入快取，避免每輪都試
            _psi_cache_time = now
    return _psi_cache


def _global_prediction_accuracy() -> tuple:
    """全域預測準確率。回傳 (rate, samples)。"""
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
    """結算所有該結算的 pending 預測。

    2026-09-06 修復（T2/T4）：原版只結算 predicted == actual_path 的「猜中」，
    猜錯的永遠掛 pending → 被 session 結束標 expired → 對賭只有贏沒有輸
    → 永遠沒有懲罰訊號 → 校準不可能發生（正確欄位從未被填 0）。
    新版：pred_turn 早於本輪的 pending 一律結算——對上 correct=1（贏），
    對不上 correct=0（輸，留痕餵對賭）。

    2026-09-07:改用 get_turn() 讀即時 turn,修掉 from-import 複本不同步
    （原 _turn_counter 複本永為 0 → prediction 永不結算）。
    """
    from tulpa.tulpa_db import get_turn
    now_turn = get_turn()
    db = _db()
    rows = db.execute(
        "SELECT id, predicted FROM prediction_events "
        "WHERE state='pending' AND pred_turn < ?",
        (now_turn,)
    ).fetchall()
    for row in rows:
        correct = 1 if row["predicted"] == actual_path else 0
        db.execute(
            "UPDATE prediction_events SET actual_turn=?, actual=?, correct=?, state='settled' WHERE id=?",
            (now_turn, actual_path, correct, row["id"]))
    db.commit()
    db.close()


def _time_axis_compete(text: str) -> dict:
    """時間軸競爭：過去/現在/未來三個 tulpa 打架。"""
    past = _past_tulpa_score(text)
    present = _present_tulpa_score(text)
    future_result = _future_tulpa_score(text)
    future = future_result["score"] if isinstance(future_result, dict) else future_result
    scored = [("past", past), ("present", present), ("future", future)]
    scored.sort(key=lambda x: -x[1])
    winner, win_score = scored[0]
    now = datetime.utcnow().isoformat()
    predicted_path = future_result.get("predicted_path", "") if isinstance(future_result, dict) else ""
    db = _db()
    db.execute(
        "INSERT INTO time_axis_log (turn, winner, score, past_score, present_score, future_score, predicted_path, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (_turn_counter, winner, win_score, past, present, future, predicted_path, now))
    db.commit()
    db.close()
    if predicted_path:
        db2 = _db()
        db2.execute(
            "INSERT INTO prediction_events (session_id, pred_turn, predicted, state, created_at) VALUES (?,?,?,'pending',?)",
            (_session_id, _turn_counter, predicted_path, now))
        db2.commit()
        db2.close()
    return {
        "winner": winner, "score": win_score,
        "past": past, "present": present, "future": future,
        "predicted_path": predicted_path,
    }


# ═══════════════════════════════════════════════════════════════
# 實驗/創造者（分裂、合併、跨域串連）
# ═══════════════════════════════════════════════════════════════

def _suggest_merge() -> dict:
    """根據 structure_isomorphism 表建議合併領域樹節點。"""
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
            "path_a": r["path_a"], "path_b": r["path_b"],
            "similarity": r["similarity"], "hits": r["hits"],
            "suggested_parent": r["path_a"].rsplit("/", 1)[0] if "/" in r["path_a"] else r["path_a"],
        })
    return {"suggested": True, "merges": suggestions}


def _execute_merge(path_a: str, path_b: str) -> str:
    """執行合併。"""
    parent = path_a.rsplit("/", 1)[0] if "/" in path_a else path_a
    now = datetime.utcnow().isoformat()
    db = _db()
    db.execute("UPDATE structure_isomorphism SET merged=1 WHERE path_a=? AND path_b=?", (path_a, path_b))
    desc = f"合併執行: {path_a} + {path_b} → 上層抽象 {parent}"
    db.execute("""
        INSERT INTO observer_insights (turn, insight_type, description, evidence, confidence, addressed, created_at)
        VALUES (?, 'merge', ?, ?, 0.8, 1, ?)
    """, (_turn_counter, desc, json.dumps({"path_a": path_a, "path_b": path_b, "parent": parent}), now))
    db.commit()
    db.close()
    return parent


def _execute_split(name: str, new_name: str, split_keywords: list) -> bool:
    """執行分裂：建立新 Tulpa 實例。"""
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
        name=new_name, keywords=split_keywords,
        base_urgency=source.base_urgency, base_importance=source.base_importance,
        base_weight=0.5,
        context_text=f"專注於 {new_name} 相關的任務",
        gist_text=f"涉及 {new_name}",
    )
    TULPAS.append(new_t)
    source.keywords = remaining_kw
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
    """每輪執行一次實驗/創造者循環。"""
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
