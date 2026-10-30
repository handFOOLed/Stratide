use crate::{
    budget::{self, Reservation},
    config::Settings,
    ensure,
    provider::{self, Outcome},
    InputSummary, Result, Store, TaskRequest,
};
use chrono::{DateTime, Timelike, Utc};
use fs2::FileExt;
use rusqlite::{params, OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::Duration,
};

struct Inner {
    store: Store,
    config_path: PathBuf,
    owner_token: String,
    summary_source: Option<Arc<dyn Fn() -> Result<InputSummary> + Send + Sync>>,
    current_summary: Mutex<(Option<DateTime<Utc>>, InputSummary)>,
    _lock: File,
    fault: Mutex<Option<String>>,
}
#[derive(Clone)]
pub struct Agent(Arc<Inner>);

impl Agent {
    pub fn open(dir: &Path, config_path: Option<&Path>, summary: InputSummary) -> Result<Self> {
        fs::create_dir_all(dir).map_err(|_| "AGENT_DIRECTORY_UNAVAILABLE")?;
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(dir.join("agent.lock"))
            .map_err(|_| "AGENT_LOCK_UNAVAILABLE")?;
        lock.try_lock_exclusive()
            .map_err(|_| "AGENT_ALREADY_RUNNING")?;
        let config_path = config_path
            .map(Path::to_path_buf)
            .unwrap_or_else(|| dir.join("settings.json"));
        let settings = if config_path.exists() {
            Settings::load(&config_path)?
        } else {
            Settings::default()
        };
        let store = Store::open(dir, &settings)?;
        store.recover(Utc::now())?;
        let token_path = dir.join("owner-token");
        if !token_path.exists() {
            let mut options = OpenOptions::new();
            options.create_new(true).write(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            let mut file = options
                .open(&token_path)
                .map_err(|_| "OWNER_TOKEN_UNAVAILABLE")?;
            file.write_all(crate::nonce()?.as_bytes())
                .map_err(|_| "OWNER_TOKEN_UNAVAILABLE")?;
            file.sync_all().map_err(|_| "OWNER_TOKEN_UNAVAILABLE")?;
        }
        ensure(
            fs::symlink_metadata(&token_path)
                .is_ok_and(|m| m.is_file() && m.len() <= 256 && !m.file_type().is_symlink()),
            "OWNER_TOKEN_INVALID",
        )?;
        let token = fs::read_to_string(&token_path)
            .map_err(|_| "OWNER_TOKEN_UNAVAILABLE")?
            .trim()
            .to_string();
        ensure(
            token.len() >= 32
                && token.len() <= 128
                && token.bytes().all(|b| b.is_ascii_alphanumeric()),
            "OWNER_TOKEN_INVALID",
        )?;
        Ok(Self(Arc::new(Inner {
            store,
            config_path,
            current_summary: Mutex::new((None, summary.clone())),
            owner_token: token,
            summary_source: None,
            _lock: lock,
            fault: Mutex::new(None),
        })))
    }
    pub fn with_summary_source(
        mut self,
        source: impl Fn() -> Result<InputSummary> + Send + Sync + 'static,
    ) -> Self {
        Arc::get_mut(&mut self.0)
            .expect("set summary source before cloning/starting")
            .summary_source = Some(Arc::new(source));
        self
    }
    fn summary(&self, now: DateTime<Utc>) -> Result<InputSummary> {
        let cached = self
            .0
            .current_summary
            .lock()
            .map_err(|_| "INPUT_CACHE_UNAVAILABLE")?;
        if let Some(source) = &self.0.summary_source {
            if cached.1.is_eod_snapshot()
                || cached
                    .0
                    .is_none_or(|at| now.signed_duration_since(at).num_seconds() >= 60)
            {
                drop(cached);
                // Refresh ONLY the explicitly selected published input. Account
                // API stays pinned to its separate startup snapshot.
                let fresh = source()?;
                let mut cached = self
                    .0
                    .current_summary
                    .lock()
                    .map_err(|_| "INPUT_CACHE_UNAVAILABLE")?;
                cached.1 = fresh;
                cached.0 = Some(now);
                return Ok(cached.1.clone());
            }
        }
        Ok(cached.1.clone())
    }
    pub fn store(&self) -> &Store {
        &self.0.store
    }
    pub fn authorized(&self, candidate: &str) -> bool {
        let expected = self.0.owner_token.as_bytes();
        let actual = candidate.as_bytes();
        if expected.len() != actual.len() {
            return false;
        }
        expected
            .iter()
            .zip(actual)
            .fold(0u8, |a, (b, c)| a | (b ^ c))
            == 0
    }
    fn settings(&self) -> Result<Settings> {
        let s = if self.0.config_path.exists() {
            Settings::load(&self.0.config_path)?
        } else {
            Settings::default()
        };
        if let Some(b) = &s.budget {
            let policy = format!("{}|{}", b.currency, b.timezone);
            if let Some(old) = self.store().setting("budget_identity")? {
                ensure(old == policy, "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE")?;
            } else {
                self.store().set("budget_identity", &policy)?;
            }
        }
        Ok(s)
    }
    pub fn start(&self) -> Result<()> {
        let agent = self.clone();
        std::thread::Builder::new()
            .name("research-worker".into())
            .spawn(move || loop {
                let outcome = agent.tick(Utc::now());
                if let Ok(mut fault) = agent.0.fault.lock() {
                    *fault = outcome.err().map(|e| e.0);
                }
                std::thread::sleep(Duration::from_millis(500));
            })
            .map_err(|_| "RESEARCH_WORKER_UNAVAILABLE")?;
        Ok(())
    }
    pub fn status(&self, now: DateTime<Utc>) -> Result<Value> {
        let settings = self.settings()?;
        let mut result = self.store().status(&settings, now)?;
        result["worker_error"] = json!(self.0.fault.lock().ok().and_then(|f| f.clone()));
        result["input"] = serde_json::to_value(
            &self
                .0
                .current_summary
                .lock()
                .map_err(|_| "INPUT_CACHE_UNAVAILABLE")?
                .1,
        )
        .map_err(|_| "INPUT_INVALID")?;
        let scopes: Vec<String> = serde_json::from_value(result["input"]["scopes"].clone())
            .map_err(|_| "INPUT_INVALID")?;
        if let Some(models) = result["models"].as_array_mut() {
            let c = self.store().connect()?;
            for (view, model) in models.iter_mut().zip(&settings.models) {
                view["authorization"] = json!(model
                    .authorize(&scopes, settings.budget.as_ref())
                    .err()
                    .map(|e| e.0)
                    .unwrap_or("authorized".into()));
                // Local policy/input/budget rejections, pre-send cancellation and
                // confirmed-not-sent retries are not Provider observations. Keep
                // prior Provider health; task.reason/authorization/budget expose
                // the local block.
                let last: Option<(String, Option<String>)> = c.query_row(
                    "SELECT
                        CASE WHEN t.result IS NOT NULL AND c.state IN ('settled','usage_received')
                             THEN 'completed' ELSE 'failed' END,
                        CASE WHEN t.reason IN ('PROVIDER_DNS_UNAVAILABLE','PROVIDER_CLIENT_UNAVAILABLE') THEN t.reason
                             WHEN t.result IS NOT NULL AND c.state IN ('settled','usage_received') THEN 'RESEARCH_SAVED'
                             WHEN c.state='settled' THEN t.reason
                             ELSE COALESCE(c.reason,t.reason) END
                     FROM tasks t LEFT JOIN calls c ON c.id=(
                        SELECT id FROM calls WHERE task_id=t.id AND state!='reserved'
                          AND (state!='no_charge' OR reason NOT IN ('RESTART_BEFORE_DISPATCH','CANCELLED_BEFORE_DISPATCH','FAKE_CONFIRMED_NOT_SENT'))
                        ORDER BY id DESC LIMIT 1)
                     WHERE t.provider_id=?1 AND t.provider_hash=?2
                       AND t.status NOT IN ('queued','running','cancel_requested')
                       AND (c.id IS NOT NULL OR t.reason IN ('PROVIDER_DNS_UNAVAILABLE','PROVIDER_CLIENT_UNAVAILABLE'))
                     ORDER BY t.finished_at DESC,t.id DESC LIMIT 1",
                    params![model.id,model.fingerprint()],
                    |r| Ok((r.get(0)?,r.get(1)?)),
                ).optional()?;
                view["availability"] = json!(match last.as_ref().map(|v| v.0.as_str()) {
                    Some("failed" | "outcome_uncertain") => "unavailable_or_outcome_unknown",
                    Some("completed") => "last_task_completed",
                    _ => "not_verified",
                });
                view["last_reason"] = json!(last.and_then(|v| v.1));
                if model.kind != "fake" {
                    let successes:i64=c.query_row("SELECT COUNT(*) FROM tasks WHERE provider_id=?1 AND provider_hash=?2 AND result IS NOT NULL",params![model.id,model.fingerprint()],|r|r.get(0))?;
                    if successes > 0 {
                        view["verification"] = json!("REAL_PROVIDER_CALL_OBSERVED");
                    }
                }
            }
        }
        Ok(result)
    }
    pub fn create(&self, request: &TaskRequest, now: DateTime<Utc>) -> Result<i64> {
        self.store()
            .create(&self.settings()?, request, &self.summary(now)?, now, None)
    }
    pub fn control(&self, action: &str, value: &Value, now: DateTime<Utc>) -> Result<Value> {
        let s = self.settings()?;
        match action {
            "pause" => self.store().set("paused", "true")?,
            "resume" => self.store().set("paused", "false")?,
            "eod" => {
                let enabled = value
                    .get("enabled")
                    .and_then(Value::as_bool)
                    .ok_or("EOD_BOOLEAN_REQUIRED")?;
                self.store()
                    .set("eod_enabled", if enabled { "true" } else { "false" })?;
            }
            "model" | "backup" => {
                let id = value
                    .get("model_id")
                    .and_then(Value::as_str)
                    .ok_or("MODEL_ID_REQUIRED")?;
                ensure(s.models.iter().any(|m| m.id == id), "MODEL_NOT_CONFIGURED")?;
                self.store().set(
                    if action == "model" {
                        "default_model"
                    } else {
                        "backup_model"
                    },
                    id,
                )?;
            }
            _ => return Err("CONTROL_ACTION_INVALID".into()),
        }
        self.status(now)
    }
    pub fn tick(&self, now: DateTime<Utc>) -> Result<()> {
        let s = self.settings()?;
        self.store().capacity(&s)?;
        self.schedule_eod(&s, now)?;
        if let Some(id) = self.store().claim(now)? {
            if let Err(error) = self.run_task(id, now) {
                self.store()
                    .finish(id, "failed", &error.0, None, Utc::now())?;
            }
        }
        Ok(())
    }
    fn run_task(&self, id: i64, now: DateTime<Utc>) -> Result<()> {
        loop {
            let task = self.store().task(id)?;
            if task["status"] == "cancel_requested" {
                return self.store().finish(
                    id,
                    "cancelled",
                    "OWNER_CANCELLED_BEFORE_REQUEST",
                    None,
                    Utc::now(),
                );
            }
            let s = self.settings()?;
            let m = s
                .models
                .iter()
                .find(|m| Some(m.id.as_str()) == task["provider_id"].as_str())
                .ok_or("PINNED_MODEL_UNAVAILABLE")?;
            ensure(
                Some(m.fingerprint().as_str()) == task["provider_hash"].as_str(),
                "PINNED_MODEL_CONFIGURATION_CHANGED",
            )?;
            let input: InputSummary =
                serde_json::from_value(task["input"].clone()).map_err(|_| "INPUT_INVALID")?;
            let request: TaskRequest = serde_json::from_value(task["request"].clone())
                .map_err(|_| "TASK_INPUT_INVALID")?;
            let task_limit = request.validate()?;
            m.authorize(&input.scopes, s.budget.as_ref())?;
            let provider_input = json!({"owner_task":request,"published_summary":input});
            let prepared = provider::prepare(m, &provider_input)?;
            // Re-read settings after DNS preparation. Revoked grants or changed
            // caps take effect before reserving or entering the send boundary.
            let latest = self.settings()?;
            let latest_m = latest
                .models
                .iter()
                .find(|p| p.id == m.id)
                .ok_or("PINNED_MODEL_UNAVAILABLE")?;
            ensure(
                latest_m.fingerprint() == m.fingerprint(),
                "PINNED_MODEL_CONFIGURATION_CHANGED",
            )?;
            latest_m.authorize(&input.scopes, latest.budget.as_ref())?;
            let mut c = self.store().connect()?;
            let calls = task["calls"].as_array().ok_or("CALL_STATE_INVALID")?;
            ensure(
                calls.len() < 2 && calls.iter().all(|v| v["state"] == "no_charge"),
                "RETRY_UNSAFE_OR_EXHAUSTED",
            )?;
            let maximum = m.cost(m.max_input_tokens, m.max_output_tokens)?;
            let reservation_time = if m.kind == "fake" { now } else { Utc::now() };
            let call_id = budget::reserve(
                &mut c,
                latest.budget.as_ref().ok_or("BUDGET_UNCONFIGURED")?,
                reservation_time,
                Reservation {
                    task_id: id,
                    maximum_micro: maximum,
                    task_limit,
                    price_version: &m.price.as_ref().ok_or("PRICE_UNCONFIGURED")?.version,
                },
            )?;
            let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
            let status: String =
                tx.query_row("SELECT status FROM tasks WHERE id=?1", [id], |r| r.get(0))?;
            if status == "cancel_requested" {
                tx.execute("UPDATE calls SET state='no_charge',reason='CANCELLED_BEFORE_DISPATCH' WHERE id=?1",[call_id])?;
                tx.commit()?;
                return self.store().finish(
                    id,
                    "cancelled",
                    "OWNER_CANCELLED_BEFORE_REQUEST",
                    None,
                    Utc::now(),
                );
            }
            tx.execute(
                "UPDATE calls SET state='dispatched' WHERE id=?1 AND state='reserved'",
                [call_id],
            )?;
            tx.commit()?;
            let outcome = provider::call(prepared, calls.len() + 1);
            let finished = Utc::now();
            match outcome {
                Outcome::NoCharge { retryable, reason } => {
                    c.execute(
                        "UPDATE calls SET state='no_charge',reason=?1,finished_at=?2 WHERE id=?3",
                        params![reason, finished.to_rfc3339(), call_id],
                    )?;
                    if retryable && calls.is_empty() {
                        continue;
                    }
                    return self.store().finish(id, "failed", reason, None, finished);
                }
                Outcome::Uncertain(reason) => {
                    c.execute("UPDATE calls SET state='outcome_uncertain',reason=?1,finished_at=?2 WHERE id=?3",params![reason,finished.to_rfc3339(),call_id])?;
                    return self
                        .store()
                        .finish(id, "outcome_uncertain", reason, None, finished);
                }
                Outcome::ChargedFailure {
                    reason,
                    input_tokens,
                    output_tokens,
                } => {
                    let violation = input_tokens.is_some_and(|n| n > m.max_input_tokens)
                        || output_tokens.is_some_and(|n| n > m.max_output_tokens);
                    c.execute("UPDATE calls SET state='charged_failure',reason=?1,finished_at=?2,input_tokens=?3,output_tokens=?4,violation=?5 WHERE id=?6",params![reason,finished.to_rfc3339(),input_tokens,output_tokens,violation,call_id])?;
                    return self.store().finish(id, "failed", reason, None, finished);
                }
                Outcome::Success {
                    research,
                    input_tokens,
                    output_tokens,
                } => {
                    research.validate()?;
                    let usage = m.cost(input_tokens, output_tokens)?;
                    let valid = input_tokens <= m.max_input_tokens
                        && output_tokens <= m.max_output_tokens
                        && usage <= maximum;
                    let fake = m.kind == "fake";
                    c.execute("UPDATE calls SET state=?1,usage_micro=?2,settled_micro=?3,input_tokens=?4,output_tokens=?5,finished_at=?6,violation=?7 WHERE id=?8",
                        params![if !valid{"outcome_uncertain"}else if fake{"settled"}else{"usage_received"},usage,if fake && valid {usage}else{0},input_tokens,output_tokens,finished.to_rfc3339(),!valid,call_id])?;
                    let result = json!({"research":research,"provider_id":m.id,"provider_kind":m.kind,"model":m.model,
                        "input_summary_version":input.version,"source_day":input.source_day,"input_mode":input.mode,
                        "generated_at":finished.to_rfc3339(),"synthetic_provider":fake,"qualification":"EXPLORATORY_NOT_INDEPENDENT",
                        "limitations":"研究意见不能作为独立策略资格/收益或实盘部署结论；历史/合成输入保持原标签。",
                        "billing":if fake{"synthetic_test_settled"}else{"usage_received_invoice_not_final"}});
                    return self.store().finish(
                        id,
                        if valid {
                            "completed"
                        } else {
                            "outcome_uncertain"
                        },
                        if valid {
                            "RESEARCH_SAVED"
                        } else {
                            "PROVIDER_BILLING_BOUND_VIOLATION"
                        },
                        Some(&result),
                        finished,
                    );
                }
            }
        }
    }
    pub fn schedule_eod(&self, s: &Settings, now: DateTime<Utc>) -> Result<()> {
        let market = now.with_timezone(&chrono_tz::Asia::Shanghai);
        let current_key = format!("eod-v1:{}", market.format("%Y-%m-%d"));
        let c = self.store().connect()?;
        // Expire missed automatic work even while scheduling is OFF or budget
        // configuration is absent. Manual queued work retains its own semantics.
        c.execute("UPDATE tasks SET status='cancelled',reason='EOD_SUPERSEDED_SKIPPED',finished_at=?1 WHERE status='queued' AND trigger_key IS NOT NULL AND trigger_key!=?2",params![now.to_rfc3339(),current_key])?;
        c.execute("UPDATE eod SET disposition='skipped_superseded' WHERE source_day<?1 AND disposition='queued' AND EXISTS(SELECT 1 FROM tasks WHERE trigger_key='eod-v1:'||eod.source_day AND reason='EOD_SUPERSEDED_SKIPPED')",[market.format("%Y-%m-%d").to_string()])?;
        if self.store().setting("eod_enabled")?.as_deref() != Some("true") {
            return Ok(());
        }
        if self
            .0
            .current_summary
            .lock()
            .map_err(|_| "INPUT_CACHE_UNAVAILABLE")?
            .1
            .is_eod_snapshot()
        {
            self.store().set("eod_reason", "EOD_SNAPSHOT_MANUAL_ONLY")?;
            return Ok(());
        }
        if s.budget.is_none() {
            self.store().set("eod_reason", "BUDGET_UNCONFIGURED")?;
            return Ok(());
        }
        let input = self.summary(now)?;
        // Only the current source session, after 16:00 in its trusted market TZ.
        // A stale pinned report is never relabeled as today's EOD.
        let valid = input.eod_eligible
            && input.mode == "historical_replay"
            && input.source_day == market.format("%Y-%m-%d").to_string()
            && market.hour() >= 16;
        if !valid {
            self.store()
                .set("eod_reason", "NO_NEW_VALID_CURRENT_EOD_SOURCE")?;
            return Ok(());
        }
        let key = format!("eod-v1:{}", input.source_day);
        let prior: Option<String> = c
            .query_row(
                "SELECT disposition FROM eod WHERE source_day=?1",
                [&input.source_day],
                |r| r.get(0),
            )
            .optional()?;
        if prior.is_some_and(|p| p == "queued") {
            return Ok(());
        }
        let paused = self.store().setting("paused")?.as_deref() == Some("true");
        if paused {
            c.execute("INSERT OR IGNORE INTO eod(source_day,input_version,disposition,at) VALUES(?1,?2,'skipped_paused',?3)",params![input.source_day,input.version,now.to_rfc3339()])?;
            self.store().set("eod_reason", "OWNER_PAUSED_LATEST_ONLY")?;
            return Ok(());
        }
        let request = TaskRequest {
            name: format!("EOD 日常研究 · {}", input.source_day),
            goal: "根据已发布摘要形成可核查假设、关键依据、反证和下一研究步骤。".into(),
            scope: "当前已发布 Paper 摘要".into(),
            start_day: input.source_day.clone(),
            end_day: input.source_day.clone(),
            task_budget_micro: None,
        };
        // trigger_key prevents a duplicate even if the process dies before eod's
        // completion marker is updated. Never replay an uncertain paid request.
        let existing: Option<i64> = c
            .query_row("SELECT id FROM tasks WHERE trigger_key=?1", [&key], |r| {
                r.get(0)
            })
            .optional()?;
        if existing.is_none() {
            self.store().create(s, &request, &input, now, Some(&key))?;
        }
        c.execute("INSERT INTO eod(source_day,input_version,disposition,at) VALUES(?1,?2,'queued',?3) ON CONFLICT(source_day) DO UPDATE SET disposition='queued',at=excluded.at",params![input.source_day,input.version,now.to_rfc3339()])?;
        self.store()
            .set("eod_reason", "LATEST_SOURCE_QUEUED_ONCE")?;
        Ok(())
    }
}
