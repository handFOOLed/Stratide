//! All provider fixtures here are synthetic; none count toward real-source acceptance.
use crate::{provider::*, store::test_access::*, *};
use serde_json::json;
use std::fs;
mod continuity;
mod r1;

fn config() -> Config {
    Config {
        observation_id: "synthetic-unit-test".into(),
        instrument: "600000.SH".into(),
        strategy_version: "none".into(),
        source: "tushare_pro".into(),
        license_note: "synthetic fixture only".into(),
        local_automation_and_raw_storage_authorized: false,
    }
}
fn at() -> i64 {
    chrono::DateTime::parse_from_rfc3339("2026-10-28T17:00:00+08:00")
        .unwrap()
        .timestamp_millis()
}
fn raw(api: &str, fields: serde_json::Value, items: serde_json::Value) -> RawResponse {
    let body =
        serde_json::to_vec(&json!({"code": 0, "data": {"fields":fields,"items":items}})).unwrap();
    RawResponse {
        api: api.into(),
        http_status: 200,
        sha256: hash(&body),
        received_at: at(),
        server_date: Some("Wed, 28 Oct 2026 09:00:00 GMT".into()),
        body,
    }
}
fn daily() -> RawResponse {
    raw(
        "daily",
        json!([
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol"
        ]),
        json!([["600000.SH", "20261028", 10.01, 10.09, 9.99, 10.02, 100.01]]),
    )
}
fn outcome() -> Outcome {
    let raw = daily();
    Outcome {
        status: "valid_eod".into(),
        bar: Some(parse_bar(&raw, &config(), "20261028").unwrap()),
        raw: vec![raw],
        calendar: vec![],
        provider_published_at: None,
        available_at: Some(at()),
        duplicate_of: None,
        revision_of: None,
        late_backfill: false,
    }
}
fn start(j: &mut Journal, id: &str, day: &str, time: i64) {
    append(
        j,
        Event::CollectionStarted {
            run_id: id.into(),
            observed_at: time,
            trade_day: day.into(),
            calendar_from: day.into(),
            calendar_through: day.into(),
        },
    )
    .unwrap();
}

// Synthetic response received on 10/28 for the missed 10/27 session.
fn late_previous_day() -> Outcome {
    let daily = raw(
        "daily",
        json!([
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "vol"
        ]),
        json!([["600000.SH", "20261027", 10.01, 10.09, 9.99, 10.02, 100.01]]),
    );
    let calendar = raw(
        "trade_cal",
        json!(["exchange", "cal_date", "is_open"]),
        json!([["SSE", "20261027", 1], ["SSE", "20261028", 1]]),
    );
    Outcome {
        status: "valid_eod".into(),
        bar: Some(parse_bar(&daily, &config(), "20261027").unwrap()),
        calendar: parse_calendar(&calendar, &config(), "20261027", "20261028").unwrap(),
        raw: vec![calendar, daily],
        available_at: Some(at()),
        provider_published_at: None,
        duplicate_of: None,
        revision_of: None,
        late_backfill: false,
    }
}

