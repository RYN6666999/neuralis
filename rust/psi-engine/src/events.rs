//! PsiEvent + EventReducer — pure fold, no I/O (autonomic pattern).
//!
//! The 18 affective events (spec §2.2) map to fixed impulse vectors on
//! affect dims and needs. `fold_event` is a pure function
//! `PsiState × PsiEvent → PsiState`; the engine drains the ring buffer in
//! insertion order (determinism pillar 2) and folds.

use crate::config::{AROUSAL, NeedKind, PLEASURE, SOCIAL, STRESS};
use crate::state::PsiState;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum AffectiveEvent {
    GoalAchieved,
    GoalFailed,
    SurprisePositive,
    SurpriseNegative,
    SocialPraise,
    SocialCriticism,
    ThreatDetected,
    ThreatResolved,
    NoveltyHigh,
    NoveltyLow,
    CompetenceSuccess,
    CompetenceFailure,
    AutonomyGranted,
    AutonomyDenied,
    RelatednessRenewed,
    RelatednessLoss,
    GrowthMilestone,
    GrowthStagnation,
}

pub const AFFECTIVE_EVENT_COUNT: usize = 18;

impl AffectiveEvent {
    /// Parse an AffectiveEvent from its Debug name (e.g. "CompetenceSuccess").
    /// Returns None for unknown names. Case-sensitive.
    pub fn from_name(name: &str) -> Option<Self> {
        use AffectiveEvent::*;
        Some(match name {
            "GoalAchieved" => GoalAchieved,
            "GoalFailed" => GoalFailed,
            "SurprisePositive" => SurprisePositive,
            "SurpriseNegative" => SurpriseNegative,
            "SocialPraise" => SocialPraise,
            "SocialCriticism" => SocialCriticism,
            "ThreatDetected" => ThreatDetected,
            "ThreatResolved" => ThreatResolved,
            "NoveltyHigh" => NoveltyHigh,
            "NoveltyLow" => NoveltyLow,
            "CompetenceSuccess" => CompetenceSuccess,
            "CompetenceFailure" => CompetenceFailure,
            "AutonomyGranted" => AutonomyGranted,
            "AutonomyDenied" => AutonomyDenied,
            "RelatednessRenewed" => RelatednessRenewed,
            "RelatednessLoss" => RelatednessLoss,
            "GrowthMilestone" => GrowthMilestone,
            "GrowthStagnation" => GrowthStagnation,
            _ => return None,
        })
    }
}

#[derive(Copy, Clone, Debug, PartialEq)]
pub struct PsiEvent {
    pub kind: AffectiveEvent,
    /// Multiplies the base impulse. 1.0 = one +/− mark from the table.
    pub intensity: f64,
    /// Producer-side timestamp, µs. Carried for audit; ordering authority
    /// is ring-buffer insertion order, not this field.
    pub timestamp_us: u64,
}

/// (affect deltas [P,A,D,S,St], need deltas in NeedKind order), in units of
/// one impulse mark. Spec §2.2 effect table.
fn deltas(kind: AffectiveEvent) -> ([f64; 5], [f64; 5]) {
    use AffectiveEvent::*;
    let mut a = [0.0; 5];
    let mut n = [0.0; 5];
    match kind {
        GoalAchieved => a[PLEASURE] = 1.0,
        GoalFailed => a[PLEASURE] = -1.0,
        SurprisePositive => {
            a[AROUSAL] = 1.0;
            a[PLEASURE] = 1.0;
        }
        SurpriseNegative => {
            a[AROUSAL] = 1.0;
            a[PLEASURE] = -1.0;
        }
        SocialPraise => {
            a[SOCIAL] = 1.0;
            a[PLEASURE] = 1.0;
        }
        SocialCriticism => {
            a[SOCIAL] = -1.0;
            a[PLEASURE] = -1.0;
        }
        ThreatDetected => {
            a[STRESS] = 1.0;
            a[AROUSAL] = 1.0;
        }
        ThreatResolved => a[STRESS] = -1.0,
        NoveltyHigh => a[AROUSAL] = 1.0,
        NoveltyLow => a[AROUSAL] = -1.0,
        CompetenceSuccess => {
            n[NeedKind::Competence as usize] = 1.0;
            a[PLEASURE] = 1.0;
        }
        CompetenceFailure => {
            n[NeedKind::Competence as usize] = -1.0;
            a[PLEASURE] = -1.0;
        }
        AutonomyGranted => n[NeedKind::Autonomy as usize] = 1.0,
        AutonomyDenied => n[NeedKind::Autonomy as usize] = -1.0,
        RelatednessRenewed => {
            n[NeedKind::Relatedness as usize] = 1.0;
            a[SOCIAL] = 1.0;
        }
        RelatednessLoss => {
            n[NeedKind::Relatedness as usize] = -1.0;
            a[SOCIAL] = -1.0;
        }
        GrowthMilestone => {
            n[NeedKind::Growth as usize] = 1.0;
            a[PLEASURE] = 1.0;
        }
        GrowthStagnation => {
            n[NeedKind::Growth as usize] = -1.0;
            a[PLEASURE] = -1.0;
        }
    }
    (a, n)
}

