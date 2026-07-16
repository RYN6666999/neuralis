# 2000Hz Runtime Specification — Rust PsiEngine Fast Loop

| Field | Value |
|-------|-------|
| **BASE_SHA** | `ab14499ec1d5f30e84b85c56e6c780c7eb4d6913` |
| **Date** | 2026-07-15 |
| **Status** | Draft — minimal viable spec for 2000Hz fast loop |
| **Author** | Wolf 8 (Document Writer) — synthesis of Wolf 1–7 |

## 1. Target

| Parameter | Value | Notes |
|-----------|-------|-------|
| Period | 500 µs | Per tick |
| Sustained tick rate | ≥2000 ticks/s | Not burst — must sustain |
| Cycle budget | 500 µs | Total: compute + sleep + jitter |
| Compute budget | ≤375 µs | Leaves 125 µs sleep margin |
| CPU budget | 1 core | Spin-sleep uses ~25% of one core |

## 2. Spin-Sleep Analysis

### How Spin-Sleep Works

The `spin-sleep` crate (Apache-2.0, SHA `38b0799`) provides a hybrid sleep strategy:

1. **Requested sleep duration** → if ≥ threshold, delegate to `std::thread::sleep()` (OS yields the thread)
2. **Spin-last phase**: For the final ~125µs, enter a busy-wait loop polling `std::time::Instant` until the deadline

This two-phase approach gives:
- **OS sleep** for the bulk of the wait (does not consume CPU)
- **Spin loop** for the final portion (consumes 100% of one core, but achieves microsecond-level precision)

### 125µs Accuracy Claim

**Evidence level**: E1 (author documentation). NOT E0 — the claimed accuracy has not been independently benchmarked on target hardware (Apple Silicon).

The crate's own tests include a `passes_eventually!` mechanism (src/lib.rs L251-269, `for _ in 0..50` retry loop) — tests may fail up to 50 times under load before succeeding. **Evidence level**: E0 (real code, pinned SHA). This does not disqualify the crate, but it means:

- **spin-sleep is NOT hard real-time**. It provides best-effort microsecond precision under normal load.
- Under OS scheduling pressure (context switches, interrupt storms), individual ticks may exceed 500µs.
- The deadline miss detection system (section 6) is the safety net, not spin-sleep itself.

### CPU Cost

At 2000Hz with 125µs spin per tick:
- Spin portion: 125µs × 2000 = 250ms/s = **25% of one core** dedicated to busy-waiting
- **Evidence level**: I (inference). Theoretical estimate: 125µs × 2000/s = 250ms/s = 25%.
- For reference, task-008 measured 24.8% on this specific platform (Apple Silicon single-machine).
- This is acceptable for a dedicated PSI thread on a multi-core system
- If CPU budget is tighter, reduce spin-last window (at the cost of occasional deadline misses)

### Implementation: `spin_sleep` API

```rust
use spin_sleep::SpinSleeper;

let sleeper = SpinSleeper::default(); // 125µs spin-last window (default = 125_000ns)
// Note: SpinSleeper::new(n) takes nanoseconds (SubsecondNanoseconds), not microseconds.
// SpinSleeper::default() sets native_accuracy_ns = 125_000.
let mut target = std::time::Instant::now();

loop {
    let tick_start = std::time::Instant::now();
    // ... compute ...
    let tick_end = std::time::Instant::now();
    let elapsed = tick_end - tick_start;

    let next_tick = target + std::time::Duration::from_micros(500);
    sleeper.sleep_until(next_tick);
    target = next_tick;
}
```

Compile-verified against `spin_sleep = "=1.3.3"` (rustc 1.97.0, 2026-07-16): `SpinSleeper::default()`, `sleep_until(Instant)` and the `mut target` pattern build clean (the unused `elapsed` is consumed by metrics in real code).

**Source**: spin-sleep crate (Apache-2.0, `38b0799c09df30b5f034f440546a59bd7a3b028b`). E1 evidence for accuracy.

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      2000Hz Runtime                               │
│                                                                   │
│  ┌──────────────┐     ┌────────────────────┐     ┌────────────┐ │
│  │    Tick      │────▶│    Compute Phase    │────▶│  SpinSleep │ │
│  │  (Instant)   │     │ (≤375µs, no I/O)    │     │ (125µs)    │ │
│  └──────────────┘     └─────────┬──────────┘     └──────┬─────┘ │
│                                │                         │       │
│                                ▼                         │       │
│                 ┌──────────────────────────┐             │       │
│                 │ Deadline Miss Detection  │◀────────────┘       │
│                 │ (tick_end - tick_start)  │                     │
│                 └──────────┬───────────────┘                     │
│                            │                                     │
│                            ▼                                     │
│                 ┌──────────────────────────┐                     │
│                 │   Metrics (hdrhistogram   │                     │
│                 │   + drift counter)        │                     │
│                 └──────────────────────────┘                     │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Event Queue (Bounded RingBuffer, lock-free)             │    │
│  │  → push from outside threads                             │    │
│  │  → pop during compute phase (no blocking)                │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Snapshot (Atomic Read of PsiState → immutable copy)     │    │
│  │  → consumed by 100Hz snapshot loop                       │    │
│  │  → NOT from ring buffer (ring buffer is events-only)     │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Bounded Ring Buffer

