# Neuralis PsiEngine v2 (Rust)

2000Hz PSI fast loop. Implements `docs/rust-psi/neuralis-psi-v2-minimal-spec.md`
and `docs/rust-psi/2000hz-runtime-spec.md` (BASE_SHA `ab14499`).

```
PsiEngine
├─ NeedDynamics      needs.rs      5-need OU process, serumtonin, drives
├─ AffectDynamics    affect.rs     5D PAD+S+St, coupling, 1/f noise, endorphin
├─ AttentionGate     attention.rs  IDLE/TASK/LEARNING/PLANNING, hysteresis
├─ EventReducer      events.rs     18 affective events, pure fold, no I/O
├─ SnapshotPublisher snapshot.rs   atomic snapshot cell, 100Hz publish
├─ TickMetrics       metrics.rs    hdrhistogram, deadline miss, drift
└─ 2000Hz runtime    runtime.rs    spin-sleep, catch-up, circuit breaker
```

## Build / test / bench

```bash
cd rust
cargo test --release          # 45 unit + integration tests (~0.2s)
cargo build --release
./target/release/psi-bench                # 60s smoke (spec acceptance)
./target/release/psi-bench --seconds 600  # 10min sustained
./target/release/psi-bench --seconds 3600 # 60min soak
```

psi-bench exits 0 only if every acceptance threshold passes
(rate ≥ 2000/s, miss < 1%, peak < 500µs, p99 < 200µs, |drift| < 10ms/60s).

## Measured on Apple Silicon (macOS 26.3, M-series) — 60s smoke

| Metric | Threshold | Measured |
|---|---|---|
| Sustained tick rate | ≥ 2000/s | 2000.0/s (120,012 ticks) |
| Deadline miss ratio | < 1% | 0.0000% |
| Peak compute | < 500µs | 35µs |
| p99 compute | < 200µs | 11µs |
| Accumulated drift | < 10ms/60s | 0µs |
| CPU (informational) | ~25% of one core | 24.8% |

## Field notes (E1 → E0)

The spec's 125µs spin-last window is only achievable on macOS when the
loop thread has the **mach time-constraint (real-time) policy** — the
runtime sets it automatically (`runtime.rs::raise_thread_priority`).
Without it, `thread::sleep` overshoots sub-ms waits by whole milliseconds
(~1300Hz effective). Full-period spinning is NOT a substitute: it burns a
core and still gets preempted every 10-20s under ambient load. Calibrate
other platforms with `psi-bench --spin-us`.

## Determinism

Same seed + same events at the same tick indices → bit-identical state
sequence (`tests/determinism.rs`). Single `StdRng`, fixed update order
(Need → Affect → Attention → EventReducer → Snapshot), f64 non-SIMD,
`codegen-units=1`.

## Not in this milestone (known gaps)

- Python ↔ Rust coexistence (`NEURALIS_PSI_BACKEND` env var, M3 backend
  factory, hybrid mode) — engine runs standalone only.
- MessagePack/CBOR snapshot serialization for the Python B-surface.
- Tier C cognitive loop (motive competition beyond gate selection, policy
  adjustment, pymdp FPI 1-step).
- Coupling weights / gate thresholds / noise amplitude are defaults
  pending calibration (spec §7 UNKNOWN items). Coupling defaults satisfy
  the documented 2×2 stability criterion (det > 0, trace < 0).
