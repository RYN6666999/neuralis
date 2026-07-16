//! AffectDynamics — 5D affect (PAD+S+St), coupling, 1/f noise, inertia,
//! two-channel valence (spec §2.2).
//!
//! Update order per spec: 1. coupling → 2. 1/f noise → 3. clamp →
//! 4. NaN guard → 5. endorphin. Emotional inertia (λ toward baseline) is
//! folded into the same integration step as the damping term.

use rand::Rng;

use crate::config::{AffectParams, AROUSAL, PLEASURE, PsiConfig, SOCIAL, STRESS};
use crate::noise::PinkNoise;
use crate::state::PsiState;

#[derive(Clone, Debug)]
pub struct AffectDynamics {
    params: AffectParams,
    pink: PinkNoise,
}

impl AffectDynamics {
    pub fn new(cfg: &PsiConfig) -> Self {
        Self {
            params: cfg.affect,
            pink: PinkNoise::new(),
        }
    }

    pub fn step<R: Rng>(&mut self, state: &mut PsiState, dt: f64, rng: &mut R) {
        let prev = *state;
        let a = &self.params;
        let w = &a.coupling;
        let [p, ar, _d, s, st] = state.affect;

        // 1. Coupling matrix — the 8 named terms, per-second weights.
        let dp = w.w_pp * p + w.w_ps * s;
        let da = w.w_aa * ar + w.w_ast * st;
        let ds = w.w_sp * p + w.w_ss * s;
        let dst = w.w_sta * ar + w.w_stst * st;
        let coupling = [dp, da, 0.0, ds, dst];

        // 2. 1/f noise — one pink sample per tick, same value on the
        // mutable dims (matches the Python v1 reference; D stays pinned).
        let noise = self.pink.sample(rng) * a.noise_amplitude * dt.sqrt();

        for i in [PLEASURE, AROUSAL, SOCIAL, STRESS] {
            let inertia = a.inertia_lambda * (a.baseline[i] - state.affect[i]);
            state.affect[i] += (coupling[i] + inertia) * dt + noise;
        }

        // 3–4. Clamp + NaN guard (also re-pins D = 0.5).
        state.sanitize(&prev);

        // 5. Two-channel valence: endorphin slow-release EMA of raw valence.
        // ponytail: spec gives the EMA per *update* with α=0.3; applied at
        // 2000Hz it tracks raw within ~5ms. α is config so Tier C can
        // recalibrate (spec §7 lists it as UNKNOWN); upgrade path is a
        // time-constant form α_dt = 1 − (1−α)^(dt/1s).
        let alpha = a.endorphin_alpha;
        state.endorphin = (1.0 - alpha) * state.endorphin + alpha * state.valence_raw();
        state.sanitize(&prev);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::DOMINANCE;
    use rand::{rngs::StdRng, SeedableRng};

    fn quiet_cfg() -> PsiConfig {
        let mut cfg = PsiConfig::default();
        cfg.affect.noise_amplitude = 0.0;
        cfg
    }

    #[test]
    fn dominance_stays_pinned() {
        let cfg = PsiConfig::default();
        let mut ad = AffectDynamics::new(&cfg);
        let mut st = PsiState::from_config(&cfg);
        let mut rng = StdRng::seed_from_u64(3);
        for _ in 0..10_000 {
            ad.step(&mut st, cfg.dt(), &mut rng);
            assert_eq!(st.affect[DOMINANCE], 0.5);
        }
    }

    #[test]
    fn stress_raises_arousal_via_coupling() {
        let cfg = quiet_cfg();
        let mut ad = AffectDynamics::new(&cfg);
        let mut calm = PsiState::from_config(&cfg);
        let mut stressed = calm;
        stressed.affect[STRESS] = 1.0;
        let mut rng = StdRng::seed_from_u64(3);
        // 2 simulated seconds — short enough that the stressed trajectory
        // has not yet relaxed back to the shared equilibrium.
        for _ in 0..4_000 {
            ad.step(&mut calm, cfg.dt(), &mut rng);
            ad.step(&mut stressed, cfg.dt(), &mut rng);
        }
        assert!(
            stressed.affect[AROUSAL] > calm.affect[AROUSAL],
            "w_ASt > 0: stress must push arousal up ({} vs {})",
            stressed.affect[AROUSAL],
            calm.affect[AROUSAL]
        );
    }

    #[test]
    fn inertia_pulls_back_to_baseline() {
        let mut cfg = quiet_cfg();
        // Isolate inertia: zero out coupling.
        cfg.affect.coupling = crate::config::CouplingWeights {
            w_pp: 0.0, w_ps: 0.0, w_aa: 0.0, w_ast: 0.0,
            w_sp: 0.0, w_ss: 0.0, w_sta: 0.0, w_stst: 0.0,
        };
        let mut ad = AffectDynamics::new(&cfg);
        let mut st = PsiState::from_config(&cfg);
        st.affect[PLEASURE] = 1.0;
        let mut rng = StdRng::seed_from_u64(3);
        let start = st.affect[PLEASURE];
        for _ in 0..200_000 {
            ad.step(&mut st, cfg.dt(), &mut rng);
        }
        let baseline = cfg.affect.baseline[PLEASURE];
        assert!(
            (st.affect[PLEASURE] - baseline).abs() < (start - baseline).abs(),
            "P should relax toward baseline"
        );
    }

    #[test]
    fn endorphin_lags_raw_valence() {
        let cfg = quiet_cfg();
        let mut ad = AffectDynamics::new(&cfg);
        let mut st = PsiState::from_config(&cfg);
        st.affect[PLEASURE] = 0.8;
        st.endorphin = 0.0;
        let mut rng = StdRng::seed_from_u64(3);
        ad.step(&mut st, cfg.dt(), &mut rng);
        assert!(st.endorphin > 0.0, "EMA moves toward raw");
        assert!(
            st.endorphin < st.valence_raw(),
            "one step must not fully catch up"
        );
    }

    #[test]
    fn domains_hold_under_noise() {
        let cfg = PsiConfig::default();
        let mut ad = AffectDynamics::new(&cfg);
        let mut st = PsiState::from_config(&cfg);
        let mut rng = StdRng::seed_from_u64(9);
        for _ in 0..100_000 {
            ad.step(&mut st, cfg.dt(), &mut rng);
            assert!((-1.0..=1.0).contains(&st.affect[PLEASURE]));
            for i in [AROUSAL, SOCIAL, STRESS] {
                assert!((0.0..=1.0).contains(&st.affect[i]));
            }
        }
    }
}
