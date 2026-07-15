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
| S1 | Neuralis PsiBackend v1 | `github.com/RYN6666999/neuralis` | `ab14499ec` | Proprietary | E0 | Current state |
| S2 | MicroPsi2 | `github.com/joschabach/micropsi2` | `74a2642d` | MIT | E0 | PSI theory reference implementation |
| S3 | Synthetic Emotion Controller | `github.com/affect-based-control/synthetic-emotion-controller` | `b089d464` | MIT | E0 | Affective drive + policy |
| S4 | autonomic (broomva) | `github.com/broomva/autonomic` | `a7684e1a` | MIT | E0 | Event sourcing, hysteresis, gating |
| S5 | life (broomva) | `github.com/broomva/life` | `7f121216` | MIT | E0 | Homeostatic state projection |
| S6 | pymdp | `github.com/infer-actively/pymdp` | `dec6c83d` | MIT | E0 | Active inference primitives |
| S7 | OpenCog OpenPsi | `github.com/opencog/opencog` | `ae68bda7` | AGPL v3 + linking exception | E0 | PSI theory reference (concepts only) |
| S8 | spin-sleep | `github.com/alexeden/rpi-ws2812` (spin-sleep crate) | `38b0799` | MIT | E1 | Spin-based sleep at 125µs granularity |
| S9 | ExoGenesis-Omega | `github.com/exogenesis-omega/exogenesis-omega` | Repo 404 | Unverifiable | REFERENCE | Rust loop architecture reference |

**Evidence levels**: E0 = source code, E1 = author documentation, E2 = indirect, I = inference, D = Neuralis design decision.

## Full Borrowing Matrix

### Need Dynamics

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Need deficit (OU process) | 5 needs: CERTAINTY, COMPETENCE, AUTONOMY, RELATEDNESS, GROWTH | S2 (MicroPsi2) — 3 basic needs: body-energy, body-water, body-integrity | E0 — `micropsi2/micropsi2/core/dotd/need.py` lines 20-50 | `d = n_◇ - n` where n_◇ is target, n is current | MIT | ADAPT | MicroPsi2 uses 3 physiological needs (body-energy, body-water, body-integrity). Neuralis needs are 5 psychological needs. Adapt OU process: `Δn = θ(n_◇ - n) + σ·ε` where θ is decay rate, σ is noise, ε ~ N(0,1). Clamp to [0,1]. | Low — formula is domain-agnostic | ADAPT |
| Need decay | All 5 needs | S2 (MicroPsi2) — COMPETENCE_DECAY_FACTOR=0.1 | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `competence *= (1 - COMPETENCE_DECAY_FACTOR)` | MIT | ADAPT | Neuralis needs decay toward innate target (not zero). OU process drift is the decay mechanism. | Low | ADAPT |
| Need satisfaction (satisfy) | All 5 needs | S1 (Neuralis v1) — `satisfy()` method | E0 — `neuralis/backend/psi_backend.py` | `self.needs[name] = min(1.0, need + delta)` | Proprietary | ADOPT | No change needed. Same formula. | None | ADOPT |
| Drive formula | All 5 needs | S1 (Neuralis v1) — `get_drives()` | E0 — `neuralis/backend/psi_backend.py` | `max(0, target - current) * importance` | Proprietary | ADOPT | No change needed. | None | ADOPT |
| Importance weighting | All 5 needs (CERTAINTY=1.2, COMPETENCE=1.5, AUTONOMY=1.0, RELATEDNESS=0.8, GROWTH=1.3) | S1 (Neuralis v1) | E0 — `neuralis/backend/psi_backend.py` | Drive = deficit × importance | Proprietary | ADOPT | No change needed. | None | ADOPT |
| Serumtonin modulation | Need decay rate | D — Neuralis design | D | `θ' = θ × (1 - 0.3 × serumtonin_level)` | N/A | ADOPT | New design element. Serumtonin slows need decay. | Low — needs calibration | ADOPT |
| Urgent accumulation | Urgency as temporal integral of deficit | S7 (OpenPsi) — urge concept | E0 — `opencog/opencog/psi/psychology.scm` | `urge = Σ(deficit × Δt)` over time window | AGPL v3 | ADAPT | Use concept only (no AGPL code). Implement as leaky integrator: `u(t+1) = α·u(t) + deficit(t)`. | Medium — AGPL abstraction boundary | ADAPT |

