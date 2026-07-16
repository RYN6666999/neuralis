//! PsiEngine — deterministic core orchestration.
//!
//! `tick()` contains no timing, no I/O and no allocation: it is the pure
//! Tier A step, callable from the 2000Hz runtime or directly from replay
//! tests. Determinism pillars (spec §5):
//!   1. one seeded StdRng owned here;
//!   2. events drained in ring-buffer insertion order;
//!   3. fixed update order Need → Affect → Attention → EventReducer →
//!      Snapshot;
//!   4. plain f64 math, no SIMD (see workspace profile note).

use std::sync::Arc;

use crossbeam_queue::ArrayQueue;
use rand::{rngs::StdRng, SeedableRng};

use crate::affect::AffectDynamics;
use crate::attention::{AttentionGate, GateState, GatingDecision};
use crate::config::{NeedKind, PsiConfig};
use crate::events::{fold_event, PsiEvent};
use crate::metrics::TickMetrics;
use crate::needs::NeedDynamics;
use crate::snapshot::{new_cell, PsiSnapshot, SnapshotCell};
use crate::state::PsiState;

pub struct PsiEngine {
    cfg: PsiConfig,
    state: PsiState,
    rng: StdRng,
    needs: NeedDynamics,
    affect: AffectDynamics,
    gate: AttentionGate,
    events: Arc<ArrayQueue<PsiEvent>>,
    snap: Arc<SnapshotCell>,
    pub metrics: TickMetrics,
    tick_count: u64,
    /// Wall-clock epoch (µs) set by the runtime; 0 under pure replay.
    epoch_us: u64,
    last_decision: GatingDecision,
}

/// Cloneable handle for producers (event push) and consumers (snapshot
/// read). Both sides are lock-free; neither can stall the fast loop.
#[derive(Clone)]
pub struct PsiHandle {
    events: Arc<ArrayQueue<PsiEvent>>,
    snap: Arc<SnapshotCell>,
}

impl PsiHandle {
    /// Push an event. If the ring is full the OLDEST event is overwritten
    /// (coalesce, spec §3) and returned.
    pub fn post_event(&self, ev: PsiEvent) -> Option<PsiEvent> {
        self.events.force_push(ev)
    }

    /// Latest published snapshot (Tier B surface).
    pub fn latest(&self) -> PsiSnapshot {
        self.snap.load()
    }
}

impl PsiEngine {
    pub fn new(cfg: PsiConfig) -> Self {
        let events = Arc::new(ArrayQueue::new(cfg.runtime.ring_capacity));
        let snap = new_cell();
        let mut engine = Self {
            state: PsiState::from_config(&cfg),
            rng: StdRng::seed_from_u64(cfg.seed),
            needs: NeedDynamics::new(&cfg),
            affect: AffectDynamics::new(&cfg),
            gate: AttentionGate::new(cfg.gate),
            events,
            snap,
            metrics: TickMetrics::new(cfg.runtime.tick_period_us),
            tick_count: 0,
            epoch_us: 0,
            last_decision: GatingDecision::Stay,
            cfg,
        };
        // Publish the initial state so early readers never see zeroes.
        engine.publish();
        engine
    }

    pub fn handle(&self) -> PsiHandle {
        PsiHandle {
            events: Arc::clone(&self.events),
            snap: Arc::clone(&self.snap),
        }
    }

    pub fn config(&self) -> &PsiConfig {
        &self.cfg
    }

    pub fn state(&self) -> &PsiState {
        &self.state
    }

    pub fn tick_count(&self) -> u64 {
        self.tick_count
    }

    pub fn attention(&self) -> GateState {
        self.gate.state()
    }

    pub fn last_gate_decision(&self) -> GatingDecision {
        self.last_decision
    }

    pub fn set_epoch_us(&mut self, us: u64) {
        self.epoch_us = us;
    }

