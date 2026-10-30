//! Headless, one explicit local-fake research task. Uses the real Agent lifecycle.
use chrono::Utc;
use serde_json::{json, Value};
use std::{fs, path::PathBuf};
use stratide_research::{
    config::Settings,
    ensure,
    eod_snapshot::{self, SnapshotSource},
    Agent, InputSummary, Result, TaskRequest,
};

fn run_dir(name: &str) -> Result<PathBuf> {
    ensure(eod_snapshot::valid_name(name), "AGENT_RUN_NAME")?;
    let dir = eod_snapshot::repository_root()
        .join("state/eod-agent")
        .join(name);
    eod_snapshot::no_links(&dir)?;
    Ok(dir)
}
fn run(args: &[String]) -> Result<Value> {
    match args
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>()
        .as_slice()
    {
        ["summary", store] => {
            let input = SnapshotSource::named(store)?.read(Utc::now().timestamp_millis())?;
            serde_json::to_value(input).map_err(|_| "INPUT_INVALID".into())
        }
        ["run", store, name] => {
            let source = SnapshotSource::named(store)?;
            let input = source.read(Utc::now().timestamp_millis())?;
            let dir = run_dir(name)?;
            fs::create_dir_all(dir.parent().unwrap()).map_err(|_| "AGENT_RUN_UNAVAILABLE")?;
            // Never overwrite an existing task/fee database or Owner configuration.
            fs::create_dir(&dir).map_err(|_| "NEW_AGENT_RUN_REQUIRED")?;
            fs::write(
                dir.join("settings.json"),
                serde_json::to_vec_pretty(&Settings::fake()).unwrap(),
            )
            .map_err(|_| "AGENT_RUN_UNAVAILABLE")?;
            let day = input.source_day.clone();
            let agent = Agent::open(&dir, None, input)?
                .with_summary_source(move || source.read(Utc::now().timestamp_millis()));
            let id = agent.create(
                &TaskRequest {
                    name: "EOD 快照显式本地研究".into(),
                    goal: "根据冻结摘要提出可核查假设、反证和下一步；保留数据来源与局限。".into(),
                    scope: "仅所选 EOD 研究摘要；本地 fake".into(),
                    start_day: day.clone(),
                    end_day: day,
                    task_budget_micro: None,
                },
                Utc::now(),
            )?;
            agent.tick(Utc::now())?;
            let task = agent.store().task(id)?;
            ensure(task["status"] == "completed", "FAKE_RESEARCH_NOT_COMPLETED")?;
            Ok(task)
        }
        ["task", name, id] => {
            let dir = run_dir(name)?;
            ensure(dir.join("agent.sqlite").is_file(), "AGENT_RUN_NOT_FOUND")?;
            let settings = Settings::load(&dir.join("settings.json"))?;
            ensure(
                settings.models.iter().all(|m| m.kind == "fake"),
                "LOCAL_FAKE_RUN_REQUIRED",
            )?;
            let input = InputSummary {
                version: "paper-summary-v1:no-input".into(),
                source_day: String::new(),
                mode: "no_input".into(),
                scopes: vec!["owner_task".into()],
                summary: json!({"paper":"not_configured"}),
                eod_eligible: false,
            };
            // Reopen only this CLI's isolated run, using the existing restart path.
            let agent = Agent::open(&dir, None, input)?;
            agent
                .store()
                .task(id.parse::<i64>().map_err(|_| "TASK_ID_INVALID")?)
        }
        _ => Err(
            "usage: eod-research summary <store> | run <store> <new-run> | task <run> <id>".into(),
        ),
    }
}
fn main() {
    match run(&std::env::args().skip(1).collect::<Vec<_>>()) {
        Ok(value) => println!("{}", serde_json::to_string(&value).unwrap()),
        Err(error) => {
            println!(
                "{}",
                json!({"error_code":error.0,"can_execute_forward_paper":false,"live_allowed":false})
            );
            std::process::exit(2);
        }
    }
}
