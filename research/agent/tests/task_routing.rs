use chrono::Utc;
use serde_json::json;
use stratide_research::{config::Settings, InputSummary, Store, TaskRequest};

#[test]
fn exact_claim_checks_id_and_trigger_without_consuming_the_queue_head() {
    let directory = tempfile::tempdir().unwrap();
    let settings = Settings::fake();
    let store = Store::open(directory.path(), &settings).unwrap();
    let now = Utc::now();
    let input = InputSummary {
        version: "claim-fixture-v1".into(),
        source_day: "2026-11-01".into(),
        mode: "synthetic_test".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    };
    let request = TaskRequest {
        name: "claim fixture".into(),
        goal: "exact task".into(),
        scope: "synthetic".into(),
        start_day: "2026-11-01".into(),
        end_day: "2026-11-01".into(),
        task_budget_micro: None,
    };
    let a = store
        .create(&settings, &request, &input, now, Some("fixture:a"))
        .unwrap();
    let b = store
        .create(&settings, &request, &input, now, Some("fixture:b"))
        .unwrap();
    assert_eq!(store.claim_exact(now, b, "fixture:a").unwrap(), None);
    assert_eq!(store.task(a).unwrap()["status"], "queued");
    assert_eq!(store.task(b).unwrap()["status"], "queued");
    store.set("paused", "true").unwrap();
    assert_eq!(store.claim_exact(now, b, "fixture:b").unwrap(), None);
    store.set("paused", "false").unwrap();
    assert_eq!(store.claim_exact(now, b, "fixture:b").unwrap(), Some(b));
    assert_eq!(store.claim_exact(now, b, "fixture:b").unwrap(), None);
    assert_eq!(store.claim(now).unwrap(), Some(a)); // legacy global selection unchanged
    assert_eq!(store.task(a).unwrap()["calls"], json!([]));
    assert_eq!(store.task(b).unwrap()["calls"], json!([]));
}
