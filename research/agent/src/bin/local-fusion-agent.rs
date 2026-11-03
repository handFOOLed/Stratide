use serde_json::{json, Value};
use stratide_research::{ensure, local_fusion as f, Result};
fn run(a: &[String]) -> Result<Value> {
    ensure(!a.is_empty(), "FUSION_ARGUMENTS")?;
    match (a[0].as_str(), a.len()) {
        ("init-cny", 1) => f::init_cny(),
        ("configure", 2) => f::configure(std::path::Path::new(&a[1])),
        ("budget", 1) => f::budget_status(),
        ("disable", 1) => f::disable(),
        ("capture-model", 2) => f::capture_model(&a[1]),
        ("preflight", 2) => f::preflight(&a[1]),
        ("enable", 2) => f::enable(&a[1]),
        ("once", 2) => f::execute(&a[1], false),
        ("queue", 2) => f::execute(&a[1], true),
        ("status" | "report" | "verify", 2) => f::inspect(&a[1], a[0] == "verify"),
        _ => Err("FUSION_ARGUMENTS".into()),
    }
}
fn main() {
    match run(&std::env::args().skip(1).collect::<Vec<_>>()) {
        Ok(v) => println!("{v}"),
        Err(e) => {
            println!(
                "{}",
                json!({"state":"BLOCKED","error_code":e.0,"paper_allowed":false,"live_allowed":false})
            );
            std::process::exit(2)
        }
    }
}
