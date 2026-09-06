#!/usr/bin/env python3
"""tulpa 套件 — 18428 六個 tulpa 競爭引擎的模組化版本。

切割自 aris_tulpa_api.py（2597 行巨獸）：
  - tulpa/tulpa_db.py        — 資料庫操作層
  - tulpa/tulpa_engine.py    — 核心引擎（Tulpa, 競爭, Ontology）
  - tulpa/tulpa_domain.py    — 領域樹（房產財商教練）
  - tulpa/tulpa_search.py    — 被動知識搜尋
  - tulpa/tulpa_evolution.py — 演化和學習（prune, isomorphism, observer）
  - tulpa/tulpa_api.py       — HTTP API 處理器（最薄）

使用方式：
    from tulpa import TULPAS, ALL_DOMAINS, compete, prune_cycle
"""

from tulpa.tulpa_db import (
    _db, _init_db, load_tulpa_state, save_tulpa_state,
    save_session_delta, load_object_facets, save_object_facet,
)
from tulpa.tulpa_engine import (
    Tulpa, TULPAS, _session_id, _session_start, _session_deltas,
    _apply_persisted, classify, learn_ontology,
    _track_domain_candidates, _track_domain_hit,
    _update_ontology_last_seen, _log_path,
    _init_keyword_stats, _log_migration, _track_keyword_miss,
    _path_similarity,
    score_tulpa, compete,
    _make_signature,
    _apply_domain_keyword_additions,
)
from tulpa.tulpa_domain import (
    ALL_DOMAINS, DomainNode, route_domain, _match_tree,
    _find_node, _path_keywords, _domain_words,
)
from tulpa.tulpa_search import (
    passive_search, _search_files, _read_head,
)
from tulpa.tulpa_api import (
    build_app, handle_cognitive, handle_health, handle_state,
    handle_audit, handle_migration, handle_observer, handle_timeaxis,
    handle_convergence, handle_experiment, handle_predictions,
)
from tulpa.tulpa_evolution import (
    prune_cycle,
    _detect_isomorphism,
    _learned_confidence,
    _observe_third_position,
    _past_tulpa_score, _present_tulpa_score, _future_tulpa_score,
    _active_alerts, _psi_state, _global_prediction_accuracy, _settle_prediction,
    _time_axis_compete,
    _suggest_merge, _execute_merge, _execute_split, _run_experiment_cycle,
)

__all__ = [
    "Tulpa", "TULPAS", "ALL_DOMAINS",
    "compete", "prune_cycle", "classify", "score_tulpa",
    "_db", "_init_db",
    "load_tulpa_state", "save_tulpa_state",
    "save_session_delta", "load_object_facets", "save_object_facet",
    "_session_id", "_session_start", "_session_deltas",
    "_apply_persisted", "learn_ontology",
    "_find_node", "_path_keywords", "_domain_words",
    "_track_domain_candidates", "_track_domain_hit",
    "_update_ontology_last_seen", "_log_path",
    "_init_keyword_stats", "_log_migration", "_track_keyword_miss",
    "_path_similarity",
    "passive_search", "route_domain", "_search_files", "_read_head",
    "_make_signature",
    "_apply_domain_keyword_additions",
    "_detect_isomorphism", "_learned_confidence",
    "_observe_third_position",
    "_past_tulpa_score", "_present_tulpa_score", "_future_tulpa_score",
    "_active_alerts", "_psi_state", "_global_prediction_accuracy",
    "_settle_prediction",
    "_time_axis_compete",
    "_suggest_merge", "_execute_merge", "_execute_split",
    "_run_experiment_cycle",
]
