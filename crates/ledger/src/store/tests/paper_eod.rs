//! Synthetic_test only: source/time/ledger counterproofs, no market claims.
use super::*;
const HOUR: i64 = 3_600_000;
pub(super) fn atomic(l: &Ledger) -> Command {
    let now = Timestamp(T0 + HOUR);
    let mut p = proposal(&l.state.config, 1);
    p.limit_price = c(1020);
    p.decision_at = now;
    p.data_available_at = now;
    p.earliest_execution_at = Timestamp(now.0 + 1);
    Command::SubmitPaperIntentV1 {
        intent: crate::paper_eod::PaperIntent {
            now,
            target_day: TradingDay(20261029),
            decision_source_sha256: "a".repeat(64),
            proposal: p,
            rules: rules(TradingDay(20261028), now),
            fees: fees(),
            marks: vec![],
        },
    }
}
fn account() -> (tempfile::TempDir, Ledger) {
    let t = tempfile::tempdir().unwrap();
    let mut g = genesis(config());
    g.at = Timestamp(T0 + HOUR);
    g.provenance.mode = DataMode::HistoricalReplay;
    g.provenance.source_version = "paper-eod-assumption-v1:synthetic_test".into();
    g.config.max_mark_age_ms = 2 * HOUR;
    let l = Ledger::create(t.path().join("ledger"), g).unwrap();
    (t, l)
}
fn intent(l: &mut Ledger) {
    let mut p = proposal(&l.state.config, 1);
    p.limit_price = c(1020);
    p.decision_at = Timestamp(T0 + HOUR);
    p.data_available_at = p.decision_at;
    p.earliest_execution_at = Timestamp(T0 + HOUR + 1);
    l.execute(
        "intent",
        submit(p, TradingDay(20261028), Timestamp(T0 + HOUR)),
    )
    .unwrap();
}
fn seal() -> Command {
    Command::FreezePaperIntentsV1 {
        now: Timestamp(T0 + HOUR),
        target_day: TradingDay(20261029),
        decision_source_sha256: "a".repeat(64),
    }
}
fn confirm(l: &Ledger) -> Command {
    confirm_for(l, TradingDay(20261029), 1)
}
fn confirm_for(l: &Ledger, day: TradingDay, offset: i64) -> Command {
    let mut b = bar(day, offset);
    b.provenance = l.state.provenance.clone();
    b.available_at = Timestamp(b.closes_at.0 + HOUR);
    Command::ExPostOpenAssumptionV1 {
        now: b.available_at,
        rules: rules(b.day, b.available_at),
        source_received_at: b.available_at,
        source_sha256: "b".repeat(64),
        corporate_actions_verified: true,
        bar: b,
    }
}

#[test]
fn atomic_validation_and_request_conflicts_leave_no_orphan_reservations() {
    let (_t, mut l) = account();
    let before = l.state.clone();
    let head = l.head().to_string();
    for target in [20261028, 20261301, 20261120] {
        let mut cmd = atomic(&l);
        if let Command::SubmitPaperIntentV1 { intent } = &mut cmd {
            intent.target_day = TradingDay(target);
        }
        assert!(l.execute("atomic", cmd).is_err());
        assert_eq!(l.state, before);
        assert_eq!(l.head(), head);
        assert_eq!(l.history().unwrap().len(), 1);
    }
    let cmd = atomic(&l);
    assert!(l.execute("atomic", cmd.clone()).unwrap());
    assert!(!l.execute("atomic", cmd.clone()).unwrap());
    assert_eq!(l.history().unwrap().len(), 2);
    assert_eq!(l.state.snapshot.cash.fen(), 1_000_000);
    assert!(l.state.snapshot.positions.is_empty());
    assert_eq!(l.state.orders.len(), 1);
    assert_eq!(l.state.snapshot.pending_orders.len(), 1);
    assert!(l
        .state
        .paper_eod
        .as_ref()
        .unwrap()
        .pending
        .as_ref()
        .unwrap()
        .confirmation_deadline
        .is_some());
    let accepted = l.state.clone();
    let mut changed = cmd;
    if let Command::SubmitPaperIntentV1 { intent } = &mut changed {
        intent.proposal.quantity = 200;
    }
    assert!(l.execute("atomic", changed).is_err());
    assert_eq!(l.state, accepted);
}

