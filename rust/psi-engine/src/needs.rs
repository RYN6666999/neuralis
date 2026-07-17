//! NeedDynamics — five psychological needs as Ornstein-Uhlenbeck processes.
//!
//! Spec §2.1: Δn = θ·(n_◇ − n) + σ·ε, with serumtonin-modulated θ,
//! clamp [0,1] and NaN guard after every step. θ is per second; the
//! Euler–Maruyama discretization scales the drift by dt and the noise by
//! √dt so behavior is rate-independent (2000Hz here vs 1Hz in Python v1).

use rand::Rng;
use rand_distr::StandardNormal;

use crate::config::{NEED_COUNT, NeedParams, PsiConfig};
use crate::state::PsiState;

#[derive(Clone, Debug)]
pub struct NeedDynamics {
    params: [NeedParams; NEED_COUNT],
    serumtonin_factor: f64,
}

impl NeedDynamics {
    pub fn new(cfg: &PsiConfig) -> Self {
        Self {
            params: cfg.needs,
            serumtonin_factor: cfg.serumtonin_factor,
        }
    }

    /// One fast-loop step. `serumtonin` ∈ [0, 1]; higher → slower decay
    /// (θ' = θ·(1 − factor·serumtonin), spec §2.1).
    pub fn step<R: Rng>(&self, state: &mut PsiState, dt: f64, serumtonin: f64, rng: &mut R) {
        let sero = serumtonin.clamp(0.0, 1.0);
        let prev = *state;
        for (i, p) in self.params.iter().enumerate() {
            let theta = p.theta * (1.0 - self.serumtonin_factor * sero);
            let eps: f64 = rng.sample(StandardNormal);
            let dn = theta * (p.target - state.needs[i]) * dt + p.sigma * eps * dt.sqrt();
            state.needs[i] += dn;
        }
        state.sanitize(&prev);
    }

    /// drive = max(0, n_◇ − n) · importance (spec §2.1).
    pub fn drives(&self, state: &PsiState) -> [f64; NEED_COUNT] {
        let mut out = [0.0; NEED_COUNT];
        for (i, p) in self.params.iter().enumerate() {
            out[i] = (p.target - state.needs[i]).max(0.0) * p.importance;
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::NeedKind;
    use rand::{rngs::StdRng, SeedableRng};

    fn setup() -> (PsiConfig, NeedDynamics, PsiState, StdRng) {
        let cfg = PsiConfig::default();
        let nd = NeedDynamics::new(&cfg);
        let st = PsiState::from_config(&cfg);
        (cfg, nd, st, StdRng::seed_from_u64(1))
    }

    /// With σ=0 the OU process converges monotonically toward the target.
    #[test]
    fn converges_to_target_without_noise() {
        let (mut cfg, _, _, mut rng) = setup();
        for p in cfg.needs.iter_mut() {
            p.sigma = 0.0;
        }
        let nd = NeedDynamics::new(&cfg);
        let mut st = PsiState::from_config(&cfg);
        let start_gap = cfg.needs[0].target - st.needs[0];
        // 10 simulated minutes at 2000Hz.
        for _ in 0..1_200_000 {
            nd.step(&mut st, cfg.dt(), 0.0, &mut rng);
        }
        let end_gap = cfg.needs[0].target - st.needs[0];
        assert!(end_gap.abs() < start_gap.abs());
        assert!(end_gap.abs() < 0.02, "gap after 10min: {end_gap}");
    }

    /// Serumtonin slows decay: gap closes less with serumtonin=1.
    #[test]
    fn serumtonin_slows_relaxation() {
        let (mut cfg, _, _, _) = setup();
        for p in cfg.needs.iter_mut() {
            p.sigma = 0.0;
        }
        let nd = NeedDynamics::new(&cfg);
        let mut fast = PsiState::from_config(&cfg);
        let mut slow = PsiState::from_config(&cfg);
        let mut rng = StdRng::seed_from_u64(1);
        for _ in 0..200_000 {
            nd.step(&mut fast, cfg.dt(), 0.0, &mut rng);
            nd.step(&mut slow, cfg.dt(), 1.0, &mut rng);
        }
        let i = NeedKind::Competence as usize;
        assert!(
            cfg.needs[i].target - slow.needs[i] > cfg.needs[i].target - fast.needs[i],
            "serumtonin=1 should lag behind serumtonin=0"
        );
    }

    #[test]
    fn drive_formula_matches_spec_table() {
        let (_cfg, nd, st, _) = setup();
        let d = nd.drives(&st);
        // COMPETENCE: (0.9 − 0.4) · 1.5 = 0.75 — the dominant initial drive.
        assert!((d[NeedKind::Competence as usize] - 0.75).abs() < 1e-12);
        // CERTAINTY: (0.8 − 0.6) · 1.2 = 0.24.
        assert!((d[NeedKind::Certainty as usize] - 0.24).abs() < 1e-12);
        // Saturated need → zero drive, not negative.
        let mut full = st;
        full.needs[NeedKind::Autonomy as usize] = 1.0;
        assert_eq!(nd.drives(&full)[NeedKind::Autonomy as usize], 0.0);
    }

    #[test]
    fn values_stay_in_domain_under_noise() {
        let (cfg, nd, mut st, mut rng) = setup();
        for _ in 0..100_000 {
            nd.step(&mut st, cfg.dt(), 0.5, &mut rng);
            for v in st.needs {
                assert!((0.0..=1.0).contains(&v));
            }
        }
    }
}
