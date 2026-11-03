//! Local CLI bridge. Never initializes or replaces an Owner wallet implicitly.
use serde_json::{json, Value};
use std::path::Path;
use stratide_research::{ensure, risk_binding as binding, structured as s, Result};

fn run(args: &[String]) -> Result<Value> {
    ensure(args.len() >= 2, "STRUCTURED_ARGUMENTS")?;
    let root = Path::new(&args[1]);
    match args[0].as_str() {
        "configure-deepseek" if args.len() == 3 => {
            stratide_research::deepseek::configure(root, Path::new(&args[2]))
        }
        "preflight" | "status-deepseek" if args.len() == 2 => {
            stratide_research::deepseek::preflight(root)
        }
        "enable-deepseek" if args.len() == 3 => stratide_research::deepseek::enable(root, &args[2]),
        "disable-deepseek" if args.len() == 2 => stratide_research::deepseek::disable(root),
        "bind" if args.len() == 3 => {
            let b = binding::bind_at(root, Path::new(&args[2]), None)?;
            Ok(json!({"authority_id":b.authority_id,"state":"EXISTING_OWNER_BOUND"}))
        }
        "configure-recorded" if args.len() == 2 => {
            let b = binding::read_at(root)?;
            binding::add_recorded_models(&b, vec![s::recorded_model()])?;
            Ok(
                json!({"state":"RECORDED_MODEL_ADDED","budget":"EXISTING_TST_OWNER_LIMITS_UNCHANGED"}),
            )
        }
        "descriptor" if args.len() == 3 => s::descriptor(root, &args[2]),
        "once" | "queue" if args.len() == 3 => s::execute(
            root,
            args[2].parse().map_err(|_| "STRUCTURED_ROUND")?,
            args[0] == "queue",
        ),
        "cancel" if args.len() == 2 => {
            let b = binding::read_at(root)?;
            let input = stratide_research::InputSummary {
                version: "no-input".into(),
                source_day: String::new(),
                mode: "no_input".into(),
                scopes: vec!["owner_task".into()],
                summary: json!({}),
                eod_eligible: false,
            };
            let a = stratide_research::Agent::open(&b.agent_dir, Some(&b.settings_path), input)?;
            let c = a.store().connect()?;
            let mut q =
                c.prepare("SELECT id,input FROM tasks WHERE status IN ('queued','running')")?;
            let rows = q
                .query_map([], |r| Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?)))?
                .collect::<std::result::Result<Vec<_>, _>>()?;
            let mut cancelled = 0;
            for (id, raw) in rows {
                let i: Value = serde_json::from_str(&raw).map_err(|_| "INPUT_INVALID")?;
                if i["summary"]["experiment"].as_str() == root.to_str() {
                    a.store().cancel(id, chrono::Utc::now())?;
                    cancelled += 1;
                }
            }
            Ok(
                json!({"state":"CANCEL_REQUESTED","task_count":cancelled,"unknown_reservations":"PRESERVED"}),
            )
        }
        _ => Err("STRUCTURED_ARGUMENTS".into()),
    }
}
fn main() {
    match run(&std::env::args().skip(1).collect::<Vec<_>>()) {
        Ok(v) => println!("{v}"),
        Err(e) => {
            println!(
                "{}",
                json!({"state":"BLOCKED","reason":e.0,"paper_allowed":false,"live_allowed":false})
            );
            std::process::exit(2);
        }
    }
}
