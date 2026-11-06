//! One first-launch Owner agreement.
//!
//! The agreement text lives in the dashboard; the trusted service only records
//! that the Owner accepted it and materializes the single standing consent the
//! research code checks (the market-research egress scope). The app never shows
//! another permission prompt.
use crate::{market_research, risk_binding, Agent, Result};
use chrono::Utc;
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};

pub const VERSION: &str = "owner-agreement-v1";

fn agent_dir(agent: &Agent) -> Result<&Path> {
    Ok(agent
        .settings_path()
        .parent()
        .ok_or("AGENT_SETTINGS_PATH_INVALID")?)
}

fn record_path(agent: &Agent) -> Result<PathBuf> {
    Ok(agent_dir(agent)?.join("consent.json"))
}

/// Older installs wrote the seen record under the data runtime directory.
fn legacy_path(agent: &Agent) -> Result<PathBuf> {
    let data = agent_dir(agent)?
        .parent()
        .ok_or("AGENT_SETTINGS_PATH_INVALID")?;
    Ok(data.join("runtime").join("consent.json"))
}

fn read_file(path: &Path) -> Option<Value> {
    let raw = fs::read(path).ok()?;
    let value: Value = serde_json::from_slice(&raw).ok()?;
    let accepted_at = value["accepted_at"].as_str()?;
    if value["version"] != VERSION || accepted_at.is_empty() {
        return None;
    }
    Some(value)
}

fn write_record(agent: &Agent, record: &Value) -> Result<()> {
    let path = record_path(agent)?;
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir).map_err(|_| "CONSENT_WRITE_FAILED")?;
    }
    let pending = path.with_extension("json.pending");
    fs::write(
        &pending,
        serde_json::to_vec_pretty(record).expect("consent JSON"),
    )
    .map_err(|_| "CONSENT_WRITE_FAILED")?;
    fs::rename(&pending, &path).map_err(|_| "CONSENT_WRITE_FAILED")?;
    Ok(())
}

fn read_record(agent: &Agent) -> Option<Value> {
    if let Ok(path) = record_path(agent) {
        if let Some(value) = read_file(&path) {
            return Some(value);
        }
    }
    let legacy = legacy_path(agent).ok()?;
    let value = read_file(&legacy)?;
    // Keep the seen flag next to settings so a later layout change still finds it.
    let _ = write_record(agent, &value);
    Some(value)
}

/// Create the standing grant only when none was recorded. Failures stay local:
/// the seen flag is already durable, and the next status read tries again.
/// Unit tests skip this so they cannot write a grant into the repo state root.
fn materialize_if_absent(agent: &Agent) {
    if cfg!(test) {
        return;
    }
    if !market_research::standing_grant_absent(agent) {
        return;
    }
    let _ = (|| -> Result<()> {
        let root = crate::risk_portfolio::root()?;
        if !root.join("agent-binding.json").exists() {
            risk_binding::bind_attached(agent)?;
        }
        market_research::grant_defaults(agent)?;
        Ok(())
    })();
}

pub fn status(agent: &Agent) -> Result<Value> {
    let accepted = read_record(agent);
    let accepted_at = accepted
        .as_ref()
        .and_then(|value| value["accepted_at"].as_str())
        .map(str::to_string);
    if accepted_at.is_some() {
        materialize_if_absent(agent);
    }
    Ok(json!({
        "version": VERSION,
        "required": accepted_at.is_none(),
        "accepted_at": accepted_at,
    }))
}

pub fn accept(agent: &Agent) -> Result<Value> {
    if read_record(agent).is_none() {
        let record = json!({
            "version": VERSION,
            "accepted_at": Utc::now().to_rfc3339(),
        });
        write_record(agent, &record)?;
    }
    // The seen record is written before the grant. A grant/bind failure must
    // not bring the page back; status retries a missing grant later.
    status(agent)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Settings;
    use crate::InputSummary;

    fn open_agent(dir: &std::path::Path) -> Agent {
        std::fs::create_dir_all(dir).unwrap();
        std::fs::write(
            dir.join("settings.json"),
            serde_json::to_vec(&Settings::fake()).unwrap(),
        )
        .unwrap();
        Agent::open(
            dir,
            None,
            InputSummary {
                version: "synthetic_test:consent".into(),
                source_day: "2026-11-04".into(),
                mode: "synthetic_test".into(),
                scopes: vec!["owner_task".into()],
                summary: json!({}),
                eod_eligible: false,
            },
        )
        .unwrap()
    }

    #[test]
    fn agreement_version_is_frozen() {
        assert_eq!(VERSION, "owner-agreement-v1");
    }

    #[test]
    fn seen_record_hides_the_page_and_a_second_accept_is_idempotent() {
        let root = tempfile::tempdir().unwrap();
        let agent = open_agent(&root.path().join("agent"));
        let before = status(&agent).unwrap();
        assert_eq!(before["required"], json!(true));
        assert!(crate::market_research::standing_grant_absent(&agent));
        let accepted = accept(&agent).unwrap();
        assert_eq!(accepted["required"], json!(false));
        assert!(accepted["accepted_at"].as_str().unwrap().len() > 0);
        assert!(root.path().join("agent").join("consent.json").is_file());
        let again = accept(&agent).unwrap();
        assert_eq!(again["required"], json!(false));
        assert_eq!(again["accepted_at"], accepted["accepted_at"]);
    }

    #[test]
    fn legacy_runtime_record_is_still_accepted() {
        let root = tempfile::tempdir().unwrap();
        let agent_dir = root.path().join("agent");
        let agent = open_agent(&agent_dir);
        let legacy = root.path().join("runtime");
        std::fs::create_dir_all(&legacy).unwrap();
        std::fs::write(
            legacy.join("consent.json"),
            br#"{"version":"owner-agreement-v1","accepted_at":"2026-11-01T00:00:00Z"}"#,
        )
        .unwrap();
        let viewed = status(&agent).unwrap();
        assert_eq!(viewed["required"], json!(false));
        assert_eq!(viewed["accepted_at"], "2026-11-01T00:00:00Z");
        assert!(agent_dir.join("consent.json").is_file());
    }
}
