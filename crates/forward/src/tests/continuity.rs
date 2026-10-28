//! synthetic_test only: advancing these clocks never proves real observation days.
use super::*;

#[test]
fn response_crossing_midnight_is_late_and_never_a_ready_on_day_step() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let midnight = chrono::DateTime::parse_from_rfc3339("2026-10-29T00:00:00+08:00")
        .unwrap()
        .timestamp_millis();
    let mut j = create_at(&path, config(), midnight - 1000);
    start(&mut j, "midnight", "20261028", midnight - 1000);
    let mut out = late_previous_day();
    out.bar = outcome().bar;
    for r in &mut out.raw {
        r.received_at = midnight + 1;
    }
    finish(
        &mut j,
        "midnight",
        "20261028",
        "20261028",
        midnight + 1,
        out,
    )
    .unwrap();
    let Event::CollectionFinished { outcome, .. } = &j.entries().last().unwrap().event else {
        panic!("missing completion")
    };
    assert!(outcome.late_backfill);
    assert!(!crate::continuity::ready(outcome, "20261028"));
    assert_eq!(j.status().unwrap().actual_valid_forward_days, 0);
    assert!(j.eod_as_of("20261028", midnight).unwrap().is_none());
    assert!(
        j.eod_as_of("20261028", midnight + 1)
            .unwrap()
            .unwrap()
            .late_backfill
    );
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let v: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    assert_eq!(v["continuity"]["missing_valid_eod_days"], 1);
    assert_eq!(v["continuity"]["valid_eod_days"], 0);
}

#[test]
fn early_probe_and_late_backfill_do_not_consume_todays_eod_slot() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let early = at() - 2 * 3_600_000;
    let mut j = create_at(&path, config(), early);
    start(&mut j, "early", "20261028", early);
    finish(
        &mut j,
        "early",
        "20261028",
        "20261028",
        early,
        Outcome::gap("not_ready_publication_window"),
    )
    .unwrap();
    assert!(j.eod_existing_step(at()).unwrap().is_none());
    start(&mut j, "backfill", "20261027", at());
    finish(
        &mut j,
        "backfill",
        "20261027",
        "20261028",
        at(),
        late_previous_day(),
    )
    .unwrap();
    drop(j);
    let j = Journal::open(&path).unwrap();
    assert!(j.eod_existing_step(at() + 1).unwrap().is_none());
}

#[test]
fn real_process_death_during_response_commit_recovers_actual_committed_state() {
    for point in ["before_commit", "after_commit"] {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("observer");
        let mut j = create_at(&path, config(), at());
        start(&mut j, "pending", "20261028", at());
        drop(j);
        let out = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", "tests::crash_child", "--nocapture"])
            .env("STRATIDE_FORWARD_TEST_ROOT", &path)
            .env("STRATIDE_FORWARD_TEST_FINISH", "1")
            .env("STRATIDE_FORWARD_FAULT_POINT", point)
            .output()
            .unwrap();
        assert_eq!(out.status.code(), Some(86));
        let mut j = Journal::open(&path).unwrap();
        let committed = point == "after_commit";
        assert_eq!(j.status().unwrap().pending_runs, usize::from(!committed));
        assert_eq!(
            j.status().unwrap().actual_valid_forward_days,
            usize::from(committed)
        );
        if committed {
            assert!(j.eod_existing_step(at()).unwrap().unwrap().ready);
            assert!(j.eod_as_of("20261028", at()).unwrap().is_some());
        } else {
            assert!(j.eod_as_of("20261028", at()).unwrap().is_none());
            // Explicit retry closes the unknown interrupted response; never reconstructs it.
            j.collect_once(None).unwrap();
            assert_eq!(j.status().unwrap().pending_runs, 0);
            assert_eq!(j.status().unwrap().actual_valid_forward_days, 0);
        }
    }
}

#[test]
fn step_waits_without_http_and_restart_does_not_retry_completed_failure() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at());
    assert_eq!(
        j.eod_existing_step(at() - 3_600_001)
            .unwrap()
            .unwrap()
            .status,
        "waiting_eod_publication_window"
    );
    assert!(j.eod_existing_step(at()).unwrap().is_none());
    start(&mut j, "failed", "20261028", at());
    finish(
        &mut j,
        "failed",
        "20261028",
        "20261028",
        at(),
        Outcome::gap("network_timeout_or_tls_error"),
    )
    .unwrap();
    let head = j.head().to_owned();
    drop(j);
    let j = Journal::open(&path).unwrap();
    let step = j.eod_existing_step(at()).unwrap().unwrap();
    assert!(!step.collected && !step.ready);
    assert!(step.status.contains("network_timeout"));
    assert_eq!(j.head(), head);
    assert!(j.eod_existing_step(at() + 86_400_000).unwrap().is_none());
}

