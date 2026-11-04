use chrono::{Duration, Utc};
use serde_json::json;
use stratide_research::{config::Settings, Agent, InputSummary, TaskRequest};
fn summary() -> InputSummary {
    InputSummary {
        version: "synthetic_test:desktop".into(),
        source_day: "2026-11-04".into(),
        mode: "synthetic_test".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    }
}
#[test]
fn approvals_expire_revoke_and_consume_once_without_budget_or_cloud() {
    let t = tempfile::tempdir().unwrap();
    std::fs::write(
        t.path().join("settings.json"),
        serde_json::to_vec(&Settings::fake()).unwrap(),
    )
    .unwrap();
    let a = Agent::open(t.path(), None, summary()).unwrap();
    let now = Utc::now();
    let action = json!({"operation":"local_timesfm","batch":"synthetic_test"});
    let id = "a".repeat(32);
    let initial = a.store().desktop_request(&id, &action, now).unwrap();
    assert_eq!(
        a.store().desktop_request(&id, &action, now).unwrap(),
        initial
    );
    assert!(a
        .store()
        .desktop_request(&id, &json!({"operation":"different"}), now)
        .is_err());
    assert!(a.store().desktop_decide(&id, "start", now).is_err());
    a.store().desktop_decide(&id, "approve", now).unwrap();
    a.store().desktop_decide(&id, "revoke", now).unwrap();
    assert!(a.store().desktop_decide(&id, "start", now).is_err());
    let id = "b".repeat(32);
    a.store().desktop_request(&id, &action, now).unwrap();
    assert_eq!(
        a.store().desktop_inbox(now + Duration::hours(2)).unwrap()["approvals"][0]["status"],
        "expired"
    );
    assert!(a
        .store()
        .desktop_decide(&id, "approve", now + Duration::hours(2))
        .is_err());
    let id = "c".repeat(32);
    a.store().desktop_request(&id, &action, now).unwrap();
    a.store().desktop_decide(&id, "approve", now).unwrap();
    a.store().desktop_decide(&id, "start", now).unwrap();
    assert!(a.store().desktop_decide(&id, "start", now).is_err());
    a.store().desktop_recover().unwrap();
    assert!(a.store().desktop_decide(&id, "start", now).is_err());
    assert_eq!(
        a.store().desktop_inbox(now).unwrap()["approvals"]
            .as_array()
            .unwrap()
            .iter()
            .find(|v| v["id"] == id)
            .unwrap()["status"],
        "outcome_uncertain"
    );
    let id = "e".repeat(32);
    a.store().desktop_request(&id, &action, now).unwrap();
    a.store().desktop_decide(&id, "approve", now).unwrap();
    a.store().desktop_decide(&id, "start", now).unwrap();
    a.store()
        .desktop_finish(&id, true, "LOCAL_NO_BILLING", now)
        .unwrap();
    assert_eq!(
        a.store()
            .connect()
            .unwrap()
            .query_row("SELECT COUNT(*) FROM calls", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        0
    );
}
#[test]
fn attached_dashboard_does_not_own_worker_lock_or_recover_history() {
    let t = tempfile::tempdir().unwrap();
    let a = Agent::open(t.path(), None, summary()).unwrap();
    drop(a);
    let attached = Agent::attach(t.path(), None, summary()).unwrap();
    let writer = Agent::open(t.path(), None, summary()).unwrap();
    assert_eq!(
        attached.status(Utc::now()).unwrap()["dashboard_mode"],
        "attached_explicit_operations"
    );
    assert!(attached
        .control("eod", &json!({"enabled":true}), Utc::now())
        .is_err());
    drop(writer);
}
#[test]
fn duplicate_task_request_is_one_task_and_changed_request_is_rejected() {
    let t = tempfile::tempdir().unwrap();
    std::fs::write(
        t.path().join("settings.json"),
        serde_json::to_vec(&Settings::fake()).unwrap(),
    )
    .unwrap();
    let a = Agent::open(t.path(), None, summary()).unwrap();
    let mut r = TaskRequest {
        name: "synthetic test".into(),
        goal: "check costs".into(),
        scope: "owner".into(),
        start_day: "2026-11-04".into(),
        end_day: "2026-11-04".into(),
        task_budget_micro: None,
    };
    let key = "d".repeat(32);
    let now = Utc::now();
    let id = a.create_once(&r, &key, now).unwrap();
    assert_eq!(a.create_once(&r, &key, now).unwrap(), id);
    r.name = "different".into();
    assert!(a.create_once(&r, &key, now).is_err());
    assert_eq!(
        a.store()
            .connect()
            .unwrap()
            .query_row("SELECT COUNT(*) FROM tasks", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        1
    );
    assert_eq!(
        a.store()
            .connect()
            .unwrap()
            .query_row("SELECT COUNT(*) FROM calls", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        0
    );
}
#[test]
fn read_receipts_cover_only_the_displayed_completed_tasks() {
    let t = tempfile::tempdir().unwrap();
    std::fs::write(
        t.path().join("settings.json"),
        serde_json::to_vec(&Settings::fake()).unwrap(),
    )
    .unwrap();
    let a = Agent::open(t.path(), None, summary()).unwrap();
    let now = Utc::now();
    let r = TaskRequest {
        name: "synthetic_test".into(),
        goal: "read receipt".into(),
        scope: "owner".into(),
        start_day: "2026-11-04".into(),
        end_day: "2026-11-04".into(),
        task_budget_micro: None,
    };
    let old = a.create(&r, now).unwrap();
    let new = a.create(&r, now).unwrap();
    a.store()
        .finish(new, "completed", "SYNTHETIC_TEST", None, now)
        .unwrap();
    a.store().desktop_mark_read(&[new]).unwrap();
    a.store()
        .finish(old, "completed", "SYNTHETIC_TEST", None, now)
        .unwrap();
    let inbox = a.store().desktop_inbox(now).unwrap();
    let notices = inbox["notifications"].as_array().unwrap();
    let old_id = old.to_string();
    let new_id = new.to_string();
    assert_eq!(
        notices.iter().find(|n| n["id"] == old_id).unwrap()["read"],
        false
    );
    assert_eq!(
        notices.iter().find(|n| n["id"] == new_id).unwrap()["read"],
        true
    );
}
