use chrono::Utc;
use serde_json::json;
use std::{
    fs,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};
use stratide_research::{
    config::{Settings, SCOPES},
    eod_snapshot::SCOPE,
    Agent, InputSummary, TaskRequest,
};

fn input() -> InputSummary {
    InputSummary {
        version: format!("eod-agent-input-v1:{}", "a".repeat(64)),
        source_day: "2026-10-29".into(),
        mode: "synthetic_test".into(),
        scopes: vec!["owner_task".into(), SCOPE.into()],
        summary: json!({"restriction":"RESEARCH_ONLY"}),
        eod_eligible: false,
    }
}
fn request() -> TaskRequest {
    TaskRequest {
        name: "显式本地研究".into(),
        goal: "核查快照局限".into(),
        scope: "EOD snapshot".into(),
        start_day: "2026-10-29".into(),
        end_day: "2026-10-29".into(),
        task_budget_micro: None,
    }
}
fn settings(dir: &std::path::Path, s: &Settings) {
    fs::write(dir.join("settings.json"), serde_json::to_vec(s).unwrap()).unwrap();
}

#[test]
fn new_scope_cannot_use_cloud_even_with_copied_or_matching_grant_and_reserves_nothing() {
    let mut legacy = Settings::fake();
    legacy.models[0].grant.as_mut().unwrap().scopes = SCOPES.map(String::from).to_vec();
    assert_eq!(
        legacy.models[0]
            .authorize(&input().scopes, legacy.budget.as_ref())
            .unwrap_err()
            .0,
        "AUTHORIZATION_REQUIRED"
    );
    for matching in [false, true] {
        let mut s = Settings::fake();
        let m = &mut s.models[0];
        m.kind = "chat_completions_v1".into();
        m.endpoint = Some("https://example.com/v1/chat/completions".into());
        m.api_key_env = Some("STRATIDE_RESEARCH_KEY_UNUSED_TEST".into());
        m.fake_scenario = None;
        let grant = m.grant.as_mut().unwrap();
        grant.receiver = m.endpoint.clone().unwrap();
        if !matching {
            grant.scopes = SCOPES.map(String::from).to_vec();
        }
        assert_eq!(
            m.authorize(&input().scopes, s.budget.as_ref())
                .unwrap_err()
                .0,
            "EOD_SNAPSHOT_LOCAL_FAKE_ONLY"
        );
        let dir = tempfile::tempdir().unwrap();
        settings(dir.path(), &s);
        let agent = Agent::open(dir.path(), None, input()).unwrap();
        let id = agent.create(&request(), Utc::now()).unwrap();
        agent.tick(Utc::now()).unwrap();
        let task = agent.store().task(id).unwrap();
        assert_eq!(task["status"], "failed");
        assert_eq!(task["reason"], "EOD_SNAPSHOT_LOCAL_FAKE_ONLY");
        assert_eq!(task["calls"], json!([]));
        let status = agent.status(Utc::now()).unwrap();
        assert_eq!(status["budget"]["reserved_micro"], "0");
        assert_eq!(status["models"][0]["availability"], "not_verified");
    }
}

#[test]
fn local_fake_frozen_task_survives_restart_and_snapshot_never_schedules_eod() {
    let s = Settings::fake();
    let dir = tempfile::tempdir().unwrap();
    settings(dir.path(), &s);
    let agent = Agent::open(dir.path(), None, input()).unwrap();
    agent
        .control("eod", &json!({"enabled":true}), Utc::now())
        .unwrap();
    let id = agent.create(&request(), Utc::now()).unwrap();
    agent.tick(Utc::now()).unwrap();
    let saved = agent.store().task(id).unwrap();
    assert_eq!(saved["status"], "completed");
    assert_eq!(saved["result"]["billing"], "synthetic_test_settled");
    assert_eq!(saved["calls"].as_array().unwrap().len(), 1);
    for _ in 0..2 {
        agent.tick(Utc::now()).unwrap();
    }
    assert_eq!(
        agent.store().list(None).unwrap()["tasks"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        agent.status(Utc::now()).unwrap()["eod"]["reason"],
        "EOD_SNAPSHOT_MANUAL_ONLY"
    );
    drop(agent);
    let agent = Agent::open(dir.path(), None, input()).unwrap();
    agent.tick(Utc::now()).unwrap();
    assert_eq!(saved, agent.store().task(id).unwrap());
    assert_eq!(
        agent.store().list(None).unwrap()["tasks"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}

#[test]
fn snapshot_new_tasks_recheck_within_cache_interval_while_queued_input_stays_frozen() {
    let dir = tempfile::tempdir().unwrap();
    settings(dir.path(), &Settings::fake());
    let blocked = Arc::new(AtomicBool::new(false));
    let source_blocked = blocked.clone();
    let agent = Agent::open(dir.path(), None, input())
        .unwrap()
        .with_summary_source(move || {
            if source_blocked.load(Ordering::SeqCst) {
                Err("SNAPSHOT_SYNC_NOT_SUCCEEDED".into())
            } else {
                Ok(input())
            }
        });
    let id = agent.create(&request(), Utc::now()).unwrap();
    blocked.store(true, Ordering::SeqCst);
    assert_eq!(
        agent.create(&request(), Utc::now()).unwrap_err().0,
        "SNAPSHOT_SYNC_NOT_SUCCEEDED"
    );
    agent.tick(Utc::now()).unwrap();
    assert_eq!(agent.store().task(id).unwrap()["status"], "completed");
}
