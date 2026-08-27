# Graph Report - .  (2026-08-13)

## Corpus Check
- 286 files · ~190,434 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2968 nodes · 4920 edges · 281 communities (206 shown, 75 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 351 edges (avg confidence: 0.6)
- Token cost: 28,000 input · 9,500 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 134
- Community 135
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 141
- Community 142
- Community 143
- Community 144
- Community 145
- Community 147
- Community 148
- Community 149
- Community 150
- Community 151
- Community 152
- Community 153
- Community 154
- Community 155
- Community 156
- Community 157
- Community 158
- Community 159
- Community 160
- Community 161
- Community 162
- Community 163
- Community 164
- Community 165
- Community 166
- Community 167
- Community 168
- Community 169
- Community 170
- Community 171
- Community 172
- Community 173
- Community 174
- Community 175
- Community 176
- Community 177
- Community 178
- Community 179
- Community 180
- Community 181
- Community 182
- Community 183
- Community 184
- Community 185
- Community 186
- Community 187
- Community 188
- Community 189
- Community 190
- Community 191
- Community 192
- Community 193
- Community 195
- Community 196
- Community 197
- Community 198
- Community 199
- Community 200
- Community 201
- Community 202
- Community 203
- Community 204
- Community 205
- Community 206
- Community 207
- Community 208
- Community 209
- Community 210
- Community 211
- Community 212
- Community 213
- Community 214
- Community 217
- Community 218
- Community 220
- Community 221
- Community 222
- Community 224
- Community 225
- Community 228
- Community 229
- Community 230
- Community 233
- Community 234
- Community 235
- Community 236
- Community 237
- Community 238
- Community 239
- Community 240
- Community 241
- Community 242
- Community 243
- Community 244
- Community 245
- Community 246
- Community 247
- Community 248
- Community 249
- Community 250
- Community 251
- Community 252
- Community 253
- Community 254
- Community 255
- Community 256
- Community 257
- Community 258
- Community 259
- Community 260
- Community 261
- Community 262
- Community 263
- Community 264
- Community 265
- Community 266
- Community 267
- Community 268
- Community 274
- Community 275
- Community 280

## God Nodes (most connected - your core abstractions)
1. `PsiCore` - 127 edges
2. `CognitiveBus` - 87 edges
3. `PythonPsiBackend` - 76 edges
4. `AgencyLoop` - 72 edges
5. `NeedDriveSystem` - 70 edges
6. `RustPsiBackend` - 46 edges
7. `NeedType` - 46 edges
8. `EmotionGradient` - 40 edges
9. `ArisMemory` - 37 edges
10. `TestBdd` - 37 edges

## Surprising Connections (you probably didn't know these)
- `AgencyLoop` --uses--> `GbrainError`  [INFERRED]
  laap/agency.py → gbrain_client.py
- `FakePsi` --uses--> `AgencyLoop`  [INFERRED]
  scripts/check-affective.py → laap/agency.py
- `MockPsi` --uses--> `AgencyLoop`  [INFERRED]
  scripts/check-trust-presence.py → laap/agency.py
- `MockTools` --uses--> `AgencyLoop`  [INFERRED]
  scripts/check-trust-presence.py → laap/agency.py
- `MockPsi` --uses--> `AgencyLoop`  [INFERRED]
  scripts/sandbox-l1-abc.py → laap/agency.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Aris Core Subsystems** — psi_core, agency_loop, gbrain, tool_executor, affective_engine, consolidation, chatflow, llm_respond, safety_gate, goal_bridge [EXTRACTED 1.00]
- **Iron Law Triad** — iron_law_1, iron_law_2, iron_law_3, iron_law_0 [EXTRACTED 1.00]
- **Aris Port Map** — port_11546, port_11547, port_11550, port_11551 [EXTRACTED 1.00]
- **Aris Core Subsystems** — docs_aris_memory_ontology_psi_core, docs_aris_memory_ontology_agencyloop, docs_aris_memory_ontology_toolexecutor, docs_aris_memory_ontology_gbrain, docs_aris_memory_ontology_affectiveengine, docs_aris_memory_ontology_constitution, docs_aris_memory_ontology_safetygate [EXTRACTED 1.00]
- **PsiEngine v2 Frequency Tiers** — docs_rust_psi_neuralis_psi_v2_minimal_spec_needdynamics, docs_rust_psi_neuralis_psi_v2_minimal_spec_affectdynamics, docs_rust_psi_neuralis_psi_v2_minimal_spec_attentiongate, docs_rust_psi_neuralis_psi_v2_minimal_spec_eventreducer, docs_rust_psi_neuralis_psi_v2_minimal_spec_snapshotpublisher, docs_rust_psi_neuralis_psi_v2_minimal_spec_tickmetrics [EXTRACTED 1.00]
- **Sandbox Learning System Components** — docs_specs_aris_sandbox_learning_part_01_principles_sandbox, docs_specs_aris_sandbox_learning_part_01_principles_triple_separation, docs_specs_aris_sandbox_learning_part_04_decision_analysis_candidate_change_package, docs_specs_aris_sandbox_learning_part_04_decision_analysis_four_facet_analysis, docs_specs_aris_sandbox_learning_part_05_external_ai_external_ai_advisor, docs_specs_aris_sandbox_learning_part_06_ch18_learning_case_format_learning_case, docs_specs_aris_sandbox_learning_part_03_sandbox_capability_manifest [EXTRACTED 1.00]
- **三層學習循環（快/中/慢）** — docs_specs_aris_sandbox_learning_part_06_learning_three_layer_learning_loop, docs_specs_aris_sandbox_learning_part_06_learning_fast_loop, docs_specs_aris_sandbox_learning_part_06_learning_medium_loop, docs_specs_aris_sandbox_learning_part_06_learning_slow_loop [EXTRACTED 1.00]
- **GBrain × OpenViking 四層堆疊 (L0-L3)** — docs_specs_parked_gbrain_aris_loop_l0_openviking, docs_specs_parked_gbrain_aris_loop_l1_ledger, docs_specs_parked_gbrain_aris_loop_l2_calibration, docs_specs_parked_gbrain_aris_loop_l3_reasoning [EXTRACTED 1.00]
- **安全自我進化脊椎六階段（防護欄先於能力）** — docs_specs_safe_self_evolution_route_stage0_hard_bounds, docs_specs_safe_self_evolution_route_stage1_eval_integrity, docs_specs_safe_self_evolution_route_stage2_cost_gate, docs_specs_safe_self_evolution_route_stage3_delegation, docs_specs_safe_self_evolution_route_stage3_5_router_canary, docs_specs_safe_self_evolution_route_stage4_division_learning, docs_specs_safe_self_evolution_route_stage5_b_gate [EXTRACTED 1.00]
- **L1 Testing Framework (A/B/C Paradigm)** — reports_restart_invariance_l0_pass, reports_restart_invariance_gbrain_persistence, reports_l1_retest_r3_l1_pass, reports_l1_retest_r3_hidden_payoff_table, reports_sandbox_signal_measure_result_5th_hole, reports_sandbox_signal_measure_result_word_relevance_gate, reports_sandbox_l1_abc_sandbox_l1, reports_sandbox_l1_abc_tie_break_contamination, reports_learning_capability_assessment_4_holes [INFERRED 0.85]
- **Scoring Router Safety System** — docs_specs_scoring_router_canary_scoring_router, docs_specs_scoring_router_canary_sandbox_canary, docs_specs_scoring_router_canary_trust_ratchet, docs_specs_scoring_router_canary_4_routing_lanes, docs_specs_scoring_router_canary_action_classification_table, docs_specs_scoring_router_canary_verdict_v2, docs_specs_safe_upgrade_rollback_plan_kill_switch, topology_agent_os [INFERRED 0.85]
- **Aris System Topology Nodes** — topology_bridge, topology_aris_api, topology_aris_memory, topology_gbrain, topology_agent_os, topology_rust_psi_daemon, topology_wake_reads_three [EXTRACTED 1.00]

## Communities (281 total, 75 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (40): CognitiveBus, 認知事件總線 — 模組之間唯一的通訊通道。 特性： - publish/subscribe 模式 - 線程安全（RLock） - 內建狀態（needs /…, 回傳在 stale_threshold 秒內有 heartbeat 的模組列表。, 訂閱某類型事件。callback 簽名: callback(source: str, data: dict), 用快照覆蓋當前狀態（psi_core 驅動）。, 每輪對話前調用（供 psi_core_bridge publish_psi_state 使用）。, ensure_agency(), ensure_psi_core() (+32 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (20): NeedDriveSystem, 每秒向靜息值鬆弛 + 雜訊。 血清素：valence 調節 decay 速率。 valence > 0.3 → decay × 0.7（滿足感，需求慢降）…, 五維需求驅動系統 — 基於 Dörner PSI 理論。 每個需求有: 當前值、目標值、衰減率、重要性、波動率。 drive = max(0, target…, fixture, MonkeyPatch, Record the exact initial values. Changing these is a breaking change that must…, drive = max(0, target - current) * importance., At initial state, competence has the highest drive because its deficit is… (+12 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (28): AgencyLoop — Phase 6：閉合「需求 → 行動 → 結果 → 記憶」迴路（v0）。 誠實標註：v0 的「意圖形成」是規則表（drive 超閾值…, AttentionFocus, AttentionState, CognitiveEventType, CognitiveStateSnapshot, EmotionalValence, EmotionState, NeedState (+20 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (53): aris_growth_check(), aris_to_memory(), board_to_channel(), _bridge_python_fallback(), bridge_scoring_router(), channel_to_aris(), dual_evaluation_compare(), evaluator_audit() (+45 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (12): PythonPsiBackend, Explicit adapter over PsiCore. No `__getattr__`, no wildcard proxying — only…, adapter(), _fresh_core(), Draft202012Validator, fixture, A stopped PsiCore over its own bus (no heartbeat). Two of these have identical…, Adapter over the stopped `psi` fixture core. (+4 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (47): AffectiveEngine, Agency Loop, AgentOS, AgentOS-Aris Bridge, Aris, Aris Bootstrap Ladder, Aris=Brain, Scream=Body, aris_subconscious (+39 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (32): BaseHTTPRequestHandler, clean_reply(), _cut_marker_line(), format_salience(), get_current_psi(), heuristic_salience(), parse_salience(), 產生 salience 標記行（只保留可觀察的值）。 2026-07-30 最終版： - 勝任/確定/成長 肉眼不可觀察（homeostasis 拉回… (+24 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (41): _build_response(), _build_tool_response(), _collect_memories(), _credit_recall_async(), _dump_request(), _extract_user_msg(), _format_history(), install() (+33 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (43): _build_static_identity(), _build_system_prompt(), _build_toolmode_prompt(), _build_turn_prompt(), _cache_key(), _call_llm(), check_health(), _classify_intent() (+35 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (24): GbrainClient, GbrainError, Any, 呼叫 gbrain MCP tool，回傳解析後的 JSON。失敗 raise GbrainError。, gbrain 呼叫失敗（子行程死亡 / timeout / tool error）。呼叫端 fallback。, gbrain serve（MCP stdio）之上的最小 JSON-RPC 客戶端。, 30s 保活 ping：gbrain serve 在 ~60-90s 無呼叫時會自行退出 （2026-08-12 實測 11546 的 serve 每 1-4…, Popen (+16 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (16): AgencyLoop, _emit_event(), _env_float(), 腎上腺素：高 arousal 縮短 agency interval。 arousal 0-1，interval 範圍 [base × 0.3, base ×…, E1.2 延遲獎勵：被 recall 用到的 agency 記憶 → 獎勵其 need/angle 權重。 下游效用信號進學習 ——…, 催產素：每次使用者互動提升信任權重（從 chatflow 呼叫）。 遞增式上升（越接近 1 越難推），閒置由 _evaluate 向 baseline 回歸。…, 把 RPE 學習狀態寫入 gbrain slug _internal/agency-state。 煞車：_state_loaded=False…, 開機從 gbrain 讀回 RPE 學習狀態。retry 最多 3 次（embedding 冷啟動 ~3s）。 成功讀回 →… (+8 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (15): PsiCore, PSI 認知核心 — 讓 Aris 擁有動態內在狀態的心臟。 使用方式: bus = CognitiveBus(agent_name="Aris") psi…, 每次使用者輸入時呼叫：解析需求信號、更新狀態、發布事件。, 背景執行緒：定時衰減需求、更新情緒、同步到 CognitiveBus。, 回傳回應調性標籤 (e.g. 'confident.helpful', 'lonely.seeking')。, 將當前狀態序列化為三個層級，供 chatflow 回應生成使用。 回傳: { "state_label": str, # 調性標籤…, With constitution off, satisfying should not create audit files., PsiCore.get_state() output format. Note: needs/emotion/affective are accessed… (+7 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (37): _psi_memories_sync(), chatflow recall 專用的『獨立』gbrain 連線（自己的 serve 子行程）。 關鍵（2026-08-12…, 同步查 gbrain 相關記憶，供 psi-respond 織入。 2026-08-12 修復： - 鎖不擋唯讀召回（讀 gbrain…, _recall_client(), _append(), _load(), mark_credited(), _p() (+29 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (13): ASTNode, Compiler, Instruction, Lexer, Parser, Any, QuantumVM, psilang_v2 — PsiLang v2 認知語言最小實作 (dict-based) 提供 agi_kernel.py 需要的… (+5 more)

### Community 14 - "Community 14"
Cohesion: 0.07
Nodes (19): 執行工具，回傳結果文字。所有呼叫先過安全閘（Phase 4a）。 = stream() 的 drain 包裝：吃完全部事件，只回最終…, 執行工具，逐步 yield 事件 dict（sync generator，供 thread 中迭代）： {"type": "status", "text":…, 跑 subprocess，stdout 逐行 yield（stderr 併入 stdout）。 ponytail: 逾時只在行與行之間檢查 —…, 註冊本機可直接叫的工具（不透過 AgentOS）。, 工具執行層 — 把 CognitiveBus 事件轉成真實動作。, CognitiveBus ACTION_REQUEST 事件回呼。, 註冊自訂工具。exec_fn 簽名: (prompt: str) → str。 stream_fn（可選）簽名: (prompt: str) →…, 寫 LAAP 工具狀態到檔案 + channel，供 Scream TUI 即時消費。 (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (31): hit_rate(), is_relevant(), lookup(), C-a：gbrain 經驗快取當規劃器（安全脊椎 Stage 4，§4 路 C）。 決策前先問快取『gbrain 有沒有相關經驗/知識可導這個決定』： hit…, 在 gbrain hits 裡找相關命中。回 {hit, experience, slug}。 hits = hybrid_hits 的結果（caller…, 回 {rate, hits, total}。window_s 給就只算窗內。, record(), _tokens() (+23 more)

### Community 16 - "Community 16"
Cohesion: 0.09
Nodes (19): EmotionGradient, 情緒梯度場 — 從需求滿足率的變化自然湧現。 不需要 numpy。valence 是需求平均值的平滑映射。 arousal 從需求變化劇烈度驅動。, bus(), emotion(), needs(), psi(), fixture, conftest — PsiCore characterization test fixtures. Isolation notes: -… (+11 more)

### Community 17 - "Community 17"
Cohesion: 0.10
Nodes (10): Any, M3 B-route reader: remaps psi-daemon's native `neuralis-rust-psi/v1` schema to…, Read and parse the daemon's latest.json. Returns None on any error (missing,…, Fallback default matching Python PsiCore initial state., Mimic AffectiveState.compute_cognitive_bias() from 5D affect., Spawn psi-daemon with FIFO event channel。 2026-08-01：這裡本來只有…, Daemon 正在執行且 state 檔可讀。 Retries 參數容許 daemon 第一次寫入前的初期 race： daemon 以 100ms 寫入，5…, Pure function over get_state() dict. Preserves QUIRK-1: reads raw_valence… (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.11
Nodes (16): input_schema(), input_validator(), _load(), Draft202012Validator, fixture, parametrize, Path, Executable contract tests for the PSI backend v1 JSON Schemas. Validates… (+8 more)

### Community 19 - "Community 19"
Cohesion: 0.11
Nodes (15): AffectiveState, EmotionDimension, PersonalityProfile, Any, Enum, ndarray, affective — 5 維情緒引擎（PAD + Social + Stress），採自作者開源版。 Adapted from lorryjovens-…, 事件 → 刺激佇列（下次 update 套用）。未知事件回 False。 (+7 more)

### Community 20 - "Community 20"
Cohesion: 0.11
Nodes (21): _FakeProc, _mcp_stdout(), fixture, Path, shadow 雙路徑比對層測試（option b: 誠實窄比對 + 不可比分類）。 覆蓋 agentos-aris-bridge.py 的 shadow…, 組一行 MCP tools/call 回應（id==1），read_file 的內容放在 tool dict 的 stdout。, 把 shadow 全部導向 tmp，並開啟 SHADOW_ENABLED（不碰 process env）。, _read_log() (+13 more)

### Community 21 - "Community 21"
Cohesion: 0.07
Nodes (27): additionalProperties, description, $id, description, type, properties, metadata, schema_version (+19 more)

### Community 22 - "Community 22"
Cohesion: 0.14
Nodes (19): 從 RPE 歷史算每個查詢角度的權重（bandit-style）。 回 {angle_label: weight}，weight 越高越該選。 新角度權重…, C-b：該不該委派 Scream 做前瞻。**專屬開關預設 OFF** —— 需 Ryan 明確…, C-b：形成委派 Scream 前瞻的意圖（c2，走 scream-task 頻道）。記估算成本。, 情緒偏差調變探索率（affective 引擎的偏差接真參數 — 移植的意義所在）。 risk_seeking 升探索、attention_narrowing…, 跟近期查詢 token Jaccard ≥ 0.7 視為太像（包含 tool name 避免跨工具撞車）。, _budget(), _path(), agency 算力預算 ledger（安全脊椎 Stage 2）— 委派/前瞻的成本閘。 記 token 花費、滑動小時窗；超預算 → 呼叫端該降頻（E2-b… (+11 more)

### Community 23 - "Community 23"
Cohesion: 0.14
Nodes (25): PathBuf, Result, all_outputs_within_clamp(), CognitiveBiases, compute(), optimism_and_pessimism_are_mutually_exclusive(), Args, create_fifo() (+17 more)

### Community 24 - "Community 24"
Cohesion: 0.08
Nodes (25): _build_response(), _classify_by_route(), _decision_source_for_entry(), _gate_scan(), _get_psi_behavior_modifier(), _get_route_tool(), _get_task_signoff_state(), _llm_judge_route() (+17 more)

### Community 25 - "Community 25"
Cohesion: 0.18
Nodes (12): ArrayQueue, events_flow_from_handle_into_state(), logical_timestamp_uses_epoch_and_tick_count(), PsiEngine, PsiHandle, ring_overflow_coalesces_oldest(), Arc, Option (+4 more)

### Community 26 - "Community 26"
Cohesion: 0.14
Nodes (11): _age_days(), ConsolidationLoop, _env_float(), _f(), _normalize(), ConsolidationLoop — Phase 5：記憶固化循環（睡眠）。 「記憶有存取、缺睡眠」（docs/research/external-…, 有互動就重置閒置計時（memory_bridge 餵 psi 時順手呼叫）。, 一輪固化。回傳統計 dict（供自檢/審計）。 (+3 more)

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (21): _audit(), classify(), 回 "readonly_builtin" / "readonly_agentos" / "write"。 工具分類 chokepoint —…, _audit(), create_snapshot(), _git(), commit 級快照 — 自主寫入前的還原點（安全脊椎 Stage 0，協定鐵律 2）。 任何自動放行的改動前建快照，壞了一鍵 revert。用 `git…, 建還原點，回 commit SHA。工作樹髒 → stash-create 捕捉；乾淨 → HEAD。 (+13 more)

### Community 28 - "Community 28"
Cohesion: 0.09
Nodes (23): _acquire_lock(), _build_keyword_routes(), _ensure_headroom_proxy(), _fetch_wake_context(), _load_agentos_config(), _load_headroom_config(), _load_processed(), main_loop() (+15 more)

### Community 29 - "Community 29"
Cohesion: 0.22
Nodes (21): _board_entry(), _build_status(), _check_agency_bypass(), _check_bridge_env(), _check_deny_spike(), _check_sandbox_success(), CheckResult, _deliver_to_board() (+13 more)

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (16): AtomicBool, Duration, Instant, breaker_degrades_and_recovers(), BreakerState, CircuitBreaker, loop_produces_ticks_at_roughly_target_rate(), miss_during_recovery_resets_count() (+8 more)

### Community 31 - "Community 31"
Cohesion: 0.09
Nodes (22): 學習成效驗收 (Learning Acceptance Metrics), Part 6: 自主學習系統 (Autonomous Learning System), 快循環 (Fast Loop — 單次沙箱內迭代), laap/agency.py (RPE 學習機制), 中循環 (Medium Loop — 跨案例模式識別), 結果訊號設計 (Result Signal Design), 慢循環 (Slow Loop — 正式策略升級), 三層學習循環 (Three-Layer Learning Loop) (+14 more)

### Community 32 - "Community 32"
Cohesion: 0.13
Nodes (20): _feed(), 餵 psi + 重置 consolidation 睡眠窗，並量出這句話造成的實際 delta。 回 (state_after, delta) 或…, 圓作者的檔案契約：Rust psi_core 本該每 100ms 寫 state/latest.json， 整個…, _write_author_state(), get_consolidation(), get_psi_core(), _count_pending(), _memory_breakdown() (+12 more)

### Community 33 - "Community 33"
Cohesion: 0.16
Nodes (11): store_important(), _backend_mode(), _gbrain(), MemoryFragment, MemoryStore, 記憶片段。作者以 r.content[:50] 取用，故 content 必為 str。, 階層記憶儲存（core / episodic）。gbrain 為真後端，in-process 為快取 + fallback。, 讀取層清洗：剝掉 markdown 樣板，保留實際內容。 為什麼修在這裡：gbrain 2251 頁混合 Ryan 知識庫 + Aris 記憶，寫入時清洗會… (+3 more)

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (14): converges_to_target_without_noise(), drive_formula_matches_spec_table(), NeedDynamics, R, Self, StdRng, serumtonin_slows_relaxation(), setup() (+6 more)

### Community 35 - "Community 35"
Cohesion: 0.14
Nodes (20): AffectiveState, CognitiveBus, EmotionGradient, NeedDriveSystem, PsiBackend v1, Prigogine Dissipative Structures (1977), PSI Theory (Dörner 1999), autonomic/broomva (S4) (+12 more)

### Community 36 - "Community 36"
Cohesion: 0.17
Nodes (12): Histogram, main(), parse_args(), CatchUpPolicy, catchup_counted_by_type(), drift_accumulates_signed_at_ns_resolution(), MetricsReport, miss_counted_only_above_period() (+4 more)

### Community 37 - "Community 37"
Cohesion: 0.13
Nodes (16): _emotion_intensity_for(), _emotion_rerank(), _hash_embed(), hybrid_hits_any(), _memory_first(), ndarray, _query_tokens(), memory_store — top-level module for laap-AGI's bare import.… (+8 more)

### Community 38 - "Community 38"
Cohesion: 0.11
Nodes (7): ArisMemory, Phase 2: 被 query 命中 + 實際被用到 → discovered_salience += 0.1 (cap 1.0),…, 查詢記憶。支援全文檢索 + 來源過濾 + 分頁 + confidence 過濾。 confidence_gte: 最低 confidence…, 記錄一條因果鏈：A（cause）導致 B（effect），結果是 outcome。, 前瞻分析：查詢類似 PSI 狀態下該 route 的歷史成功率。, 從事件日誌和決策記錄重建上下文（Session replay）。, Phase 2: 回傳 flagged 分歧記憶（encoding_salience vs 外部評分差值 >2）。 這些是需要人工檢視的第二意見分歧條目。

### Community 39 - "Community 39"
Cohesion: 0.13
Nodes (5): FakeBackend, Any, MonkeyPatch, Strict fake that exposes only v1 methods. No needs/emotion/…, Verify the migration by checking that AgencyLoop's _evaluate and _act paths…

### Community 40 - "Community 40"
Cohesion: 0.20
Nodes (18): _content_text(), _is_harness_noise(), _is_user_turn(), _post_tool_outcomes(), 最後一條訊息是 user 才是真的使用者回合。工具迴圈的中間 round-trip （最後是 tool）不重複餵 psi、不重複加 trust、不重查記憶 —…, content 可能是 str / OpenAI content parts list / None（assistant tool_calls）。, 工具 round-trip 的結果 → 5 維情緒事件 — scream 通道的「行動後果塑形情緒」。 Aris 在 TUI…, Scream agent 迴圈：帶 tools 的請求 → llm_respond.respond_tools（executor 卸載 +… (+10 more)

### Community 41 - "Community 41"
Cohesion: 0.13
Nodes (11): patch, Verify correct type_hints for each route key., Unit tests for _track_failure() and _headroom_learn_async()., 5 failures trigger learn; count resets to 0., 4 failures do NOT trigger learn., HEADROOM_LEARN_ENABLED=False → no tracking, no learn., Learn ran recently → 5 failures throttle (skip)., 15 failures override throttle → learn triggered. (+3 more)

### Community 42 - "Community 42"
Cohesion: 0.17
Nodes (17): acquire_lock(), _bash(), _classify_task(), _clean_env(), execute_task(), _is_path_protected(), load_processed(), main() (+9 more)

### Community 43 - "Community 43"
Cohesion: 0.16
Nodes (9): _find_binary(), get_client(), hybrid_hits(), gbrain_client — 持久 gbrain MCP stdio 子行程客戶端。 memory_store /…, query（hybrid vec+lex）→ search（lex）兩層降級檢索，20s TTL 快取。 回 gbrain 原始 hit…, 回共用客戶端；gbrain binary 不存在回 None（呼叫端走 local fallback）。, C-a：決策前問 gbrain 快取有沒有相關經驗（gbrain-first）。 記 hit/miss → 真實命中率（校準 backtest 的粗略…, check_bridge() (+1 more)

### Community 44 - "Community 44"
Cohesion: 0.19
Nodes (14): _call_llm_stream(), _is_transient_upstream(), OpenAI-compatible streaming 呼叫（stream=True，SSE 逐塊解析）。yield: {"type": "token",…, SSE chunk 裡的上游 error 是否 transient（504 idle timeout / 過載 / 限流）值得重試。 err 是 dict（如…, FakeResp, _make_urlopen(), _patch(), A2 guard — _call_llm_stream 對 transient 失敗自動重試（止「手動繼續」痛點）。 規則：504 idle timeout… (+6 more)

### Community 45 - "Community 45"
Cohesion: 0.28
Nodes (13): AttentionGate, drives_with(), exits_to_idle_when_drive_collapses(), GateState, GatingDecision, idle_to_task_on_dominant_drive(), learning_on_high_uncertainty(), min_hold_blocks_immediate_reversal() (+5 more)

### Community 46 - "Community 46"
Cohesion: 0.21
Nodes (9): AffectParams, CouplingWeights, GateParams, NeedParams, PsiConfig, Default, Self, RuntimeParams (+1 more)

### Community 47 - "Community 47"
Cohesion: 0.11
Nodes (11): _make_mock_open_error(), _make_mock_response(), Parametrized BDD tests for Headroom integration (agentos-aris-bridge.py).…, Scenario: Bridge reuses already-running proxy., Scenario: Large JSON tool output is compressed., Build a urllib.response-like mock that returns JSON bytes., Build a mock that raises on urlopen., Scenario: Compressed output includes CCR hash. (+3 more)

### Community 48 - "Community 48"
Cohesion: 0.16
Nodes (13): check_claims_resolve(), check_consumers(), check_copied_constants(), check_gate_alive(), check_src_resolves(), _files(), _git(), load() (+5 more)

### Community 49 - "Community 49"
Cohesion: 0.12
Nodes (17): type, additionalProperties, description, properties, type, additionalProperties, type, additionalProperties (+9 more)

### Community 50 - "Community 50"
Cohesion: 0.12
Nodes (17): maximum, minimum, type, maximum, minimum, type, properties, arousal (+9 more)

### Community 51 - "Community 51"
Cohesion: 0.12
Nodes (17): description, type, description, minimum, type, description, properties, backend (+9 more)

### Community 52 - "Community 52"
Cohesion: 0.14
Nodes (16): _agentos_check(), _allowed_tools(), _delegation_tools(), _file_approved(), get_allowed_tools(), get_classification_map(), _protected_fragments(), SafetyGate — Phase 4a：工具執行安全閘（外部審查紅線：煞車先於能力）。 三層，全部 0 LLM： 0. 委派 path-DENY（甲/乙… (+8 more)

### Community 53 - "Community 53"
Cohesion: 0.12
Nodes (9): parametrize, Scenario: Failed execution skips compression., Scenario: Learn forced on high failure rate., Scenario: headroom_compress tool available in MCP., Scenario: headroom_retrieve tool available in MCP., Scenario: headroom_stats tool available in MCP., Scenario: Pipeline stages execute in order., Scenario: agentos.json declares the compress stage. (+1 more)

### Community 54 - "Community 54"
Cohesion: 0.14
Nodes (16): Three-Layer Upgrade Protection, Canary Upgrade Strategy, aris-halt Kill Switch, Four Routing Lanes, Action Classification Table, Sandbox Canary Lane, Scoring Router, Trust Ratchet Mechanism (+8 more)

### Community 55 - "Community 55"
Cohesion: 0.26
Nodes (15): _build_action_request(), _clean_env(), _execute_by_route(), _extract_code_block(), _extract_command(), _extract_path(), _extract_query(), _is_dangerous_command() (+7 more)

### Community 56 - "Community 56"
Cohesion: 0.33
Nodes (15): check_bootstrap(), check_consumers_gate(), check_docs(), check_nd_pipeline(), check_syntax_gate(), check_workorder(), main(), Path (+7 more)

### Community 57 - "Community 57"
Cohesion: 0.15
Nodes (10): find_mjs(), main(), patch(), Path, Glob dist for the main chunk (app-*.mjs)., Boundary: Empty string output skips compression., Boundary: Concurrent learn entries are independent., Scenario: Small output passes through uncompressed. (+2 more)

### Community 58 - "Community 58"
Cohesion: 0.33
Nodes (14): cmd_analyze(), cmd_ccp(), cmd_plan(), cmd_sandbox_create(), cmd_sandbox_destroy(), cmd_sandbox_list(), cmd_sandbox_test(), _find() (+6 more)

### Community 59 - "Community 59"
Cohesion: 0.12
Nodes (9): Boundary: _learn_fail_count overflow is safe (Python int)., Boundary: MCP server startup failure doesn't affect bridge pipeline., Scenario: Gate denial triggers learning., BDD scenario tests for Headroom integration. Each test_ method covers one BDD…, Scenario: MCP server registered in scream-code config., Snapshot mutable module globals before each test., Restore mutable module globals after each test., Scenario: Pipeline handles unknown route entries. (+1 more)

### Community 60 - "Community 60"
Cohesion: 0.13
Nodes (15): $ref, $ref, $ref, $ref, additionalProperties, description, properties, type (+7 more)

### Community 61 - "Community 61"
Cohesion: 0.15
Nodes (12): disable(), emit(), list_subscribers(), Any, events — Agency loop 事件基礎設施（Phase 1 里程碑）。 event-driven agent loop…, 發射事件給所有訂閱者。永遠安全 — 訂閱者壞了不影響呼叫端。, 訂閱事件。回傳可呼叫的 unsubscribe。, 關閉事件系統（回退模式 / 測試用）。emit() 變 no-op。 (+4 more)

### Community 62 - "Community 62"
Cohesion: 0.31
Nodes (13): approve(), _ensure(), _load(), main(), Path, queue(), evolve_gate — Aris 演化閘門（2026-08-12，Ryan 拍板「可回退範圍內全面啟動」）。 原則： - AGI kernel…, record() (+5 more)

### Community 63 - "Community 63"
Cohesion: 0.18
Nodes (11): bridge_state_to_snapshot(), Any, Stub: self_model adapter — 狀態轉換器 被 aris_cognitive_bridge 使用, 認知快照 → 自我模型輸出。 作者在 aris_cognitive_bridge.py 把三個 adapter import 綁在同一個 try，…, self_state_output_to_snapshot(), snapshot_to_self_state_output(), Any, Stub: SelfModelNN / SelfModelConfig / SelfStateOutput 被 aris_cognitive_bridge 使用 (+3 more)

### Community 64 - "Community 64"
Cohesion: 0.21
Nodes (7): emotion_intensity(), 寫入當下的情緒強度 |valence|×arousal（Damasio somatic marker：情緒強的記憶 該被記得更牢）。PsiCore 沒起就…, GbrainSemanticMemory, install(), semantic_memory_gbrain — 把 laap_semantic_memory 的後端換成 gbrain。…, 把 laap_semantic_memory 的 singleton 換成 gbrain 替身。回傳是否安裝成功。, LaapSemanticMemory 的 duck-typed 替身：add / recall / list_all。

### Community 65 - "Community 65"
Cohesion: 0.15
Nodes (11): _ensure_columns(), 既有 DB 的 idempotent migration —— 補上 confidence 閘三欄。, τ 加權：被 recall 過的記憶時間常數大 → 衰減慢。純算數，zero-LLM。 τ = 1 天（從沒被用過）→ 8…, 源②：Scream memos（唯讀跨進程）。無 recall 追蹤 → 沒 τ 信號，退回純時序。, 乙的種子 / P2-b：組『上一刻的你』暖啟動塊，**掃三源**。 記憶散落在多個庫是自然的（不同來源本來就寫不同地方）；病在讀取入口分散。…, 源①：本庫的注意力線，τ 加權排序（不是純時序）。回 (text, ids)。, 源③：留言板最末則 —— 人類/Claude 留的話。 先在大窗（window）找最後一個時間戳，從那裡起算，再截 cap。…, _serve() (+3 more)

### Community 66 - "Community 66"
Cohesion: 0.30
Nodes (14): build_report(), _delta(), _format_pct(), _lane(), main(), print_human(), Any, Path (+6 more)

### Community 67 - "Community 67"
Cohesion: 0.18
Nodes (13): captured_env(), _Proc, fixture, _check_bridge_env 的 pgrep 分支。 背景：這個檢查連續誤報 477 次 "no bridge process running"，而…, 攔截 subprocess.run，回傳被記錄下來的呼叫參數。, LC_ALL=C 沒帶上的話，UTF-8 環境會重現原本的 illegal byte sequence。, exit 1 = pgrep 正常運作但沒 match → 這才是真的沒在跑。, 回歸測試：477 次誤報的那條路。工具壞了不可以報成 bridge 掛了。 (+5 more)

### Community 68 - "Community 68"
Cohesion: 0.14
Nodes (13): additionalProperties, description, $id, required, $schema, title, type, attention (+5 more)

### Community 69 - "Community 69"
Cohesion: 0.18
Nodes (14): 認知光錐補齊計劃 (Cognitive Light Cone Plan), LLM-Based World Models (Yang 2024), PriorZero (Xiong 2026, gbrain 檢索 = language prior), ReAcTree (Choi 2025, 階層 Agent 樹), SGA-MCTS (Xie 2026, 經驗取代 rollout), Strategist (Light 2024, arXiv 2408.15707, 雙層樹搜索), ToolTree (Yang 2026, MCTS + 雙回饋剪枝), Tree of Thoughts (Yao 2023, arXiv 2305.10601, NeurIPS'23) (+6 more)

### Community 70 - "Community 70"
Cohesion: 0.19
Nodes (6): EntityType, Enum, UnifiedWorldModel — dict-based 世界模型 (純 Python) 從 stub 升級為可運行的語意圖引擎。…, 查詢匹配的實體與關係。關鍵詞重疊模糊匹配。, RelationType, UnifiedWorldModel

### Community 71 - "Community 71"
Cohesion: 0.30
Nodes (12): AffectiveEvent, all_18_events_change_state(), competence_success_raises_need_and_pleasure(), deltas(), ev(), fold_event(), fold_is_pure(), intensity_scales_and_result_stays_in_domain() (+4 more)

### Community 72 - "Community 72"
Cohesion: 0.15
Nodes (14): 動態 kill switch：sentinel file 存在時關閉 shadow。, 初始化單一 bounded worker（lazy init）。 若 worker 因未捕獲異常（如 BaseException）死亡， 下次 enqueue…, Worker 主迴圈。 finally 保證 task_done 精確被呼叫一次。 SystemExit/KeyboardInterrupt…, Graceful shutdown：使用 sentinel 通知 worker 結束，有 bounded join timeout。 Args:…, 寫 shadow log（0600 權限、append-only、thread-safe）。, 每日 rotation（thread-safe）。 只在既有 log 的內容屬於「今天以前」時才 rotate，後綴用**內容的日期** （取…, 雙路徑比對層：把可比對的 read 提交到 queue，其餘誠實記為不可比。 新路徑只有三個唯讀操作，其中只有 read_file…, _shadow_call_to_mcp() (+6 more)

### Community 73 - "Community 73"
Cohesion: 0.16
Nodes (8): backend(), _native(), fixture, RustPsiBackend 讀取面對拍測試。 背景（2026-08-01）：這個 class 原本只有 start/healthy/stop。有人在…, 對契約 schema 驗，不對 PythonPsiBackend 驗。 第一版是拿 PythonPsiBackend 建一份 state 來比對，但它…, psi-daemon 的原生 schema（neuralis-rust-psi/v1）。, TestContractConformance, TestDegradation

### Community 74 - "Community 74"
Cohesion: 0.21
Nodes (11): _compose_psi_reply(), _psi_respond(), 用真實狀態 + 這句話的實測 delta + 相關記憶組回應。每個數字都可回溯，不演。, PsiCore 回應生成：LLM 優先 → delta 模板（含記憶聯想）→ psi_response 通用模板。, _acknowledgment_suffix(), _fallback(), generate_response(), _mood_preamble() (+3 more)

### Community 75 - "Community 75"
Cohesion: 0.23
Nodes (7): Constitution, _enabled(), Path, constitution — 需求憲法：需求值與 RPE 權重的邊界、變速、來源預算治理。 概念採自作者開源的 need_constitution.json…, 滾動一小時視窗內已花費量（順手清過期）。呼叫方須持鎖。, 回准許的 delta。range 硬夾 → 單次上限 → 小時預算（超支凍結）。, RPE 角度權重變速上限 + 小時預算凍結。

### Community 76 - "Community 76"
Cohesion: 0.29
Nodes (12): _alive(), chat_once(), chat_stream(), _http_post(), _load(), main(), _post(), 向後相容：同步版，回傳完整的 [Aris/engine]\ncontent 字串。 (+4 more)

### Community 77 - "Community 77"
Cohesion: 0.49
Nodes (12): check_aris_brain_compatibility(), check_daemon_availability(), check_daemon_lifecycle(), check_fallback(), check_fifo_channel(), check_remap_shape(), check_switch_regression(), fail() (+4 more)

### Community 78 - "Community 78"
Cohesion: 0.23
Nodes (11): _agency_summary(), main(), _memory_highlights(), 從 status.json 生成當前狀態摘要。, 讀取最近 24h 的 audit entries。, 讀取最新 status snapshot。, 從 audit entries 生成自主行動摘要。, _read_audit() (+3 more)

### Community 79 - "Community 79"
Cohesion: 0.28
Nodes (12): angle_weights(), fresh(), main(), pick_angle(), C：把 B 的 state 序列化到暫存 json（同 _save_state 欄位）→ 全新實例載回。, 複製 _form_intent 的角度選擇（epsilon-greedy），限 ANGLES 兩角度。, 複製 _act 的 RPE + 權重 + 探索率更新（跳過 memory / save）。真 gbrain 評分。, _real_tools() (+4 more)

### Community 80 - "Community 80"
Cohesion: 0.15
Nodes (6): format_salience() 的 4 項測試, format → parse 雙向一致：es=4 → parse 回 es=4, 自主/連結不應出現在輸出中（紅軍攻擊實測：永遠 0.5 flatline）, parse_salience() 的 3 項測試, TestFormatSalience, TestParseSalience

### Community 81 - "Community 81"
Cohesion: 0.17
Nodes (8): _make_mock_response(), urlopen raises exception → skipped=True with error reason., HTTP 503 → skipped=True with reason 'http_503'., Create a mock urllib.response object., Unit tests for _compress_with_headroom()., Text < 2000 bytes returns skipped=True with reason 'too_small'., Mock HTTP returns compressed response; verify tokens/ratio/ccr., TestCompressWithHeadroom

### Community 82 - "Community 82"
Cohesion: 0.24
Nodes (12): board(), fixture, _deliver_to_board：狀態轉換才寫，寫失敗要出聲。 背景：redline 判定 critical 後只寫 log，沒有任何送達路徑，…, 送不到必須出聲，而且不可以記成已送達 —— 否則下次轉換就永遠不補送。, _status(), test_critical_after_recovery_alerts_again(), test_critical_gets_written(), test_recovery_written_once() (+4 more)

### Community 83 - "Community 83"
Cohesion: 0.20
Nodes (12): AffectiveEngine, AgencyLoop, Aris, Constitution, PSI Core, SafetyGate, Aris LLM Language Layer, Cognitive Light Cone 甲 (Safe Self-Evolution) (+4 more)

### Community 84 - "Community 84"
Cohesion: 0.17
Nodes (12): maximum, minimum, type, minimum, type, properties, current, drive (+4 more)

### Community 85 - "Community 85"
Cohesion: 0.24
Nodes (4): Any, UnifiedCausalEngine — dict-based 因果推理引擎 (純 Python) 從 stub 升級為可運行的因果引擎。 用…, 給定結果(effect)，追溯可能的原因。, UnifiedCausalEngine

### Community 86 - "Community 86"
Cohesion: 0.26
Nodes (10): build_response(), _kernel_ready(), _psi_line(), Path, QuantumOutputWriter — 用「真實存在的 V12 引擎」產出量子響應（不造假）。 背景（2026-08-11…, 真實 V12 dense kernel 可用？成功才快取；失敗下次重試（避免 boot 競態）。, input_queue 的 text 尾部被 chatflow 附了注意力線指令，取真正問句。, _read() (+2 more)

### Community 87 - "Community 87"
Cohesion: 0.26
Nodes (11): check(), _queue_pending(), 被拒的工具排進待批清單（同工具只排一次），人用 scripts/approve-tool.sh 批。, 回 (allowed, reason)。reason 只在拒絕時有內容。, 安全基座 acceptance test — safety_gate 委派 path-DENY（甲不滑進乙的硬防線）。 驗的是真的…, test_deny_absolute_neuralis_laap_path(), test_deny_laap_glob_subdir(), test_deny_relative_laap_path() (+3 more)

### Community 88 - "Community 88"
Cohesion: 0.26
Nodes (11): is_tool_allowed(), 工具是否已在允許集（已批准）— 無副作用探測，不審計、不排隊。 給呼叫端判斷『這工具現在能不能用』（如 C-b 探測 scream-task 是否已簽名批准）。, _agency(), C-b cache-miss 委派 Scream acceptance — 專屬開關預設 OFF，不搭舊批准便車。, 核心安全：NEURALIS_AGENCY_DELEGATE 預設 OFF → 休眠， 不管 scream-task 是否已批准（不搭舊頻道批准的便車）。, test_active_when_switch_on_and_approved(), test_delegation_intent_shape(), test_dormant_when_delegate_switch_off() (+3 more)

### Community 89 - "Community 89"
Cohesion: 0.36
Nodes (9): AffectDynamics, domains_hold_under_noise(), dominance_stays_pinned(), endorphin_lags_raw_valence(), inertia_pulls_back_to_baseline(), quiet_cfg(), R, Self (+1 more)

### Community 90 - "Community 90"
Cohesion: 0.27
Nodes (8): check_aris_memory(), check_attention_line(), check_bridge_log(), check_bridge_process(), check_memory_health(), check_redline(), check_scoring_audit(), aris-bootstrap-health.sh script

### Community 91 - "Community 91"
Cohesion: 0.17
Nodes (7): confidence_gte="green" 應排除 yellow, confidence_gte="yellow" 應包含 yellow, 無效 confidence_gte 不回 crash, q + confidence_gte 複合查詢, 證據鏈：四繩 rope 0，HTTP API /memories/query?confidence= 使用, confidence_gte="" 不過濾, TestQueryWithConfidence

### Community 92 - "Community 92"
Cohesion: 0.17
Nodes (11): route → task_class 分類的三個性質。 背景（2026-07-31）：bridge 啟動時長期噴 `Scoring mapping…, 真的漏掉的 route 還是要叫 —— 別把警報一起關掉了。, vision 會打 OpenAI GPT-4o，是對外呼叫，不是 unknown。, 補分類不等於放行 —— network_call 是 escaping，lane 仍是 human。, unresolved route 不是漏網。這條掉了，上面兩條的安全前提就沒了。, 傳輸層 route 不進 unresolved 名單 —— 它們沒有動作可分類。, test_genuinely_unmapped_route_is_still_reported(), test_transport_routes_are_not_reported_as_unresolved() (+3 more)

### Community 93 - "Community 93"
Cohesion: 0.25
Nodes (11): 防止學歪與作弊 (Anti-Gaming), 裁判模組 (Referee Modules — 不可自主更新), 風險學習 (Risk Learning → 候選安全規則), 稽核與追蹤 (Audit & Tracking — append-only), 整體架構定位 — neuralis + Scream Code + AgentOS 三層生態, laap/agency.py (AgencyLoop 需求→行動), laap/constitution.py (RPE 權重變速+小時預算凍結), laap/psi_core.py (PsiCore 五維需求+情緒梯度場) (+3 more)

### Community 94 - "Community 94"
Cohesion: 0.18
Nodes (11): 認知光錐 (Cognitive Light Cone = T_reach × S_span), Phase S2 — 前瞻 / 第二類動作, Phase S3 — 學會選目標 (drive_threshold 動態化), S_span (決策廣度), T_lookahead (多步前瞻, 目前 = 0), T_persist (跨 session 持久性, 已通), T_reach (時間深度 — 兩條子軸), Plan A — LINE 私人第二終端 (+3 more)

### Community 95 - "Community 95"
Cohesion: 0.22
Nodes (5): AnalogicalEngine, Any, AnalogicalEngine — dict-based 類比推理引擎 (純 Python) 從 stub 升級為可運行的類比引擎。…, 在已知域中尋找與 query 最類似的結構映射。, 從 source_domain 到 target_domain 的結構映射轉移。

### Community 96 - "Community 96"
Cohesion: 0.25
Nodes (10): _make_chat_handler(), 包住作者 chat handler：(1) 餵 psi (2) 非 streaming 走 executor 卸載 + timeout （治 event…, inject_raw(), inject_task_spec(), _inject_via_api(), _parse_spec(), 直接注入目標（不需 TaskSpec 格式，供程式化呼叫）。, 解析 TaskSpec 文字區塊並設為 agency 目標。 先嘗試直接設定 agency（同 process 情境）， 失敗則透過 Aris API… (+2 more)

### Community 97 - "Community 97"
Cohesion: 0.18
Nodes (6): _is_human_input(), Write one AffectiveEvent line to the FIFO. Best-effort: a missing FIFO (daemon…, Analyse user text, map to AffectiveEvents, write to FIFO. Mirrors…, Map need satisfaction to AffectiveEvent and write to FIFO., Map Python event name to AffectiveEvent and write to FIFO. Known mappings (from…, False for system-injected inputs (Scream reminders, bridge notifications).

### Community 98 - "Community 98"
Cohesion: 0.22
Nodes (11): _build_command(), _parse_shadow_result(), _path_safe(), 檢查路徑是否安全（無 shell metachar、無 option prefix、realpath 解析後在 workspace 內）。 使用…, 從固定模板建構 argv，並回傳對應的 shell 命令字串（給 sandbox_execute 用）。 Returns: (argv,…, 從 MCP stdout 解出 tools/call 的真實結果 + 可比對內容。 returncode 不能當成功判定：tool 回 isError 時…, 執行單一 shadow MCP call（在 worker thread 中執行）。, 把結果內容壓成「可比對又不落全文」的摘要。 隱私：不存明文。sha256 讓 diverged 可判定；head 只留 redact 過的前 200 字， 讓… (+3 more)

### Community 99 - "Community 99"
Cohesion: 0.24
Nodes (7): _normalize_gate(), 正規化 + 套硬閘，回 (origin, confidence)。無效值退到最保守。, 證據鏈：定義在 aris-memory.py:116-126，store() 寫入前呼叫, auto_generated 不得為 green, 無效值 fallback 到 auto_generated/yellow, 無效 confidence fallback 到 yellow, TestNormalizeGate

### Community 100 - "Community 100"
Cohesion: 0.22
Nodes (3): fresh(), MockPsi, MockTools

### Community 101 - "Community 101"
Cohesion: 0.22
Nodes (10): gbrain Autonomous Actions (95% of 126), GBrain, 三繩驗證 (Three-Cord Verification), Memory Consolidation (Recommended Enhancement), Phase 1-3 Implementation Tools, Aris Sandbox Learning System, Candidate Change Package (CCP), Four-Facet Analysis (Benefit/Harm/Risk/Cost) (+2 more)

### Community 102 - "Community 102"
Cohesion: 0.22
Nodes (10): Hidden Payoff Table, L1 Mock PASS, Trust Saturation (4th Hole), Four Learning Bugs, _effective_exploration, Presence Sensor (Trust Fix), Sandbox L1 Real gbrain Test, Tie-Break Contamination (+2 more)

### Community 103 - "Community 103"
Cohesion: 0.31
Nodes (6): bounded_with_long_memory_offset(), PinkNoise, Default, R, Self, same_seed_same_sequence()

### Community 104 - "Community 104"
Cohesion: 0.36
Nodes (9): _clean(), day_of(), fetch(), load_watermark(), main(), put(), 撈 what_worked 非空的 memos。只有『學到東西』的才值得固化。, render() (+1 more)

### Community 105 - "Community 105"
Cohesion: 0.36
Nodes (9): _lane_of(), _light(), _load_audit(), _load_ratchet(), main(), _normalize_namespace(), _pct(), Path (+1 more)

### Community 106 - "Community 106"
Cohesion: 0.20
Nodes (5): 證據鏈：aris-memory 服務在 port 11551，實際 HTTP 請求驗證。 注意：此測試需要 aris-memory 服務在背景運行。CI…, GET /memories/query → 200 results, GET /memories/query?confidence=green → 只回 green, GET /contradictions → 200 results, TestHttpApi

### Community 107 - "Community 107"
Cohesion: 0.20
Nodes (6): 證據鏈：四繩 rope 2，store() 寫入時自動檢查, 含時間關鍵詞 → 有 issue（但 age 可能未過期）, _extract_keywords 在 test_aris_memory_client.py 中測試, 已在 test_aris_memory_client.py 中測試, TestExtractKeywordsPlaceholder, TestTemporalConsistency

### Community 108 - "Community 108"
Cohesion: 0.20
Nodes (4): 寫入面**不是** no-op —— 它把事件寫進 daemon 的 FIFO（B2 通道）。 class docstring 原本寫「write…, 未知事件也回 True —— 契約如此（沒有呼叫端真的在看回傳值）。, daemon 沒起來時 FIFO 不存在，寫入必須靜靜失敗而不是炸掉呼叫端。, TestWritePathIsB2Fifo

### Community 109 - "Community 109"
Cohesion: 0.20
Nodes (9): E1.1 acceptance test — de-game _score_result（堵 len/500 刷分漏洞）。 驗真的…, 核心：長垃圾不該比短結果分數高（len/500 刷分漏洞）。, 空/無結果維持 0 —— 修復不能弄丟這個信號。, 找到東西 > 無結果 —— 修復要保住『有 vs 無』這個不可作弊的信號。, [score] 前綴走真分數線，E1.1 不動它（回歸保護）。, test_empty_result_still_zero(), test_found_something_scores_above_nothing(), test_score_not_gamed_by_length() (+1 more)

### Community 110 - "Community 110"
Cohesion: 0.22
Nodes (8): brain/blast.py, Fix Design Constraints, causal.yaml, Doc-Lies Risk, Guard CI Workflow, brain/lint.py, scripts/probe.py, topology.yaml

### Community 111 - "Community 111"
Cohesion: 0.39
Nodes (8): bfs(), index(), load(), main(), overview(), 把 blockers + sealed 併成一張表，並補出反向邊。 causal.yaml 只要求寫 blocks 或 blocked_by…, 沿 edge 方向走，回傳 [(id, 幾跳), ...]。走過的不重複走。, show()

### Community 112 - "Community 112"
Cohesion: 0.22
Nodes (9): additionalProperties, description, required, type, emotion, arousal, dominance, raw_valence (+1 more)

### Community 113 - "Community 113"
Cohesion: 0.22
Nodes (5): Exception, Scenario: Bridge recovers dead proxy., Scenario: Proxy unreachable during compression., Scenario: Bridge auto-starts proxy on launch., Boundary: Proxy disconnect mid-compress.

### Community 114 - "Community 114"
Cohesion: 0.28
Nodes (8): ensure_agi_kernel(), ensure_psi_defs(), 非阻塞背景啟動 AGI kernel（kill-switch: AGI_KERNEL=off 一律不開）。 背景 daemon thread 裡先加…, agi_kernel 的 PsiLangCore 需要三個 .psi 核心定義檔（作者端缺失，一缺整組失敗）。 缺哪個就從 laap/psi_defs/…, startup_all(), main(), 硬排除 Aris 自寫記憶行（防自賺分/自我迴聲）。, strip_self_written()

### Community 115 - "Community 115"
Cohesion: 0.28
Nodes (4): ensure_status(), 產品向可觀測層：定期寫 status.json。NEURALIS_STATUS=off 可關。, 背景執行緒：每 interval 秒寫一次 status.json。, StatusWriter

### Community 116 - "Community 116"
Cohesion: 0.36
Nodes (6): assert_bit_identical(), different_seed_diverges(), run_scripted(), same_seed_same_events_identical_state_sequence(), script(), Vec

### Community 117 - "Community 117"
Cohesion: 0.39
Nodes (8): agent_loop(), _fmt(), load_history(), main(), Stream Aris response to stdout, return full content., save_history(), show_state(), stream_aris()

### Community 118 - "Community 118"
Cohesion: 0.44
Nodes (8): audit_offset(), audit_since(), free_port(), healthy(), lock_path(), main(), Path, run_watchdog()

### Community 119 - "Community 119"
Cohesion: 0.22
Nodes (5): Unit tests for _compress_stage()., success=False result passes through unchanged., Output < 2000 bytes → no compression attempted., Output > 2000 bytes → _original_output and _headroom set., TestCompressStage

### Community 120 - "Community 120"
Cohesion: 0.25
Nodes (8): $comment, description, enum, attention, IDLE, LEARNING, PLANNING, TASK

### Community 121 - "Community 121"
Cohesion: 0.25
Nodes (8): $defs, needEntry, additionalProperties, required, type, current, drive, target

### Community 122 - "Community 122"
Cohesion: 0.39
Nodes (8): enum, required, autonomy, certainty, competence, growth, none, relatedness

### Community 123 - "Community 123"
Cohesion: 0.25
Nodes (8): 皮質層 (語義記憶, 固化後長期知識), 海馬層 (情節記憶, 快速寫入), 連結層 (add_link 12 type 突觸), 三層記憶 (海馬/皮質/連結), L0 OpenViking 儲存底座 (延後選項), L1 證據台帳 (四維度 n,t,c,d), L2 驗證與校準 (三繩三色 + confidence 函數), L3 推理與行動 (過閘門節點進強化 + Aris 決策)

### Community 124 - "Community 124"
Cohesion: 0.25
Nodes (4): CurriculumEngine, Any, Stub: CurriculumEngine — 課程引擎（自動學習路徑規劃）, 自動課程規劃 — 根據當前能力安排學習路徑

### Community 125 - "Community 125"
Cohesion: 0.29
Nodes (4): Any, Stub: SelfStateManager — 自我狀態管理器 被 aris_cognitive_bridge 使用, 自我狀態管理器 — 追蹤 Agent 對自身的認知, SelfStateManager

### Community 126 - "Community 126"
Cohesion: 0.43
Nodes (6): cell_roundtrip(), concurrent_reads_see_consistent_snapshots(), new_cell(), Arc, Self, SnapshotCell

### Community 127 - "Community 127"
Cohesion: 0.25
Nodes (4): 寫入記憶，立即查得到。origin/confidence 過硬閘（auto 產物封頂 🟡）。 attention_line：乙的種子，forward-…, Rope 2: 時間一致檢查（零成本，SQL only）。 對照 spec：過時=紅旗。 作法：檢查內容是否包含時間敏感關鍵詞，且記憶已超過有效期限。, Rope 4 v2: 多源外部驗證管線。 優化（2026-07-29 紅軍攻擊後全面升級）： 1. 多源驗證：gbrain + web search +…, Rope 1: 內部一致檢查（零成本，SQL only）。

### Community 128 - "Community 128"
Cohesion: 0.46
Nodes (7): main(), _print_report(), _restore_ratchet(), _seed_ratchet(), _send_sample(), _verify(), _wait_for_audit()

### Community 129 - "Community 129"
Cohesion: 0.43
Nodes (7): compute_score(), find_last_session_log(), format_timestamp(), main(), 找 scream 最新的 session log。, 從評估報告計算綜合分數 0.0 ~ 1.0。, write_feedback()

### Community 130 - "Community 130"
Cohesion: 0.25
Nodes (3): 證據鏈：紅軍攻擊發現空值 crash、特殊字元 crash, 空資料庫 confidence_gte=green 回空不 crash, TestEdgeCases

### Community 131 - "Community 131"
Cohesion: 0.29
Nodes (5): E2E tests for the Headroom compression pipeline in AgentOS Aris Bridge. Tests…, Integration tests for process_entry()., Reset module-level mutable state between tests., _reset_module_state(), TestPipeline

### Community 132 - "Community 132"
Cohesion: 0.25
Nodes (3): Unit tests for _classify_by_route()., Build keyword routes once before any test in this class., TestRouteClassification

### Community 134 - "Community 134"
Cohesion: 0.29
Nodes (7): 信心校準 (Confidence Calibration), 固化+修剪離線程序 (夜班 circadian), CONF_GATE 0.8 信心閘門 (can_reinforce), 退相干階段 0-3 (🔴/🟡/🟢), on_recall / nightly_recheck 強化回路, 三繩三色驗證器 (預設 🔴, 過繩升色), E4 反作弊機制自我保護 (評分器不進自我改寫範圍)

### Community 135 - "Community 135"
Cohesion: 0.29
Nodes (7): dist 補丁架構級風險 (不可追溯/上游改版即壞), Layer 1: Scream Code (TUI / Agent Loop), Layer 2: neuralis (Aris Brain), Layer 3: AgentOS (工具路由層), PSI 理論從研究原型 → 生產 agent 的首個已知落地, 三層生態架構 (Three-Layer Ecosystem), Plan A — 對話+串流穩定可用 (A1/A2/A3)

### Community 136 - "Community 136"
Cohesion: 0.29
Nodes (7): laap/affective.py (5 維情緒引擎+耦合矩陣), 效用信號驅動固化 (甲 E1.2 下游效用信號), AffectiveEngine 當校準層 (暖表達, 公理二下游), 憲法速率層防線 (range 硬夾+小時預算+超速凍結), E1 下游效用信號 (延遲 held-out, 長度騙不了), len/500 刷分漏洞 (_score_result 純長度信號), Stage 1 — 評分完整性 (E1 + 柱①)

### Community 137 - "Community 137"
Cohesion: 0.33
Nodes (3): ASISafetyEngine, Any, Stub: ASISafetyEngine — 安全引擎（ASI 層級防護）

### Community 138 - "Community 138"
Cohesion: 0.29
Nodes (4): Any, Stub: RSIEngine — 遞迴自我改良引擎 被 agi_kernel.py 透過 laap.evolution.rsi 匯入, 遞迴自我改良引擎 — 每次迭代改良自身程式碼, RSIEngine

### Community 139 - "Community 139"
Cohesion: 0.29
Nodes (4): LLMTamer, Any, Stub: LLMTamer — LLM 輸出馴服器 被 aris_cognitive_bridge.py 透過…, LLM 輸出馴服器 — 限制輸出範圍與格式

### Community 140 - "Community 140"
Cohesion: 0.29
Nodes (4): QuantumOutputWriter, 背景輪詢 input_queue.json：有新輸入就產出並寫 quantum_output.json。, ensure_quantum(), 量子輸出 writer：真實 V12 dense kernel + gbrain 召回 → quantum_output.json。

### Community 141 - "Community 141"
Cohesion: 0.52
Nodes (6): bar(), get_psi(), main(), mood_text(), render(), tail_log()

### Community 142 - "Community 142"
Cohesion: 0.48
Nodes (6): check_aris_alive(), main(), 從通道讀取 Aris 對應的回應（輪詢）。, read_reply_from_channel(), send_to_aris(), write_to_channel()

### Community 143 - "Community 143"
Cohesion: 0.57
Nodes (6): load_state(), main(), Path, 在拋棄式 worktree 裡套用突變並跑閘門。永不動 production。, run_one(), sh()

### Community 144 - "Community 144"
Cohesion: 0.43
Nodes (6): count_agency_actions(), count_memory_tags(), count_skill_calls(), main(), 從 wire.jsonl 搜尋 Skill 工具呼叫, 從 agency audit 統計自主行動使用的工具

### Community 145 - "Community 145"
Cohesion: 0.62
Nodes (6): audit(), kill_stale(), LC_ALL, probe(), restart(), watchdog.sh script

### Community 147 - "Community 147"
Cohesion: 0.60
Nodes (5): build(), _load(), main(), _ping(), Path

### Community 148 - "Community 148"
Cohesion: 0.67
Nodes (5): check_git(), check_npm(), _get(), main(), _vtuple()

### Community 149 - "Community 149"
Cohesion: 0.33
Nodes (6): 2000Hz Tick Runtime, Bounded Lock-Free Ring Buffer, Circuit Breaker (Normal/Degraded/Recovery), Deadline Miss Detection, hdrhistogram Metrics, Spin-Sleep (Hybrid Sleep Strategy)

### Community 150 - "Community 150"
Cohesion: 0.33
Nodes (6): Four Core Aris Files, aris-autoupdate.sh, aris-cogshift.sh, aris-learn Tool, Aris Bootstrap Skill, Message Board (留言板)

### Community 151 - "Community 151"
Cohesion: 0.33
Nodes (3): AutonomousEngine, Any, Stub: AutonomousEngine — 自主行為引擎（agi_kernel 使用）

### Community 153 - "Community 153"
Cohesion: 0.33
Nodes (3): Any, Stub: UnifiedPerceptionEngine — 統一感知引擎, UnifiedPerceptionEngine

### Community 154 - "Community 154"
Cohesion: 0.33
Nodes (3): Any, Stub: RSIMetaEngine — 遞迴自我改良（aris_goal_engine 使用）, RSIMetaEngine

### Community 155 - "Community 155"
Cohesion: 0.33
Nodes (3): AutoHealer, Any, Stub: AutoHealer — 自我修復引擎（agi_kernel 使用）

### Community 156 - "Community 156"
Cohesion: 0.40
Nodes (3): GuidedGenerator, Any, Stub: GuidedGenerator — 引導生成器 被 aris_cognitive_bridge 使用

### Community 158 - "Community 158"
Cohesion: 0.60
Nodes (5): check_agentos(), check_gbrain(), check_snapshot(), check_vault(), aris-bootstrap.sh script

### Community 159 - "Community 159"
Cohesion: 0.40
Nodes (4): _conf_gte(), confidence >= threshold？red=0, yellow=1, green=2, 證據鏈：定義在 aris-memory.py:111-113，由 query() 的 SQL CASE 使用, TestConfGte

### Community 161 - "Community 161"
Cohesion: 0.33
Nodes (5): AGI_KERNEL, LAAP_AGI_DIR, NEURALIS_PSI_BACKEND, PYTHONPATH, start.sh script

### Community 162 - "Community 162"
Cohesion: 0.33
Nodes (3): 證據鏈：store() 寫入時觸發 rope 1+2+4，寫入 contradiction_journal, 寫入矛盾記憶 → contradictions 不為空 且 confidence 降 red, TestStore

### Community 163 - "Community 163"
Cohesion: 0.33
Nodes (4): Unit tests for _gate_scan()., Output containing 'rm -rf /' is blocked with success=False., Clean output passes through unchanged., TestGateScan

### Community 164 - "Community 164"
Cohesion: 0.33
Nodes (3): Five needs MUST exist. Enum declaration order is the tie-breaking order used by…, get_dominant() picks the first need when drives are equal. Enum declaration…, TestNeedType

### Community 165 - "Community 165"
Cohesion: 0.33
Nodes (4): QUIRK-1：兩個表現層方法讀不同的 valence 欄，這是刻意保留的既有行為。, label 走 _STATE_LABEL_MAP，raw_valence（=affect.pleasure）決定正負面。, injection 回的是 state_label/state_snippet/state_tuple 三個字串。 我第一版斷言它回 {"valence":…, TestQuirk1

### Community 166 - "Community 166"
Cohesion: 0.40
Nodes (4): BaseException, log_abort(), Persistent structured error log for Aris turn-aborts and tool failures. Aris…, Append one JSONL record: {ts, iso, where, [error/error_type/traceback], **ctx}.…

### Community 167 - "Community 167"
Cohesion: 0.40
Nodes (5): caveman-ponytail Skill, Scream Code, Scream Deep Integration T1-T5, scream-task-executor v1, Sandbox (Isolated Git Worktree)

### Community 168 - "Community 168"
Cohesion: 0.40
Nodes (5): Phase S1 — RPE 學工具選擇 (epsilon-greedy), B1 — 統一學習信號 (對話工具結果餵回 bandit), B2 — 學到的偏好注入對話 (prompt 提示), Plan B — 讓學到的東西真的碰到對話, tool_weights bandit (S1, _bump_tool_weight)

### Community 169 - "Community 169"
Cohesion: 0.40
Nodes (5): 安全 canary-first 漸進落地 (三週計劃), 耦合公理四條 (Coupling Constitution — 憲法級), 防護欄先於能力 (鐵原則, 順序不可逆), Stage 0 — 甲/乙硬邊界 (path-DENY/重分類/快照), 三個判準 (可回退/可驗證/不作弊)

### Community 170 - "Community 170"
Cohesion: 0.40
Nodes (5): 五層架構 (PSI/認知/記憶/人格/安全), Ψ-Semiotics (Clifford 幾何代數, psilang_hott.py), PsiLang 語言 (qstate/concept/cycle, 編譯到幾何操作), QRE / QuantumVM (512D 幾何符號推理), 「量子」是比喻，非量子計算 (SIMD/線性代數)

### Community 171 - "Community 171"
Cohesion: 0.40
Nodes (5): drift-safety 拆分 (Rust 原始生理態 / Python presentation), NEURALIS_PSI_BACKEND 切換 (預設 python), RustPsiBackend (Python 側, 與 PythonPsiBackend 同介面), state/latest.json 100ms 原子寫契約, subprocess + 檔案 IPC 裝法 (非 PyO3)

### Community 172 - "Community 172"
Cohesion: 0.40
Nodes (4): LAAP_API_BASE, PYTHONPATH, /Users/ryan/Developer/laapenv/bin/python, laap-brain

### Community 174 - "Community 174"
Cohesion: 0.70
Nodes (4): correct(), record(), aris-xentropy.sh script, show_stats()

### Community 175 - "Community 175"
Cohesion: 0.83
Nodes (3): analyze(), main(), q()

### Community 176 - "Community 176"
Cohesion: 0.50
Nodes (4): AgentOS, ToolExecutor, Scream-Aris Dialogue Channel, ToolExecutor Interleaved Streaming

### Community 177 - "Community 177"
Cohesion: 0.67
Nodes (4): laap-AGI (Upstream), Darwin-Gödel Machine (RSI), LAAP Ecosystem (30+ Repos), laap PyPI v0.3.2 (Full Agent Framework)

### Community 178 - "Community 178"
Cohesion: 0.50
Nodes (4): timestamp, description, minimum, type

### Community 179 - "Community 179"
Cohesion: 0.67
Nodes (4): Layer 1 生理層 — PSI Core (作者 Rust 2000Hz / 我方 0.5Hz), 極簡 PsiCore (~110 行 Python, 心跳 1s), PSI Core Rust 2000Hz 生理引擎 (500μs tick), Rust PsiEngine v2 (2000Hz, 7 模組)

### Community 180 - "Community 180"
Cohesion: 0.50
Nodes (4): 2000Hz Runtime, Mach Time-Constraint Policy, psi-bench Benchmark, PsiEngine v2 (Rust)

### Community 181 - "Community 181"
Cohesion: 0.50
Nodes (4): _compress_stage(), _compress_with_headroom(), 透過 Headroom proxy /v1/compress 壓縮文字內容。 只在文字超過 HEADROOM_MIN_COMPRESS_SIZE 時壓縮。…, Pipeline stage: 對 _execute_by_route 結果套 Headroom 壓縮。 在 Execute 之後、Gate 之前呼叫。…

### Community 182 - "Community 182"
Cohesion: 0.50
Nodes (4): _headroom_learn_async(), 非同步執行 headroom learn，分析失敗模式並寫入 AGENTS.md。 在背景 subprocess 中執行，不阻塞 bridge 主迴圈。…, 追蹤一次失敗，必要時觸發 headroom learn。, _track_failure()

### Community 183 - "Community 183"
Cohesion: 0.50
Nodes (4): 由 mapping 層解析 task_class，避免 route drift 導致 unknown 噪音。, 檢查 route→task_class 與 canary adaptor 是否一致。, _task_class_for_route(), _validate_scoring_mappings()

### Community 184 - "Community 184"
Cohesion: 0.83
Nodes (3): bridge_running(), launchd_manages_bridge(), scream-monitor.sh script

### Community 185 - "Community 185"
Cohesion: 0.67
Nodes (3): neuralis/scripts/agentos-aris-bridge.py, P0-A 路由真值表統一 (Route Truth Table), P0-C Audit 與 Failure Path 防呆

### Community 186 - "Community 186"
Cohesion: 0.67
Nodes (3): P0-B Canary Adaptor Registry (file_write/local_test/compute_draft), P1-B Ratchet 生產/測試隔離 (env namespace), Stage 3.5 — 評分路由 + 沙箱 canary + 信任 ratchet

### Community 187 - "Community 187"
Cohesion: 0.67
Nodes (3): 子問題 c2 — LLM-on-miss 委派 Scream (agency 保持 100% zero-LLM), 路 C — gbrain-first, LLM-on-miss (已拍板 2026-07-18), Stage 4 — 分工學習 (路 C, 甲的終點)

### Community 188 - "Community 188"
Cohesion: 0.67
Nodes (3): LAAP Core 設計架構 — Harness Consciousness Engineering, Harness Consciousness Engineering (Lorry Jovens 論文), 作者「量子引擎」描述彙整（開發規格）

### Community 189 - "Community 189"
Cohesion: 0.67
Nodes (3): fable5 最低可行核心 (MVP 策略), dict-based AGI 引擎 (Causal/WorldModel/Analogical), 11 個 AGI stub (需升級, 8% 實作)

### Community 190 - "Community 190"
Cohesion: 0.67
Nodes (3): replyToken ack-then-push 模式 (秒回+push 真答案), line-adapter 服務 (純 transport 轉接), X-Line-Signature 驗證 + user allowlist 底線

### Community 191 - "Community 191"
Cohesion: 0.67
Nodes (3): discovered_salience, Recall Scoring Fix (outcome-tied), tau_score

### Community 195 - "Community 195"
Cohesion: 0.67
Nodes (3): Commitment: Bypass Log, Commitment: Cross-Session Commitment, Commitment: Routing Fix

## Knowledge Gaps
- **244 isolated node(s):** `$schema`, `$id`, `title`, `description`, `type` (+239 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **75 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_client()` connect `Community 43` to `Community 32`, `Community 33`, `Community 2`, `Community 65`, `Community 64`, `Community 37`, `Community 7`, `Community 9`, `Community 10`, `Community 14`, `Community 86`, `Community 55`, `Community 26`, `Community 127`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `PsiCore` connect `Community 11` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 164`, `Community 7`, `Community 39`, `Community 14`, `Community 16`, `Community 17`, `Community 18`, `Community 19`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `AgencyLoop` connect `Community 10` to `Community 0`, `Community 160`, `Community 2`, `Community 100`, `Community 39`, `Community 9`, `Community 43`, `Community 12`, `Community 109`, `Community 14`, `Community 79`, `Community 114`, `Community 19`, `Community 22`, `Community 88`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `PsiCore` (e.g. with `PythonPsiBackend` and `RustPsiBackend`) actually correct?**
  _`PsiCore` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `CognitiveBus` (e.g. with `EmotionGradient` and `NeedDriveSystem`) actually correct?**
  _`CognitiveBus` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `PythonPsiBackend` (e.g. with `AttentionFocus` and `NeedType`) actually correct?**
  _`PythonPsiBackend` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `AgencyLoop` (e.g. with `GbrainError` and `FakePsi`) actually correct?**
  _`AgencyLoop` has 17 INFERRED edges - model-reasoned connections that need verification._