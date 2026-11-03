//! Owner-only, one-shot DeepSeek control. All costs remain in the original Store.
use crate::{
    config::{Budget, Grant, Model, Price, Settings},
    ensure, hash, risk_binding, structured as s, Agent, InputSummary, Result,
};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Stdio},
};
use zeroize::Zeroizing;

pub const ID: &str = "ds4.1flash";
pub const MODEL: &str = "deepseek-flash";
pub const ENDPOINT: &str = "https://api.deepseek.com/chat/completions";
pub const KEY_ENV: &str = "STRATIDE_RESEARCH_KEY_DEEPSEEK";
pub const PRICE_SOURCE: &str = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/";
pub const PRICE_VERSION: &str = "deepseek-cny-20261103-peak-v1";
const CONFIG: &str = "structured_deepseek_config_v1";
const PERMIT: &str = "structured_deepseek_once_v1";

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub version: u32,
    pub key_file: PathBuf,
    pub grant_version: String,
    pub synthetic_only: bool,
    pub provider_terms_reviewed: bool,
    pub authorized_at: String,
    pub price_reviewed_at: String,
    pub price_valid_until: String,
    pub max_call_micro: i64,
}
impl Config {
    fn validate(&self) -> Result<()> {
        let now = Utc::now();
        let reviewed = DateTime::parse_from_rfc3339(&self.price_reviewed_at)
            .map_err(|_| "DEEPSEEK_PRICE_REVIEW_REQUIRED")?;
        let until = DateTime::parse_from_rfc3339(&self.price_valid_until)
            .map_err(|_| "DEEPSEEK_PRICE_REVIEW_REQUIRED")?;
        ensure(
            self.version == 1
                && self.synthetic_only
                && self.provider_terms_reviewed
                && self.grant_version == "deepseek-synthetic-grant-v1"
                && DateTime::parse_from_rfc3339(&self.authorized_at).is_ok_and(|at| at <= now)
                && self.key_file.is_absolute(),
            "DEEPSEEK_OWNER_AUTHORIZATION_REQUIRED",
        )?;
        ensure(
            reviewed <= now
                && until > now
                && until > reviewed
                && (until - reviewed).num_seconds() <= 7 * 86400,
            "DEEPSEEK_PRICE_EXPIRED_REFRESH_FROZEN_CONFIG",
        )?;
        ensure(
            (98_304..=1_000_000_000_000).contains(&self.max_call_micro),
            "DEEPSEEK_CALL_CAP_TOO_SMALL",
        )
    }
    pub fn model(&self) -> Model {
        let mut m = s::recorded_model();
        m.id = ID.into();
        m.label = "DeepSeek V4.1 Flash".into();
        m.model = MODEL.into();
        m.endpoint = Some(ENDPOINT.into());
        m.api_key_env = Some(KEY_ENV.into());
        m.max_input_tokens = 32768;
        m.max_output_tokens = 4096;
        m.timeout_seconds = 60;
        m.price = Some(Price {
            version: PRICE_VERSION.into(),
            source: PRICE_SOURCE.into(),
            currency: "CNY".into(),
            input_micro_per_million: 2_000_000,
            output_micro_per_million: 8_000_000,
            bounded_text_billing_verified: true,
        });
        m.grant = Some(Grant {
            receiver: ENDPOINT.into(),
            purpose: s::SCOPE.into(),
            scopes: vec![s::SCOPE.into()],
            authorized_at: self.authorized_at.clone(),
            revoked: false,
        });
        let c = m.cloud.as_mut().unwrap();
        c.transport = "https".into();
        c.model_version = "DeepSeek-V4.1-Flash-1017_ALIAS_MUTABLE".into();
        c.billing_bound_source = PRICE_SOURCE.into();
        c.billing_bound_version = PRICE_VERSION.into();
        c.max_call_micro = self.max_call_micro;
        m
    }
}
pub fn is_model(m: &Model) -> bool {
    s::is_model(m) && m.cloud.as_ref().is_some_and(|c| c.transport == "https")
}
pub fn validate_model(m: &Model) -> Result<()> {
    ensure(
        m.id == ID
            && m.model == MODEL
            && m.endpoint.as_deref() == Some(ENDPOINT)
            && m.api_key_env.as_deref() == Some(KEY_ENV),
        "DEEPSEEK_FIXED_MODEL_ENDPOINT_REQUIRED",
    )?;
    ensure(
        m.max_input_tokens == 32768 && m.max_output_tokens == 4096 && m.timeout_seconds <= 60,
        "DEEPSEEK_TOKEN_TIMEOUT_POLICY",
    )
}
pub fn authorize(m: &Model, b: &Budget) -> Result<()> {
    validate_model(m)?;
    let p = m.price.as_ref().ok_or("PRICE_UNCONFIGURED")?;
    let c = m.cloud.as_ref().unwrap();
    ensure(
        b.currency == "CNY"
            && p.currency == "CNY"
            && p.source == PRICE_SOURCE
            && p.version == PRICE_VERSION
            && p.input_micro_per_million == 2_000_000
            && p.output_micro_per_million == 8_000_000
            && c.billing_bound_source == PRICE_SOURCE
            && c.billing_bound_version == PRICE_VERSION,
        "DEEPSEEK_CURRENT_CNY_PEAK_PRICE_REQUIRED",
    )
}
fn get<T: serde::de::DeserializeOwned>(c: &Connection, key: &str) -> Result<T> {
    let raw: Option<String> = c
        .query_row("SELECT value FROM meta WHERE key=?1", [key], |r| r.get(0))
        .optional()?;
    serde_json::from_str(&raw.ok_or("REAL_PROVIDER_NOT_RUN_OWNER_AUTHORIZATION_MISSING")?)
        .map_err(|_| "DEEPSEEK_LOCAL_CONFIG_INVALID".into())
}
fn set(c: &Connection, key: &str, value: &impl Serialize) -> Result<()> {
    c.execute("INSERT INTO meta(key,value) VALUES(?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![key, serde_json::to_string(value).map_err(|_| "DEEPSEEK_LOCAL_CONFIG_INVALID")?])?;
    Ok(())
}
fn connection(b: &risk_binding::Binding, write: bool) -> Result<Connection> {
    let c = Connection::open_with_flags(
        b.agent_dir.join("agent.sqlite"),
        if write {
            OpenFlags::SQLITE_OPEN_READ_WRITE
        } else {
            OpenFlags::SQLITE_OPEN_READ_ONLY
        },
    )?;
    b.verify(&c)?;
    Ok(c)
}
fn settings_config(c: &Connection, settings: &Settings) -> Result<(Config, Model)> {
    let cfg: Config = get(c, CONFIG)?;
    cfg.validate()?;
    let model = settings
        .models
        .iter()
        .find(|m| m.id == ID)
        .ok_or("DEEPSEEK_MODEL_NOT_CONFIGURED")?;
    model.authorize(&[s::SCOPE.into()], settings.budget.as_ref())?;
    ensure(
        model.fingerprint() == cfg.model().fingerprint(),
        "DEEPSEEK_FROZEN_MODEL_CHANGED",
    )?;
    let b = settings.budget.as_ref().ok_or("BUDGET_UNCONFIGURED")?;
    let identity: String = c.query_row(
        "SELECT value FROM meta WHERE key='budget_identity'",
        [],
        |r| r.get(0),
    )?;
    ensure(
        identity == format!("CNY|{}", b.timezone),
        "EXISTING_REAL_CNY_OWNER_BUDGET_REQUIRED",
    )?;
    Ok((cfg, model.clone()))
}
pub fn check_configuration(root: &Path) -> Result<()> {
    let b = risk_binding::read_at(root)?;
    let c = connection(&b, false)?;
    let (cfg, _) = settings_config(&c, &Settings::load(&b.settings_path)?)?;
    key_metadata(&cfg.key_file)
}

// This exact projection is independent of datasets, dates, statistics and feedback.
pub fn safe_request(source: Value) -> Value {
    json!({"response_source":source,
        "research_boundary":{"mode":"SYNTHETIC_ONLY_NO_MARKET_DATA","max_positions":50,"candidate_limit":4},
        "development_summary":{"mode":"synthetic_test","observed_sessions":0,"feedback":null},
        "grammar":s::grammar(),"output_contract":s::output_contract()})
}
pub fn validate_request(ctx: &s::Context, plan: &Value, v: &Value) -> Result<()> {
    ensure(
        ctx.round == 1
            && plan["cloud"]["mode"] == "authorized_cloud"
            && plan["limits"]["rounds"] == 1
            && plan["limits"]["candidates"] == 4
            && plan["cloud"]["parser_sha"]
                .as_str()
                .is_some_and(crate::risk_portfolio::valid_sha),
        "DEEPSEEK_ONE_SYNTHETIC_ROUND_ONLY",
    )?;
    ensure(
        v == &safe_request(
            json!({"kind":"rust_agent_structured_v1","task_ref":ctx.trigger(),"plan_sha":ctx.plan_sha,
        "round":1,"producer_sha":s::adapter_sha(),"model_sha":ctx.model_sha,"prompt_sha":s::prompt_sha(),
        "parser_sha":plan["cloud"]["parser_sha"]}),
        ),
        "DEEPSEEK_SYNTHETIC_FIELDS_ONLY",
    )
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Permit {
    enabled: bool,
    plan_sha: String,
    request_sha: String,
    model_sha: String,
    config_sha: String,
}
pub fn gate(c: &Connection, settings: &Settings, ctx: &s::Context) -> Result<Config> {
    let (cfg, model) = settings_config(c, settings)?;
    let p: Permit = get(c, PERMIT)?;
    ensure(
        p.enabled
            && p.plan_sha == ctx.plan_sha
            && p.request_sha == ctx.request_sha
            && p.model_sha == ctx.model_sha
            && p.config_sha == hash(&serde_json::to_vec(&cfg).unwrap()),
        "DEEPSEEK_DISABLED_OR_ONCE_CONSUMED",
    )?;
    let budget = settings.budget.as_ref().ok_or("BUDGET_UNCONFIGURED")?;
    crate::budget::check_dispatch(c, budget, Utc::now())?;
    let view = crate::budget::view(c, Some(budget), Utc::now())?;
    let own_reserved:i64=c.query_row("SELECT COALESCE(SUM(c.maximum_micro),0) FROM calls c JOIN tasks t ON t.id=c.task_id WHERE t.trigger_key=?1 AND c.state='reserved'",[ctx.trigger()],|r|r.get(0))?;
    let maximum = model.cost(model.max_input_tokens, model.max_output_tokens)?;
    for k in ["daily_remaining_micro", "monthly_remaining_micro"] {
        ensure(
            view[k]
                .as_str()
                .and_then(|s| s.parse::<i64>().ok())
                .is_some_and(|remaining| remaining + own_reserved >= maximum),
            "DEEPSEEK_BUDGET_EXHAUSTED",
        )?;
    }
    Ok(cfg)
}
pub fn consume(c: &Connection) -> Result<()> {
    let mut p: Permit = get(c, PERMIT)?;
    ensure(p.enabled, "DEEPSEEK_DISABLED_OR_ONCE_CONSUMED")?;
    p.enabled = false;
    set(c, PERMIT, &p)
}
pub fn key_metadata(path: &Path) -> Result<()> {
    crate::eod_snapshot::no_links(path).map_err(|_| "DEEPSEEK_KEY_SOURCE_UNSAFE")?;
    ensure(
        fs::metadata(path).is_ok_and(|m| m.is_file() && m.len() > 0 && m.len() <= 8192),
        "DEEPSEEK_KEY_SOURCE_MISSING_OR_SIZE",
    )?;
    let parent = path.parent().ok_or("DEEPSEEK_KEY_SOURCE_UNSAFE")?;
    let git = |args: &[&str]| {
        Command::new("git")
            .arg("-C")
            .arg(parent)
            .args(args)
            .stdin(Stdio::null())
            .stderr(Stdio::null())
            .output()
    };
    if git(&["rev-parse", "--is-inside-work-tree"])
        .map_err(|_| "DEEPSEEK_GIT_CHECK_UNAVAILABLE")?
        .status
        .success()
    {
        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("DEEPSEEK_KEY_SOURCE_UNSAFE")?;
        let tracked = git(&["ls-files", "--error-unmatch", "--", name])
            .map_err(|_| "DEEPSEEK_GIT_CHECK_UNAVAILABLE")?;
        ensure(
            !tracked.status.success(),
            "DEEPSEEK_KEY_FILE_TRACKED_REMOVE_FROM_GIT_WITH_OWNER",
        )?;
        ensure(
            git(&["check-ignore", "--quiet", "--", name])
                .map_err(|_| "DEEPSEEK_GIT_CHECK_UNAVAILABLE")?
                .status
                .success(),
            "DEEPSEEK_KEY_FILE_MUST_BE_IGNORED",
        )?;
    }
    Ok(())
}
// Accept one bare key, one key in a Markdown fence, or one `API Key: sk-...` line.
// Anything else (including multiple keys or other credential text) is rejected.
pub(crate) fn parse_key(raw: &str) -> Result<Zeroizing<String>> {
    let mut found = None;
    for line in raw
        .trim_start_matches('\u{feff}')
        .lines()
        .map(str::trim)
        .filter(|s| !s.is_empty())
    {
        if matches!(
            line,
            "# DeepSeek API Key" | "# DeepSeek" | "# API Key" | "# Synthetic test credential"
        ) {
            continue;
        }
        if matches!(line, "```" | "```text" | "```markdown") {
            continue;
        }
        let candidate = line
            .strip_prefix("API Key:")
            .or_else(|| line.strip_prefix("api_key:"))
            .unwrap_or(line)
            .trim()
            .trim_matches('`');
        ensure(
            found.is_none()
                && candidate.starts_with("sk-")
                && (24..=256).contains(&candidate.len())
                && candidate
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
                && !["placeholder", "your_key", "example", "replace"]
                    .iter()
                    .any(|s| candidate.to_ascii_lowercase().contains(s)),
            "DEEPSEEK_KEY_FILE_REQUIRES_EXACTLY_ONE_KEY",
        )?;
        found = Some(Zeroizing::new(candidate.to_string()));
    }
    found.ok_or("DEEPSEEK_KEY_FILE_REQUIRES_EXACTLY_ONE_KEY".into())
}
pub(crate) fn read_key(cfg: &Config) -> Result<Zeroizing<String>> {
    key_metadata(&cfg.key_file)?;
    let bytes = Zeroizing::new(fs::read(&cfg.key_file).map_err(|_| "DEEPSEEK_KEY_READ_FAILED")?);
    let raw = std::str::from_utf8(&bytes).map_err(|_| "DEEPSEEK_KEY_FILE_INVALID")?;
    parse_key(raw)
}
pub fn configure(root: &Path, config_path: &Path) -> Result<Value> {
    let b = risk_binding::read_at(root)?;
    let mut settings = Settings::load(&b.settings_path)?;
    let c = connection(&b, false)?;
    let budget = settings
        .budget
        .as_ref()
        .ok_or("EXISTING_REAL_CNY_OWNER_BUDGET_REQUIRED")?;
    ensure(
        budget.currency == "CNY",
        "EXISTING_REAL_CNY_OWNER_BUDGET_REQUIRED",
    )?;
    let identity: String = c.query_row(
        "SELECT value FROM meta WHERE key='budget_identity'",
        [],
        |r| r.get(0),
    )?;
    ensure(
        identity == format!("CNY|{}", budget.timezone),
        "EXISTING_REAL_CNY_OWNER_BUDGET_REQUIRED",
    )?;
    let cfg: Config = serde_json::from_value(crate::risk_portfolio::read(config_path, 8192)?)
        .map_err(|_| "DEEPSEEK_LOCAL_CONFIG_INVALID")?;
    cfg.validate()?;
    key_metadata(&cfg.key_file)?; // Metadata only: never read the key during configuration.
    let model = cfg.model();
    if let Some(old) = settings.models.iter_mut().find(|m| m.id == ID) {
        ensure(is_model(old), "DEEPSEEK_MODEL_ID_CONFLICT")?;
        *old = model;
    } else {
        settings.models.push(model);
    }
    settings.validate()?;
    let a = Agent::open(&b.agent_dir, Some(&b.settings_path), blank())?;
    let temp = b.settings_path.with_extension("json.deepseek-pending");
    crate::eod_snapshot::no_links(&temp)?;
    use std::io::Write;
    let mut f = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temp)
        .map_err(|_| "DEEPSEEK_CONFIG_WRITE")?;
    f.write_all(&serde_json::to_vec_pretty(&settings).unwrap())
        .map_err(|_| "DEEPSEEK_CONFIG_WRITE")?;
    f.sync_all().map_err(|_| "DEEPSEEK_CONFIG_WRITE")?;
    drop(f);
    fs::rename(temp, &b.settings_path).map_err(|_| "DEEPSEEK_CONFIG_WRITE")?;
    set(&a.store().connect()?, CONFIG, &cfg)?;
    set(
        &a.store().connect()?,
        PERMIT,
        &Permit {
            enabled: false,
            plan_sha: "0".repeat(64),
            request_sha: "0".repeat(64),
            model_sha: "0".repeat(64),
            config_sha: "0".repeat(64),
        },
    )?;
    Ok(
        json!({"state":"CONFIGURED_OFF","model_id":ID,"model":MODEL,"key_content_read":false,"paper_allowed":false,"live_allowed":false}),
    )
}
fn blank() -> InputSummary {
    InputSummary {
        version: "no-input".into(),
        source_day: String::new(),
        mode: "no_input".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    }
}
pub fn preflight(root: &Path) -> Result<Value> {
    let b = risk_binding::read_at(root)?;
    let settings = Settings::load(&b.settings_path)?;
    let c = connection(&b, false)?;
    let (cfg, model) = settings_config(&c, &settings)?;
    let paused: String = c.query_row("SELECT value FROM meta WHERE key='paused'", [], |r| {
        r.get(0)
    })?;
    let control = crate::risk_portfolio::read(&root.join("control/state.json"), 4096)?;
    ensure(
        paused != "true" && control["paused"] == false,
        "STRUCTURED_OWNER_PAUSED",
    )?;
    ensure(control["cancelled"] == false, "STRUCTURED_OWNER_CANCELLED")?;
    key_metadata(&cfg.key_file)?;
    let ctx: s::Context = serde_json::from_value(crate::risk_portfolio::read(
        &root.join("cloud/round-01/context.json"),
        8192,
    )?)
    .map_err(|_| "DEEPSEEK_REQUEST_NOT_PREPARED")?;
    ensure(ctx.experiment == root, "STRUCTURED_CONTEXT_INVALID")?;
    s::validate_request(&ctx, &model)?;
    let budget = crate::budget::view(&c, settings.budget.as_ref(), Utc::now())?;
    let maximum = model.cost(model.max_input_tokens, model.max_output_tokens)?;
    for k in ["daily_remaining_micro", "monthly_remaining_micro"] {
        ensure(
            budget[k]
                .as_str()
                .and_then(|s| s.parse::<i64>().ok())
                .is_some_and(|n| n >= maximum),
            "DEEPSEEK_BUDGET_EXHAUSTED",
        )?;
    }
    let p: Option<Permit> = get(&c, PERMIT).ok();
    Ok(
        json!({"state":"PREFLIGHT_READY_REQUIRES_EXPLICIT_ENABLE_ONCE","enabled":p.is_some_and(|p|p.enabled),
        "model_id":ID,"model":MODEL,"receiver":ENDPOINT,"purpose":s::SCOPE,"grant_version":cfg.grant_version,
        "price_version":PRICE_VERSION,"price_valid_until":cfg.price_valid_until,"maximum_micro":maximum,
        "currency":"CNY","budget":budget,"request_sha":ctx.request_sha,"model_sha":ctx.model_sha,
        "fields":s::FIELDS,"payload":"fixed synthetic boundary + zero observations + public AST grammar + opaque source IDs",
        "credential":"present_untracked_ignored_or_outside_git_CONTENT_UNREAD","network_calls":0,
        "verification":"REAL_PROVIDER_NOT_VERIFIED","paper_allowed":false,"live_allowed":false}),
    )
}
pub fn enable(root: &Path, opt_in: &str) -> Result<Value> {
    ensure(
        opt_in == "APPROVE_ONE_SYNTHETIC_DEEPSEEK_REQUEST",
        "DEEPSEEK_EXPLICIT_ONCE_OPT_IN_REQUIRED",
    )?;
    let view = preflight(root)?;
    let b = risk_binding::read_at(root)?;
    let a = Agent::open(&b.agent_dir, Some(&b.settings_path), blank())?;
    let c = a.store().connect()?;
    let (cfg, _) = settings_config(&c, &Settings::load(&b.settings_path)?)?;
    let p = Permit {
        enabled: true,
        plan_sha: crate::risk_portfolio::read(&root.join("cloud/round-01/context.json"), 8192)?
            ["plan_sha"]
            .as_str()
            .ok_or("STRUCTURED_CONTEXT_INVALID")?
            .into(),
        request_sha: view["request_sha"].as_str().unwrap().into(),
        model_sha: view["model_sha"].as_str().unwrap().into(),
        config_sha: hash(&serde_json::to_vec(&cfg).unwrap()),
    };
    set(&c, PERMIT, &p)?;
    Ok(
        json!({"state":"ONE_SYNTHETIC_REQUEST_ENABLED","request_sha":p.request_sha,"automatic_research":false,"key_content_read":false}),
    )
}
pub fn disable(root: &Path) -> Result<Value> {
    let b = risk_binding::read_at(root)?;
    let c = connection(&b, true)?;
    // An IMMEDIATE write serializes with the original final-dispatch transaction.
    c.execute_batch("BEGIN IMMEDIATE")?;
    if let Ok(mut p) = get::<Permit>(&c, PERMIT) {
        p.enabled = false;
        set(&c, PERMIT, &p)?;
    }
    c.execute_batch("COMMIT")?;
    Ok(
        json!({"state":"OFF","unknown_reservations":"PRESERVED","in_flight_request":"MAY_HAVE_BEEN_SENT","paper_allowed":false,"live_allowed":false}),
    )
}
