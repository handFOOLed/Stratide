//! One explicit Owner action that connects a cloud research provider.
//!
//! Only the official DeepSeek and OpenAI endpoints are accepted. The API key is
//! stored in Windows Credential Manager and never echoed back. DeepSeek also
//! receives the frozen provider configuration the market-research pipeline reads;
//! OpenAI is stored and connectivity-tested but is not wired into the market
//! pipeline, whose fusion contract pins the DeepSeek model.
use crate::{config::Settings, credman, deepseek, ensure, hash, market_research, Agent, Result};
use chrono::{DateTime, Duration, Utc};
use rusqlite::{params, Connection, TransactionBehavior};
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

fn mask(key: &str) -> String {
    format!(
        "{}••••{}",
        &key[..3],
        &key[key.len() - 4..]
    )
}

pub fn target(agent: &Agent, provider: &str) -> String {
    let digest = hash(agent.settings_path().to_string_lossy().as_bytes());
    format!("Stratide/{digest}/research-{provider}-v1")
}

fn set(c: &Connection, key: &str, value: &impl serde::Serialize) -> Result<()> {
    c.execute(
        "INSERT INTO meta(key,value) VALUES(?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![key, serde_json::to_string(value).expect("provider configuration JSON")],
    )?;
    Ok(())
}

pub(crate) fn market_config(c: &Connection) -> Result<Option<deepseek::Config>> {
    market_research::get(c, FUSION)
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
    let mut c = agent.store().connect()?;
    let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let now = Utc::now();
    // A masked fingerprint is enough to recognise the saved key later; the
    // secret itself is never returned to the page.
    let key_hint = mask(key);
    let record = json!({
        "provider": provider,
        "target": target,
        "configured_at": now.to_rfc3339(),
        "key_hint": key_hint,
    });
    if provider == DEEPSEEK {
        let config = market_config(&tx)?
            .filter(|config| config.credential_target.as_deref() == Some(target.as_str()))
            .unwrap_or_else(|| deepseek::Config {
            version: 1,
            key_file: agent.settings_path().with_file_name("credential-deepseek.md"),
            credential_target: Some(target.clone()),
            grant_version: "deepseek-synthetic-grant-v1".into(),
            synthetic_only: true,
            provider_terms_reviewed: true,
            authorized_at: now.to_rfc3339(),
            price_reviewed_at: String::new(),
            price_valid_until: String::new(),
            max_call_micro: 5_000_000,
        });
        set(&tx, FUSION, &config)?;
    }
    set(&tx, PROFILE, &record)?;
    credman::write(&target, &format!("Stratide {}", label(provider)), key)?;
    tx.commit()?;
    status(agent)
}
pub fn status(agent: &Agent) -> Result<Value> {
    let c = agent.store().connect()?;
    let profile: Option<Value> = market_research::get(&c, PROFILE)?;
    let fusion = market_config(&c)?;
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
    let research_key_present = fusion.as_ref().is_some_and(|cfg| match &cfg.credential_target {
        Some(target) => credman::exists(target),
        None => cfg.key_file.is_file(),
    });
    let price = fusion.as_ref().map(|cfg| {
        let state = match cfg.validate_price_at(Utc::now()) {
            Ok(()) => "VALID",
            Err(error) if error.0 == "DEEPSEEK_PRICE_REVIEW_REQUIRED" => "REVIEW_REQUIRED",
            Err(_) => "EXPIRED",
        };
        json!({
            "state": state,
            "valid_until": DateTime::parse_from_rfc3339(&cfg.price_valid_until).ok().map(|at| at.to_rfc3339()),
            "reviewable": research_key_present && cfg.credential_target.as_deref() == Some(target(agent, DEEPSEEK).as_str()),
            "version": deepseek::PRICE_VERSION,
            "source": deepseek::PRICE_SOURCE,
            "input_micro_per_million": deepseek::INPUT_MICRO_PER_MILLION.to_string(),
            "output_micro_per_million": deepseek::OUTPUT_MICRO_PER_MILLION.to_string(),
        })
    });
    Ok(json!({
        "provider": provider,
        "configured_at": profile.as_ref().and_then(|p| p["configured_at"].as_str()),
        "key_hint": profile.as_ref().and_then(|value| value["key_hint"].as_str()),
        "key_present": key_present,
        "model_installed": model_installed,
        "research_provider": model_installed.then_some(DEEPSEEK),
        "research_key_present": research_key_present,
        "research_price": price,
        "budget": budget,
        "endpoint": provider.as_deref().map(|p| endpoint(p).unwrap_or("")),
    }))
}

