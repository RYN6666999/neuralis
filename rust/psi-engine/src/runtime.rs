//! 2000Hz runtime — spin-sleep pacing, overload recovery, circuit breaker
//! (2000hz-runtime-spec.md §2, §5–§7).
//!
//! spin-sleep is NOT hard real-time (E1 evidence, unverified on Apple
//! Silicon); the deadline-miss detector + catch-up policy + circuit
//! breaker are the safety net, not the sleeper.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use spin_sleep::{SpinSleeper, SpinStrategy};

use crate::config::{CatchUpPolicy, RuntimeParams};
use crate::engine::PsiEngine;
use crate::metrics::MetricsReport;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum BreakerState {
    Normal,
    Degraded,
    Recovery,
}

/// Circuit breaker: Normal → Degraded (200Hz) → Recovery (counting
/// on-time ticks) → Normal. Overload again within `relapse_window_s` of a
/// recovery → deeper Degraded (100Hz). Spec §5.
#[derive(Debug)]
pub struct CircuitBreaker {
    params: RuntimeParams,
    state: BreakerState,
    consecutive_on_time: u64,
    depth: u8,
    last_recovery: Option<Instant>,
    pub trips: u64,
}

impl CircuitBreaker {
    pub fn new(params: RuntimeParams) -> Self {
        Self {
            params,
            state: BreakerState::Normal,
            consecutive_on_time: 0,
            depth: 0,
            last_recovery: None,
            trips: 0,
        }
    }

    pub fn state(&self) -> BreakerState {
        self.state
    }

    /// Current tick period given breaker state.
    pub fn period_us(&self) -> u64 {
        match (self.state, self.depth) {
            (BreakerState::Normal, _) => self.params.tick_period_us,
            (_, d) if d >= 2 => self.params.deep_degraded_period_us,
            _ => self.params.degraded_period_us,
        }
    }

    /// Severe overload observed (compute ≥ 10 × period).
    pub fn trip(&mut self, now: Instant) {
        let relapse = self
            .last_recovery
            .map(|t| now.duration_since(t).as_secs() < self.params.relapse_window_s)
            .unwrap_or(false);
        self.depth = if relapse { 2 } else { 1 };
        self.state = BreakerState::Degraded;
        self.consecutive_on_time = 0;
        self.trips += 1;
    }

    /// Feed one tick outcome; may restore Normal.
    pub fn on_tick(&mut self, on_time: bool, now: Instant) {
        match self.state {
            BreakerState::Normal => {}
            BreakerState::Degraded | BreakerState::Recovery => {
                if on_time {
                    self.consecutive_on_time += 1;
                    self.state = BreakerState::Recovery;
                    if self.consecutive_on_time >= self.params.recovery_ticks {
                        self.state = BreakerState::Normal;
                        self.consecutive_on_time = 0;
                        self.last_recovery = Some(now);
                    }
                } else {
                    self.consecutive_on_time = 0;
                    self.state = BreakerState::Degraded;
                }
            }
        }
    }
}

/// Longest sleep-overshoot backlog (in tick slots) the loop will burst
/// through to stay on schedule; beyond this (50ms at 2000Hz) the slots are
/// dropped instead. Applies to late WAKES only — compute overruns follow
/// the configured CatchUpPolicy.
const MAX_CATCHUP_SLOTS: u32 = 100;

#[derive(Debug)]
pub struct RunReport {
    pub wall: Duration,
    pub report: MetricsReport,
    pub breaker_trips: u64,
    pub final_breaker: BreakerState,
    /// Sustained rate over the whole run, ticks/s.
    pub rate_hz: f64,
}