#[test]
fn atomic_intent_and_no_fill_survive_death_on_both_sides_of_commit() {
    for action in ["paper-intent", "paper-no-fill"] {
        for point in ["before_commit", "after_commit"] {
            let (t, mut l) = account();
            let path = t.path().join("ledger");
            if action == "paper-no-fill" {
                l.execute("paper-intent", atomic(&l)).unwrap();
            }
            let before = l.state.clone();
            drop(l);
            let output = child(&path, action, Some(point));
            assert_eq!(
                output.status.code(),
                Some(86),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            let mut l = Ledger::open(&path).unwrap();
            if point == "before_commit" {
                assert_eq!(l.state, before);
            }
            let command = if action == "paper-intent" {
                atomic(&l)
            } else {
                Command::ExpirePaperIntentsV1 {
                    now: crate::paper_eod::confirmation_deadline(TradingDay(20261029)).unwrap(),
                }
            };
            assert_eq!(
                l.execute(action, command.clone()).unwrap(),
                point == "before_commit"
            );
            assert!(!l.execute(action, command).unwrap());
            assert_eq!(l.state.snapshot.cash.fen(), 1_000_000);
            assert!(l.state.snapshot.positions.is_empty());
            assert!(l.state.fills.is_empty());
            let book = l.state.paper_eod.as_ref().unwrap();
            if action == "paper-intent" {
                assert!(book.pending.is_some());
                assert_eq!(l.state.snapshot.pending_orders.len(), 1);
                assert!(book.no_fills.is_empty());
            } else {
                assert!(book.pending.is_none());
                assert!(l.state.snapshot.pending_orders.is_empty());
                assert_eq!(book.no_fills.len(), 1);
            }
            drop(l);
            assert!(Ledger::read(path).is_ok());
        }
    }
}

#[test]
fn no_bar_and_legacy_orphans_terminate_without_fills_then_new_decisions_continue() {
    let (t, mut l) = account();
    l.execute("atomic", atomic(&l)).unwrap();
    let cutoff = crate::paper_eod::confirmation_deadline(TradingDay(20261029)).unwrap();
    let before = l.state.clone();
    assert!(l
        .execute(
            "early-expiry",
            Command::ExpirePaperIntentsV1 {
                now: Timestamp(cutoff.0 - 1)
            }
        )
        .is_err());
    assert_eq!(l.state, before);
    drop(l);
    let mut l = Ledger::open(t.path().join("ledger")).unwrap();
    let mut late = confirm(&l);
    if let Command::ExPostOpenAssumptionV1 { now, .. } = &mut late {
        *now = cutoff;
    }
    assert!(l.execute("late-price", late).is_err());
    assert_eq!(l.state, before);
    let expiry = Command::ExpirePaperIntentsV1 { now: cutoff };
    l.execute("no-bar", expiry.clone()).unwrap();
    assert!(!l.execute("no-bar", expiry).unwrap());
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert_eq!(l.state.snapshot.cash, before.snapshot.cash);
    assert_eq!(l.state.snapshot.positions, before.snapshot.positions);
    assert_eq!(l.state.snapshot.marks, before.snapshot.marks);
    assert_eq!(l.state.snapshot.as_of, before.snapshot.as_of);
    assert_eq!(l.state.risk, before.risk);
    assert!(l.state.fills.is_empty());
    assert_eq!(l.state.orders[0].status, OrderStatus::Expired);
    assert_eq!(
        l.state.paper_eod.as_ref().unwrap().no_fills[0].reason,
        crate::paper_eod::NoFillReason::DataUnavailable
    );
    assert!(l.execute("old-price", confirm(&l)).is_err());
    let ended = l.state.clone();
    assert!(l
        .execute(
            "backdated-observation",
            Command::Observe {
                now: Timestamp(cutoff.0 - 1),
                day: TradingDay(20261029),
                marks: vec![],
                external_flow_fen: 0
            }
        )
        .is_err());
    assert_eq!(l.state, ended);
    let mut next = atomic(&l);
    if let Command::SubmitPaperIntentV1 { intent } = &mut next {
        intent.now = Timestamp(cutoff.0 + 1);
        intent.target_day = TradingDay(20261030);
        intent.proposal.proposal_id = ProposalId(2);
        intent.proposal.decision_at = intent.now;
        intent.proposal.data_available_at = intent.now;
        intent.proposal.earliest_execution_at = Timestamp(intent.now.0 + 1);
        intent.rules = rules(TradingDay(20261029), intent.now);
    }
    l.execute("new-day", next).unwrap();
    l.execute("new-fill", confirm_for(&l, TradingDay(20261030), 2))
        .unwrap();
    assert_eq!(l.state.fills.len(), 1);
    assert_eq!(l.state.snapshot.cash.fen(), 899867);
    assert_eq!(l.state.snapshot.positions[0].quantity, 100);
    // A fresh observed loss during atomic submission still commits the risk
    // rejection/lock, rather than rolling the observation back with a freeze.
    let mut rejected = atomic(&l);
    if let Command::SubmitPaperIntentV1 { intent } = &mut rejected {
        intent.now = Timestamp(l.state.snapshot.as_of.0 + 1);
        intent.target_day = TradingDay(20261102);
        intent.proposal.proposal_id = ProposalId(3);
        intent.proposal.decision_at = intent.now;
        intent.proposal.data_available_at = intent.now;
        intent.proposal.earliest_execution_at = Timestamp(intent.now.0 + 1);
        intent.rules = rules(TradingDay(20261030), intent.now);
        intent.marks = vec![mark(800, intent.now.0)];
    }
    l.execute("loss-rejection", rejected).unwrap();
    assert_eq!(l.state.orders.last().unwrap().status, OrderStatus::Rejected);
    assert!(l.state.paper_eod.as_ref().unwrap().pending.is_none());
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert!(l
        .state
        .risk
        .freezes(RiskScope::Account)
        .contains(&FreezeReason::DailyLoss));
    let expected = l.state.clone();
    drop(l);
    assert_eq!(
        Ledger::open(t.path().join("ledger")).unwrap().state,
        expected
    );

    let (t, mut legacy) = account();
    intent(&mut legacy); // old :submit succeeded, :freeze never happened
    legacy
        .execute(
            "lock",
            Command::Freeze {
                scope: RiskScope::Account,
                reason: FreezeReason::Manual,
            },
        )
        .unwrap();
    let before = legacy.state.clone();
    drop(legacy);
    let mut legacy = Ledger::open(t.path().join("ledger")).unwrap();
    assert!(legacy
        .execute(
            "same-day",
            Command::ExpirePaperIntentsV1 {
                now: Timestamp(T0 + 2 * HOUR)
            }
        )
        .is_err());
    legacy
        .execute(
            "recover",
            Command::ExpirePaperIntentsV1 {
                now: Timestamp(T0 + DAY + HOUR),
            },
        )
        .unwrap();
    assert_eq!(legacy.state.snapshot.cash, before.snapshot.cash);
    assert_eq!(legacy.state.snapshot.positions, before.snapshot.positions);
    assert!(legacy.state.snapshot.pending_orders.is_empty());
    assert!(legacy.state.fills.is_empty());
    assert_eq!(legacy.state.risk, before.risk);
    assert_eq!(
        legacy.state.paper_eod.as_ref().unwrap().no_fills[0].reason,
        crate::paper_eod::NoFillReason::UnsealedLegacyIntent
    );
    let expected = legacy.state.clone();
    drop(legacy);
    assert_eq!(
        Ledger::open(t.path().join("ledger")).unwrap().state,
        expected
    );
}
#[test]
fn prior_intents_restart_integer_ledger_and_read_only_projection() {
    let (t, mut l) = account();
    intent(&mut l);
    l.execute("seal", seal()).unwrap();
    let before = l.state.clone();
    drop(l);
    let mut l = Ledger::open(t.path().join("ledger")).unwrap();
    assert_eq!(l.state, before);
    let cmd = confirm(&l);
    l.execute("confirm", cmd.clone()).unwrap();
    assert_eq!(l.state.fills.len(), 1);
    assert_eq!(
        l.state.paper_eod.as_ref().unwrap().receipts[0]
            .intents
            .execution_model,
        "next-open-adverse-tick-100-v1"
    );
    let f = &l.state.fills[0];
    assert_eq!(
        (f.quantity, f.price.fen(), f.fees.total().unwrap().fen()),
        (100, 1001, 33)
    );
    assert!(f.opening_evidence.is_none());
    assert!(f
        .historical_execution
        .as_ref()
        .unwrap()
        .starts_with("EX_POST_OPEN_ASSUMPTION"));
    assert_eq!(l.state.snapshot.cash.fen(), 899867);
    assert!(!l.execute("confirm", cmd).unwrap());
    let expected = l.state.clone();
    drop(l);
    let mut ro = Ledger::read(t.path().join("ledger")).unwrap();
    assert_eq!(ro.state, expected);
    assert!(ro
        .execute(
            "write-through-reader",
            Command::Freeze {
                scope: RiskScope::Account,
                reason: FreezeReason::Manual
            }
        )
        .is_err());
}
#[test]
fn next_day_input_cannot_select_cancel_or_rewrite_frozen_orders() {
    let (_t, mut l) = account();
    intent(&mut l);
    assert!(l.execute("without-seal", confirm(&l)).is_err());
    l.execute("seal", seal()).unwrap();
    let s = l.state.clone();
    let mut p = proposal(&s.config, 2);
    p.quantity = 200;
    assert!(l
        .execute(
            "late-choice",
            submit(p, TradingDay(20261028), Timestamp(T0 + HOUR))
        )
        .is_err());
    for case in 0..5 {
        let mut cmd = confirm(&l);
        if let Command::ExPostOpenAssumptionV1 {
            bar,
            source_received_at,
            source_sha256,
            corporate_actions_verified,
            ..
        } = &mut cmd
        {
            match case {
                0 => *corporate_actions_verified = false,
                1 => source_sha256.clear(),
                2 => *source_received_at = bar.opens_at,
                3 => bar.day = TradingDay(20261030),
                4 => bar.status_verified = false,
                _ => unreachable!(),
            }
        }
        assert!(l.execute(&format!("invalid-{case}"), cmd).is_err());
        assert_eq!(l.state, s);
    }
}
#[test]
fn account_risk_lock_still_rejects_assumed_open_fill() {
    let (_t, mut l) = account();
    intent(&mut l);
    l.execute("seal", seal()).unwrap();
    l.execute(
        "halt",
        Command::Freeze {
            scope: RiskScope::Account,
            reason: FreezeReason::Manual,
        },
    )
    .unwrap();
    l.execute("confirm", confirm(&l)).unwrap();
    assert!(l.state.fills.is_empty());
    assert_eq!(l.state.snapshot.cash.fen(), 1_000_000);
    assert!(!l.state.risk.freezes(RiskScope::Account).is_empty());
}