    /// One Tier A step. Allowed-operations list only (spec §3 Tier A):
    /// OU decay, affect inertia/coupling, gate comparisons, event fold,
    /// snapshot store. No I/O, no allocation, no blocking.
    pub fn tick(&mut self) {
        let dt = self.cfg.dt();

        // Serumtonin level derived from the slow valence channel
        // (endorphin [-1,1] → [0,1]). The spec defines the modulation
        // formula but not the source; Python v1 derives it from valence.
        let serumtonin = ((self.state.endorphin + 1.0) / 2.0).clamp(0.0, 1.0);

        // 1. NeedDynamics
        self.needs.step(&mut self.state, dt, serumtonin, &mut self.rng);
        // 2. AffectDynamics
        self.affect.step(&mut self.state, dt, &mut self.rng);
        // 3. AttentionGate
        let drives = self.needs.drives(&self.state);
        let uncertainty = 1.0 - self.state.needs[NeedKind::Certainty as usize];
        self.last_decision = self.gate.update(&drives, uncertainty);
        // 4. EventReducer — drain in insertion order, bounded by capacity
        // so a producer flood cannot pin the loop past its budget.
        let mut drained = 0;
        while drained < self.cfg.runtime.ring_capacity {
            match self.events.pop() {
                Some(ev) => {
                    self.state =
                        fold_event(self.state, &ev, self.cfg.affect.event_impulse);
                    drained += 1;
                }
                None => break,
            }
        }

        self.tick_count += 1;

        // 5. Snapshot (Tier B cadence).
        if self.tick_count.is_multiple_of(self.cfg.runtime.snapshot_divisor) {
            self.publish();
        }
    }

    pub fn snapshot(&self) -> PsiSnapshot {
        PsiSnapshot {
            needs: self.state.needs,
            drives: self.needs.drives(&self.state),
            affect: self.state.affect,
            endorphin: self.state.endorphin,
            attention: self.gate.state(),
            timestamp_us: self.epoch_us
                + self.tick_count * self.cfg.runtime.tick_period_us,
            tick_count: self.tick_count,
            metrics: self.metrics.summary(),
        }
    }

    fn publish(&mut self) {
        self.snap.store(self.snapshot());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::AffectiveEvent;

    #[test]
    fn tick_advances_and_publishes_at_divisor() {
        let mut e = PsiEngine::new(PsiConfig::default());
        let h = e.handle();
        let initial = h.latest();
        assert_eq!(initial.tick_count, 0);
        for _ in 0..20 {
            e.tick();
        }
        let snap = h.latest();
        assert_eq!(snap.tick_count, 20, "divisor=20 → published at tick 20");
    }

    #[test]
    fn events_flow_from_handle_into_state() {
        let mut e = PsiEngine::new(PsiConfig::default());
        let h = e.handle();
        let before = e.state().needs[NeedKind::Competence as usize];
        h.post_event(PsiEvent {
            kind: AffectiveEvent::CompetenceSuccess,
            intensity: 1.0,
            timestamp_us: 0,
        });
        e.tick();
        let after = e.state().needs[NeedKind::Competence as usize];
        assert!(after > before, "event impulse must land within one tick");
    }

    #[test]
    fn ring_overflow_coalesces_oldest() {
        let mut cfg = PsiConfig::default();
        cfg.runtime.ring_capacity = 2;
        let e = PsiEngine::new(cfg);
        let h = e.handle();
        let mk = |ts| PsiEvent {
            kind: AffectiveEvent::NoveltyHigh,
            intensity: 1.0,
            timestamp_us: ts,
        };
        assert_eq!(h.post_event(mk(1)), None);
        assert_eq!(h.post_event(mk(2)), None);
        let displaced = h.post_event(mk(3));
        assert_eq!(displaced.map(|e| e.timestamp_us), Some(1), "oldest evicted");
    }

    #[test]
    fn logical_timestamp_uses_epoch_and_tick_count() {
        let mut e = PsiEngine::new(PsiConfig::default());
        e.set_epoch_us(1_000_000);
        for _ in 0..3 {
            e.tick();
        }
        assert_eq!(e.snapshot().timestamp_us, 1_000_000 + 3 * 500);
    }
}
