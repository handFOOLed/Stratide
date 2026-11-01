//! Fixed local bridge into the existing Agent, Store, Provider and Budget Gate.
use chrono::{DateTime, Utc};
use rusqlite::OptionalExtension;
use serde_json::{json, Value};
use std::{fs, path::Path};
use stratide_research::{
    config::Settings, ensure, eod_snapshot, multimodal as mm, Agent, InputSummary, Result,
    TaskRequest,
};

fn read(path: &Path, max: u64) -> Result<Value> {
    eod_snapshot::no_links(path)?;
    ensure(
        fs::metadata(path).is_ok_and(|m| m.is_file() && m.len() <= max),
        "MULTIMODAL_FILE_SIZE",
    )?;
    serde_json::from_slice(&fs::read(path).map_err(|_| "MULTIMODAL_FILE_MISSING")?)
        .map_err(|_| "MULTIMODAL_FILE_INVALID".into())
}

fn run(args: &[String], now: DateTime<Utc>) -> Result<Value> {
    ensure(
        (2..=3).contains(&args.len()) && eod_snapshot::valid_name(&args[1]),
        "MULTIMODAL_ARGUMENTS",
    )?;
    let root = mm::state_root()?;
    let dir = root.join(&args[1]);
    let config = read(&dir.join("config.json"), 8192)?;
    ensure(
        config["policy"] == mm::POLICY
            && config["agent_dir"] == ".agent"
            && config["name"] == args[1]
            && config["checkout_root"]
                == eod_snapshot::repository_root().to_string_lossy().as_ref(),
        "MULTIMODAL_CONFIG",
    )?;
    let agent_dir = root.join(".agent");
    let settings_path = agent_dir.join("settings.json");
    for file in [
        "settings.json",
        "agent.sqlite",
        "agent.sqlite-wal",
        "agent.sqlite-shm",
        "agent.sqlite-journal",
        "agent.lock",
        "owner-token",
    ] {
        eod_snapshot::no_links(&agent_dir.join(file))?;
    }
    if args[0] == "init" && !settings_path.exists() {
        ensure(!agent_dir.exists(), "MULTIMODAL_AGENT_INIT_INCOMPLETE")?;
        fs::create_dir(&agent_dir).map_err(|_| "MULTIMODAL_AGENT_INIT")?;
        let mut settings = Settings::fake();
        settings
            .models
            .retain(|m| m.fake_scenario.as_deref() != Some("safe_transient"));
        fs::write(
            &settings_path,
            serde_json::to_vec_pretty(&settings).unwrap(),
        )
        .map_err(|_| "MULTIMODAL_AGENT_INIT")?;
    }
    // Raw fake-only checks precede Agent open, key lookup, recovery or any DNS.
    let settings = Settings::load_multimodal(&settings_path)?;
    let blank = InputSummary {
        version: "multimodal:no-input".into(),
        source_day: String::new(),
        mode: "no_input".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    };
    let agent = Agent::open(&agent_dir, None, blank)?;
    if args[0] == "init" {
        agent.store().set("multimodal_agent_v1", mm::POLICY)?;
        let key = format!("mm_enabled:{}", args[1]);
        if agent.store().setting(&key)?.is_none() {
            agent.store().set(&key, "false")?;
        }
        return Ok(json!({"state":"INITIALIZED","enabled":false,"contract":mm::public_contract()}));
    }
    ensure(
        agent.store().setting("multimodal_agent_v1")?.as_deref() == Some(mm::POLICY),
        "MULTIMODAL_AGENT_BINDING",
    )?;
    ensure(
        args.len() == 3 && args[2].len() == 64 && args[2].bytes().all(|c| c.is_ascii_hexdigit()),
        "MULTIMODAL_TASK_KEY",
    )?;
    let input_path = dir
        .join("experiments")
        .join(&args[2])
        .join("fusion-input.json");
    let input: InputSummary =
        serde_json::from_value(read(&input_path, 32768)?).map_err(|_| "MULTIMODAL_INPUT_SCHEMA")?;
    let summary = mm::validate_input(&input, now)?;
    ensure(
        summary.task_id == args[2]
            && Some(summary.source_identity.as_str()) == config["source_identity_sha256"].as_str(),
        "MULTIMODAL_BINDING_CHANGED",
    )?;
    let claim = agent
        .store()
        .setting(&format!("mm_source_owner:{}", summary.source_identity))?;
    ensure(
        claim.as_deref() == Some(&args[1]),
        "MULTIMODAL_SOURCE_OWNED",
    )?;
    let trigger = format!("multimodal-v1:{}:{}", args[1], args[2]);
    mm::require_enabled(&agent.store().connect()?, Some(&trigger))?;
    let prior: Option<i64> = agent
        .store()
        .connect()?
        .query_row(
            "SELECT id FROM tasks WHERE trigger_key=?1",
            [&trigger],
            |r| r.get(0),
        )
        .optional()?;
    if let Some(id) = prior {
        let saved = agent.store().task(id)?;
        ensure(
            saved["input"] == serde_json::to_value(&input).unwrap(),
            "MULTIMODAL_INPUT_CHANGED",
        )?;
        if saved["status"] != "queued" || args[0] == "queue" {
            return Ok(saved);
        }
    }
    // Any NEW inference must still be bound to the current original PR33 SHA.
    let current = eod_snapshot::SnapshotSource::named(
        config["snapshot_store_name"]
            .as_str()
            .ok_or("MULTIMODAL_CONFIG")?,
    )?
    .read(now.timestamp_millis())?;
    ensure(
        current.summary["snapshot_sha256"] == summary.input_snapshot_sha256
            && current.source_day == input.source_day
            && current.mode == input.mode,
        "MULTIMODAL_SNAPSHOT_CHANGED",
    )?;
    let day = now
        .with_timezone(&chrono_tz::Asia::Shanghai)
        .format("%Y%m%d")
        .to_string();
    ensure(
        day == summary.source_day
            && chrono::Timelike::hour(&now.with_timezone(&chrono_tz::Asia::Shanghai)) >= 16,
        "MISSED_OR_STALE",
    )?;
    let plan = read(
        &dir.join("experiments").join(&args[2]).join("input.json"),
        2 * 1024 * 1024,
    )?;
    let fusion = &plan["plan"]["fusion"];
    let model_id = fusion["provider_id"]
        .as_str()
        .ok_or("FUSION_MODEL_REQUIRED")?;
    let model = settings
        .models
        .iter()
        .find(|m| m.id == model_id)
        .ok_or("PINNED_MODEL_UNAVAILABLE")?;
    ensure(
        fusion["provider_hash"] == model.fingerprint() && fusion["model"] == model.model,
        "PINNED_MODEL_CONFIGURATION_CHANGED",
    )?;
    model.authorize(&input.scopes, settings.budget.as_ref())?;
    let id = if let Some(id) = prior {
        id
    } else {
        ensure(args[0] == "queue", "MULTIMODAL_TASK_MISSING")?;
        // Original selection + exclusive Agent lock; no second queue or bill.
        agent.store().set("default_model", model_id)?;
        let request = TaskRequest { name: format!("Time-Series + Fusion · {}", input.source_day),
            goal: "针对已核验的独立时序证据与基线，输出可证伪研究假设、正反依据、风险、下一实验与局限。".into(),
            scope: "multimodal_research_v1 / LOCAL_FAKE_ONLY / RESEARCH_ONLY".into(),
            start_day: input.source_day.clone(), end_day: input.source_day.clone(), task_budget_micro: None };
        agent
            .store()
            .create(&settings, &request, &input, now, Some(&trigger))?
    };
    ensure(
        matches!(args[0].as_str(), "queue" | "tick"),
        "MULTIMODAL_COMMAND",
    )?;
    if args[0] == "tick" {
        agent.tick(now)?;
    }
    agent.store().task(id)
}

fn output(value: Result<Value>) -> (i32, Value) {
    match value {
        Ok(v) => (0, v),
        Err(e) => (
            2,
            json!({"error_code":e.0,"can_execute_forward_paper":false,"live_allowed":false}),
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