#[test]
fn point_in_time_view_excludes_eod_at_open_and_future_revisions_and_late_receipts() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at());
    start(&mut j, "first", "20261028", at());
    finish(&mut j, "first", "20261028", "20261028", at(), outcome()).unwrap();
    let original = j
        .eod_as_of("20261028", at())
        .unwrap()
        .unwrap()
        .bar
        .close_fen;
    let original_head = j.head().to_owned();
    assert!(j.eod_as_of("20261028", at() - 1).unwrap().is_none());
    assert!(j
        .eod_as_of("20261028", at() - 8 * 3_600_000)
        .unwrap()
        .is_none());
    assert!(
        !j.eod_as_of("20261028", at())
            .unwrap()
            .unwrap()
            .opening_execution_eligible
    );
    start(&mut j, "revision", "20261028", at() + 1000);
    let mut revised = outcome();
    revised.raw[0].received_at += 1000;
    revised.bar.as_mut().unwrap().close_fen += 1;
    finish(
        &mut j,
        "revision",
        "20261028",
        "20261028",
        at() + 1000,
        revised,
    )
    .unwrap();
    start(&mut j, "late", "20261027", at() + 2000);
    finish(
        &mut j,
        "late",
        "20261027",
        "20261028",
        at() + 2000,
        late_previous_day(),
    )
    .unwrap();
    drop(j);
    let j = Journal::open(&path).unwrap();
    assert_eq!(j.entries()[2].digest, original_head);
    assert_eq!(
        j.eod_as_of("20261028", at())
            .unwrap()
            .unwrap()
            .bar
            .close_fen,
        original
    );
    assert_eq!(
        j.eod_as_of("20261028", at() + 1000)
            .unwrap()
            .unwrap()
            .bar
            .close_fen,
        original + 1
    );
    assert!(j.eod_as_of("20261027", at()).unwrap().is_none());
    assert!(
        j.eod_as_of("20261027", at() + 2000)
            .unwrap()
            .unwrap()
            .late_backfill
    );
}

#[test]
fn continuity_counts_open_gaps_failed_days_closed_days_and_late_attempts() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at() - 5 * 86_400_000); // synthetic 10/23
    let failed = at() - 2 * 86_400_000;
    start(&mut j, "failure", "20261026", failed);
    finish(
        &mut j,
        "failure",
        "20261026",
        "20261026",
        failed,
        Outcome::gap("missing_daily_not_proof_of_suspension"),
    )
    .unwrap();
    start(&mut j, "today", "20261028", at());
    let mut out = late_previous_day();
    out.bar = outcome().bar;
    out.calendar = (23..=28)
        .map(|d| CalendarDay {
            day: format!("202610{d}"),
            is_open: !matches!(d, 24 | 25),
        })
        .collect();
    finish(&mut j, "today", "20261028", "20261028", at(), out).unwrap();
    start(&mut j, "late", "20261027", at() + 1000);
    finish(
        &mut j,
        "late",
        "20261027",
        "20261028",
        at() + 1000,
        late_previous_day(),
    )
    .unwrap();
    let head = j.head().to_owned();
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let value: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    let c = &value["continuity"];
    assert_eq!(c["valid_eod_days"], 1);
    assert_eq!(c["missing_valid_eod_days"], 3);
    assert_eq!(c["closed_days"], 2);
    assert_eq!(c["longest_known_open_day_gap"], 3);
    assert_eq!(c["days"][4]["late_attempts"], 1);
    assert_eq!(c["days"][3]["on_day_attempts"], 1);
    drop(j);
    let j = Journal::open(&path).unwrap();
    assert_eq!(j.head(), head);
    let reopened = temp.path().join("reopened");
    j.report(&reopened).unwrap();
    for name in ["report.json", "daily.csv", "events.json"] {
        assert_eq!(
            fs::read(report.join(name)).unwrap(),
            fs::read(reopened.join(name)).unwrap()
        );
    }
}

#[test]
fn unknown_calendar_and_later_conflict_do_not_certify_continuity_or_asof() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at() - 86_400_000);
    start(&mut j, "first", "20261028", at());
    let mut out = outcome();
    out.calendar = vec![CalendarDay {
        day: "20261028".into(),
        is_open: true,
    }];
    finish(&mut j, "first", "20261028", "20261028", at(), out).unwrap();
    assert!(j.eod_existing_step(at()).unwrap().unwrap().ready);
    start(&mut j, "conflict", "20261028", at() + 1000);
    let mut out = outcome();
    out.calendar = vec![CalendarDay {
        day: "20261028".into(),
        is_open: false,
    }];
    finish(&mut j, "conflict", "20261028", "20261028", at() + 1000, out).unwrap();
    assert!(!j.eod_existing_step(at() + 1000).unwrap().unwrap().ready);
    assert!(j.eod_as_of("20261028", at()).unwrap().is_some());
    assert!(j.eod_as_of("20261028", at() + 1000).unwrap().is_none());
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let v: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    assert_eq!(v["continuity"]["calendar_unknown_days"], 1);
    assert_eq!(v["continuity"]["calendar_conflict_days"], 1);
    assert_eq!(v["continuity"]["valid_eod_days"], 0);
}