/// Pure fold step. `impulse` is the configured base magnitude
/// (AffectParams::event_impulse). Result is sanitized against the input
/// state, so a hostile intensity cannot push values out of domain.
pub fn fold_event(state: PsiState, event: &PsiEvent, impulse: f64) -> PsiState {
    let (da, dn) = deltas(event.kind);
    let k = impulse * event.intensity;
    let mut next = state;
    for i in 0..5 {
        next.affect[i] += da[i] * k;
        next.needs[i] += dn[i] * k;
    }
    next.sanitize(&state);
    next
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::PsiConfig;

    fn ev(kind: AffectiveEvent) -> PsiEvent {
        PsiEvent { kind, intensity: 1.0, timestamp_us: 0 }
    }

    #[test]
    fn all_18_events_change_state() {
        use AffectiveEvent::*;
        let cfg = PsiConfig::default();
        let base = PsiState::from_config(&cfg);
        let all = [
            GoalAchieved, GoalFailed, SurprisePositive, SurpriseNegative,
            SocialPraise, SocialCriticism, ThreatDetected, ThreatResolved,
            NoveltyHigh, NoveltyLow, CompetenceSuccess, CompetenceFailure,
            AutonomyGranted, AutonomyDenied, RelatednessRenewed,
            RelatednessLoss, GrowthMilestone, GrowthStagnation,
        ];
        assert_eq!(all.len(), AFFECTIVE_EVENT_COUNT);
        for kind in all {
            let next = fold_event(base, &ev(kind), 0.1);
            assert_ne!(next, base, "{kind:?} must have an effect");
        }
    }

    #[test]
    fn competence_success_raises_need_and_pleasure() {
        let cfg = PsiConfig::default();
        let base = PsiState::from_config(&cfg);
        let next = fold_event(base, &ev(AffectiveEvent::CompetenceSuccess), 0.1);
        let i = NeedKind::Competence as usize;
        assert!((next.needs[i] - (base.needs[i] + 0.1)).abs() < 1e-12);
        assert!(next.affect[PLEASURE] > base.affect[PLEASURE]);
    }

    #[test]
    fn threat_detected_raises_stress_and_arousal() {
        let cfg = PsiConfig::default();
        let base = PsiState::from_config(&cfg);
        let next = fold_event(base, &ev(AffectiveEvent::ThreatDetected), 0.1);
        assert!(next.affect[STRESS] > base.affect[STRESS]);
        assert!(next.affect[AROUSAL] > base.affect[AROUSAL]);
    }

    #[test]
    fn intensity_scales_and_result_stays_in_domain() {
        let cfg = PsiConfig::default();
        let base = PsiState::from_config(&cfg);
        let big = fold_event(base, &PsiEvent {
            kind: AffectiveEvent::GoalAchieved,
            intensity: 1e9,
            timestamp_us: 0,
        }, 0.1);
        assert_eq!(big.affect[PLEASURE], 1.0, "clamped, not exploded");
        let neg = fold_event(base, &PsiEvent {
            kind: AffectiveEvent::CompetenceFailure,
            intensity: 1e9,
            timestamp_us: 0,
        }, 0.1);
        assert_eq!(neg.needs[NeedKind::Competence as usize], 0.0);
    }

    #[test]
    fn fold_is_pure() {
        let cfg = PsiConfig::default();
        let base = PsiState::from_config(&cfg);
        let e = ev(AffectiveEvent::SocialPraise);
        assert_eq!(fold_event(base, &e, 0.1), fold_event(base, &e, 0.1));
    }
}
