use super::*;
use crate::cash_dividend::{CashDividendV1, CashUnit, DividendPhase};

fn event() -> CashDividendV1 {
    let value: serde_json::Value = serde_json::from_slice(
        &fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../samples/cash-dividend-v1.json"),
        )
        .unwrap(),
    )
    .unwrap();
    serde_json::from_value(value["cash_dividends"][0].clone()).unwrap()
}
fn new_at(path: &Path, e: CashDividendV1, mut cfg: PaperAccountConfig) -> Ledger {
    cfg.max_mark_age_ms = 7 * DAY;
    cfg.max_snapshot_age_ms = 7 * DAY;
    let mut g = genesis(cfg);
    g.at = Timestamp(e.record_close_at.0 - 2 * DAY);
    g.day = TradingDay(20260713);
    Ledger::create_cash_dividend_v4(path, g, vec![e]).unwrap()
}
fn setup(e: CashDividendV1) -> (tempfile::TempDir, Ledger) {
    let t = tempfile::tempdir().unwrap();
    let l = new_at(&t.path().join("account"), e, config());
    (t, l)
}
fn phase(e: &CashDividendV1, p: DividendPhase, price: i64) -> Command {
    let (now, day) = match p {
        DividendPhase::Record => (e.record_at, e.record_day),
        DividendPhase::Ex => (e.ex_at, e.ex_day),
        DividendPhase::Payment => (e.payment_at, e.payment_day),
    };
    Command::CashDividendV1 {
        event_id: e.event_id.clone(),
        phase: p,
        now,
        day,
        marks: vec![mark(price, now.0)],
    }
}
fn proposal_at(
    l: &Ledger,
    id: u128,
    side: Side,
    quantity: i64,
    at: Timestamp,
    day: TradingDay,
    price: i64,
) -> Command {
    let mut p = proposal(&l.state.config, id);
    p.side = side;
    p.quantity = quantity;
    p.limit_price = c(price);
    p.decision_at = at;
    p.data_available_at = at;
    p.earliest_execution_at = Timestamp(at.0 + 1);
    p.expires_at = Timestamp(at.0 + 7 * DAY);
    let mut cmd = submit(p, day, at);
    if let Command::Submit { fees, .. } = &mut cmd {
        fees.as_mut().unwrap().valid_from = TradingDay(20260701);
        fees.as_mut().unwrap().valid_through = TradingDay(20260731);
    }
    cmd
}
fn filled(l: &mut Ledger, day: TradingDay, close: i64, price: i64, id: &str) {
    let mut b = bar(day, 1);
    b.provenance = l.state.provenance.clone();
    b.opens_at = Timestamp(close - 19_800_000);
    b.closes_at = Timestamp(close);
    b.available_at = Timestamp(close + 1000);
    b.open = c(price);
    b.close = c(price);
    b.low = c(price - 50);
    b.high = c(price + 50);
    apply(l, id, session(b));
}
fn buy_before(l: &mut Ledger, e: &CashDividendV1) {
    let at = l.state.snapshot.as_of;
    let cmd = proposal_at(l, 1, Side::Buy, 100, at, TradingDay(20260713), 1000);
    apply(l, "buy", cmd);
    filled(
        l,
        TradingDay(20260714),
        e.record_close_at.0 - DAY,
        1000,
        "fill-buy",
    );
    assert_eq!(l.state.fills.len(), 1);
}

#[test]
fn dividend_100_shares_gross_tax_receivable_cash_and_no_second_profit() {
    for rate in [0, 200_000, 1_000_000] {
        let mut e = event();
        e.tax.withholding_ppm = rate;
        let (_t, mut l) = setup(e.clone());
        buy_before(&mut l, &e);
        let cash = l.state.snapshot.cash;
        apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
        assert_eq!(l.state.dividend_totals().unwrap().gross_income_fen, 0);
        apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
        let totals = l.state.dividend_totals().unwrap();
        assert_eq!(totals.receivable_fen, 4200);
        assert_eq!(totals.liability_fen, i64::from(rate) * 4200 / 1_000_000);
        assert_eq!(l.state.snapshot.cash, cash);
        let nav = l.state.equity;
        let peak = l.state.risk.peak();
        apply(&mut l, "pay", phase(&e, DividendPhase::Payment, 958));
        assert_eq!(l.state.equity, nav);
        assert_eq!(l.state.risk.peak(), peak);
        assert_eq!(
            l.state.snapshot.cash.fen(),
            cash.fen() + 4200 - totals.liability_fen
        );
        assert_eq!(l.state.snapshot.equity_basis.net_external_flow_total_fen, 0);
        assert_eq!(l.state.fills.len(), 1);
        assert_eq!(l.history().unwrap().len(), 6);
        assert_eq!(l.state.dividend_totals().unwrap().receivable_fen, 0);
    }
}

