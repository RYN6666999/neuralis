# Borrowing Matrix — Neuralis PsiBackend v2

| Field | Value |
|-------|-------|
| **BASE_SHA** | `ab14499ec1d5f30e84b85c56e6c780c7eb4d6913` |
| **Date** | 2026-07-15 |
| **Branch** | `task-007b-psi-borrowing-analysis` |
| **Author** | Wolf 8 (Document Writer) — synthesis of Wolf 1–7 research |

## Overview — External Sources

| # | Source | Repository | SHA | License | Evidence Level | Domain |
|---|--------|-----------|-----|---------|----------------|--------|
| S1 | Neuralis PsiBackend v1 | `github.com/RYN6666999/neuralis` | `ab14499ec` | MIT | E0 | Current state |
| S2 | MicroPsi2 | `github.com/joschabach/micropsi2` | `74a2642d` | MIT | E0 | PSI theory reference implementation |
| S3 | Synthetic Emotion Controller | `github.com/affect-based-control/synthetic-emotion-controller` | `b089d464` | MIT | E0 | Affective drive + policy |
| S4 | autonomic (broomva) | `github.com/broomva/autonomic` | `a7684e1a` | MIT | E0 | Event sourcing, hysteresis, gating |
| S5 | autonomic (broomva) — life | `github.com/broomva/autonomic` | `a7684e1a` | MIT | E0 | Homeostatic state, economic mode, projection |
| S6 | pymdp | `github.com/infer-actively/pymdp` | `dec6c83d` | MIT | E0 | Active inference primitives |
| S7 | OpenCog OpenPsi | `github.com/opencog/opencog` | `ae68bda7` | AGPL v3 + linking exception | E0 | PSI theory reference (concepts only) |
| S8 | spin-sleep | `github.com/alexheretic/spin-sleep` | `38b0799` | Apache-2.0 | E0 | Spin-based sleep at 125µs granularity (DEFAULT_NATIVE_SLEEP_ACCURACY=125_000 ns, lib.rs L78) |
| S9 | ExoGenesis-Omega | `github.com/prancer-io/ExoGenesis-Omega` | Repo exists | null (API license=null) | REFERENCE | Rust loop architecture reference |

**Evidence levels**: E0 = source code, E1 = author documentation, E2 = indirect, I = inference, D = Neuralis design decision.

## Full Borrowing Matrix

### Need Dynamics

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Need deficit (OU process) | 5 needs: CERTAINTY, COMPETENCE, AUTONOMY, RELATEDNESS, GROWTH | D — Neuralis design (standard OU mathematics) | E0 — `laap/psi_core.py` L105-146 (targets, baselines, volatilities) | Standard OU: `d = target - baseline` (not n_◇ - n). Drive = `max(0, target - current)`. | MIT | ADAPT | OU process is Neuralis design (D). Standard Ornstein-Uhlenbeck mathematics. MicroPsi2 uses 3 physiological needs — not the source of OU. Neuralis needs are 5 psychological. | Low — formula is domain-agnostic | ADAPT |
| Need decay | All 5 needs | S2 (MicroPsi2) — COMPETENCE_DECAY_FACTOR=0.1 | E0 — `micropsi_core/nodenet/stepoperators.py` L117-118 | `competence *= (1 - COMPETENCE_DECAY_FACTOR)` | MIT | ADAPT | Neuralis needs decay toward baseline (not zero). OU process drift is the decay mechanism. | Low | ADAPT |
| Need satisfaction (satisfy) | All 5 needs | S1 (Neuralis v1) — `satisfy()` method | E0 — `laap/psi_core.py` L171-177 | `max(0.0, min(1.0, v + allowed))` with constitution guard | MIT | ADOPT | `satisfy()` at psi_core.py L171-177: amount goes through `get_constitution().guard_need()` first, then `max(0.0, min(1.0, v + allowed))`. | None | ADOPT |
| Drive formula | All 5 needs | S1 (Neuralis v1) — `compute_drive()` | E0 — `laap/psi_core.py` L198-201 | `max(0, target - current) * importance` | MIT | ADOPT | No change needed. | None | ADOPT |
| Importance weighting | All 5 needs (CERTAINTY=1.2, COMPETENCE=1.5, AUTONOMY=1.0, RELATEDNESS=0.8, GROWTH=1.3) | S1 (Neuralis v1) | E0 — `laap/psi_core.py` L130-136 | Drive = deficit × importance | MIT | ADOPT | No change needed. | None | ADOPT |
| Serotonin modulation | Need decay rate | D — Neuralis design | D — `laap/psi_core.py` L149-169 (tick + serotonin) | v1 is step function: `valence>0.3 → decay×0.7, valence<-0.3 → decay×1.3` (0.3 factor is uncalibrated) | N/A | ADOPT | New design element. Serotonin slows need decay. Note: v1 uses step function, not continuous. 0.3 factor is uncalibrated. | Low — needs calibration | ADOPT |
| Urgent accumulation | Urgency as temporal integral of deficit | S7 (OpenPsi) — urge concept | E0 — `opencog/openpsi/demand.scm`, `opencog/openpsi/dynamics/` | urge formula: I (insufficient evidence) | AGPL v3 | ADAPT | Use concept only (no AGPL code). Implement as leaky integrator: `u(t+1) = α·u(t) + deficit(t)`. | Medium — AGPL abstraction boundary | ADAPT |

