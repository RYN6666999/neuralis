//! psi-bench — acceptance benchmark for the 2000Hz fast loop.
//!
//! Runs the engine on a dedicated thread with a 100Hz snapshot consumer
//! and an event producer (simulated Tier D traffic), then scores the run
//! against the acceptance thresholds in 2000hz-runtime-spec.md §4:
//!
//!   sustained rate ≥ 2000 ticks/s, miss ratio < 1%, peak compute < 500µs,
//!   p99 compute < 200µs, |drift| < 10ms per 60s window.
//!
//! Usage: psi-bench [--seconds N] [--seed S] [--events-hz H] [--warmup-s W]
//!   smoke = 60s (default), sustained = 600s, soak = 3600s.
//! A warmup phase (default 2s) runs first and its metrics are discarded —
//! the spec's sustained test is explicitly "warm + steady state"; the
//! first ticks pay one-time page-fault/cache costs.
//! Exit code 0 = all thresholds pass, 1 = at least one failed.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use psi_engine::metrics::TickMetrics;
use psi_engine::{
    run, run_for, AffectiveEvent, PsiConfig, PsiEngine, PsiEvent,
};

fn parse_args() -> (u64, u64, u64, u64, u64) {
    let mut seconds = 60_u64;
    let mut seed = 0_u64;
    let mut events_hz = 10_u64;
    let mut warmup_s = 2_u64;
    let mut spin_us = 0_u64; // 0 = config default
    let args: Vec<String> = std::env::args().collect();
    let mut i = 1;
    while i < args.len() {
        let take = |i: usize| -> u64 {
            args.get(i + 1)
                .and_then(|v| v.parse().ok())
                .unwrap_or_else(|| {
                    eprintln!("bad value for {}", args[i]);
                    std::process::exit(2);
                })
        };
        match args[i].as_str() {
            "--seconds" => {
                seconds = take(i);
                i += 2;
            }
            "--seed" => {
                seed = take(i);
                i += 2;
            }
            "--events-hz" => {
                events_hz = take(i);
                i += 2;
            }
            "--warmup-s" => {
                warmup_s = take(i);
                i += 2;
            }
            "--spin-us" => {
                spin_us = take(i);
                i += 2;
            }
            other => {
                eprintln!("unknown arg {other}");
                eprintln!(
                    "usage: psi-bench [--seconds N] [--seed S] [--events-hz H] [--warmup-s W] [--spin-us U]"
                );
                std::process::exit(2);
            }
        }
    }
    (seconds, seed, events_hz, warmup_s, spin_us)
}

fn main() {
    let (seconds, seed, events_hz, warmup_s, spin_us) = parse_args();
    let mut cfg = PsiConfig::default();
    cfg.seed = seed;
    if spin_us > 0 {
        cfg.runtime.spin_window_us = spin_us as u32;
    }
    let period_us = cfg.runtime.tick_period_us;

    let mut engine = PsiEngine::new(cfg);
    let handle = engine.handle();
    let stop = Arc::new(AtomicBool::new(false));

    println!(
        "psi-bench: {seconds}s @ {}Hz target, seed={seed}, events={events_hz}Hz, warmup={warmup_s}s",
        1_000_000 / period_us
    );

    if warmup_s > 0 {
        run_for(&mut engine, Duration::from_secs(warmup_s));
        engine.metrics = TickMetrics::new(period_us);
    }

    let report = std::thread::scope(|s| {
        // Event producer — simulated Tier D traffic.
        let producer_stop = Arc::clone(&stop);
        let producer_handle = handle.clone();
        s.spawn(move || {
            if events_hz == 0 {
                return;
            }
            let kinds = [
                AffectiveEvent::CompetenceSuccess,
                AffectiveEvent::NoveltyHigh,
                AffectiveEvent::SocialPraise,
                AffectiveEvent::ThreatDetected,
                AffectiveEvent::ThreatResolved,
            ];
            let mut n = 0_usize;
            let period = Duration::from_micros(1_000_000 / events_hz);
            while !producer_stop.load(Ordering::Relaxed) {
                producer_handle.post_event(PsiEvent {
                    kind: kinds[n % kinds.len()],
                    intensity: 0.5,
                    timestamp_us: 0,
                });
                n += 1;
                std::thread::sleep(period);
            }
        });

        // 100Hz snapshot consumer — exercises the Tier B read path.
        let consumer_stop = Arc::clone(&stop);
        let consumer_handle = handle.clone();
        let consumer = s.spawn(move || {
            let mut reads = 0_u64;
            let mut last_tick = 0_u64;
            let mut stale = 0_u64;
            while !consumer_stop.load(Ordering::Relaxed) {
                let snap = consumer_handle.latest();
                reads += 1;
                if snap.tick_count == last_tick {
                    stale += 1;
                }
                last_tick = snap.tick_count;
                std::thread::sleep(Duration::from_millis(10));
            }
            (reads, stale)
        });

        // Stop timer.
        let timer_stop = Arc::clone(&stop);
        s.spawn(move || {
            std::thread::sleep(Duration::from_secs(seconds));
            timer_stop.store(true, Ordering::Relaxed);
        });

        let t0 = Instant::now();
        let run_report = run(&mut engine, &stop);
        let wall = t0.elapsed();
        let (reads, stale) = consumer.join().expect("consumer panicked");
        println!(
            "snapshot consumer: {reads} reads, {stale} stale ({:.2}% fresh)",
            100.0 * (reads - stale) as f64 / reads.max(1) as f64
        );
        let _ = wall;
        run_report
    });

    let m = report.report;
    let rate = report.rate_hz;
    // Drift budget scales with window: 10ms per 60s.
    let drift_budget_us = (10_000.0 * seconds as f64 / 60.0) as i64;

    let target_rate = (1_000_000 / period_us) as f64;
    let checks = [
        ("sustained tick rate", format!("{rate:.1}/s"), rate >= target_rate * 0.999),
        (
            "deadline miss ratio",
            format!("{:.4}%", m.miss_ratio * 100.0),
            m.miss_ratio < 0.01,
        ),
        (
            "peak compute",
            format!("{}µs", m.max_us),
            m.max_us < period_us,
        ),
        ("p99 compute", format!("{}µs", m.p99_us), m.p99_us < 200),
        (
            "accumulated drift",
            format!("{}µs (budget ±{drift_budget_us})", m.drift_us),
            m.drift_us.abs() < drift_budget_us,
        ),
    ];

    println!();
    println!("ticks={} wall={:.1}s breaker_trips={} final_breaker={:?}", m.ticks, report.wall.as_secs_f64(), report.breaker_trips, report.final_breaker);
    println!(
        "compute µs: p50={} p95={} p99={} p99.9={} max={}",
        m.p50_us, m.p95_us, m.p99_us, m.p999_us, m.max_us
    );
    println!(
        "catch-up: skip={} burst={} delay={}",
        m.catchup_skip, m.catchup_burst, m.catchup_delay
    );
    println!();

    let mut all_pass = true;
    for (name, value, pass) in &checks {
        println!(
            "{} {name}: {value}",
            if *pass { "PASS" } else { "FAIL" }
        );
        all_pass &= *pass;
    }

    println!();
    println!("⚠️  thresholds are starting estimates (spec §4) — calibrate on target hardware.");
    std::process::exit(if all_pass { 0 } else { 1 });
}
