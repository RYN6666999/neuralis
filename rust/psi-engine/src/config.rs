//! PsiConfig — every calibratable constant in one place.
//!
//! All rate constants are **per second**; the integrator scales by `dt`
//! (tick period). This keeps the numbers identical to the Python v1
//! reference (`laap/psi_core.py`) which ticks at 1Hz with dt=1.0.
//! Values flagged UNKNOWN in the spec (§7) default to the reference
//! implementation's numbers and are meant to be recalibrated.

/// Index order is the B-surface contract order (same as Python NeedType).
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
#[repr(usize)]
pub enum NeedKind {
    Certainty = 0,
    Competence = 1,
    Autonomy = 2,
    Relatedness = 3,
    Growth = 4,
}

pub const NEED_COUNT: usize = 5;

/// Affect vector index order: P, A, D, S, St.
pub const AFFECT_COUNT: usize = 5;
pub const PLEASURE: usize = 0;
pub const AROUSAL: usize = 1;
pub const DOMINANCE: usize = 2;
pub const SOCIAL: usize = 3;
pub const STRESS: usize = 4;

#[derive(Copy, Clone, Debug)]
pub struct NeedParams {
    pub initial: f64,
    pub target: f64,
    /// OU decay rate θ, per second, domain (0, 0.1].
    pub theta: f64,
    /// OU noise amplitude σ, per √second, domain [0, 0.01].
    pub sigma: f64,
    /// Drive scaling, domain [0.5, 2.0].
    pub importance: f64,
}

/// Coupling weights, per second. Spec §2.2 names 8 terms (its "7 non-zero"
/// count is off by one — all 8 listed names are implemented). Cross-term
/// defaults come from the Python v1 author matrix where the structure
/// overlaps. UNKNOWN (§7): values TBD.
///
/// Stability constraint (autonomic StabilityBudget concept): the linear
/// system splits into two 2×2 subsystems, (P,S) and (A,St). Each must
/// satisfy trace < 0 and det > 0 or the affect state saturates at its
/// clamp instead of settling: (w_aa−λ)(w_stst−λ) > w_ast·w_sta, and
/// (w_pp−λ)(w_ss−λ) > w_ps·w_sp, with λ = inertia_lambda. The defaults
/// hold with margin: 0.36·0.36 > 0.5·0.2 and 0.26·0.26 > 0.15·0.3.
/// Verified by `stable_coupling_defaults` below.
#[derive(Copy, Clone, Debug)]
pub struct CouplingWeights {
    pub w_pp: f64,
    pub w_ps: f64,
    pub w_aa: f64,
    pub w_ast: f64,
    pub w_sp: f64,
    pub w_ss: f64,
    pub w_sta: f64,
    pub w_stst: f64,
}

impl Default for CouplingWeights {
    fn default() -> Self {
        Self {
            w_pp: -0.25,
            w_ps: 0.15,
            w_aa: -0.35,
            w_ast: 0.5,
            w_sp: 0.3,
            w_ss: -0.25,
            w_sta: 0.2,
            w_stst: -0.35,
        }
    }
}

#[derive(Copy, Clone, Debug)]
pub struct AffectParams {
    /// Inertia target e_target per dimension [P, A, D, S, St].
    pub baseline: [f64; AFFECT_COUNT],
    /// Emotional inertia λ, per second (spec: 0.01).
    pub inertia_lambda: f64,
    pub coupling: CouplingWeights,
    /// 1/f noise amplitude. UNKNOWN (§7): requires tuning.
    pub noise_amplitude: f64,
    /// Endorphin slow-release: endorphin = (1-α)·endorphin + α·valence_raw.
    /// Spec value α=0.3. Applied per tick — see AffectDynamics for caveat.
    pub endorphin_alpha: f64,
    /// Base magnitude of one +/− mark in the 18-event effect table.
    pub event_impulse: f64,
}

impl Default for AffectParams {
    fn default() -> Self {
        Self {
            baseline: [0.0, 0.3, 0.5, 0.3, 0.1],
            inertia_lambda: 0.01,
            coupling: CouplingWeights::default(),
            noise_amplitude: 0.03,
            endorphin_alpha: 0.3,
            event_impulse: 0.1,
        }
    }
}

/// Hysteresis gate thresholds (autonomic pattern): separate enter/exit
/// levels + minimum hold to prevent mode flapping. UNKNOWN (§7): must be
/// tuned on real usage.
#[derive(Copy, Clone, Debug)]
pub struct GateParams {
    pub task_enter: f64,
    pub task_exit: f64,
    pub learning_enter: f64,
    pub learning_exit: f64,
    /// PLANNING triggers when ≥2 drives exceed this level.
    pub planning_enter: f64,
    pub planning_exit: f64,
    /// Minimum ticks in a state before a transition is allowed.
    pub min_hold_ticks: u64,
}

