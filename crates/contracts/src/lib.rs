//! Compile-time workspace anchor only. Trading contracts require grill-with-docs review.

/// Not a protocol version. Merely an M0 scaffold identifier.
pub const VERSION: &str = "0.0.1-scaffold";

#[cfg(test)]
mod tests {
    #[test]
    fn scaffold_does_not_claim_trading_readiness() {
        assert!(super::VERSION.contains("scaffold"));
    }
}
