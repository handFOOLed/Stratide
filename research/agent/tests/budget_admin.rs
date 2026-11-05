//! Owner-editable research budget: strict input, committed holds, atomic
//! settings write and store audit. No Provider call or real install is used.
use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use std::fs;
use stratide_research::{
    budget::{self, Reservation},
    budget_admin,
    config::{Budget, Settings},
    Agent, InputSummary, TaskRequest,
};

fn now() -> DateTime<Utc> {
    "2026-11-05T09:00:00Z".parse().unwrap()
}

fn at(value: &str) -> DateTime<Utc> {
    value.parse().unwrap()
}

fn input() -> InputSummary {
    InputSummary {
        version: "budget-admin-v1".into(),
        source_day: "2026-11-05".into(),
        mode: "historical_replay".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({"source":"synthetic_test_fixture_only"}),
        eod_eligible: false,
    }
}

fn request() -> TaskRequest {
    TaskRequest {
        name: "预算编辑回归".into(),
        goal: "验证预算上限修改的边界".into(),
        scope: "本地合成预算夹具".into(),
        start_day: "2026-11-05".into(),
        end_day: "2026-11-05".into(),
        task_budget_micro: None,
    }
}

fn settings() -> Settings {
    let mut settings = Settings::fake();
    settings.budget = Some(Budget {
        currency: "TST".into(),
        timezone: "Asia/Shanghai".into(),
        daily_limit_micro: 5_000_000,
        monthly_limit_micro: 100_000_000,
    });
    settings
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

fn body(daily: i64, monthly: i64, confirm: bool) -> Value {
    json!({
        "daily_limit_micro": daily.to_string(),
        "monthly_limit_micro": monthly.to_string(),
        "confirm_below_committed": confirm,
    })
}

fn reserve(agent: &Agent, budget: &Budget, at: DateTime<Utc>, maximum_micro: i64) -> i64 {
    let task = agent.create(&request(), at).unwrap();
    budget::reserve(
        &mut agent.store().connect().unwrap(),
        budget,
        at,
        Reservation {
            task_id: task,
            maximum_micro,
            task_limit: None,
            price_version: "synthetic_budget_admin",
        },
    )
    .unwrap()
}

fn settle(agent: &Agent, call: i64) {
    agent
        .store()
        .connect()
        .unwrap()
        .execute(
            "UPDATE calls SET state='settled',settled_micro=maximum_micro WHERE id=?1",
            [call],
        )
        .unwrap();
}

fn audit_rows(agent: &Agent) -> Vec<(String, String)> {
    let connection = agent.store().connect().unwrap();
    let mut query = connection
        .prepare("SELECT key,value FROM meta WHERE key LIKE 'budget_audit:%' ORDER BY key")
        .unwrap();
    query
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
        .unwrap()
        .collect::<std::result::Result<Vec<_>, _>>()
        .unwrap()
}

#[test]
fn invalid_or_unsafe_inputs_are_rejected_without_writing() {
    let settings = settings();
    let (dir, agent) = setup(&settings);
    let path = dir.path().join("settings.json");
    let before = fs::read(&path).unwrap();
    for request in [
        body(10, 5, false),
        json!({"daily_limit_micro":"0","monthly_limit_micro":"10","confirm_below_committed":false}),
        json!({"daily_limit_micro":"-1","monthly_limit_micro":"10","confirm_below_committed":false}),
        json!({"daily_limit_micro":"1.5","monthly_limit_micro":"10","confirm_below_committed":false}),
        json!({"daily_limit_micro":"1000000000001","monthly_limit_micro":"1000000000001","confirm_below_committed":false}),
        json!({"daily_limit_micro":"100","monthly_limit_micro":"200"}),
        json!({"daily_limit_micro":"100","monthly_limit_micro":"200","confirm_below_committed":false,"unknown":true}),
    ] {
        assert_eq!(
            budget_admin::update(&agent, &request, now()).unwrap_err().0,
            "BUDGET_INPUT_INVALID",
            "{request}"
        );
        assert_eq!(fs::read(&path).unwrap(), before, "{request}");
    }
}

#[test]
fn committed_holds_require_confirmation_and_bind_future_reservations() {
    let settings = settings();
    let (dir, agent) = setup(&settings);
    let path = dir.path().join("settings.json");
    let before = fs::read(&path).unwrap();
    reserve(&agent, settings.budget.as_ref().unwrap(), now(), 3_000_000);

    assert_eq!(
        budget_admin::update(&agent, &body(2_000_000, 10_000_000, false), now())
            .unwrap_err()
            .0,
        "BUDGET_BELOW_COMMITTED"
    );
    assert_eq!(fs::read(&path).unwrap(), before);
    assert!(audit_rows(&agent).is_empty());

    let response = budget_admin::update(&agent, &body(2_000_000, 10_000_000, true), now()).unwrap();
    assert_eq!(response["budget"]["daily_limit_micro"], "2000000");
    assert_eq!(response["budget"]["daily_settled_micro"], "0");
    assert_eq!(response["budget"]["reserved_micro"], "3000000");
    assert_eq!(response["budget"]["daily_remaining_micro"], "0");
    assert_eq!(response["budget"]["monthly_remaining_micro"], "7000000");
    assert_eq!(agent.status(now()).unwrap()["budget"], response["budget"]);

    let audits = audit_rows(&agent);
    assert_eq!(audits.len(), 1);
    let audit: Value = serde_json::from_str(&audits[0].1).unwrap();
    assert_eq!(audit["old"]["daily_limit_micro"], "5000000");
    assert_eq!(audit["new"]["daily_limit_micro"], "2000000");
    assert_eq!(audit["source"], "owner_web");

    // The existing hold keeps consuming its full maximum and is not released.
    let updated = Settings::load(&path).unwrap();
    let task = agent.create(&request(), now()).unwrap();
    assert_eq!(
        budget::reserve(
            &mut agent.store().connect().unwrap(),
            updated.budget.as_ref().unwrap(),
            now(),
            Reservation {
                task_id: task,
                maximum_micro: 1,
                task_limit: None,
                price_version: "synthetic_budget_admin",
            },
        )
        .unwrap_err()
        .0,
        "DAILY_BUDGET_EXHAUSTED"
    );
}

#[test]
fn cap_equal_to_committed_is_not_below() {
    let settings = settings();
    let (_dir, agent) = setup(&settings);
    reserve(&agent, settings.budget.as_ref().unwrap(), now(), 3_000_000);
    let response =
        budget_admin::update(&agent, &body(3_000_000, 10_000_000, false), now()).unwrap();
    assert_eq!(response["budget"]["daily_remaining_micro"], "0");
}

#[test]
fn settled_monthly_usage_also_requires_confirmation() {
    let settings = settings();
    let (_dir, agent) = setup(&settings);
    let call = reserve(
        &agent,
        settings.budget.as_ref().unwrap(),
        at("2026-11-01T04:00:00Z"),
        5_000_000,
    );
    settle(&agent, call);
    assert_eq!(
        budget_admin::update(&agent, &body(1_000_000, 2_000_000, false), now())
            .unwrap_err()
            .0,
        "BUDGET_BELOW_COMMITTED"
    );
    let response = budget_admin::update(&agent, &body(1_000_000, 2_000_000, true), now()).unwrap();
    assert_eq!(response["budget"]["daily_settled_micro"], "0");
    assert_eq!(response["budget"]["monthly_settled_micro"], "5000000");
    assert_eq!(response["budget"]["monthly_remaining_micro"], "0");
    assert_eq!(response["budget"]["daily_remaining_micro"], "1000000");
}

#[test]
fn successful_edit_updates_status_and_records_audit_without_touching_calls() {
    let settings = settings();
    let (dir, agent) = setup(&settings);
    let path = dir.path().join("settings.json");
    reserve(&agent, settings.budget.as_ref().unwrap(), now(), 1_000_000);
    let before = agent.status(now()).unwrap();

    let response =
        budget_admin::update(&agent, &body(6_000_000, 50_000_000, false), now()).unwrap();
    let budget = &response["budget"];
    assert_eq!(budget["state"], "configured");
    assert_eq!(budget["currency"], "TST");
    assert_eq!(budget["timezone"], "Asia/Shanghai");
    assert_eq!(budget["unit"], "micro_currency_1e-6");
    assert_eq!(budget["day"], "2026-11-05");
    assert_eq!(budget["month"], "2026-11");
    assert_eq!(budget["daily_limit_micro"], "6000000");
    assert_eq!(budget["monthly_limit_micro"], "50000000");
    assert_eq!(budget["reserved_micro"], "1000000");
    assert_eq!(budget["daily_remaining_micro"], "5000000");
    assert_eq!(budget["monthly_remaining_micro"], "49000000");
    assert_eq!(budget["call_count"], "1");
    assert_eq!(agent.status(now()).unwrap()["budget"], *budget);
    assert_eq!(before["budget"]["call_count"], budget["call_count"]);
    assert_eq!(before["budget"]["reserved_micro"], budget["reserved_micro"]);

    let saved = Settings::load(&path).unwrap();
    let saved_budget = saved.budget.as_ref().unwrap();
    assert_eq!(saved_budget.currency, "TST");
    assert_eq!(saved_budget.daily_limit_micro, 6_000_000);
    assert_eq!(saved_budget.monthly_limit_micro, 50_000_000);
    assert_eq!(
        saved
            .models
            .iter()
            .map(|model| model.fingerprint())
            .collect::<Vec<_>>(),
        settings
            .models
            .iter()
            .map(|model| model.fingerprint())
            .collect::<Vec<_>>()
    );
    assert_eq!(saved.default_model, settings.default_model);
    assert_eq!(saved.max_tasks, settings.max_tasks);
    assert_eq!(saved.max_storage_mb, settings.max_storage_mb);

    let audits = audit_rows(&agent);
    assert_eq!(audits.len(), 1);
    let at = audits[0]
        .0
        .strip_prefix(budget_admin::AUDIT_PREFIX)
        .unwrap();
    let audit: Value = serde_json::from_str(&audits[0].1).unwrap();
    assert_eq!(audit["at"], at);
    assert!(DateTime::parse_from_rfc3339(at).is_ok());
    assert_eq!(audit["source"], "owner_web");
    assert_eq!(audit["old"]["currency"], "TST");
    assert_eq!(audit["old"]["timezone"], "Asia/Shanghai");
    assert_eq!(audit["old"]["daily_limit_micro"], "5000000");
    assert_eq!(audit["old"]["monthly_limit_micro"], "100000000");
    assert_eq!(audit["new"]["daily_limit_micro"], "6000000");
    assert_eq!(audit["new"]["monthly_limit_micro"], "50000000");
}

#[test]
fn budget_edit_does_not_clear_overrun_lock_or_release_holds() {
    let settings = settings();
    let (dir, agent) = setup(&settings);
    let call = reserve(&agent, settings.budget.as_ref().unwrap(), now(), 1_000_000);
    agent
        .store()
        .connect()
        .unwrap()
        .execute("UPDATE calls SET violation=1 WHERE id=?1", [call])
        .unwrap();
    let response =
        budget_admin::update(&agent, &body(6_000_000, 50_000_000, false), now()).unwrap();
    assert_eq!(response["budget"]["reserved_micro"], "1000000");
    let updated = Settings::load(&dir.path().join("settings.json")).unwrap();
    let task = agent.create(&request(), now()).unwrap();
    assert_eq!(
        budget::reserve(
            &mut agent.store().connect().unwrap(),
            updated.budget.as_ref().unwrap(),
            now(),
            Reservation {
                task_id: task,
                maximum_micro: 1,
                task_limit: None,
                price_version: "synthetic_budget_admin",
            },
        )
        .unwrap_err()
        .0,
        "BILLING_OVERRUN_REQUIRES_OWNER"
    );
}

#[test]
fn configured_currency_and_timezone_are_immutable() {
    let settings = settings();
    let (dir, agent) = setup(&settings);
    let path = dir.path().join("settings.json");
    let before = fs::read(&path).unwrap();
    for (field, value) in [("currency", "CNY"), ("timezone", "UTC")] {
        let mut request = body(6_000_000, 50_000_000, false);
        request[field] = json!(value);
        assert_eq!(
            budget_admin::update(&agent, &request, now()).unwrap_err().0,
            "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE",
            "{field}"
        );
        assert_eq!(fs::read(&path).unwrap(), before);
    }
    // Repeating the existing identity is not a change.
    let mut same = body(6_000_000, 50_000_000, false);
    same["currency"] = json!("TST");
    same["timezone"] = json!("Asia/Shanghai");
    budget_admin::update(&agent, &same, now()).unwrap();
}

#[test]
fn first_configuration_sets_and_locks_identity() {
    let dir = tempfile::tempdir().unwrap();
    let agent = Agent::open(dir.path(), None, input()).unwrap();
    let path = dir.path().join("settings.json");
    assert!(!path.exists());
    let response = budget_admin::update(
        &agent,
        &json!({
            "daily_limit_micro": "5000000",
            "monthly_limit_micro": "100000000",
            "confirm_below_committed": false,
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
        }),
        now(),
    )
    .unwrap();
    assert_eq!(response["budget"]["state"], "configured");
    assert_eq!(response["budget"]["currency"], "CNY");
    assert_eq!(
        agent.store().setting("budget_identity").unwrap().unwrap(),
        "CNY|Asia/Shanghai"
    );
    let saved = Settings::load(&path).unwrap();
    assert_eq!(saved.budget.as_ref().unwrap().daily_limit_micro, 5_000_000);

    let mut changed = body(5_000_000, 100_000_000, false);
    changed["currency"] = json!("USD");
    assert_eq!(
        budget_admin::update(&agent, &changed, now()).unwrap_err().0,
        "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE"
    );
    changed["currency"] = json!("CNY");
    changed["timezone"] = json!("Asia/Shanghai");
    budget_admin::update(&agent, &changed, now()).unwrap();
}

#[test]
fn first_configuration_without_identity_uses_install_defaults() {
    let dir = tempfile::tempdir().unwrap();
    let agent = Agent::open(dir.path(), None, input()).unwrap();
    let response =
        budget_admin::update(&agent, &body(5_000_000, 100_000_000, false), now()).unwrap();
    assert_eq!(response["budget"]["currency"], "CNY");
    assert_eq!(response["budget"]["timezone"], "Asia/Shanghai");
}

#[test]
fn invalid_first_identity_is_rejected_without_creating_settings() {
    for (currency, timezone) in [
        ("cny", "Asia/Shanghai"),
        ("CN", "Asia/Shanghai"),
        ("CNY", "Mars/Olympus"),
    ] {
        let dir = tempfile::tempdir().unwrap();
        let agent = Agent::open(dir.path(), None, input()).unwrap();
        let mut request = body(5_000_000, 100_000_000, false);
        request["currency"] = json!(currency);
        request["timezone"] = json!(timezone);
        assert_eq!(
            budget_admin::update(&agent, &request, now()).unwrap_err().0,
            "BUDGET_INPUT_INVALID"
        );
        assert!(!dir.path().join("settings.json").exists());
    }
}

#[cfg(unix)]
#[test]
fn symlinked_settings_file_is_rejected() {
    let settings = settings();
    let (dir, agent) = setup(&settings);
    let path = dir.path().join("settings.json");
    let target = dir.path().join("elsewhere.json");
    fs::rename(&path, &target).unwrap();
    std::os::unix::fs::symlink(&target, &path).unwrap();
    let before = fs::read(&target).unwrap();
    assert_eq!(
        budget_admin::update(&agent, &body(6_000_000, 50_000_000, false), now())
            .unwrap_err()
            .0,
        "BUDGET_CONFIG_INVALID"
    );
    assert_eq!(fs::read(&target).unwrap(), before);
}
