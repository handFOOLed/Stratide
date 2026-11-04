//! A completed local CPU task feeds one call through the original Agent/Budget.
use crate::{
    config::{Budget, Model, Settings},
    deepseek as ds, ensure, hash, provider, risk_binding as binding, risk_cpu as cpu,
    risk_portfolio as rp, Agent, InputSummary, Research, Result, TaskRequest,
};
use chrono::Utc;
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    io::{Read, Write},
    path::Path,
    time::Instant,
};
use zeroize::Zeroizing;
pub const POLICY: &str = "local_timesfm_fusion_v1";
pub const MODEL_ID: &str = "ds4.1flash-fusion";
const CONFIG: &str = "local_timesfm_fusion_config_v1";
const PERMIT: &str = "local_timesfm_fusion_permit_v1";
const GRANT: &str = "deepseek-synthetic-fusion-grant-v1";
// PR72 0b24575 used the identical V1 request/decoder before model snapshots.
// This compatibility pin is accepted by read-only verification, never dispatch.
const PRE_SNAPSHOT_ADAPTER_SHA: &str =
    "a5bd6c9a53d223a60fdfb25633d077b4f5ef1a2df93170af3a5f41f18db57474";

const LEGACY_ROLE_ADAPTER_SHA: &str =
    "e979cf6ba7894239493c1a72daac7dbff3e4357a1ddf342aab14d1052c1772e7";
const PR78_R1_ADAPTER_SHA: &str =
    "4686ab55ecc60385210d608dde678e66bf363ccf87fd0736abdca5dfdf6920b1";
