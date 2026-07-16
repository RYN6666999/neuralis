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

**Ornstein-Uhlenbeck (OU) process** (per need):

```
Δn = θ · (n_◇ − n) + σ · ε
```

Where:
- `n` = current need value, domain [0, 1], clamped post-update
- `n_◇` = target need value, domain [0, 1], constant per need
- `θ` = decay rate, domain (0, 0.1], configurable per need
- `σ` = noise amplitude, domain [0, 0.01], configurable
- `ε` = standard normal sample, ~N(0, 1), seeded RNG

> **Decision (M01)**: The OU process currently pulls toward target `n_◇` (n_◇ − n term). This is a **v2 design change**, NOT adopted from v1. v1 baseline semantics uses a fixed D=0.5 (psi_core.py L46) with no target-pulling OU. Target-seeking causes resting drive to approach zero when need is near target — v1 baseline semantics preserves resting drive by keeping the need-decay fixed. For Compatibility Mode, pre-compute `drive = max(0, target − current) · importance` without the OU target-pull. The target-seeking OU is marked **D** (Enhanced Mode).

**Update order**: 1. OU process → 2. Serotonin modulation → 3. Clamp [0, 1] → 4. NaN guard

**Serotonin modulation**:

```
θ' = θ · (1 − 0.3 · serotonin_level)
```

Where `serotonin_level ∈ [0, 1]`. Higher serotonin → slower decay (need satisfaction lasts longer).

**Serotonin source**: v1 step function — valence > 0.3 → level × 0.7, valence < −0.3 → level × 1.3 (psi_core.py L158–163).

**Drive formula**:

```
drive = max(0, n_◇ − n) · importance
```

Where:
- `drive` = urgency/intensity of the need, domain [0, ∞)
- `importance` = scaling factor, domain [0.5, 2.0]

**Determinism**: Single seeded RNG (NOT `random.gauss` + `numpy` dual source). Seed must be configurable. Floating-point policy: f64, round-trip deterministic, same seed → same sequence.

**Source**: Neuralis v1 (BASE_SHA, `psi_backend.py`), with OU process adapted from MicroPsi2 (MIT, `74a2642d`, `need.py`).

---

### 2.2 AffectDynamics

**Two-channel valence**:

```
valence_raw ∈ [-1, 1]          # immediate emotional response
# v1 non-asymmetric (Compatibility Mode):
Δendorphin = valence_raw > endorphin
             ? 0.3 · (valence_raw − endorphin)    # ascent
             : 0.09 · (valence_raw − endorphin)   # descent at 0.3× ascent rate
# Symmetric EMA is D (Enhanced Mode).
# Source: Neuralis v1 (BASE_SHA, psi_core.py L64-71).
```

**Five-dimensional affect state**:

| Axis | Symbol | Domain | Description |
|------|--------|--------|-------------|
| Pleasure | P | [-1, 1] | Hedonic tone |
| Arousal | A | [0, 1] | Activation level |
| Dominance | D | 0.5 (fixed) | Control (constant per current design) |
| Social | S | [0, 1] | Social warmth |
| Stress | St | [0, 1] | Pressure/cortisol analogue |

**Coupling matrix** (5×5, 8 non-zero terms including St←P −0.4):

```
ΔP =  w_PP·P  + 0      + 0      + w_PS·S  + 0
ΔA =  0      + w_AA·A  + 0      + 0       + w_ASt·St
ΔD =  0      + 0      + 0      + 0       + 0          (D fixed)
ΔS =  w_SP·P + 0      + 0      + w_SS·S  + 0
ΔSt = w_StP·P + 0      + 0      + 0       + w_StSt·St   # St←P −0.4
```

**8 non-zero terms**: w_PP, w_PS, w_AA, w_ASt, w_SP, w_SS, w_StP, w_StSt

**1/f noise**: Pink noise generator added to affect state. Amplitude configurable.

**Update order**: 1. Coupling matrix multiplication → 2. 1/f noise addition → 3. Clamp per-dimension domain → 4. NaN guard → 5. Endorphin update

**Emotional inertia** (Neuralis D — not from MicroPsi2):

```
e(t+1) = e(t) + λ · (e_target − e(t))
```

Where `λ = 0.01` (inertia factor, numerically borrowed from MicroPsi2 JOY_DECAY_FACTOR). Applied to all 5 dimensions.

NOTE: MicroPsi2 joy decay uses sign-hold + copysign decay, NOT EMA. The EMA formula is a Neuralis design decision.

**Affective events** (18 v1 canonical events):