### Affect Dynamics

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Valence (2-channel) | Emotion | S1 (Neuralis v1) — raw + endorphin slow-release | E0 — `laap/psi_core.py` L44, L50-69 | `valence_raw ∈ [-1,1]`, endorphin: 上升100%跟隨, 下跌僅+delta×0.3 (非對稱, psi_core.py L64-71) | MIT | ADOPT | Compatibility Mode: v1 非對稱更新。對稱 EMA 是 D (Future/Enhanced Mode). | None | ADOPT |
| Arousal | Emotion | S1 (Neuralis v1) | E0 — `laap/psi_core.py` L45 | `arousal ∈ [0,1]` | MIT | ADOPT | No change needed. | None | ADOPT |
| Dominance | Emotion | S1 (Neuralis v1) — EmotionGradient(D=0.5 fixed) | E0 — `laap/psi_core.py` L46 (EmotionGradient fixed D=0.5) vs `laap/affective.py` L36 (AffectiveState dynamic, baseline 0.3) | `dominance = 0.5` (fixed in EmotionGradient). AffectiveState uses dynamic dominance with baseline 0.3. | MIT | ADOPT | EmotionGradient D=0.5 fixed (psi_core L46). AffectiveState D dynamic baseline 0.3 (affective.py L36). v2 fixed D mark as D. | None | ADOPT |
| 5D PAD+Social+Stress | Emotion | S1 (Neuralis v1) | E0 — `laap/affective.py` L43-62 (event map), L70-88 (state+matrix) | 5D vector: P, A, D, S, St | MIT | ADOPT | No change needed. | None | ADOPT |
| Coupling matrix (8 non-zero terms) | Emotion | S1 (Neuralis v1) | E0 — `laap/affective.py` L77-88 (8 non-zero coupling terms) | 5×5 matrix, 8 non-zero coupling terms (affective.py L80-88) | MIT | ADOPT | v1 has 8 non-zero terms. If v2 topology is different, mark as D. | None | ADOPT |
| 1/f noise | Affect noise | S1 (Neuralis v1) | E0 — `laap/affective.py` L97-108 | Pink noise generator | MIT | ADOPT | No change needed. | None | ADOPT |
| Pleasure | Emotional modulator | S2 (MicroPsi2) — `calculate()` | E0 — `micropsi_core/nodenet/stepoperators.py` L140-173 | `gentle_sigmoid((expected-unexpected)/10) + gentle_sigmoid(urge_change×-3)` | MIT | ADAPT | MicroPsi2 scales pleasure for physiological needs. Neuralis will recompute from relative need deficit change. | Low — formula is domain-agnostic | ADAPT |
| Sustaining joy | Emotional modulator | S2 (MicroPsi2) — JOY_DECAY_FACTOR=0.01 | E0 — `micropsi_core/nodenet/stepoperators.py` L140-173 | `joy = same-sign(pleasure) + copysign(JOY_DECAY, joy)` (decay, not EMA) | MIT | ADAPT | Same-sign + copysign decay, NOT EMA. Use as inertia on emotional state. | Low | ADAPT |
| Emotional inertia | Affect dampening | S2 (MicroPsi2) — sustaining joy concept | E0 — same as above | Emotional state changes are smoothed by joy decay factor | MIT | ADAPT | Apply inertia to all 5D affect dimensions. | Low | ADAPT |
| Activation | Attention/arousal correlate | S2 (MicroPsi2) — `activation()` | E0 — `micropsi_core/nodenet/stepoperators.py` L140-173 | `(Σimportance+Σurgency)/((motives*2)+1) + urge_change` | MIT | ADAPT | Neuralis arousal replaces this. Formula not directly applicable. | Low | ADAPT |
| Competence modulation | COMPETENCE need | S2 (MicroPsi2) — `competence()` | E0 — `micropsi_core/nodenet/stepoperators.py` L117-118 | `competence *= (1 - COMPETENCE_DECAY_FACTOR)` (0.1/0.01) | MIT | ADAPT | Neuralis already has COMPETENCE as a need. The MicroPsi2 decay formula informs the OU process parameters. | Low | ADAPT |
| Unexpectedness | Prediction error for attention | S2 (MicroPsi2) — `unexpectedness()` | E0 — `micropsi_core/nodenet/stepoperators.py` L140-173 | sigmoid cumulative function | MIT | ADAPT | Same formula concept. Input to attention salience. | Low | ADAPT |
| Securing rate | Behavioral confidence | S2 (MicroPsi2) — `securing_rate()` | E0 — `micropsi_core/nodenet/stepoperators.py` L140-173 | `(1-competence)-0.5·urgency·importance+fear+unexpectedness` | MIT | ADAPT | Use as cognitive confidence metric. Not a need. | Low | ADAPT |
| Resolution | Goal achievement satisfaction | S2 (MicroPsi2) — `resolution()` | E0 — `micropsi_core/nodenet/stepoperators.py` L140-173 | `=1-activation` | MIT | ADAPT | Same formula concept. | Low | ADAPT |
| Selection threshold | Motive competition | S2 (MicroPsi2) — `selection_threshold()` | E0 — `micropsi_core/nodenet/stepoperators.py` L140-173 | `=activation` | MIT | ADAPT | Not directly applicable to Neuralis. Neuralis uses drive-based competition. | Low | ADAPT |

