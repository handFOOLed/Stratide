//! Narrow JSON bridge. The owner CLI holds the original Agent/Worker locks.
use serde_json::{json, Value};
use std::io::Read;
use stratide_research::{ensure, risk_cpu as cpu, risk_portfolio as rp, Result};
fn run() -> Result<Value> {
    let mut raw = Vec::new();
    std::io::stdin()
        .take(524289)
        .read_to_end(&mut raw)
        .map_err(|_| "LOCAL_IPC_READ")?;
    ensure(raw.len() <= 524288, "LOCAL_IPC_SIZE")?;
    let args: Vec<String> = std::env::args().skip(1).collect();
    ensure(args.len() == 1, "LOCAL_ARGUMENTS")?;
    let v: Value = if raw.is_empty() {
        json!({})
    } else {
        serde_json::from_slice(&raw).map_err(|_| "LOCAL_JSON")?
    };
    match args[0].as_str() {
        "descriptor" => Ok(cpu::descriptor()),
        "project" | "evaluate-project" => {
            let plan: cpu::Plan = serde_json::from_value(v).map_err(|_| "LOCAL_PLAN_SCHEMA")?;
            plan.validate(args[0] == "project")?;
            Ok(
                json!({"worker_request_json":plan.request().to_string(),"baselines":rp::baselines(&plan.frozen),"provider_hash":plan.pin()}),
            )
        }
        "decode" | "decode-development" => {
            let plan =
                serde_json::from_value(v["plan"].clone()).map_err(|_| "LOCAL_PLAN_SCHEMA")?;
            let response = serde_json::from_value(v["response"].clone())
                .map_err(|_| "LOCAL_RESPONSE_SCHEMA")?;
            if args[0] == "decode-development" {
                cpu::decode_development(&plan, &response)
            } else {
                cpu::decode(&plan, &response)
            }
        }
        "begin" => cpu::begin(&serde_json::from_value(v).map_err(|_| "LOCAL_PLAN_SCHEMA")?),
        "complete" | "fail" => {
            let plan =
                serde_json::from_value(v["plan"].clone()).map_err(|_| "LOCAL_PLAN_SCHEMA")?;
            let response = v
                .get("response")
                .map(|v| serde_json::from_value(v.clone()).map_err(|_| "LOCAL_RESPONSE_SCHEMA"))
                .transpose()?;
            cpu::finish(
                v["id"].as_i64().ok_or("LOCAL_TASK_ID")?,
                &plan,
                response.as_ref(),
                v["failure"].as_str(),
            )
        }
        "enable" | "disable" => {
            let (_, db) = cpu::connection(true)?;
            db.execute("INSERT INTO meta VALUES('timesfm_cpu_enabled',?1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",[if args[0]=="enable"{"true"}else{"false"}])?;
            Ok(json!({"enabled":args[0]=="enable","billing":"LOCAL_NO_BILLING"}))
        }
        _ => Err("LOCAL_ARGUMENTS".into()),
    }
}
fn main() {
    match run() {
        Ok(v) => println!("{v}"),
        Err(e) => {
            println!(
                "{}",
                json!({"error_code":e.0,"billing":"LOCAL_NO_BILLING","paper_allowed":false,"live_allowed":false})
            );
            std::process::exit(2)
        }
    }
}
