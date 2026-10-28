//! Paper-only contracts. Trusted account/configuration/evidence are never Worker input.

mod paper;
pub use paper::*;

/// Not a protocol version. Merely an M0 scaffold identifier.
pub const VERSION: &str = "0.0.1-scaffold";

#[cfg(test)]
mod tests {
    #[test]
    fn scaffold_does_not_claim_trading_readiness() {
        assert!(super::VERSION.contains("scaffold"));
    }
}