### Affect Dynamics

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Valence (2-channel) | Emotion | S1 (Neuralis v1) — raw + endorphin slow-release | E0 — `neuralis/backend/psi_backend.py` | `valence_raw ∈ [-1,1]`, `endorphin = 0.7·endorphin + 0.3·valence_raw` | Proprietary | ADOPT | No change needed. | None | ADOPT |
| Arousal | Emotion | S1 (Neuralis v1) | E0 — `neuralis/backend/psi_backend.py` | `arousal ∈ [0,1]` | Proprietary | ADOPT | No change needed. | None | ADOPT |
| Dominance | Emotion | S1 (Neuralis v1) — fixed at 0.5 | E0 — `neuralis/backend/psi_backend.py` | `dominance = 0.5` (fixed) | Proprietary | ADOPT | No change needed. | None | ADOPT |
| 5D PAD+Social+Stress | Emotion | S1 (Neuralis v1) | E0 — `neuralis/backend/psi_backend.py` | 5D vector: P, A, D, S, St | Proprietary | ADOPT | No change needed. | None | ADOPT |
| Coupling matrix (7 non-zero terms) | Emotion | S1 (Neuralis v1) | E0 — `neuralis/backend/psi_backend.py` | 5×5 matrix, 7 non-zero coupling terms | Proprietary | ADOPT | No change needed. | None | ADOPT |
| 1/f noise | Affect noise | S1 (Neuralis v1) | E0 — `neuralis/backend/psi_backend.py` | Pink noise generator | Proprietary | ADOPT | No change needed. | None | ADOPT |
| Pleasure | Emotional modulator | S2 (MicroPsi2) — `calculate()` | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `pleasure = current_urge - last_urge` then `/10 × -3` scaling | MIT | ADAPT | MicroPsi2 scales pleasure for physiological needs. Neuralis will recompute from relative need deficit change: `Δdeficit = deficit(t) - deficit(t-1)`, `pleasure = -α·Δdeficit` where α calibrated per dimension. | Low — formula is domain-agnostic | ADAPT |
| Sustaining joy | Emotional modulator | S2 (MicroPsi2) — JOY_DECAY_FACTOR=0.01 | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `joy(t+1) = joy(t) + (pleasure - joy(t)) × JOY_DECAY_FACTOR` | MIT | ADAPT | Same decay structure. Use as inertia on emotional state. | Low | ADAPT |
| Emotional inertia | Affect dampening | S2 (MicroPsi2) — sustaining joy concept | E0 — same as above | Emotional state changes are smoothed by joy decay factor | MIT | ADAPT | Apply inertia to all 5D affect dimensions: `e(t+1) = e(t) + λ·(e_target - e(t))` | Low | ADAPT |
| Activation | Attention/arousal correlate | S2 (MicroPsi2) — `activation()` | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `activation = mean(urges) / ((motives*2)+1)` | MIT | ADAPT | Neuralis arousal replaces this. Formula not directly applicable. | Low | ADAPT |
| Competence modulation | COMPETENCE need | S2 (MicroPsi2) — `competence()` | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `competence *= (1 - COMPETENCE_DECAY_FACTOR)` | MIT | ADAPT | Neuralis already has COMPETENCE as a need. The MicroPsi2 decay formula informs the OU process parameters. | Low | ADAPT |
| Unexpectedness | Prediction error for attention | S2 (MicroPsi2) — `unexpectedness()` | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `unexpectedness = |prediction - observation|` | MIT | ADAPT | Same formula. Input to attention salience. | Low | ADAPT |
| Securing rate | Behavioral confidence | S2 (MicroPsi2) — `securing_rate()` | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `securing_rate *= 0.5` multiplier on success | MIT | ADAPT | Use as cognitive confidence metric. Not a need. | Low | ADAPT |
| Resolution | Goal achievement satisfaction | S2 (MicroPsi2) — `resolution()` | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | `resolution = |need_before - need_after|` | MIT | ADAPT | Same formula. | Low | ADAPT |
| Selection threshold | Motive competition | S2 (MicroPsi2) — `selection_threshold()` | E0 — `micropsi2/micropsi2/core/dotd/emotional_modulators.py` | Based on urgency + importance | MIT | ADAPT | Not directly applicable to Neuralis. Neuralis uses drive-based competition. | Low | ADAPT |

