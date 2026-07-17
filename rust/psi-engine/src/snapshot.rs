//! PsiSnapshot — the B-surface contract struct (spec §6) plus the atomic
//! snapshot cell it is published through.
//!
//! The cell is `crossbeam_utils::atomic::AtomicCell<PsiSnapshot>`: for a
//! struct this size crossbeam implements it as a seqlock — single-writer
//! stores never block, readers retry optimistically. The fast loop writes
//! every `snapshot_divisor` ticks (20 @ 2000Hz = 100Hz, Tier B); any
//! thread reads `latest()` without disturbing the loop.
//!
//! ponytail: consumers poll `latest()`; a push channel (spec mentions one)
//! can wrap this cell in a Tier B thread once a Rust-side consumer exists.

use std::sync::Arc;

use crossbeam_utils::atomic::AtomicCell;

use crate::attention::GateState;
use crate::config::{AFFECT_COUNT, NEED_COUNT};

/// Copyable metrics excerpt embedded in each snapshot (the full histogram
/// stays in TickMetrics — too big and not Copy).
#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct MetricsSummary {
    pub ticks: u64,
    pub deadline_misses: u64,
    /// Σ(actual_interval − period), µs. Positive = running late.
    pub drift_us: i64,
    pub last_compute_us: u64,
}

/// B-surface contract (spec §6): field order mirrors the Python PsiState
/// schema. Same NeedKind ordering as `laap/psi_core.py`.
#[derive(Copy, Clone, Debug, PartialEq)]
pub struct PsiSnapshot {
    pub needs: [f64; NEED_COUNT],
    pub drives: [f64; NEED_COUNT],
    /// [P, A, D, S, St].
    pub affect: [f64; AFFECT_COUNT],
    /// Slow-release valence channel (two-channel valence).
    pub endorphin: f64,
    pub attention: GateState,
    /// Microseconds since epoch: `epoch_us + tick_count · period`. Logical
    /// time — deterministic under replay (epoch 0 when no runtime).
    pub timestamp_us: u64,
    pub tick_count: u64,
    pub metrics: MetricsSummary,
}

impl PsiSnapshot {
    pub fn zeroed() -> Self {
        Self {
            needs: [0.0; NEED_COUNT],
            drives: [0.0; NEED_COUNT],
            affect: [0.0; AFFECT_COUNT],
            endorphin: 0.0,
            attention: GateState::Idle,
            timestamp_us: 0,
            tick_count: 0,
            metrics: MetricsSummary::default(),
        }
    }
}

/// Shared cell: one writer (the engine), any readers.
pub type SnapshotCell = AtomicCell<PsiSnapshot>;

pub fn new_cell() -> Arc<SnapshotCell> {
    Arc::new(AtomicCell::new(PsiSnapshot::zeroed()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cell_roundtrip() {
        let cell = new_cell();
        let mut s = PsiSnapshot::zeroed();
        s.tick_count = 42;
        s.needs[0] = 0.6;
        cell.store(s);
        assert_eq!(cell.load(), s);
    }

    #[test]
    fn concurrent_reads_see_consistent_snapshots() {
        use std::thread;
        let cell = new_cell();
        let writer = Arc::clone(&cell);
        let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let stop_w = Arc::clone(&stop);
        let t = thread::spawn(move || {
            let mut n: u64 = 0;
            while !stop_w.load(std::sync::atomic::Ordering::Relaxed) {
                let mut s = PsiSnapshot::zeroed();
                n += 1;
                s.tick_count = n;
                // Correlated fields: torn reads would break the invariant.
                s.needs = [n as f64; NEED_COUNT];
                writer.store(s);
            }
        });
        for _ in 0..100_000 {
            let s = cell.load();
            assert_eq!(s.needs[0], s.tick_count as f64, "torn snapshot");
            assert_eq!(s.needs[0], s.needs[4], "torn snapshot");
        }
        stop.store(true, std::sync::atomic::Ordering::Relaxed);
        t.join().unwrap();
    }
}
