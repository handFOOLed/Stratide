use crate::{budget, config::Settings, ensure, InputSummary, Result, TaskRequest};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

const APPLICATION_ID: i64 = 0x53524131;
#[derive(Clone)]
pub struct Store {
    pub path: PathBuf,
}

impl Store {
    pub fn open(dir: &Path, settings: &Settings) -> Result<Self> {
        settings.validate()?;
        fs::create_dir_all(dir).map_err(|_| "AGENT_DIRECTORY_UNAVAILABLE")?;
        ensure(
            fs::symlink_metadata(dir).is_ok_and(|m| m.is_dir() && !m.file_type().is_symlink()),
            "AGENT_DIRECTORY_INVALID",
        )?;
        let path = dir.join("agent.sqlite");
        if path.exists() {
            ensure(
                fs::symlink_metadata(&path)
                    .is_ok_and(|m| m.is_file() && !m.file_type().is_symlink()),
                "AGENT_STORE_INVALID",
            )?;
        }
        let result = Self { path };
        let mut c = result.connect()?;
        let app: i64 = c.pragma_query_value(None, "application_id", |r| r.get(0))?;
        if app == 0 {
            let tables: i64 = c.query_row(
                "SELECT count(*) FROM sqlite_master WHERE type='table'",
                [],
                |r| r.get(0),
            )?;
            ensure(tables == 0, "NOT_AN_AGENT_DATABASE")?;
        } else {
            ensure(app == APPLICATION_ID, "NOT_AN_AGENT_DATABASE")?;
            let version: i64 = c.pragma_query_value(None, "user_version", |r| r.get(0))?;
            ensure(version == 1, "AGENT_SCHEMA_UNSUPPORTED")?;
        }
        c.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(
                id INTEGER PRIMARY KEY AUTOINCREMENT, request TEXT NOT NULL, input TEXT NOT NULL,
                provider_id TEXT NOT NULL, provider_hash TEXT NOT NULL, status TEXT NOT NULL,
                reason TEXT, result TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                cancel_requested_at TEXT, trigger_key TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS calls(
                id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER NOT NULL REFERENCES tasks(id),
                day TEXT NOT NULL,month TEXT NOT NULL,maximum_micro INTEGER NOT NULL CHECK(maximum_micro>0),
                settled_micro INTEGER NOT NULL DEFAULT 0,usage_micro INTEGER,input_tokens INTEGER,output_tokens INTEGER,
                price_version TEXT NOT NULL,state TEXT NOT NULL,reason TEXT,created_at TEXT NOT NULL,finished_at TEXT,
                violation INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS calls_task ON calls(task_id);
            CREATE TABLE IF NOT EXISTS eod(source_day TEXT PRIMARY KEY,input_version TEXT NOT NULL,disposition TEXT NOT NULL,at TEXT NOT NULL);
            PRAGMA application_id=1397899569; PRAGMA user_version=1;")?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        for (key, value) in [("paused", "false"), ("eod_enabled", "false")] {
            tx.execute(
                "INSERT OR IGNORE INTO meta(key,value) VALUES(?1,?2)",
                params![key, value],
            )?;
        }
        if let Some(b) = &settings.budget {
            let policy = format!("{}|{}", b.currency, b.timezone);
            let existing: Option<String> = tx
                .query_row(
                    "SELECT value FROM meta WHERE key='budget_identity'",
                    [],
                    |r| r.get(0),
                )
                .optional()?;
            ensure(
                existing.as_deref().is_none_or(|p| p == policy),
                "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE",
            )?;
            tx.execute(
                "INSERT OR IGNORE INTO meta(key,value) VALUES('budget_identity',?1)",
                [policy],
            )?;
        }
        for (key, value) in [
            ("default_model", &settings.default_model),
            ("backup_model", &settings.backup_model),
        ] {
            if let Some(id) = value {
                tx.execute(
                    "INSERT OR IGNORE INTO meta(key,value) VALUES(?1,?2)",
                    params![key, id],
                )?;
            }
        }
        tx.commit()?;
        Ok(result)
    }
    pub fn connect(&self) -> Result<Connection> {
        let c = Connection::open(&self.path)?;
        c.busy_timeout(Duration::from_millis(500))?;
        if c.query_row(
            "SELECT value FROM meta WHERE key='eod_auto_binding'",
            [],
            |r| r.get::<_, String>(0),
        )
        .is_ok()
        {
            // Owner-local controls share this WAL with an in-flight fake. Allow
            // its small FULL commit to finish before recording the fake result.
            c.busy_timeout(Duration::from_secs(5))?;
        }
        c.execute_batch("PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;")?;
        Ok(c)
    }
    pub fn setting(&self, key: &str) -> Result<Option<String>> {
        Ok(self
            .connect()?
            .query_row("SELECT value FROM meta WHERE key=?1", [key], |r| r.get(0))
            .optional()?)
    }
    pub fn set(&self, key: &str, value: &str) -> Result<()> {
        self.connect()?.execute("INSERT INTO meta(key,value) VALUES(?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE meta.value!=excluded.value",params![key,value])?;
        Ok(())
    }
    pub fn recover(&self, now: DateTime<Utc>) -> Result<()> {
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        // 'reserved' is durably known not to have entered send(). A dispatch marker
        // is committed BEFORE the network boundary; a crash after that is uncertain.
        tx.execute("UPDATE calls SET state='no_charge',reason='RESTART_BEFORE_DISPATCH',finished_at=?1 WHERE state='reserved'",[now.to_rfc3339()])?;
        tx.execute("UPDATE calls SET state='outcome_uncertain',reason='RESTART_AFTER_DISPATCH' WHERE state='dispatched'",[])?;
        tx.execute("UPDATE tasks SET status='outcome_uncertain',reason='RESTART_EXTERNAL_OUTCOME_UNKNOWN',finished_at=?1
            WHERE status IN ('running','cancel_requested') AND EXISTS(SELECT 1 FROM calls WHERE task_id=tasks.id AND state!='no_charge')",[now.to_rfc3339()])?;
        tx.execute("UPDATE tasks SET status='cancelled',reason='RESTART_CANCELLED_BEFORE_DISPATCH',finished_at=?1 WHERE status='cancel_requested'",[now.to_rfc3339()])?;
        tx.execute("UPDATE tasks SET status='queued',reason='RECOVERED_BEFORE_DISPATCH' WHERE status='running'",[])?;
        tx.commit()?;
        Ok(())
    }
    pub fn capacity(&self, settings: &Settings) -> Result<()> {
        let mut bytes = 0;
        for p in [
            &self.path,
            &self.path.with_extension("sqlite-wal"),
            &self.path.with_extension("sqlite-shm"),
        ] {
            bytes += fs::metadata(p).map(|m| m.len()).unwrap_or(0);
        }
        ensure(
            bytes < settings.max_storage_mb * 1024 * 1024,
            "RESEARCH_STORAGE_LIMIT",
        )
    }
    pub fn create(
        &self,
        settings: &Settings,
        request: &TaskRequest,
        input: &InputSummary,
        now: DateTime<Utc>,
        trigger: Option<&str>,
    ) -> Result<i64> {
        request.validate()?;
        self.capacity(settings)?;
        let id = self
            .setting("default_model")?
            .ok_or("DEFAULT_MODEL_UNCONFIGURED")?;
        let model = settings
            .models
            .iter()
            .find(|m| m.id == id)
            .ok_or("DEFAULT_MODEL_UNAVAILABLE")?;
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        if trigger.is_some_and(|key| key.starts_with("eod-auto-v1:")) {
            // Serialize Owner disable/pause with creation of the daily task.
            let enabled: Option<String> = tx
                .query_row(
                    "SELECT value FROM meta WHERE key='eod_auto_enabled'",
                    [],
                    |r| r.get(0),
                )
                .optional()?;
            let paused: String =
                tx.query_row("SELECT value FROM meta WHERE key='paused'", [], |r| {
                    r.get(0)
                })?;
            ensure(enabled.as_deref() == Some("true"), "OWNER_DISABLED")?;
            ensure(paused != "true", "OWNER_PAUSED")?;
        }
        crate::multimodal::require_enabled(&tx, trigger)?;
        let count: i64 = tx.query_row("SELECT COUNT(*) FROM tasks", [], |r| r.get(0))?;
        ensure(count < settings.max_tasks as i64, "TASK_STORAGE_LIMIT")?;
        tx.execute("INSERT INTO tasks(request,input,provider_id,provider_hash,status,created_at,trigger_key) VALUES(?1,?2,?3,?4,'queued',?5,?6)",
            params![serde_json::to_string(request).map_err(|_|"TASK_INPUT_INVALID")?,serde_json::to_string(input).map_err(|_|"INPUT_INVALID")?,id,model.fingerprint(),now.to_rfc3339(),trigger])?;
        let result = tx.last_insert_rowid();
        tx.commit()?;
        Ok(result)
    }
    pub fn claim(&self, now: DateTime<Utc>) -> Result<Option<i64>> {
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let paused: String =
            tx.query_row("SELECT value FROM meta WHERE key='paused'", [], |r| {
                r.get(0)
            })?;
        if paused == "true" {
            return Ok(None);
        }
        let id: Option<i64> = tx
            .query_row(
                "SELECT id FROM tasks WHERE status='queued' ORDER BY id LIMIT 1",
                [],
                |r| r.get(0),
            )
            .optional()?;
        if let Some(id) = id {
            tx.execute(
                "UPDATE tasks SET status='running',started_at=?1,reason=NULL WHERE id=?2",
                params![now.to_rfc3339(), id],
            )?;
        }
        tx.commit()?;
        Ok(id)
    }
    pub fn cancel(&self, id: i64, now: DateTime<Utc>) -> Result<()> {
        let changed=self.connect()?.execute("UPDATE tasks SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END,
            cancel_requested_at=?1,finished_at=CASE WHEN status='queued' THEN ?1 ELSE finished_at END,reason='OWNER_CANCEL_REQUESTED'
            WHERE id=?2 AND status IN ('queued','running')",params![now.to_rfc3339(),id])?;
        ensure(changed == 1, "TASK_NOT_CANCELLABLE")
    }
    pub fn retry(&self, id: i64) -> Result<()> {
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let changed = tx.execute(
            "UPDATE tasks SET status='queued',reason='OWNER_SAFE_RETRY',finished_at=NULL
            WHERE id=?1 AND status='failed' AND (SELECT COUNT(*) FROM calls WHERE task_id=?1)<2
            AND NOT EXISTS(SELECT 1 FROM calls WHERE task_id=?1 AND state!='no_charge')",
            [id],
        )?;
        ensure(changed == 1, "TASK_RETRY_UNSAFE_OR_EXHAUSTED")?;
        tx.commit()?;
        Ok(())
    }
    pub fn finish(
        &self,
        id: i64,
        status: &str,
        reason: &str,
        result: Option<&Value>,
        now: DateTime<Utc>,
    ) -> Result<()> {
        self.connect()?.execute("UPDATE tasks SET status=CASE WHEN status='cancel_requested' AND ?1!='outcome_uncertain' THEN 'cancelled' ELSE ?1 END,
            reason=?2,result=?3,finished_at=?4 WHERE id=?5",params![status,reason,result.map(Value::to_string),now.to_rfc3339(),id])?;
        Ok(())
    }
    pub fn task(&self, id: i64) -> Result<Value> {
        let c = self.connect()?;
        let mut value=c.query_row("SELECT id,request,input,provider_id,provider_hash,status,reason,result,created_at,started_at,finished_at,cancel_requested_at FROM tasks WHERE id=?1",[id],|r| {
            let request:String=r.get(1)?; let input:String=r.get(2)?; let result:Option<String>=r.get(7)?;
            Ok(json!({"id":r.get::<_,i64>(0)?.to_string(),"request":serde_json::from_str::<Value>(&request).unwrap_or(Value::Null),
                "input":serde_json::from_str::<Value>(&input).unwrap_or(Value::Null),"provider_id":r.get::<_,String>(3)?,"provider_hash":r.get::<_,String>(4)?,
                "status":r.get::<_,String>(5)?,"reason":r.get::<_,Option<String>>(6)?,"result":result.and_then(|s|serde_json::from_str::<Value>(&s).ok()),
                "created_at":r.get::<_,String>(8)?,"started_at":r.get::<_,Option<String>>(9)?,"finished_at":r.get::<_,Option<String>>(10)?,"cancel_requested_at":r.get::<_,Option<String>>(11)?}))
        }).optional()?.ok_or("TASK_NOT_FOUND")?;
        let mut q=c.prepare("SELECT id,state,maximum_micro,settled_micro,usage_micro,input_tokens,output_tokens,price_version,reason,day,month FROM calls WHERE task_id=?1 ORDER BY id")?;
        let calls=q.query_map([id],|r| Ok(json!({"id":r.get::<_,i64>(0)?.to_string(),"state":r.get::<_,String>(1)?,"maximum_micro":r.get::<_,i64>(2)?.to_string(),
            "settled_micro":r.get::<_,i64>(3)?.to_string(),"usage_micro":r.get::<_,Option<i64>>(4)?.map(|v|v.to_string()),
            "input_tokens":r.get::<_,Option<i64>>(5)?.map(|v|v.to_string()),"output_tokens":r.get::<_,Option<i64>>(6)?.map(|v|v.to_string()),
            "price_version":r.get::<_,String>(7)?,"reason":r.get::<_,Option<String>>(8)?,"day":r.get::<_,String>(9)?,"month":r.get::<_,String>(10)?})))?
            .collect::<std::result::Result<Vec<_>,_>>()?;
        let retryable = value["status"] == "failed"
            && calls.len() < 2
            && calls.iter().all(|c| c["state"] == "no_charge");
        value["calls"] = json!(calls);
        value["retryable"] = json!(retryable);
        Ok(value)
    }
    pub fn list(&self, before: Option<i64>) -> Result<Value> {
        let c = self.connect()?;
        let mut q = c.prepare("SELECT id FROM tasks WHERE id<?1 ORDER BY id DESC LIMIT 21")?;
        let ids = q
            .query_map([before.unwrap_or(i64::MAX)], |r| r.get::<_, i64>(0))?
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let next = if ids.len() > 20 {
            ids.get(19).map(|v| v.to_string())
        } else {
            None
        };
        let mut tasks = vec![];
        for id in ids.into_iter().take(20) {
            let t = self.task(id)?;
            tasks.push(json!({"id":t["id"],"name":t["request"]["name"],"status":t["status"],"reason":t["reason"],
                "created_at":t["created_at"],"started_at":t["started_at"],"finished_at":t["finished_at"],"provider_id":t["provider_id"],
                "conclusion":t.pointer("/result/research/hypothesis"),"calls":t["calls"],"retryable":t["retryable"]}));
        }
        Ok(json!({"tasks":tasks,"next_before":next}))
    }
    /// Only the local CLI can reconcile an invoice. Web and model have no route.
    pub fn settle(&self, id: i64, actual: i64, reference: &str, now: DateTime<Utc>) -> Result<()> {
        ensure(
            (0..=1_000_000_000_000).contains(&actual)
                && !reference.trim().is_empty()
                && reference.len() <= 200,
            "INVOICE_INVALID",
        )?;
        let changed=self.connect()?.execute("UPDATE calls SET state='settled',settled_micro=?1,reason=?2,finished_at=?3 WHERE id=?4 AND state IN ('usage_received','outcome_uncertain','charged_failure')",params![actual,format!("OWNER_INVOICE:{reference}"),now.to_rfc3339(),id])?;
        ensure(changed == 1, "INVOICE_STATE_INVALID")
    }
    pub fn status(&self, settings: &Settings, now: DateTime<Utc>) -> Result<Value> {
        let c = self.connect()?;
        let recent: Option<(String, String)> = c
            .query_row(
                // EOD rows record scheduling/deduplication decisions. Task state
                // is authoritative for execution, including existing queued
                // markers written before an earlier process completed/crashed.
                "SELECT e.source_day,
                    CASE WHEN t.reason='EOD_SUPERSEDED_SKIPPED' THEN 'skipped_superseded'
                         ELSE COALESCE(t.status,e.disposition) END
                 FROM eod e LEFT JOIN tasks t ON t.trigger_key='eod-v1:'||e.source_day
                 ORDER BY e.source_day DESC LIMIT 1",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        let skipped: i64 = c.query_row(
            "SELECT COUNT(*) FROM eod WHERE disposition LIKE 'skipped%'",
            [],
            |r| r.get(0),
        )?;
        let models=settings.models.iter().map(|m|json!({"id":m.id,"label":m.label,"kind":m.kind,"model":m.model,"endpoint":m.endpoint,
            "authorization":m.authorize(&["owner_task".into()],settings.budget.as_ref()).err().map(|e|e.0).unwrap_or("authorized".into()),
            "price_version":m.price.as_ref().map(|p|&p.version),"verification":if m.kind=="fake"{"FAKE_SYNTHETIC_ONLY"}else{"REAL_PROVIDER_NOT_VERIFIED"}})).collect::<Vec<_>>();
        let mut q=c.prepare("SELECT provider_id,COUNT(*),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COALESCE(SUM(usage_micro),0) FROM calls JOIN tasks ON tasks.id=calls.task_id GROUP BY provider_id")?;
        let usage=q.query_map([],|r|Ok(json!({"provider_id":r.get::<_,String>(0)?,"calls":r.get::<_,i64>(1)?.to_string(),"input_tokens":r.get::<_,i64>(2)?.to_string(),"output_tokens":r.get::<_,i64>(3)?.to_string(),"usage_micro":r.get::<_,i64>(4)?.to_string()})))?.collect::<std::result::Result<Vec<_>,_>>()?;
        Ok(
            json!({"service":"local_research","paused":self.setting("paused")?.as_deref()==Some("true"),"worker_concurrency":"1",
            "default_model":self.setting("default_model")?,"backup_model":self.setting("backup_model")?,"automatic_fallback":"disabled_explicit_owner_switch_required",
            "models":models,"budget":budget::view(&c,settings.budget.as_ref(),now)?,"usage_by_model":usage,
            "eod":{"enabled":self.setting("eod_enabled")?.as_deref()==Some("true"),"latest":recent.map(|(d,s)|json!({"source_day":d,"disposition":s})),"skipped":skipped.to_string(),"reason":self.setting("eod_reason")?},
            "qualification":"EXPLORATORY_NOT_INDEPENDENT","budget_settings":"local_owner_configuration_only"}),
        )
    }
}
