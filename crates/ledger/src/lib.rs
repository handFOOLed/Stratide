//! Trusted paper-only execution and durable ledger. No broker or Worker runtime.
pub mod cash_dividend;
mod engine;
mod model;
pub mod paper_eod;
mod store;
pub use model::*;
pub use store::{AuditEntry, Ledger};
pub mod synthetic;
