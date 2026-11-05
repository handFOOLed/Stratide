//! One explicit Owner action that connects a cloud research provider.
//!
//! Only the official DeepSeek and OpenAI endpoints are accepted. The API key is
//! stored in Windows Credential Manager and never echoed back. DeepSeek also
//! receives the frozen provider configuration the market-research pipeline reads;
//! OpenAI is stored and connectivity-tested but is not wired into the market
//! pipeline, whose fusion contract pins the DeepSeek model.
use crate::{config::Settings, credman, deepseek, ensure, hash, market_research, Agent, Result};
use chrono::{Duration, Utc};
use serde_json::{json, Value};

pub const DEEPSEEK: &str = "deepseek";
pub const OPENAI: &str = "openai";
const PROFILE: &str = "provider_profile_v1";
const FUSION: &str = "local_timesfm_fusion_config_v1";

fn endpoint(provider: &str) -> Result<&'static str> {
    match provider {
        DEEPSEEK => Ok("https://api.deepseek.com"),
        OPENAI => Ok("https://api.openai.com/v1"),
        _ => Err("PROVIDER_UNSUPPORTED".into()),
    }
}

fn label(provider: &str) -> &'static str {
    match provider {
        DEEPSEEK => "DeepSeek",
        OPENAI => "OpenAI",
        _ => "unknown",
    }
}

fn valid_key(key: &str) -> bool {
    key.starts_with("sk-")
        && (24..=256).contains(&key.len())
        && key
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

pub fn target(agent: &Agent, provider: &str) -> String {
    let digest = hash(agent.settings_path().to_string_lossy().as_bytes());
    format!("Stratide/{digest}/research-{provider}-v1")
}

fn profile(agent: &Agent) -> Result<Option<Value>> {
    agent
        .store()
        .setting(PROFILE)?
        .map(|raw| serde_json::from_str(&raw).map_err(|_| "PROVIDER_PROFILE_INVALID".into()))
        .transpose()
}

pub fn configure(agent: &Agent, body: &Value) -> Result<Value> {
    let provider = body["provider"].as_str().ok_or("PROVIDER_REQUIRED")?;
    endpoint(provider)?;
    let key = body["key"].as_str().ok_or("PROVIDER_KEY_REQUIRED")?.trim();
    ensure(valid_key(key), "PROVIDER_KEY_INVALID")?;
    // The market pipeline reuses this Owner agent store as its cost ledger; the
    // binding is created once, before the first secret, and stays immutable.
    let root = crate::risk_portfolio::root()?;
    if !root.join("agent-binding.json").exists() {
        crate::risk_binding::bind_attached(agent)?;
    }
    let target = target(agent, provider);
    credman::write(&target, &format!("Stratide {}", label(provider)), key)?;
    let now = Utc::now();
    let record = json!({
        "provider": provider,
        "target": target,
        "configured_at": now.to_rfc3339(),
    });
    agent
        .store()
        .set(PROFILE, &serde_json::to_string(&record).expect("profile JSON"))?;
    if provider == DEEPSEEK {
        let until = now + Duration::days(7);
        let config = deepseek::Config {
            version: 1,
            key_file: agent.settings_path().with_file_name("credential-deepseek.md"),
            credential_target: Some(target.clone()),
            grant_version: "deepseek-synthetic-grant-v1".into(),
            synthetic_only: true,
            provider_terms_reviewed: true,
            authorized_at: now.to_rfc3339(),
            price_reviewed_at: now.to_rfc3339(),
            price_valid_until: until.to_rfc3339(),
            max_call_micro: 5_000_000,
        };
        config.validate()?;
        agent
            .store()
            .set(FUSION, &serde_json::to_string(&config).expect("config JSON"))?;
    }
    status(agent)
}
pub fn status(agent: &Agent) -> Result<Value> {
    let profile = profile(agent)?;
    let provider = profile
        .as_ref()
        .and_then(|p| p["provider"].as_str())
        .map(String::from);
    let key_present = provider
        .as_ref()
        .is_some_and(|p| credman::exists(&target(agent, p)));
    let settings = if agent.settings_path().exists() {
        Settings::load(agent.settings_path())?
    } else {
        Settings::default()
    };
    let model_installed = settings
        .models
        .iter()
        .any(|m| m.id == market_research::MODEL_ID);
    let budget = settings.budget.as_ref().map(|b| {
        json!({
            "currency": b.currency,
            "timezone": b.timezone,
            "daily_limit_micro": b.daily_limit_micro,
            "monthly_limit_micro": b.monthly_limit_micro,
        })
    });
    Ok(json!({
        "provider": provider,
        "configured_at": profile.as_ref().and_then(|p| p["configured_at"].as_str()),
        "key_present": key_present,
        "model_installed": model_installed,
        "budget": budget,
        "endpoint": provider.as_deref().map(|p| endpoint(p).unwrap_or("")),
    }))
}

pub fn test(agent: &Agent) -> Result<Value> {
    let profile = profile(agent)?.ok_or("PROVIDER_NOT_CONFIGURED")?;
    let provider = profile["provider"]
        .as_str()
        .ok_or("PROVIDER_PROFILE_INVALID")?;
    let target = profile["target"]
        .as_str()
        .ok_or("PROVIDER_PROFILE_INVALID")?;
    let key = credman::read(target)?;
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .https_only(true)
        .build()
        .map_err(|_| "PROVIDER_CLIENT_UNAVAILABLE")?;
    let url = format!("{}/models", endpoint(provider)?);
    let response = client
        .get(url)
        .bearer_auth(key.as_str())
        .send()
        .map_err(|_| "PROVIDER_UNREACHABLE")?;
    let status = response.status().as_u16();
    match status {
        200 => {
            let body: Value = response.json().map_err(|_| "PROVIDER_RESPONSE_INVALID")?;
            let models = body["data"].as_array().map(Vec::len).unwrap_or(0);
            Ok(json!({"state": "OK", "status": 200, "models": models}))
        }
        401 | 403 => Err("PROVIDER_KEY_REJECTED".into()),
        _ => Err(format!("PROVIDER_HTTP_{status}").into()),
    }
}

pub fn remove(agent: &Agent) -> Result<Value> {
    if let Some(profile) = profile(agent)? {
        let provider = profile["provider"]
            .as_str()
            .ok_or("PROVIDER_PROFILE_INVALID")?;
        credman::delete(&target(agent, provider))?;
    }
    let c = agent.store().connect()?;
    c.execute("DELETE FROM meta WHERE key=?1", [PROFILE])?;
    c.execute("DELETE FROM meta WHERE key=?1", [FUSION])?;
    status(agent)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_official_endpoints_are_accepted() {
        assert_eq!(endpoint(DEEPSEEK).unwrap(), "https://api.deepseek.com");
        assert_eq!(endpoint(OPENAI).unwrap(), "https://api.openai.com/v1");
        assert_eq!(endpoint("http://127.0.0.1:9").unwrap_err().0, "PROVIDER_UNSUPPORTED");
    }

    #[test]
    fn key_shape_is_enforced_before_any_write() {
        assert!(valid_key("sk-0123456789abcdefghijkl"));
        assert!(!valid_key("pk-0123456789abcdefghijkl"));
        assert!(!valid_key("sk-short"));
        assert!(!valid_key("sk-0123456789abcdefghijkl "));
        assert!(!valid_key("sk-0123456789abcdefghijkl/.."));
    }
}
