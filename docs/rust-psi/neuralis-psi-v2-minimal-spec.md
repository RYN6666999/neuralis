# Neuralis PsiBackend v2 — Minimal Specification

| Field | Value |
|-------|-------|
| **BASE_SHA** | `ab14499ec1d5f30e84b85c56e6c780c7eb4d6913` |
| **Date** | 2026-07-15 |
| **Status** | Draft — minimal viable spec for Rust PSI engine |
| **Author** | Wolf 8 (Document Writer) — synthesis of Wolf 1–7 |

## 1. PsiEngine Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PsiEngine                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ NeedDynamics │  │ AffectDynamics│  │    AttentionGate       │  │
│  │ (5 needs)    │  │ (5D PAD+S+St)│  │ (IDLE/TASK/LEARN/PLAN) │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬────────────┘  │
│         │                 │                       │              │
│         └─────────────────┼───────────────────────┘              │
│                           │                                      │
│                    ┌──────▼───────┐                              │
│                    │  EventReducer│                              │
│                    │  (fold-only) │                              │
│                    └──────┬───────┘                              │
│                           │                                      │
│                    ┌──────▼───────┐                              │
│                    │    Snapshot  │                              │
│                    │ (atomic copy)│                              │
│                    └──────┬───────┘                              │
│                           │                                      │
│              ┌────────────▼────────────┐                         │
│              │    TickMetrics          │                         │
│              │ (hdrhistogram,deadline, │                         │
│              │  drift, catch-up count) │                         │
│              └─────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘

Tiers:
  A. 2000Hz ── NeedDynamics.affect_inertia, input_pulse_decay, prediction_error_smooth, TickMetrics
  B. 100Hz  ── SnapshotPublisher (atomic read → publish), metric aggregation
  C. 10Hz   ── AttentionGate, motive competition, policy adjustment, PE interpretation
  D. Event  ── LLM, tools, episodic memory, persistence, consolidation
```

## 2. Subsystem Specifications

### 2.1 NeedDynamics

**Five psychological needs** (physiological needs are handled by separate systems; ENERGY and GROWTH are distinct domains):

| Need | Initial | Target | Decay Rate (θ) | Importance | Domain |
|------|---------|--------|-----------------|------------|--------|
| CERTAINTY | 0.6 | 0.8 | 0.008 | 1.2 | Psychological — predictability |
| COMPETENCE | 0.4 | 0.9 | 0.012 | 1.5 | Psychological — efficacy |
| AUTONOMY | 0.5 | 0.7 | 0.005 | 1.0 | Psychological — agency |
| RELATEDNESS | 0.5 | 0.7 | 0.010 | 0.8 | Psychological — social connection |
| GROWTH | 0.5 | 0.8 | 0.006 | 1.3 | Psychological — self-actualization |

**ENERGY** (physiological) is a separate subsystem. It is NOT merged with GROWTH.

**Ornstein-Uhlenbeck (OU) process** (per need). Two distinct anchors — do not conflate them:

```
drift = θ · (baseline − current) · dt        # mean reversion — toward BASELINE
noise = σ · ε · √dt                          # OU diffusion term
current ← clamp(current + drift + noise, 0, 1)

