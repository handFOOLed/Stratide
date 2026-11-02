//! Compiled only by libtest. The installed CLI has no clock/transport/fault override.
use crate::{risk_portfolio as rp, Agent, InputSummary};
use serde_json::{json, Value};
use std::{
    fs,
    io::Read,
    time::{Duration, Instant},
};

pub fn fault(point: &str) {
    let Ok(encoded) = std::env::var("STRATIDE_RP_TEST_FAULT") else {
        return;
    };
    let v: Value = serde_json::from_str(&encoded).unwrap();
    if v["point"] != point {
        return;
    }
    let batch = v["batch"].as_str().unwrap();
    assert!(batch.starts_with("rp-test-") && crate::eod_snapshot::valid_name(batch));
    let path = rp::root().unwrap().join(batch);
    fs::write(path.join("test-marker"), point).unwrap();
    if v["behavior"] == "kill" {
        std::process::exit(86)
    }
    let start = Instant::now();
    while !path.join("test-release").is_file() {
        assert!(start.elapsed() < Duration::from_secs(45));
        std::thread::sleep(Duration::from_millis(10));
    }
}
#[test]
fn process_driver() {
    if std::env::var("STRATIDE_RP_TEST_DRIVER").as_deref() != Ok("1") {
        return;
    }
    let mut encoded = String::new();
    std::io::stdin().read_to_string(&mut encoded).unwrap();
    let v: Value = serde_json::from_str(&encoded).unwrap();
    let name = v["batch"].as_str().unwrap();
    assert!(name.starts_with("rp-test-") && crate::eod_snapshot::valid_name(name));
    let agent = Agent::open(
        &rp::agent_dir().unwrap(),
        None,
        InputSummary {
            version: "fixture".into(),
            source_day: String::new(),
            mode: "no_input".into(),
            scopes: vec!["owner_task".into()],
            summary: json!({}),
            eod_eligible: false,
        },
    )
    .unwrap();
    if v["hold_lock"] == true {
        fault("holding_lock");
        return;
    }
    let id = v["task_id"].as_i64().unwrap();
    let trigger: String = agent
        .store()
        .connect()
        .unwrap()
        .query_row("SELECT trigger_key FROM tasks WHERE id=?1", [id], |r| {
            r.get(0)
        })
        .unwrap();
    assert!(trigger.starts_with(&format!("{}:{}:", rp::POLICY, name)));
    agent.tick_task(chrono::Utc::now(), id, &trigger).unwrap();
    println!("RP_RESULT={}", agent.store().task(id).unwrap());
}