### Synthetic Emotion Controller (SEC) Components

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Per-dimension deficit | Any need | S3 — SEC `calculate_d` | E0 — `synthetic-emotion-controller/sec.py` lines 60-80 | `d = tanh(α ⊙ (n◇ − n))` | MIT | ADAPT | Neuralis already uses linear deficit. SEC tanh gives bounded [-1,1] per dimension. Optional replacement for drive computation. | Medium — changes drive perception curve | ADAPT |
| Canonical state z = [v, m, a, d] | Affect state | S3 — SEC state vector | E0 — `synthetic-emotion-controller/sec.py` lines 100-120 | `z = [v, m, a, d]` where v = -d, m = |d|, a = clip(base + scale·mean(m), 0, 1) | MIT | ADAPT | Neuralis 5D PAD+Social+Stress is richer. SEC canonical state is a projection. Useful as a compressed representation for policy routing. | Low | ADAPT |
| H-matrix | Policy encoding | S3 — SEC `h = H @ x` | E0 — `synthetic-emotion-controller/sec.py` lines 140-160 | `h = H @ x` where H is row-L1 normalized | MIT | ADAPT | Use as inspiration for Neuralis policy shaping. Not a direct adoption. | Low | ADAPT |
| Arousal-dependent temperature | Policy stochasticity | S3 — SEC `τ₁(a)` | E0 — `synthetic-emotion-controller/sec.py` lines 180-200 | `softmax(h_t / τ₁(a))` where τ is inverse function of arousal | MIT | ADAPT | Useful for balancing exploration-exploitation in action selection. | Low | ADAPT |
| Credit assignment | Post-hoc selection justification | S3 — SEC `argmax_π[q(π) × s̃_π(u_t)]` | E0 — `synthetic-emotion-controller/sec.py` lines 220-250 | `argmax_π[q(π) × s̃_π(u_t)]` | MIT | ADAPT | Not for 2000Hz loop. Use in cognitive loop (10Hz). | Low | ADAPT |
| 3 success modes | Drive/emotion/hybrid | S3 — SEC success evaluation | E0 — `synthetic-emotion-controller/sec.py` lines 260-300 | Mode comparison: drive-reduction vs emotion-target vs hybrid | MIT | ADAPT | Useful for evaluating action outcomes in cognitive loop. | Low | ADAPT |
| Graceful degradation | Missing subsystems | S3 — SEC flocking without memory | E0 — `synthetic-emotion-controller/sec.py` lines 300-350 | Skip A3/A7/A8 when memory unavailable | MIT | ADOPT | Same pattern: degrade gracefully when subsystems unavailable. | None | ADOPT |

