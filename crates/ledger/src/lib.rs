//! Trusted paper-only execution and durable ledger. No broker or Worker runtime.
mod engine;
mod model;
mod store;
pub use model::*;
pub use store::Ledger;
pub mod synthetic;
