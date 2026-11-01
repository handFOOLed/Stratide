//! Local bridge for scripts/eod-auto-research.py. No shell, clock flag or HTTP.
use chrono::{DateTime, Timelike, Utc};
use rusqlite::OptionalExtension;
use serde_json::{json, Value};
use std::{fs, path::PathBuf};
use stratide_research::{
    config::Settings,
    ensure,
    eod_snapshot::{self, SnapshotSource},
    Agent, InputSummary, Result, TaskRequest,
};

fn root(name: &str) -> Result<PathBuf> {
    ensure(eod_snapshot::valid_name(name), "AUTO_NAME_INVALID")?;
    let root = eod_snapshot::repository_root()
        .join("state/eod-auto")
        .join(name);
    for file in [
        "config.json",
        "agent/settings.json",
        "agent/agent.sqlite",
        "agent/agent.sqlite-wal",
        "agent/agent.sqlite-shm",
        "agent/agent.lock",
        "agent/owner-token",
    ] {
        eod_snapshot::no_links(&root.join(file))?;
    }
    Ok(root)
}

fn current(store: &str, now: DateTime<Utc>) -> Result<InputSummary> {
    let input = SnapshotSource::named(store)?.read(now.timestamp_millis())?;
    let market = now.with_timezone(&chrono_tz::Asia::Shanghai);
    ensure(market.hour() >= 16, "BEFORE_EOD_WINDOW")?;
    ensure(
        input.source_day == market.format("%Y-%m-%d").to_string(),
        "MISSED_OR_STALE",
    )?;
    for key in ["observed_at", "received_at", "available_at"] {
        let ms = input.summary[key].as_i64().ok_or("SNAPSHOT_TIME_INVALID")?;
        let t = DateTime::from_timestamp_millis(ms)
            .ok_or("SNAPSHOT_TIME_INVALID")?
            .with_timezone(&chrono_tz::Asia::Shanghai);
        ensure(
            t.format("%Y-%m-%d").to_string() == input.source_day && t.hour() >= 16,
            "MISSED_OR_STALE",
        )?;
    }
    ensure(
        input.summary["quality"]["coverage"]
            .as_array()
            .is_some_and(|rows| {
                rows.iter().any(|r| {
                    r["source_day"] == input.source_day.replace('-', "")
                        && r["state"] == "valid_eod"
                })
            }),
        "NO_VALID_CURRENT_EOD",
    )?;
    Ok(input)
}

