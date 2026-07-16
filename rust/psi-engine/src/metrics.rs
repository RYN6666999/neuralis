//! TickMetrics — hdrhistogram + deadline miss + drift + catch-up counters
//! (2000hz-runtime-spec.md §4). Everything here is allocation-free after
//! construction, so recording is fast-loop safe.

use hdrhistogram::Histogram;

use crate::config::CatchUpPolicy;
use crate::snapshot::MetricsSummary;

#[derive(Debug)]
pub struct TickMetrics {
    /// Compute duration, µs. Bounds cover 1µs..10s at 3 sig figs.
    hist: Histogram<u64>,
    period_us: u64,
    pub ticks: u64,
    pub deadline_misses: u64,
    /// Σ(actual_interval − period) in ns. Accumulated at ns resolution:
    /// µs truncation biases each ~500µs interval by up to −1µs, which
    /// integrates to seconds-scale phantom drift over a soak run.
    pub drift_ns: i64,
    pub last_compute_us: u64,
    pub catchup_skip: u64,
    pub catchup_burst: u64,
    pub catchup_delay: u64,
    pub breaker_trips: u64,
}

/// Aggregated view for reports and the bench binary.
#[derive(Copy, Clone, Debug)]
pub struct MetricsReport {
    pub ticks: u64,
    pub deadline_misses: u64,
    pub miss_ratio: f64,
    pub drift_us: i64,
    pub p50_us: u64,
    pub p95_us: u64,
    pub p99_us: u64,
    pub p999_us: u64,
    pub max_us: u64,
    pub catchup_skip: u64,
    pub catchup_burst: u64,
    pub catchup_delay: u64,
    pub breaker_trips: u64,
}

impl TickMetrics {
    pub fn new(period_us: u64) -> Self {
        Self {
            hist: Histogram::new_with_bounds(1, 10_000_000, 3)
                .expect("static bounds are valid"),
            period_us,
            ticks: 0,
            deadline_misses: 0,
            drift_ns: 0,
            last_compute_us: 0,
            catchup_skip: 0,
            catchup_burst: 0,
            catchup_delay: 0,
            breaker_trips: 0,
        }
    }

    /// Record one tick's compute duration. Deadline rule per spec §6:
    /// compute_duration > period → miss.
    pub fn record_compute(&mut self, us: u64) {
        self.ticks += 1;
        self.last_compute_us = us;
        self.hist.saturating_record(us.max(1));
        if us > self.period_us {
            self.deadline_misses += 1;
        }
    }

    /// Record the true tick-to-tick interval; drift = Σ(actual − period).
    pub fn record_interval_ns(&mut self, actual_ns: u64) {
        self.drift_ns += actual_ns as i64 - (self.period_us * 1_000) as i64;
    }

    pub fn record_catchup(&mut self, policy: CatchUpPolicy) {
        match policy {
            CatchUpPolicy::Skip => self.catchup_skip += 1,
            CatchUpPolicy::Burst => self.catchup_burst += 1,
            CatchUpPolicy::Delay => self.catchup_delay += 1,
        }
    }

    pub fn summary(&self) -> MetricsSummary {
        MetricsSummary {
            ticks: self.ticks,
            deadline_misses: self.deadline_misses,
            drift_us: self.drift_ns / 1_000,
            last_compute_us: self.last_compute_us,
        }
    }

    pub fn report(&self) -> MetricsReport {
        let q = |x: f64| self.hist.value_at_quantile(x);
        MetricsReport {
            ticks: self.ticks,
            deadline_misses: self.deadline_misses,
            miss_ratio: if self.ticks == 0 {
                0.0
            } else {
                self.deadline_misses as f64 / self.ticks as f64
            },
            drift_us: self.drift_ns / 1_000,
            p50_us: q(0.50),
            p95_us: q(0.95),
            p99_us: q(0.99),
            p999_us: q(0.999),
            max_us: self.hist.max(),
            catchup_skip: self.catchup_skip,
            catchup_burst: self.catchup_burst,
            catchup_delay: self.catchup_delay,
            breaker_trips: self.breaker_trips,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn miss_counted_only_above_period() {
        let mut m = TickMetrics::new(500);
        m.record_compute(499);
        m.record_compute(500);
        m.record_compute(501);
        assert_eq!(m.ticks, 3);
        assert_eq!(m.deadline_misses, 1);
        assert!((m.report().miss_ratio - 1.0 / 3.0).abs() < 1e-12);
    }

    #[test]
    fn drift_accumulates_signed_at_ns_resolution() {
        let mut m = TickMetrics::new(500);
        m.record_interval_ns(520_000); // +20µs
        m.record_interval_ns(490_000); // -10µs
        assert_eq!(m.drift_ns, 10_000);
        assert_eq!(m.report().drift_us, 10);
        // Sub-µs residue is retained, not truncated away per interval.
        m.record_interval_ns(500_400);
        m.record_interval_ns(500_400);
        assert_eq!(m.drift_ns, 10_800);
    }

    #[test]
    fn percentiles_ordered() {
        let mut m = TickMetrics::new(500);
        for us in 1..=1000 {
            m.record_compute(us);
        }
        let r = m.report();
        assert!(r.p50_us <= r.p95_us);
        assert!(r.p95_us <= r.p99_us);
        assert!(r.p99_us <= r.p999_us);
        assert!(r.p999_us <= r.max_us);
    }

    #[test]
    fn catchup_counted_by_type() {
        let mut m = TickMetrics::new(500);
        m.record_catchup(CatchUpPolicy::Skip);
        m.record_catchup(CatchUpPolicy::Skip);
        m.record_catchup(CatchUpPolicy::Burst);
        assert_eq!((m.catchup_skip, m.catchup_burst, m.catchup_delay), (2, 1, 0));
    }
}
