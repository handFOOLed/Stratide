use chrono::{DateTime, Utc};
use serde_json::json;
use std::{
    fs,
    sync::{Arc, Barrier},
    thread,
};
use stratide_research::{
    budget::{self, Reservation},
    config::Settings,
    provider, Agent, InputSummary, Store, TaskRequest,
};

fn at(s: &str) -> DateTime<Utc> {
    s.parse().unwrap()
}
fn input() -> InputSummary {
    InputSummary {
        version: "fixture-summary-v1".into(),
        source_day: "2026-10-29".into(),
        mode: "synthetic_test".into(),
        scopes: vec!["owner_task".into(), "paper_summary_v1".into()],
        summary: json!({"simulated_fills":"2"}),
        eod_eligible: false,
    }
}
fn request() -> TaskRequest {
    TaskRequest {
        name: "费用 / 证据核查".into(),
        goal: "核查已发布摘要的费用假设和反证".into(),
        scope: "Paper 摘要".into(),
        start_day: "2026-10-01".into(),
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
fn reserve(
    store: &Store,
    b: &str,
    amount: i64,
    id: i64,
    settings: &Settings,
) -> stratide_research::Result<i64> {
    budget::reserve(
        &mut store.connect()?,
        settings.budget.as_ref().unwrap(),
        at(b),
        Reservation {
            task_id: id,
            maximum_micro: amount,
            task_limit: None,
            price_version: "fixture-v1",
        },
    )
}

#[test]
fn missing_budget_grant_price_and_scope_prevent_any_dispatch() {
    for failure in ["budget", "grant", "price", "scope", "rate", "currency"] {
        let mut s = Settings::fake();
        match failure {
            "budget" => s.budget = None,
            "grant" => s.models[0].grant = None,
            "price" => s.models[0].price = None,
            "scope" => s.models[0].grant.as_mut().unwrap().scopes = vec!["owner_task".into()],
            "rate" => {
                s.models[0]
                    .price
                    .as_mut()
                    .unwrap()
                    .bounded_text_billing_verified = false
            }
            "currency" => s.models[0].price.as_mut().unwrap().currency = "USD".into(),
            _ => unreachable!(),
        }
        let (_dir, a) = setup(&s);
        let now = at("2026-10-29T09:00:00Z");
        let id = a.create(&request(), now).unwrap();
        a.tick(now).unwrap();
        let t = a.store().task(id).unwrap();
        assert_eq!(t["status"], "failed", "{failure}");
        assert_eq!(
            t["calls"],
            json!([]),
            "must fail before network/fee boundary: {failure}"
        );
    }
}

#[test]
fn concurrent_reservations_use_one_cap_and_each_period_enforces_its_own_limit() {
    let mut s = Settings::fake();
    s.budget.as_mut().unwrap().daily_limit_micro = 10;
    s.budget.as_mut().unwrap().monthly_limit_micro = 100;
    let (_dir, a) = setup(&s);
    let now = at("2026-10-29T09:00:00Z");
    let ids = [
        a.create(&request(), now).unwrap(),
        a.create(&request(), now).unwrap(),
    ];
    let barrier = Arc::new(Barrier::new(3));
    let mut threads = vec![];
    for id in ids {
        let store = a.store().clone();
        let settings = s.clone();
        let b = barrier.clone();
        threads.push(thread::spawn(move || {
            b.wait();
            reserve(&store, "2026-10-29T09:00:00Z", 6, id, &settings)
        }));
    }
    barrier.wait();
    let results: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    assert_eq!(results.iter().filter(|r| r.is_ok()).count(), 1);
    assert!(results
        .iter()
        .any(|r| r.as_ref().is_err_and(|e| e.0 == "DAILY_BUDGET_EXHAUSTED")));
    // Independent SQL oracle: two concurrent callers must not hold 12 under 10.
    let held: i64 = a
        .store()
        .connect()
        .unwrap()
        .query_row("SELECT SUM(maximum_micro) FROM calls", [], |r| r.get(0))
        .unwrap();
    assert_eq!(held, 6);
    s.budget.as_mut().unwrap().daily_limit_micro = 100;
    s.budget.as_mut().unwrap().monthly_limit_micro = 10;
    assert_eq!(
        reserve(a.store(), "2026-10-29T09:00:00Z", 5, ids[0], &s)
            .unwrap_err()
            .0,
        "MONTHLY_BUDGET_EXHAUSTED"
    );
}

#[test]
fn unsettled_commitments_carry_across_midnight_month_and_restart_without_currency_timezone_reset() {
    let mut s = Settings::fake();
    s.budget.as_mut().unwrap().daily_limit_micro = 10;
    s.budget.as_mut().unwrap().monthly_limit_micro = 10;
    let (dir, a) = setup(&s);
    let id = a.create(&request(), at("2026-10-31T15:59:00Z")).unwrap();
    let call = reserve(a.store(), "2026-10-31T15:59:00Z", 8, id, &s).unwrap();
    a.store()
        .connect()
        .unwrap()
        .execute("UPDATE calls SET state='dispatched' WHERE id=?1", [call])
        .unwrap();
    drop(a);
    let a = Agent::open(dir.path(), None, input()).unwrap();
    let v = a.status(at("2026-10-31T16:01:00Z")).unwrap();
    assert_eq!(v["budget"]["day"], "2026-11-01");
    assert_eq!(v["budget"]["reserved_micro"], "8");
    assert_eq!(
        reserve(a.store(), "2026-10-31T16:01:00Z", 3, id, &s)
            .unwrap_err()
            .0,
        "DAILY_BUDGET_EXHAUSTED"
    );
    let mut altered = s.clone();
    altered.budget.as_mut().unwrap().timezone = "UTC".into();
    assert!(Store::open(dir.path(), &altered).is_err());
    // Reconciliation uses the original booking period; cannot relabel an invoice.
    a.store()
        .settle(call, 7, "fixture invoice", at("2026-11-01T01:00:00Z"))
        .unwrap();
    let v = a.status(at("2026-10-31T15:59:00Z")).unwrap();
    assert_eq!(v["budget"]["daily_settled_micro"], "7");
}

#[test]
fn safe_no_charge_retries_once_unknown_charge_never_retries_even_after_switch_or_restart() {
    let (dir, a) = setup(&Settings::fake());
    let now = at("2026-10-29T09:00:00Z");
    a.control("model", &json!({"model_id":"fake-safe-retry"}), now)
        .unwrap();
    let safe = a.create(&request(), now).unwrap();
    a.tick(now).unwrap();
    let t = a.store().task(safe).unwrap();
    assert_eq!(t["status"], "completed");
    assert_eq!(t["calls"].as_array().unwrap().len(), 2);
    assert_eq!(t["calls"][0]["state"], "no_charge");
    a.control("model", &json!({"model_id":"fake-unknown"}), now)
        .unwrap();
    let unknown = a.create(&request(), now).unwrap();
    a.tick(now).unwrap();
    let t = a.store().task(unknown).unwrap();
    assert_eq!(t["status"], "outcome_uncertain");
    assert!(!t["retryable"].as_bool().unwrap());
    assert!(a.store().retry(unknown).is_err());
    let held = a.status(now).unwrap()["budget"]["reserved_micro"].clone();
    assert_ne!(held, "0");
    a.control("backup", &json!({"model_id":"fake"}), now)
        .unwrap();
    a.control("model", &json!({"model_id":"fake"}), now)
        .unwrap();
    drop(a);
    let a = Agent::open(dir.path(), None, input()).unwrap();
    a.tick(now).unwrap();
    assert_eq!(
        a.store().task(unknown).unwrap()["calls"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(a.status(now).unwrap()["budget"]["reserved_micro"], held);
}

#[test]
fn queue_cancel_pause_persist_and_running_cancel_keeps_result_and_charges() {
    let (dir, a) = setup(&Settings::fake());
    let now = Utc::now();
    a.control("pause", &json!({}), now).unwrap();
    let queued = a.create(&request(), now).unwrap();
    a.tick(now).unwrap();
    assert_eq!(a.store().task(queued).unwrap()["status"], "queued");
    a.store().cancel(queued, now).unwrap();
    assert_eq!(a.store().task(queued).unwrap()["status"], "cancelled");
    drop(a);
    let a = Agent::open(dir.path(), None, input()).unwrap();
    assert_eq!(a.status(now).unwrap()["paused"], true);
    a.control("resume", &json!({}), now).unwrap();
    a.control("model", &json!({"model_id":"fake-slow"}), now)
        .unwrap();
    let id = a.create(&request(), now).unwrap();
    let worker = a.clone();
    let running = thread::spawn(move || worker.tick(now).unwrap());
    for _ in 0..100 {
        if a.store().task(id).unwrap()["calls"]
            .as_array()
            .unwrap()
            .len()
            == 1
        {
            break;
        }
        thread::sleep(std::time::Duration::from_millis(20));
    }
    a.store().cancel(id, Utc::now()).unwrap();
    assert_eq!(a.store().task(id).unwrap()["status"], "cancel_requested");
    running.join().unwrap();
    let t = a.store().task(id).unwrap();
    assert_eq!(t["status"], "cancelled");
    assert!(t["result"].is_object());
    assert_eq!(t["calls"][0]["state"], "settled");
}

#[test]
fn crash_before_dispatch_is_recoverable_after_dispatch_is_uncertain() {
    for dispatched in [false, true] {
        let s = Settings::fake();
        let (dir, a) = setup(&s);
        let now = Utc::now();
        let id = a.create(&request(), now).unwrap();
        assert_eq!(a.store().claim(now).unwrap(), Some(id));
        let call = reserve(a.store(), "2026-10-29T09:00:00Z", 100, id, &s).unwrap();
        if dispatched {
            a.store()
                .connect()
                .unwrap()
                .execute("UPDATE calls SET state='dispatched' WHERE id=?1", [call])
                .unwrap();
        }
        drop(a);
        let a = Agent::open(dir.path(), None, input()).unwrap();
        let t = a.store().task(id).unwrap();
        assert_eq!(
            t["status"],
            if dispatched {
                "outcome_uncertain"
            } else {
                "queued"
            }
        );
        assert_eq!(
            t["calls"][0]["state"],
            if dispatched {
                "outcome_uncertain"
            } else {
                "no_charge"
            }
        );
        if dispatched {
            a.tick(now).unwrap();
            assert_eq!(
                a.store().task(id).unwrap()["calls"]
                    .as_array()
                    .unwrap()
                    .len(),
                1
            );
        }
    }
}

#[test]
fn new_default_does_not_migrate_queued_tasks_config_revocation_blocks_send_and_task_cap_applies() {
    let s = Settings::fake();
    let (dir, a) = setup(&s);
    let now = Utc::now();
    let original = a.create(&request(), now).unwrap();
    a.control("model", &json!({"model_id":"fake-unknown"}), now)
        .unwrap();
    a.tick(now).unwrap();
    assert_eq!(a.store().task(original).unwrap()["provider_id"], "fake");
    assert_eq!(a.store().task(original).unwrap()["status"], "completed");
    let mut r = request();
    r.task_budget_micro = Some("1".into());
    let capped = a.create(&r, now).unwrap();
    a.tick(now).unwrap();
    assert_eq!(
        a.store().task(capped).unwrap()["reason"],
        "TASK_BUDGET_EXHAUSTED"
    );
    let revoked = a.create(&request(), now).unwrap();
    let mut changed = s;
    changed.models[2].grant.as_mut().unwrap().revoked = true;
    fs::write(
        dir.path().join("settings.json"),
        serde_json::to_vec(&changed).unwrap(),
    )
    .unwrap();
    a.tick(now).unwrap();
    let t = a.store().task(revoked).unwrap();
    assert_eq!(t["status"], "failed");
    assert_eq!(t["calls"], json!([]));
}

#[test]
fn eod_off_stale_synthetic_pause_latest_only_and_crash_marker_deduplication() {
    let s = Settings::fake();
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("settings.json"),
        serde_json::to_vec(&s).unwrap(),
    )
    .unwrap();
    let mut summary = input();
    summary.mode = "historical_replay".into();
    summary.eod_eligible = true;
    let source = Arc::new(std::sync::Mutex::new(summary.clone()));
    let future = source.clone();
    let a = Agent::open(dir.path(), None, summary)
        .unwrap()
        .with_summary_source(move || Ok(future.lock().unwrap().clone()));
    let now = at("2026-10-29T09:00:00Z");
    a.tick(now).unwrap();
    assert!(a.store().list(None).unwrap()["tasks"]
        .as_array()
        .unwrap()
        .is_empty());
    a.control("eod", &json!({"enabled":true}), now).unwrap();
    a.control("pause", &json!({}), now).unwrap();
    a.tick(now).unwrap();
    assert_eq!(a.status(now).unwrap()["eod"]["skipped"], "1");
    source.lock().unwrap().source_day = "2026-10-30".into();
    source.lock().unwrap().version = "next-day".into();
    let next = at("2026-10-30T09:00:00Z");
    a.tick(next).unwrap();
    a.control("resume", &json!({}), next).unwrap();
    a.tick(next).unwrap();
    a.tick(next).unwrap();
    let list = a.store().list(None).unwrap();
    assert_eq!(list["tasks"].as_array().unwrap().len(), 1);
    let id = list["tasks"][0]["id"]
        .as_str()
        .unwrap()
        .parse::<i64>()
        .unwrap();
    a.store()
        .connect()
        .unwrap()
        .execute("DELETE FROM eod WHERE source_day='2026-10-30'", [])
        .unwrap();
    a.tick(next).unwrap();
    assert_eq!(
        a.store().list(None).unwrap()["tasks"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        a.store().task(id).unwrap()["calls"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    a.tick(at("2026-11-02T09:00:00Z")).unwrap();
    assert_eq!(
        a.status(next).unwrap()["eod"]["reason"],
        "NO_NEW_VALID_CURRENT_EOD_SOURCE"
    );
}

#[test]
fn malicious_text_is_data_network_targets_and_generated_tool_payloads_are_rejected() {
    for target in [
        "http://api.example.com/v1/chat/completions",
        "https://127.0.0.1/v1/chat/completions",
        "https://service.local/v1/chat/completions",
        "https://a.example.com:8443/v1/chat/completions",
        "https://user:pass@api.example.com/v1/chat/completions",
        "https://api.example.com/v1/chat/completions?url=internal",
    ] {
        assert!(provider::endpoint(target).is_err(), "{target}");
    }
    for ip in [
        "127.0.0.1",
        "10.2.3.4",
        "169.254.169.254",
        "172.16.1.2",
        "192.168.1.1",
        "100.100.100.200",
        "::1",
        "::ffff:127.0.0.1",
        "fc00::1",
        "fe80::1",
    ] {
        assert!(!provider::public_ip(ip.parse().unwrap()), "{ip}");
    }
    assert!(provider::public_ip("8.8.8.8".parse().unwrap()));
    let output = json!({"choices":[{"message":{"tool_calls":[{"name":"paper-apply"}]}}],"usage":{"prompt_tokens":1,"completion_tokens":1}});
    assert!(matches!(
        provider::decode(output.to_string().as_bytes()),
        provider::Outcome::ChargedFailure { .. }
    ));
    let (dir, a) = setup(&Settings::fake());
    let now = Utc::now();
    a.control("model", &json!({"model_id":"fake-text"}), now)
        .unwrap();
    let id = a.create(&request(), now).unwrap();
    a.tick(now).unwrap();
    assert!(
        a.store().task(id).unwrap()["result"]["research"]["hypothesis"]
            .as_str()
            .unwrap()
            .starts_with("<img")
    );
    assert!(!dir.path().join("secrets").exists());
    assert!(serde_json::from_value::<TaskRequest>(json!({"name":"x","goal":"x","scope":"x","start_day":"2026-10-01","end_day":"2026-10-29","task_budget_micro":null,"shell":"whoami"})).is_err());
}

#[test]
fn price_rounding_invoice_overrun_and_resource_capacity_are_enforced_outside_provider() {
    let mut s = Settings::fake();
    let price = s.models[0].price.as_mut().unwrap();
    price.input_micro_per_million = 500_001;
    price.output_micro_per_million = 1_000_001;
    // Hand-calculated independent oracle: 3*500001+2*1000001 = 3500005,
    // so round UP to 4 micro units. No binary floating point.
    assert_eq!(s.models[0].cost(3, 2).unwrap(), 4);
    s.max_tasks = 1;
    let (_dir, a) = setup(&s);
    let now = Utc::now();
    let id = a.create(&request(), now).unwrap();
    assert_eq!(
        a.create(&request(), now).unwrap_err().0,
        "TASK_STORAGE_LIMIT"
    );
    let call = reserve(a.store(), "2026-10-29T09:00:00Z", 8, id, &s).unwrap();
    a.store()
        .connect()
        .unwrap()
        .execute(
            "UPDATE calls SET state='outcome_uncertain' WHERE id=?1",
            [call],
        )
        .unwrap();
    a.store()
        .settle(call, 9, "verified external invoice", now)
        .unwrap();
    assert_eq!(
        reserve(a.store(), "2026-11-01T09:00:00Z", 1, id, &s)
            .unwrap_err()
            .0,
        "BILLING_OVERRUN_REQUIRES_OWNER"
    );
}

#[test]
fn queued_old_eod_expires_while_switch_off_without_discarding_manual_work() {
    let s = Settings::fake();
    let (_dir, a) = setup(&s);
    let now = at("2026-10-29T09:00:00Z");
    let automatic = a
        .store()
        .create(&s, &request(), &input(), now, Some("eod-v1:2026-10-29"))
        .unwrap();
    let manual = a.create(&request(), now).unwrap();
    a.control("pause", &json!({}), now).unwrap();
    a.tick(at("2026-10-30T09:00:00Z")).unwrap();
    assert_eq!(a.store().task(automatic).unwrap()["status"], "cancelled");
    assert_eq!(
        a.store().task(automatic).unwrap()["reason"],
        "EOD_SUPERSEDED_SKIPPED"
    );
    assert_eq!(a.store().task(manual).unwrap()["status"], "queued");
}
