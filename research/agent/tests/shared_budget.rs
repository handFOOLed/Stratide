//! Independent SQLite/process assertions for original Owner + cloud entry points.
use chrono::{DateTime, Utc};
use serde_json::{json, Value};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};
use stratide_research::{
    budget::{self, Reservation},
    config::Settings,
    risk_binding as binding, Agent, InputSummary, Store, TaskRequest,
};

fn now(s: &str) -> DateTime<Utc> {
    s.parse().unwrap()
}
fn input() -> InputSummary {
    InputSummary {
        version: "shared-budget-fixture".into(),
        source_day: "2026-10-31".into(),
        mode: "synthetic_test".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({"fixture":"no market data"}),
        eod_eligible: false,
    }
}
fn request() -> TaskRequest {
    TaskRequest {
        name: "Shared budget fixture".into(),
        goal: "Verify existing Owner cost authority".into(),
        scope: "research-only".into(),
        start_day: "2026-10-31".into(),
        end_day: "2026-10-31".into(),
        task_budget_micro: None,
    }
}
fn settings() -> Settings {
    let mut s = Settings::fake();
    s.models.extend(binding::recorded_models());
    s
}
fn setup(s: &Settings) -> (tempfile::TempDir, Agent) {
    let dir = tempfile::tempdir().unwrap();
    fs::write(
        dir.path().join("settings.json"),
        serde_json::to_vec(s).unwrap(),
    )
    .unwrap();
    let agent = Agent::open(dir.path(), None, input()).unwrap();
    (dir, agent)
}
fn reserve(
    store: &Store,
    s: &Settings,
    id: i64,
    maximum: i64,
    at: &str,
) -> stratide_research::Result<i64> {
    budget::reserve(
        &mut store.connect()?,
        s.budget.as_ref().unwrap(),
        now(at),
        Reservation {
            task_id: id,
            maximum_micro: maximum,
            task_limit: None,
            price_version: "synthetic-bounded-quote",
        },
    )
}
fn canonical(path: &Path) -> PathBuf {
    let result = fs::canonicalize(path).unwrap();
    #[cfg(windows)]
    {
        if let Some(s) = result.to_str().unwrap().strip_prefix(r"\\?\") {
            return PathBuf::from(s);
        }
    }
    result
}