drive = max(0, target − current) · importance  # deficit — measured against TARGET
```

Where:
- `current` = need value, domain [0, 1], clamped post-update
- `baseline` = mean-reversion center of `current` (v1: the initial values — [laap/psi_core.py L129](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/psi_core.py#L129))
- `target` = drive anchor, used **only** in the drive/deficit computation, never as the reversion center
- `θ` = decay rate, per second, domain (0, 0.1], configurable per need
- `σ` = noise amplitude, domain [0, 0.01], configurable
- `ε` = standard normal sample, ~N(0, 1), single seeded RNG

Forbidden formulations: `target − baseline` (appears in no dynamics), and `current` reverting toward `target`.

> **Decision (M01, resolved)**: v1 relaxes `current` toward **baseline** with Gaussian noise — E0: [laap/psi_core.py L164-L168](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/psi_core.py#L164-L168) (`relax = (baselines[nt] − values[nt]) · ar · dt`). Because baseline < target for every need, resting drive stays positive — the agent keeps standing motivation at equilibrium. A target-seeking OU (reverting toward `target`) would drive resting drive to zero; it is NOT v1 behavior and is not part of this spec. The OU **formalization** (single seeded RNG, √dt noise scaling) is Neuralis v2 design (D) — it does NOT come from MicroPsi2, which contains no OU process at the pinned SHA. Deterministic mode: σ = 0, or fixed seed + fixed update order.

**Update order**: 1. Serotonin-modulated rate → 2. OU drift + noise → 3. Clamp [0, 1] → 4. NaN guard

**Serotonin modulation — two layers, kept separate**:

1. **v1 compatibility semantics (E0, ADOPT)** — step function on valence applied to the **decay rate** (not to a "serotonin level"):
   ```
   valence >  0.3 → rate × 0.7
   valence < −0.3 → rate × 1.3
   otherwise      → rate × 1.0
   ```
   E0 — [laap/psi_core.py L157-L165](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/psi_core.py#L157-L165). This is the Compatibility Mode default.

2. **v2 proposed continuous regulation (D / UNKNOWN — NOT ADOPT, NOT E0)**:
   ```
   θ' = θ · (1 − 0.3 · serotonin_level),  serotonin_level ∈ [0, 1]
   ```
   Neuralis design proposal with no external source; the 0.3 factor is uncalibrated. Must not enter the minimal core before calibration.

**Drive formula**:

```
drive = max(0, target − current) · importance
```

Where:
- `drive` = urgency/intensity of the need, domain [0, ∞)
- `importance` = scaling factor, domain [0.5, 2.0]

E0 — [laap/psi_core.py L198-L201](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/psi_core.py#L198-L201).

**Determinism**: Single seeded RNG (NOT `random.gauss` + `numpy` dual source). Seed must be configurable. Floating-point policy: f64, round-trip deterministic, same seed → same sequence.

**Source**: Neuralis v1 (`laap/psi_core.py` at BASE_SHA — permalinks above). OU formalization: Neuralis v2 design (D).

---

### 2.2 AffectDynamics

**Two-channel valence**:

```
valence_raw ∈ [-1, 1]              # immediate emotional response
# v1 ASYMMETRIC update (Compatibility Mode), Δ = valence_raw − endorphin:
#   Δ > 0  →  endorphin = valence_raw        # rise: full follow (weight 1.0)
#   Δ ≤ 0  →  endorphin += 0.3 · Δ           # fall: slow release (weight 0.3)
# Symmetric EMA is D (Future/Enhanced Mode) only — not v1 behavior.
```

E0 (both branches incl. the 0.3 weight) — [laap/psi_core.py L64-L71](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/psi_core.py#L64-L71).

**Five-dimensional affect state**:

| Axis | Symbol | Domain | Description |
|------|--------|--------|-------------|
| Pleasure | P | [-1, 1] | Hedonic tone |
| Arousal | A | [0, 1] | Activation level |
| Dominance | D | 0.5 (fixed) | Control (constant per current design) |
| Social | S | [0, 1] | Social warmth |
| Stress | St | [0, 1] | Pressure/cortisol analogue |

**Coupling matrix — v1 ground truth (E0)**. v1 has exactly 8 non-zero terms, direction `to ← from`, **no diagonal (self) terms**:

```
ΔP  =                                w_PS·S                    # P←S  +0.15
ΔA  =                w_ASt·St      + w_AS·S                    # A←St +0.5,  A←S +0.25
ΔD  =  w_DP·P      + w_DA·A                                    # D←P  +0.2,  D←A −0.15  (v1 D is DYNAMIC)
ΔS  =  w_SP·P                                                  # S←P  +0.3
ΔSt =  w_StP·P     + w_StA·A                                   # St←P −0.4,  St←A +0.2
```

E0 — [laap/affective.py L79-L87](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/affective.py#L79-L87).

**v2 deviations from v1 (both D-level decisions, NOT v1):**
1. v2 fixes D = 0.5 → the two v1 dominance terms (D←P, D←A) are dropped in v2, leaving 6 active cross terms.
2. Any diagonal damping terms (w_PP, w_AA, w_SS, w_StSt) a v2 implementation adds for stability are v2 additions (D) with values TBD; they do not exist in v1. Stability of the chosen topology must be shown (trace < 0, det > 0 per 2×2 subsystem).

**1/f noise**: Pink noise generator added to affect state. Amplitude configurable.

**Update order**: 1. Coupling matrix multiplication → 2. 1/f noise addition → 3. Clamp per-dimension domain → 4. NaN guard → 5. Endorphin update

**Emotional inertia** (Neuralis D — not from MicroPsi2):

```
e(t+1) = e(t) + λ · (e_target − e(t))
```

Where `λ = 0.01` (inertia factor, numerically borrowed from MicroPsi2 JOY_DECAY_FACTOR). Applied to all 5 dimensions.

NOTE: MicroPsi2 joy decay uses sign-hold + copysign decay, NOT EMA. The EMA formula is a Neuralis design decision.

**Affective events — the 18 v1 canonical events** (verbatim from `EVENT_EMOTION_MAP`; stimulus vector = [P, A, D, S, St]):

| # | v1 Event (exact string) | Stimulus [P, A, D, S, St] |
|---|------------------------|---------------------------|
| 1 | `user_positive_feedback` | [1.0, 0.5, 0.3, 0.5, −0.4] |
| 2 | `user_negative_feedback` | [−1.0, 0.5, −0.4, −0.4, 0.6] |
| 3 | `task_success` | [0.6, 0.2, 0.4, 0.3, −0.2] |
| 4 | `task_failure` | [−0.6, 0.35, −0.35, −0.25, 0.5] |
| 5 | `user_engagement` | [0.4, 0.3, 0.2, 0.5, −0.15] |
| 6 | `user_disengagement` | [−0.3, −0.15, −0.15, −0.4, 0.25] |
| 7 | `system_error` | [−0.4, 0.5, −0.2, −0.15, 0.6] |
| 8 | `system_recovery` | [0.35, −0.2, 0.25, 0.2, −0.4] |
| 9 | `learning_progress` | [0.5, 0.15, 0.3, 0.35, −0.15] |
| 10 | `idle_period` | [0.0, −0.3, 0.0, −0.15, −0.15] |
| 11 | `surprise_positive` | [0.6, 0.5, 0.1, 0.3, −0.1] |
| 12 | `surprise_negative` | [−0.5, 0.6, −0.2, −0.2, 0.5] |
| 13 | `frustration` | [−0.4, 0.5, −0.3, −0.1, 0.6] |
| 14 | `curiosity_aroused` | [0.2, 0.4, 0.1, 0.2, −0.1] |
| 15 | `achievement` | [0.7, 0.3, 0.5, 0.3, −0.25] |
| 16 | `anxiety` | [−0.1, 0.7, −0.2, −0.1, 0.6] |
| 17 | `relief` | [0.4, −0.3, 0.2, 0.2, −0.5] |
| 18 | `gratitude` | [0.6, 0.15, 0.2, 0.5, −0.2] |

**Source (E0, one dict, all 18 entries)**: [laap/affective.py L43-L62](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/affective.py#L43-L62). Production call sites use these exact strings (e.g. `task_success`/`task_failure` at [laap/agency.py L439](https://github.com/RYN6666999/neuralis/blob/ab14499ec1d5f30e84b85c56e6c780c7eb4d6913/laap/agency.py#L439); `user_engagement` per contract). Unknown events return `False` per PsiBackend v1 contract (`docs/contracts/psi-backend.md` §5).

**Rust adapter rule**: the Rust enum/adapter MUST map these 18 strings one-to-one (exact strings, no synonyms, no renames). Any additional v2 events (e.g. semantic names like `GOAL_ACHIEVED`) live in a separate **extension namespace** marked D, must not shadow or replace the v1 vocabulary, and must round-trip `post_affective_event(name) -> bool` exactly as v1 does. The task-008 engine's current 18 invented names do NOT satisfy this rule and require an adapter before M4/M5.

**Cognitive biases** (8 v1 bias keys):

| # | Bias | Mechanism |
|---|------|-----------|
| 1 | optimism | Valence shift +0.1 |
| 2 | risk_seeking | Higher risk tolerance |
| 3 | attention_narrowing | Focus on salient stimuli |
| 4 | confirmation_bias | Prediction error discount |
| 5 | overconfidence | Self-assessment bias |
| 6 | temporal_discounting | Present > future reward weighting |
| 7 | social_proximity | Social distance modulation |
| 8 | creativity | Novelty-seeking boost |

**Source**: Neuralis v1 (BASE_SHA, `laap/affective.py` L167–186).

---

### 2.3 AttentionGate

**Four states** (v1 schema is 4 values: IDLE/TASK/LEARNING/PLANNING. v1 SOCIAL was caused by KNOWN-ISSUE-1 AttributeError, not a design removal.):

| State | Description | Typical Triggers | Typical Duration |
|-------|-------------|------------------|-----------------|
| IDLE | Low arousal, no active task | Default, after task completion | Variable |
| TASK | Focused on current goal | Drive > threshold | Task duration |
| LEARNING | Exploring, information-seeking | Uncertainty > threshold | Variable |
| PLANNING | Deliberation, action selection | Multiple competing drives | Short |

**Transitions**: Hysteresis gating — E0: [autonomic-core/src/hysteresis.rs L16-L45](https://github.com/broomva/autonomic/blob/a7684e1aae1a5d09cb3475c733ec64bfc83ba7b9/autonomic-core/src/hysteresis.rs#L16-L45) (MIT). Separate enter/exit thresholds + minimum hold time to prevent oscillation.

**Source**: Neuralis v1 + autonomic HysteresisGate (MIT, `a7684e1a`).

---

### 2.4 EventReducer

**Pattern**: Event sourcing from autonomic — E0: [autonomic-core/src/events.rs L19](https://github.com/broomva/autonomic/blob/a7684e1aae1a5d09cb3475c733ec64bfc83ba7b9/autonomic-core/src/events.rs#L19) (`enum AutonomicEvent`; MIT).

```
PsiEvent → EventReducer → StateProjection → Hysteresis → Gating → Snapshot
```

- `PsiEvent`: enum with type, payload, timestamp
- `EventReducer`: `fold(events, |state, event| match event { ... })` — pure function, no I/O
- `StateProjection`: derives current state from event sequence
- `Hysteresis`: applies hysteresis thresholds to state transitions
- `Gating`: produces GatingDecision — the `Enter/Exit/Stay/Block` enum is a **v2 design (D)**; autonomic's real `GatingDecision` is a struct (see borrowing-matrix S4 row)
- `Snapshot`: atomic copy of current state

The reducer is a pure fold + evaluate — no I/O, deterministic, testable.

**Source**: autonomic (MIT) — fold reducer: [autonomic-controller/src/projection.rs L1-L23](https://github.com/broomva/autonomic/blob/a7684e1aae1a5d09cb3475c733ec64bfc83ba7b9/autonomic-controller/src/projection.rs#L1-L23); HomeostaticState: [autonomic-core/src/gating.rs L271-L283](https://github.com/broomva/autonomic/blob/a7684e1aae1a5d09cb3475c733ec64bfc83ba7b9/autonomic-core/src/gating.rs#L271-L283). (`broomva/life` is NOT a source — no direct-borrowing evidence exists.)

---

### 2.5 SnapshotPublisher

**Pattern**: State → atomic cell → snapshot (ring buffer is for events only).

```
State (ArcSwap<PsiState>) → atomic_read → Snapshot → Publish (via channel)
```

- **State cell**: `ArcSwap<PsiState>`, updated by tick loop after each complete tick
- **Snapshot**: immutable struct copy of current PsiState, taken from atomic read of state cell — NOT from event ring buffer
- **Event ring buffer**: fixed-size, pre-allocated, lock-free (atomic head/tail indices). Stores incoming `PsiEvent`s only, not state.
- **Publish**: snapshot sent to snapshot channel (consumed by 100Hz loop)
- **Schema compliance**: Snapshot is a v2 Rust internal structure. Must provide mapping to v1 PsiBackend state schema. B-surface is the Python attribute transition surface, NOT the snapshot schema.
- **Lock-free caveat**: No formal memory model analysis, no ABA or multi-producer contention analysis. Overwrite-oldest coalesce on the event ring buffer breaks determinism (Pillar 2). Overflow behavior must be documented as a determinism exception.

**Source**: Neuralis design (D). autonomic snapshot pattern (MIT, `a7684e1a`).

---

### 2.6 TickMetrics

**Measured per tick**:

| Metric | Unit | Collection | Decay |
|--------|------|-----------|-------|
| Tick duration | µs | hdrhistogram | Raw |
| Deadline miss | bool | Counter | Counter |
| Drift | µs | Running sum | Σ(actual − target) |
| Catch-up event | bool | Counter | Count by type (Skip/Burst/Delay) |

**hdrhistogram**: High Dynamic Range histogram. Track p50, p95, p99, p99.9, max.

**Source**: Neuralis design (D).

---

## 3. Frequency Tier Specification

### Tier A: 2000Hz Fast Loop (500µs Budget)

**Purpose**: Homeostatic/psychological need regulation — need decay, affect inertia, prediction error smoothing, timing metrics.

**Allowed operations**:
- Need decay/integration (OU process)
- Input pulse decay (smooth incoming signals)
- Affect inertia (emotional damping)
- Prediction error smoothing (exponential moving average)
- Clamp + NaN guard on all state variables
- Tick/deadline/drift metrics (hdrhistogram update, counter increment)
- Ring buffer push (events only, no processing)

**FORBIDDEN operations**:
- ❌ JSON serialization/deserialization
- ❌ Disk I/O (read/write files)
- ❌ Network I/O (HTTP, sockets, IPC)
- ❌ LLM inference
- ❌ Vector search
- ❌ Episodic memory (encode/retrieve)
- ❌ Blocking locks (mutex contention)
- ❌ Heap allocation (pre-allocate at startup)
- ❌ Full pymdp inference (VFE, EFE, policy posterior)
- ❌ Logging (beyond atomic counter increments)

**Implementation**: Spin-sleep + `std::time::Instant` + bounded ring buffer (events) + atomic snapshot.

**Lock-free caveat**: No formal memory model analysis. No ABA or multi-producer contention analysis. Overwrite-oldest on event ring buffer breaks determinism (must accept this exception for overflow).

**Source**: Neuralis design (D). Spin-sleep (Apache-2.0, `38b0799c09df30b5f034f440546a59bd7a3b028b`, E1 for accuracy claim). See `2000hz-runtime-spec.md`.

---

### Tier B: 100Hz Snapshot Loop

**Purpose**: State publishing, metric aggregation.

**Operations**:
- Atomic read of the PsiState cell → immutable Snapshot (the event ring buffer is NOT the snapshot source)
- Publish snapshot via channel to consumers
- Aggregate tick metrics (compute percentiles from hdrhistogram)
- No I/O, no LLM, no blocking

---

### Tier C: 10Hz Cognitive Loop

**Purpose**: Deliberation, selection, planning.

**Operations**:
- Motive competition (compare drives across needs)
- Attention selection (gate state transitions)
- Policy adjustment (update action tendencies)
- Prediction error interpretation (meaning/attribution)
- Credit assignment (SEC pattern, MIT, `b089d464`)

---

### Tier D: Event-Driven Slow Loop

**Purpose**: Deep cognition, external interaction.

**Operations**:
- LLM calls
- Tool execution (gbrain, files, network)
- Episodic memory encode/retrieve
- Persistence (save/load state)
- Consolidation (long-term memory)
- Schema contract updates

**Triggered by**: Events, not time. Minimum 1s between consecutive calls.

---

## 4. Python ↔ Rust Coexistence

**Environment variable**: `NEURALIS_PSI_BACKEND`

| Value | Behavior |
|-------|----------|
| `rust` | Use Rust PsiEngine exclusively |
| `python` (or unset) | Use Python PsiBackend v1 (current fallback) |
| `hybrid` | Python for slow loop, Rust for 2000Hz fast loop |

**Coexistence strategy**:
1. Rust engine reads initial state from Python (on startup, via `NEURALIS_PSI_BACKEND=python` → serialize → Rust deserializes)
2. Rust engine runs 2000Hz loop independently
3. Snapshot channel bridges to Python for cognitive loop (if hybrid mode)
4. On shutdown, Rust writes final state back to Python format

---

## 5. Deterministic Replay Requirements

**Four pillars**:

| Pillar | Requirement | Implementation |
|--------|-------------|----------------|
| Seed | Single, configurable u64 | `PsiConfig { seed: u64 }` |
| Event ordering | Events processed in received order | RingBuffer preserves insertion order |
| Update ordering | Fixed order per tick | 1. NeedDynamics → 2. AffectDynamics → 3. AttentionGate → 4. EventReducer → 5. Snapshot |
| Floating-point policy | Same binary, same platform | f64, non-SIMD, round-trip deterministic. No `-ffast-math`. Cross-platform (libm differences, FMA contraction) not guaranteed. |

**RNG**: Single `rand::rngs::StdRng` seeded from config. One RNG per PsiEngine instance. NOT two RNGs (Neuralis v1 uses `random.gauss` + `numpy` — non-symmetric).

**Two identical runs with same seed + same events → identical state sequence**.

---

## 6. Schema Contract Compliance

**B-surface compatibility**: B-surface is the Python attribute transition surface (PsiBackend v1 contract §12). It is NOT the snapshot schema.

The Rust internal `PsiSnapshot` is a **v2 new structure**. It does NOT directly match the v1 `PsiState` schema. A mapping layer is required.

```rust
// Rust internal snapshot — v2 structure (NOT v1 PsiState)
struct PsiSnapshot {
    needs: [Need; 5],          // same order as Python
    drives: [f64; 5],
    affect: Affect5D,          // P, A, D, S, St
    attention_state: GateState, // IDLE/TASK/LEARNING/PLANNING
    logical_time: u64,          // epoch + tick_index × period
    wall_clock: u64,            // separate observation field, MUST NOT affect replay
    tick_count: u64,
    metrics: TickMetrics,
    // NOTE: the event queue is deliberately NOT a snapshot field — events
    // live in the separate ring buffer; a Vec here would also violate the
    // fast-loop no-allocation rule.
}
```

**Mapping: v2 Snapshot → v1 `get_state()` dict** — the v1 schema (`psi-state.schema.json`) requires exactly these six fields: `needs`, `dominant_need`, `dominant_drive`, `emotion`, `attention`, `tick`. The mapping layer must produce all six:

| v1 schema field (required) | Built from v2 | Notes |
|----------------------------|---------------|-------|
| `needs` | `needs` + per-need `target` + computed drive | v1 shape: `{name: {current, target, drive}}`, same 5 needs, identical order |
| `dominant_need` | argmax over `drives` | v1: need name string, `"none"` when all drives ≤ 0 |
| `dominant_drive` | max of `drives` | rounded per v1 conventions |
| `emotion` | `affect` P/A + `endorphin` channel | v1 shape: `{valence (endorphin channel), raw_valence, arousal, dominance}`; EmotionGradient dominance = 0.5 |
| `attention` | `attention_state` | enum `{IDLE, TASK, LEARNING, PLANNING}`, 4 values only |
| `tick` | `tick_count` | direct pass-through |

Optional v1 fields (`affective`, `schema_version`, `backend`, `timestamp`): `affective.dims` maps from `affect`, `affective.biases` from the v1 bias computation, `timestamp` from `logical_time` (epoch-relative). v2-only fields (`metrics`, `drives` array, `wall_clock`) do NOT appear in the v1 surface.

**⚠️ Wall clock (`wall_clock`) is for observability only. It MUST NOT affect replay state. Replay uses `logical_time` exclusively.**

Serialization format: MessagePack or CBOR is a **D decision**. A JSON migration path is required for v1 contract compliance (§4 of PsiBackend contract: `get_state()` must be JSON-serializable).

---

## 7. UNKNOWN Items

| Item | Reason |
|------|--------|
| Optimal OU process θ per need | Requires empirical calibration |
| Serotonin modulation factor (0.3) | Theoretical value. Needs calibration. |
| 1/f noise amplitude | Unknown. Requires tuning. |
| Coupling matrix coefficients | v1's 8 values are known (E0, §2.2); only v2's added diagonal damping terms are TBD. |
| Hysteresis thresholds for attention gates | Must be tuned on real usage. |
| Acceptable deadline miss ratio | Depends on application requirements. |
| Spin-sleep accuracy on Apple Silicon | E1 claim only. Must benchmark. |
| Deterministic replay across Rust/Python boundary | Float format differences may cause divergence. |
| Hybrid mode latency | Channel overhead between Rust 2000Hz and Python 10Hz unknown. |