fn run(args: &[String], now: DateTime<Utc>) -> Result<Value> {
    ensure(
        args.len() == 2,
        "usage: eod-auto-agent <init|intent|queue|tick> <auto-name>",
    )?;
    let dir = root(&args[1])?;
    let config: Value = serde_json::from_slice(
        &fs::read(dir.join("config.json")).map_err(|_| "AUTO_CONFIG_MISSING")?,
    )
    .map_err(|_| "AUTO_CONFIG_INVALID")?;
    let binding = config["binding_sha256"]
        .as_str()
        .ok_or("AUTO_BINDING_INVALID")?;
    let store = config["snapshot_store_name"]
        .as_str()
        .ok_or("AUTO_CONFIG_INVALID")?;
    let agent_dir = dir.join("agent");
    if args[0] == "init" {
        fs::create_dir(&agent_dir).map_err(|_| "NEW_AGENT_DIRECTORY_REQUIRED")?;
        fs::write(
            agent_dir.join("settings.json"),
            serde_json::to_vec_pretty(&Settings::fake()).unwrap(),
        )
        .map_err(|_| "AUTO_INIT_IO")?;
    } else {
        ensure(
            agent_dir.join("agent.sqlite").is_file(),
            "AUTO_INIT_INCOMPLETE",
        )?;
    }
    let settings = Settings::load_eod_auto(&agent_dir.join("settings.json"))?;
    let selected = settings
        .models
        .iter()
        .find(|m| Some(&m.id) == settings.default_model.as_ref())
        .ok_or("DEFAULT_MODEL_UNCONFIGURED")?;
    selected.authorize(
        &["owner_task".into(), eod_snapshot::SCOPE.into()],
        settings.budget.as_ref(),
    )?;
    if args[0] == "check" {
        return Ok(json!({"state":"LOCAL_FAKE_ONLY"}));
    }
    let blank = InputSummary {
        version: "eod-auto:no-input".into(),
        source_day: String::new(),
        mode: "no_input".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    };
    // Opening is the original Agent recovery path and holds its exclusive lock.
    let agent = Agent::open(&agent_dir, None, blank)?;
    if args[0] == "init" {
        agent.store().set("eod_auto_binding", binding)?;
        agent.store().set("eod_auto_enabled", "false")?;
        return Ok(json!({"state":"INITIALIZED","enabled":false}));
    }
    ensure(
        agent.store().setting("eod_auto_binding")?.as_deref() == Some(binding),
        "AUTO_BINDING_CHANGED",
    )?;
    ensure(
        agent.store().setting("eod_auto_enabled")?.as_deref() == Some("true"),
        "OWNER_DISABLED",
    )?;
    ensure(
        agent.store().setting("paused")?.as_deref() != Some("true"),
        "OWNER_PAUSED",
    )?;
    let input = current(store, now)?;
    let selected = agent
        .store()
        .setting("default_model")?
        .ok_or("DEFAULT_MODEL_UNCONFIGURED")?;
    let model = settings
        .models
        .iter()
        .find(|m| m.id == selected)
        .ok_or("DEFAULT_MODEL_UNAVAILABLE")?;
    ensure(
        model.fake_scenario.as_deref() != Some("safe_transient"),
        "EOD_AUTO_SINGLE_ATTEMPT_REQUIRED",
    )?;
    model.authorize(&input.scopes, settings.budget.as_ref())?;
    let key = format!("eod-auto-v1:{binding}:{}", input.source_day);
    let meta = format!("eod_auto_intent:{}", input.source_day);
    if args[0] == "intent" && agent.store().setting(&meta)?.is_none() {
        agent
            .store()
            .set(&meta, &json!({"trigger_key":key,"input":input}).to_string())?;
    }
    let intent: Value =
        serde_json::from_str(&agent.store().setting(&meta)?.ok_or("AUTO_INTENT_MISSING")?)
            .map_err(|_| "AUTO_INTENT_INVALID")?;
    ensure(intent["trigger_key"] == key, "AUTO_BINDING_CHANGED")?;
    let id: Option<i64> = agent
        .store()
        .connect()?
        .query_row("SELECT id FROM tasks WHERE trigger_key=?1", [&key], |r| {
            r.get(0)
        })
        .optional()?;
    // Existing daily tasks always win over a later revision. No replacement.
    if args[0] == "intent" {
        return Ok(json!({"state":"INTENT_RECORDED","task_id":id.map(|i| i.to_string())}));
    }
    ensure(
        serde_json::to_value(&input).is_ok_and(|v| v == intent["input"]),
        "SOURCE_CHANGED_REVIEW_REQUIRED",
    )?;
    let id = if let Some(id) = id {
        id
    } else {
        ensure(args[0] == "queue", "AUTO_TASK_MISSING")?;
        let request = TaskRequest {
            name: format!("EOD 自动本地研究 · {}", input.source_day),
            goal: "根据冻结 EOD 摘要提出可核查假设、依据、反证和下一研究步骤。".into(),
            scope: "LOCAL_FAKE_ONLY / RESEARCH_ONLY / 原始 on-day EOD".into(),
            start_day: input.source_day.clone(),
            end_day: input.source_day.clone(),
            task_budget_micro: None,
        };
        agent
            .store()
            .create(&settings, &request, &input, now, Some(&key))?
    };
    if args[0] == "tick" {
        // tick rechecks persisted pause, authorization and TST budget, and uses
        // the input already frozen in tasks. Never calls start/background work.
        agent.tick(now)?;
    } else {
        ensure(args[0] == "queue", "AUTO_COMMAND_INVALID")?;
    }
    agent.store().task(id)
}

fn output(result: Result<Value>) -> (i32, Value) {
    match result {
        Ok(value) => (0, value),
        Err(error) => (
            2,
            json!({"error_code":error.0,
        "can_execute_forward_paper":false,"live_allowed":false}),
        ),
    }
}

fn main() {
    let (code, value) = output(run(
        &std::env::args().skip(1).collect::<Vec<_>>(),
        Utc::now(),
    ));
    println!("{value}");
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;

    #[test]
    fn fixture_cli() {
        // Only the libtest executable has an injected clock. The public binary
        // has no flag or environment-variable clock override.
        if std::env::var("STRATIDE_AUTO_FIXTURE_TEST").as_deref() != Ok("1") {
            return;
        }
        let mut request = String::new();
        std::io::stdin().read_to_string(&mut request).unwrap();
        let request: Value = serde_json::from_str(&request).unwrap();
        let args: Vec<String> = serde_json::from_value(request["args"].clone()).unwrap();
        assert!(args[1].starts_with("auto-test-"));
        let dir = root(&args[1]).unwrap();
        let config: Value =
            serde_json::from_slice(&fs::read(dir.join("config.json")).unwrap()).unwrap();
        let clock = DateTime::from_timestamp_millis(request["now_ms"].as_i64().unwrap()).unwrap();
        assert!(config["snapshot_store_name"]
            .as_str()
            .unwrap()
            .starts_with("auto-test-"));
        // Inspect the original restricted synthetic fixture, without opening a
        // damaged snapshot WAL before the actual reader can reject it.
        let path = PathBuf::from(request["fixture_source"].as_str().unwrap());
        assert!(path.starts_with(eod_snapshot::repository_root().join("state/eod-auto-tests")));
        eod_snapshot::no_links(&path).unwrap();
        let db =
            rusqlite::Connection::open_with_flags(path, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)
                .unwrap();
        let genesis: String = db
            .query_row("SELECT payload FROM events WHERE seq=0", [], |r| r.get(0))
            .unwrap();
        assert_eq!(
            serde_json::from_str::<Value>(&genesis).unwrap()["host"],
            "synthetic_test"
        );
        let (code, value) = output(run(&args, clock));
        println!(
            "EOD_AUTO_FIXTURE_RESULT={}",
            json!({"exit_code":code,"value":value})
        );
    }
}