impl Default for GateParams {
    fn default() -> Self {
        Self {
            task_enter: 0.45,
            task_exit: 0.30,
            learning_enter: 0.50,
            learning_exit: 0.35,
            planning_enter: 0.40,
            planning_exit: 0.25,
            // 100ms at 2000Hz — transitions are a Tier C (10Hz) concern.
            min_hold_ticks: 200,
        }
    }
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum CatchUpPolicy {
    /// Default: drop the missed tick, advance target (spec §7 rationale).
    Skip,
    /// Run the next tick immediately (risks cascading overload).
    Burst,
    /// Reset schedule to now + period (accumulates persistent drift).
    Delay,
}

#[derive(Copy, Clone, Debug)]
pub struct RuntimeParams {
    /// Tick period, µs. 500µs = 2000Hz.
    pub tick_period_us: u64,
    /// Spin-last window for spin-sleep, µs. The spec's 125µs (E1 claim)
    /// verified E0 on Apple Silicon (macOS 26.3, M-series) — but ONLY
    /// with the mach time-constraint policy the runtime sets on the loop
    /// thread. Measured via psi-bench:
    ///   default scheduler: sleeps overshoot by whole ms → ~1300Hz;
    ///   full spin (500µs): ~1 core burned, preempted every 10-20s anyway;
    ///   125µs + RT policy: 2000.1Hz, 0 misses, peak 24µs, drift 0µs.
    /// On non-macOS targets calibrate with `psi-bench --spin-us`.
    pub spin_window_us: u32,
    /// Publish a snapshot every N ticks. 20 @ 2000Hz = 100Hz (Tier B).
    pub snapshot_divisor: u64,
    /// Event ring capacity. UNKNOWN (§8): 1024 is an estimate.
    pub ring_capacity: usize,
    pub catch_up: CatchUpPolicy,
    /// Degraded rate period (200Hz) under severe overload.
    pub degraded_period_us: u64,
    /// Deeper degraded rate (100Hz) on relapse within the relapse window.
    pub deep_degraded_period_us: u64,
    /// Consecutive on-time ticks required to recover to Normal.
    pub recovery_ticks: u64,
    /// Overload within this window after recovery → deeper degrade.
    pub relapse_window_s: u64,
}

impl Default for RuntimeParams {
    fn default() -> Self {
        Self {
            tick_period_us: 500,
            spin_window_us: 125,
            snapshot_divisor: 20,
            ring_capacity: 1024,
            catch_up: CatchUpPolicy::Skip,
            degraded_period_us: 5_000,
            deep_degraded_period_us: 10_000,
            recovery_ticks: 10,
            relapse_window_s: 60,
        }
    }
}

#[derive(Copy, Clone, Debug)]
pub struct PsiConfig {
    /// Determinism pillar 1: single configurable seed.
    pub seed: u64,
    pub needs: [NeedParams; NEED_COUNT],
    /// Serumtonin modulation: θ' = θ · (1 − factor · serumtonin_level).
    /// Spec value 0.3 (theoretical, needs calibration).
    pub serumtonin_factor: f64,
    pub affect: AffectParams,
    pub gate: GateParams,
    pub runtime: RuntimeParams,
}

impl Default for PsiConfig {
    fn default() -> Self {
        // Table from neuralis-psi-v2-minimal-spec.md §2.1; σ from the
        // Python v1 volatilities (within the spec's [0, 0.01] domain).
        let needs = [
            // CERTAINTY
            NeedParams { initial: 0.6, target: 0.8, theta: 0.008, sigma: 0.004, importance: 1.2 },
            // COMPETENCE
            NeedParams { initial: 0.4, target: 0.9, theta: 0.012, sigma: 0.006, importance: 1.5 },
            // AUTONOMY
            NeedParams { initial: 0.5, target: 0.7, theta: 0.005, sigma: 0.003, importance: 1.0 },
            // RELATEDNESS
            NeedParams { initial: 0.5, target: 0.7, theta: 0.010, sigma: 0.005, importance: 0.8 },
            // GROWTH
            NeedParams { initial: 0.5, target: 0.8, theta: 0.006, sigma: 0.004, importance: 1.3 },
        ];
        Self {
            seed: 0,
            needs,
            serumtonin_factor: 0.3,
            affect: AffectParams::default(),
            gate: GateParams::default(),
            runtime: RuntimeParams::default(),
        }
    }
}

impl PsiConfig {
    /// Tick duration in seconds — the `dt` used by all integrators.
    pub fn dt(&self) -> f64 {
        self.runtime.tick_period_us as f64 / 1_000_000.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Guard against re-introducing an unstable default coupling matrix
    /// (saddle point → affect saturates at clamp). See CouplingWeights doc.
    #[test]
    fn stable_coupling_defaults() {
        let w = CouplingWeights::default();
        let l = AffectParams::default().inertia_lambda;
        let sub = |a: f64, d: f64, b: f64, c: f64| {
            let (a, d) = (a - l, d - l);
            assert!(a + d < 0.0, "trace must be negative");
            assert!(a * d - b * c > 0.0, "det must be positive");
        };
        sub(w.w_aa, w.w_stst, w.w_ast, w.w_sta); // (A, St)
        sub(w.w_pp, w.w_ss, w.w_ps, w.w_sp); // (P, S)
    }
}
