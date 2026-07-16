//! Cognitive biases — read-side derivation from a snapshot (Tier C).
//!
//! The spec (§2.2) names 8 biases with mechanisms but no formulas
//! (UNKNOWN §7). These are placeholder linear derivations in the style of
//! the Python v1 `compute_cognitive_bias`, exposed so Tier C consumers get
//! real parameters instead of a dict nobody reads.
//! ponytail: coefficients are calibration TBD; keep the output clamp at
//! ±0.8 (matches Python v1) so no consumer can be saturated by a bias.

use crate::config::{AROUSAL, SOCIAL, STRESS};
use crate::snapshot::PsiSnapshot;

#[derive(Copy, Clone, Debug, PartialEq)]
pub struct CognitiveBiases {
    /// Positive appraisal shift (spec: valence shift +0.1).
    pub optimism: f64,
    /// Negative appraisal shift (spec: valence shift -0.1).
    pub pessimism: f64,
    /// Prediction-error discount factor.
    pub confirmation: f64,
    /// Extra weight on recent events.
    pub recency: f64,
    /// Extra weight on vivid (arousing/stressful) events.
    pub availability: f64,
    /// Slowness of adjustment away from anchors.
    pub anchoring: f64,
    /// Discount applied to others' perspectives.
    pub egocentric: f64,
    /// Degree to which self-state is attributed to others.
    pub projection: f64,
}

const CLAMP: f64 = 0.8;

pub fn compute(snap: &PsiSnapshot) -> CognitiveBiases {
    let e = snap.endorphin;
    let a = snap.affect[AROUSAL];
    let st = snap.affect[STRESS];
    let so = snap.affect[SOCIAL];
    let c = |v: f64| v.clamp(0.0, CLAMP);
    CognitiveBiases {
        optimism: c(0.1 * e.max(0.0)),
        pessimism: c(0.1 * (-e).max(0.0)),
        confirmation: c(0.25 * e.abs()),
        recency: c(0.3 * a),
        availability: c(0.2 * a + 0.2 * st),
        anchoring: c(0.3 * (1.0 - a)),
        egocentric: c(0.2 * (1.0 - so)),
        projection: c(0.2 * so),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::PLEASURE;

    #[test]
    fn optimism_and_pessimism_are_mutually_exclusive() {
        let mut s = PsiSnapshot::zeroed();
        s.endorphin = 0.5;
        let b = compute(&s);
        assert!(b.optimism > 0.0);
        assert_eq!(b.pessimism, 0.0);
        s.endorphin = -0.5;
        let b = compute(&s);
        assert_eq!(b.optimism, 0.0);
        assert!(b.pessimism > 0.0);
    }

    #[test]
    fn all_outputs_within_clamp() {
        let mut s = PsiSnapshot::zeroed();
        s.endorphin = 1.0;
        s.affect = [1.0, 1.0, 0.5, 1.0, 1.0];
        let b = compute(&s);
        for v in [
            b.optimism, b.pessimism, b.confirmation, b.recency,
            b.availability, b.anchoring, b.egocentric, b.projection,
        ] {
            assert!((0.0..=CLAMP).contains(&v));
        }
        // PLEASURE untouched by compute — snapshot is read-only input.
        assert_eq!(s.affect[PLEASURE], 1.0);
    }
}
