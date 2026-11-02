//! Fixed bridge: two original Agent tasks in one original daily/monthly Budget Gate.
use chrono::Utc;
use rusqlite::OptionalExtension;
use serde_json::{json, Value};
use std::path::Path;
use stratide_research::{
    config::Settings, ensure, risk_binding as binding, risk_cloud as cloud, risk_portfolio as rp,
    Agent, InputSummary, Result, TaskRequest,
};

fn blank() -> InputSummary {
    InputSummary {
        version: "risk-portfolio:no-input".into(),
        source_day: String::new(),
        mode: "no_input".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    }
}
fn run(args: &[String]) -> Result<Value> {
    ensure(!args.is_empty(), "RISK_ARGUMENTS")?;
    if args[0] == "init" {
        let bound = match args.len() {
            1 => binding::read()?,
            3 if args[1] == "--agent-dir" => binding::bind(Path::new(&args[2]), None)?,
            5 if args[1] == "--agent-dir" && args[3] == "--agent-config" => {
                binding::bind(Path::new(&args[2]), Some(Path::new(&args[4])))?
            }
            _ => return Err("RISK_ARGUMENTS".into()),
        };
        let agent = Agent::open(&bound.agent_dir, Some(&bound.settings_path), blank())?;
        if agent.store().setting("risk_portfolio_enabled")?.is_none() {
            agent.store().set("risk_portfolio_enabled", "false")?;
        }
        return Ok(
            json!({"state":"INITIALIZED","authority_id":bound.authority_id,"enabled":agent.store().setting("risk_portfolio_enabled")?.as_deref()==Some("true"),"scope":rp::SCOPE,"cloud":"CLOUD_NOT_AUTHORIZED","billing":"NOT_BILLED"}),
        );
    }
    let bound = binding::read()?;
    let dir = bound.agent_dir.clone();
    for file in [
        "settings.json",
        "agent.sqlite",
        "agent.sqlite-wal",
        "agent.sqlite-shm",
        "agent.sqlite-journal",
        "agent.lock",
        "owner-token",
    ] {
        stratide_research::eod_snapshot::no_links(&dir.join(file))?;
    }
    let s = Settings::load(&bound.settings_path)?;
    let agent = Agent::open(&dir, Some(&bound.settings_path), blank())?;
    bound.verify(&agent.store().connect()?)?;
    if args[0] == "configure-recorded" {
        ensure(args.len() == 1, "RISK_ARGUMENTS")?;
        binding::add_recorded_models(&bound, binding::recorded_models())?;
        return Ok(
            json!({"state":"RECORDED_MODELS_ADDED","budget":"EXISTING_OWNER_BUDGET_UNCHANGED","authority_id":bound.authority_id}),
        );
    }
    if matches!(args[0].as_str(), "enable" | "disable") {
        ensure(args.len() == 1, "RISK_ARGUMENTS")?;
        agent.store().set(
            "risk_portfolio_enabled",
            if args[0] == "enable" { "true" } else { "false" },
        )?;
        return Ok(
            json!({"enabled":args[0]=="enable","mode":"SYNTHETIC_RECORDED_ONLY","live_allowed":false}),
        );
    }
    if args[0] == "descriptor" {
        return Ok(json!(s.models.iter().map(|m|json!({"id":m.id,"fingerprint":m.fingerprint(),"model":m.model,"kind":m.kind,
            "adapter_sha256":rp::adapter_sha(),"prompt_sha256":rp::prompt_sha(),
            "receiver":m.endpoint,"fields":m.cloud.as_ref().map(|c|&c.fields),"price_version":cloud::price_version(m).ok(),
            "maximum_micro":m.cost(m.max_input_tokens,m.max_output_tokens).ok(),"transport":m.cloud.as_ref().map(|c|&c.transport)})).collect::<Vec<_>>()));
    }
    ensure(
        args.len() == 3
            && matches!(args[0].as_str(), "queue" | "tick")
            && stratide_research::eod_snapshot::valid_name(&args[1])
            && matches!(args[2].as_str(), "risk" | "fusion"),
        "RISK_ARGUMENTS",
    )?;
    let raw = rp::read(&rp::root()?.join(&args[1]).join("frozen.json"), 256 * 1024)?;
    let frozen_sha = rp::sha(&raw);
    let f: rp::Frozen = serde_json::from_value(raw).map_err(|_| "RISK_FROZEN_SCHEMA")?;
    f.validate(Utc::now())?;
    let trigger = format!("{}:{}:{}:{}", rp::POLICY, args[1], frozen_sha, args[2]);
    let db = agent.store().connect()?;
    let risk = if args[2] == "fusion" {
        let id: i64 = db.query_row(
            "SELECT id FROM tasks WHERE trigger_key=?1",
            [format!("{}:{}:{}:risk", rp::POLICY, args[1], frozen_sha)],
            |r| r.get(0),
        )?;
        Some(agent.store().task(id)?)
    } else {
        None
    };
    let t = rp::TaskInput {
        batch: args[1].clone(),
        frozen_sha256: frozen_sha.clone(),
        phase: args[2].clone(),
        risk_task_id: risk.as_ref().and_then(|v| v["id"].as_str()?.parse().ok()),
        risk_result_sha256: if let Some(v) = &risk {
            let encoded: String = db.query_row(
                "SELECT result FROM tasks WHERE id=?1",
                [v["id"].as_str().unwrap()],
                |r| r.get(0),
            )?;
            Some(stratide_research::hash(encoded.as_bytes()))
        } else {
            None
        },
    };
    let input = InputSummary {
        version: format!("{}:{}:{}", rp::SCOPE, frozen_sha, args[2]),
        source_day: f.series[0].observations.last().unwrap().trade_day.clone(),
        mode: f.input_mode.clone(),
        scopes: vec![
            rp::SCOPE.into(),
            if args[2] == "risk" {
                "risk_timeseries_v1".into()
            } else {
                "portfolio_fusion_v1".into()
            },
        ],
        summary: serde_json::to_value(t).unwrap(),
        eod_eligible: false,
    };
    let prior: Option<i64> = db
        .query_row(
            "SELECT id FROM tasks WHERE trigger_key=?1",
            [&trigger],
            |r| r.get(0),
        )
        .optional()?;
    let id = if let Some(id) = prior {
        let prior = agent.store().task(id)?;
        ensure(
            prior["input"] == serde_json::to_value(&input).unwrap(),
            "RISK_EXISTING_TASK_CHANGED",
        )?;
        id
    } else {
        ensure(args[0] == "queue", "RISK_TASK_MISSING")?;
        let owner_key = format!("rp_batch_owner:{frozen_sha}");
        if agent.store().setting(&owner_key)?.is_none() {
            agent.store().set(&owner_key, &args[1])?;
        }
        rp::gate(&db, Some(&trigger), &input, Utc::now(), &s)?;
        let pin = if args[2] == "risk" {
            &f.risk_model
        } else {
            &f.fusion_model
        };
        let request = TaskRequest {
            name: format!("Risk/Portfolio {} {}", args[2], f.strategy_version),
            goal: "Produce bounded research evidence or an autonomous stock/cash target portfolio"
                .into(),
            scope: rp::SCOPE.into(),
            start_day: input.source_day.clone(),
            end_day: input.source_day.clone(),
            task_budget_micro: Some(f.batch_budget_micro.to_string()),
        };
        agent
            .store()
            .create_for_model(&s, &request, &input, Utc::now(), Some(&trigger), &pin.id)?
    };
    if args[0] == "tick" && agent.store().task(id)?["status"] == "queued" {
        agent.tick_task(Utc::now(), id, &trigger)?;
    }
    agent.store().task(id)
}
fn main() {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    match run(&args) {
        Ok(v) => println!("{v}"),
        Err(e) => {
            println!(
                "{}",
                json!({"error_code":e.0,"cloud":"CLOUD_NOT_AUTHORIZED","billing":"NOT_BILLED","live_allowed":false})
            );
            std::process::exit(2);
        }
    }
}