### Synthetic Emotion Controller (SEC) Components

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Per-dimension deficit | Any need | S3 — SEC `calculate_d` | E0 — `affect_memory_demo.py` L123-150 (A1-A8) | `d = tanh(α ⊙ (n◇ − n))` | MIT | ADAPT | Neuralis already uses linear deficit. SEC tanh gives bounded [-1,1] per dimension. Optional replacement for drive computation. | Medium — changes drive perception curve | ADAPT |
| Canonical state z = [v, m, a, d] | Affect state | S3 — SEC state vector | E0 — `affect_memory_demo.py` L441 (z) | `z = [v, m, a, d]` where v = -d, m = |d|, a = clip(base + scale·mean(m), 0, 1) | MIT | ADAPT | Neuralis 5D PAD+Social+Stress is richer. SEC canonical state is a projection. Useful as a compressed representation for policy routing. | Low | ADAPT |
| H-matrix | Policy encoding | S3 — SEC `h = H @ x` | E0 — `affect_memory_demo.py` L395 (tanh) | `h = H @ x` where H is row-L1 normalized | MIT | ADAPT | Use as inspiration for Neuralis policy shaping. Not a direct adoption. | Low | ADAPT |
| Arousal-dependent temperature | Policy stochasticity | S3 — SEC `τ₁(a)` | E0 — `affect_memory_demo.py` L454-461 (τ) | `softmax(h_t / τ₁(a))` where τ is inverse function of arousal | MIT | ADAPT | Useful for balancing exploration-exploitation in action selection. | Low | ADAPT |
| Credit assignment | Post-hoc selection justification | S3 — SEC `argmax_π[q(π) × s̃_π(u_t)]` | E0 — `affect_memory_demo.py` L476 (k-NN) | `argmax_π[q(π) × s̃_π(u_t)]` | MIT | ADAPT | Not for 2000Hz loop. Use in cognitive loop (10Hz). | Low | ADAPT |
| 3 success modes | Drive/emotion/hybrid | S3 — SEC success evaluation | E0 — `affect_memory_demo.py` (A1-A8 context) | Mode comparison: drive-reduction vs emotion-target vs hybrid | MIT | ADAPT | Useful for evaluating action outcomes in cognitive loop. | Low | ADAPT |
| Graceful degradation | Missing subsystems | S3 — SEC flocking without memory | E0 — `flock_no_memory.py` (A3/A7/A8) | Skip A3/A7/A8 when memory unavailable | MIT | ADOPT | Same pattern: degrade gracefully when subsystems unavailable. | None | ADOPT |

