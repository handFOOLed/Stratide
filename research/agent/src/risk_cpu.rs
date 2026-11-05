//! Explicit local non-billable research, using the original Agent tasks and Frozen V1.
//! Never scheduled by Agent::tick; never touches calls, cloud settings or trading.
use crate::{
    ensure, hash, risk_binding, risk_portfolio as rp, InputSummary, Result, Store, TaskRequest,
};
use chrono::Utc;
use rusqlite::{params, Connection, OpenFlags, OptionalExtension, TransactionBehavior};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

// Exact merged PR18 implementation; accepted only for read-only old synthetic receipts.
const PR18_CODE_SHA: &str = "26c92639fd78b143c4bd400988f447f29fcb52294319734555bae14efe669f2a";
pub const POLICY: &str = "timesfm-cpu-v1";
pub const REVISION: &str = "1d952420fba87f3c6dee4f240de0f1a0fbc790e3";
pub const WEIGHT_SHA: &str = "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8";
pub fn code_sha() -> String {
    hash(
        concat!(
            include_str!("risk_cpu.rs"),
            include_str!("../Cargo.toml"),
            include_str!("risk_history.rs"),
            include_str!("../../../research/timesfm_cpu/history.py"),
            include_str!("../../../research/historical_warehouse.py"),
            include_str!("../../../research/historical_sidecar.py"),
            include_str!("../../../research/timesfm_cpu/model.py"),
            include_str!("../../../research/timesfm_cpu/worker.py"),
            include_str!("../../../research/timesfm_cpu/runtime.py"),
            include_str!("../../../research/timesfm_cpu/cli.py"),
            include_str!("bin/timesfm-risk-agent.rs"),
            include_str!("../../../research/timesfm_cpu/requirements.lock")
        )
        .as_bytes(),
    )
}
pub fn descriptor() -> Value {
    json!({"policy":POLICY,"model":"google/timesfm-2.5-200m-pytorch","revision":REVISION,
        "weight_sha256":WEIGHT_SHA,"code_sha256":code_sha(),"adapter_sha256":rp::adapter_sha(),
        "prompt_sha256":rp::prompt_sha(),"billing":"LOCAL_NO_BILLING","paper_allowed":false,"live_allowed":false})
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub batch: String,
    pub frozen: rp::Frozen,
    pub manifest_sha256: String,
    pub code_sha256: String,
    pub max_context: usize,
    pub batch_size: usize,
    pub threads: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub history: Option<super::risk_history::History>,
}
impl Plan {
    pub fn validate(&self, fresh: bool) -> Result<()> {
        ensure(
            crate::eod_snapshot::valid_name(&self.batch)
                && rp::valid_sha(&self.manifest_sha256)
                && (self.code_sha256 == code_sha()
                    || (!fresh && self.history.is_none() && self.code_sha256 == PR18_CODE_SHA)),
            "LOCAL_PIN_CHANGED_NEW_TASK_REQUIRED",
        )?;
        if let Some(h) = &self.history {
            h.validate(&self.frozen, &self.code_sha256)?;
        } else {
            self.frozen.validate(if fresh {
                Utc::now()
            } else {
                self.frozen.as_of.parse().map_err(|_| "RISK_AS_OF")?
            })?;
        }
        ensure(
            matches!(self.max_context, 256 | 512)
                && (1..=4).contains(&self.batch_size)
                && (1..=4).contains(&self.threads),
            "LOCAL_CONFIG_BOUNDS",
        )
    }
    pub fn pin(&self) -> String {
        let mut pin = json!({"code":self.code_sha256,"manifest":self.manifest_sha256,
            "revision":REVISION,"weight":WEIGHT_SHA,"context":self.max_context,"batch":self.batch_size,"threads":self.threads});
        if let Some(h) = &self.history {
            pin["history_sha256"] = json!(h.payload_sha256);
        }
        rp::sha(&pin)
    }
    pub fn request(&self) -> Value {
        json!({"schema_version":1,"input_mode":self.frozen.input_mode,"horizon":20,"max_context":self.max_context,
            "batch_size":self.batch_size,"threads":self.threads,"repeats":1,
            "series":rp::baselines(&self.frozen).iter().map(|b|json!({"instrument":b["instrument"],"values":b["rolling_context"]})).collect::<Vec<_>>()})
    }
    pub fn input(&self) -> InputSummary {
        InputSummary {
            version: format!("{POLICY}:{}", rp::sha(&serde_json::to_value(self).unwrap())),
            source_day: self.frozen.series[0]
                .observations
                .last()
                .unwrap()
                .trade_day
                .clone(),
            mode: self.frozen.input_mode.clone(),
            scopes: vec![rp::SCOPE.into(), "risk_timeseries_v1".into()],
            summary: json!({"phase":"local_cpu_risk","plan":self}),
            eod_eligible: false,
        }
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Forecast {
    pub instrument: String,
    pub values: Vec<f64>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Response {
    pub schema_version: u32,
    pub request_sha256: String,
    pub model_revision: String,
    pub weight_sha256: String,
    pub forecasts: Vec<Forecast>,
    pub clamp_count: u32,
    pub clamp_policy: String,
    pub metrics: Value,
    pub isolation: Value,
}
pub fn decode(plan: &Plan, response: &Response) -> Result<Value> {
    decode_inner(plan, response, false)
}
/// Read-only engineering diagnostics; cannot complete a production task.
pub fn decode_development(plan: &Plan, response: &Response) -> Result<Value> {
    decode_inner(plan, response, true)
}
fn decode_inner(plan: &Plan, response: &Response, development: bool) -> Result<Value> {
    plan.validate(false)?;
    ensure(
        response.schema_version == 1
            && response.request_sha256 == hash(plan.request().to_string().as_bytes())
            && response.model_revision == REVISION
            && response.weight_sha256 == WEIGHT_SHA
            && response.clamp_count == 0
            && response.clamp_policy == "REJECT_NEGATIVE_NO_CLAMP"
            && response.forecasts.len() == plan.frozen.series.len(),
        "LOCAL_RESPONSE_BINDING",
    )?;
    let isolated = response.isolation["mechanism"] == "systemd-cgroup-v2+bubblewrap"
        && response.isolation["memory_max_bytes"]
            .as_u64()
            .is_some_and(|n| n > 0 && n <= 6 * 1024 * 1024 * 1024)
        && response.isolation["memory_swap_max_bytes"] == 0;
    ensure(
        isolated
            || (development
                && response.isolation["mechanism"] == "UNISOLATED_DEVELOPMENT_DIAGNOSTIC"),
        "LOCAL_ISOLATION_REQUIRED",
    )?;
    let f = &plan.frozen;
    let mut experts = Vec::new();
    for (b, row) in rp::baselines(f).iter().zip(&response.forecasts) {
        ensure(
            b["instrument"] == row.instrument
                && row.values.len() == 20
                && row
                    .values
                    .iter()
                    .all(|x| x.is_finite() && (0.0..=0.35).contains(x)),
            "LOCAL_FORECAST_UNITS_OR_ORDER",
        )?;
        let avg = row.values.iter().sum::<f64>() / 20.;
        let mut baseline = b.clone();
        baseline.as_object_mut().unwrap().remove("rolling_context");
        experts.push(json!({"schema_version":1,"instrument":row.instrument,"input_mode":f.input_mode,
            "snapshot_ref":f.snapshot_ref,"readiness_ref":f.readiness_ref,"as_of":f.as_of,"forecast_horizons":[5,20],
            "volatility_forecast":[{"sessions":5,"value_ratio":row.values[..5].iter().sum::<f64>()/5.}, {"sessions":20,"value_ratio":avg}],
            "forecast_sessions":f.target_sessions(),"session_mapping":"ordinal_daily_model_axis_to_frozen_exchange_calendar_v1",
            "target":"rolling20_rms_daily_return_ratio","unit":"daily_return_ratio","annualization":null,
            "downside_metric":"UNKNOWN_UNCALIBRATED","market_regime":if avg>=0.025 {"HIGH_VOLATILITY"}else{"NORMAL_VOLATILITY"},
            "regime_rule":"rms_daily_ratio_ge_0.025_v1_exploratory_not_risk_policy","uncertainty":"UNKNOWN_UNCALIBRATED",
            "baseline_comparison":baseline,"quality_blockers":["SYNTHETIC_ENGINEERING_ONLY"],"calibration_status":"UNKNOWN_UNCALIBRATED",
            "covariance":"UNKNOWN_INSUFFICIENT_EVIDENCE","error_comparison":"UNKNOWN_NO_FORWARD_OUTCOMES","job_ref":null,
            "cost":{"allocation":"SHARED_BATCH_COST_NOT_PER_INSTRUMENT","receipt":"parent_bundle.receipt","actual_bill":"LOCAL_NO_BILLING"},"authority":rp::AUTHORITY}));
    }
    let mut bundle = rp::safe();
    bundle["paper_allowed"] = json!(false);
    bundle["risk_experts"] = json!(experts);
    if !isolated {
        for expert in bundle["risk_experts"].as_array_mut().unwrap() {
            expert["quality_blockers"]
                .as_array_mut()
                .unwrap()
                .push(json!("DEVELOPMENT_ISOLATION_NOT_VERIFIED"));
        }
    }
    bundle["receipt"] = json!({"transport":"local_cpu","billing":"LOCAL_NO_BILLING","model_revision":REVISION,
        "weight_sha256":WEIGHT_SHA,"code_sha256":plan.code_sha256,"manifest_sha256":plan.manifest_sha256,
        "frozen_input_sha256":rp::sha(&serde_json::to_value(f).unwrap()),"request_sha256":response.request_sha256,
        "clamp_policy":response.clamp_policy,"clamp_count":0,"metrics":response.metrics,"isolation":response.isolation,"development_only":!isolated});
    if let Some(h) = &plan.history {
        for e in bundle["risk_experts"].as_array_mut().unwrap() {
            e["quality_blockers"] = h.payload["blockers"].clone();
            e["session_mapping"] = json!("ordinal_future_sessions_dates_unknown");
            e["historical_pit_status"] = json!("NOT_VERIFIED");
            e["coverage"] = json!("PARTIAL");
        }
        bundle["historical_research"] = json!({"input_sha256":h.payload_sha256,
            "adapter_version":"historical-timesfm-v1","quality":h.payload["quality"],
            "historical_pit_status":"NOT_VERIFIED","coverage":"PARTIAL",
            "cloud_egress":"REAL_MARKET_DATA_EGRESS_DENIED"});
        bundle["receipt"]["historical_input_sha256"] = json!(h.payload_sha256);
        bundle["receipt"]["plan_sha256"] = json!(rp::sha(&serde_json::to_value(plan).unwrap()));
    }
    rp::validate_output(&bundle)?;
    Ok(bundle)
}
pub fn connection(write: bool) -> Result<(risk_binding::Binding, Connection)> {
    let b = risk_binding::read()?;
    let flags = if write {
        OpenFlags::SQLITE_OPEN_READ_WRITE
    } else {
        OpenFlags::SQLITE_OPEN_READ_ONLY
    };
    let c = Connection::open_with_flags(b.agent_dir.join("agent.sqlite"), flags)?;
    b.verify(&c)?;
    c.busy_timeout(std::time::Duration::from_secs(5))?;
    if write {
        c.execute_batch("PRAGMA synchronous=FULL;")?;
    }
    Ok((b, c))
}
fn gate(db: &Connection) -> Result<()> {
    let get = |key: &str| -> Result<Option<String>> {
        Ok(db
            .query_row("SELECT value FROM meta WHERE key=?1", [key], |r| r.get(0))
            .optional()?)
    };
    ensure(
        get("timesfm_cpu_enabled")?.as_deref() == Some("true"),
        "LOCAL_CPU_DISABLED",
    )?;
    ensure(get("paused")?.as_deref() != Some("true"), "OWNER_PAUSED")
}
pub fn begin(plan: &Plan) -> Result<Value> {
    plan.validate(true)?;
    let (binding, mut db) = connection(true)?;
    let settings = crate::config::Settings::load(&binding.settings_path)?;
    Store {
        path: binding.agent_dir.join("agent.sqlite"),
    }
    .capacity(&settings)?;
    let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
    gate(&tx)?;
    let trigger = format!("{POLICY}:{}", plan.batch);
    let input = serde_json::to_string(&plan.input()).unwrap();
    let prior: Option<(i64, String, String, String, i64)> = tx
        .query_row(
            "SELECT t.id,t.input,t.status,t.provider_id,(SELECT COUNT(*) FROM calls WHERE task_id=t.id) FROM tasks t WHERE trigger_key=?1",
            [&trigger],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?, r.get(4)?)),
        )
        .optional()?;
    let id = if let Some((id, old, status, provider_id, call_count)) = prior {
        if old != input {
            // A local TimesFM task is pre-cloud, non-billable evidence. A product
            // or model-code update legitimately changes its frozen input; retrying
            // must not deadlock automatic research forever. Audited replacement is
            // only allowed when this local task never produced a billable call.
            ensure(provider_id == "local-timesfm-2.5-cpu" && call_count == 0,
                   "LOCAL_PIN_CHANGED_NEW_TASK_REQUIRED")?;
            let now = Utc::now().to_rfc3339();
            let audit = serde_json::json!({"at":now,"old_input_sha256":crate::hash(old.as_bytes()),
                "new_provider_hash":plan.pin(),"source":"local_pin_refresh"});
            tx.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?1,?2)",
                params![format!("timesfm_cpu_superseded:{id}:{now}"), audit.to_string()])?;
            tx.execute("UPDATE tasks SET input=?1,provider_hash=?2,status='local_running',started_at=?3,finished_at=NULL,reason=NULL,result=NULL WHERE id=?4",
                params![input, plan.pin(), now, id])?;
        } else if status == "local_running" {
            // Caller holds the original Agent and singleton Worker lifetime locks.
            tx.execute("UPDATE tasks SET status='failed',reason='WORKER_INTERRUPTED_NO_RETRY',finished_at=?1 WHERE id=?2",params![Utc::now().to_rfc3339(),id])?;
        }
        id
    } else {
        let count: i64 = tx.query_row("SELECT COUNT(*) FROM tasks", [], |r| r.get(0))?;
        ensure(count < settings.max_tasks as i64, "RESEARCH_TASK_LIMIT")?;
        let request = TaskRequest {
            name: format!("TimesFM CPU {}", plan.batch),
            goal: "Local rolling RMS risk evidence".into(),
            scope: rp::SCOPE.into(),
            start_day: plan.input().source_day.clone(),
            end_day: plan.input().source_day,
            task_budget_micro: None,
        };
        request.validate()?;
        let now = Utc::now().to_rfc3339();
        tx.execute("INSERT INTO tasks(request,input,provider_id,provider_hash,status,created_at,started_at,trigger_key) VALUES(?1,?2,'local-timesfm-2.5-cpu',?3,'local_running',?4,?4,?5)",
            params![serde_json::to_string(&request).unwrap(),input,plan.pin(),now,trigger])?;
        tx.last_insert_rowid()
    };
    tx.commit()?;
    Store {
        path: binding.agent_dir.join("agent.sqlite"),
    }
    .task(id)
}
pub fn finish(
    id: i64,
    plan: &Plan,
    response: Option<&Response>,
    failure: Option<&str>,
) -> Result<Value> {
    let bundle = response.map(|r| decode(plan, r)).transpose()?;
    let (binding, mut db) = connection(true)?;
    let tx = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let (input, pin, status): (String, String, String) = tx.query_row(
        "SELECT input,provider_hash,status FROM tasks WHERE id=?1 AND trigger_key=?2",
        params![id, format!("{POLICY}:{}", plan.batch)],
        |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
    )?;
    ensure(
        input == serde_json::to_string(&plan.input()).unwrap()
            && pin == plan.pin()
            && matches!(status.as_str(), "local_running" | "cancel_requested"),
        "LOCAL_TASK_CHANGED",
    )?;
    let active = gate(&tx).is_ok() && status == "local_running";
    let result = bundle.map(|b| {
        let mut result = json!({"billing":"LOCAL_NO_BILLING","backend":"TimesFM 2.5 CPU",
        "worker_response":response,"research":{"risk_portfolio":b}});
        if plan.history.is_some() {
            result["source_day"] = json!(plan.input().source_day);
            result["input_mode"] = json!(plan.frozen.input_mode);
            result["input_summary_version"] = json!(plan.input().version);
            result["model"] = json!("local-timesfm-2.5-cpu");
            result["synthetic_provider"] = json!(false);
            result["task_id"] = json!(id);
            result["attempt"] = json!(1);
            result["result_sha256"] = json!(rp::sha(&result));
        }
        result
    });
    let (state, reason) = if !active {
        ("cancelled", "OWNER_STOPPED")
    } else if result.is_some() {
        ("completed", "LOCAL_NO_BILLING")
    } else {
        ("failed", failure.unwrap_or("WORKER_FAILED"))
    };
    ensure(
        reason.len() <= 80 && reason.bytes().all(|b| b.is_ascii_uppercase() || b == b'_'),
        "LOCAL_FAILURE_CODE",
    )?;
    tx.execute(
        "UPDATE tasks SET status=?1,reason=?2,result=?3,finished_at=?4 WHERE id=?5",
        params![
            state,
            reason,
            result.filter(|_| active).map(|v| v.to_string()),
            Utc::now().to_rfc3339(),
            id
        ],
    )?;
    tx.commit()?;
    Store {
        path: binding.agent_dir.join("agent.sqlite"),
    }
    .task(id)
}