- Fixed size at startup (e.g., 1024 slots)
- Lock-free: atomic head and tail indices (std::sync::atomic)
- Push: CAS on head. If full, overwrite oldest (coalesce).
- Pop: CAS on tail. Returns None if empty.
- No heap allocation after initialization.

### Atomic Snapshot

- Read lock-free from PsiState (atomic cell), NOT from ring buffer
- Copy to immutable struct (PsiSnapshot)
- Published via channel to 100Hz consumer

## 4. Metrics

### Measured Values

| Metric | Unit | Instrumentation | Notes |
|--------|------|----------------|-------|
| Compute duration | µs | `Instant::now()` diff at start/end of compute | Indicator 1: actual work time |
| Wake-up lateness | µs | `max(0, actual_start - scheduled_start)` | Indicator 2: scheduling delay (positive = late; D8 definition) |
| Completion deadline miss | bool | `actual_end > scheduled_start + period` | Indicator 3: end-to-end; `completion_deadline = scheduled_start + period` |
| End-to-end tick interval | µs | `actual_start - previous_actual_start` | Indicator 4: true period between consecutive starts |
| Net phase offset | µs | `Σ(actual_interval - 500µs)` | Running sum; positive and negative cancel (R05) |
| Max absolute phase error | µs | `max\|phase_error\|` | Worst-case phase deviation (not cancelled by sign) |
| Skipped slots | count | Jump in tick index | Ticks dropped entirely |
| Catch-up count | count | Burst recovery events | How many times burst mode was entered |
| Queue depth | count | Ring buffer occupancy at pop | Events pending in ring buffer |
| Dropped/coalesced events | count | CAS overwrite count | Events lost due to ring buffer full |

### hdrhistogram

Use `hdrhistogram` crate to record compute duration. Record after each tick.

| Percentile | Purpose |
|------------|---------|
| p50 | Median tick duration |
| p95 | Typical worst case |
| p99 | Rare outliers |
| p99.9 | Extreme outliers |
| Max | Absolute worst case |

### Test Durations

| Test | Duration | Purpose |
|------|----------|---------|
| Smoke | 60 s | Quick verification |
| Sustained | 10 min | Warm + steady state |
| Soak | 60 min | Recommended for confidence |

### Acceptance Thresholds

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Sustained tick rate | ≥2000 ticks/s | Measured over 60s. Rate = actual completed ticks / wall time. |
| Completion deadline miss ratio | <1% | Over any 60s window. Miss = `actual_end > scheduled_start + period` (Indicator 3, per §4 D8). ⚠️ psi-bench currently uses `rate ≥ 2000 × 0.999` — this softening must be disclosed. |
| Peak compute duration | <500µs | No single tick exceeds period |
| p99 compute duration | <200µs | 99th percentile of work |
| Wake-up lateness p99 | <50µs | Scheduling delay, 99th percentile |
| Net phase offset | <10ms over 60s | 500µs × 2000 = 1s/s, offset <1%. Positive and negative cancel. |
| Max absolute phase error | <10ms over 60s | Worst-case phase deviation (not cancelled by sign) |
| Skipped slots | 0 | No dropped ticks under sustained load |

**⚠️ These thresholds must be calibrated on target hardware. They are starting estimates, not guaranteed.**

**⚠️ Benchmark context (from D9):** Current task-008 data is:
- 590 seconds, not a full 600 seconds
- Apple Silicon single-machine results only
- 2000 ticks/s is the measured rate on that run
- 0% miss is under the old compute-only miss definition
- NOT a hard real-time guarantee
- NOT cross-platform proof
- NOT a full 10-minute acceptance
- 60-minute soak not yet completed

## 5. Overload Behavior

### Three Recovery Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| **Skip** (default) | Drop the missed tick. Advance target to next period. | Light overload, transient spike |
| **Burst** | Run next tick immediately after compute finishes. Skip sleep. | Brief overload, need to catch up |
| **Delay** | Shift schedule: `target = now + 500µs` (reset, not catch up). | Sustained overload, drift is acceptable |

### Selection Logic

```
if compute_duration < 500µs:
    normal: sleep until next target
    # no drift accumulation

elif compute_duration < 1000µs:
    # single tick overrun
    strategy = Skip (default)
    target += 500µs  # skip one tick
    drift += compute_duration - 500µs

elif compute_duration < 5000µs:
    # multi-tick overrun
    strategy = Skip
    target = now + 500µs  # reset, skip all missed
    drift += compute_duration - 500µs

else:
    # severe overload
    # circuit breaker: reduce rate
    target = now + 5000µs  # temporarily run at 200Hz
    drift += compute_duration - 500µs
    rate_reduction_active = true
```

### Gradual Rate Reduction

When `rate_reduction_active`:
- Run at reduced rate (e.g., 200Hz = 5000µs period)
- After 10 consecutive on-time ticks, restore to 2000Hz
- If another overload within 60s of restoring, drop to 100Hz

