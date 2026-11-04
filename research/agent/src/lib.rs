pub mod budget;
pub mod config;
pub mod deepseek;
pub mod desktop;
pub mod eod_snapshot;
pub mod fusion_researcher;
pub mod local_fusion;
#[cfg(test)]
mod local_fusion_tests;
pub mod multimodal;
pub mod provider;
pub mod risk_binding;
pub mod risk_cloud;
pub mod risk_cpu;
pub mod risk_history;
pub mod risk_portfolio;
#[cfg(test)]
mod risk_portfolio_tests;
mod service;
mod store;
pub mod structured;
#[cfg(test)]
mod structured_tests;
use serde::{Deserialize, Serialize};
use serde_json::Value;
pub use service::Agent;
use sha2::{Digest, Sha256};
pub use store::Store;

#[derive(Debug, Clone)]
pub struct Error(pub String);
impl From<&str> for Error {
    fn from(s: &str) -> Self {
        Self(s.into())
    }
}
impl From<String> for Error {
    fn from(s: String) -> Self {
        Self(s)
    }
}
impl From<rusqlite::Error> for Error {
    fn from(_: rusqlite::Error) -> Self {
        Self("AGENT_STORAGE_UNAVAILABLE".into())
    }
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for Error {}
pub type Result<T> = std::result::Result<T, Error>;
pub fn ensure(ok: bool, message: &str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn nonce() -> Result<String> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).map_err(|_| "RANDOM_UNAVAILABLE")?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Research {
    pub hypothesis: String,
    pub evidence: Vec<String>,
    pub risks: Vec<String>,
    pub next_steps: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fusion: Option<Box<multimodal::Fusion>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub risk_portfolio: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub structured_research: Option<structured::Receipt>,
}
impl Research {
    pub fn validate(&self) -> Result<()> {
        if let Some(receipt) = &self.structured_research {
            receipt.validate()?;
        }
        if let Some(v) = &self.risk_portfolio {
            risk_portfolio::validate_output(v)?;
        }
        if let Some(fusion) = &self.fusion {
            fusion.validate()?;
        }
        ensure(
            !self.hypothesis.trim().is_empty()
                && self.hypothesis.len() <= 4096
                && [&self.evidence, &self.risks, &self.next_steps]
                    .iter()
                    .all(|a| {
                        !a.is_empty()
                            && a.len() <= 8
                            && a.iter().all(|s| !s.trim().is_empty() && s.len() <= 2048)
                    })
                && serde_json::to_vec(self).is_ok_and(|s| {
                    s.len()
                        <= if self.risk_portfolio.is_some() || self.structured_research.is_some() {
                            65536
                        } else {
                            16384
                        }
                }),
            "RESEARCH_OUTPUT_INVALID",
        )
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TaskRequest {
    pub name: String,
    pub goal: String,
    pub scope: String,
    pub start_day: String,
    pub end_day: String,
    pub task_budget_micro: Option<String>,
}
impl TaskRequest {
    pub fn validate(&self) -> Result<Option<i64>> {
        ensure(
            [(&self.name, 120), (&self.goal, 2000), (&self.scope, 300)]
                .iter()
                .all(|(v, max)| {
                    !v.trim().is_empty()
                        && v.len() <= *max
                        && !v.chars().any(|c| c.is_control() && c != '\n')
                }),
            "TASK_INPUT_INVALID",
        )?;
        let start = parse_day(&self.start_day)?;
        let end = parse_day(&self.end_day)?;
        ensure(start <= end, "TASK_DATE_RANGE_INVALID")?;
        self.task_budget_micro
            .as_deref()
            .map(|s| {
                let value = s.parse::<i64>().map_err(|_| "TASK_BUDGET_INVALID")?;
                ensure(
                    value > 0 && value <= 1_000_000_000_000,
                    "TASK_BUDGET_INVALID",
                )?;
                Ok(value)
            })
            .transpose()
    }
}
pub fn parse_day(s: &str) -> Result<chrono::NaiveDate> {
    ensure(s.len() == 10, "TASK_DATE_INVALID")?;
    let d = chrono::NaiveDate::parse_from_str(s, "%Y-%m-%d").map_err(|_| "TASK_DATE_INVALID")?;
    ensure(d.format("%Y-%m-%d").to_string() == s, "TASK_DATE_INVALID")?;
    Ok(d)
}

/// Constructed only from explicitly selected, validated host projections.
#[derive(Clone, Serialize, Deserialize)]
pub struct InputSummary {
    pub version: String,
    pub source_day: String,
    pub mode: String,
    pub scopes: Vec<String>,
    pub summary: Value,
    // True only for a verified published source session; never inferred weekdays.
    pub eod_eligible: bool,
}

impl InputSummary {
    pub fn is_eod_snapshot(&self) -> bool {
        self.scopes.iter().any(|s| s == eod_snapshot::SCOPE)
    }
}