#[test]
fn selecting_cloud_task_preserves_existing_default_and_shared_call_table() {
    let s = settings();
    let (_dir, a) = setup(&s);
    let time = now("2026-10-31T08:00:00Z");
    let old = a.create(&request(), time).unwrap();
    a.tick(time).unwrap();
    assert_eq!(a.store().task(old).unwrap()["status"], "completed");
    let id = a
        .store()
        .create_for_model(
            &s,
            &request(),
            &input(),
            time,
            Some("cloud-fixture:risk"),
            "risk-timesfm",
        )
        .unwrap();
    assert_eq!(a.store().task(id).unwrap()["provider_id"], "risk-timesfm");
    assert_eq!(
        a.store().setting("default_model").unwrap().as_deref(),
        Some("fake")
    );
    let next = a.create(&request(), time).unwrap();
    assert_eq!(a.store().task(next).unwrap()["provider_id"], "fake");
    let db = a.store().connect().unwrap();
    let paid: i64 = db
        .query_row(
            "SELECT SUM(settled_micro) FROM calls WHERE task_id=?1",
            [old],
            |r| r.get(0),
        )
        .unwrap();
    assert!(paid > 0);
    assert_eq!(
        db.query_row("SELECT COUNT(*) FROM tasks", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        3
    );
}

#[test]
fn original_spend_and_cloud_quotes_share_both_period_caps() {
    for period in ["daily", "monthly"] {
        let mut s = settings();
        s.budget.as_mut().unwrap().daily_limit_micro = 85000;
        s.budget.as_mut().unwrap().monthly_limit_micro = 85000;
        let (_dir, a) = setup(&s);
        let time = now("2026-10-31T08:00:00Z");
        let legacy = a.create(&request(), time).unwrap();
        let call = reserve(a.store(), &s, legacy, 6500, "2026-10-31T08:00:00Z").unwrap();
        a.store()
            .connect()
            .unwrap()
            .execute(
                "UPDATE calls SET state='settled',settled_micro=6000 WHERE id=?1",
                [call],
            )
            .unwrap();
        if period == "monthly" {
            s.budget.as_mut().unwrap().daily_limit_micro = 100000;
        }
        let risk = a
            .store()
            .create_for_model(&s, &request(), &input(), time, None, "risk-timesfm")
            .unwrap();
        reserve(a.store(), &s, risk, 1000, "2026-10-31T08:00:00Z").unwrap();
        let fusion = a
            .store()
            .create_for_model(&s, &request(), &input(), time, None, "fusion-deepseek")
            .unwrap();
        assert_eq!(
            reserve(a.store(), &s, fusion, 81920, "2026-10-31T08:00:00Z")
                .unwrap_err()
                .0,
            format!("{}_BUDGET_EXHAUSTED", period.to_uppercase())
        );
        let db = a.store().connect().unwrap();
        assert_eq!(db.query_row("SELECT SUM(settled_micro)+SUM(CASE WHEN state!='settled' THEN maximum_micro ELSE 0 END) FROM calls",[],|r|r.get::<_,i64>(0)).unwrap(),7000);
    }
}

#[test]
fn legacy_unknown_survives_restart_and_month_change_in_cloud_budget() {
    let mut s = settings();
    s.budget.as_mut().unwrap().daily_limit_micro = 90000;
    s.budget.as_mut().unwrap().monthly_limit_micro = 90000;
    let (dir, a) = setup(&s);
    let legacy = a.create(&request(), now("2026-10-31T15:59:00Z")).unwrap();
    let call = reserve(a.store(), &s, legacy, 80000, "2026-10-31T15:59:00Z").unwrap();
    a.store()
        .connect()
        .unwrap()
        .execute("UPDATE calls SET state='dispatched' WHERE id=?1", [call])
        .unwrap();
    drop(a);
    let a = Agent::open(dir.path(), None, input()).unwrap();
    let time = now("2026-10-31T16:01:00Z");
    let risk = a
        .store()
        .create_for_model(&s, &request(), &input(), time, None, "risk-timesfm")
        .unwrap();
    reserve(a.store(), &s, risk, 1000, "2026-10-31T16:01:00Z").unwrap();
    let fusion = a
        .store()
        .create_for_model(&s, &request(), &input(), time, None, "fusion-deepseek")
        .unwrap();
    assert_eq!(
        reserve(a.store(), &s, fusion, 81920, "2026-10-31T16:01:00Z")
            .unwrap_err()
            .0,
        "DAILY_BUDGET_EXHAUSTED"
    );
    let db = a.store().connect().unwrap();
    let row: (String, String, i64) = db
        .query_row(
            "SELECT state,month,maximum_micro FROM calls WHERE id=?1",
            [call],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .unwrap();
    assert_eq!(row, ("outcome_uncertain".into(), "2026-10".into(), 80000));
    assert_eq!(
        budget::view(&db, s.budget.as_ref(), time).unwrap()["reserved_micro"],
        "81000"
    );
}

#[test]
fn existing_authority_rejects_a_second_settings_file_or_database() {
    let s = settings();
    let (dir, a) = setup(&s);
    let config = canonical(&dir.path().join("settings.json"));
    a.store().set(binding::ID_KEY, &"b".repeat(64)).unwrap();
    a.store()
        .set(binding::CONFIG_KEY, config.to_str().unwrap())
        .unwrap();
    let bound = binding::Binding {
        schema_version: 1,
        agent_dir: canonical(dir.path()),
        settings_path: config.clone(),
        authority_id: "b".repeat(64),
    };
    bound.verify(&a.store().connect().unwrap()).unwrap();
    let (_other_dir, other) = setup(&s);
    assert_eq!(
        bound
            .verify(&other.store().connect().unwrap())
            .unwrap_err()
            .0,
        "CLOUD_AGENT_DATABASE_MISMATCH"
    );
    drop(a);
    let alternate = dir.path().join("same-budget-different-file.json");
    fs::write(&alternate, serde_json::to_vec(&s).unwrap()).unwrap();
    let result = Agent::open(dir.path(), Some(&alternate), input());
    assert_eq!(result.err().unwrap().0, "AGENT_SETTINGS_AUTHORITY_MISMATCH");
    Agent::open(dir.path(), Some(&config), input()).unwrap();
}

#[test]
fn cross_entry_process() {
    if std::env::var("STRATIDE_SHARED_BUDGET_CHILD").as_deref() != Ok("1") {
        return;
    }
    let mut data = String::new();
    std::io::stdin().read_to_string(&mut data).unwrap();
    let v: Value = serde_json::from_str(&data).unwrap();
    let dir = Path::new(v["dir"].as_str().unwrap());
    let id = v["task_id"].as_i64().unwrap();
    let s = Settings::load(&dir.join("settings.json")).unwrap();
    let store = Store {
        path: dir.join("agent.sqlite"),
    };
    fs::write(dir.join(format!("ready-{id}")), b"ready").unwrap();
    let start = Instant::now();
    while !dir.join("go").exists() {
        assert!(start.elapsed() < Duration::from_secs(10));
        std::thread::sleep(Duration::from_millis(5));
    }
    let result = reserve(
        &store,
        &s,
        id,
        v["maximum"].as_i64().unwrap(),
        "2026-10-31T08:00:00Z",
    );
    println!(
        "SHARED_RESULT={}",
        json!({"reserved":result.is_ok(),"error":result.err().map(|e|e.0)})
    );
}

#[test]
fn two_processes_from_legacy_and_cloud_share_one_atomic_reservation() {
    let mut s = settings();
    let legacy = s.models.iter().find(|m| m.id == "fake").unwrap();
    let amount = legacy
        .cost(legacy.max_input_tokens, legacy.max_output_tokens)
        .unwrap();
    s.budget.as_mut().unwrap().daily_limit_micro = amount;
    let (dir, a) = setup(&s);
    let time = now("2026-10-31T08:00:00Z");
    let old = a.create(&request(), time).unwrap();
    let new = a
        .store()
        .create_for_model(&s, &request(), &input(), time, None, "risk-timesfm")
        .unwrap();
    let mut children = Vec::new();
    for (id, max) in [(old, amount), (new, 1000)] {
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "cross_entry_process", "--nocapture"])
            .env("STRATIDE_SHARED_BUDGET_CHILD", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(
                json!({"dir":dir.path(),"task_id":id,"maximum":max})
                    .to_string()
                    .as_bytes(),
            )
            .unwrap();
        children.push(child);
    }
    let start = Instant::now();
    while !dir.path().join(format!("ready-{old}")).exists()
        || !dir.path().join(format!("ready-{new}")).exists()
    {
        assert!(start.elapsed() < Duration::from_secs(10));
        std::thread::sleep(Duration::from_millis(5));
    }
    fs::write(dir.path().join("go"), b"go").unwrap();
    let mut outcomes = Vec::new();
    for child in children {
        let out = child.wait_with_output().unwrap();
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        let text = String::from_utf8(out.stdout).unwrap();
        let line = text
            .lines()
            .find_map(|s| s.strip_prefix("SHARED_RESULT="))
            .unwrap();
        outcomes.push(serde_json::from_str::<Value>(line).unwrap());
    }
    assert_eq!(outcomes.iter().filter(|v| v["reserved"] == true).count(), 1);
    assert!(outcomes
        .iter()
        .any(|v| v["error"] == "DAILY_BUDGET_EXHAUSTED"));
    let db = a.store().connect().unwrap();
    let row: (i64, i64) = db
        .query_row("SELECT COUNT(*),SUM(maximum_micro) FROM calls", [], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })
        .unwrap();
    assert_eq!(row.0, 1);
    assert!(row.1 <= amount);
}
