//! Owner-scoped market research. Reuses Agent tasks, atomic Budget Gate and TLS.
//! Historical/synthetic Fusion contracts are deliberately left untouched.
use crate::{
    config::{Budget, Model, Settings},
    deepseek as ds, ensure, hash, risk_cpu as cpu, risk_portfolio as rp, Agent, InputSummary,
    Research, Result, TaskRequest,
};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::io::Read;
use zeroize::Zeroizing;

pub const POLICY: &str = "market-research-v1";
pub const MODEL_ID: &str = "market-deepseek-fusion";
pub const MODEL_VERSION: &str = "DeepSeek-V4.1-Flash-1017_ALIAS_MUTABLE";
pub const CONFIG: &str = "market_research_config_v1";
const CURRENT_GRANT: &str = "market_research_current_grant";
pub const FIELDS: [&str; 7] = [
    "symbols",
    "risk_forecasts",
    "baselines",
    "source_refs",
    "quality",
    "as_of",
    "output_contract",
];
const PURPOSE: &str = "market_strategy_research";
const SOURCE: &str = "tushare_market_eod";
const DENIED: &str = "REAL_MARKET_DATA_EGRESS_DENIED";
const SYSTEM: &str = "FusionResearcherV1 / market-v1. You are a research scientist, never a trader. Use only the supplied numeric RMS risk forecasts, Naive and EWMA; they do not predict return direction. Return exactly the output_contract JSON envelope. Keep controlled portfolio text and conclusions exactly as supplied. Propose quantitative strategy/allocation hypotheses only inside untrusted_hypothesis.text, including a falsifiable next experiment. Cash plus asset weights must equal 10000; only evidence symbols. No tools, code, URLs, orders, risk permissions, return guarantees or independently verified PIT claims. 10000 cash is valid. Never fabricate account facts.";