#[test]
fn registration_empty_then_buy_gets_no_entitlement_and_sell_does_not_remove_it() {
    for own_at_record in [false, true] {
        let e = event();
        let (_t, mut l) = setup(e.clone());
        if own_at_record {
            buy_before(&mut l, &e);
        }
        apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
        // A new order after record: sale retains entitlement; later purchase
        // never acquires the already frozen right. Ex cancels pre-ex orders.
        apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
        let at = Timestamp(e.ex_at.0 + 19_800_001);
        apply(
            &mut l,
            "post-record-marks",
            observe(958, at.0, e.ex_day.0, 0),
        );
        let cmd = proposal_at(
            &l,
            20,
            if own_at_record { Side::Sell } else { Side::Buy },
            100,
            at,
            e.ex_day,
            958,
        );
        apply(&mut l, "post-record-trade", cmd);
        filled(
            &mut l,
            TradingDay(20260717),
            e.ex_at.0 + DAY + 19_800_000,
            958,
            "post-record-fill",
        );
        assert_eq!(l.state.fills.len(), if own_at_record { 2 } else { 1 });
        apply(&mut l, "pay", phase(&e, DividendPhase::Payment, 958));
        assert_eq!(
            l.state.dividend_totals().unwrap().cash_paid_fen,
            if own_at_record { 3360 } else { 0 }
        );
    }
}

#[test]
fn record_day_session_buy_is_eligible_despite_post_close_accounting_timestamp() {
    let e = event();
    let (_t, mut l) = setup(e.clone());
    let at = Timestamp(e.record_close_at.0 - DAY);
    let cmd = proposal_at(&l, 1, Side::Buy, 100, at, TradingDay(20260714), 1000);
    apply(&mut l, "buy-before-record-session", cmd);
    filled(
        &mut l,
        e.record_day,
        e.record_close_at.0,
        1000,
        "record-session-fill",
    );
    assert_eq!(l.state.fills.len(), 1);
    assert!(l.state.fills[0].simulated_at > e.record_close_at);
    apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
    assert_eq!(
        l.state.cash_dividends.as_ref().unwrap().events[0].entitled_shares,
        Some(100)
    );
}

#[test]
fn successive_events_are_accounted_per_event_and_overlaps_are_explicitly_rejected() {
    let e = event();
    let mut second = e.clone();
    second.event_id = "second-synthetic-event-v1".into();
    second.record_at.0 += 7 * DAY;
    second.record_close_at.0 += 7 * DAY;
    second.record_day = TradingDay(20260722);
    second.ex_at.0 += 7 * DAY;
    second.ex_day = TradingDay(20260723);
    second.payment_at.0 += 4 * DAY;
    second.payment_day = TradingDay(20260724);
    let t = tempfile::tempdir().unwrap();
    let mut cfg = config();
    cfg.max_mark_age_ms = 7 * DAY;
    cfg.max_snapshot_age_ms = 7 * DAY;
    let mut g = genesis(cfg);
    g.at = Timestamp(e.record_close_at.0 - 2 * DAY);
    g.day = TradingDay(20260713);
    let mut overlap = e.clone();
    overlap.event_id = "same-date-other-id".into();
    assert!(Ledger::create_cash_dividend_v4(
        t.path().join("overlap"),
        g.clone(),
        vec![e.clone(), overlap]
    )
    .is_err());
    let mut l = Ledger::create_cash_dividend_v4(
        t.path().join("account"),
        g,
        vec![e.clone(), second.clone()],
    )
    .unwrap();
    buy_before(&mut l, &e);
    for (i, e) in [e, second].iter().enumerate() {
        let before = 1000 - 42 * i as i64;
        let after = before - 42;
        apply(
            &mut l,
            &format!("r{i}"),
            phase(e, DividendPhase::Record, before),
        );
        apply(&mut l, &format!("e{i}"), phase(e, DividendPhase::Ex, after));
        apply(
            &mut l,
            &format!("p{i}"),
            phase(e, DividendPhase::Payment, after),
        );
    }
    assert_eq!(l.state.dividend_totals().unwrap().gross_income_fen, 8400);
    assert_eq!(l.state.dividend_totals().unwrap().tax_expense_fen, 1680);
    assert_eq!(l.state.dividend_totals().unwrap().cash_paid_fen, 6720);
    assert_eq!(l.state.equity, Some(c(998_289)));
    assert!(l.history().is_ok());
}