const SYSTEM:&str="Return exactly one JSON TargetPortfolioProposal V1 using output_contract values and field types. Input is synthetic engineering evidence, never market alpha. Propose a falsifiable research hypothesis and stocks/cash or 100 percent cash. Missing return/opportunity/account facts remain UNKNOWN. Positions use only evidence instruments. Text arrays contain at least one concise item. No tools, code, URLs, permissions or orders. All cash is valid; weights plus cash equal 10000. Keep output below 2500 tokens. Return exactly the root keys in output_contract, with no wrapper or extra keys. All evidence and risk text fields shown as arrays must be arrays of strings, never objects. estimated_turnover_bps and estimated_fees_micro must be null.";
const PR19_CODE_SHA: &str = "b2a855cd86acd7acd7cd09c224ba5946e67dd35a0fb7584209fc558fced188ab";
pub fn code_sha() -> String {
    hash(
        concat!(
            include_str!("local_fusion.rs"),
            include_str!("bin/local-fusion-agent.rs"),
            include_str!("fusion_researcher.rs"),
            include_str!("../prompts/fusion-researcher-v1-system.txt"),
            include_str!("../prompts/fusion-researcher-v1-developer.txt"),
            include_str!("../prompts/fusion-researcher-v1-legacy-system.txt"),
            include_str!("../prompts/fusion-researcher-v1-legacy-developer.txt")
        )
        .as_bytes(),
    )
}
pub fn is_model(m: &Model) -> bool {
    m.kind == POLICY
}
pub fn is_input(i: &InputSummary) -> bool {
    i.scopes.iter().any(|s| s == POLICY)
}
pub fn blank() -> InputSummary {
    InputSummary {
        version: "no-input".into(),
        source_day: String::new(),
        mode: "no_input".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    }
}
fn get<T: serde::de::DeserializeOwned>(c: &Connection, k: &str) -> Result<T> {
    let raw: String = c.query_row("SELECT value FROM meta WHERE key=?1", [k], |r| r.get(0))?;
    serde_json::from_str(&raw).map_err(|_| "FUSION_LOCAL_CONFIG_INVALID".into())
}
fn set(c: &Connection, k: &str, v: &impl Serialize) -> Result<()> {
    c.execute(
        "INSERT INTO meta VALUES(?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![k, serde_json::to_string(v).unwrap()],
    )?;
    Ok(())
}
pub fn connection() -> Result<(binding::Binding, Connection)> {
    let b = binding::read()?;
    let c = Connection::open_with_flags(
        b.agent_dir.join("agent.sqlite"),
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )?;
    b.verify(&c)?;
    Ok((b, c))
}
fn validate_config(cfg: &ds::Config) -> Result<()> {
    ensure(cfg.grant_version == GRANT, "FUSION_PURPOSE_GRANT_REQUIRED")?;
    let mut common = cfg.clone();
    common.grant_version = "deepseek-synthetic-grant-v1".into();
    common.validate()
}
pub fn model(cfg: &ds::Config) -> Model {
    let mut m = cfg.model();
    m.id = MODEL_ID.into();
    m.label = "ds4.1flash / local TimesFM Fusion".into();
    m.kind = POLICY.into();
    let g = m.grant.as_mut().unwrap();
    g.purpose = "portfolio_fusion_v1".into();
    g.scopes = vec![POLICY.into(), "portfolio_fusion_v1".into()];
    let c = m.cloud.as_mut().unwrap();
    c.policy_version = POLICY.into();
    c.scope = "portfolio_fusion_v1".into();
    c.fields = vec![
        "synthetic_risk_summary".into(),
        "source_refs".into(),
        "output_contract".into(),
    ];
    m
}
pub fn validate_model(m: &Model) -> Result<()> {
    let c = m.cloud.as_ref().ok_or("FUSION_MODEL_INVALID")?;
    ensure(
        is_model(m)
            && m.id == MODEL_ID
            && m.model == ds::MODEL
            && m.endpoint.as_deref() == Some(ds::ENDPOINT)
            && m.api_key_env.as_deref() == Some(ds::KEY_ENV)
            && m.max_input_tokens == 32768
            && m.max_output_tokens == 4096
            && m.timeout_seconds <= 60
            && c.transport == "https"
            && c.policy_version == POLICY
            && c.scope == "portfolio_fusion_v1"
            && c.fields == ["synthetic_risk_summary", "source_refs", "output_contract"]
            && c.project.is_none()
            && c.dataset.is_none()
            && c.location.is_none()
            && c.maximum_bytes_billed.is_none()
            && c.billing_unit == "input_output_tokens"
            && m.fake_scenario.is_none(),
        "FUSION_MODEL_INVALID",
    )
}
pub fn authorize(m: &Model, scopes: &[String], b: Option<&Budget>) -> Result<()> {
    validate_model(m)?;
    let b = b.ok_or("BUDGET_UNCONFIGURED")?;
    let g = m.grant.as_ref().ok_or("FUSION_PURPOSE_GRANT_REQUIRED")?;
    ensure(
        scopes == [POLICY, "portfolio_fusion_v1"]
            && g.purpose == "portfolio_fusion_v1"
            && g.scopes == scopes
            && g.receiver == ds::ENDPOINT
            && !g.revoked
            && chrono::DateTime::parse_from_rfc3339(&g.authorized_at)
                .is_ok_and(|at| at <= Utc::now()),
        "FUSION_PURPOSE_GRANT_REQUIRED",
    )?;
    let mut shared = m.clone();
    shared.id = ds::ID.into();
    shared.kind = "structured_research_v1".into();
    ds::authorize(&shared, b)?;
    ensure(
        m.price
            .as_ref()
            .is_some_and(|p| p.bounded_text_billing_verified)
            && m.cost(m.max_input_tokens, m.max_output_tokens)?
                <= m.cloud.as_ref().unwrap().max_call_micro,
        "PRICE_UNBOUNDED",
    )
}
pub fn init_cny() -> Result<Value> {
    let state = rp::root()?;
    if state.join("agent-binding.json").exists() {
        let (b, c) = connection()?;
        let s = Settings::load(&b.settings_path)?;
        let identity: String = c.query_row(
            "SELECT value FROM meta WHERE key='budget_identity'",
            [],
            |r| r.get(0),
        )?;
        ensure(
            identity == "CNY|Asia/Shanghai"
                && s.budget.as_ref().is_some_and(|b| b.currency == "CNY"),
            "TST_HISTORY_IMMUTABLE_USE_EXISTING_REAL_CNY_AGENT",
        )?;
        return Ok(json!({"state":"EXISTING_CNY_AUTHORITY","authority_id":b.authority_id}));
    }
    let dir = state
        .parent()
        .ok_or("CLOUD_STATE_ROOT")?
        .join("owner-agent-cny");
    crate::eod_snapshot::no_links(&dir)?;
    fs::create_dir_all(&dir).map_err(|_| "FUSION_INIT_FAILED")?;
    let path = dir.join("settings.json");
    if !path.exists() {
        let s = Settings {
            budget: Some(Budget {
                currency: "CNY".into(),
                timezone: "Asia/Shanghai".into(),
                daily_limit_micro: 5_000_000,
                monthly_limit_micro: 100_000_000,
            }),
            ..Settings::default()
        };
        let mut f = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .map_err(|_| "FUSION_INIT_FAILED")?;
        f.write_all(&serde_json::to_vec_pretty(&s).unwrap())
            .map_err(|_| "FUSION_INIT_FAILED")?;
        f.sync_all().map_err(|_| "FUSION_INIT_FAILED")?;
    }
    let s = Settings::load(&path)?;
    ensure(
        s.budget
            .as_ref()
            .is_some_and(|b| b.currency == "CNY" && b.timezone == "Asia/Shanghai"),
        "TST_HISTORY_IMMUTABLE_USE_EXISTING_REAL_CNY_AGENT",
    )?;
    drop(Agent::open(&dir, Some(&path), blank())?);
    let b = binding::bind(&dir, None)?;
    Ok(
        json!({"state":"UNIQUE_ORIGINAL_CNY_AGENT_BOUND","authority_id":b.authority_id,"old_TST_ledgers":"UNTOUCHED","automatic_research":false}),
    )
}
pub fn configure(path: &Path) -> Result<Value> {
    let (b, c) = connection()?;
    let mut s = Settings::load(&b.settings_path)?;
    let identity: String = c.query_row(
        "SELECT value FROM meta WHERE key='budget_identity'",
        [],
        |r| r.get(0),
    )?;
    ensure(
        identity == "CNY|Asia/Shanghai"
            && s.budget
                .as_ref()
                .is_some_and(|b| b.currency == "CNY" && b.timezone == "Asia/Shanghai"),
        "EXISTING_REAL_CNY_OWNER_BUDGET_REQUIRED",
    )?;
    let cfg: ds::Config =
        serde_json::from_value(rp::read(path, 8192)?).map_err(|_| "FUSION_LOCAL_CONFIG_INVALID")?;
    validate_config(&cfg)?;
    ds::key_metadata(&cfg.key_file)?;
    let mut scfg = cfg.clone();
    scfg.grant_version = "deepseek-synthetic-grant-v1".into();
    // PR17's descriptor shares the wallet; its separate control remains unconfigured/OFF.
    for m in [scfg.model(), model(&cfg)] {
        if let Some(old) = s.models.iter_mut().find(|old| old.id == m.id) {
            ensure(
                (m.id == MODEL_ID && is_model(old)) || (m.id == ds::ID && ds::is_model(old)),
                "DEEPSEEK_MODEL_ID_CONFLICT",
            )?;
            if m.id == MODEL_ID {
                *old = m;
            }
        } else {
            s.models.push(m);
        }
    }
    let budget = s.budget.as_mut().unwrap();
    budget.daily_limit_micro = 5_000_000;
    budget.monthly_limit_micro = 100_000_000;
    s.default_model = Some(ds::ID.into());
    s.validate()?;
    drop(c);
    let a = Agent::open(&b.agent_dir, Some(&b.settings_path), blank())?;
    let pending = b.settings_path.with_extension("json.fusion-pending");
    crate::eod_snapshot::no_links(&pending)?;
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&pending)
        .map_err(|_| "FUSION_CONFIG_WRITE")?;
    f.write_all(&serde_json::to_vec_pretty(&s).unwrap())
        .map_err(|_| "FUSION_CONFIG_WRITE")?;
    f.sync_all().map_err(|_| "FUSION_CONFIG_WRITE")?;
    drop(f);
    fs::rename(pending, &b.settings_path).map_err(|_| "FUSION_CONFIG_WRITE")?;
    let c = a.store().connect()?;
    set(&c, CONFIG, &cfg)?;
    a.store().set("default_model", ds::ID)?;
    set(&c, PERMIT, &json!({"enabled":false}))?;
    Ok(
        json!({"state":"CONFIGURED_OFF","default_model":ds::ID,"fusion_model_id":MODEL_ID,"api_model":ds::MODEL,"key_content_read":false,
        "budget":crate::budget::view(&c,s.budget.as_ref(),Utc::now())?}),
    )
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Context {
    pub policy: String,
    pub batch: String,
    pub authority_id: String,
    pub parent_task_id: i64,
    pub parent_result_sha256: String,
    pub parent_plan_sha256: String,
    pub model_sha256: String,
    pub adapter_sha256: String,
}
impl Context {
    pub fn trigger(&self) -> String {
        format!(
            "{POLICY}:{}:{}",
            self.parent_task_id, self.parent_result_sha256
        )
    }
    pub fn input(&self, f: &rp::Frozen) -> InputSummary {
        InputSummary {
            version: format!("{POLICY}:{}", rp::sha(&serde_json::to_value(self).unwrap())),
            source_day: f.series[0].observations.last().unwrap().trade_day.clone(),
            mode: f.input_mode.clone(),
            scopes: vec![POLICY.into(), "portfolio_fusion_v1".into()],
            summary: serde_json::to_value(self).unwrap(),
            eod_eligible: false,
        }
    }
}
pub fn context(i: &InputSummary) -> Result<Context> {
    let ctx: Context =
        serde_json::from_value(i.summary.clone()).map_err(|_| "FUSION_CONTEXT_INVALID")?;
    ensure(
        ctx.policy == POLICY
            && crate::eod_snapshot::valid_name(&ctx.batch)
            && ctx.adapter_sha256 == code_sha()
            && rp::valid_sha(&ctx.model_sha256)
            && rp::valid_sha(&ctx.parent_result_sha256)
            && rp::valid_sha(&ctx.parent_plan_sha256),
        "FUSION_CONTEXT_INVALID",
    )?;
    Ok(ctx)
}
pub fn parent(c: &Connection, ctx: &Context, fresh: bool) -> Result<(cpu::Plan, Value)> {
    let b = binding::read()?;
    b.verify(c)?;
    ensure(
        ctx.authority_id == b.authority_id,
        "FUSION_CROSS_AGENT_DENIED",
    )?;
    let (status, pid, pin, input, encoded, trigger): (
        String,
        String,
        String,
        String,
        Option<String>,
        Option<String>,
    ) = c.query_row(
        "SELECT status,provider_id,provider_hash,input,result,trigger_key FROM tasks WHERE id=?1",
        [ctx.parent_task_id],
        |r| {
            Ok((
                r.get(0)?,
                r.get(1)?,
                r.get(2)?,
                r.get(3)?,
                r.get(4)?,
                r.get(5)?,
            ))
        },
    )?;
    let i: InputSummary = serde_json::from_str(&input).map_err(|_| "LOCAL_TASK_CHANGED")?;
    let plan: cpu::Plan =
        serde_json::from_value(i.summary["plan"].clone()).map_err(|_| "LOCAL_PLAN_SCHEMA")?;
    ensure(
        plan.history.is_none() && plan.frozen.input_mode == "synthetic_test",
        "REAL_MARKET_DATA_EGRESS_DENIED",
    )?;
    let encoded = encoded.ok_or("FUSION_LOCAL_PARENT_INCOMPLETE")?;
    ensure(
        status == "completed"
            && pid == "local-timesfm-2.5-cpu"
            && trigger.as_deref() == Some(format!("{}:{}", cpu::POLICY, ctx.batch).as_str())
            && plan.batch == ctx.batch
            && pin == plan.pin()
            && serde_json::to_value(&i).unwrap() == serde_json::to_value(plan.input()).unwrap()
            && plan.frozen.risk_model.id == "local-timesfm-2.5-cpu"
            && plan.frozen.risk_model.fingerprint == plan.code_sha256
            && hash(encoded.as_bytes()) == ctx.parent_result_sha256
            && rp::sha(&serde_json::to_value(&plan).unwrap()) == ctx.parent_plan_sha256,
        "FUSION_LOCAL_PARENT_CHANGED",
    )?;
    plan.validate(fresh)?;
    let n: i64 = c.query_row(
        "SELECT count(*) FROM calls WHERE task_id=?1",
        [ctx.parent_task_id],
        |r| r.get(0),
    )?;
    ensure(n == 0, "LOCAL_BILLING_INVALID")?;
    let result: Value = serde_json::from_str(&encoded).map_err(|_| "LOCAL_RESULT_CHANGED")?;
    let response: cpu::Response = serde_json::from_value(result["worker_response"].clone())
        .map_err(|_| "LOCAL_RESPONSE_SCHEMA")?;
    let bundle = cpu::decode(&plan, &response)?;
    ensure(
        result["billing"] == "LOCAL_NO_BILLING"
            && bundle["receipt"]["development_only"] == false
            && result["research"]["risk_portfolio"] == bundle,
        "FUSION_LOCAL_PARENT_CHANGED",
    )?;
    Ok((plan, bundle))
}
fn configured(c: &Connection, s: &Settings) -> Result<(ds::Config, Model)> {
    let cfg: ds::Config = get(c, CONFIG)?;
    validate_config(&cfg)?;
    let m = s
        .models
        .iter()
        .find(|m| m.id == MODEL_ID)
        .ok_or("FUSION_MODEL_MISSING")?;
    authorize(
        m,
        &[POLICY.into(), "portfolio_fusion_v1".into()],
        s.budget.as_ref(),
    )?;
    ensure(
        m.fingerprint() == model(&cfg).fingerprint(),
        "FUSION_MODEL_CHANGED",
    )?;
    Ok((cfg, m.clone()))
}
pub fn gate(c: &Connection, trigger: Option<&str>, i: &InputSummary, s: &Settings) -> Result<()> {
    let ctx = context(i)?;
    let (plan, _) = parent(c, &ctx, true)?;
    ensure(
        serde_json::to_value(i).unwrap() == serde_json::to_value(ctx.input(&plan.frozen)).unwrap()
            && trigger == Some(ctx.trigger().as_str()),
        "FUSION_INPUT_CHANGED",
    )?;
    let (_, m) = configured(c, s)?;
    ensure(m.fingerprint() == ctx.model_sha256, "FUSION_MODEL_CHANGED")?;
    let paused: String = c.query_row("SELECT value FROM meta WHERE key='paused'", [], |r| {
        r.get(0)
    })?;
    let p: Value = get(c, PERMIT)?;
    ensure(paused != "true", "OWNER_PAUSED")?;
    ensure(
        p["enabled"] == true
            && p["trigger"] == ctx.trigger()
            && p["context_sha256"] == rp::sha(&serde_json::to_value(&ctx).unwrap()),
        "FUSION_DISABLED_OR_ONCE_CONSUMED",
    )
}
pub fn consume(c: &Connection) -> Result<()> {
    let mut p: Value = get(c, PERMIT)?;
    ensure(p["enabled"] == true, "FUSION_DISABLED_OR_ONCE_CONSUMED")?;
    p["enabled"] = json!(false);
    set(c, PERMIT, &p)
}
fn make_context(c: &Connection, s: &Settings, batch: &str) -> Result<(Context, cpu::Plan, Value)> {
    ensure(crate::eod_snapshot::valid_name(batch), "LOCAL_BATCH_NAME")?;
    let (id, raw, encoded): (i64, String, Option<String>) = c.query_row(
        "SELECT id,input,result FROM tasks WHERE trigger_key=?1",
        [format!("{}:{batch}", cpu::POLICY)],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    )?;
    let input: Value = serde_json::from_str(&raw).map_err(|_| "LOCAL_PLAN_SCHEMA")?;
    let plan: cpu::Plan = serde_json::from_value(input["summary"]["plan"].clone())
        .map_err(|_| "LOCAL_PLAN_SCHEMA")?;
    ensure(
        plan.history.is_none() && plan.frozen.input_mode == "synthetic_test",
        "REAL_MARKET_DATA_EGRESS_DENIED",
    )?;
    let m = s
        .models
        .iter()
        .find(|m| m.id == MODEL_ID)
        .ok_or("FUSION_MODEL_MISSING")?;
    let ctx = Context {
        policy: POLICY.into(),
        batch: batch.into(),
        authority_id: binding::read()?.authority_id,
        parent_task_id: id,
        parent_result_sha256: hash(encoded.ok_or("FUSION_LOCAL_PARENT_INCOMPLETE")?.as_bytes()),
        parent_plan_sha256: rp::sha(&serde_json::to_value(&plan).unwrap()),
        model_sha256: m.fingerprint(),
        adapter_sha256: code_sha(),
    };
    let (plan, bundle) = parent(c, &ctx, false)?;
    Ok((ctx, plan, bundle))
}
pub fn body(m: &Model, ctx: &Context, f: &rp::Frozen, bundle: &Value) -> Result<Value> {
    let experts = bundle["risk_experts"]
        .as_array()
        .ok_or("RISK_EVIDENCE_REQUIRED")?;
    let researcher = ctx.adapter_sha256 == code_sha();
    let legacy_role = ctx.adapter_sha256 == PR78_R1_ADAPTER_SHA;
    if researcher || legacy_role {
        crate::fusion_researcher::validate_evidence(f, experts)?;
    }
    let summary:Vec<Value>=experts.iter().map(|e|json!({"instrument":e["instrument"],"volatility_forecast":e["volatility_forecast"],
        "target":e["target"],"unit":e["unit"],"market_regime":e["market_regime"],"naive":e["baseline_comparison"]["naive"],
        "ewma":e["baseline_comparison"]["ewma"],"uncertainty":e["uncertainty"],"quality_blockers":e["quality_blockers"],
        "covariance":e["covariance"],"downside_metric":e["downside_metric"]})).collect();
    let contract = json!({"schema_version":1,"proposal_id":"bounded research identifier","strategy_version":f.strategy_version,
        "strategy_hash":f.strategy_hash(),"strategy_definition":"concise falsifiable hypothesis; no code",
        "source_refs":[f.snapshot_ref,f.strategy_hash()],"as_of":f.as_of,"horizon":20,
        "candidate_instruments":f.series.iter().map(|s|&s.instrument).collect::<Vec<_>>(),"positions":[],"cash_weight_bps":10000,
        "rationale":"string","evidence_for":["string"],"evidence_against":["string"],"risk_assessment":["string"],
        "invalidation_conditions":["string"],"next_experiment":["string"],"limitations":["string"],
        "estimated_turnover_bps":null,"estimated_fees_micro":null,"authority":"RESEARCH_ONLY"});
    let mut user = json!({"mode":"SYNTHETIC_ENGINEERING_ONLY","synthetic_risk_summary":summary,
        "source_refs":{"snapshot_sha256":f.snapshot_ref,"local_result_sha256":ctx.parent_result_sha256,
            "local_plan_sha256":ctx.parent_plan_sha256,"model_weight_sha256":cpu::WEIGHT_SHA},
        "opportunity":"UNKNOWN_NO_RETURN_EVIDENCE","account":"UNKNOWN_NO_ACCOUNT_ORDERS","output_contract":contract,
        "positions_contract":"optional [{instrument,target_weight_bps}] only evidence instruments; cash plus positions exactly 10000"});
    let system = if researcher || legacy_role {
        user["researcher_contract"] = json!({"version":crate::fusion_researcher::VERSION,
            "prompt_sha256":if legacy_role {crate::fusion_researcher::legacy_prompt_sha()} else {crate::fusion_researcher::prompt_sha()},
            "narrative_authority":"UNTRUSTED_HYPOTHESIS_NOT_EVIDENCE"});
        user["output_contract"]["evidence_for"] = json!(["SYNTHETIC_RISK_EVIDENCE_ONLY"]);
        user["output_contract"]["limitations"] = json!(crate::fusion_researcher::LIMITATIONS);
        if legacy_role {
            crate::fusion_researcher::legacy_instructions()
        } else {
            for (key, value) in crate::fusion_researcher::controlled_text()
                .as_object()
                .unwrap()
            {
                user["output_contract"][key] = value.clone();
            }
            user["output_contract"]["proposal_id"] = json!("fusion-research");
            user["output_contract"] = json!({"portfolio":user["output_contract"],
                "conclusions":crate::fusion_researcher::conclusions(&[f.snapshot_ref.clone(),f.strategy_hash()]),
                "untrusted_hypothesis":{"classification":"UNTRUSTED_HYPOTHESIS","text":"Falsifiable research hypothesis only"}});
            user["researcher_contract"]["output_envelope"] =
                json!(crate::fusion_researcher::CONTRACT);
            crate::fusion_researcher::instructions()
        }
    } else {
        SYSTEM.to_owned()
    };
    let body = json!({"model":m.model,"messages":[{"role":"system","content":system},{"role":"user","content":user.to_string()}],
        "max_tokens":m.max_output_tokens,"thinking":{"type":"disabled"},"response_format":{"type":"json_object"},"stream":false});
    ensure(
        body.to_string().len() + 1024 <= m.max_input_tokens as usize,
        "INPUT_TOKEN_BOUND_EXCEEDED",
    )?;
    Ok(body)
}
pub fn preflight(batch: &str) -> Result<Value> {
    let (b, c) = connection()?;
    let s = Settings::load(&b.settings_path)?;
    let (ctx, plan, bundle) = make_context(&c, &s, batch)?;
    let (cfg, m) = configured(&c, &s)?;
    ds::key_metadata(&cfg.key_file)?;
    plan.validate(true)?;
    let paused: String = c.query_row("SELECT value FROM meta WHERE key='paused'", [], |r| {
        r.get(0)
    })?;
    ensure(paused != "true", "OWNER_PAUSED")?;
    let n: i64 = c.query_row(
        "SELECT count(*) FROM calls c JOIN tasks t ON t.id=c.task_id WHERE t.trigger_key=?1",
        [ctx.trigger()],
        |r| r.get(0),
    )?;
    ensure(n == 0, "FUSION_SINGLE_ATTEMPT_ALREADY_RECORDED")?;
    let request = body(&m, &ctx, &plan.frozen, &bundle)?;
    let maximum = m.cost(m.max_input_tokens, m.max_output_tokens)?;
    let budget = crate::budget::view(&c, s.budget.as_ref(), Utc::now())?;
    for k in ["daily_remaining_micro", "monthly_remaining_micro"] {
        ensure(
            budget[k]
                .as_str()
                .and_then(|s| s.parse::<i64>().ok())
                .is_some_and(|n| n >= maximum),
            "FUSION_BUDGET_EXHAUSTED",
        )?;
    }
    Ok(
        json!({"state":"PREFLIGHT_READY","model_alias":ds::ID,"model_id":MODEL_ID,"api_model":ds::MODEL,"receiver":ds::ENDPOINT,
        "purpose":"portfolio_fusion_v1","grant_version":GRANT,"payload":"synthetic 5/20 RMS + Naive/EWMA + UNKNOWN + source SHA + JSON contract",
        "request_sha256":rp::sha(&request),"request_bytes":request.to_string().len(),"maximum_micro":maximum,"currency":"CNY",
        "price_version":ds::PRICE_VERSION,"budget":budget,"context":ctx,"key_content_read":false,"network_calls":0,
        "paper_allowed":false,"live_allowed":false}),
    )
}
pub fn enable(batch: &str) -> Result<Value> {
    let view = preflight(batch)?;
    let (b, _) = connection()?;
    let a = Agent::open(&b.agent_dir, Some(&b.settings_path), blank())?;
    let ctx: Context =
        serde_json::from_value(view["context"].clone()).map_err(|_| "FUSION_CONTEXT_INVALID")?;
    set(
        &a.store().connect()?,
        PERMIT,
        &json!({"enabled":true,"trigger":ctx.trigger(),"context_sha256":rp::sha(&serde_json::to_value(&ctx).unwrap())}),
    )?;
    Ok(
        json!({"state":"ONE_SYNTHETIC_FUSION_ENABLED","automatic_research":false,"key_content_read":false}),
    )
}
pub fn disable() -> Result<Value> {
    let b = binding::read()?;
    let c = Connection::open_with_flags(
        b.agent_dir.join("agent.sqlite"),
        OpenFlags::SQLITE_OPEN_READ_WRITE,
    )?;
    b.verify(&c)?;
    c.busy_timeout(std::time::Duration::from_secs(5))?;
    c.execute_batch("PRAGMA synchronous=FULL; BEGIN IMMEDIATE")?;
    set(&c, PERMIT, &json!({"enabled":false}))?;
    c.execute_batch("COMMIT")?;
    Ok(json!({"state":"OFF","unknown_reservations":"PRESERVED","in_flight":"MAY_HAVE_BEEN_SENT"}))
}
pub fn execute(batch: &str, queue_only: bool) -> Result<Value> {
    let b = binding::read()?;
    let a = Agent::open(&b.agent_dir, Some(&b.settings_path), blank())?;
    let s = Settings::load(&b.settings_path)?;
    let c = a.store().connect()?;
    let (ctx, plan, _) = make_context(&c, &s, batch)?;
    let trigger = ctx.trigger();
    let prior: Option<i64> = c
        .query_row(
            "SELECT id FROM tasks WHERE trigger_key=?1",
            [&trigger],
            |r| r.get(0),
        )
        .optional()?;
    let id = if let Some(id) = prior {
        id
    } else {
        let i = ctx.input(&plan.frozen);
        gate(&c, Some(&trigger), &i, &s)?;
        let m = s.models.iter().find(|m| m.id == MODEL_ID).unwrap();
        save_model(&ctx, m)?;
        let req = TaskRequest {
            name: format!("Local TimesFM Fusion {batch}"),
            goal: "Synthetic risk to research portfolio".into(),
            scope: POLICY.into(),
            start_day: i.source_day.clone(),
            end_day: i.source_day.clone(),
            task_budget_micro: Some(m.cost(m.max_input_tokens, m.max_output_tokens)?.to_string()),
        };
        a.store()
            .create_for_model(&s, &req, &i, Utc::now(), Some(&trigger), MODEL_ID)?
    };
    if !queue_only && a.store().task(id)?["status"] == "queued" {
        a.tick_task(Utc::now(), id, &trigger)?;
    }
    a.store().task(id)
}
pub struct Prepared {
    model: Model,
    ctx: Context,
    plan: cpu::Plan,
    parent: Value,
    body: Value,
    key: Zeroizing<String>,
    https: (reqwest::blocking::Client, reqwest::Url),
}
pub fn prepare(m: &Model, input: &Value) -> Result<Prepared> {
    let i: InputSummary = serde_json::from_value(input["published_summary"].clone())
        .map_err(|_| "FUSION_INPUT_CHANGED")?;
    let ctx = context(&i)?;
    let (b, c) = connection()?;
    let s = Settings::load(&b.settings_path)?;
    gate(&c, Some(&ctx.trigger()), &i, &s)?;
    let (cfg, _) = configured(&c, &s)?;
    frozen_model(&ctx)?;
    let (plan, parent) = parent(&c, &ctx, true)?;
    let body = body(m, &ctx, &plan.frozen, &parent)?;
    let key = ds::read_key_file(&cfg.key_file)?;
    ensure(
        !body.to_string().contains(key.as_str()),
        "DEEPSEEK_SECRET_IN_REQUEST_DENIED",
    )?;
    #[cfg(test)]
    let https = crate::local_fusion_tests::transport(&ctx)?;
    #[cfg(not(test))]
    let https = provider::https_client(m)?;
    Ok(Prepared {
        model: m.clone(),
        ctx,
        plan,
        parent,
        body,
        key,
        https,
    })
}
fn usage(v: &Value, m: &Model) -> Result<(u32, u32)> {
    let i = v["usage"]["prompt_tokens"]
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or("DEEPSEEK_USAGE")?;
    let o = v["usage"]["completion_tokens"]
        .as_u64()
        .and_then(|n| u32::try_from(n).ok())
        .ok_or("DEEPSEEK_USAGE")?;
    ensure(
        i > 0
            && o > 0
            && i <= m.max_input_tokens
            && o <= m.max_output_tokens
            && v["usage"]["total_tokens"] == u64::from(i) + u64::from(o),
        "DEEPSEEK_USAGE_BOUND",
    )?;
    Ok((i, o))
}
pub fn decode(
    m: &Model,
    ctx: &Context,
    f: &rp::Frozen,
    parent: &Value,
    request_sha: &str,
    bytes: &[u8],
) -> Result<(Value, u32, u32)> {
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
            && choices[0]["message"]["function_call"].is_null()
            && choices[0]["message"]["reasoning_content"]
                .as_str()
                .is_none_or(|s| s.is_empty()),
        "DEEPSEEK_RESPONSE_PROTOCOL",
    )?;
    let (i, o) = usage(&v, m)?;
    let content = choices[0]["message"]["content"]
        .as_str()
        .ok_or("PORTFOLIO_JSON")?;
    let researcher = ctx.adapter_sha256 == code_sha();
    let (portfolio, annotations) = if researcher {
        let response: crate::fusion_researcher::Response =
            serde_json::from_str(content).map_err(|_| "PORTFOLIO_SCHEMA")?;
        crate::fusion_researcher::validate_response(&response)?;
        (
            response.portfolio,
            Some((response.conclusions, response.untrusted_hypothesis)),
        )
    } else {
        let portfolio: rp::Portfolio =
            serde_json::from_str(content).map_err(|_| "PORTFOLIO_SCHEMA")?;
        if ctx.adapter_sha256 == PR78_R1_ADAPTER_SHA {
            crate::fusion_researcher::validate_legacy_portfolio(&portfolio)?;
        }
        (portfolio, None)
    };
    portfolio.bind(f, &[f.snapshot_ref.clone(), f.strategy_hash()])?;
    let mut result = rp::safe();
    result["paper_allowed"] = json!(false);
    result["portfolio"] = serde_json::to_value(&portfolio).unwrap();
    if let Some((conclusions, hypothesis)) = annotations {
        result["conclusions"] = conclusions;
        result["untrusted_hypothesis"] = serde_json::to_value(hypothesis).unwrap();
    }
    result["strategy_artifact_sha256"] = json!(rp::sha(&result["portfolio"]));
    result["risk_evidence_sha256"] = json!(rp::sha(parent));
    result["discovery"]=json!(portfolio.candidate_instruments.iter().filter(|id|!f.series.iter().any(|s|s.instrument==**id))
        .map(|id|json!({"instrument":id,"status":"DISCOVERY_UNVERIFIED","execution_candidate":false})).collect::<Vec<_>>());
    let safe_id = |v: &Value| {
        v.as_str()
            .filter(|s| {
                !s.is_empty()
                    && s.len() <= 128
                    && s.bytes()
                        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
            })
            .map(String::from)
    };
    result["receipt"] = json!({"contract":POLICY,"transport":if cfg!(test){"test_loopback"}else{"https"},"verification":if cfg!(test){"TEST_LOOPBACK_NOT_REAL_PROVIDER"}else{"REAL_PROVIDER_CALL_OBSERVED"},"model_alias":ds::ID,
        "model_id":m.id,"model":m.model,"response_model":v["model"],"provider_request_id":safe_id(&v["id"]),
        "system_fingerprint":safe_id(&v["system_fingerprint"]),"provider_hash":m.fingerprint(),"adapter_sha256":ctx.adapter_sha256,
        "request_sha256":request_sha,"raw_result_sha256":hash(bytes),"local_parent_result_sha256":ctx.parent_result_sha256,
        "local_parent_task_id":ctx.parent_task_id,"frozen_input_sha256":rp::sha(&serde_json::to_value(f).unwrap()),"content":content,
        "input_tokens":i,"output_tokens":o,"maximum_reserved_micro":m.cost(m.max_input_tokens,m.max_output_tokens)?,
        "usage_estimate_micro":m.cost(i,o)?,"price_version":m.price.as_ref().ok_or("PRICE_UNCONFIGURED")?.version,
        "billing":"USAGE_ESTIMATE_MAXIMUM_HELD_UNTIL_OWNER_INVOICE_RECONCILIATION","actual_bill_micro":null,"currency":"CNY"});
    if researcher || ctx.adapter_sha256 == PR78_R1_ADAPTER_SHA {
        result["receipt"]["prompt_version"] = json!(crate::fusion_researcher::VERSION);
        result["receipt"]["prompt_sha256"] = json!(if researcher {
            crate::fusion_researcher::prompt_sha()
        } else {
            crate::fusion_researcher::legacy_prompt_sha()
        });
        result["receipt"]["narrative_authority"] = json!("UNTRUSTED_HYPOTHESIS_NOT_EVIDENCE");
    }
    rp::validate_output(&result)?;
    Ok((result, i, o))
}
fn wire_path(batch: &str) -> Result<std::path::PathBuf> {
    ensure(crate::eod_snapshot::valid_name(batch), "LOCAL_BATCH_NAME")?;
    let path = rp::root()?.join(batch).join("local-fusion-wire.json");
    crate::eod_snapshot::no_links(&path)?;
    Ok(path)
}
fn save_wire(batch: &str, bytes: &[u8]) -> Result<()> {
    ensure(bytes.len() <= 65536, "DEEPSEEK_RESPONSE_SIZE")?;
    let path = wire_path(batch)?;
    fs::create_dir_all(path.parent().unwrap()).map_err(|_| "FUSION_WIRE_AUDIT_WRITE_FAILED")?;
    let mut opts = fs::OpenOptions::new();
    opts.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600);
    }
    let mut file = opts
        .open(path)
        .map_err(|_| "FUSION_WIRE_AUDIT_WRITE_FAILED")?;
    file.write_all(bytes)
        .map_err(|_| "FUSION_WIRE_AUDIT_WRITE_FAILED")?;
    file.sync_all()
        .map_err(|_| crate::Error("FUSION_WIRE_AUDIT_WRITE_FAILED".into()))
}
pub fn call(p: Prepared) -> provider::Outcome {
    let started = Instant::now();
    let request_sha = rp::sha(&p.body);
    let failure = |reason: String, bytes: Option<&[u8]>| {
        let v = bytes.and_then(|b| serde_json::from_slice::<Value>(b).ok());
        let u = v.as_ref().and_then(|v| usage(v, &p.model).ok());
        provider::Outcome::CloudFailure {
            reason: reason.clone(),
            receipt: json!({"contract":POLICY,"state":"OUTCOME_UNCERTAIN",
            "error_code":reason,"request_sha256":request_sha,
            "response_model":v.as_ref().and_then(|v|v["model"].as_str()).filter(|s|*s==ds::MODEL),
            "provider_request_id":v.as_ref().and_then(|v|v["id"].as_str()).filter(|s|!s.is_empty()&&s.len()<=128&&s.bytes().all(|b|b.is_ascii_alphanumeric()||matches!(b,b'-'|b'_'))),"raw_result_sha256":bytes.map(hash),
            "input_tokens":u.map(|u|u.0),"output_tokens":u.map(|u|u.1),"usage_estimate_micro":u.and_then(|(i,o)|p.model.cost(i,o).ok()),
            "billing":"UNKNOWN_MAXIMUM_HELD","retry_allowed":false,"http_error_body":"NOT_STORED_OR_LOGGED","synthetic_response_audit":"PRIVATE_LOCAL_ONLY_IF_PRESENT"}),
        }
    };
    let response = match p
        .https
        .0
        .post(p.https.1.clone())
        .bearer_auth(p.key.as_str())
        .json(&p.body)
        .send()
    {
        Ok(r) => r,
        Err(_) => return failure("OUTCOME_UNCERTAIN_TRANSPORT".into(), None),
    };
    if !response.status().is_success() {
        return failure(
            format!("OUTCOME_UNCERTAIN_HTTP_{}", response.status().as_u16()),
            None,
        );
    }
    let mut bytes = Vec::new();
    if response.take(65537).read_to_end(&mut bytes).is_err() {
        return failure("OUTCOME_UNCERTAIN_BODY_INTERRUPTED".into(), None);
    }
    if bytes.windows(p.key.len()).any(|s| s == p.key.as_bytes()) {
        return failure("DEEPSEEK_SECRET_ECHO_DENIED".into(), None);
    }
    if let Err(e) = save_wire(&p.ctx.batch, &bytes) {
        return failure(e.0, Some(&bytes));
    }
    let (mut result, input_tokens, output_tokens) = match decode(
        &p.model,
        &p.ctx,
        &p.plan.frozen,
        &p.parent,
        &request_sha,
        &bytes,
    ) {
        Ok(v) => v,
        Err(e) => return failure(e.0, Some(&bytes)),
    };
    result["receipt"]["latency_ms"] = json!(started.elapsed().as_millis() as u64);
    provider::Outcome::Success {
        research: Research {
            hypothesis: result["portfolio"]["strategy_definition"]
                .as_str()
                .unwrap()
                .into(),
            evidence: vec![format!(
                "Verified local parent SHA {}",
                p.ctx.parent_result_sha256
            )],
            risks: vec!["SYNTHETIC_ENGINEERING_ONLY; UNKNOWN_UNCALIBRATED".into()],
            next_steps: vec!["Independent research review; Paper/Live BLOCKED".into()],
            fusion: None,
            risk_portfolio: Some(result),
            structured_research: None,
        },
        input_tokens,
        output_tokens,
    }
}
fn model_snapshot_path(batch: &str) -> Result<std::path::PathBuf> {
    ensure(crate::eod_snapshot::valid_name(batch), "LOCAL_BATCH_NAME")?;
    let path = rp::root()?.join(batch).join("local-fusion-model.json");
    crate::eod_snapshot::no_links(&path)?;
    Ok(path)
}
fn frozen_model(ctx: &Context) -> Result<Model> {
    let path = model_snapshot_path(&ctx.batch)?;
    ensure(path.is_file(), "FUSION_HISTORICAL_MODEL_SNAPSHOT_REQUIRED")?;
    let m: Model = serde_json::from_value(rp::read(&path, 32768)?)
        .map_err(|_| "FUSION_FROZEN_MODEL_INVALID")?;
    validate_model(&m)?;
    ensure(
        m.fingerprint() == ctx.model_sha256,
        "FUSION_FROZEN_MODEL_CHANGED",
    )?;
    Ok(m)
}
fn save_model(ctx: &Context, m: &Model) -> Result<()> {
    ensure(
        m.fingerprint() == ctx.model_sha256,
        "FUSION_ORIGINAL_MODEL_UNAVAILABLE",
    )?;
    let path = model_snapshot_path(&ctx.batch)?;
    if path.exists() {
        frozen_model(ctx)?;
        return Ok(());
    }
    fs::create_dir_all(path.parent().unwrap()).map_err(|_| "FUSION_MODEL_SNAPSHOT_WRITE")?;
    let mut opts = fs::OpenOptions::new();
    opts.create_new(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600);
    }
    let mut file = opts.open(path).map_err(|_| "FUSION_MODEL_SNAPSHOT_WRITE")?;
    file.write_all(&serde_json::to_vec_pretty(m).unwrap())
        .map_err(|_| "FUSION_MODEL_SNAPSHOT_WRITE")?;
    file.sync_all()
        .map_err(|_| crate::Error("FUSION_MODEL_SNAPSHOT_WRITE".into()))
}
fn task_for_batch(c: &Connection, batch: &str) -> Result<Option<i64>> {
    ensure(crate::eod_snapshot::valid_name(batch), "LOCAL_BATCH_NAME")?;
    Ok(c.query_row("SELECT id FROM tasks WHERE trigger_key LIKE ?1 AND json_extract(input,'$.summary.batch')=?2",
        params![format!("{POLICY}:%"),batch],|r|r.get(0)).optional()?)
}
/// Explicit recovery only when the available Model is byte-for-byte the one
/// pinned by the original task fingerprint. Never edits tasks/results/calls.
pub fn capture_model(batch: &str) -> Result<Value> {
    let (b, c) = connection()?;
    let id = task_for_batch(&c, batch)?.ok_or("FUSION_TASK_MISSING")?;
    let (raw, pin, pid, trigger): (String, String, String, String) = c.query_row(
        "SELECT input,provider_hash,provider_id,trigger_key FROM tasks WHERE id=?1",
        [id],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
    )?;
    let i: InputSummary = serde_json::from_str(&raw).map_err(|_| "FUSION_INPUT_CHANGED")?;
    let ctx: Context =
        serde_json::from_value(i.summary.clone()).map_err(|_| "FUSION_CONTEXT_INVALID")?;
    let (plan, _) = parent(&c, &ctx, false)?;
    ensure(
        ctx.policy == POLICY
            && ctx.batch == batch
            && pid == MODEL_ID
            && pin == ctx.model_sha256
            && trigger == ctx.trigger()
            && serde_json::to_value(&i).unwrap()
                == serde_json::to_value(ctx.input(&plan.frozen)).unwrap(),
        "FUSION_INPUT_CHANGED",
    )?;
    if model_snapshot_path(batch)?.exists() {
        frozen_model(&ctx)?;
    } else {
        let s = Settings::load(&b.settings_path)?;
        let m = s
            .models
            .iter()
            .find(|m| m.id == MODEL_ID && m.fingerprint() == pin)
            .ok_or("FUSION_ORIGINAL_MODEL_UNAVAILABLE")?;
        save_model(&ctx, m)?;
    }
    Ok(
        json!({"state":"ORIGINAL_PINNED_MODEL_PRESERVED","task_id":id,"model_sha256":pin,
        "evidence":"EXACT_ORIGINAL_TASK_FINGERPRINT","database_mutated":false,"key_content_read":false,"network_calls":0}),
    )
}
pub fn inspect(batch: &str, verify: bool) -> Result<Value> {
    let (binding, c) = connection()?;
    let Some(id) = task_for_batch(&c, batch)? else {
        let s = Settings::load(&binding.settings_path)?;
        let (ctx, plan, _) = make_context(&c, &s, batch)?;
        return Ok(json!({"state":"LOCAL_PARENT_READY","context":ctx,"frozen":plan.frozen}));
    };
    let (status, raw, saved_input, trigger): (String, Option<String>, String, String) = c
        .query_row(
            "SELECT status,result,input,trigger_key FROM tasks WHERE id=?1",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )?;
    let saved: InputSummary =
        serde_json::from_str(&saved_input).map_err(|_| "FUSION_INPUT_CHANGED")?;
    let ctx: Context =
        serde_json::from_value(saved.summary.clone()).map_err(|_| "FUSION_CONTEXT_INVALID")?;
    let (plan, parent) = parent(&c, &ctx, false)?;
    ensure(
        ctx.policy == POLICY
            && ctx.batch == batch
            && trigger == ctx.trigger()
            && serde_json::to_value(&saved).unwrap()
                == serde_json::to_value(ctx.input(&plan.frozen)).unwrap(),
        "FUSION_INPUT_CHANGED",
    )?;
    let result = raw
        .as_ref()
        .map(|s| serde_json::from_str::<Value>(s).map_err(|_| "FUSION_RESULT_CHANGED"))
        .transpose()?;
    if verify {
        ensure(status == "completed", "FUSION_TASK_INCOMPLETE")?;
        ensure(
            ctx.adapter_sha256 == code_sha()
                || ctx.adapter_sha256 == PRE_SNAPSHOT_ADAPTER_SHA
                || ctx.adapter_sha256 == PR19_CODE_SHA
                || ctx.adapter_sha256 == LEGACY_ROLE_ADAPTER_SHA
                || ctx.adapter_sha256 == PR78_R1_ADAPTER_SHA,
            "FUSION_ADAPTER_CHANGED_NEW_TASK_REQUIRED",
        )?;
        let (input, pid, pin): (String, String, String) = c.query_row(
            "SELECT input,provider_id,provider_hash FROM tasks WHERE id=?1",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )?;
        let i: InputSummary = serde_json::from_str(&input).map_err(|_| "FUSION_INPUT_CHANGED")?;
        ensure(
            serde_json::to_value(&i).unwrap()
                == serde_json::to_value(ctx.input(&plan.frozen)).unwrap()
                && pid == MODEL_ID
                && pin == ctx.model_sha256,
            "FUSION_INPUT_CHANGED",
        )?;
        let bundle = &result.as_ref().ok_or("FUSION_RESULT_CHANGED")?["research"]["risk_portfolio"];
        let receipt = &bundle["receipt"];
        let m = frozen_model(&ctx)?;
        let request = body(&m, &ctx, &plan.frozen, &parent)?;
        let path = wire_path(batch)?;
        ensure(
            fs::metadata(&path).is_ok_and(|m| m.is_file() && m.len() <= 65536),
            "FUSION_WIRE_AUDIT_MISSING",
        )?;
        let wire = fs::read(path).map_err(|_| "FUSION_WIRE_AUDIT_MISSING")?;
        ensure(
            receipt["raw_result_sha256"] == hash(&wire),
            "FUSION_WIRE_AUDIT_CHANGED",
        )?;
        let (mut rebuilt, _, _) =
            decode(&m, &ctx, &plan.frozen, &parent, &rp::sha(&request), &wire)?;
        rebuilt["receipt"]["latency_ms"] = receipt["latency_ms"].clone();
        ensure(rebuilt == *bundle, "FUSION_RESULT_CHANGED")?;
        let (n,valid):(i64,i64)=c.query_row("SELECT count(*),sum(state IN ('usage_received','settled') AND input_tokens=?2 AND output_tokens=?3 AND maximum_micro=?4 AND usage_micro=?5 AND price_version=?6) FROM calls WHERE task_id=?1",
            params![id,receipt["input_tokens"].as_i64(),receipt["output_tokens"].as_i64(),receipt["maximum_reserved_micro"].as_i64(),receipt["usage_estimate_micro"].as_i64(),m.price.as_ref().ok_or("PRICE_UNCONFIGURED")?.version],
            |r|Ok((r.get(0)?,r.get(1)?)))?;
        ensure(n == 1 && valid == 1, "FUSION_CALL_CHANGED")?;
    }
    Ok(
        json!({"state":status,"task_id":id,"context":ctx,"frozen":plan.frozen,"local_risk":parent,"result":result,
        "conclusion_contract":if ctx.adapter_sha256 == code_sha() {crate::fusion_researcher::CONTRACT} else {"LEGACY_UNTRUSTED_HYPOTHESIS_NOT_REQUALIFIED"},
        "result_storage_sha256":raw.map(|s|hash(s.as_bytes())),"verified":verify,"paper_allowed":false,"live_allowed":false}),
    )
}
pub fn budget_status() -> Result<Value> {
    let (b, c) = connection()?;
    let s = Settings::load(&b.settings_path)?;
    let mut v = crate::budget::view(&c, s.budget.as_ref(), Utc::now())?;
    let mut q=c.prepare("SELECT c.id,c.task_id,t.provider_id,json_extract(t.result,'$.model'),c.state,c.maximum_micro,c.usage_micro,c.input_tokens,c.output_tokens FROM tasks t JOIN calls c ON c.task_id=t.id ORDER BY c.id DESC LIMIT 10")?;
    let recent=q.query_map([],|r|Ok(json!({"id":r.get::<_,i64>(0)?,"task_id":r.get::<_,i64>(1)?,"model_id":r.get::<_,String>(2)?,
        "api_model":r.get::<_,Option<String>>(3)?,"state":r.get::<_,String>(4)?,"maximum_micro":r.get::<_,i64>(5)?,
        "usage_estimate_micro":r.get::<_,Option<i64>>(6)?,"input_tokens":r.get::<_,Option<i64>>(7)?,"output_tokens":r.get::<_,Option<i64>>(8)?})))?
        .collect::<std::result::Result<Vec<_>,_>>()?;
    let estimates:(i64,i64)=c.query_row(
        "SELECT COALESCE(SUM(CASE WHEN day=?1 THEN usage_micro ELSE 0 END),0),COALESCE(SUM(CASE WHEN month=?2 THEN usage_micro ELSE 0 END),0) FROM calls",
        params![v["day"].as_str(),v["month"].as_str()],|r|Ok((r.get(0)?,r.get(1)?)))?;
    v["daily_usage_estimate_micro"] = json!(estimates.0.to_string());
    v["monthly_usage_estimate_micro"] = json!(estimates.1.to_string());
    v["recent_calls"] = json!(recent);
    Ok(v)
}
