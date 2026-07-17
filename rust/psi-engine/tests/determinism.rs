//! Deterministic replay — spec §5: two runs with the same seed and the
//! same events at the same tick indices produce an identical state
//! sequence (bit-exact f64).

use psi_engine::{AffectiveEvent, PsiConfig, PsiEngine, PsiEvent, PsiState};

const TICKS: u64 = 10_000;

/// Deterministic event script: (tick index, event).
fn script() -> Vec<(u64, PsiEvent)> {
    let ev = |kind, tick: u64| PsiEvent {
        kind,
        intensity: 1.0,
        timestamp_us: tick * 500,
    };
    vec![
        (100, ev(AffectiveEvent::ThreatDetected, 100)),
        (500, ev(AffectiveEvent::CompetenceSuccess, 500)),
        (501, ev(AffectiveEvent::SocialPraise, 501)),
        (2_000, ev(AffectiveEvent::GoalAchieved, 2_000)),
        (2_000, ev(AffectiveEvent::NoveltyHigh, 2_000)),
        (7_777, ev(AffectiveEvent::RelatednessLoss, 7_777)),
    ]
}

/// Run TICKS ticks, injecting the script, recording the full state
/// sequence (sampled every tick).
fn run_scripted(seed: u64) -> Vec<PsiState> {
    let cfg = PsiConfig { seed, ..PsiConfig::default() };
    let mut engine = PsiEngine::new(cfg);
    let handle = engine.handle();
    let script = script();
    let mut states = Vec::with_capacity(TICKS as usize);
    for tick in 0..TICKS {
        for (at, ev) in &script {
            if *at == tick {
                handle.post_event(*ev);
            }
        }
        engine.tick();
        states.push(*engine.state());
    }
    states
}

fn assert_bit_identical(a: &PsiState, b: &PsiState, tick: usize) {
    for i in 0..5 {
        assert_eq!(
            a.needs[i].to_bits(),
            b.needs[i].to_bits(),
            "needs[{i}] diverged at tick {tick}"
        );
        assert_eq!(
            a.affect[i].to_bits(),
            b.affect[i].to_bits(),
            "affect[{i}] diverged at tick {tick}"
        );
    }
    assert_eq!(
        a.endorphin.to_bits(),
        b.endorphin.to_bits(),
        "endorphin diverged at tick {tick}"
    );
}

#[test]
fn same_seed_same_events_identical_state_sequence() {
    let a = run_scripted(0xC0FFEE);
    let b = run_scripted(0xC0FFEE);
    assert_eq!(a.len(), b.len());
    for (tick, (sa, sb)) in a.iter().zip(b.iter()).enumerate() {
        assert_bit_identical(sa, sb, tick);
    }
}

#[test]
fn different_seed_diverges() {
    let a = run_scripted(1);
    let b = run_scripted(2);
    let last = (TICKS - 1) as usize;
    assert_ne!(
        a[last], b[last],
        "different seeds must produce different trajectories"
    );
}

#[test]
fn event_presence_changes_trajectory() {
    let cfg = PsiConfig { seed: 99, ..PsiConfig::default() };
    let mut plain = PsiEngine::new(cfg);
    let mut evented = PsiEngine::new(cfg);
    let handle = evented.handle();
    for tick in 0..1_000_u64 {
        if tick == 10 {
            handle.post_event(PsiEvent {
                kind: AffectiveEvent::GoalFailed,
                intensity: 1.0,
                timestamp_us: 0,
            });
        }
        plain.tick();
        evented.tick();
    }
    assert_ne!(plain.state(), evented.state());
}

/// Snapshots carry deterministic logical timestamps under replay
/// (epoch 0, timestamp = tick_count · period).
#[test]
fn replay_snapshots_are_deterministic() {
    let cfg = PsiConfig { seed: 7, ..PsiConfig::default() };
    let mut a = PsiEngine::new(cfg);
    let mut b = PsiEngine::new(cfg);
    for _ in 0..200 {
        a.tick();
        b.tick();
    }
    let (sa, sb) = (a.snapshot(), b.snapshot());
    assert_eq!(sa.timestamp_us, sb.timestamp_us);
    assert_eq!(sa.needs, sb.needs);
    assert_eq!(sa.drives, sb.drives);
    assert_eq!(sa.affect, sb.affect);
    assert_eq!(sa.attention, sb.attention);
}
