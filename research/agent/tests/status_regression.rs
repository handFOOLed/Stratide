//! Backend-only regressions for the frozen Agent status response.
use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use std::fs;
use stratide_research::{config::Settings, Agent, InputSummary, TaskRequest};

fn now() -> DateTime<Utc> {
    "2026-10-29T09:00:00Z".parse().unwrap()
}
fn input() -> InputSummary {
    InputSummary {
        version: "status-regression-v1".into(),
        source_day: "2026-10-29".into(),
        mode: "historical_replay".into(),
        scopes: vec!["owner_task".into(), "paper_summary_v1".into()],
        summary: json!({"source":"synthetic_test_fixture_only"}),
        eod_eligible: true,
    }
}
fn request() -> TaskRequest {
    TaskRequest {
        name: "后端状态回归".into(),
        goal: "验证任务状态及 Provider 故障归因".into(),
        scope: "本地 fake 摘要".into(),
        start_day: "2026-10-29".into(),
        end_day: "2026-10-29".into(),
        task_budget_micro: None,
    }
}
fn setup(settings: &Settings) -> (tempfile::TempDir, Agent) {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("settings.json"),
        serde_json::to_vec(settings).unwrap(),
    )
    .unwrap();
    let agent = Agent::open(dir.path(), None, input()).unwrap();
    (dir, agent)
}
fn eod(agent: &Agent, settings: &Settings) -> i64 {
    agent
        .control("eod", &json!({"enabled":true}), now())
        .unwrap();
    agent.schedule_eod(settings, now()).unwrap();
    agent.store().list(None).unwrap()["tasks"][0]["id"]
        .as_str()
        .unwrap()
        .parse()
        .unwrap()
}
fn model(agent: &Agent, id: &str) -> Value {
    agent.status(now()).unwrap()["models"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["id"] == id)
        .unwrap()
        .clone()
}

#[test]
fn eod_latest_reflects_completed_task_and_restart_does_not_schedule_another_call() {
    let settings = Settings::fake();
    let (dir, agent) = setup(&settings);
    let id = eod(&agent, &settings);
    assert_eq!(
        agent.status(now()).unwrap()["eod"]["latest"]["disposition"],
        "queued"
    );
    agent.tick(now()).unwrap();
    assert_eq!(agent.store().task(id).unwrap()["status"], "completed");
    assert_eq!(
        agent.status(now()).unwrap()["eod"]["latest"]["disposition"],
        "completed"
    );
    let calls = agent.status(now()).unwrap()["budget"]["call_count"].clone();
    drop(agent);
    let agent = Agent::open(dir.path(), None, input()).unwrap();
    agent.tick(now()).unwrap();
    assert_eq!(
        agent.status(now()).unwrap()["eod"]["latest"]["disposition"],
        "completed"
    );
    assert_eq!(agent.status(now()).unwrap()["budget"]["call_count"], calls);
}

#[test]
fn eod_latest_reflects_running_cancel_requested_and_cancelled() {
    let settings = Settings::fake();
    let (_dir, agent) = setup(&settings);
    let id = eod(&agent, &settings);
    assert_eq!(agent.store().claim(now()).unwrap(), Some(id));
    assert_eq!(
        agent.status(now()).unwrap()["eod"]["latest"]["disposition"],
        "running"
    );
    agent.store().cancel(id, now()).unwrap();
    assert_eq!(
        agent.status(now()).unwrap()["eod"]["latest"]["disposition"],
        "cancel_requested"
    );
    agent
        .store()
        .finish(
            id,
            "cancelled",
            "OWNER_CANCELLED_BEFORE_REQUEST",
            None,
            now(),
        )
        .unwrap();
    assert_eq!(
        agent.status(now()).unwrap()["eod"]["latest"]["disposition"],
        "cancelled"
    );
}

