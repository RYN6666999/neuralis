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
//!        [--event-fifo PATH] [--max-seconds N]
//!
//! Runs until SIGTERM/SIGKILL (Python `RustPsiBackend.stop()`), or exits
//! after `--max-seconds N` when set (test/soak harness). B1 scope: publish
//! only. B2: `--event-fifo` enables a FIFO-based event input channel.

use std::ffi::CString;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use psi_engine::events::PsiEvent;
use psi_engine::runtime::run_for;
use psi_engine::statefile::{snapshot_to_json, write_atomic};
use psi_engine::{run, PsiConfig, PsiEngine};

struct Args {
    state_file: PathBuf,
    seed: u64,
    write_ms: u64,
    spin_us: u64,
    max_seconds: u64, // 0 = run forever (daemon); >0 = test/soak cap
    event_fifo: Option<PathBuf>,
}

#[cfg(unix)]
extern "C" {
    fn mkfifo(path: *const std::ffi::c_char, mode: std::ffi::c_uint) -> std::ffi::c_int;
}

/// Create a FIFO (named pipe) at `path`. Removes stale file first, then
/// creates a fresh FIFO. Panics on failure.
#[cfg(unix)]
fn create_fifo(path: &PathBuf) {
    let _ = fs::remove_file(path);
    let cstr = CString::new(path.as_os_str().as_encoded_bytes()).unwrap();
    let ret = unsafe { mkfifo(cstr.as_ptr(), 0o600) };
    if ret != 0 {
        panic!("mkfifo({}) failed: {}", path.display(),
               std::io::Error::last_os_error());
    }
}

fn parse_args() -> Args {
    let mut a = Args {
        state_file: PathBuf::new(),
        seed: 0,
        write_ms: 100,
        spin_us: 0,
        max_seconds: 0,
        event_fifo: None,
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
            "--event-fifo" => {
                a.event_fifo = Some(PathBuf::from(take(&argv, i)));
                i += 2;
            }
            "--max-seconds" => {
                a.max_seconds = num(take(&argv, i), "--max-seconds");
                i += 2;
            }
            other => {
                eprintln!("unknown arg {other}");
                eprintln!("usage: psi-daemon --state-file PATH [--seed S] [--write-ms M] [--spin-us U] [--event-fifo PATH] [--max-seconds N]");
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

    let fifo_desc = args.event_fifo.as_ref()
        .map(|f| format!(" event-fifo={}", f.display()))
        .unwrap_or_default();
    eprintln!(
        "psi-daemon: state-file={} write={}ms seed={} max_seconds={}{}",
        args.state_file.display(),
        args.write_ms,
        args.seed,
        args.max_seconds,
        fifo_desc,
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

        // Event FIFO reader — B2 input channel. Reads lines from the FIFO,
        // parses them as "EventName,intensity" and posts to the engine.
        if let Some(ref fifo_path) = args.event_fifo {
            let ev_stop = Arc::clone(&stop);
            let ev_handle = handle.clone();
            let path = fifo_path.clone();
            s.spawn(move || {
                // Ensure the FIFO exists (create it).
                let _ = fs::remove_file(&path);
                create_fifo(&path);
                // Open the FIFO for reading (blocks until a writer opens it).
                // Re-open on each writer close (FIFO semantics: read returns
                // EOF when the last writer closes; re-open for the next one).
                while !ev_stop.load(Ordering::Relaxed) {
                    match fs::File::open(&path) {
                        Ok(file) => {
                            let reader = BufReader::new(file);
                            for line in reader.lines() {
                                if ev_stop.load(Ordering::Relaxed) {
                                    return;
                                }
                                match line {
                                    Ok(text) => {
                                        let text = text.trim().to_owned();
                                        if text.is_empty() { continue; }
                                        let (name, intensity) = match text.split_once(',') {
                                            Some((n, i)) => (n, i.parse::<f64>().unwrap_or(1.0)),
                                            None => (text.as_str(), 1.0),
                                        };
                                        if let Some(kind) = psi_engine::events::AffectiveEvent::from_name(name) {
                                            ev_handle.post_event(PsiEvent {
                                                kind,
                                                intensity: intensity.clamp(0.0, 10.0),
                                                timestamp_us: 0,
                                            });
                                        }
                                    }
                                    Err(_) => break,
                                }
                            }
                        }
                        Err(e) => {
                            eprintln!("psi-daemon: fifo open error: {e}");
                            std::thread::sleep(Duration::from_millis(500));
                        }
                    }
                }
            });
        }

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