/// Drive the engine until `stop` is set. Blocking call — run it on a
/// dedicated thread; use `PsiHandle` from other threads.
pub fn run(engine: &mut PsiEngine, stop: &AtomicBool) -> RunReport {
    let params = engine.config().runtime;
    raise_thread_priority(params.tick_period_us);
    // SpinSleeper accuracy is in ns: everything closer than this to the
    // deadline is spin-waited. SpinLoopHint instead of the default
    // YieldThread: yield_now() is a syscall macOS uses as a deschedule
    // point (measured: ~7µs median wake lateness + multi-ms outliers).
    let sleeper = SpinSleeper::new(params.spin_window_us * 1_000)
        .with_spin_strategy(SpinStrategy::SpinLoopHint);
    let mut breaker = CircuitBreaker::new(params);

    let epoch = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::ZERO)
        .as_micros() as u64;
    engine.set_epoch_us(epoch);

    let start = Instant::now();
    // Scheduled start of the next tick. Fixed-cadence: advanced from the
    // schedule, not from wall time, so on-time ticks accumulate no drift.
    let mut next_start = start;
    let mut prev_tick_start: Option<Instant> = None;

    while !stop.load(Ordering::Relaxed) {
        let now = Instant::now();
        if next_start > now {
            sleeper.sleep(next_start - now);
        }

        let tick_start = Instant::now();
        if let Some(prev) = prev_tick_start {
            engine
                .metrics
                .record_interval_ns(tick_start.duration_since(prev).as_nanos() as u64);
        }
        prev_tick_start = Some(tick_start);

        // --- COMPUTE PHASE (Tier A only) ---
        engine.tick();
        // --- END COMPUTE PHASE ---

        let compute_us = tick_start.elapsed().as_micros() as u64;
        engine.metrics.record_compute(compute_us);

        let after = Instant::now();
        let period = Duration::from_micros(breaker.period_us());
        let period_us = period.as_micros() as u64;
        let on_time = compute_us <= period_us;
        breaker.on_tick(on_time, after);

        // Overload selection logic (spec §5), thresholds relative to the
        // current period: ≤1p normal, <2p single overrun, <10p multi-tick
        // overrun, ≥10p severe → breaker.
        if compute_us <= period_us {
            next_start += period;
            // Late wake (OS deschedule during sleep) is NOT compute
            // overload: fixed cadence catches up by running the due slots
            // back-to-back (compute is ~1µs, so a 10-slot backlog costs
            // ~10µs and keeps sim time aligned with wall time). Only a
            // pathological gap gets skipped so one multi-second stall
            // cannot trigger a thousand-tick burst.
            if next_start + MAX_CATCHUP_SLOTS * period < after {
                next_start = after + period;
                engine.metrics.record_catchup(CatchUpPolicy::Skip);
            }
        } else if compute_us < 2 * period_us {
            match params.catch_up {
                // This tick overran into the next slot: skip that slot.
                CatchUpPolicy::Skip => next_start += 2 * period,
                // Run the next tick immediately after compute finishes.
                CatchUpPolicy::Burst => next_start = after,
                // Reset the schedule from now (accepts persistent drift).
                CatchUpPolicy::Delay => next_start = after + period,
            }
            engine.metrics.record_catchup(params.catch_up);
        } else if compute_us < 10 * period_us {
            // Multi-tick overrun: reset, skip all missed slots.
            next_start = after + period;
            engine.metrics.record_catchup(CatchUpPolicy::Skip);
        } else {
            // Severe overload: degrade rate (200Hz, then 100Hz on relapse).
            breaker.trip(after);
            next_start = after + Duration::from_micros(breaker.period_us());
            engine.metrics.record_catchup(CatchUpPolicy::Delay);
        }
        engine.metrics.breaker_trips = breaker.trips;
    }

    let wall = start.elapsed();
    let report = engine.metrics.report();
    RunReport {
        wall,
        rate_hz: report.ticks as f64 / wall.as_secs_f64(),
        report,
        breaker_trips: breaker.trips,
        final_breaker: breaker.state(),
    }
}