### Event Sourcing & Hysteresis

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| AutonomicEvent → EventReducer | Event pipeline | S4 (autonomic) — `AutonomicEvent` | E0 — `autonomic-core/src/events.rs` L19 | Event struct with type + payload + timestamp | MIT | ADAPT | Rename to Neuralis event types. Same pattern. Note: struct is `AutonomicEvent` (events.rs L19), not `PsiEvent`. | Low | ADAPT |
| StateProjection | Derived state from events | S4 (autonomic) — `StateProjection` | E0 — `autonomic-controller/src/projection.rs` L1-23 | `projection = fold(events, initial_state, reducer)` | MIT | ADAPT | Same pattern. Neuralis-specific event types. | Low | ADAPT |
| HysteresisGate | State transitions | S4 (autonomic) — `HysteresisGate` | E0 — `autonomic-core/src/hysteresis.rs` L16-45 | Separate enter/exit thresholds + min-hold time | MIT | ADOPT | Direct adoption. Separate thresholds prevent oscillation. | None | ADOPT |
| GatingDecision | Action gating | S4 (autonomic) — `GatingDecision` | E0 — `autonomic-core/src/rules.rs` L15, L55, L66 | Struct: `{rule_id, economic_mode, max_tokens, priority}`. Not an enum. | MIT | ADOPT | GatingDecision is a struct (not enum). Enter/Exit/Stay/Block is D (v2 design). | None | ADOPT |
| RuleSet | Behavioral rules | S4 (autonomic) — `RuleSet` | E0 — `autonomic-core/src/rules.rs` L15, L55, L66 | Collection of rules with context matching | MIT | ADAPT | Neuralis-specific rule format. | Low | ADAPT |
| ContextRuling | Context-dependent behavior | S4 (autonomic) — `ContextRuling` | E0 — `autonomic-core/src/context.rs` L16 | Rule + context predicate | MIT | ADAPT | Same pattern. | Low | ADAPT |
| StabilityBudget | Stability monitoring | S4 (autonomic) — `StabilityBudget` | E0 — `autonomic-core/src/rcs_budget.rs` L92/L178 | Budget + decay + replenish | MIT | ADOPT | Direct adoption. | None | ADOPT |
| MarginEstimator | Safety margins | S4 (autonomic) — `MarginEstimator` | E0 — `autonomic-core/src/rcs_budget.rs` L92/L178 | Estimate margin to threshold | MIT | ADOPT | Direct adoption. | None | ADOPT |
| HomeostaticState → PSI | Physiological → psychological | S5 (autonomic) — `HomeostaticState` | E0 — `autonomic-core/src/gating.rs` L271-283 | 5 sub-states (not 3-pillar) | MIT | ADAPT | Map to 5-need psychological state. Source is `autonomic-core/src/gating.rs` L271-283, not `life/src/homeostatic.rs`. | Low | ADAPT |
| EconomicMode → PsiMode | Operational mode | S5 (autonomic) — `EconomicMode` | E0 — `autonomic-core/src/economic.rs` L15 | Mode enum with transition rules | MIT | ADAPT | Rename to Neuralis attention gate states. Source is `autonomic-core/src/economic.rs` L15, not `life/src/economic.rs`. | Low | ADAPT |
| fold() → PsiEvent match arms | Event reduction | S5 (autonomic) — fold pattern | E0 — `autonomic-controller/src/projection.rs` L23 | `fold(events, |state, event| match event { ... })` | MIT | ADOPT | Same pattern. Source is `autonomic-controller/src/projection.rs` L23, not `life/src/event.rs`. | None | ADOPT |