pub fn test(agent: &Agent, expected: Option<&str>) -> Result<Value> {
    let profile: Value = market_research::get(&agent.store().connect()?, PROFILE)?
        .ok_or("PROVIDER_NOT_CONFIGURED")?;
    let provider = profile["provider"]
        .as_str()
        .ok_or("PROVIDER_PROFILE_INVALID")?;
    ensure(expected.is_none_or(|value| value == provider), "PROVIDER_SELECTION_CHANGED")?;
    let url = format!("{}/models", endpoint(provider)?);
    let target = target(agent, provider);
    ensure(profile["target"] == target, "PROVIDER_PROFILE_INVALID")?;
    let key = credman::read(&target)?;
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .https_only(true)
        .build()
        .map_err(|_| "PROVIDER_CLIENT_UNAVAILABLE")?;
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
            Ok(json!({"state": "OK", "provider": provider, "status": 200, "models": models}))
        }
        401 | 403 => Err("PROVIDER_KEY_REJECTED".into()),
        _ => Err(format!("PROVIDER_HTTP_{status}").into()),
    }
}

fn apply_price_review(config: &mut deepseek::Config, body: &Value, now: DateTime<Utc>) -> Result<()> {
    ensure(
        body == &json!({"confirmed": true, "price_version": deepseek::PRICE_VERSION}),
        "DEEPSEEK_PRICE_REVIEW_REQUIRED",
    )?;
    config.price_reviewed_at = now.to_rfc3339();
    config.price_valid_until = (now + Duration::days(7)).to_rfc3339();
    config.validate_price_at(now)
}

pub fn review_price(agent: &Agent, body: &Value) -> Result<Value> {
    let mut c = agent.store().connect()?;
    let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let mut config = market_config(&tx)?.ok_or("MARKET_PROVIDER_CONFIGURATION_REQUIRED")?;
    let target = target(agent, DEEPSEEK);
    ensure(
        config.credential_target.as_deref() == Some(target.as_str()) && credman::exists(&target),
        "MARKET_PROVIDER_CONFIGURATION_REQUIRED",
    )?;
    apply_price_review(&mut config, body, Utc::now())?;
    config.validate()?;
    set(&tx, FUSION, &config)?;
    tx.commit()?;
    status(agent)
}

pub fn remove(agent: &Agent) -> Result<Value> {
    let mut c = agent.store().connect()?;
    let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
    if let Some(profile) = market_research::get::<Value>(&tx, PROFILE)? {
        let provider = profile["provider"]
            .as_str()
            .ok_or("PROVIDER_PROFILE_INVALID")?;
        endpoint(provider)?;
        tx.execute("DELETE FROM meta WHERE key=?1", [PROFILE])?;
        if provider == DEEPSEEK {
            tx.execute("DELETE FROM meta WHERE key=?1", [FUSION])?;
        }
        credman::delete(&target(agent, provider))?;
    }
    tx.commit()?;
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

    #[test]
    fn price_review_requires_explicit_confirmation_of_the_current_bound() {
        let now = Utc::now();
        let mut config = deepseek::Config {
            version: 1,
            key_file: tempfile::tempdir().unwrap().path().join("fixture-key"),
            credential_target: None,
            grant_version: "deepseek-synthetic-grant-v1".into(),
            synthetic_only: true,
            provider_terms_reviewed: true,
            authorized_at: (now - Duration::days(8)).to_rfc3339(),
            price_reviewed_at: (now - Duration::days(8)).to_rfc3339(),
            price_valid_until: (now - Duration::days(1)).to_rfc3339(),
            max_call_micro: 5_000_000,
        };
        let before = serde_json::to_value(&config).unwrap();
        assert_eq!(config.validate().unwrap_err().0, "DEEPSEEK_PRICE_EXPIRED_REFRESH_FROZEN_CONFIG");
        for body in [json!({}), json!({"confirmed":true, "price_version":"old"})] {
            assert!(apply_price_review(&mut config, &body, now).is_err());
            assert_eq!(serde_json::to_value(&config).unwrap(), before);
        }
        let pinned_model = config.model().fingerprint();
        apply_price_review(&mut config, &json!({"confirmed":true,"price_version":deepseek::PRICE_VERSION}), now).unwrap();
        assert_eq!(config.model().fingerprint(), pinned_model);
        config.validate().unwrap();
        assert!(config.validate_price_at(now + Duration::days(7)).is_err());
    }
}
