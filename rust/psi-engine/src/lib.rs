//! Neuralis PsiEngine v2 — 2000Hz PSI fast loop.
//!
//! Implementation of `docs/rust-psi/neuralis-psi-v2-minimal-spec.md` and
//! `docs/rust-psi/2000hz-runtime-spec.md` (BASE_SHA ab14499).
//!
//! Layout mirrors the spec architecture:
//! - [`config`] — PsiConfig, every calibratable constant
//! - [`state`] — PsiState (flat Copy struct) + clamp/NaN sanitizer
//! - [`needs`] — NeedDynamics: 5-need OU process, serumtonin, drives
//! - [`affect`] — AffectDynamics: 5D PAD+S+St, coupling, 1/f, endorphin
//! - [`noise`] — deterministic Voss-McCartney pink noise
//! - [`attention`] — AttentionGate: 4 states, hysteresis, min hold
//! - [`events`] — PsiEvent (18 affective events) + pure fold reducer
//! - [`bias`] — 8 cognitive biases, read-side (Tier C)
//! - [`snapshot`] — PsiSnapshot (B-surface) + atomic snapshot cell
//! - [`metrics`] — TickMetrics: hdrhistogram, deadline, drift, catch-up
//! - [`engine`] — PsiEngine: deterministic tick orchestration
//! - [`runtime`] — 2000Hz loop: spin-sleep, overload, circuit breaker
//!
//! Determinism contract (spec §5): same seed + same event sequence at the
//! same tick indices → identical state sequence. Verified by
//! `tests/determinism.rs`.

pub mod affect;
pub mod attention;
pub mod bias;
pub mod config;
pub mod engine;
pub mod events;
pub mod metrics;
pub mod needs;
pub mod noise;
pub mod snapshot;
pub mod state;
pub mod statefile;
pub mod runtime;

pub use attention::{AttentionGate, GateState, GatingDecision};
pub use config::{CatchUpPolicy, NeedKind, PsiConfig};
pub use engine::{PsiEngine, PsiHandle};
pub use events::{AffectiveEvent, PsiEvent};
pub use runtime::{run, run_for, BreakerState, RunReport};
pub use snapshot::{MetricsSummary, PsiSnapshot};
pub use state::PsiState;