#[test]
fn receivable_cannot_fund_orders_and_old_pending_order_expires() {
    let e = event();
    let (_t, mut l) = setup(e.clone());
    buy_before(&mut l, &e);
    apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
    let at = Timestamp(e.record_at.0 + 1);
    let old = proposal_at(&l, 11, Side::Sell, 100, at, e.record_day, 1000);
    apply(&mut l, "old-sell", old);
    assert_eq!(l.state.snapshot.pending_orders.len(), 1);
    apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert_eq!(l.state.orders[1].status, OrderStatus::Expired);
    assert!(l.state.orders[1].reason.contains("CASH_DIVIDEND_V1"));
    let mut stale = l.state.orders[1].proposal.clone();
    stale.proposal_id = ProposalId(999);
    assert!(l
        .execute("renamed-stale", submit(stale, e.ex_day, e.ex_at))
        .is_err());
    // 900 shares plus worst-case 1800 fen fees = 901800 > cash899969,
    // but < cash+receivable904169. Enough exposure authority: reject for cash.
    let attempt = proposal_at(&l, 12, Side::Buy, 900, e.ex_at, e.ex_day, 1000);
    apply(&mut l, "cash-only", attempt);
    let order = l.state.orders.last().unwrap();
    assert_eq!(order.status, OrderStatus::Rejected);
    assert!(order.reason.contains("可用资金不足"), "{}", order.reason);
}

#[test]
fn duplicate_conflict_ordering_backfill_and_unknown_marks_fail_closed() {
    let e = event();
    let (t, mut l) = setup(e.clone());
    buy_before(&mut l, &e);
    assert!(l
        .execute("early", phase(&e, DividendPhase::Payment, 958))
        .is_err());
    assert!(l
        .execute("skip", observe(958, e.ex_at.0, e.ex_day.0, 0))
        .is_err());
    let record = phase(&e, DividendPhase::Record, 1000);
    apply(&mut l, "record", record.clone());
    assert!(!l.execute("record", record.clone()).unwrap());
    assert!(l.execute("different-id", record.clone()).is_err());
    assert!(l
        .execute("record", phase(&e, DividendPhase::Record, 1001))
        .is_err());
    let mut unknown = phase(&e, DividendPhase::Ex, 958);
    if let Command::CashDividendV1 { marks, .. } = &mut unknown {
        marks.clear();
    }
    assert!(l.execute("unknown", unknown).is_err());
    let mut stale = phase(&e, DividendPhase::Ex, 958);
    if let Command::CashDividendV1 { marks, .. } = &mut stale {
        marks[0].as_of = Timestamp(e.ex_at.0 - 1);
    }
    assert!(l.execute("stale", stale).is_err());
    let before = l.head().to_string();
    drop(l);
    let mut l = Ledger::open(t.path().join("account")).unwrap();
    assert_eq!(l.head(), before);
    assert!(!l.execute("record", record).unwrap());
    apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
    apply(&mut l, "pay", phase(&e, DividendPhase::Payment, 958));
    assert!(l
        .execute("repay", phase(&e, DividendPhase::Payment, 958))
        .is_err());
    assert!(l.history().is_ok());
}

#[test]
fn ex_tax_loss_uses_one_nav_and_financial_locks_survive_payment_restart() {
    let e = event();
    let t = tempfile::tempdir().unwrap();
    let path = t.path().join("account");
    let mut cfg = config();
    cfg.account_limits.daily_loss = c(500);
    cfg.strategy_limits.daily_loss = c(500);
    cfg.account_limits.drawdown = c(500);
    cfg.strategy_limits.drawdown = c(500);
    let mut l = new_at(&path, e.clone(), cfg);
    buy_before(&mut l, &e);
    apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
    apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
    assert_eq!(l.state.snapshot.equity_basis.day_start_equity, c(999_969));
    assert_eq!(l.state.equity, Some(c(999_129))); // only tax840 loss at ex
    assert_eq!(l.state.risk.peak(), c(1_000_000));
    assert!(l
        .state
        .risk
        .freezes(RiskScope::Account)
        .contains(&FreezeReason::DailyLoss));
    let locks = l.state.risk.clone();
    drop(l);
    let mut l = Ledger::open(&path).unwrap();
    apply(&mut l, "pay", phase(&e, DividendPhase::Payment, 958));
    assert_eq!(l.state.risk, locks);
    assert_eq!(l.state.equity, Some(c(999_129)));
}

