//! synthetic_test regressions for the independent rejection of 945b250.
use super::*;

#[test]
fn r1_interrupted_attempt_consumes_automatic_slot_before_and_after_recovery() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at());
    start(&mut j, "unknown-response", "20261028", at());
    // The persisted intent already consumes the slot, even before Interrupted.
    assert!(j.eod_existing_step(at() + 1).unwrap().is_some());
    drop(j);
    let mut j = Journal::open(&path).unwrap();
    let before = j.status().unwrap().collection_attempts;
    let step = j.eod_step_at(at() + 1).unwrap();
    assert!(!step.collected && !step.ready);
    assert!(step.status.contains("interrupted_response_unknown"));
    assert_eq!(j.status().unwrap().collection_attempts, before);
    assert_eq!(j.status().unwrap().pending_runs, 0);
    let head = j.head().to_owned();
    drop(j);
    let mut j = Journal::open(&path).unwrap();
    assert!(!j.eod_step_at(at() + 2).unwrap().collected);
    assert_eq!(j.head(), head);
    // An old day's interruption does not consume tomorrow's slot.
    assert!(j.eod_existing_step(at() + 86_400_000).unwrap().is_none());
    // Manual retry remains available; it does not reconstruct the unknown raw.
    j.collect_once(None).unwrap();
    assert_eq!(j.status().unwrap().collection_attempts, before + 1);
    assert_eq!(j.status().unwrap().actual_valid_forward_days, 0);
}

#[test]
fn r1_automatic_recovery_does_not_start_a_new_collection() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at());
    start(&mut j, "unknown-response", "20261028", at());
    drop(j);
    let mut j = Journal::open(&path).unwrap();
    let step = j.eod_step_at(at() + 1).unwrap();
    assert!(
        !step.collected,
        "automatic recovery must wait for an explicit retry"
    );
    assert_eq!(j.status().unwrap().collection_attempts, 1);
}

#[test]
fn r1_later_rollback_cannot_erase_an_earlier_asof_view() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at());
    start(&mut j, "first", "20261028", at());
    finish(&mut j, "first", "20261028", "20261028", at(), outcome()).unwrap();
    start(&mut j, "later", "20261028", at() + 2000);
    finish(
        &mut j,
        "later",
        "20261028",
        "20261028",
        at() + 2000,
        Outcome::gap("network_timeout_or_tls_error"),
    )
    .unwrap();
    let before = serde_json::to_value(j.eod_as_of("20261028", at() + 1000).unwrap()).unwrap();
    assert!(!before.is_null());
    assert!(check_clock(&mut j, at() - 1000).is_err());
    let after = serde_json::to_value(j.eod_as_of("20261028", at() + 1000).unwrap()).unwrap();
    assert_eq!(
        before, after,
        "a later fault with a regressed clock cannot become a past fact"
    );
    assert!(j.eod_as_of("20261028", at() + 2001).unwrap().is_none());
    assert!(j.eod_as_of("20261028", at() + 2000).unwrap().is_some());
    let uncertainty = j.clock_uncertainty().unwrap();
    assert_eq!(uncertainty.ordered_prefix_high_water, at() + 2000);
    assert_eq!(uncertainty.reported_detected_at, at() - 1000);
    assert_eq!(
        uncertainty.fault_sequence,
        uncertainty.ordered_prefix_last_sequence + 1
    );
    drop(j);
    let j = Journal::open(&path).unwrap();
    assert_eq!(
        before,
        serde_json::to_value(j.eod_as_of("20261028", at() + 1000).unwrap()).unwrap()
    );
}

#[test]
fn r1_process_death_at_start_and_finish_commit_boundaries_respects_automatic_slot() {
    for stage in ["start", "finish"] {
        for point in ["before_commit", "after_commit"] {
            let temp = tempfile::tempdir().unwrap();
            let path = temp.path().join("observer");
            let mut j = create_at(&path, config(), at());
            if stage == "finish" {
                start(&mut j, "pending", "20261028", at());
            }
            drop(j);
            let flag = if stage == "start" {
                "STRATIDE_FORWARD_TEST_START"
            } else {
                "STRATIDE_FORWARD_TEST_FINISH"
            };
            let out = std::process::Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "tests::crash_child", "--nocapture"])
                .env("STRATIDE_FORWARD_TEST_ROOT", &path)
                .env(flag, "1")
                .env("STRATIDE_FORWARD_FAULT_POINT", point)
                .output()
                .unwrap();
            assert_eq!(out.status.code(), Some(86));
            let mut j = Journal::open(&path).unwrap();
            let attempts = j.status().unwrap().collection_attempts;
            let no_intent = stage == "start" && point == "before_commit";
            let step = j.eod_step_at(at() + 1).unwrap();
            assert_eq!(step.collected, no_intent, "{stage}/{point}");
            assert_eq!(
                j.status().unwrap().collection_attempts,
                attempts + usize::from(no_intent)
            );
            assert_eq!(j.status().unwrap().pending_runs, 0);
            assert_eq!(step.ready, stage == "finish" && point == "after_commit");
            if !no_intent {
                let head = j.head().to_owned();
                drop(j);
                let mut j = Journal::open(&path).unwrap();
                assert!(!j.eod_step_at(at() + 2).unwrap().collected);
                assert_eq!(j.head(), head);
            }
        }
    }
}

#[test]
fn r1_calendar_conflict_is_scoped_to_its_date_in_asof_and_report() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at() - 86_400_000);
    start(&mut j, "previous-day", "20261027", at());
    finish(
        &mut j,
        "previous-day",
        "20261027",
        "20261028",
        at(),
        late_previous_day(),
    )
    .unwrap();
    start(&mut j, "today", "20261028", at());
    let mut today = outcome();
    today.calendar = late_previous_day().calendar;
    finish(&mut j, "today", "20261028", "20261028", at(), today).unwrap();
    assert!(j.eod_as_of("20261027", at()).unwrap().is_some());
    let before = serde_json::to_value(j.eod_as_of("20261028", at()).unwrap()).unwrap();
    assert!(!before.is_null());
    start(&mut j, "conflict-only-yesterday", "20261028", at() + 1000);
    let mut revised = outcome();
    revised.calendar = vec![
        CalendarDay {
            day: "20261027".into(),
            is_open: false,
        },
        CalendarDay {
            day: "20261028".into(),
            is_open: true,
        },
    ];
    finish(
        &mut j,
        "conflict-only-yesterday",
        "20261028",
        "20261028",
        at() + 1000,
        revised,
    )
    .unwrap();
    assert_eq!(
        before,
        serde_json::to_value(j.eod_as_of("20261028", at() + 1000).unwrap()).unwrap()
    );
    assert!(j.eod_as_of("20261027", at() + 1000).unwrap().is_none());
    assert!(j.eod_as_of("20261027", at()).unwrap().is_some());
    let report = temp.path().join("report");
    j.report(&report).unwrap();
    let v: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    assert_eq!(v["continuity"]["calendar_conflict_days"], 1);
    assert_eq!(v["continuity"]["valid_eod_days"], 1);
    drop(j);
    let j = Journal::open(&path).unwrap();
    assert_eq!(
        before,
        serde_json::to_value(j.eod_as_of("20261028", at() + 1000).unwrap()).unwrap()
    );
}
