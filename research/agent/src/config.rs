use crate::{ensure, hash, Result};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, fs, path::Path};

pub const PURPOSE: &str = "paper_research_v1";
pub const SCOPES: [&str; 3] = ["owner_task", "paper_summary_v1", "historical_summary_v1"];

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    pub version: u32,
    pub budget: Option<Budget>,
    pub models: Vec<Model>,
    pub default_model: Option<String>,
    pub backup_model: Option<String>,
    pub max_tasks: usize,
    pub max_storage_mb: u64,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Budget {
    pub currency: String,
    pub timezone: String,
    pub daily_limit_micro: i64,
    pub monthly_limit_micro: i64,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Price {
    pub version: String,
    pub source: String,
    pub currency: String,
    pub input_micro_per_million: i64,
    pub output_micro_per_million: i64,
    // Owner attests this text protocol has no other billable tools/minimum fees.
    pub bounded_text_billing_verified: bool,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Grant {
    pub receiver: String,
    pub purpose: String,
    pub scopes: Vec<String>,
    pub authorized_at: String,
    pub revoked: bool,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Model {
    pub id: String,
    pub label: String,
    pub kind: String,
    pub model: String,
    pub endpoint: Option<String>,
    pub api_key_env: Option<String>,
    pub max_input_tokens: u32,
    pub max_output_tokens: u32,
    pub timeout_seconds: u64,
    pub price: Option<Price>,
    pub grant: Option<Grant>,
    pub fake_scenario: Option<String>,
}
impl Default for Settings {
    fn default() -> Self {
        Self {
            version: 1,
            budget: None,
            models: vec![],
            default_model: None,
            backup_model: None,
            max_tasks: 1000,
            max_storage_mb: 64,
        }
    }
}
impl Settings {
    pub fn load(path: &Path) -> Result<Self> {
        let meta = fs::symlink_metadata(path).map_err(|_| "CONFIG_UNREADABLE")?;
        ensure(meta.is_file() && meta.len() <= 128 * 1024, "CONFIG_INVALID")?;
        let settings: Self =
            serde_json::from_slice(&fs::read(path).map_err(|_| "CONFIG_UNREADABLE")?)
                .map_err(|_| "CONFIG_INVALID")?;
        settings.validate()?;
        Ok(settings)
    }
    pub fn validate(&self) -> Result<()> {
        ensure(
            self.version == 1
                && self.max_tasks > 0
                && self.max_tasks <= 10_000
                && (8..=256).contains(&self.max_storage_mb)
                && self.models.len() <= 16,
            "CONFIG_INVALID",
        )?;
        if let Some(b) = &self.budget {
            ensure(
                b.currency.len() == 3
                    && b.currency.bytes().all(|c| c.is_ascii_uppercase())
                    && b.timezone.parse::<chrono_tz::Tz>().is_ok()
                    && (1..=1_000_000_000_000).contains(&b.daily_limit_micro)
                    && (1..=1_000_000_000_000).contains(&b.monthly_limit_micro),
                "BUDGET_CONFIG_INVALID",
            )?;
        }
        let mut ids = BTreeSet::new();
        for m in &self.models {
            ensure(
                !m.id.is_empty()
                    && m.id.len() <= 48
                    && m.id
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
                    && ids.insert(m.id.as_str())
                    && m.label.len() <= 120
                    && !m.label.is_empty()
                    && !m.model.is_empty()
                    && m.model.len() <= 128
                    && (1024..=131_072).contains(&m.max_input_tokens)
                    && (64..=8192).contains(&m.max_output_tokens)
                    && (1..=60).contains(&m.timeout_seconds),
                "MODEL_CONFIG_INVALID",
            )?;
            match m.kind.as_str() {
                "fake" => ensure(
                    m.endpoint.is_none()
                        && m.api_key_env.is_none()
                        && matches!(
                            m.fake_scenario.as_deref(),
                            Some(
                                "success"
                                    | "safe_transient"
                                    | "timeout"
                                    | "slow"
                                    | "malicious"
                                    | "permanent"
                            )
                        ),
                    "FAKE_CONFIG_INVALID",
                )?,
                "chat_completions_v1" => {
                    crate::provider::endpoint(m.endpoint.as_deref().ok_or("ENDPOINT_REQUIRED")?)?;
                    let key = m.api_key_env.as_deref().ok_or("KEY_ENV_REQUIRED")?;
                    ensure(
                        key.starts_with("STRATIDE_RESEARCH_KEY_")
                            && key.len() <= 100
                            && key
                                .bytes()
                                .all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == b'_')
                            && m.fake_scenario.is_none(),
                        "KEY_ENV_INVALID",
                    )?;
                }
                _ => return Err("PROVIDER_UNSUPPORTED".into()),
            }
        }
        for id in [&self.default_model, &self.backup_model]
            .into_iter()
            .flatten()
        {
            ensure(ids.contains(id.as_str()), "MODEL_SELECTION_INVALID")?;
        }
        Ok(())
    }
    pub fn fake() -> Self {
        let mut result = Self {
            budget: Some(Budget {
                currency: "TST".into(),
                timezone: "Asia/Shanghai".into(),
                daily_limit_micro: 1_000_000,
                monthly_limit_micro: 10_000_000,
            }),
            default_model: Some("fake".into()),
            ..Self::default()
        };
        for (id, scenario) in [
            ("fake", "success"),
            ("fake-safe-retry", "safe_transient"),
            ("fake-unknown", "timeout"),
            ("fake-slow", "slow"),
            ("fake-text", "malicious"),
        ] {
            result.models.push(Model {
                id: id.into(),
                label: format!("本地 fake · {scenario}"),
                kind: "fake".into(),
                model: "deterministic-fixture-v1".into(),
                endpoint: None,
                api_key_env: None,
                max_input_tokens: 32768,
                max_output_tokens: 1024,
                timeout_seconds: 30,
                price: Some(Price {
                    version: "synthetic-price-v1".into(),
                    source: "synthetic_test".into(),
                    currency: "TST".into(),
                    input_micro_per_million: 1_000_000,
                    output_micro_per_million: 2_000_000,
                    bounded_text_billing_verified: true,
                }),
                grant: Some(Grant {
                    receiver: "local_fake".into(),
                    purpose: PURPOSE.into(),
                    scopes: SCOPES.map(String::from).to_vec(),
                    authorized_at: "synthetic_test".into(),
                    revoked: false,
                }),
                fake_scenario: Some(scenario.into()),
            });
        }
        result
    }
}
impl Model {
    pub fn fingerprint(&self) -> String {
        hash(&serde_json::to_vec(self).expect("model JSON"))
    }
    pub fn authorize(&self, scopes: &[String], budget: Option<&Budget>) -> Result<()> {
        let b = budget.ok_or("BUDGET_UNCONFIGURED")?;
        let p = self.price.as_ref().ok_or("PRICE_UNCONFIGURED")?;
        ensure(
            p.currency == b.currency
                && !p.version.is_empty()
                && !p.source.is_empty()
                && p.bounded_text_billing_verified
                && (1..=1_000_000_000_000).contains(&p.input_micro_per_million)
                && (1..=1_000_000_000_000).contains(&p.output_micro_per_million),
            "PRICE_UNBOUNDED",
        )?;
        let g = self.grant.as_ref().ok_or("AUTHORIZATION_REQUIRED")?;
        let receiver = self.endpoint.as_deref().unwrap_or("local_fake");
        ensure(
            !g.revoked
                && !g.authorized_at.is_empty()
                && g.receiver == receiver
                && g.purpose == PURPOSE
                && scopes.iter().all(|s| g.scopes.contains(s)),
            "AUTHORIZATION_REQUIRED",
        )?;
        if self.kind != "fake" {
            ensure(
                std::env::var(self.api_key_env.as_ref().ok_or("KEY_ENV_REQUIRED")?)
                    .is_ok_and(|s| !s.trim().is_empty() && s.len() <= 4096),
                "PROVIDER_KEY_MISSING",
            )?;
        }
        Ok(())
    }
    pub fn cost(&self, input: u32, output: u32) -> Result<i64> {
        let price = self.price.as_ref().ok_or("PRICE_UNCONFIGURED")?;
        let numerator = i128::from(input) * i128::from(price.input_micro_per_million)
            + i128::from(output) * i128::from(price.output_micro_per_million);
        let total = (numerator + 999_999) / 1_000_000;
        ensure(total > 0 && total <= 1_000_000_000_000, "PRICE_UNBOUNDED")?;
        Ok(total as i64)
    }
}
