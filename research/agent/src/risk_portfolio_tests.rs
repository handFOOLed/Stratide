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
        Some(&rp::settings_path().unwrap()),
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
    if v["legacy"] == true {
        let selected = agent.store().setting("default_model").unwrap().unwrap();
        let now = v["at"]
            .as_str()
            .map(|s| s.parse().unwrap())
            .unwrap_or_else(chrono::Utc::now);
        if let Some(model) = v["model"].as_str() {
            agent
                .control("model", &json!({"model_id":model}), now)
                .unwrap();
        }
        let input = InputSummary {
            version: "original-owner-fixture-v1".into(),
            source_day: now.format("%Y-%m-%d").to_string(),
            mode: "synthetic_test".into(),
            scopes: vec!["owner_task".into()],
            summary: json!({"fixture":"original owner research"}),
            eod_eligible: false,
        };
        let request = crate::TaskRequest {
            name: "Original Owner Agent".into(),
            goal: "Verify shared research spending".into(),
            scope: "owner_task".into(),
            start_day: input.source_day.clone(),
            end_day: input.source_day.clone(),
            task_budget_micro: None,
        };
        let trigger = format!("legacy-owner-fixture:{name}");
        let settings = crate::config::Settings::load(&rp::settings_path().unwrap()).unwrap();
        let id = agent
            .store()
            .create(&settings, &request, &input, now, Some(&trigger))
            .unwrap();
        agent.tick_task(now, id, &trigger).unwrap();
        agent
            .control("model", &json!({"model_id":selected}), chrono::Utc::now())
            .unwrap();
        println!("RP_RESULT={}", agent.store().task(id).unwrap());
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
