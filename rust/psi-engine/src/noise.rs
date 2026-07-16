//! Deterministic 1/f (pink) noise — Voss-McCartney algorithm.
//!
//! The Python v1 reference shapes white noise in the frequency domain with
//! numpy FFT and an unseeded RNG; that is neither allocation-free nor
//! deterministic. Voss-McCartney sums N white-noise rows where row k is
//! refreshed every 2^k samples — O(1) per sample, no allocation, and fully
//! driven by the engine's single seeded RNG (determinism pillar 1).

use rand::Rng;
use rand_distr::StandardNormal;

const ROWS: usize = 16;

#[derive(Clone, Debug)]
pub struct PinkNoise {
    rows: [f64; ROWS],
    counter: u64,
    /// Normalizes the row sum to roughly unit variance.
    scale: f64,
}

impl PinkNoise {
    pub fn new() -> Self {
        Self {
            rows: [0.0; ROWS],
            counter: 0,
            scale: 1.0 / (ROWS as f64).sqrt(),
        }
    }

    /// Next pink sample, ~unit variance. Draws at most 2 normals per call
    /// from the shared RNG (always exactly one for the trailing-zero row
    /// plus one white component — a fixed count, so the RNG stream stays
    /// aligned for replay).
    pub fn sample<R: Rng>(&mut self, rng: &mut R) -> f64 {
        let row = (self.counter.trailing_zeros() as usize).min(ROWS - 1);
        self.rows[row] = rng.sample(StandardNormal);
        self.counter = self.counter.wrapping_add(1);
        let white: f64 = rng.sample(StandardNormal);
        (self.rows.iter().sum::<f64>() + white) * self.scale
    }
}

impl Default for PinkNoise {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::{rngs::StdRng, SeedableRng};

    #[test]
    fn same_seed_same_sequence() {
        let mut a = (PinkNoise::new(), StdRng::seed_from_u64(7));
        let mut b = (PinkNoise::new(), StdRng::seed_from_u64(7));
        for _ in 0..1000 {
            assert_eq!(a.0.sample(&mut a.1), b.0.sample(&mut b.1));
        }
    }

    #[test]
    fn bounded_with_long_memory_offset() {
        let mut p = PinkNoise::new();
        let mut rng = StdRng::seed_from_u64(42);
        let n = 20_000;
        let mut sum = 0.0;
        for _ in 0..n {
            let s = p.sample(&mut rng);
            assert!(s.is_finite());
            assert!(s.abs() < 10.0, "sample {s} implausibly large");
            sum += s;
        }
        // 1/f noise has power at low frequencies: slow rows hold their
        // value across most of a finite window, so the window mean sits
        // OFF zero — that is the point of pink noise. Only guard against
        // gross drift (an unbounded accumulator bug), not near-zero mean.
        assert!((sum / n as f64).abs() < 0.75);
    }
}
