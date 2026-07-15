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

**Update order**: 1. OU process → 2. Serumtonin modulation → 3. Clamp [0, 1] → 4. NaN guard

**Serumtonin modulation**:

```
θ' = θ · (1 − 0.3 · serumtonin_level)
```

Where `serumtonin_level ∈ [0, 1]`. Higher serumtonin → slower decay (need satisfaction lasts longer).

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
endorphin = 0.7·endorphin + 0.3·valence_raw   # slow-release smoothing
```

**Five-dimensional affect state**:

| Axis | Symbol | Domain | Description |
|------|--------|--------|-------------|
| Pleasure | P | [-1, 1] | Hedonic tone |
| Arousal | A | [0, 1] | Activation level |
| Dominance | D | 0.5 (fixed) | Control (constant per current design) |
| Social | S | [0, 1] | Social warmth |
| Stress | St | [0, 1] | Pressure/cortisol analogue |

**Coupling matrix** (5×5, 7 non-zero terms):

```
ΔP =  w_PP·P  + 0      + 0      + w_PS·S  + 0
ΔA =  0      + w_AA·A  + 0      + 0       + w_ASt·St
ΔD =  0      + 0      + 0      + 0       + 0          (D fixed)
ΔS =  w_SP·P + 0      + 0      + w_SS·S  + 0
ΔSt = 0      + w_StA·A + 0      + 0       + w_StSt·St
```

**7 non-zero terms**: w_PP, w_PS, w_AA, w_ASt, w_SP, w_SS, w_StA, w_StSt

**1/f noise**: Pink noise generator added to affect state. Amplitude configurable.

**Update order**: 1. Coupling matrix multiplication → 2. 1/f noise addition → 3. Clamp per-dimension domain → 4. NaN guard → 5. Endorphin update

**Emotional inertia** (adapted from MicroPsi2 sustaining joy, MIT):

```
e(t+1) = e(t) + λ · (e_target − e(t))
```

Where `λ = 0.01` (inertia factor). Applied to all 5 dimensions.

**Affective events** (18 events):

| # | Event | Effect |
|---|-------|--------|
| 1 | GOAL_ACHIEVED | P+ |
| 2 | GOAL_FAILED | P- |
| 3 | SURPRISE_POSITIVE | A+, P+ |
| 4 | SURPRISE_NEGATIVE | A+, P- |
| 5 | SOCIAL_PRAISE | S+, P+ |
| 6 | SOCIAL_CRITICISM | S-, P- |
| 7 | THREAT_DETECTED | St+, A+ |
| 8 | THREAT_RESOLVED | St- |
| 9 | NOVELTY_HIGH | A+ |
| 10 | NOVELTY_LOW | A- |
| 11 | COMPETENCE_SUCCESS | COMPETENCE+, P+ |
| 12 | COMPETENCE_FAILURE | COMPETENCE-, P- |
| 13 | AUTONOMY_GRANTED | AUTONOMY+ |
| 14 | AUTONOMY_DENIED | AUTONOMY- |
| 15 | RELATEDNESS_RENEWED | RELATEDNESS+, S+ |
| 16 | RELATEDNESS_LOSS | RELATEDNESS-, S- |
| 17 | GROWTH_MILESTONE | GROWTH+, P+ |
| 18 | GROWTH_STAGNATION | GROWTH-, P- |

**Cognitive biases** (8 biases):

| # | Bias | Mechanism |
|---|------|-----------|
| 1 | Optimism | Valence shift +0.1 |
| 2 | Pessimism | Valence shift -0.1 |
| 3 | Confirmation | Prediction error discount |
| 4 | Recency | Higher weight on recent events |
| 5 | Availability | Higher weight on vivid events |
| 6 | Anchoring | Slow adjustment from initial value |
| 7 | Egocentric | Social weight discount |
| 8 | Projection | Self-state attributed to others |

**Source**: Neuralis v1 (BASE_SHA, `psi_backend.py`). MicroPsi2 joy decay (MIT, `74a2642d`, `emotional_modulators.py`).

---

### 2.3 AttentionGate

**Four states** (no SOCIAL state — removed from Neuralis v1 design):

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

**Pattern**: Atomic snapshot from bounded ring buffer.

```
RingBuffer → AtomicRead → Snapshot → Publish (via channel)
```

- RingBuffer: fixed-size, pre-allocated, lock-free (atomic head/tail indices)
- Snapshot: immutable struct copy of current PsiState
- Publish: sent to snapshot channel (consumed by 100Hz loop)
- Schema compliance: Snapshot struct must match B-surface contract

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

**Purpose**: Physiological regulation — need decay, affect inertia, prediction error smoothing, timing metrics.

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

**Implementation**: Spin-sleep + `std::time::Instant` + bounded ring buffer + atomic snapshot.

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
| Floating-point policy | Same binary result on same input | f64, non-SIMD, round-trip deterministic. No `-ffast-math`. |

**RNG**: Single `rand::rngs::StdRng` seeded from config. One RNG per PsiEngine instance. NOT two RNGs (Neuralis v1 uses `random.gauss` + `numpy` — non-symmetric).

**Two identical runs with same seed + same events → identical state sequence**.

---

## 6. Schema Contract Compliance

**B-surface compatibility**: Snapshot struct must match the same schema as `PsiState` in Python.

```rust
// B-surface contract (pseudocode, not final)
struct PsiSnapshot {
    needs: [Need; 5],          // same order as Python
    drives: [f64; 5],
    affect: Affect5D,          // P, A, D, S, St
    attention_state: GateState, // IDLE/TASK/LEARNING/PLANNING
    timestamp: u64,             // microseconds since epoch
    tick_count: u64,
    metrics: TickMetrics,
}
```

Serialization format: MessagePack or CBOR (binary, not JSON, for 100Hz loop).

---

## 7. UNKNOWN Items

| Item | Reason |
|------|--------|
| Optimal OU process θ per need | Requires empirical calibration |
| Serumtonin modulation factor (0.3) | Theoretical value. Needs calibration. |
| 1/f noise amplitude | Unknown. Requires tuning. |
| Coupling matrix coefficients | Known structure (7 terms), values TBD. |
| Hysteresis thresholds for attention gates | Must be tuned on real usage. |
| Acceptable deadline miss ratio | Depends on application requirements. |
| Spin-sleep accuracy on Apple Silicon | E1 claim only. Must benchmark. |
| Deterministic replay across Rust/Python boundary | Float format differences may cause divergence. |
| Hybrid mode latency | Channel overhead between Rust 2000Hz and Python 10Hz unknown. |