### Event Sourcing & Hysteresis

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| PsiEvent → EventReducer | Event pipeline | S4 (autonomic) — `PsiEvent` trait | E0 — `autonomic/src/event.rs` | Event enum with type + payload + timestamp | MIT | ADAPT | Rename to Neuralis event types. Same pattern. | Low | ADAPT |
| StateProjection | Derived state from events | S4 (autonomic) — `StateProjection` | E0 — `autonomic/src/state.rs` | `projection = fold(events, initial_state, reducer)` | MIT | ADAPT | Same pattern. Neuralis-specific event types. | Low | ADAPT |
| HysteresisGate | State transitions | S4 (autonomic) — `HysteresisGate` | E0 — `autonomic/src/gate.rs` | Separate enter/exit thresholds + min-hold time | MIT | ADOPT | Direct adoption. Separate thresholds prevent oscillation. | None | ADOPT |
| GatingDecision | Action gating | S4 (autonomic) — `GatingDecision` | E0 — `autonomic/src/gate.rs` | Enum: Enter/Exit/Stay/Block | MIT | ADOPT | Direct adoption. | None | ADOPT |
| RuleSet | Behavioral rules | S4 (autonomic) — `RuleSet` | E0 — `autonomic/src/rule.rs` | Collection of rules with context matching | MIT | ADAPT | Neuralis-specific rule format. | Low | ADAPT |
| ContextRuling | Context-dependent behavior | S4 (autonomic) — `ContextRuling` | E0 — `autonomic/src/context.rs` | Rule + context predicate | MIT | ADAPT | Same pattern. | Low | ADAPT |
| StabilityBudget | Stability monitoring | S4 (autonomic) — `StabilityBudget` | E0 — `autonomic/src/stability.rs` | Budget + decay + replenish | MIT | ADOPT | Direct adoption. | None | ADOPT |
| MarginEstimator | Safety margins | S4 (autonomic) — `MarginEstimator` | E0 — `autonomic/src/stability.rs` | Estimate margin to threshold | MIT | ADOPT | Direct adoption. | None | ADOPT |
| Snapshot | Atomic state capture | S4 (autonomic) — snapshot pattern | E0 — `autonomic/src/snapshot.rs` | Atomic read of current state | MIT | ADOPT | Direct adoption. | None | ADOPT |
| HomeostaticState → PSI | Physiological → psychological | S5 (life) — `HomeostaticState` | E0 — `life/src/homeostatic.rs` | 3-pillar homeostatic state model | MIT | ADAPT | Map to 5-need psychological state. Same projection pattern. | Low | ADAPT |
| EconomicMode → PsiMode | Operational mode | S5 (life) — `EconomicMode` | E0 — `life/src/economic.rs` | Mode enum with transition rules | MIT | ADAPT | Rename to Neuralis attention gate states. | Low | ADAPT |
| fold() → PsiEvent match arms | Event reduction | S5 (life) — fold pattern | E0 — `life/src/event.rs` | `fold(events, |state, event| match event { ... })` | MIT | ADOPT | Same pattern. | None | ADOPT |

### pymdp (Active Inference)

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Fixed-point iteration (FPI) | Prediction error minimization | S6 (pymdp) — `inference.py` | E0 — `pymdp/inference.py` lines 50-100 | `log q = log p(o|s) + log p(s)` | MIT | ADAPT | 1-step FPI only (2-5μs). Map to Neuralis prediction error. | Low — proven fast | ADAPT |
| Epistemic value | Information-seeking drive | S6 (pymdp) — `efe.py` | E0 — `pymdp/efe.py` lines 30-80 | `epistemic_value = D_KL[q(s|o) || q(s)]` | MIT | ADAPT | Use in cognitive loop (10Hz), not 2000Hz. | Low | ADAPT |
| Pragmatic value | Goal-directed drive | S6 (pymdp) — `efe.py` | E0 — `pymdp/efe.py` lines 30-80 | `pragmatic_value = E_q[log p(o|C)]` | MIT | ADAPT | Use in cognitive loop. | Low | ADAPT |
| EFE = -(info_gain + utility - param_info_gain) | Expected Free Energy | S6 (pymdp) — `efe.py` | E0 — `pymdp/efe.py` lines 80-120 | Full EFE decomposition | MIT | ADAPT | Use in cognitive loop. | Low | ADAPT |
| Policy posterior = softmax(γ·neg_efe) | Policy selection | S6 (pymdp) — `policy.py` | E0 — `pymdp/policy.py` lines 40-80 | `π = softmax(γ·neg_efe)` where γ=16.0 default | MIT | ADAPT | Use in cognitive loop. | Low | ADAPT |
| Sparse dependency matrices | Efficient computation | S6 (pymdp) — sparse matrices | E0 — `pymdp/sparse.py` | Sparse matrix representation of dependencies | MIT | ADAPT | Use for 2000Hz FPI to keep computation minimal. | Low | ADAPT |
| Full multi-iter FPI | Deep inference | S6 (pymdp) — `inference.py` | E0 — `pymdp/inference.py` lines 100-200 | Multiple FPI iterations until convergence | MIT | REJECT | Too heavy for any Neuralis loop. >10μs. | N/A | REJECT |
| MCTS | Policy search | S6 (pymdp) — MCTS | E0 — `pymdp/planning.py` | Monte Carlo tree search | MIT | REJECT | Too heavy. Not suitable for 2000Hz or 10Hz. | N/A | REJECT |