#[test]
fn event_contract_source_tax_units_overflow_and_real_gate() {
    let e = event();
    for kind in 0..14 {
        let mut x = e.clone();
        match kind {
            0 => x.fact_status = "FACTS_PARTIAL".into(),
            1 => x.real_account_eligible = true,
            2 => x.tax.identity = "unknown".into(),
            3 => x.source_available_at = Timestamp(x.record_at.0 + 1),
            4 => x.ex_day = TradingDay(20260717),
            5 => x.schema = "STOCK_DIVIDEND".into(),
            6 => x.version.clear(),
            7 => x.cash_amount_fen = -1,
            8 => x.currency = "USD".into(),
            9 => {
                x.cash_unit = CashUnit::PerTenShares;
                x.cash_amount_fen = 421;
            }
            10 => x.source_sha256 = "unknown".into(),
            11 => x.historical_pit = "VERIFIED".into(),
            12 => x.instrument.code = "510300".into(),
            13 => x.tax.withholding_ppm = 1_000_001,
            _ => unreachable!(),
        }
        assert!(x.validate(&DataMode::SyntheticTest).is_err(), "case{kind}");
    }
    let mut ten = e.clone();
    ten.cash_unit = CashUnit::PerTenShares;
    ten.cash_amount_fen = 420;
    assert_eq!(ten.amounts(100).unwrap(), (4200, 840));
    ten.cash_amount_fen = i64::MAX - 7;
    assert!(ten.amounts(100).is_err());
    let mut tiny = e.clone();
    tiny.cash_amount_fen = 1;
    tiny.tax.withholding_ppm = 1;
    assert_eq!(tiny.amounts(1).unwrap(), (1, 1)); // explicit per-event ceiling
    let mut historical = e.clone();
    historical.mode = DataMode::HistoricalReplay;
    historical.evidence_basis = "historical_ex_post_assumption".into();
    historical.tax.basis = "historical_ex_post_assumption".into();
    historical.fact_status = "EX_POST_MODEL_ONLY".into();
    historical.source_available_at = Timestamp(historical.payment_at.0 + 1000);
    assert!(historical.validate(&DataMode::HistoricalReplay).is_ok()); // never PIT
}

#[test]
fn v3_is_never_migrated_and_v4_tamper_tail_or_genesis_is_rejected() {
    let (t, mut old) = create();
    let before = old.head().to_string();
    let e = event();
    assert!(old
        .execute("dividend", phase(&e, DividendPhase::Record, 1000))
        .is_err());
    drop(old);
    assert!(Ledger::create_cash_dividend_v4(
        t.path().join("account"),
        genesis(config()),
        vec![e.clone()]
    )
    .is_err());
    let old = Ledger::open(t.path().join("account")).unwrap();
    assert_eq!(old.schema_version(), 3);
    assert_eq!(old.head(), before);
    for kind in 0..3 {
        let (t, mut l) = setup(e.clone());
        apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
        let p = t.path().join("account");
        drop(l);
        let db = Connection::open(p.join("ledger.sqlite")).unwrap();
        match kind {
            0 => {
                db.execute(
                    "UPDATE events SET payload=replace(payload,'42','43') WHERE seq=0",
                    [],
                )
                .unwrap();
            }
            1 => {
                db.execute("DELETE FROM events WHERE seq=1", []).unwrap();
            }
            2 => {
                db.execute("UPDATE checkpoint SET digest='bad'", [])
                    .unwrap();
            }
            _ => unreachable!(),
        }
        drop(db);
        assert!(Ledger::open(&p).is_err());
    }
}

