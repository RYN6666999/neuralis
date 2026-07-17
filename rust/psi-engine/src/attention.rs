//! AttentionGate — 4 states with hysteresis (autonomic HysteresisGate
//! pattern: separate enter/exit thresholds + minimum hold time).
//!
//! No SOCIAL state (spec §2.3 — removed from the Neuralis v1 design).
//! Candidate priority: PLANNING (competition) > TASK (dominant drive) >
//! LEARNING (uncertainty) > IDLE.

use crate::config::{GateParams, NEED_COUNT};

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum GateState {
    Idle,
    Task,
    Learning,
    Planning,
}

/// autonomic GatingDecision shape: what the gate did this tick.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum GatingDecision {
    Enter(GateState),
    Stay,
    /// A transition was warranted but suppressed by the minimum hold.
    Block,
    /// Fell back to Idle.
    Exit,
}

#[derive(Clone, Debug)]
pub struct AttentionGate {
    params: GateParams,
    state: GateState,
    ticks_in_state: u64,
}

impl AttentionGate {
    pub fn new(params: GateParams) -> Self {
        Self {
            params,
            state: GateState::Idle,
            ticks_in_state: 0,
        }
    }

    pub fn state(&self) -> GateState {
        self.state
    }

    /// Evaluate one tick. `drives` in NeedKind order; `uncertainty` is
    /// 1 − certainty need (the LEARNING trigger).
    pub fn update(&mut self, drives: &[f64; NEED_COUNT], uncertainty: f64) -> GatingDecision {
        self.ticks_in_state = self.ticks_in_state.saturating_add(1);
        let p = &self.params;

        let max_drive = drives.iter().copied().fold(0.0_f64, f64::max);
        let competing = drives.iter().filter(|&&d| d > p.planning_enter).count();

        // Hysteresis: while the current state's exit condition still holds,
        // stay put — enter thresholds are only consulted from below.
        let holds = match self.state {
            GateState::Task => max_drive > p.task_exit,
            GateState::Learning => uncertainty > p.learning_exit,
            GateState::Planning => competing >= 2 || max_drive > p.planning_exit,
            GateState::Idle => {
                // Idle "holds" only if nothing wants to enter.
                competing < 2 && max_drive <= p.task_enter && uncertainty <= p.learning_enter
            }
        };
        if holds {
            return GatingDecision::Stay;
        }

        // Candidate by priority (enter thresholds).
        let candidate = if competing >= 2 {
            GateState::Planning
        } else if max_drive > p.task_enter {
            GateState::Task
        } else if uncertainty > p.learning_enter {
            GateState::Learning
        } else {
            GateState::Idle
        };

        if candidate == self.state {
            return GatingDecision::Stay;
        }
        if self.ticks_in_state < p.min_hold_ticks {
            return GatingDecision::Block;
        }

        self.state = candidate;
        self.ticks_in_state = 0;
        if candidate == GateState::Idle {
            GatingDecision::Exit
        } else {
            GatingDecision::Enter(candidate)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::NeedKind;

    fn params() -> GateParams {
        GateParams {
            min_hold_ticks: 10,
            ..GateParams::default()
        }
    }

    fn drives_with(kind: NeedKind, v: f64) -> [f64; NEED_COUNT] {
        let mut d = [0.0; NEED_COUNT];
        d[kind as usize] = v;
        d
    }

    #[test]
    fn idle_to_task_on_dominant_drive() {
        let mut g = AttentionGate::new(params());
        let d = drives_with(NeedKind::Competence, 0.8);
        // Held for min_hold first.
        for _ in 0..9 {
            assert_eq!(g.update(&d, 0.0), GatingDecision::Block);
        }
        assert_eq!(g.update(&d, 0.0), GatingDecision::Enter(GateState::Task));
        assert_eq!(g.state(), GateState::Task);
    }

    #[test]
    fn planning_beats_task_when_drives_compete() {
        let mut g = AttentionGate::new(params());
        let mut d = [0.0; NEED_COUNT];
        d[0] = 0.7;
        d[1] = 0.6;
        for _ in 0..20 {
            g.update(&d, 0.0);
        }
        assert_eq!(g.state(), GateState::Planning);
    }

    #[test]
    fn learning_on_high_uncertainty() {
        let mut g = AttentionGate::new(params());
        let d = [0.0; NEED_COUNT];
        for _ in 0..20 {
            g.update(&d, 0.9);
        }
        assert_eq!(g.state(), GateState::Learning);
    }

    /// The flapping test the hysteresis exists for: a signal oscillating
    /// between exit and enter thresholds must not toggle the state.
    #[test]
    fn no_flapping_between_enter_and_exit_thresholds() {
        let p = params();
        let mut g = AttentionGate::new(p);
        // Enter TASK.
        let hi = drives_with(NeedKind::Competence, p.task_enter + 0.2);
        for _ in 0..20 {
            g.update(&hi, 0.0);
        }
        assert_eq!(g.state(), GateState::Task);
        // Oscillate inside the hysteresis band (above exit, below enter).
        let band = drives_with(NeedKind::Competence, (p.task_enter + p.task_exit) / 2.0);
        for _ in 0..1000 {
            assert_eq!(g.update(&band, 0.0), GatingDecision::Stay);
        }
        assert_eq!(g.state(), GateState::Task);
    }

    #[test]
    fn exits_to_idle_when_drive_collapses() {
        let p = params();
        let mut g = AttentionGate::new(p);
        let hi = drives_with(NeedKind::Competence, 0.8);
        for _ in 0..20 {
            g.update(&hi, 0.0);
        }
        assert_eq!(g.state(), GateState::Task);
        let none = [0.0; NEED_COUNT];
        let mut saw_exit = false;
        for _ in 0..20 {
            if g.update(&none, 0.0) == GatingDecision::Exit {
                saw_exit = true;
            }
        }
        assert!(saw_exit);
        assert_eq!(g.state(), GateState::Idle);
    }

    #[test]
    fn min_hold_blocks_immediate_reversal() {
        let p = params();
        let mut g = AttentionGate::new(p);
        let hi = drives_with(NeedKind::Competence, 0.8);
        for _ in 0..10 {
            g.update(&hi, 0.0);
        }
        assert_eq!(g.state(), GateState::Task);
        // Drive collapses right after entering: hold must block the exit.
        let none = [0.0; NEED_COUNT];
        assert_eq!(g.update(&none, 0.0), GatingDecision::Block);
        assert_eq!(g.state(), GateState::Task);
    }
}
