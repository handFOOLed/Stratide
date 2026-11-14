//! Explicit local bridge; the existing Agent owns recovery and paid dispatch.
use serde_json::{json, Value};
use std::io::Read;
use stratide_research::{ensure, local_fusion, market_research as m, Agent, Result};
fn run() -> Result<Value> {
    let action = std::env::args().nth(1).ok_or("MARKET_ARGUMENTS")?;
    let mut raw = Vec::new();
    std::io::stdin()
        .take(8193)
        .read_to_end(&mut raw)
        .map_err(|_| "MARKET_INPUT")?;
    ensure(raw.len() <= 8192, "MARKET_INPUT_SIZE")?;
    let v: Value = serde_json::from_slice(&raw).map_err(|_| "MARKET_INPUT")?;
    let resume_id = match v.get("resume_task_id") {
        None | Some(Value::Null) => None,
        Some(id) => Some(id.as_i64().filter(|id| *id > 0).ok_or("TASK_ID_INVALID")?),
    };
    let b = stratide_research::risk_binding::read()?;
    let agent = if action == "once" || action == "install-model" {
        Agent::open(&b.agent_dir, Some(&b.settings_path), local_fusion::blank())?
    } else {
        Agent::attach(&b.agent_dir, Some(&b.settings_path), local_fusion::blank())?
    };
    match action.as_str() {
        "status" => m::status(&agent),
        "install-model" => m::install_model(&agent),
        "configure" | "grant" | "revoke" | "pause" => m::control(&agent, &action, v),
        "preview" => m::preview(
            &agent,
            v["source_day"].as_str().ok_or("MARKET_DAY_INVALID")?,
        ),
        "once" => m::execute(
            &agent,
            v["source_day"].as_str().ok_or("MARKET_DAY_INVALID")?,
            resume_id,
        ),
        "task" => {
            let task = agent
                .store()
                .task(v["task_id"].as_i64().ok_or("TASK_ID_INVALID")?)?;
            ensure(task["provider_id"] == m::MODEL_ID, "MARKET_TASK_REQUIRED")?;
            Ok(task)
        }
        _ => Err("MARKET_ARGUMENTS".into()),
    }
}
fn main() {
    match run() {
        Ok(v) => println!("{v}"),
        Err(e) => {
            println!("{}", json!({"state":"BLOCKED","error_code":e.0}));
            std::process::exit(2)
        }
    }
}
