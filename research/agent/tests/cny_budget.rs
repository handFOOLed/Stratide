//! Exact Owner CNY caps, both routes, and unknown holds across Shanghai periods.
use chrono::{DateTime, Utc};
use stratide_research::{
    budget::{self, Reservation},
    config::{Budget, Settings},
    deepseek, local_fusion as f, Store, TaskRequest,
};
fn at(s: &str) -> DateTime<Utc> {
    s.parse().unwrap()
}
fn setup() -> (tempfile::TempDir, Settings, Store) {
    let dir = tempfile::tempdir().unwrap();
    let cfg = deepseek::Config {
        version: 1,
        key_file: dir.path().join("not-read.md"),
    credential_target: None,
        grant_version: "deepseek-synthetic-fusion-grant-v1".into(),
        synthetic_only: true,
        provider_terms_reviewed: true,
        authorized_at: "2026-11-01T00:00:00Z".into(),
        price_reviewed_at: "2026-11-01T00:00:00Z".into(),
        price_valid_until: "2026-11-02T00:00:00Z".into(),
        max_call_micro: 100000,
    };
    let s = Settings {
        budget: Some(Budget {
            currency: "CNY".into(),
            timezone: "Asia/Shanghai".into(),
            daily_limit_micro: 5_000_000,
            monthly_limit_micro: 100_000_000,
        }),
        models: vec![cfg.model(), f::model(&cfg)],
        default_model: Some(deepseek::ID.into()),
        ..Settings::default()
    };
    let store = Store::open(dir.path(), &s).unwrap();
    (dir, s, store)
}
fn reserve(
    store: &Store,
    s: &Settings,
    model: &str,
    n: i64,
    time: DateTime<Utc>,
) -> stratide_research::Result<i64> {
    let input = f::blank();
    let req = TaskRequest {
        name: "CNY budget test".into(),
        goal: "Shared cap".into(),
        scope: "owner_task".into(),
        start_day: "2026-11-01".into(),
        end_day: "2026-11-01".into(),
        task_budget_micro: None,
    };
    let id = store.create_for_model(s, &req, &input, time, None, model)?;
    budget::reserve(
        &mut store.connect()?,
        s.budget.as_ref().unwrap(),
        time,
        Reservation {
            task_id: id,
            maximum_micro: n,
            task_limit: None,
            price_version: deepseek::PRICE_VERSION,
        },
    )
}
#[test]
fn five_yuan_is_shared_between_structured_and_fusion() {
    let (_dir, s, store) = setup();
    let t = at("2026-11-03T04:00:00Z");
    reserve(&store, &s, deepseek::ID, 2_000_000, t).unwrap();
    reserve(&store, &s, f::MODEL_ID, 2_000_000, t).unwrap();
    reserve(&store, &s, deepseek::ID, 1_000_000, t).unwrap();
    assert_eq!(
        reserve(&store, &s, f::MODEL_ID, 1, t).unwrap_err().0,
        "DAILY_BUDGET_EXHAUSTED"
    );
    let v = budget::view(&store.connect().unwrap(), s.budget.as_ref(), t).unwrap();
    assert_eq!(v["daily_remaining_micro"], "0");
    assert_eq!(v["call_count"], "3");
}
#[test]
fn hundred_yuan_monthly_total_rejects_new_day_and_both_models() {
    let (_dir, s, store) = setup();
    for day in 1..=20 {
        let t = at(&format!("2026-11-{day:02}T04:00:00Z"));
        let id = reserve(
            &store,
            &s,
            if day % 2 == 0 {
                deepseek::ID
            } else {
                f::MODEL_ID
            },
            5_000_000,
            t,
        )
        .unwrap();
        store
            .connect()
            .unwrap()
            .execute(
                "UPDATE calls SET state='settled',settled_micro=maximum_micro WHERE id=?1",
                [id],
            )
            .unwrap();
    }
    let t = at("2026-11-21T04:00:00Z");
    for m in [deepseek::ID, f::MODEL_ID] {
        assert_eq!(
            reserve(&store, &s, m, 98304, t).unwrap_err().0,
            "MONTHLY_BUDGET_EXHAUSTED"
        );
    }
    let v = budget::view(&store.connect().unwrap(), s.budget.as_ref(), t).unwrap();
    assert_eq!(v["daily_remaining_micro"], "5000000");
    assert_eq!(v["monthly_remaining_micro"], "0");
}
#[test]
fn shanghai_month_rollover_keeps_unknown_holds_after_restart() {
    let (dir, s, store) = setup();
    let old = at("2026-10-31T15:59:00Z");
    let id = reserve(&store, &s, deepseek::ID, 4_950_000, old).unwrap();
    store
        .connect()
        .unwrap()
        .execute(
            "UPDATE calls SET state='outcome_uncertain' WHERE id=?1",
            [id],
        )
        .unwrap();
    drop(store);
    let store = Store::open(dir.path(), &s).unwrap();
    let next = at("2026-10-31T16:01:00Z");
    let v = budget::view(&store.connect().unwrap(), s.budget.as_ref(), next).unwrap();
    assert_eq!(v["month"], "2026-11");
    assert_eq!(v["reserved_micro"], "4950000");
    assert_eq!(v["daily_remaining_micro"], "50000");
    assert_eq!(v["monthly_remaining_micro"], "95050000");
    assert_eq!(
        reserve(&store, &s, f::MODEL_ID, 98304, next).unwrap_err().0,
        "DAILY_BUDGET_EXHAUSTED"
    );
    let mut changed = s.clone();
    changed.budget.as_mut().unwrap().currency = "TST".into();
    assert_eq!(
        Store::open(dir.path(), &changed).err().unwrap().0,
        "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE"
    );
}
