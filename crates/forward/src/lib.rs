//! A separate observe-only journal. No dependency on risk, execution or money ledgers.
mod continuity;
mod model;
mod provider;
mod report;
mod store;
pub use continuity::{EodStep, EodView};
pub use model::*;
pub use provider::source_check;
pub use store::Journal;
pub type Result<T> = std::result::Result<T, String>;

pub(crate) fn hash(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests;
