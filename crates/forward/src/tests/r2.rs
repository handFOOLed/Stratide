//! synthetic_test: exact independent readiness probe, followed by recovery/report coverage.
use super::*;

#[test]
fn r2_readiness_matches_target_date_evidence_after_backfill_and_restart() {
    for conflict_day in ["20261028", "20261027"] {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("observer");
        let mut j = create_at(&path, config(), at());
        start(&mut j, "today", "20261028", at());
        let mut today = outcome();
        today.calendar = late_previous_day().calendar;
        finish(&mut j, "today", "20261028", "20261028", at(), today).unwrap();
        let original = j.entries()[2].clone();
        assert!(j.eod_existing_step(at()).unwrap().unwrap().ready);
        start(&mut j, "backfill", "20261027", at() + 1000);
        let mut previous = late_previous_day();
        for d in &mut previous.calendar {
            if d.day == conflict_day {
                d.is_open = false;
            }
        }
        for raw in &mut previous.raw {
            raw.received_at = at() + 1000;
        }
        finish(
            &mut j,
            "backfill",
            "20261027",
            "20261028",
            at() + 1000,
            previous,
        )
        .unwrap();
        let head = j.head().to_owned();
        let expected_ready = conflict_day != "20261028";
        let step = j.eod_step_at(at() + 1001).unwrap();
        assert_eq!(step.ready, expected_ready);
        assert!(!step.collected);
        if !expected_ready {
            assert_eq!(step.status, "already_attempted_today:calendar_conflict");
        }
        assert_eq!(j.head(), head);
        assert_eq!(j.status().unwrap().collection_attempts, 2);
        assert_eq!(j.entries()[2].digest, original.digest);
        assert_eq!(
            serde_json::to_value(&j.entries()[2].event).unwrap(),
            serde_json::to_value(&original.event).unwrap()
        );
        assert_eq!(
            j.eod_as_of("20261028", at() + 1001).unwrap().is_some(),
            expected_ready
        );
        assert!(j.eod_as_of("20261028", at()).unwrap().is_some());
        let report = temp.path().join("report");
        j.report(&report).unwrap();
        let v: serde_json::Value =
            serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
        assert_eq!(
            v["continuity"]["days"][0]["state"],
            if expected_ready {
                "valid_eod"
            } else {
                "calendar_conflict"
            }
        );
        let rows = v["days_and_attempts"].as_array().unwrap();
        assert!(rows
            .iter()
            .any(|r| r["run_id"] == "today" && r["status"] == "valid_eod"));
        assert!(rows.iter().any(|r| r["run_id"] == "backfill"
            && r["late_backfill"] == true
            && r["status"] == "calendar_conflict"));
        drop(j);
        let mut j = Journal::open(&path).unwrap();
        let step = j.eod_step_at(at() + 1002).unwrap();
        assert_eq!(step.ready, expected_ready);
        assert!(!step.collected);
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
}

#[test]
fn r2_first_eod_still_conservatively_rejects_a_response_with_other_date_conflict() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("observer");
    let mut j = create_at(&path, config(), at());
    start(&mut j, "calendar-only", "20261027", at());
    let mut old = Outcome::gap("missing_daily_not_proof_of_suspension");
    old.calendar = vec![CalendarDay {
        day: "20261027".into(),
        is_open: true,
    }];
    finish(&mut j, "calendar-only", "20261027", "20261028", at(), old).unwrap();
    start(&mut j, "first-today", "20261028", at() + 1000);
    let mut today = outcome();
    today.calendar = vec![
        CalendarDay {
            day: "20261027".into(),
            is_open: false,
        },
        CalendarDay {
            day: "20261028".into(),
            is_open: true,
        },
    ];
    assert_eq!(
        finish(
            &mut j,
            "first-today",
            "20261028",
            "20261028",
            at() + 1000,
            today
        )
        .unwrap(),
        "calendar_conflict"
    );
    assert!(
        matches!(&j.entries().last().unwrap().event, Event::CollectionFinished { outcome, .. } if outcome.bar.is_none())
    );
    assert!(j.eod_as_of("20261028", at() + 1001).unwrap().is_none());
    assert!(!j.eod_existing_step(at() + 1001).unwrap().unwrap().ready);
}

#[test]
fn audit_backfill_conflict_must_invalidate_current_ready() {
    let temp = tempfile::tempdir().unwrap();
    let mut j = create_at(&temp.path().join("observer"), config(), at());
    start(&mut j, "today", "20261028", at());
    let mut today = outcome();
    today.calendar = vec![CalendarDay {
        day: "20261028".into(),
        is_open: true,
    }];
    finish(&mut j, "today", "20261028", "20261028", at(), today).unwrap();
    start(&mut j, "backfill", "20261027", at() + 1000);
    let mut previous = late_previous_day();
    previous.calendar = vec![CalendarDay {
        day: "20261028".into(),
        is_open: false,
    }];
    for raw in &mut previous.raw {
        raw.received_at = at() + 1000;
    }
    finish(
        &mut j,
        "backfill",
        "20261027",
        "20261028",
        at() + 1000,
        previous,
    )
    .unwrap();
    assert!(j.eod_as_of("20261028", at() + 1000).unwrap().is_none());
    let step = j.eod_existing_step(at() + 1000).unwrap().unwrap();
    assert!(
        !step.ready,
        "conflicting same-day calendar must invalidate readiness"
    );
}