#[test]
fn dividend_crash_child() {
    let Ok(path) = std::env::var("STRATIDE_DIVIDEND_CRASH_PATH") else {
        return;
    };
    let mut l = Ledger::open(&path).unwrap();
    let e = l.state.cash_dividends.as_ref().unwrap().events[0]
        .event
        .clone();
    let p = match std::env::var("STRATIDE_DIVIDEND_PHASE").unwrap().as_str() {
        "record" => DividendPhase::Record,
        "ex" => DividendPhase::Ex,
        _ => DividendPhase::Payment,
    };
    l.execute(
        "crashed-phase",
        phase(
            &e,
            p,
            if std::env::var("STRATIDE_DIVIDEND_PHASE").unwrap() == "record" {
                1000
            } else {
                958
            },
        ),
    )
    .unwrap();
}

#[test]
fn crash_before_and_after_each_dividend_commit_is_atomic_and_idempotent() {
    for (name, target) in [
        ("record", DividendPhase::Record),
        ("ex", DividendPhase::Ex),
        ("payment", DividendPhase::Payment),
    ] {
        for point in ["before_commit", "after_commit"] {
            let e = event();
            let (t, mut l) = setup(e.clone());
            buy_before(&mut l, &e);
            if target != DividendPhase::Record {
                apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
            }
            if target == DividendPhase::Payment {
                apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
            }
            let path = t.path().join("account");
            drop(l);
            let output = Process::new(std::env::current_exe().unwrap())
                .args(["--exact", "store::tests::dividends::dividend_crash_child"])
                .env("STRATIDE_DIVIDEND_CRASH_PATH", &path)
                .env("STRATIDE_DIVIDEND_PHASE", name)
                .env("STRATIDE_TEST_CRASH_AT", point)
                .output()
                .unwrap();
            assert_eq!(output.status.code(), Some(86), "{name}/{point}: {output:?}");
            let mut l = Ledger::open(&path).unwrap();
            let cmd = phase(
                &e,
                target.clone(),
                if target == DividendPhase::Record {
                    1000
                } else {
                    958
                },
            );
            assert_eq!(
                l.execute("crashed-phase", cmd.clone()).unwrap(),
                point == "before_commit"
            );
            assert!(!l.execute("crashed-phase", cmd).unwrap());
            assert!(l.history().is_ok());
            if target == DividendPhase::Payment {
                assert_eq!(l.state.dividend_totals().unwrap().cash_paid_fen, 3360);
            }
        }
    }
}

fn historical_setup(mut e: CashDividendV1) -> (tempfile::TempDir, Ledger, CashDividendV1) {
    e.mode = DataMode::HistoricalReplay;
    e.evidence_basis = "historical_ex_post_assumption".into();
    e.fact_status = "EX_POST_MODEL_ONLY".into();
    e.tax.basis = "historical_ex_post_assumption".into();
    e.source_available_at = Timestamp(e.payment_at.0 + DAY); // Actual late acquisition, never PIT.
    let t = tempfile::tempdir().unwrap();
    let mut g = genesis(config());
    g.config.max_mark_age_ms = 7 * DAY;
    g.config.max_snapshot_age_ms = 7 * DAY;
    g.provenance.mode = DataMode::HistoricalReplay;
    g.at = Timestamp(e.record_close_at.0 - 2 * DAY);
    g.day = TradingDay(20260713);
    let l = Ledger::create_cash_dividend_v4(t.path().join("account"), g, vec![e.clone()]).unwrap();
    (t, l, e)
}

fn historical_open(l: &Ledger, day: TradingDay, opens: Timestamp, price: i64) -> Command {
    let mut b = bar(day, 1);
    b.provenance = l.state.provenance.clone();
    b.opens_at = opens;
    b.closes_at = Timestamp(opens.0 + 19_800_000);
    b.available_at = Timestamp(b.closes_at.0 + 1);
    b.open = c(price);
    b.close = c(price);
    b.high = c(price + 10);
    b.low = c(price - 10);
    Command::HistoricalNextOpenV1 {
        now: b.available_at,
        rules: rules(day, b.available_at),
        bar: b,
    }
}

fn historical_buy(l: &mut Ledger, e: &CashDividendV1) {
    let cmd = proposal_at(
        l,
        1,
        Side::Buy,
        100,
        l.state.snapshot.as_of,
        TradingDay(20260713),
        1020,
    );
    apply(l, "historical-buy", cmd);
    let cmd = historical_open(
        l,
        TradingDay(20260714),
        Timestamp(e.ex_at.0 - 2 * DAY),
        1000,
    );
    apply(l, "historical-fill", cmd);
    assert_eq!(l.state.fills.len(), 1);
    assert_eq!(l.state.fills[0].price, c(1001));
}

