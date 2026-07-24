//! Native state-file contract — serialize a `PsiSnapshot` to the
//! `neuralis-rust-psi/v1` JSON schema and publish it atomically.
//!
//! M3 B-route decision (2026-07-24): the Rust engine writes its OWN native
//! schema; Python readers migrate to consume it (not a byte-for-byte copy
//! of the legacy `_write_author_state` payload). This keeps the Rust
//! attention model (Idle/Task/Learning/Planning) and affect structure
//! honest instead of emulating the Python vocabulary.
//!
//! No serde: every value is a f64/u64 or a fixed string key, so a
//! hand-rolled writer has zero injection surface and no dependency cost.

use std::fs;
use std::io;
use std::path::Path;

use crate::config::{
    AROUSAL, DOMINANCE, NEED_COUNT, PLEASURE, SOCIAL, STRESS,
};
use crate::snapshot::PsiSnapshot;

pub const STATE_SCHEMA: &str = "neuralis-rust-psi/v1";
pub const STATE_SOURCE: &str = "neuralis-rust-psi";

/// NeedKind order (config.rs): Certainty, Competence, Autonomy,
/// Relatedness, Growth. `snapshot.needs[i]` / `drives[i]` follow it.
const NEED_NAMES: [&str; NEED_COUNT] =
    ["certainty", "competence", "autonomy", "relatedness", "growth"];

/// GateState → lowercase tag (Python readers key on this string).
fn attention_tag(a: crate::attention::GateState) -> &'static str {
    use crate::attention::GateState::*;
    match a {
        Idle => "idle",
        Task => "task",
        Learning => "learning",
        Planning => "planning",
    }
}

/// One flat `{name: value, ...}` object from a 5-array + name table.
fn need_object(vals: &[f64; NEED_COUNT]) -> String {
    let mut s = String::from("{");
    for i in 0..NEED_COUNT {
        if i > 0 {
            s.push(',');
        }
        s.push_str(&format!("\"{}\":{}", NEED_NAMES[i], vals[i]));
    }
    s.push('}');
    s
}

/// Serialize a snapshot to the `neuralis-rust-psi/v1` schema.
/// `daemon_uptime_s` / `ts_s` are wall-clock; the snapshot itself carries
/// only logical time (`tick_count`, `timestamp_us`).
pub fn snapshot_to_json(
    snap: &PsiSnapshot,
    daemon_uptime_s: f64,
    ts_s: f64,
) -> String {
    let a = &snap.affect;
    format!(
        concat!(
            "{{\"schema\":\"{schema}\",",
            "\"tick\":{tick},",
            "\"needs\":{needs},",
            "\"drives\":{drives},",
            "\"affect\":{{\"pleasure\":{p},\"arousal\":{ar},\"dominance\":{d},\"social\":{so},\"stress\":{st}}},",
            "\"endorphin\":{endo},",
            "\"attention\":\"{att}\",",
            "\"metrics\":{{\"ticks\":{mt},\"deadline_misses\":{mm},\"drift_us\":{md},\"last_compute_us\":{mc}}},",
            "\"daemon_uptime\":{up},",
            "\"ts\":{ts},",
            "\"source\":\"{source}\"}}"
        ),
        schema = STATE_SCHEMA,
        tick = snap.tick_count,
        needs = need_object(&snap.needs),
        drives = need_object(&snap.drives),
        p = a[PLEASURE],
        ar = a[AROUSAL],
        d = a[DOMINANCE],
        so = a[SOCIAL],
        st = a[STRESS],
        endo = snap.endorphin,
        att = attention_tag(snap.attention),
        mt = snap.metrics.ticks,
        mm = snap.metrics.deadline_misses,
        md = snap.metrics.drift_us,
        mc = snap.metrics.last_compute_us,
        up = daemon_uptime_s,
        ts = ts_s,
        source = STATE_SOURCE,
    )
}

/// Publish atomically: write `<path>.tmp` in the same dir, fsync-free
/// rename over `path`. Readers see either the old or the new whole file,
/// never a torn one (rename is atomic on the same filesystem).
pub fn write_atomic(path: &Path, contents: &str) -> io::Result<()> {
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, contents)?;
    fs::rename(&tmp, path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::attention::GateState;
    use crate::snapshot::{MetricsSummary, PsiSnapshot};

    fn sample() -> PsiSnapshot {
        PsiSnapshot {
            needs: [0.1, 0.2, 0.3, 0.4, 0.5],
            drives: [0.5, 0.4, 0.3, 0.2, 0.1],
            affect: [0.11, 0.22, 0.33, 0.44, 0.55],
            endorphin: -0.07,
            attention: GateState::Learning,
            timestamp_us: 123,
            tick_count: 4242,
            metrics: MetricsSummary {
                ticks: 4242,
                deadline_misses: 1,
                drift_us: -3,
                last_compute_us: 8,
            },
        }
    }

    #[test]
    fn json_has_all_five_needs_by_name() {
        let j = snapshot_to_json(&sample(), 1.0, 2.0);
        for name in NEED_NAMES {
            assert!(j.contains(&format!("\"{name}\":")), "missing need {name}");
        }
    }

    #[test]
    fn attention_tag_is_native_vocab() {
        let j = snapshot_to_json(&sample(), 0.0, 0.0);
        assert!(j.contains("\"attention\":\"learning\""));
        assert_eq!(attention_tag(GateState::Idle), "idle");
        assert_eq!(attention_tag(GateState::Planning), "planning");
    }

    #[test]
    fn affect_dims_map_to_pad_s_st() {
        let j = snapshot_to_json(&sample(), 0.0, 0.0);
        assert!(j.contains("\"pleasure\":0.11"));
        assert!(j.contains("\"arousal\":0.22"));
        assert!(j.contains("\"dominance\":0.33"));
        assert!(j.contains("\"social\":0.44"));
        assert!(j.contains("\"stress\":0.55"));
    }

    #[test]
    fn schema_and_source_stamped() {
        let j = snapshot_to_json(&sample(), 12.5, 99.0);
        assert!(j.contains("\"schema\":\"neuralis-rust-psi/v1\""));
        assert!(j.contains("\"source\":\"neuralis-rust-psi\""));
        assert!(j.contains("\"tick\":4242"));
        assert!(j.contains("\"daemon_uptime\":12.5"));
    }

    #[test]
    fn round_trips_as_valid_json_shape() {
        // No serde in the crate; assert the structural invariants a naive
        // parser needs: balanced braces, no trailing comma, quoted keys.
        let j = snapshot_to_json(&sample(), 1.0, 2.0);
        assert_eq!(j.matches('{').count(), j.matches('}').count());
        assert!(j.starts_with('{') && j.ends_with('}'));
        assert!(!j.contains(",}"));
    }
}
