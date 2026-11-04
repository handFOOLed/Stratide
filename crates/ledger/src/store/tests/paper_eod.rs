//! Synthetic_test only: source/time/ledger counterproofs, no market claims.
use super::*;
const HOUR: i64 = 3_600_000;
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
    let mut b = bar(TradingDay(20261029), 1);
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