### pymdp (Active Inference)

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Fixed-point iteration (FPI) | Prediction error minimization | S6 (pymdp) — `inference.py` | E0 — `pymdp/legacy/algos/fpi.py` | `log q = log p(o|s) + log p(s)` | MIT | ADAPT | 1-step FPI only. Map to Neuralis prediction error. | Low | ADAPT |
| Epistemic value | Information-seeking drive | S6 (pymdp) — `efe.py` | E0 — `pymdp/control.py` L208-251 | `epistemic_value = D_KL[q(s|o) || q(s)]` | MIT | ADAPT | Use in cognitive loop (10Hz), not 2000Hz. | Low | ADAPT |
| Pragmatic value | Goal-directed drive | S6 (pymdp) — `efe.py` | E0 — `pymdp/control.py` L208-251 | `pragmatic_value = E_q[log p(o|C)]` | MIT | ADAPT | Use in cognitive loop. | Low | ADAPT |
| EFE = -(info_gain + utility - param_info_gain) | Expected Free Energy | S6 (pymdp) — `efe.py` | E0 — `pymdp/control.py` L208-251 | Full EFE decomposition | MIT | ADAPT | Use in cognitive loop. | Low | ADAPT |
| Policy posterior = softmax(γ·neg_efe) | Policy selection | S6 (pymdp) — `policy.py` | E0 — `pymdp/control.py` L208 (γ=16.0) | `π = softmax(γ·neg_efe)` where γ=16.0 default | MIT | ADAPT | Use in cognitive loop. | Low | ADAPT |
| Sparse dependency matrices | Efficient computation | S6 (pymdp) — sparse matrices | E0 — `pymdp/planning/mcts.py` | Sparse matrix representation of dependencies | MIT | ADAPT | Use for 2000Hz FPI to keep computation minimal. | Low | ADAPT |
| Full multi-iter FPI | Deep inference | S6 (pymdp) — `inference.py` | E0 — `pymdp/legacy/algos/fpi.py` | Multiple FPI iterations until convergence | MIT | REJECT | Too heavy for any Neuralis loop. | N/A | REJECT |
| MCTS | Policy search | S6 (pymdp) — MCTS | E0 — `pymdp/planning/mcts.py` | Monte Carlo tree search | MIT | REJECT | Too heavy. Not suitable for 2000Hz or 10Hz. | N/A | REJECT |

