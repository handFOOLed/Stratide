//! One first-launch Owner agreement.
//!
//! The agreement text lives in the dashboard; the trusted service only records
//! that the Owner accepted it and materializes the single standing consent the
//! research code checks (the market-research egress scope). The app never shows
//! another permission prompt.
use crate::{ensure, market_research, risk_binding, Agent, Result};
use chrono::Utc;
use serde_json::{json, Value};
use std::fs;

pub const VERSION: &str = "owner-agreement-v1";

fn path(agent: &Agent) -> Result<std::path::PathBuf> {
    let data = agent
        .settings_path()
        .parent()
        .and_then(|agent_dir| agent_dir.parent())
        .ok_or("AGENT_SETTINGS_PATH_INVALID")?;
    Ok(data.join("runtime").join("consent.json"))
}

pub fn status(agent: &Agent) -> Result<Value> {
    let path = path(agent)?;
    let accepted: Option<Value> = path
        .is_file()
        .then(|| fs::read(&path).ok())
        .flatten()
        .and_then(|raw| serde_json::from_slice(&raw).ok());
    let accepted_at = accepted
        .as_ref()
        .and_then(|value| value["accepted_at"].as_str())
        .map(String::from);
    Ok(json!({
        "version": VERSION,
        "required": accepted_at.is_none(),
        "accepted_at": accepted_at,
    }))
}

pub fn accept(agent: &Agent) -> Result<Value> {
    ensure(status(agent)?["required"] == json!(true), "CONSENT_ALREADY_ACCEPTED")?;
    let root = crate::risk_portfolio::root()?;
    if !root.join("agent-binding.json").exists() {
        risk_binding::bind_attached(agent)?;
    }
    market_research::grant_defaults(agent)?;
    let record = json!({
        "version": VERSION,
        "accepted_at": Utc::now().to_rfc3339(),
    });
    let path = path(agent)?;
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir).map_err(|_| "CONSENT_WRITE_FAILED")?;
    }
    let pending = path.with_extension("json.pending");
    fs::write(
        &pending,
        serde_json::to_vec_pretty(&record).expect("consent JSON"),
    )
    .map_err(|_| "CONSENT_WRITE_FAILED")?;
    fs::rename(&pending, &path).map_err(|_| "CONSENT_WRITE_FAILED")?;
    status(agent)
}

#[cfg(test)]
mod tests {
    #[test]
    fn agreement_version_is_frozen() {
        assert_eq!(super::VERSION, "owner-agreement-v1");
    }
}
