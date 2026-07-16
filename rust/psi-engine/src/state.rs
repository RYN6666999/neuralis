//! PsiState — the mutable core state, one flat Copy struct.
//!
//! Subsystems (NeedDynamics/AffectDynamics) are operators over this
//! struct; the EventReducer is a pure fold over it. Keeping the state in
//! one Copy value is what makes deterministic replay and the atomic
//! snapshot cheap (stack copies only, no heap).

use crate::config::{AFFECT_COUNT, DOMINANCE, NEED_COUNT, PLEASURE, PsiConfig};

#[derive(Copy, Clone, Debug, PartialEq)]
pub struct PsiState {
    /// Need satisfaction values, [0, 1]. Order: NeedKind.
    pub needs: [f64; NEED_COUNT],
    /// Affect vector [P, A, D, S, St]. Domains: P [-1,1], A/S/St [0,1],
    /// D fixed 0.5.
    pub affect: [f64; AFFECT_COUNT],
    /// Slow-release valence channel (two-channel valence, spec §2.2).
    pub endorphin: f64,
}

impl PsiState {
    pub fn from_config(cfg: &PsiConfig) -> Self {
        let mut needs = [0.0; NEED_COUNT];
        for (i, p) in cfg.needs.iter().enumerate() {
            needs[i] = p.initial;
        }
        Self {
            needs,
            affect: cfg.affect.baseline,
            endorphin: 0.0,
        }
    }

    /// Immediate valence channel: the pleasure dimension.
    pub fn valence_raw(&self) -> f64 {
        self.affect[PLEASURE]
    }

    /// Clamp every field to its domain and guard NaN/inf by falling back
    /// to the given previous (known-good) state. Runs after every update
    /// step (spec update order steps 3–4).
    pub fn sanitize(&mut self, prev: &PsiState) {
        for i in 0..NEED_COUNT {
            self.needs[i] = guard(self.needs[i], prev.needs[i]).clamp(0.0, 1.0);
        }
        // P is [-1,1]; A, S, St are [0,1]; D is pinned.
        self.affect[0] = guard(self.affect[0], prev.affect[0]).clamp(-1.0, 1.0);
        for i in 1..AFFECT_COUNT {
            self.affect[i] = guard(self.affect[i], prev.affect[i]).clamp(0.0, 1.0);
        }
        self.affect[DOMINANCE] = 0.5;
        self.endorphin = guard(self.endorphin, prev.endorphin).clamp(-1.0, 1.0);
    }
}

fn guard(v: f64, fallback: f64) -> f64 {
    if v.is_finite() { v } else { fallback }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_clamps_domains_and_pins_dominance() {
        let cfg = PsiConfig::default();
        let prev = PsiState::from_config(&cfg);
        let mut s = prev;
        s.needs[0] = 1.7;
        s.needs[1] = -0.2;
        s.affect = [-3.0, 2.0, 0.9, -1.0, 5.0];
        s.endorphin = 9.0;
        s.sanitize(&prev);
        assert_eq!(s.needs[0], 1.0);
        assert_eq!(s.needs[1], 0.0);
        assert_eq!(s.affect, [-1.0, 1.0, 0.5, 0.0, 1.0]);
        assert_eq!(s.endorphin, 1.0);
    }

    #[test]
    fn sanitize_replaces_nan_with_previous_value() {
        let cfg = PsiConfig::default();
        let prev = PsiState::from_config(&cfg);
        let mut s = prev;
        s.needs[2] = f64::NAN;
        s.affect[1] = f64::INFINITY;
        s.sanitize(&prev);
        assert_eq!(s.needs[2], prev.needs[2]);
        assert_eq!(s.affect[1], prev.affect[1]);
    }
}