### OpenPsi Concepts (AGPL — Abstract Only)

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Demand concept | Need as goal with satisfaction | S7 (OpenPsi) — abstract | E0 — `opencog/openpsi/demand.scm` | `demand ∈ [0,1]` with target | AGPL v3 | REFERENCE | Concept only. No code copied. Neuralis already has equivalent. | Legal — AGPL boundary | REFERENCE |
| Component model | Parallel behavior modules | S7 (OpenPsi) — abstract | I — insufficient evidence | Independent step rates + action selectors | AGPL v3 | REFERENCE | Concept only. Useful for architecture inspiration. | Legal — AGPL boundary | REFERENCE |
| Rule triple (context-action-goal) | Behavioral rule | S7 (OpenPsi) — abstract | E0 — `opencog/openpsi/rule.scm`, `opencog/openpsi/main.scm`, `opencog/openpsi/dynamics/` | Context → Action → Goal expectation | AGPL v3 | REFERENCE | Concept already present in Neuralis design. | Legal — AGPL boundary | REFERENCE |

### 2000Hz Runtime

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Spin-sleep pattern | Tick scheduling | S8 (spin-sleep) | E0 — `spin-sleep/src/lib.rs` L78 (DEFAULT_NATIVE_SLEEP_ACCURACY = 125_000 ns) | `spin_sleep::sleep(125µs)` with spin-last-125µs strategy | Apache-2.0 | ADAPT | E0 evidence: `DEFAULT_NATIVE_SLEEP_ACCURACY = 125_000 ns` is the default value, not guaranteed precision. Must verify on target hardware. | Medium — accuracy depends on OS/hardware | ADAPT |
| `std::time::Instant` | Timing | Rust stdlib | E1 (clock name) + I (41-42ns is inference from mach_timebase, not in Rust docs) | `CLOCK_UPTIME_RAW` on macOS, ~41-42ns tick on Apple Silicon | N/A | ADOPT | Direct adoption. Clock name from Rust docs. Tick timing is inference from mach_timebase. | None | ADOPT |
| Bounded ring buffer | Event queue | D — Neuralis design | D | Fixed-size ring buffer with atomic head/tail | N/A | ADOPT | New design. | Low | ADOPT |
| Atomic snapshot | State publishing | D — Neuralis design | D | Atomic read of RingBuffer → snapshot | N/A | ADOPT | New design. | Low | ADOPT |
| hdrhistogram | Tick duration metrics | D — Neuralis design | D | High Dynamic Range histogram | N/A | ADOPT | New design. | Low | ADOPT |
| Deadline miss detection | Reliability | D — Neuralis design | D | `tick_end - tick_start > 500µs → miss++` | N/A | ADOPT | New design. | Low | ADOPT |
| Drift tracking | Clock sync | D — Neuralis design | D | `accumulated = Σ(actual_interval - target_period)` | N/A | ADOPT | New design. | Low | ADOPT |
| Catch-up: Skip/Burst/Delay | Overload recovery | D — Neuralis design | D | Skip (default): drop missed ticks. Burst: run faster. Delay: shift schedule. | N/A | ADOPT | New design. Skip default. | Low | ADOPT |
| DegradationManager | Graceful degradation | S9 (ExoGenesis-Omega) | REFERENCE — `prancer-io/ExoGenesis-Omega`, license未聲明(API license=null) | State machine: normal → degraded → recovery | null | REFERENCE | Concept only. Neuralis will implement its own degradation logic. | Legal — API license=null | REFERENCE |
| HealthMonitor | System health | S9 (ExoGenesis-Omega) | REFERENCE — same as above | Periodic health checks | null | REJECT | Neuralis uses its own deadline/drift/metrics system. | Legal — API license=null | REJECT |
| Predictive hierarchy | Multi-level prediction | S9 (ExoGenesis-Omega) | REFERENCE — same as above | Hierarchical prediction loop | null | REJECT | Architecture reference only. | Technical — not directly applicable | REJECT |

### Rejected Items