#[test]
fn late_backfill_keeps_missed_day_gap_in_json_csv_and_after_restart() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("journal");
    let mut j = create_at(&path, config(), at() - 86_400_000);
    start(&mut j, "late", "20261027", at());
    finish(
        &mut j,
        "late",
        "20261027",
        "20261028",
        at(),
        late_previous_day(),
    )
    .unwrap();
    let head = j.head().to_owned();
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let value: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    let rows = value["days_and_attempts"].as_array().unwrap();
    let gap = rows
        .iter()
        .find(|r| r["calendar_day"] == "20261027" && r["status"] == "gap_no_collection_on_open_day")
        .expect("late backfill must not hide the missed forward day");
    assert!(gap["run_id"].is_null() && gap["observed_at"].is_null() && gap["close_fen"].is_null());
    assert_eq!(gap["calendar_received_at"], local_time(at()).unwrap());
    let late = rows.iter().find(|r| r["run_id"] == "late").unwrap();
    assert_eq!(late["status"], "valid_eod");
    assert_eq!(late["late_backfill"], true);
    assert_eq!(late["observed_at"], local_time(at()).unwrap());
    assert_eq!(late["received_at"], local_time(at()).unwrap());
    assert_eq!(late["available_at"], local_time(at()).unwrap());
    assert_eq!(value["status"]["actual_valid_forward_days"], 0);
    let csv = fs::read(report.join("daily.csv")).unwrap();
    let mut reader = csv::Reader::from_reader(csv.as_slice());
    let headers = reader.headers().unwrap().clone();
    let day = headers.iter().position(|h| h == "calendar_day").unwrap();
    let status = headers.iter().position(|h| h == "status").unwrap();
    let statuses: Vec<_> = reader
        .records()
        .map(|r| r.unwrap())
        .filter(|r| &r[day] == "20261027")
        .map(|r| r[status].to_string())
        .collect();
    assert_eq!(statuses, ["gap_no_collection_on_open_day", "valid_eod"]);
    drop(j);
    let j = Journal::open(&path).unwrap();
    assert_eq!(j.head(), head);
    let reopened = temp.path().join("reopened-report");
    j.report(&reopened).unwrap();
    for name in ["report.json", "daily.csv", "events.json"] {
        assert_eq!(
            fs::read(report.join(name)).unwrap(),
            fs::read(reopened.join(name)).unwrap()
        );
    }
    j.report(&report).unwrap();
    // Optional artifact export belongs only to this synthetic test binary.
    if let Ok(destination) = std::env::var("STRATIDE_SYNTHETIC_GAP_REPORT") {
        j.report(destination).unwrap();
    }
}

#[test]
fn same_day_failure_remains_explicit_without_inventing_no_attempt_gap() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("journal");
    let yesterday = at() - 86_400_000;
    let mut j = create_at(&path, config(), yesterday);
    start(&mut j, "failed-on-day", "20261027", yesterday);
    finish(
        &mut j,
        "failed-on-day",
        "20261027",
        "20261027",
        yesterday,
        Outcome::gap("network_timeout_or_tls_error"),
    )
    .unwrap();
    start(&mut j, "late", "20261027", at());
    finish(
        &mut j,
        "late",
        "20261027",
        "20261028",
        at(),
        late_previous_day(),
    )
    .unwrap();
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let value: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    let rows: Vec<_> = value["days_and_attempts"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["calendar_day"] == "20261027")
        .collect();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0]["status"], "network_timeout_or_tls_error");
    assert_eq!(rows[1]["late_backfill"], true);
}