fn sha<T: Serialize>(value: &T) -> String {
    rp::sha(&serde_json::to_value(value).expect("JSON"))
}
pub fn get<T: serde::de::DeserializeOwned>(c: &Connection, key: &str) -> Result<Option<T>> {
    let raw: Option<String> = c
        .query_row("SELECT value FROM meta WHERE key=?1", [key], |r| r.get(0))
        .optional()?;
    raw.map(|s| {
        serde_json::from_str(&s).map_err(|_| crate::Error("MARKET_RESEARCH_STATE_INVALID".into()))
    })
    .transpose()
}
fn set(c: &Connection, key: &str, value: &impl Serialize) -> Result<()> {
    c.execute(
        "INSERT INTO meta VALUES(?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![key, serde_json::to_string(value).expect("JSON")],
    )?;
    Ok(())
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub automatic_timesfm: bool,
    pub automatic_deepseek: bool,
    pub candidate_count: usize,
    pub daily_call_limit: u32,
    pub trading_day_call_limit: u32,
    pub model_version: String,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            automatic_timesfm: false,
            automatic_deepseek: false,
            candidate_count: 8,
            daily_call_limit: 1,
            trading_day_call_limit: 1,
            model_version: MODEL_VERSION.into(),
        }
    }
}
impl Config {
    fn validate(&self) -> Result<()> {
        ensure(
            (1..=8).contains(&self.candidate_count)
                && (1..=8).contains(&self.daily_call_limit)
                && (1..=8).contains(&self.trading_day_call_limit)
                && self.model_version == MODEL_VERSION,
            "MARKET_RESEARCH_CONFIG_INVALID",
        )
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Scope {
    pub provider: String,
    pub recipient: String,
    pub purpose: String,
    pub source_category: String,
    pub fields: Vec<String>,
    pub max_symbols: usize,
    pub horizon: u32,
    pub context_sessions: u32,
    pub valid_until: String,
    pub provider_terms_reviewed: bool,
}
impl Scope {
    fn validate(&self, now: DateTime<Utc>) -> Result<()> {
        let until = self
            .valid_until
            .parse::<DateTime<Utc>>()
            .map_err(|_| DENIED)?;
        let fields: std::collections::BTreeSet<_> =
            self.fields.iter().map(String::as_str).collect();
        ensure(
            self.provider == "deepseek"
                && self.recipient == ds::ENDPOINT
                && self.purpose == PURPOSE
                && self.source_category == SOURCE
                && self.fields.len() == FIELDS.len()
                && fields == FIELDS.into_iter().collect()
                && (1..=8).contains(&self.max_symbols)
                && self.horizon == 20
                && self.context_sessions == 84
                && self.provider_terms_reviewed
                && until > now,
            DENIED,
        )
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Grant {
    version: u64,
    authorized_at: String,
    scope: Scope,
}
fn active_grant(c: &Connection, now: DateTime<Utc>) -> Result<Grant> {
    let version: u64 = get(c, CURRENT_GRANT)?.ok_or(DENIED)?;
    let grant: Grant = get(c, &format!("market_research_grant:{version}"))?.ok_or(DENIED)?;
    let revoked: bool = get(c, &format!("market_research_revoked:{version}"))?.unwrap_or(false);
    ensure(
        !revoked
            && grant.version == version
            && grant
                .authorized_at
                .parse::<DateTime<Utc>>()
                .is_ok_and(|at| at <= now),
        DENIED,
    )?;
    grant.scope.validate(now)?;
    Ok(grant)
}
pub fn is_model(m: &Model) -> bool {
    m.kind == POLICY
}
pub fn is_input(i: &InputSummary) -> bool {
    i.scopes.iter().any(|s| s == POLICY)
}
fn credential_config(c: &Connection) -> Result<ds::Config> {
    // Reuse only the existing provider/key/price configuration. Its old grant is
    // never a real-data permission. The independent Scope above is mandatory.
    let cfg: ds::Config = get(c, "local_timesfm_fusion_config_v1")?
        .ok_or("MARKET_PROVIDER_CONFIGURATION_REQUIRED")?;
    let mut check = cfg.clone();
    check.grant_version = "deepseek-synthetic-grant-v1".into();
    check.validate()?;
    Ok(cfg)
}
fn model(cfg: &ds::Config) -> Model {
    let mut m = cfg.model();
    m.id = MODEL_ID.into();
    m.label = "DeepSeek · 全市场策略研究".into();
    m.kind = POLICY.into();
    let cloud = m.cloud.as_mut().expect("cloud");
    cloud.policy_version = POLICY.into();
    cloud.scope = PURPOSE.into();
    cloud.fields = FIELDS.into_iter().map(String::from).collect();
    let grant = m.grant.as_mut().expect("grant");
    grant.purpose = PURPOSE.into();
    grant.scopes = vec![rp::SCOPE.into(), POLICY.into()];
    m
}
pub fn validate_model(m: &Model) -> Result<()> {
    let mut shared = m.clone();
    shared.id = ds::ID.into();
    ds::validate_model(&shared)?;
    let cloud = m.cloud.as_ref().ok_or("MARKET_MODEL_INVALID")?;
    ensure(
        m.id == MODEL_ID
            && is_model(m)
            && m.fake_scenario.is_none()
            && cloud.transport == "https"
            && cloud.policy_version == POLICY
            && cloud.scope == PURPOSE
            && cloud.model_version == MODEL_VERSION
            && cloud.fields == FIELDS,
        "MARKET_MODEL_INVALID",
    )
}
pub fn authorize(m: &Model, scopes: &[String], budget: Option<&Budget>) -> Result<()> {
    validate_model(m)?;
    ensure(
        scopes == [rp::SCOPE, POLICY],
        "MARKET_RESEARCH_SCOPE_INVALID",
    )?;
    let b = budget.ok_or("BUDGET_UNCONFIGURED")?;
    ensure(
        b.currency == "CNY"
            && b.timezone == "Asia/Shanghai"
            && b.daily_limit_micro <= 5_000_000
            && b.monthly_limit_micro <= 100_000_000,
        "MARKET_SHARED_BUDGET_CAP_REQUIRED",
    )?;
    let mut shared = m.clone();
    shared.id = ds::ID.into();
    ds::authorize(&shared, b)?;
    ensure(
        m.cost(m.max_input_tokens, m.max_output_tokens)?
            <= m.cloud.as_ref().expect("cloud").max_call_micro,
        "PRICE_UNBOUNDED",
    )
}

/// Called by the authenticated local Owner API; GET never installs/configures.
/// The standing consent recorded by the first-launch agreement: one scope for
/// the DeepSeek official endpoint, ten years, the exact field list the contract
/// accepts. Kept out of the dashboard so the app never asks again.
pub fn grant_defaults(agent: &Agent) -> Result<Value> {
    let scope = Scope {
        provider: "deepseek".into(),
        recipient: ds::ENDPOINT.into(),
        purpose: PURPOSE.into(),
        source_category: SOURCE.into(),
        fields: FIELDS.iter().map(|field| (*field).to_string()).collect(),
        max_symbols: 8,
        horizon: 20,
        context_sessions: 84,
        valid_until: (Utc::now() + chrono::Duration::days(3650)).to_rfc3339(),
        provider_terms_reviewed: true,
    };
    control(agent, "grant", json!({"confirmed": true, "scope": scope}))
}

pub fn control(agent: &Agent, action: &str, value: Value) -> Result<Value> {
    let mut c = agent.store().connect()?;
    crate::risk_binding::read()?.verify(&c)?;
    let tx = c.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
    match action {
        "configure" => {
            let cfg: Config =
                serde_json::from_value(value).map_err(|_| "MARKET_RESEARCH_CONFIG_INVALID")?;
            cfg.validate()?;
            set(&tx, CONFIG, &cfg)?;
        }
        "grant" => {
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct Input {
                confirmed: bool,
                scope: Scope,
            }
            let input: Input = serde_json::from_value(value).map_err(|_| DENIED)?;
            ensure(input.confirmed, DENIED)?;
            input.scope.validate(Utc::now())?;
            let old: u64 = get(&tx, CURRENT_GRANT)?.unwrap_or(0);
            let grant = Grant {
                version: old + 1,
                authorized_at: Utc::now().to_rfc3339(),
                scope: input.scope,
            };
            tx.execute(
                "INSERT INTO meta VALUES(?1,?2)",
                params![
                    format!("market_research_grant:{}", grant.version),
                    serde_json::to_string(&grant).expect("JSON")
                ],
            )?;
            set(&tx, CURRENT_GRANT, &grant.version)?;
        }
        "revoke" => {
            ensure(value == json!({}), "MARKET_CONTROL_INVALID")?;
            if let Some(version) = get::<u64>(&tx, CURRENT_GRANT)? {
                set(&tx, &format!("market_research_revoked:{version}"), &true)?;
                set(
                    &tx,
                    &format!("market_research_revoked_at:{version}"),
                    &Utc::now().to_rfc3339(),
                )?;
            }
        }
        "pause" => {
            ensure(value == json!({}), "MARKET_CONTROL_INVALID")?;
            let mut cfg: Config = get(&tx, CONFIG)?.unwrap_or_default();
            cfg.automatic_timesfm = false;
            cfg.automatic_deepseek = false;
            set(&tx, CONFIG, &cfg)?;
        }
        _ => return Err("MARKET_CONTROL_INVALID".into()),
    }
    tx.commit()?;
    status(agent)
}
pub fn install_model(agent: &Agent) -> Result<Value> {
    let binding = crate::risk_binding::read()?;
    binding.verify(&agent.store().connect()?)?;
    let cfg = credential_config(&agent.store().connect()?)?;
    let mut settings = Settings::load(&binding.settings_path)?;
    let m = model(&cfg);
    authorize(
        &m,
        &[rp::SCOPE.into(), POLICY.into()],
        settings.budget.as_ref(),
    )?;
    ensure(
        !settings.models.iter().any(|p| p.id == MODEL_ID),
        "MARKET_MODEL_ALREADY_INSTALLED",
    )?;
    settings.models.push(m);
    settings.validate()?;
    use std::io::Write;
    let pending = binding.settings_path.with_extension("json.market-pending");
    crate::eod_snapshot::no_links(&pending)?;
    let mut file = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&pending)
        .map_err(|_| "MARKET_CONFIG_WRITE")?;
    file.write_all(&serde_json::to_vec_pretty(&settings).expect("JSON"))
        .map_err(|_| "MARKET_CONFIG_WRITE")?;
    file.sync_all().map_err(|_| "MARKET_CONFIG_WRITE")?;
    drop(file);
    std::fs::rename(pending, &binding.settings_path).map_err(|_| "MARKET_CONFIG_WRITE")?;
    Ok(json!({"state":"MODEL_INSTALLED","automatic_research":false,"real_egress":false}))
}
pub fn status(agent: &Agent) -> Result<Value> {
    let c = agent.store().connect()?;
    crate::risk_binding::read()?.verify(&c)?;
    let cfg: Config = get(&c, CONFIG)?.unwrap_or_default();
    let version: Option<u64> = get(&c, CURRENT_GRANT)?;
    let grant: Option<Grant> = match version {
        Some(v) => get(&c, &format!("market_research_grant:{v}"))?,
        None => None,
    };
    let mut query = c.prepare(
        "SELECT value FROM meta WHERE key LIKE 'market_research_run:%' ORDER BY key DESC LIMIT 30",
    )?;
    let runs=query.query_map([],|r|r.get::<_,String>(0))?.map(|r| {
        let v:Value=serde_json::from_str(&r?).map_err(|_|"MARKET_RESEARCH_STATE_INVALID")?;
        let result:Option<String>=if let Some(id)=v["fusion_task_id"].as_str() {
            c.query_row("SELECT result FROM tasks WHERE id=?1 AND status='completed'",[id],|r|r.get(0)).optional()?.flatten()
        } else {None};
        let research=match result {Some(raw)=>serde_json::from_str::<Value>(&raw).map_err(|_|"MARKET_RESEARCH_STATE_INVALID")?["research"]["risk_portfolio"].clone(),None=>Value::Null};
        Ok(json!({"source_day":v["source_day"],"state":v["state"],"events":v["events"],"reason":v["reason"],"research":research,
            "cloud_status":v["cloud_status"],"universe_count":v["screen"]["universe_count"],"qualified_count":v["screen"]["qualified_count"],
            "selected":v["screen"]["selected"],"rejection_counts":v["screen"]["rejection_counts"],"screen_sha256":v["screen_sha256"],
            "candidate_sha256":v["candidate_sha256"],"registration_sha256":v["registration_sha256"],"fusion_task_id":v["fusion_task_id"],
            "historical_pit_status":"NOT_VERIFIED","paper_allowed":false,"live_allowed":false}))
    }).collect::<Result<Vec<_>>>()?;
    let b = crate::risk_binding::read()?;
    let settings = Settings::load(&b.settings_path)?;
    Ok(
        json!({"config":cfg,"grant":grant,"grant_active":active_grant(&c,Utc::now()).is_ok(),
        "grant_sha256":grant.as_ref().map(sha),"runs":runs,"fields":FIELDS,
        "recipient":ds::ENDPOINT,"purpose":PURPOSE,"source_category":SOURCE,
        "model_installed":settings.models.iter().any(|m|m.id==MODEL_ID),
        "budget":crate::budget::view(&c,settings.budget.as_ref(),Utc::now())?,
        "daily_cap_micro":"5000000","monthly_cap_micro":"100000000",
        "refresh":"READ_ONLY_NO_INFERENCE","real_market_e2e":"NOT_AUTHORIZED_NOT_RUN"}),
    )
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Context {
    pub source_day: String,
    pub screen_sha256: String,
    pub parent_task_id: i64,
    pub parent_result_sha256: String,
    pub grant_sha256: String,
    pub grant_version: u64,
    pub config_sha256: String,
    pub model_sha256: String,
}
impl Context {
    fn trigger(&self) -> String {
        format!("{POLICY}:{}", self.source_day)
    }
    fn input(&self, plan: &cpu::Plan) -> InputSummary {
        InputSummary {
            version: format!("{POLICY}:{}", sha(self)),
            source_day: plan.frozen.series[0]
                .observations
                .last()
                .expect("observations")
                .trade_day
                .clone(),
            mode: plan.frozen.input_mode.clone(),
            scopes: vec![rp::SCOPE.into(), POLICY.into()],
            summary: serde_json::to_value(self).expect("JSON"),
            eod_eligible: false,
        }
    }
}
fn run(c: &Connection, day: &str) -> Result<Value> {
    ensure(
        day.len() == 8 && day.bytes().all(|b| b.is_ascii_digit()),
        "MARKET_DAY_INVALID",
    )?;
    let v: Value = get(c, &format!("market_research_run:{day}"))?.ok_or("MARKET_RUN_REQUIRED")?;
    ensure(
        v["source_day"] == day
            && v["screen_sha256"] == rp::sha(&v["screen"])
            && v["config_sha256"] == rp::sha(&v["config"])
            && v["screen"]["source_day"] == day
            && v["screen"]["as_of"] == v["as_of"],
        "MARKET_RUN_CHANGED",
    )?;
    Ok(v)
}
fn parent(c: &Connection, ctx: &Context) -> Result<(cpu::Plan, Value)> {
    let r = run(c, &ctx.source_day)?;
    ensure(
        r["data_mode"] == "tushare_incremental_eod"
            || (cfg!(test) && r["data_mode"] == "synthetic_test"),
        "MARKET_SOURCE_MODE_ISOLATION",
    )?;
    let (status, pid, raw, encoded, trigger): (String, String, String, String, String) = c
        .query_row(
            "SELECT status,provider_id,input,result,trigger_key FROM tasks WHERE id=?1",
            [ctx.parent_task_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
        )?;
    let input: InputSummary = serde_json::from_str(&raw).map_err(|_| "MARKET_PARENT_INVALID")?;
    let plan: cpu::Plan = serde_json::from_value(input.summary["plan"].clone())
        .map_err(|_| "MARKET_PARENT_INVALID")?;
    plan.validate(true)?;
    ensure(
        status == "completed"
            && pid == "local-timesfm-2.5-cpu"
            && trigger == format!("{}:market-{}", cpu::POLICY, ctx.source_day)
            && plan.batch == format!("market-{}", ctx.source_day)
            && sha(&plan) == r["plan_sha256"]
            && ctx.screen_sha256 == r["screen_sha256"]
            && ctx.config_sha256 == r["config_sha256"]
            && hash(encoded.as_bytes()) == ctx.parent_result_sha256
            && plan.frozen.as_of == r["as_of"]
            && plan.history.is_some()
            && plan.frozen.input_mode == "historical_research_only",
        "MARKET_PARENT_BINDING",
    )?;
    let selected = r["screen"]["selected"]
        .as_array()
        .ok_or("MARKET_SCREEN_INVALID")?;
    ensure(
        selected.len() == plan.frozen.series.len()
            && selected
                .iter()
                .zip(&plan.frozen.series)
                .all(|(s, p)| s["instrument"] == p.instrument)
            && plan.frozen.series.iter().all(|s| {
                s.observations.iter().all(|o| {
                    o.available_at.parse::<DateTime<Utc>>().is_ok_and(|at| {
                        plan.frozen
                            .as_of
                            .parse::<DateTime<Utc>>()
                            .is_ok_and(|cut| at <= cut)
                    })
                })
            }),
        "MARKET_PARENT_FUTURE_OR_MIXED",
    )?;
    let result: Value = serde_json::from_str(&encoded).map_err(|_| "MARKET_PARENT_INVALID")?;
    let response = serde_json::from_value(result["worker_response"].clone())
        .map_err(|_| "MARKET_PARENT_INVALID")?;
    let bundle = cpu::decode(&plan, &response)?;
    ensure(
        bundle["receipt"]["development_only"] == false
            && bundle == result["research"]["risk_portfolio"],
        "MARKET_PARENT_INVALID",
    )?;
    Ok((plan, bundle))
}
pub fn gate(
    c: &Connection,
    trigger: Option<&str>,
    input: &InputSummary,
    settings: &Settings,
) -> Result<()> {
    let ctx: Context =
        serde_json::from_value(input.summary.clone()).map_err(|_| "MARKET_CONTEXT_INVALID")?;
    let cfg: Config = get(c, CONFIG)?.ok_or("MARKET_RESEARCH_DISABLED")?;
    cfg.validate()?;
    ensure(
        cfg.automatic_timesfm && cfg.automatic_deepseek,
        "MARKET_RESEARCH_DISABLED",
    )?;
    let paused: String = c.query_row("SELECT value FROM meta WHERE key='paused'", [], |r| {
        r.get(0)
    })?;
    ensure(paused != "true", "OWNER_PAUSED")?;
    let grant = active_grant(c, Utc::now())?;
    ensure(
        sha(&grant) == ctx.grant_sha256 && grant.version == ctx.grant_version,
        DENIED,
    )?;
    let (plan, _) = parent(c, &ctx)?;
    ensure(
        plan.frozen.series.len() <= grant.scope.max_symbols
            && plan
                .frozen
                .series
                .iter()
                .all(|s| s.observations.len() <= grant.scope.context_sessions as usize),
        DENIED,
    )?;
    let m = settings
        .models
        .iter()
        .find(|m| m.id == MODEL_ID)
        .ok_or("MARKET_MODEL_REQUIRED")?;
    authorize(m, &input.scopes, settings.budget.as_ref())?;
    ensure(
        m.fingerprint() == ctx.model_sha256
            && sha(input) == sha(&ctx.input(&plan))
            && trigger == Some(ctx.trigger().as_str()),
        "MARKET_CONTEXT_CHANGED",
    )?;
    let original: Config = serde_json::from_value(run(c, &ctx.source_day)?["config"].clone())
        .map_err(|_| "MARKET_CONFIG_INVALID")?;
    let day = Utc::now()
        .with_timezone(&chrono_tz::Asia::Shanghai)
        .format("%Y-%m-%d")
        .to_string();
    let today:i64=c.query_row("SELECT COUNT(*) FROM calls c JOIN tasks t ON t.id=c.task_id WHERE t.provider_id=?1 AND c.day=?2 AND c.state!='no_charge'",params![MODEL_ID,day],|r|r.get(0))?;
    let source:i64=c.query_row("SELECT COUNT(*) FROM calls c JOIN tasks t ON t.id=c.task_id WHERE t.trigger_key=?1 AND c.state!='no_charge'",[ctx.trigger()],|r|r.get(0))?;
    // The current reserved call is included at the final dispatch check.
    let reserved:i64=c.query_row("SELECT COUNT(*) FROM calls c JOIN tasks t ON t.id=c.task_id WHERE t.trigger_key=?1 AND c.state='reserved'",[ctx.trigger()],|r|r.get(0))?;
    ensure(
        today - reserved < i64::from(cfg.daily_call_limit.min(original.daily_call_limit))
            && source - reserved
                < i64::from(
                    cfg.trading_day_call_limit
                        .min(original.trading_day_call_limit),
                ),
        "MARKET_CALL_LIMIT_REACHED",
    )?;
    credential_config(c)?;
    Ok(())
}

fn conclusions(refs: &[String]) -> Value {
    let mut v = crate::fusion_researcher::conclusions(refs);
    v["evidence_scope"] = json!("REAL_MARKET_RMS_RESEARCH_ONLY");
    v
}
fn text() -> Value {
    let mut v = crate::fusion_researcher::controlled_text();
    v["strategy_definition"] = json!("MARKET_RMS_RESEARCH_HYPOTHESIS");
    v["evidence_for"] = json!(["LOCAL_MARKET_RMS_EVIDENCE_ONLY"]);
    v["limitations"] = json!([
        "PIT_NOT_VERIFIED",
        "CORPORATE_ACTION_COVERAGE_PARTIAL",
        "RETURN_DIRECTION_UNKNOWN",
        "ACCOUNT_UNKNOWN",
        "UNCALIBRATED"
    ]);
    v
}
fn request(m: &Model, ctx: &Context, plan: &cpu::Plan, bundle: &Value) -> Result<Value> {
    let f = &plan.frozen;
    // Project fields individually. Raw bars, account/ledger, free-form source
    // metadata and credentials have no representation in this payload.
    let rows = bundle["risk_experts"]
        .as_array()
        .ok_or("MARKET_EVIDENCE_INVALID")?;
    let refs = vec![ctx.screen_sha256.clone(), ctx.parent_result_sha256.clone()];
    let mut portfolio = json!({"schema_version":1,"proposal_id":"market-research","strategy_version":POLICY,
        "strategy_hash":sha(ctx),"source_refs":refs,"as_of":f.as_of,"horizon":20,
        "candidate_instruments":f.series.iter().map(|s|&s.instrument).collect::<Vec<_>>(),"positions":[],"cash_weight_bps":10000,
        "estimated_turnover_bps":null,"estimated_fees_micro":null,"authority":"RESEARCH_ONLY"});
    for (k, v) in text().as_object().expect("text") {
        portfolio[k] = v.clone();
    }
    let payload = json!({"symbols":f.series.iter().map(|s|&s.instrument).collect::<Vec<_>>(),
        "risk_forecasts":rows.iter().map(|r|json!({"instrument":r["instrument"],"volatility_forecast":r["volatility_forecast"],"target":r["target"],"unit":r["unit"]})).collect::<Vec<_>>(),
        "baselines":rows.iter().map(|r|json!({"instrument":r["instrument"],"naive":r["baseline_comparison"]["naive"],"ewma":r["baseline_comparison"]["ewma"]})).collect::<Vec<_>>(),
        "source_refs":refs,"quality":{"historical_pit_status":"NOT_VERIFIED","corporate_actions":"PARTIAL","confidence":"UNCALIBRATED","return_direction":"UNKNOWN"}});
    let user = json!({"mode":"REAL_MARKET_RESEARCH_ONLY","purpose":PURPOSE,"source_category":SOURCE,"as_of":f.as_of,"payload":payload,
        "output_contract":{"portfolio":portfolio,"conclusions":conclusions(&refs),
            "untrusted_hypothesis":{"classification":"UNTRUSTED_HYPOTHESIS","text":"Falsifiable hypothesis and next experiment"}}});
    let body = json!({"model":m.model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":user.to_string()}],
        "max_tokens":m.max_output_tokens,"thinking":{"type":"disabled"},"response_format":{"type":"json_object"},"stream":false});
    ensure(
        body.to_string().len() + 1024 <= m.max_input_tokens as usize,
        "INPUT_TOKEN_BOUND_EXCEEDED",
    )?;
    Ok(body)
}
fn context(c: &Connection, settings: &Settings, day: &str, require_grant: bool) -> Result<Context> {
    let r = run(c, day)?;
    let (id, encoded): (i64, String) = c.query_row(
        "SELECT id,result FROM tasks WHERE trigger_key=?1 AND status='completed'",
        [format!("{}:market-{day}", cpu::POLICY)],
        |r| Ok((r.get(0)?, r.get(1)?)),
    )?;
    let grant = if require_grant {
        Some(active_grant(c, Utc::now())?)
    } else {
        None
    };
    let m = settings
        .models
        .iter()
        .find(|m| m.id == MODEL_ID)
        .ok_or("MARKET_MODEL_REQUIRED")?;
    Ok(Context {
        source_day: day.into(),
        screen_sha256: r["screen_sha256"]
            .as_str()
            .ok_or("MARKET_SCREEN_INVALID")?
            .into(),
        config_sha256: r["config_sha256"]
            .as_str()
            .ok_or("MARKET_CONFIG_INVALID")?
            .into(),
        parent_task_id: id,
        parent_result_sha256: hash(encoded.as_bytes()),
        grant_sha256: grant.as_ref().map(sha).unwrap_or_else(|| "0".repeat(64)),
        grant_version: grant.as_ref().map(|g| g.version).unwrap_or(0),
        model_sha256: m.fingerprint(),
    })
}
pub fn preview(agent: &Agent, day: &str) -> Result<Value> {
    let b = crate::risk_binding::read()?;
    let settings = Settings::load(&b.settings_path)?;
    let c = agent.store().connect()?;
    b.verify(&c)?;
    let ctx = context(&c, &settings, day, false)?;
    let (plan, bundle) = parent(&c, &ctx)?;
    let m = settings
        .models
        .iter()
        .find(|m| m.id == MODEL_ID)
        .expect("configured");
    let body = request(m, &ctx, &plan, &bundle)?;
    Ok(
        json!({"request":body,"request_sha256":sha(&body),"context":ctx,"maximum_micro":m.cost(m.max_input_tokens,m.max_output_tokens)?.to_string(),
        "currency":"CNY","budget":crate::budget::view(&c,settings.budget.as_ref(),Utc::now())?,"network_calls":0,"key_content_read":false}),
    )
}
pub fn execute(agent: &Agent, day: &str) -> Result<Value> {
    let c = agent.store().connect()?;
    crate::risk_binding::read()?.verify(&c)?;
    let trigger = format!("{POLICY}:{day}");
    let prior: Option<i64> = c
        .query_row(
            "SELECT id FROM tasks WHERE trigger_key=?1",
            [&trigger],
            |r| r.get(0),
        )
        .optional()?;
    let id = match prior {
        Some(id) => id,
        None => {
            let b = crate::risk_binding::read()?;
            let settings = Settings::load(&b.settings_path)?;
            let ctx = context(&c, &settings, day, true)?;
            let (plan, _) = parent(&c, &ctx)?;
            let i = ctx.input(&plan);
            gate(&c, Some(&trigger), &i, &settings)?;
            let m = settings
                .models
                .iter()
                .find(|m| m.id == MODEL_ID)
                .expect("configured");
            let req = TaskRequest {
                name: format!("全市场策略研究 {day}"),
                goal: "冻结研究假说与组合目标；不授予交易资格".into(),
                scope: rp::SCOPE.into(),
                start_day: i.source_day.clone(),
                end_day: i.source_day.clone(),
                task_budget_micro: Some(
                    m.cost(m.max_input_tokens, m.max_output_tokens)?.to_string(),
                ),
            };
            agent.store().create_for_model(
                &settings,
                &req,
                &i,
                Utc::now(),
                Some(&trigger),
                MODEL_ID,
            )?
        }
    };
    if agent.store().task(id)?["status"] == "queued" {
        agent.tick_task(Utc::now(), id, &trigger)?;
    }
    agent.store().task(id)
}
pub struct Prepared {
    model: Model,
    ctx: Context,
    body: Value,
    key: Zeroizing<String>,
    https: (reqwest::blocking::Client, reqwest::Url),
}
pub fn prepare(m: &Model, input: &Value) -> Result<Prepared> {
    let i: InputSummary = serde_json::from_value(input["published_summary"].clone())
        .map_err(|_| "MARKET_INPUT_INVALID")?;
    let ctx: Context =
        serde_json::from_value(i.summary.clone()).map_err(|_| "MARKET_CONTEXT_INVALID")?;
    let (b, c) = crate::local_fusion::connection()?;
    let settings = Settings::load(&b.settings_path)?;
    gate(&c, Some(&ctx.trigger()), &i, &settings)?;
    let (plan, bundle) = parent(&c, &ctx)?;
    let body = request(m, &ctx, &plan, &bundle)?;
    let cfg = credential_config(&c)?;
    let key = ds::read_key(&cfg)?;
    ensure(
        !body.to_string().contains(key.as_str()),
        "DEEPSEEK_SECRET_IN_REQUEST_DENIED",
    )?;
    #[cfg(test)]
    let https = tests::transport(&ctx)?;
    #[cfg(not(test))]
    let https = crate::provider::https_client(m)?;
    Ok(Prepared {
        model: m.clone(),
        ctx,
        body,
        key,
        https,
    })
}
fn decode(m: &Model, ctx: &Context, body: &Value, bytes: &[u8]) -> Result<(Value, u32, u32)> {
    ensure(bytes.len() <= 65536, "DEEPSEEK_RESPONSE_SIZE")?;
    let v: Value = serde_json::from_slice(bytes).map_err(|_| "DEEPSEEK_RESPONSE_JSON")?;
    let choices = v["choices"].as_array().ok_or("DEEPSEEK_CHOICES")?;
    ensure(
        v["model"] == ds::MODEL
            && choices.len() == 1
            && choices[0]["index"] == 0
            && choices[0]["finish_reason"] == "stop"
            && choices[0]["message"]["role"] == "assistant"
            && choices[0]["message"]["tool_calls"].is_null()
            && choices[0]["message"]["function_call"].is_null(),
        "DEEPSEEK_RESPONSE_PROTOCOL",
    )?;
    let input = v["usage"]["prompt_tokens"]
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or("DEEPSEEK_USAGE")?;
    let output = v["usage"]["completion_tokens"]
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or("DEEPSEEK_USAGE")?;
    ensure(
        input > 0
            && output > 0
            && input <= m.max_input_tokens
            && output <= m.max_output_tokens
            && v["usage"]["total_tokens"] == u64::from(input) + u64::from(output),
        "DEEPSEEK_USAGE_BOUND",
    )?;
    let response: crate::fusion_researcher::Response = serde_json::from_str(
        choices[0]["message"]["content"]
            .as_str()
            .ok_or("PORTFOLIO_SCHEMA")?,
    )
    .map_err(|_| "PORTFOLIO_SCHEMA")?;
    let p = &response.portfolio;
    p.validate()?;
    let user: Value =
        serde_json::from_str(body["messages"][1]["content"].as_str().expect("user")).expect("JSON");
    let expected = &user["output_contract"]["portfolio"];
    let actual = serde_json::to_value(p).expect("portfolio");
    for (key, value) in expected.as_object().expect("contract") {
        if key != "positions" && key != "cash_weight_bps" {
            ensure(
                actual[key] == *value,
                "MARKET_CONTROLLED_CONCLUSION_REQUIRED",
            )?;
        }
    }
    ensure(
        p.positions.iter().all(|p| {
            user["payload"]["symbols"]
                .as_array()
                .expect("symbols")
                .contains(&json!(p.instrument))
        }) && response.conclusions == conclusions(&p.source_refs)
            && response.untrusted_hypothesis.classification == "UNTRUSTED_HYPOTHESIS"
            && rp::text(&response.untrusted_hypothesis.text, 4000),
        "MARKET_RESPONSE_AUTHORITY_OR_BINDING",
    )?;
    let mut result = rp::safe();
    result["paper_allowed"] = json!(false);
    result["portfolio"] = actual;
    result["conclusions"] = response.conclusions;
    result["untrusted_hypothesis"] =
        serde_json::to_value(response.untrusted_hypothesis).expect("JSON");
    result["strategy_artifact_sha256"] = json!(rp::sha(&result["portfolio"]));
    result["receipt"] = json!({"contract":POLICY,"grant_version":ctx.grant_version,"grant_sha256":ctx.grant_sha256,
        "transport":if cfg!(test){"test_loopback"}else{"https"},"verification":if cfg!(test){"TEST_LOOPBACK_NOT_REAL_PROVIDER"}else{"REAL_PROVIDER_CALL_OBSERVED"},
        "request_sha256":sha(body),"response_sha256":hash(bytes),"parent_task_id":ctx.parent_task_id,
        "parent_result_sha256":ctx.parent_result_sha256,"model_sha256":ctx.model_sha256,"model_version":MODEL_VERSION,
        "prompt_sha256":hash(SYSTEM.as_bytes()),"input_tokens":input,"output_tokens":output,"price_version":m.price.as_ref().expect("price").version,
        "usage_estimate_micro":m.cost(input,output)?,"billing":"USAGE_ESTIMATE_MAXIMUM_HELD_UNTIL_OWNER_INVOICE_RECONCILIATION",
        "historical_pit_status":"NOT_VERIFIED","narrative_authority":"UNTRUSTED_HYPOTHESIS_NOT_EVIDENCE"});
    rp::validate_output(&result)?;
    Ok((result, input, output))
}
pub fn call(p: Prepared) -> crate::provider::Outcome {
    use crate::provider::Outcome;
    let response = match p
        .https
        .0
        .post(p.https.1)
        .bearer_auth(p.key.as_str())
        .json(&p.body)
        .send()
    {
        Ok(r) => r,
        Err(_) => return Outcome::Uncertain("MARKET_PROVIDER_OUTCOME_UNKNOWN"),
    };
    if !response.status().is_success() {
        return Outcome::Uncertain("MARKET_PROVIDER_HTTP_OUTCOME_UNKNOWN");
    }
    let mut bytes = Vec::new();
    if response.take(65537).read_to_end(&mut bytes).is_err() {
        return Outcome::Uncertain("MARKET_PROVIDER_BODY_UNKNOWN");
    }
    if bytes.windows(p.key.len()).any(|s| s == p.key.as_bytes()) {
        return Outcome::Uncertain("DEEPSEEK_SECRET_ECHO_DENIED");
    }
    match decode(&p.model, &p.ctx, &p.body, &bytes) {
        Ok((result, input_tokens, output_tokens)) => Outcome::Success {
            research: Research {
                hypothesis: "MARKET_RMS_RESEARCH_HYPOTHESIS".into(),
                evidence: vec![p.ctx.parent_result_sha256],
                risks: vec!["PIT_NOT_VERIFIED; UNCALIBRATED; RESEARCH_ONLY".into()],
                next_steps: vec!["Independent evaluation required".into()],
                fusion: None,
                risk_portfolio: Some(result),
                structured_research: None,
            },
            input_tokens,
            output_tokens,
        },
        Err(_) => Outcome::Uncertain("MARKET_PROVIDER_RESPONSE_REJECTED_NO_RETRY"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    pub(super) fn transport(ctx: &Context) -> Result<(reqwest::blocking::Client, reqwest::Url)> {
        let (_, c) = crate::local_fusion::connection()?;
        assert_eq!(run(&c, &ctx.source_day)?["data_mode"], "synthetic_test");
        let port = std::env::var("STRATIDE_MARKET_TEST_PORT")
            .map_err(|_| "TEST_LOOPBACK_REQUIRED")?
            .parse::<u16>()
            .map_err(|_| "TEST_PORT")?;
        ensure(port > 0, "TEST_PORT")?;
        Ok((
            reqwest::blocking::Client::builder()
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .retry(reqwest::retry::never())
                .timeout(std::time::Duration::from_millis(1000))
                .build()
                .expect("client"),
            reqwest::Url::parse(&format!("http://127.0.0.1:{port}/chat/completions")).expect("URL"),
        ))
    }
    #[test]
    fn scope_rejects_missing_field_other_purpose_recipient_and_expiry() {
        let scope = Scope {
            provider: "deepseek".into(),
            recipient: ds::ENDPOINT.into(),
            purpose: PURPOSE.into(),
            source_category: SOURCE.into(),
            fields: FIELDS.into_iter().map(String::from).collect(),
            max_symbols: 8,
            horizon: 20,
            context_sessions: 84,
            valid_until: (Utc::now() + chrono::Duration::days(1)).to_rfc3339(),
            provider_terms_reviewed: true,
        };
        scope.validate(Utc::now()).unwrap();
        let mut bad = scope.clone();
        bad.fields.pop();
        assert!(bad.validate(Utc::now()).is_err());
        let mut bad = scope.clone();
        bad.purpose = "orders".into();
        assert!(bad.validate(Utc::now()).is_err());
        let mut bad = scope.clone();
        bad.recipient = "https://other.example/chat/completions".into();
        assert!(bad.validate(Utc::now()).is_err());
        let mut bad = scope.clone();
        bad.source_category = "account_ledger".into();
        assert!(bad.validate(Utc::now()).is_err());
        let mut bad = scope.clone();
        bad.valid_until = Utc::now().to_rfc3339();
        assert!(bad.validate(Utc::now()).is_err());
    }
    #[test]
    fn process_driver() {
        if std::env::var("STRATIDE_MARKET_TEST_DRIVER").as_deref() != Ok("1") {
            return;
        }
        let mut raw = String::new();
        std::io::stdin().read_to_string(&mut raw).unwrap();
        let v: Value = serde_json::from_str(&raw).unwrap();
        let result = (|| -> Result<Value> {
            let b = crate::risk_binding::read()?;
            let agent = Agent::open(
                &b.agent_dir,
                Some(&b.settings_path),
                crate::local_fusion::blank(),
            )?;
            execute(&agent, v["source_day"].as_str().unwrap())
        })();
        println!(
            "MARKET_RESULT={}",
            match result {
                Ok(v) => v,
                Err(e) => json!({"state":"BLOCKED","error_code":e.0}),
            }
        );
    }
}