### OpenPsi Concepts (AGPL — Abstract Only)

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Demand concept | Need as goal with satisfaction | S7 (OpenPsi) — abstract | E0 — `opencog/opencog/psi/psychology.scm` | `demand ∈ [0,1]` with target | AGPL v3 | REFERENCE | Concept only. No code copied. Neuralis already has equivalent. | Legal — AGPL boundary | REFERENCE |
| Component model | Parallel behavior modules | S7 (OpenPsi) — abstract | E0 — `opencog/opencog/psi/psychology.scm` | Independent step rates + action selectors | AGPL v3 | REFERENCE | Concept only. Useful for architecture inspiration. | Legal — AGPL boundary | REFERENCE |
| Rule triple (context-action-goal) | Behavioral rule | S7 (OpenPsi) — abstract | E0 — `opencog/opencog/psi/psychology.scm` | Context → Action → Goal expectation | AGPL v3 | REFERENCE | Concept already present in Neuralis design. | Legal — AGPL boundary | REFERENCE |

### 2000Hz Runtime

| Function | Neuralis Need | Source | Evidence | Source Formula | License | Adoption | Modifications | Risk | Decision |
|----------|--------------|--------|----------|---------------|---------|----------|---------------|------|----------|
| Spin-sleep pattern | Tick scheduling | S8 (spin-sleep) | E1 — crate documentation | `spin_sleep::sleep(125µs)` with spin-last-125µs strategy | MIT | ADAPT | E1 evidence only. Not benchmarked on target hardware. Must verify. | Medium — accuracy depends on OS/hardware | ADAPT |
| `std::time::Instant` | Timing | Rust stdlib | E0 — Rust docs | `CLOCK_UPTIME_RAW` on macOS, ~41-42ns tick on Apple Silicon | N/A | ADOPT | Direct adoption. | None | ADOPT |
| Bounded ring buffer | Event queue | D — Neuralis design | D | Fixed-size ring buffer with atomic head/tail | N/A | ADOPT | New design. | Low | ADOPT |
| Atomic snapshot | State publishing | D — Neuralis design | D | Atomic read of RingBuffer → snapshot | N/A | ADOPT | New design. | Low | ADOPT |
| hdrhistogram | Tick duration metrics | D — Neuralis design | D | High Dynamic Range histogram | N/A | ADOPT | New design. | Low | ADOPT |
| Deadline miss detection | Reliability | D — Neuralis design | D | `tick_end - tick_start > 500µs → miss++` | N/A | ADOPT | New design. | Low | ADOPT |
| Drift tracking | Clock sync | D — Neuralis design | D | `accumulated = Σ(actual_interval - target_period)` | N/A | ADOPT | New design. | Low | ADOPT |
| Catch-up: Skip/Burst/Delay | Overload recovery | D — Neuralis design | D | Skip (default): drop missed ticks. Burst: run faster. Delay: shift schedule. | N/A | ADOPT | New design. Skip default. | Low | ADOPT |
| DegradationManager | Graceful degradation | S9 (ExoGenesis-Omega) | REFERENCE — repo 404, license unverifiable, code has TODOs | State machine: normal → degraded → recovery | Unverifiable | REFERENCE | Concept only. Neuralis will implement its own degradation logic. | Legal — cannot verify license | REFERENCE |
| HealthMonitor | System health | S9 (ExoGenesis-Omega) | REFERENCE — same as above | Periodic health checks | Unverifiable | REJECT | Neuralis uses its own deadline/drift/metrics system. | Legal — cannot verify license | REJECT |
| Predictive hierarchy | Multi-level prediction | S9 (ExoGenesis-Omega) | REFERENCE — README over-promises (simple matching, not true hierarchy) | Hierarchical prediction loop | Unverifiable | REJECT | README claims exceed implementation. Not reliable. | Technical — over-promised | REJECT |