#[test]
fn eod_failure_and_uncertainty_follow_actual_task_without_releasing_holds() {
    for uncertain in [false, true] {
        let mut settings = Settings::fake();
        if uncertain {
            settings.default_model = Some("fake-unknown".into());
        } else {
            settings.budget.as_mut().unwrap().daily_limit_micro = 1;
        }
        let (_dir, agent) = setup(&settings);
        let id = eod(&agent, &settings);
        agent.tick(now()).unwrap();
        let expected = if uncertain {
            "outcome_uncertain"
        } else {
            "failed"
        };
        assert_eq!(agent.store().task(id).unwrap()["status"], expected);
        let status = agent.status(now()).unwrap();
        assert_eq!(status["eod"]["latest"]["disposition"], expected);
        let held = status["budget"]["reserved_micro"].clone();
        if uncertain {
            assert_ne!(held, "0");
        } else {
            assert_eq!(held, "0");
        }
        agent.tick(now()).unwrap();
        assert_eq!(
            agent.status(now()).unwrap()["budget"]["reserved_micro"],
            held
        );
        assert_eq!(
            agent.store().list(None).unwrap()["tasks"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }
}

#[test]
fn local_budget_authorization_and_price_rejections_are_not_provider_failures() {
    for rejection in ["budget", "grant", "price", "daily", "monthly"] {
        let mut settings = Settings::fake();
        match rejection {
            "budget" => settings.budget = None,
            "grant" => settings.models[0].grant = None,
            "price" => settings.models[0].price = None,
            "daily" => settings.budget.as_mut().unwrap().daily_limit_micro = 1,
            "monthly" => settings.budget.as_mut().unwrap().monthly_limit_micro = 1,
            _ => unreachable!(),
        }
        let (_dir, agent) = setup(&settings);
        let id = agent.create(&request(), now()).unwrap();
        agent.tick(now()).unwrap();
        let task = agent.store().task(id).unwrap();
        assert_eq!(task["status"], "failed");
        assert_eq!(task["calls"], json!([]));
        let status = model(&agent, "fake");
        assert_eq!(status["availability"], "not_verified", "{rejection}");
        assert_eq!(status["last_reason"], Value::Null, "{rejection}");
        assert!(task["reason"].is_string());
    }
}

#[test]
fn local_denial_and_queued_cancellation_preserve_prior_provider_success_or_uncertainty() {
    for provider in ["fake", "fake-unknown"] {
        let mut settings = Settings::fake();
        settings.default_model = Some(provider.into());
        let (_dir, agent) = setup(&settings);
        agent.create(&request(), now()).unwrap();
        agent.tick(now()).unwrap();
        let previous = model(&agent, provider);
        let held = agent.status(now()).unwrap()["budget"]["reserved_micro"].clone();
        let mut capped = request();
        capped.task_budget_micro = Some("1".into());
        let id = agent.create(&capped, now()).unwrap();
        agent.tick(now()).unwrap();
        assert_eq!(
            agent.store().task(id).unwrap()["reason"],
            "TASK_BUDGET_EXHAUSTED"
        );
        let after = model(&agent, provider);
        assert_eq!(after["availability"], previous["availability"]);
        assert_eq!(after["last_reason"], previous["last_reason"]);
        let cancelled = agent.create(&request(), now()).unwrap();
        agent.store().cancel(cancelled, now()).unwrap();
        assert_eq!(
            model(&agent, provider)["last_reason"],
            previous["last_reason"]
        );
        assert_eq!(
            agent.status(now()).unwrap()["budget"]["reserved_micro"],
            held
        );
    }
}

#[test]
fn confirmed_no_charge_provider_rejection_still_marks_provider_unavailable() {
    let mut settings = Settings::fake();
    settings.models[0].fake_scenario = Some("permanent".into());
    let (_dir, agent) = setup(&settings);
    let id = agent.create(&request(), now()).unwrap();
    agent.tick(now()).unwrap();
    assert_eq!(
        agent.store().task(id).unwrap()["calls"][0]["state"],
        "no_charge"
    );
    let status = model(&agent, "fake");
    assert_eq!(status["availability"], "unavailable_or_outcome_unknown");
    assert_eq!(status["last_reason"], "FAKE_PERMANENT_REJECTION");
}

#[test]
fn provider_dns_preparation_failure_is_distinct_from_local_policy_rejection() {
    let (_dir, agent) = setup(&Settings::fake());
    let id = agent.create(&request(), now()).unwrap();
    agent.store().claim(now()).unwrap();
    // Fault injection at the real pre-send failure completion boundary. No DNS
    // lookup or external request is made by this deterministic test.
    agent
        .store()
        .finish(id, "failed", "PROVIDER_DNS_UNAVAILABLE", None, now())
        .unwrap();
    assert_eq!(agent.store().task(id).unwrap()["calls"], json!([]));
    let status = model(&agent, "fake");
    assert_eq!(status["availability"], "unavailable_or_outcome_unknown");
    assert_eq!(status["last_reason"], "PROVIDER_DNS_UNAVAILABLE");
}
