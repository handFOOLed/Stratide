//! Synthetic engine probes exercising the explicitly historical model; these
//! fixtures are never evidence of market provenance or observed forward returns.
use super::*;

fn historical() -> (tempfile::TempDir, Ledger) {
    let temp = tempfile::tempdir().unwrap();
    let mut g = genesis(config());
    g.provenance.mode = DataMode::HistoricalReplay;
    let l = Ledger::create(temp.path().join("account"), g).unwrap();
    (temp, l)
}

fn next(l: &Ledger, day: u32, offset: i64) -> Command {
    let mut b = bar(TradingDay(day), offset);
    b.provenance = l.state.provenance.clone();
    Command::HistoricalNextOpenV1 {
        now: b.available_at,
        rules: rules(b.day, b.available_at),
        bar: b,
    }
}

fn submit_buy(l: &mut Ledger, id: u128) {
    let mut p = proposal(&l.state.config, id);
    p.limit_price = c(1020);
    apply(
        l,
        &format!("buy-{id}"),
        submit(p, TradingDay(20261028), Timestamp(T0)),
    );
}

#[test]
fn historical_fen_fees_tplusone_reservations_and_restart_are_conserved() {
    let (temp, mut l) = historical();
    submit_buy(&mut l, 1);
    let cmd = next(&l, 20261029, 1);
    apply(&mut l, "open29", cmd.clone());
    assert_eq!(l.state.fills.len(), 1);
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
        .starts_with("historical_ex_post_execution_assumption"));
    assert_eq!(l.state.snapshot.cash.fen(), 899867);
    assert!(l.state.snapshot.pending_orders.is_empty());
    let mut sell = proposal(&l.state.config, 2);
    sell.side = Side::Sell;
    sell.limit_price = c(980);
    sell.decision_at = Timestamp(T0 + DAY);
    sell.data_available_at = sell.decision_at;
    sell.earliest_execution_at = Timestamp(T0 + DAY + 1);
    apply(
        &mut l,
        "same-day-sell",
        submit(sell.clone(), TradingDay(20261029), Timestamp(T0 + DAY)),
    );
    assert_eq!(l.state.orders[1].status, OrderStatus::Rejected);
    assert!(l.state.orders[1].reason.contains("T+1"));
    let day30 = next(&l, 20261030, 2);
    apply(&mut l, "open30", day30);
    // Submit after settlement, still using only the current EOD snapshot.
    sell.proposal_id = ProposalId(3);
    sell.decision_at = Timestamp(T0 + 2 * DAY);
    sell.data_available_at = sell.decision_at;
    sell.earliest_execution_at = Timestamp(T0 + 2 * DAY + 1);
    apply(
        &mut l,
        "sell30",
        submit(sell, TradingDay(20261030), Timestamp(T0 + 2 * DAY)),
    );
    let sell_cmd = next(&l, 20261102, 5);
    apply(&mut l, "open02", sell_cmd.clone());
    assert_eq!(l.state.fills.len(), 2);
    assert_eq!(l.state.fills[1].fees.total().unwrap().fen(), 81);
    assert_eq!(l.state.snapshot.cash.fen(), 999686);
    assert!(l.state.snapshot.positions.is_empty());
    let before = l.state.clone();
    drop(l);
    let mut recovered = Ledger::open(temp.path().join("account")).unwrap();
    assert_eq!(recovered.state, before);
    apply(&mut recovered, "open02", sell_cmd.clone());
    assert_eq!(recovered.state, before);
    assert!(recovered
        .execute("different-id-same-session", sell_cmd)
        .is_err());
    assert_eq!(recovered.state, before);
}

#[test]
fn historical_later_extrema_volume_and_close_do_not_select_open_fills() {
    let mut outcomes = vec![];
    for price in [810, 1100] {
        let (temp, mut l) = historical();
        submit_buy(&mut l, 1);
        let mut cmd = next(&l, 20261029, 1);
        if let Command::HistoricalNextOpenV1 { bar, .. } = &mut cmd {
            bar.low = c(800);
            bar.high = c(1200);
            bar.close = c(price);
            bar.volume_shares = if price == 810 { 0 } else { 1_000_000 };
            bar.capacity_shares = 0; // Neither controls the fixed historical capacity.
        }
        apply(&mut l, "open", cmd);
        outcomes.push((
            l.state.fills[0].quantity,
            l.state.fills[0].price,
            l.state.fills[0].fees.clone(),
        ));
        assert_eq!(
            l.state
                .risk
                .freezes(RiskScope::Account)
                .contains(&FreezeReason::DailyLoss),
            price == 810
        );
        if price == 810 {
            let risk = l.state.risk.clone();
            drop(l);
            let mut resumed = Ledger::open(temp.path().join("account")).unwrap();
            assert_eq!(resumed.state.risk, risk);
            let recovered_quote = next(&resumed, 20261030, 2);
            apply(&mut resumed, "next-day-recovered-quote", recovered_quote);
            assert!(resumed
                .state
                .risk
                .freezes(RiskScope::Account)
                .contains(&FreezeReason::DailyLoss));
            let mut p = proposal(&resumed.state.config, 2);
            p.limit_price = c(1020);
            p.decision_at = Timestamp(T0 + 2 * DAY);
            p.data_available_at = p.decision_at;
            p.earliest_execution_at = Timestamp(T0 + 2 * DAY + 1);
            apply(
                &mut resumed,
                "blocked-after-restart",
                submit(p, TradingDay(20261030), Timestamp(T0 + 2 * DAY)),
            );
            assert_eq!(resumed.state.orders[1].status, OrderStatus::Rejected);
            assert!(resumed.state.orders[1].reason.contains("风险冻结"));
        }
    }
    assert_eq!(outcomes[0], outcomes[1]);
}

#[test]
fn historical_mode_gate_limit_jump_suspension_capacity_and_locks_are_binding() {
    let (_temp, mut synthetic) = create();
    let mut cmd = next(&synthetic, 20261029, 1);
    assert!(synthetic
        .execute("no-historical-in-synthetic", cmd.clone())
        .is_err());
    for reason in ["limit", "suspended", "frozen", "unknown-settlement"] {
        let (_temp, mut l) = historical();
        submit_buy(&mut l, 1);
        cmd = next(&l, 20261029, 1);
        if let Command::HistoricalNextOpenV1 { bar, rules, .. } = &mut cmd {
            match reason {
                "limit" => bar.open = c(1100),
                "suspended" => rules.tradable = false,
                "unknown-settlement" => rules.settlement = SettlementRule::Unknown,
                _ => apply(
                    &mut l,
                    "lock",
                    Command::Freeze {
                        scope: RiskScope::Account,
                        reason: FreezeReason::Manual,
                    },
                ),
            }
        }
        if reason == "unknown-settlement" {
            assert!(l.execute("open", cmd).is_err());
        } else {
            apply(&mut l, "open", cmd);
            assert!(l.state.snapshot.pending_orders.is_empty());
        }
        assert!(l.state.fills.is_empty());
        assert_eq!(l.state.snapshot.cash.fen(), 1_000_000);
    }
    let (_temp, mut l) = historical();
    submit_buy(&mut l, 1);
    submit_buy(&mut l, 2);
    let cmd = next(&l, 20261029, 1);
    apply(&mut l, "open", cmd);
    assert_eq!(l.state.fills.len(), 1); // Shared capacity, never per-order duplication.
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert_eq!(l.state.orders[1].status, OrderStatus::Expired);
}