#[test]
fn historical_v4_open_boundary_cancels_pre_ex_orders_and_preserves_net_assets() {
    let (t, mut l, e) = historical_setup(event());
    historical_buy(&mut l, &e);
    apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
    let cmd = proposal_at(&l, 2, Side::Sell, 100, e.record_at, e.record_day, 950);
    apply(&mut l, "stale-sell", cmd);
    assert_eq!(l.state.snapshot.pending_orders.len(), 1);
    let cash = l.state.snapshot.cash.fen();
    apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
    assert_eq!(l.state.equity, Some(c(cash + 100 * 958 + 4200 - 840)));
    assert_eq!(l.state.orders[1].status, OrderStatus::Expired);
    drop(l);
    let mut l = Ledger::open(t.path().join("account")).unwrap();
    let cmd = historical_open(&l, e.ex_day, e.ex_at, 958);
    apply(&mut l, "ex-session", cmd.clone()); // equality permitted only at v4 ex/payment
    assert_eq!(l.state.fills.len(), 1); // no pre-ex stale sell
    assert!(l.execute("duplicate-session", cmd).is_err());
    let nav = l.state.equity;
    apply(&mut l, "pay", phase(&e, DividendPhase::Payment, 958));
    let cmd = historical_open(&l, e.payment_day, e.payment_at, 958);
    apply(&mut l, "payment-session", cmd);
    assert_eq!(l.state.equity, nav);
    assert_eq!(l.state.snapshot.cash, c(cash + 3360));
    assert_eq!(l.state.snapshot.equity_basis.net_external_flow_total_fen, 0);
    assert!(l.history().is_ok());
}

#[test]
fn historical_v3_still_rejects_same_open_state_without_frozen_dividend_boundary() {
    let t = tempfile::tempdir().unwrap();
    let e = event();
    let mut g = genesis(config());
    g.provenance.mode = DataMode::HistoricalReplay;
    g.at = e.ex_at;
    g.day = e.ex_day;
    let mut l = Ledger::create(t.path().join("account"), g).unwrap();
    let cmd = historical_open(&l, e.ex_day, e.ex_at, 958);
    assert!(l.execute("same-opening", cmd).is_err());
    assert_eq!(l.schema_version(), 3);
}

#[test]
fn historical_v4_crash_commit_recovery_then_same_open_replay_uses_one_reducer() {
    for (name, target) in [
        ("ex", DividendPhase::Ex),
        ("payment", DividendPhase::Payment),
    ] {
        for point in ["before_commit", "after_commit"] {
            let (t, mut l, e) = historical_setup(event());
            historical_buy(&mut l, &e);
            apply(&mut l, "record", phase(&e, DividendPhase::Record, 1000));
            if target == DividendPhase::Payment {
                apply(&mut l, "ex", phase(&e, DividendPhase::Ex, 958));
            }
            let path = t.path().join("account");
            drop(l);
            let output = Process::new(std::env::current_exe().unwrap())
                .args(["--exact", "store::tests::dividends::dividend_crash_child"])
                .env("STRATIDE_DIVIDEND_CRASH_PATH", &path)
                .env("STRATIDE_DIVIDEND_PHASE", name)
                .env("STRATIDE_TEST_CRASH_AT", point)
                .output()
                .unwrap();
            assert_eq!(output.status.code(), Some(86), "{name}/{point}: {output:?}");
            let mut l = Ledger::open(&path).unwrap();
            let cmd = phase(&e, target.clone(), 958);
            assert_eq!(
                l.execute("crashed-phase", cmd.clone()).unwrap(),
                point == "before_commit"
            );
            assert!(!l.execute("crashed-phase", cmd).unwrap());
            let (at, day) = if target == DividendPhase::Ex {
                (e.ex_at, e.ex_day)
            } else {
                (e.payment_at, e.payment_day)
            };
            let cmd = historical_open(&l, day, at, 958);
            apply(&mut l, "recovered-historical-opening", cmd);
            assert_eq!(
                l.state.equity,
                Some(c(l.state.snapshot.cash.fen()
                    + 100 * 958
                    + if target == DividendPhase::Ex { 3360 } else { 0 }))
            );
            assert!(l.history().is_ok());
        }
    }
}
