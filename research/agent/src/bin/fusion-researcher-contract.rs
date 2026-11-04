//! Offline role/contract inspection. No Agent, key, network, budget or ledger access.
use serde_json::{json, Value};
use std::io::Read;
use stratide_research::{ensure, fusion_researcher as f, risk_portfolio as rp, Result};
fn run() -> Result<Value> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    ensure(args.len() == 1, "FUSION_CONTRACT_ARGUMENTS")?;
    if args[0] == "descriptor" {
        return Ok(f::descriptor());
    }
    ensure(
        matches!(args[0].as_str(), "validate" | "validate-evidence"),
        "FUSION_CONTRACT_ARGUMENTS",
    )?;
    let mut raw = Vec::new();
    std::io::stdin()
        .take(65537)
        .read_to_end(&mut raw)
        .map_err(|_| "FUSION_CONTRACT_READ")?;
    ensure(raw.len() <= 65536, "FUSION_CONTRACT_SIZE")?;
    let v: Value = serde_json::from_slice(&raw).map_err(|_| "FUSION_CONTRACT_JSON")?;
    ensure(
        v.as_object().is_some_and(|m| m.len() == 2),
        "FUSION_CONTRACT_SCHEMA",
    )?;
    let frozen: rp::Frozen =
        serde_json::from_value(v["frozen"].clone()).map_err(|_| "RISK_INPUT_SCHEMA")?;
    ensure(
        frozen.input_mode == "synthetic_test",
        "REAL_MARKET_DATA_EGRESS_DENIED",
    )?;
    if args[0] == "validate-evidence" {
        f::validate_evidence(
            &frozen,
            v["experts"].as_array().ok_or("FUSION_EVIDENCE_SCHEMA")?,
        )?;
        return Ok(json!({"valid":true,"prompt_version":f::VERSION,"billable_calls":0}));
    }
    let response: f::Response =
        serde_json::from_value(v["response"].clone()).map_err(|_| "PORTFOLIO_SCHEMA")?;
    response.portfolio.bind(
        &frozen,
        &[frozen.snapshot_ref.clone(), frozen.strategy_hash()],
    )?;
    f::validate_response(&response)?;
    Ok(
        json!({"valid":true,"prompt_version":f::VERSION,"prompt_sha256":f::prompt_sha(),
        "authority":"RESEARCH_ONLY","billable_calls":0,"paper_allowed":false,"live_allowed":false}),
    )
}
fn main() {
    match run() {
        Ok(v) => println!("{v}"),
        Err(e) => {
            println!("{}", json!({"valid":false,"error_code":e.0}));
            std::process::exit(2)
        }
    }
}