### Circuit Breaker

- State: Normal → Degraded → Recovery → Normal
- Normal: 2000Hz operation
- Degraded: Reduced rate
- Recovery: 10 consecutive on-time ticks
- Re-enter Degraded if overload within 60s of recovery

**Source**: Degradation concept from ExoGenesis-Omega (REFERENCE — `prancer-io/ExoGenesis-Omega`, API license=null). Neuralis-specific implementation.

## 6. Deadline Miss Detection Pattern

```rust
use std::time::{Duration, Instant};

struct TickResult {
    compute_duration: Duration,
    wake_lateness: Duration,
    completion_lateness: Duration,
    deadline_miss: bool,
    /// Signed phase error in µs: positive = late, negative = early.
    /// Signed (not clamped to zero) so max |phase error| in §4 is honest.
    phase_error_signed_us: i64,
    tick_index: u64,
    scheduled_start: Instant,
    actual_start: Instant,
    actual_end: Instant,
}

fn tick(compute: impl FnOnce(), tick_index: u64, epoch: Instant) -> TickResult {
    // Scheduled start: epoch + tick_index × period.
    // NOTE: multiply in integer µs — std::time::Duration implements
    // Mul<u32> only, so `Duration::from_micros(500) * tick_index` (u64)
    // does NOT compile.
    let scheduled_start = epoch + Duration::from_micros(500 * tick_index);
    let actual_start = Instant::now();

    // Indicator 1: compute duration (actual work time)
    compute();
    let actual_end = Instant::now();
    let compute_duration = actual_end - actual_start;

    // Indicator 2: wake-up lateness (scheduling delay; positive = late).
    // saturating_duration_since avoids the Instant-subtraction panic when early.
    let wake_lateness = actual_start.saturating_duration_since(scheduled_start);

    // Indicator 3: completion deadline miss (end-to-end)
    let completion_deadline = scheduled_start + Duration::from_micros(500);
    let deadline_miss = actual_end > completion_deadline;
    let completion_lateness = actual_end.saturating_duration_since(completion_deadline);

    // Indicator 4: end-to-end tick interval
    // (computed externally from consecutive actual_start values)

    // Phase tracking — signed, so early ticks are not silently zeroed.
    let phase_error_signed_us = if actual_start >= scheduled_start {
        actual_start.duration_since(scheduled_start).as_micros() as i64
    } else {
        -(scheduled_start.duration_since(actual_start).as_micros() as i64)
    };

    TickResult {
        compute_duration,
        wake_lateness,
        completion_lateness,
        deadline_miss,
        phase_error_signed_us,
        tick_index,
        scheduled_start,
        actual_start,
        actual_end,
    }
}
```

Compile-verified and executed (rustc 1.97.0, 2026-07-16; smoke output: early tick → negative phase error, `deadline_miss=false`).

## 7. Catch-Up Policy

**Default: Skip**. Rationale:
- Skip is the simplest strategy — drop the missed tick and continue
- Burst risks cascading overload (running faster increases CPU contention)
- Delay accumulates persistent drift
- For a PSI system, missing one tick is less harmful than running out of phase

**Configurable**: User can override via `PsiConfig::catch_up_policy`.

## 8. UNKNOWN Items

| Item | Reason |
|------|--------|
| Spin-sleep 125µs accuracy on Apple Silicon | E1 claim only. Not independently verified. |
| spin-sleep test reliability under load | Tests may fail 50 times ("passes_eventually!") |
| Acceptable deadline miss ratio for PsiEngine | Depends on application sensitivity. |
| hdrhistogram memory overhead | Must be measured. Configurable precision. |
| RingBuffer optimal size (1024 slots) | Estimate. Must be tuned. |
| Circuit breaker thresholds | Theoretical. Must be calibrated. |
| CPU contention with other threads | Depends on system load. |
| Tick duration distribution under sustained load | Unknown until benchmarked. |
| Lock-free ring buffer overhead on Apple Silicon | CAS contention under 2000Hz push/pop unknown. |
| Channel latency for snapshot publishing | Depends on channel implementation (crossbeam, flume, std). |

## 9. Summary of Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Sleep strategy | Spin-sleep (hybrid) | Best available for Rust. E1 evidence. |
| Spin-last window | 125 µs | Crate default (`SpinSleeper::default()`, E0: lib.rs L78 `DEFAULT=125_000ns`). **I**: 25% CPU (theoretical: 125µs × 2000/s = 250ms/s). |
| Default catch-up | Skip | Simplest. Least disruptive. |
| Metrics | hdrhistogram | Industry standard for latency measurement. |
| Event queue | Bounded ring buffer | Lock-free, no heap allocation. |
| Overload recovery | Gradual rate reduction | Prevents cascading failure. |
| Circuit breaker | 3-state (Normal/Degraded/Recovery) | Standard pattern. |
| Test durations | 60s smoke, 10min sustained, 60min soak | Increasing confidence. |
| Determinism | Seed + event ordering + update ordering + float policy | See `neuralis-psi-v2-minimal-spec.md` §5. |