| Function | Source | Reason for Rejection |
|----------|--------|---------------------|
| Emo_valence (MicroPsi2) | S2 | Formula is explicit: `0.5 - urge_change - sum_urges` (stepoperators.py L159). Not adoptable as-is. |
| Fear (MicroPsi2) | S2 | Set to 0 (placeholder). `stepoperators.py` L144. No meaningful implementation. |
| Helplessness (MicroPsi2) | S2 | Set to 0 (placeholder). `stepoperators.py` L144. No meaningful implementation. |
| Exp_fear (MicroPsi2) | S2 | Set to 0 (placeholder). `stepoperators.py` L144. No meaningful implementation. |
| Full multi-iter FPI (pymdp) | S6 | Too heavy. Not suitable for any Neuralis loop. |
| MCTS (pymdp) | S6 | Too heavy. Not suitable for 2000Hz or 10Hz. |
| Predictive hierarchy (ExoGenesis) | S9 | Architecture reference only. Not a direct adoption. |
| HealthMonitor (ExoGenesis) | S9 | License unverifiable (API license=null). Neuralis has its own system. |
| Lago/Arcan/Haima/Chronos/Anima/Ergon (autonomic) | S4 | Credit-based economics, LLM model tier, JWT — not relevant to Neuralis PSI. |
| LLM model tier | S4/S9 | Not for 2000Hz loop. Event-driven slow loop only. |
| Vector search | S9 | Not for 2000Hz loop. Event-driven slow loop only. |
| Episodic memory (in 2000Hz) | S3 | SEC uses k-NN + softmax for episodic. Not for 2000Hz. Event-driven slow loop only. |

### Unknown Items

| Item | Reason |
|------|--------|
| Optimal OU process θ per need | Requires empirical calibration on target hardware |
| Spin-sleep 125µs accuracy on Neuralis hardware | E1 claim only (DEFAULT_NATIVE_SLEEP_ACCURACY = 125_000 ns at spin-sleep lib.rs L78). Not independently verified. |
| spin-sleep test reliability under load | Tests may fail 50 times ("passes_eventually!") |
| ExoGenesis-Omega license | `prancer-io/ExoGenesis-Omega` repo exists, API license=null |
| Neuralis v1 determinism (2 RNG sources) | `random.gauss` + `numpy` — non-symmetric. Rust must use a single, seeded RNG. |

## Licensing Summary

| Source | License | What We Can Use | Restrictions |
|--------|---------|-----------------|-------------|
| Neuralis v1 | MIT | Everything | Attribution required |
| MicroPsi2 | MIT | All formulas, algorithms | Attribution required |
| Synthetic Emotion Controller | MIT | All formulas, algorithms | Attribution required |
| autonomic | MIT | All code, patterns | Attribution required |
| pymdp | MIT | All formulas, algorithms | Attribution required |
| OpenPsi | AGPL v3 + linking exception | Concepts only | NO code copying. Abstraction boundary: concept only. |
| spin-sleep | Apache-2.0 | Library usage | Attribution required |
| ExoGenesis-Omega | Unverifiable (API license=null) | Architecture concepts only | CAUTION: API license=null, not MIT/BSD |
| pymdp (sparse) | MIT | Library usage | Attribution required |

## Evidence Level Summary

| Level | Count | Sources |
|-------|-------|--------|
| E0 (source code) | 50 | Neuralis v1, MicroPsi2, SEC, autonomic, pymdp, OpenPsi, spin-sleep |
| E1 (author docs) | 1 | spin-sleep 125µs accuracy claim |
| E1+I | 1 | `std::time::Instant` clock name (E1) + 41-42ns tick inference from mach_timebase (I) |
| D (Neuralis design) | 13 | 2000Hz runtime components, serotonin modulation, OU process, GatingDecision v2, snapshot v2 |
| REFERENCE | 3 | OpenPsi concepts, ExoGenesis-Omega, ExoGenesis degradation |
| I (inference) | 0 | — |
| UNKNOWN | 6 | Listed in Unknown Items table |