/// Ask the OS to preempt the fast-loop thread less. Best-effort — errors
/// ignored; the deadline-miss detector remains the real safety net.
///
/// macOS: mach time-constraint policy — the canonical API for sub-ms
/// periodic threads (CoreAudio render threads use it). Without it the
/// default scheduler preempts the loop for multiple ms roughly every
/// 10-20s under ambient load (measured via psi-bench peak-compute).
/// QoS user-interactive is set first as the fallback if the RT request
/// is rejected.
#[cfg(target_os = "macos")]
fn raise_thread_priority(period_us: u64) {
    #[allow(non_camel_case_types)]
    type qos_class_t = std::ffi::c_uint;
    const QOS_CLASS_USER_INTERACTIVE: qos_class_t = 0x21;
    const THREAD_TIME_CONSTRAINT_POLICY: u32 = 2;

    #[repr(C)]
    struct TimeConstraintPolicy {
        period: u32,
        computation: u32,
        constraint: u32,
        preemptible: u32, // boolean_t
    }
    #[repr(C)]
    struct MachTimebaseInfo {
        numer: u32,
        denom: u32,
    }
    extern "C" {
        fn pthread_set_qos_class_self_np(
            qos: qos_class_t,
            relative_priority: std::ffi::c_int,
        ) -> std::ffi::c_int;
        fn mach_thread_self() -> u32;
        fn mach_timebase_info(info: *mut MachTimebaseInfo) -> i32;
        fn thread_policy_set(
            thread: u32,
            flavor: u32,
            policy_info: *const TimeConstraintPolicy,
            count: u32,
        ) -> i32;
    }

    unsafe {
        pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);

        let mut tb = MachTimebaseInfo { numer: 0, denom: 0 };
        if mach_timebase_info(&mut tb) != 0 || tb.numer == 0 {
            return;
        }
        // mach_absolute_time · numer/denom = ns  →  abs = ns · denom/numer.
        let ns_to_abs = |ns: u64| (ns * tb.denom as u64 / tb.numer as u64) as u32;
        let period_ns = period_us * 1_000;
        let policy = TimeConstraintPolicy {
            period: ns_to_abs(period_ns),
            // Declared duty cycle: 20% compute, must finish within 80% of
            // the period. Generous vs the measured ~1µs median compute —
            // understating it invites demotion, overstating wastes RT
            // budget the OS reserves.
            computation: ns_to_abs(period_ns / 5),
            constraint: ns_to_abs(period_ns * 4 / 5),
            preemptible: 1,
        };
        let count = (std::mem::size_of::<TimeConstraintPolicy>()
            / std::mem::size_of::<u32>()) as u32;
        thread_policy_set(
            mach_thread_self(),
            THREAD_TIME_CONSTRAINT_POLICY,
            &policy,
            count,
        );
    }
}

#[cfg(not(target_os = "macos"))]
fn raise_thread_priority(_period_us: u64) {}

/// Convenience wrapper: run for a fixed duration on the current thread.
pub fn run_for(engine: &mut PsiEngine, duration: Duration) -> RunReport {
    let stop = AtomicBool::new(false);
    std::thread::scope(|s| {
        s.spawn(|| {
            std::thread::sleep(duration);
            stop.store(true, Ordering::Relaxed);
        });
        run(engine, &stop)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::PsiConfig;

    fn params() -> RuntimeParams {
        RuntimeParams::default()
    }

    #[test]
    fn breaker_degrades_and_recovers() {
        let mut b = CircuitBreaker::new(params());
        let t0 = Instant::now();
        assert_eq!(b.state(), BreakerState::Normal);
        assert_eq!(b.period_us(), 500);

        b.trip(t0);
        assert_eq!(b.state(), BreakerState::Degraded);
        assert_eq!(b.period_us(), 5_000, "first degrade = 200Hz");

        for _ in 0..9 {
            b.on_tick(true, t0);
            assert_eq!(b.state(), BreakerState::Recovery);
        }
        b.on_tick(true, t0);
        assert_eq!(b.state(), BreakerState::Normal);
        assert_eq!(b.period_us(), 500);
    }

    #[test]
    fn miss_during_recovery_resets_count() {
        let mut b = CircuitBreaker::new(params());
        let t0 = Instant::now();
        b.trip(t0);
        for _ in 0..5 {
            b.on_tick(true, t0);
        }
        b.on_tick(false, t0);
        assert_eq!(b.state(), BreakerState::Degraded);
        // Needs the full run again.
        for _ in 0..9 {
            b.on_tick(true, t0);
            assert_ne!(b.state(), BreakerState::Normal);
        }
        b.on_tick(true, t0);
        assert_eq!(b.state(), BreakerState::Normal);
    }

    #[test]
    fn relapse_within_window_degrades_deeper() {
        let mut b = CircuitBreaker::new(params());
        let t0 = Instant::now();
        b.trip(t0);
        for _ in 0..10 {
            b.on_tick(true, t0);
        }
        assert_eq!(b.state(), BreakerState::Normal);
        // Second overload immediately after recovery → 100Hz.
        b.trip(t0 + Duration::from_secs(1));
        assert_eq!(b.period_us(), 10_000, "relapse = deep degrade (100Hz)");
        assert_eq!(b.trips, 2);
    }

    /// Short real-clock smoke: the loop runs near the target rate for
    /// 200ms. Loose bound — CI boxes jitter; the real acceptance run is
    /// the psi-bench binary (60s window).
    #[test]
    fn loop_produces_ticks_at_roughly_target_rate() {
        let mut engine = PsiEngine::new(PsiConfig::default());
        let r = run_for(&mut engine, Duration::from_millis(200));
        assert!(
            r.report.ticks > 100,
            "expected >100 ticks in 200ms, got {}",
            r.report.ticks
        );
        assert!(r.rate_hz > 500.0, "rate {} implausibly low", r.rate_hz);
    }
}