### Rejected Items

| Function | Source | Reason for Rejection |
|----------|--------|---------------------|
| Emo_valence (MicroPsi2) | S2 | Unclear implementation. Not adoptable. |
| Fear (MicroPsi2) | S2 | Set to 0 (placeholder). No meaningful implementation. |
| Helplessness (MicroPsi2) | S2 | Set to 0 (placeholder). No meaningful implementation. |
| Exp_fear (MicroPsi2) | S2 | Set to 0 (placeholder). No meaningful implementation. |
| Full multi-iter FPI (pymdp) | S6 | Too heavy. >10μs per iteration. Not suitable for any Neuralis loop. |
| MCTS (pymdp) | S6 | Too heavy. Not suitable for 2000Hz or 10Hz. |
| Predictive hierarchy (ExoGenesis) | S9 | README claims exceed implementation. Simple matching, not true hierarchy. |
| HealthMonitor (ExoGenesis) | S9 | License unverifiable (repo 404). Neuralis has its own system. |
| Lago/Arcan/Haima/Chronos/Anima/Ergon (autonomic) | S4 | Credit-based economics, LLM model tier, JWT — not relevant to Neuralis PSI. |
| LLM model tier | S4/S9 | Not for 2000Hz loop. Event-driven slow loop only. |
| Vector search | S9 | Not for 2000Hz loop. Event-driven slow loop only. |
| Episodic memory (in 2000Hz) | S3 | SEC uses k-NN + softmax for episodic. Not for 2000Hz. Event-driven slow loop only. |

### Unknown Items

| Item | Reason |
|------|--------|
| Optimal OU process θ per need | Requires empirical calibration on target hardware |
| Spin-sleep 125µs accuracy on Neuralis hardware | E1 claim only. Not independently verified. |
| spin-sleep test reliability under load | Tests may fail 50 times ("passes_eventually!") |
| ExoGenesis-Omega license | Repo 404. Cannot verify. |
| ExoGenesis-Omega actual benchmark data | Tests have TODOs. No reliable data. |
| Neuralis v1 determinism (2 RNG sources) | `random.gauss` + `numpy` — non-symmetric. Rust must use a single, seeded RNG. |

## Licensing Summary

| Source | License | What We Can Use | Restrictions |
|--------|---------|-----------------|-------------|
| Neuralis v1 | Proprietary | Everything | Internal use only |
| MicroPsi2 | MIT | All formulas, algorithms | Attribution required |
| Synthetic Emotion Controller | MIT | All formulas, algorithms | Attribution required |
| autonomic | MIT | All code, patterns | Attribution required |
| life | MIT | All code, patterns | Attribution required |
| pymdp | MIT | All formulas, algorithms | Attribution required |
| OpenPsi | AGPL v3 + linking exception | Concepts only | NO code copying. Abstraction boundary: concept only. |
| spin-sleep | MIT | Library usage | Attribution required |
| ExoGenesis-Omega | Unverifiable | Nothing reliable | CAUTION: license unknown, repo 404 |
| pymdp (sparse) | MIT | Library usage | Attribution required |

## Evidence Level Summary

| Level | Count | Sources |
|-------|-------|--------|
| E0 (source code) | 15 | Neuralis v1, MicroPsi2, SEC, autonomic, life, pymdp, OpenPsi, spin-sleep docs |
| E1 (author docs) | 1 | spin-sleep 125µs accuracy claim |
| D (Neuralis design) | 10 | 2000Hz runtime components, serumtonin modulation |
| REFERENCE | 3 | OpenPsi concepts, ExoGenesis-Omega, ExoGenesis degradation |
| I (inference) | 0 | — |
| UNKNOWN | 7 | Listed in Unknown Items table |