#[test]
fn backfill_before_observation_start_does_not_invent_old_gap() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("journal");
    let mut j = create_at(&path, config(), at());
    start(&mut j, "before-start", "20261027", at());
    finish(
        &mut j,
        "before-start",
        "20261027",
        "20261028",
        at(),
        late_previous_day(),
    )
    .unwrap();
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let value: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    let rows: Vec<_> = value["days_and_attempts"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["calendar_day"] == "20261027")
        .collect();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["late_backfill"], true);
    assert_eq!(value["status"]["actual_valid_forward_days"], 0);
}
#[test]
fn exact_fen_and_volume_no_float_rounding() {
    let bar = parse_bar(&daily(), &config(), "20261028").unwrap();
    assert_eq!((bar.open_fen, bar.volume_shares), (1001, 10001));
    for bad in [
        json!("10.001"),
        json!("1e1"),
        json!("-1"),
        json!(null),
        json!("99999999999999999999999999999999999"),
    ] {
        assert!(scaled(&bad, 100).is_err());
    }
    assert_eq!(scaled(&json!("10.0100"), 100).unwrap(), 1001);
    assert!(parse_bar(&daily(), &config(), "20261027").is_err());
    assert!(clock_verified(&daily()));
    let mut bad_clock = daily();
    bad_clock.received_at += 400_000;
    assert!(!clock_verified(&bad_clock));
}
#[test]
fn calendar_missing_closed_and_permission_are_distinct() {
    let cal = raw(
        "trade_cal",
        json!(["exchange", "cal_date", "is_open"]),
        json!([["SSE", "20261028", 0]]),
    );
    assert!(!parse_calendar(&cal, &config(), "20261028", "20261028").unwrap()[0].is_open);
    assert!(parse_calendar(&cal, &config(), "20261027", "20261028")
        .unwrap_err()
        .contains("incomplete"));
    let missing = raw("daily", json!(["ts_code"]), json!([]));
    assert_eq!(
        parse_bar(&missing, &config(), "20261028").unwrap_err(),
        "missing_daily_not_proof_of_suspension"
    );
    let mut denied = missing;
    denied.body = br#"{"code":2002,"msg":"not retained in logs"}"#.to_vec();
    assert_eq!(
        parse_bar(&denied, &config(), "20261028").unwrap_err(),
        "permission_denied_2002"
    );
}
#[test]
fn duplicate_revision_backfill_preserve_original_and_no_financial_ledger() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("journal");
    let mut j = create_at(&path, config(), at());
    for (id, delta) in [("first", 0), ("repeat", 0), ("revision", 1)] {
        start(&mut j, id, "20261028", at());
        let mut out = outcome();
        out.bar.as_mut().unwrap().close_fen += delta;
        finish(&mut j, id, "20261028", "20261028", at(), out).unwrap();
    }
    let original_digest = j.entries()[2].digest.clone();
    assert!(
        matches!(&j.entries()[4].event, Event::CollectionFinished { outcome, .. } if outcome.duplicate_of==Some(2))
    );
    assert!(
        matches!(&j.entries()[6].event, Event::CollectionFinished { outcome, .. } if outcome.revision_of==Some(4))
    );
    start(&mut j, "backfill", "20261028", at() + 86_400_000);
    let mut late = outcome();
    late.available_at = Some(at() + 86_400_000);
    late.raw[0].received_at += 86_400_000;
    finish(
        &mut j,
        "backfill",
        "20261028",
        "20261029",
        at() + 86_400_000,
        late,
    )
    .unwrap();
    assert!(
        matches!(&j.entries()[8].event, Event::CollectionFinished { outcome, .. } if outcome.late_backfill)
    );
    assert_eq!(j.status().unwrap().actual_valid_forward_days, 1);
    assert_eq!(j.status().unwrap().simulated_fills, 0);
    let head = j.head().to_owned();
    drop(j);
    let j = Journal::open(&path).unwrap();
    assert_eq!(j.head(), head);
    assert_eq!(j.entries()[2].digest, original_digest);
    assert!(!path.join("ledger.sqlite").exists());
    assert!(Journal::create(&path, config()).is_err());
}
#[test]
fn local_single_writer_and_durable_clock_halt() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("journal");
    let mut j = create_at(&path, config(), at());
    assert!(Journal::open(&path).is_err());
    assert!(check_clock(&mut j, at() - 1).is_err());
    drop(j);
    let mut j = Journal::open(&path).unwrap();
    assert!(j.status().unwrap().clock_halted);
    assert!(check_clock(&mut j, at() + 10_000).is_err());
}
#[test]
fn journal_tamper_tail_loss_raw_tamper_and_transaction_rollback_fail_closed() {
    for kind in ["payload", "tail", "raw", "rollback"] {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("journal");
        let mut j = create_at(&path, config(), at());
        start(&mut j, "first", "20261028", at());
        finish(&mut j, "first", "20261028", "20261028", at(), outcome()).unwrap();
        drop(j);
        let db = rusqlite::Connection::open(path.join("forward.sqlite")).unwrap();
        assert!(db
            .execute("UPDATE events SET digest='bad' WHERE seq=1", [])
            .is_err());
        db.execute_batch("DROP TRIGGER no_event_update; DROP TRIGGER no_event_delete;")
            .unwrap();
        match kind {
            "payload" => {
                db.execute("UPDATE events SET payload='{}' WHERE seq=1", [])
                    .unwrap();
            }
            "tail" => {
                db.execute("DELETE FROM events WHERE seq=2", []).unwrap();
            }
            "raw" => {
                db.execute("UPDATE events SET payload=replace(payload,'\"body\":[123','\"body\":[124') WHERE seq=2", []).unwrap();
            }
            _ => {
                db.execute_batch(
                    "BEGIN IMMEDIATE; INSERT INTO events VALUES(3,'bad','bad'); ROLLBACK;",
                )
                .unwrap();
            }
        }
        drop(db);
        assert_eq!(Journal::open(&path).is_ok(), kind == "rollback");
    }
}
#[test]
fn blocked_license_survives_restart_pending_recovery_and_immutable_reports() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("journal");
    let mut j = Journal::create(&path, config()).unwrap();
    start(&mut j, "interrupted", &local_day(now()).unwrap(), now());
    drop(j);
    let mut j = Journal::open(&path).unwrap();
    assert_eq!(j.status().unwrap().pending_runs, 1);
    assert_eq!(
        j.collect_once(None).unwrap(),
        "blocked_source_license_unverified"
    );
    assert!(j
        .entries()
        .iter()
        .any(|e| matches!(&e.event, Event::Interrupted {run_id, ..} if run_id=="interrupted")));
    assert_eq!(j.status().unwrap().actual_valid_forward_days, 0);
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    j.report(&report).unwrap();
    let value: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    assert!(value["status"]["nav_fen"].is_null());
    assert_eq!(value["status"]["strategy_proposals"], 0);
    j.collect_once(None).unwrap();
    assert!(j.report(&report).is_err());
    assert!(j.collect_once(Some("20000101")).is_ok());
    assert!(j.collect_once(Some("99990101")).is_err());
}

