//! New, versioned research contract. Never an order or an execution candidate.
use crate::{config::Settings, ensure, hash, InputSummary, Result};
use chrono::{DateTime, Datelike, Duration, NaiveDate, Utc};
use rusqlite::{Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{collections::BTreeSet, fs, path::PathBuf};

pub const SCOPE: &str = "risk_portfolio_v1";
pub const POLICY: &str = "risk-portfolio-v1";
pub const SCOPES: [&str; 3] = [SCOPE, "risk_timeseries_v1", "portfolio_fusion_v1"];
pub const AUTHORITY: &str = "RESEARCH_ONLY";
pub const PROMPT: &str = "portfolio-json-v1";
pub fn adapter_sha() -> String {
    hash(
        concat!(
            include_str!("risk_cloud.rs"),
            include_str!("risk_portfolio.rs"),
            include_str!("risk_binding.rs")
        )
        .as_bytes(),
    )
}
pub fn prompt_sha() -> String {
    hash(crate::risk_cloud::PORTFOLIO_SYSTEM.as_bytes())
}

pub fn root() -> Result<PathBuf> {
    let out = std::process::Command::new("git")
        .args(["rev-parse", "--path-format=absolute", "--git-common-dir"])
        .env_remove("GIT_DIR")
        .env_remove("GIT_WORK_TREE")
        .env_remove("GIT_COMMON_DIR")
        .current_dir(crate::eod_snapshot::repository_root())
        .output()
        .map_err(|_| "CLOUD_STATE_ROOT")?;
    ensure(out.status.success(), "CLOUD_STATE_ROOT")?;
    let git = PathBuf::from(
        String::from_utf8(out.stdout)
            .map_err(|_| "CLOUD_STATE_ROOT")?
            .trim(),
    );
    Ok(git
        .parent()
        .ok_or("CLOUD_STATE_ROOT")?
        .join("state/risk-portfolio"))
}
pub fn agent_dir() -> Result<PathBuf> {
    Ok(crate::risk_binding::read()?.agent_dir)
}
pub fn settings_path() -> Result<PathBuf> {
    Ok(crate::risk_binding::read()?.settings_path)
}
pub fn is_input(i: &InputSummary) -> bool {
    i.scopes.iter().any(|s| SCOPES.contains(&s.as_str()))
}
pub fn sha(v: &Value) -> String {
    hash(&serde_json::to_vec(v).expect("JSON value"))
}
pub fn valid_sha(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
pub fn instrument(s: &str) -> bool {
    s.len() == 9
        && s.as_bytes()[..6].iter().all(u8::is_ascii_digit)
        && matches!(&s[6..], ".SH" | ".SZ" | ".BJ")
}
pub fn text(s: &str, max: usize) -> bool {
    let l = s.to_ascii_lowercase();
    !s.trim().is_empty()
        && s.len() <= max
        && !s.chars().any(char::is_control)
        && ![
            "http:",
            "https:",
            "file:",
            "$(",
            "`",
            "powershell",
            "cmd.exe",
            "python ",
            "import ",
            "exec(",
            "eval(",
            "../",
            "\\",
            "#!/",
        ]
        .iter()
        .any(|x| l.contains(x))
}
pub fn read(path: &std::path::Path, max: u64) -> Result<Value> {
    crate::eod_snapshot::no_links(path)?;
    ensure(
        fs::metadata(path).is_ok_and(|m| m.is_file() && m.len() <= max),
        "RISK_FILE_MISSING_OR_SIZE",
    )?;
    serde_json::from_slice(&fs::read(path).map_err(|_| "RISK_FILE_READ")?)
        .map_err(|_| "RISK_JSON_INVALID".into())
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub trade_day: String,
    pub available_at: String,
    pub close_fen: i64,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Series {
    pub instrument: String,
    pub observations: Vec<Observation>,
    pub corporate_actions: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Pin {
    pub id: String,
    pub fingerprint: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Opportunity {
    pub instrument: String,
    pub status: String,
    pub evidence: Vec<String>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Frozen {
    pub schema_version: u32,
    pub scope: String,
    pub policy: String,
    pub input_mode: String,
    pub snapshot_ref: String,
    pub readiness_ref: String,
    pub as_of: String,
    pub strategy_version: String,
    pub prompt_version: String,
    pub prompt_sha256: String,
    pub adapter_sha256: String,
    pub calendar: Vec<String>,
    pub calendar_provenance: String,
    pub series: Vec<Series>,
    pub opportunities: Vec<Opportunity>,
    pub account_facts: String,
    pub risk_model: Pin,
    pub fusion_model: Pin,
    pub batch_budget_micro: i64,
    pub risk_recording_sha256: String,
    pub fusion_recording_sha256: String,
}
impl Frozen {
    pub fn validate(&self, now: DateTime<Utc>) -> Result<()> {
        ensure(
            self.schema_version == 1
                && self.scope == SCOPE
                && self.policy == POLICY
                && self.prompt_version == PROMPT,
            "RISK_INPUT_SCHEMA",
        )?;
        ensure(
            self.prompt_sha256 == prompt_sha() && self.adapter_sha256 == adapter_sha(),
            "PROMPT_OR_ADAPTER_CHANGED_NEW_TASK_REQUIRED",
        )?;
        // A claimed receipt in arbitrary JSON cannot certify real PIT/forward data.
        // The current PR54 real source is BLOCKED. No historical/synthetic splice.
        ensure(
            self.input_mode == "synthetic_test"
                && self.readiness_ref == "SYNTHETIC_ENGINEERING_ONLY"
                && self.calendar_provenance == "SYNTHETIC_EXCHANGE_SESSION_FIXTURE",
            "REAL_READINESS_BLOCKED",
        )?;
        ensure(
            valid_sha(&self.snapshot_ref)
                && text(&self.strategy_version, 64)
                && self.account_facts == "UNKNOWN_NO_ACCOUNT_ORDERS"
                && (1..=1_000_000_000_000).contains(&self.batch_budget_micro),
            "RISK_INPUT_IDENTITY",
        )?;
        ensure(
            self.snapshot_ref == sha(&json!({"series":self.series,"calendar":self.calendar})),
            "SNAPSHOT_INPUT_SHA_MISMATCH",
        )?;
        let at = self
            .as_of
            .parse::<DateTime<Utc>>()
            .map_err(|_| "RISK_AS_OF")?;
        ensure(
            at <= now && now - at < Duration::hours(24),
            "FUTURE_OR_STALE_SNAPSHOT",
        )?;
        ensure(
            (1..=8).contains(&self.series.len()) && (104..=256).contains(&self.calendar.len()),
            "RISK_INPUT_SIZE",
        )?;
        let mut dates = Vec::new();
        for d in &self.calendar {
            let day = crate::parse_day(d)?;
            ensure(
                day.weekday().num_days_from_monday() < 5 && dates.last().is_none_or(|p| p < &day),
                "NON_TRADING_OR_UNORDERED_CALENDAR",
            )?;
            dates.push(day);
        }
        let mut names = BTreeSet::new();
        for s in &self.series {
            ensure(
                instrument(&s.instrument)
                    && names.insert(&s.instrument)
                    && s.corporate_actions == "SYNTHETIC_NONE_VERIFIED",
                "SERIES_IDENTITY_OR_CORPORATE_ACTION",
            )?;
            // 84 closes -> 83 returns -> 64 rolling-20 RMS observations.
            ensure(
                (84..=192).contains(&s.observations.len()),
                "INSUFFICIENT_MODEL_CONTEXT",
            )?;
            ensure(
                self.calendar.len() == s.observations.len() + 20,
                "MODEL_HORIZON_CALENDAR",
            )?;
            for (o, d) in s.observations.iter().zip(&self.calendar) {
                let available = o
                    .available_at
                    .parse::<DateTime<Utc>>()
                    .map_err(|_| "OBSERVATION_AVAILABILITY")?;
                ensure(
                    o.trade_day == *d
                        && (1..=1_000_000_000).contains(&o.close_fen)
                        && available <= at
                        && available.date_naive() >= crate::parse_day(d)?,
                    "BAD_OR_FUTURE_OBSERVATION",
                )?;
            }
            let last = crate::parse_day(&s.observations.last().unwrap().trade_day)?;
            let decision_day = at.with_timezone(&chrono_tz::Asia::Shanghai).date_naive();
            ensure(
                last <= decision_day && (decision_day - last).num_days() <= 3,
                "SNAPSHOT_SOURCE_DAY_MISMATCH",
            )?;
            ensure(
                s.observations
                    .windows(2)
                    .all(|o| (o[1].close_fen as f64 / o[0].close_fen as f64 - 1.).abs() <= 0.35),
                "RETURN_UNITS_OR_ACTION_GAP",
            )?;
        }
        ensure(
            self.opportunities.len() == self.series.len(),
            "OPPORTUNITY_EVIDENCE_MISSING",
        )?;
        let mut opportunities = BTreeSet::new();
        for o in &self.opportunities {
            ensure(
                names.contains(&o.instrument)
                    && opportunities.insert(&o.instrument)
                    && matches!(o.status.as_str(), "UNKNOWN" | "VERIFIED_SYNTHETIC")
                    && o.evidence.len() <= 6
                    && (o.status != "UNKNOWN" || o.evidence.is_empty())
                    && o.evidence.iter().all(|s| text(s, 256)),
                "OPPORTUNITY_SCHEMA",
            )?;
        }
        ensure(
            valid_sha(&self.risk_model.fingerprint)
                && valid_sha(&self.fusion_model.fingerprint)
                && valid_sha(&self.risk_recording_sha256)
                && valid_sha(&self.fusion_recording_sha256),
            "MODEL_PIN_REQUIRED",
        )
    }
    pub fn strategy_hash(&self) -> String {
        sha(
            &json!({"strategy_version":self.strategy_version,"prompt_version":self.prompt_version,
        "prompt_sha256":self.prompt_sha256,"adapter_sha256":self.adapter_sha256,"risk_model":self.risk_model,"fusion_model":self.fusion_model}),
        )
    }
    pub fn target_sessions(&self) -> &[String] {
        &self.calendar[self.series[0].observations.len()..]
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TaskInput {
    pub batch: String,
    pub frozen_sha256: String,
    pub phase: String,
    pub risk_task_id: Option<i64>,
    pub risk_result_sha256: Option<String>,
}
pub fn context(i: &InputSummary, now: DateTime<Utc>) -> Result<(TaskInput, Frozen)> {
    let t: TaskInput = serde_json::from_value(i.summary.clone()).map_err(|_| "RISK_TASK_SCHEMA")?;
    ensure(
        crate::eod_snapshot::valid_name(&t.batch)
            && valid_sha(&t.frozen_sha256)
            && matches!(t.phase.as_str(), "risk" | "fusion"),
        "RISK_TASK_IDENTITY",
    )?;
    let v = read(&root()?.join(&t.batch).join("frozen.json"), 256 * 1024)?;
    ensure(
        sha(&v) == t.frozen_sha256,
        "FROZEN_SOURCE_OR_RECEIPT_CHANGED",
    )?;
    let f: Frozen = serde_json::from_value(v).map_err(|_| "RISK_FROZEN_SCHEMA")?;
    f.validate(now)?;
    for (phase, expected) in [
        ("risk", &f.risk_recording_sha256),
        ("fusion", &f.fusion_recording_sha256),
    ] {
        let path = root()?
            .join(&t.batch)
            .join(format!("{phase}-recording.json"));
        crate::eod_snapshot::no_links(&path)?;
        ensure(
            fs::metadata(&path).is_ok_and(|m| m.is_file() && m.len() <= 65536),
            "RECORDING_SIZE",
        )?;
        ensure(
            hash(&fs::read(path).map_err(|_| "RECORDING_MISSING")?) == *expected,
            "OUTBOUND_RECEIPT_CHANGED_NEW_TASK_REQUIRED",
        )?;
    }
    ensure(
        i.version == format!("{SCOPE}:{}:{}", t.frozen_sha256, t.phase)
            && i.mode == f.input_mode
            && i.source_day == f.series[0].observations.last().unwrap().trade_day
            && !i.eod_eligible
            && i.scopes
                == [
                    SCOPE,
                    if t.phase == "risk" {
                        "risk_timeseries_v1"
                    } else {
                        "portfolio_fusion_v1"
                    },
                ],
        "RISK_SCOPE_BINDING",
    )?;
    ensure(
        (t.phase == "risk" && t.risk_task_id.is_none() && t.risk_result_sha256.is_none())
            || (t.phase == "fusion"
                && t.risk_task_id.is_some()
                && t.risk_result_sha256.as_deref().is_some_and(valid_sha)),
        "RISK_PARENT_REQUIRED",
    )?;
    Ok((t, f))
}
pub fn gate(
    c: &Connection,
    trigger: Option<&str>,
    i: &InputSummary,
    now: DateTime<Utc>,
    settings: &Settings,
) -> Result<()> {
    crate::risk_binding::read()?.verify(c)?;
    let (t, f) = context(i, now)?;
    ensure(
        trigger == Some(format!("{POLICY}:{}:{}:{}", t.batch, t.frozen_sha256, t.phase).as_str()),
        "RISK_TRIGGER_BINDING",
    )?;
    let enabled: Option<String> = c
        .query_row(
            "SELECT value FROM meta WHERE key='risk_portfolio_enabled'",
            [],
            |r| r.get(0),
        )
        .optional()?;
    ensure(
        enabled.as_deref() == Some("true"),
        "CLOUD_RESEARCH_DISABLED",
    )?;
    let owner: Option<String> = c
        .query_row(
            "SELECT value FROM meta WHERE key=?1",
            [format!("rp_batch_owner:{}", t.frozen_sha256)],
            |r| r.get(0),
        )
        .optional()?;
    ensure(
        owner.as_deref() == Some(t.batch.as_str()),
        "FROZEN_BATCH_OWNED_BY_ANOTHER_NAME",
    )?;
    let mut total = 0;
    for (pin, kind, scope) in [
        (&f.risk_model, "bigquery_forecast_v1", "risk_timeseries_v1"),
        (
            &f.fusion_model,
            "deepseek_portfolio_v1",
            "portfolio_fusion_v1",
        ),
    ] {
        let m = settings
            .models
            .iter()
            .find(|m| m.id == pin.id)
            .ok_or("PINNED_MODEL_UNAVAILABLE")?;
        ensure(
            m.fingerprint() == pin.fingerprint && m.kind == kind,
            "PINNED_MODEL_CONFIGURATION_CHANGED",
        )?;
        m.authorize(&[SCOPE.into(), scope.into()], settings.budget.as_ref())?;
        total += m.cost(m.max_input_tokens, m.max_output_tokens)?;
    }
    ensure(total <= f.batch_budget_micro, "BATCH_BUDGET_EXHAUSTED")?;
    if let Some(id) = t.risk_task_id {
        risk_parent(
            c,
            id,
            t.risk_result_sha256.as_deref().unwrap(),
            &t.frozen_sha256,
        )?;
    }
    Ok(())
}
pub fn risk_parent(c: &Connection, id: i64, expected: &str, frozen: &str) -> Result<Value> {
    let (status, input, result): (String, String, Option<String>) = c.query_row(
        "SELECT status,input,result FROM tasks WHERE id=?1",
        [id],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    )?;
    let input: Value = serde_json::from_str(&input).map_err(|_| "RISK_PARENT_INVALID")?;
    let encoded = result.ok_or("RISK_PARENT_MISSING")?;
    let result: Value = serde_json::from_str(&encoded).map_err(|_| "RISK_PARENT_INVALID")?;
    ensure(
        status == "completed"
            && input["summary"]["frozen_sha256"] == frozen
            && input["summary"]["phase"] == "risk"
            && hash(encoded.as_bytes()) == expected,
        "RISK_PARENT_CHANGED",
    )?;
    Ok(result["research"]["risk_portfolio"].clone())
}
pub fn baselines(f: &Frozen) -> Vec<Value> {
    f.series.iter().map(|s| {
        let r:Vec<f64>=s.observations.windows(2).map(|o| o[1].close_fen as f64/o[0].close_fen as f64-1.).collect();
        let rolling:Vec<f64>=r.windows(20).map(|w| (w.iter().map(|x|x*x).sum::<f64>()/20.).sqrt()).collect();
        let ewma=r.iter().skip(1).fold(r[0]*r[0],|v,x|0.94*v+0.06*x*x).sqrt();
        json!({"instrument":s.instrument,"unit":"daily_return_ratio","target":"rolling20_rms_daily_return_ratio",
            "window":20,"annualization":null,"naive":rolling.last().unwrap(),"ewma_lambda":0.94,"ewma":ewma,
            "observed_last_return":r.last().unwrap(),"observed_history_rms":(r.iter().map(|x|x*x).sum::<f64>()/r.len() as f64).sqrt(),
            "rolling_context":rolling,"missing":0,"action_handling":s.corporate_actions,"gap_detection":"VALIDATED_SESSION_SEQUENCE"})
    }).collect()
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Position {
    pub instrument: String,
    pub target_weight_bps: u32,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Portfolio {
    pub schema_version: u32,
    pub proposal_id: String,
    pub strategy_version: String,
    pub strategy_hash: String,
    pub strategy_definition: String,
    pub source_refs: Vec<String>,
    pub as_of: String,
    pub horizon: u32,
    pub candidate_instruments: Vec<String>,
    pub positions: Vec<Position>,
    pub cash_weight_bps: u32,
    pub rationale: String,
    pub evidence_for: Vec<String>,
    pub evidence_against: Vec<String>,
    pub risk_assessment: Vec<String>,
    pub invalidation_conditions: Vec<String>,
    pub next_experiment: Vec<String>,
    pub limitations: Vec<String>,
    pub estimated_turnover_bps: Option<u32>,
    pub estimated_fees_micro: Option<u64>,
    pub authority: String,
}
impl Portfolio {
    pub fn validate(&self) -> Result<()> {
        let mut ids = BTreeSet::new();
        let mut stocks = BTreeSet::new();
        ensure(
            self.schema_version == 1
                && text(&self.proposal_id, 80)
                && text(&self.strategy_version, 64)
                && valid_sha(&self.strategy_hash)
                && text(&self.strategy_definition, 1500)
                && (1..=20).contains(&self.horizon)
                && self.authority == AUTHORITY
                && self.source_refs.len() <= 8
                && !self.source_refs.is_empty()
                && self.source_refs.iter().all(|s| valid_sha(s))
                && self.candidate_instruments.len() <= 16
                && self
                    .candidate_instruments
                    .iter()
                    .all(|s| instrument(s) && ids.insert(s))
                && self.positions.len() <= 8
                && self.positions.iter().all(|p| {
                    instrument(&p.instrument)
                        && ids.contains(&p.instrument)
                        && stocks.insert(&p.instrument)
                        && p.target_weight_bps <= 10000
                })
                && self.cash_weight_bps <= 10000
                && self
                    .positions
                    .iter()
                    .map(|p| u64::from(p.target_weight_bps))
                    .sum::<u64>()
                    + u64::from(self.cash_weight_bps)
                    == 10000
                && self.estimated_turnover_bps.is_none()
                && self.estimated_fees_micro.is_none(),
            "TARGET_PORTFOLIO_INVALID",
        )?;
        ensure(
            text(&self.rationale, 2000)
                && [
                    &self.evidence_for,
                    &self.evidence_against,
                    &self.risk_assessment,
                    &self.invalidation_conditions,
                    &self.next_experiment,
                    &self.limitations,
                ]
                .iter()
                .all(|v| !v.is_empty() && v.len() <= 6 && v.iter().all(|s| text(s, 768))),
            "PORTFOLIO_TEXT_OR_CAPABILITY_REJECTED",
        )?;
        self.as_of
            .parse::<DateTime<Utc>>()
            .map_err(|_| "PORTFOLIO_AS_OF")?;
        Ok(())
    }
    pub fn bind(&self, f: &Frozen, source_refs: &[String]) -> Result<()> {
        self.validate()?;
        ensure(
            self.strategy_version == f.strategy_version
                && self.strategy_hash == f.strategy_hash()
                && self.source_refs == source_refs
                && self.as_of == f.as_of
                && self
                    .positions
                    .iter()
                    .all(|p| f.series.iter().any(|s| s.instrument == p.instrument)),
            "PORTFOLIO_SOURCE_OR_INSTRUMENT_UNVERIFIED",
        )
    }
}
pub fn validate_output(v: &Value) -> Result<()> {
    ensure(
        v["schema_version"] == 1
            && v["authority"] == AUTHORITY
            && v["eligibility"] == "ELIGIBILITY_DENIED"
            && v["can_execute_forward_paper"] == false
            && v["live_allowed"] == false,
        "RISK_OUTPUT_AUTHORITY",
    )?;
    if let Some(p) = v.get("portfolio") {
        serde_json::from_value::<Portfolio>(p.clone())
            .map_err(|_| "PORTFOLIO_SCHEMA")?
            .validate()?;
    }
    Ok(())
}
pub fn safe() -> Value {
    json!({"schema_version":1,"authority":AUTHORITY,"eligibility":"ELIGIBILITY_DENIED","can_execute_forward_paper":false,"live_allowed":false})
}
pub fn ordinal(index: usize) -> String {
    (NaiveDate::from_ymd_opt(2000, 1, 1).unwrap() + Duration::days(index as i64))
        .format("%Y-%m-%dT00:00:00Z")
        .to_string()
}
