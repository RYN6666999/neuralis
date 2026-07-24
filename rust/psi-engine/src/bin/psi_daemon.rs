//! psi-daemon — long-running 2000Hz PSI loop that publishes the native
//! `state/latest.json` every N ms (M3 B-route, subprocess backend).
//!
//! The Rust engine owns the state-file contract the author designed for:
//! psi core writes state every ~100ms, the Python side reads it. This is
//! the isolation-safe alternative to PyO3 — a crash here dies alone and
//! the Python watchdog restarts it; the atomic tmp+rename keeps readers
//! from ever seeing a torn file.
//!
//! Usage: psi-daemon --state-file PATH [--seed S] [--write-ms M] [--spin-us U]
//!
//! Runs until SIGTERM/SIGKILL (Python `RustPsiBackend.stop()`), or exits
//! after `--max-seconds N` when set (test/soak harness). B1 scope: publish
//! only. The Python→Rust input channel (process_input / events) is B2.

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use psi_engine::runtime::run_for;
use psi_engine::statefile::{snapshot_to_json, write_atomic};
use psi_engine::{run, PsiConfig, PsiEngine};

struct Args {
    state_file: PathBuf,
    seed: u64,
    write_ms: u64,
    spin_us: u64,
    max_seconds: u64, // 0 = run forever (daemon); >0 = test/soak cap
}

fn parse_args() -> Args {
    let mut a = Args {
        state_file: PathBuf::new(),
        seed: 0,
        write_ms: 100,
        spin_us: 0,
        max_seconds: 0,
    };
    let argv: Vec<String> = std::env::args().collect();
    let mut i = 1;
    let take = |argv: &[String], i: usize| -> String {
        argv.get(i + 1).cloned().unwrap_or_else(|| {
            eprintln!("missing value for {}", argv[i]);
            std::process::exit(2);
        })
    };
    let num = |s: String, flag: &str| -> u64 {
        s.parse().unwrap_or_else(|_| {
            eprintln!("bad number for {flag}: {s}");
            std::process::exit(2);
        })
    };
    while i < argv.len() {
        match argv[i].as_str() {
            "--state-file" => {
                a.state_file = PathBuf::from(take(&argv, i));
                i += 2;
            }
            "--seed" => {
                a.seed = num(take(&argv, i), "--seed");
                i += 2;
            }
            "--write-ms" => {
                a.write_ms = num(take(&argv, i), "--write-ms").max(1);
                i += 2;
            }
            "--spin-us" => {
                a.spin_us = num(take(&argv, i), "--spin-us");
                i += 2;
            }
            "--max-seconds" => {
                a.max_seconds = num(take(&argv, i), "--max-seconds");
                i += 2;
            }
            other => {
                eprintln!("unknown arg {other}");
                eprintln!("usage: psi-daemon --state-file PATH [--seed S] [--write-ms M] [--spin-us U] [--max-seconds N]");
                std::process::exit(2);
            }
        }
    }
    if a.state_file.as_os_str().is_empty() {
        eprintln!("--state-file is required");
        std::process::exit(2);
    }
    a
}

fn unix_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn main() {
    let args = parse_args();
    let mut cfg = PsiConfig { seed: args.seed, ..PsiConfig::default() };
    if args.spin_us > 0 {
        cfg.runtime.spin_window_us = args.spin_us as u32;
    }

    let mut engine = PsiEngine::new(cfg);
    let handle = engine.handle();
    let stop = Arc::new(AtomicBool::new(false));
    let boot = Instant::now();

    eprintln!(
        "psi-daemon: state-file={} write={}ms seed={} max_seconds={}",
        args.state_file.display(),
        args.write_ms,
        args.seed,
        args.max_seconds
    );

    std::thread::scope(|s| {
        // Publisher — read the snapshot cell every write_ms, atomic-write.
        let pub_stop = Arc::clone(&stop);
        let pub_handle = handle.clone();
        let path = args.state_file.clone();
        let period = Duration::from_millis(args.write_ms);
        s.spawn(move || {
            let mut warned = false;
            while !pub_stop.load(Ordering::Relaxed) {
                let snap = pub_handle.latest();
                let json = snapshot_to_json(
                    &snap,
                    boot.elapsed().as_secs_f64(),
                    unix_secs(),
                );
                if let Err(e) = write_atomic(&path, &json) {
                    // Best-effort: a transient FS error must not kill the
                    // loop. Warn once, keep publishing.
                    if !warned {
                        eprintln!("psi-daemon: state write failed: {e}");
                        warned = true;
                    }
                }
                std::thread::sleep(period);
            }
        });

        // Optional stop timer (test/soak). 0 = daemon runs until signalled.
        if args.max_seconds > 0 {
            let timer_stop = Arc::clone(&stop);
            let secs = args.max_seconds;
            s.spawn(move || {
                std::thread::sleep(Duration::from_secs(secs));
                timer_stop.store(true, Ordering::Relaxed);
            });
            // Bounded run so the scope joins cleanly after the timer.
            run_for(&mut engine, Duration::from_secs(secs + 1));
        } else {
            // Daemon: block on the loop until SIGTERM kills the process.
            let _ = run(&mut engine, &stop);
        }
    });
}