| # | Event | Effect |
|---|-------|--------|
| 1 | user_engagement | P+, A+ |
| 2 | task_success | P+, COMPETENCE+ |
| 3 | task_failure | P-, COMPETENCE- |
| 4 | surprise | A+ |
| 5 | threat | St+, A+ |
| 6 | praise | S+, P+ |
| 7 | criticism | S-, P- |
| 8 | comfort | S+ |
| 9 | discomfort | S- |
| 10 | novelty | A+ |
| 11 | competence_success | COMPETENCE+, P+ |
| 12 | competence_failure | COMPETENCE-, P- |
| 13 | autonomy_granted | AUTONOMY+ |
| 14 | autonomy_denied | AUTONOMY- |
| 15 | relatedness_renewed | RELATEDNESS+, S+ |
| 16 | relatedness_loss | RELATEDNESS-, S- |
| 17 | growth_milestone | GROWTH+, P+ |
| 18 | growth_stagnation | GROWTH-, P- |

**Source**: Neuralis v1 (BASE_SHA, `laap/affective.py` L43–62). Unknown events return False per PsiBackend v1 contract.

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

**Transitions**: Hysteresis gating (from autonomic, MIT, `a7684e1a`, `gate.rs`). Separate enter/exit thresholds + minimum hold time to prevent oscillation.

**Source**: Neuralis v1 + autonomic HysteresisGate (MIT, `a7684e1a`).

---

### 2.4 EventReducer

**Pattern**: Event sourcing from autonomic (MIT, `a7684e1a`, `event.rs`).

```
PsiEvent → EventReducer → StateProjection → Hysteresis → Gating → Snapshot
```

- `PsiEvent`: enum with type, payload, timestamp
- `EventReducer`: `fold(events, |state, event| match event { ... })` — pure function, no I/O
- `StateProjection`: derives current state from event sequence
- `Hysteresis`: applies hysteresis thresholds to state transitions
- `Gating`: produces GatingDecision (Enter/Exit/Stay/Block)
- `Snapshot`: atomic copy of current state

The reducer is a pure fold + evaluate — no I/O, deterministic, testable.

**Source**: autonomic (MIT, `a7684e1a`). life (MIT, `7f121216`, `homeostatic.rs`).

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

**Source**: Neuralis design (D). Spin-sleep (MIT, `38b0799`, E1). See `2000hz-runtime-spec.md`.

---

### Tier B: 100Hz Snapshot Loop

**Purpose**: State publishing, metric aggregation.

**Operations**:
- Atomic read of RingBuffer → immutable Snapshot
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
    event_queue: Vec<PsiEvent>, // NOT part of state snapshot — separate queue
}
```

**Mapping: v2 Snapshot → v1 PsiState** (required 6 fields per `psi-state.schema.json`):

| v2 field | v1 schema field | Notes |
|----------|----------------|-------|
| `needs` → `needs` | `[Need { name, current, target, ... }]` | Same 5 needs, identical order |
| `drives` → `drives` | `[f64; 5]` | Computed from needs at mapping time |
| `affect` → `affect` | `{ P, A, D, S, St }` | D is always 0.5 in v1 |
| `attention_state` → `attention` | `enum { IDLE, TASK, LEARNING, PLANNING }` | 4 values only |
| `logical_time` → `timestamp` | u64 — must be epoch-relative | `epoch + tick_index × period` |
| `tick_count` → `tick_count` | u64 | Direct pass-through |

**⚠️ Wall clock (`wall_clock`) is for observability only. It MUST NOT affect replay state. Replay uses `logical_time` exclusively.**

Serialization format: MessagePack or CBOR is a **D decision**. A JSON migration path is required for v1 contract compliance (§4 of PsiBackend contract: `get_state()` must be JSON-serializable).

---

## 7. UNKNOWN Items

| Item | Reason |
|------|--------|
| Optimal OU process θ per need | Requires empirical calibration |
| Serotonin modulation factor (0.3) | Theoretical value. Needs calibration. |
| 1/f noise amplitude | Unknown. Requires tuning. |
| Coupling matrix coefficients | Known structure (8 terms), values TBD. |
| Hysteresis thresholds for attention gates | Must be tuned on real usage. |
| Acceptable deadline miss ratio | Depends on application requirements. |
| Spin-sleep accuracy on Apple Silicon | E1 claim only. Must benchmark. |
| Deterministic replay across Rust/Python boundary | Float format differences may cause divergence. |
| Hybrid mode latency | Channel overhead between Rust 2000Hz and Python 10Hz unknown. |