#[test]
fn crash_child() {
    let Ok(path) = std::env::var("STRATIDE_FORWARD_TEST_ROOT") else {
        return;
    };
    let mut j = Journal::open(path).unwrap();
    if std::env::var("STRATIDE_FORWARD_TEST_START").is_ok() {
        start(&mut j, "pending", "20261028", at());
        return;
    }
    if std::env::var("STRATIDE_FORWARD_TEST_FINISH").is_ok() {
        let _ = finish(&mut j, "pending", "20261028", "20261028", at(), outcome());
        return;
    }
    let _ = j.collect_once(None);
}

#[test]
fn later_calendar_evidence_marks_missed_days_and_does_not_rewrite_prior_attempt() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("journal");
    let mut j = create_at(&path, config(), at() - 86_400_000);
    start(&mut j, "late-calendar", "20261028", at());
    let mut out = outcome();
    out.calendar = vec![
        CalendarDay {
            day: "20261027".into(),
            is_open: true,
        },
        CalendarDay {
            day: "20261028".into(),
            is_open: true,
        },
    ];
    finish(&mut j, "late-calendar", "20261028", "20261028", at(), out).unwrap();
    start(&mut j, "calendar-revision", "20261028", at() + 1);
    let mut out = outcome();
    out.calendar = vec![CalendarDay {
        day: "20261028".into(),
        is_open: false,
    }];
    assert_eq!(
        finish(
            &mut j,
            "calendar-revision",
            "20261028",
            "20261028",
            at() + 1,
            out
        )
        .unwrap(),
        "calendar_conflict"
    );
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let v: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    let days = v["days_and_attempts"].as_array().unwrap();
    assert_eq!(days[0]["status"], "gap_no_collection_on_open_day");
    assert!(days[0]["observed_at"].is_null());
    assert_eq!(days[1]["is_open"], true);
    assert_eq!(days[2]["status"], "calendar_conflict");
    assert!(days[2]["close_fen"].is_null());
}

#[test]
fn real_process_death_at_commit_boundaries_recovers_without_invented_response() {
    for point in ["before_commit", "after_commit"] {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("journal");
        drop(Journal::create(&path, config()).unwrap());
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "tests::crash_child", "--nocapture"])
            .env("STRATIDE_FORWARD_TEST_ROOT", &path)
            .env("STRATIDE_FORWARD_FAULT_POINT", point)
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(86), "{output:?}");
        let mut j = Journal::open(&path).unwrap();
        assert_eq!(
            j.status().unwrap().pending_runs,
            usize::from(point == "after_commit")
        );
        assert_eq!(j.status().unwrap().actual_valid_forward_days, 0);
        assert_eq!(
            j.collect_once(None).unwrap(),
            "blocked_source_license_unverified"
        );
        assert_eq!(j.status().unwrap().pending_runs, 0);
        assert!(j.entries().iter().all(|e| match &e.event {
            Event::CollectionFinished { outcome, .. } =>
                outcome.raw.is_empty() && outcome.bar.is_none(),
            _ => true,
        }));
    }
}
