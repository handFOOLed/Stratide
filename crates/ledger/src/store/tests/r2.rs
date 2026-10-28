use super::*;

#[test]
fn full_day_evidence_requires_exclusive_expiry_after_close_for_buys_and_sells() {
    let b = bar(TradingDay(20261102), 5);
    for side in [Side::Buy, Side::Sell] {
        for expiry in [
            b.opens_at.0 - 1,
            b.opens_at.0,
            b.opens_at.0 + 1,
            b.opens_at.0 + (b.closes_at.0 - b.opens_at.0) / 2,
            b.closes_at.0 - 1,
            b.closes_at.0,
            b.closes_at.0 + 1,
        ] {
            let (temp, mut l) = create();
            if side == Side::Sell {
                buy(&mut l, 100);
                apply(&mut l, "settle", observe(1000, T0 + 2 * DAY, 20261030, 0));
            }
            let mut p = proposal(&l.state.config, 2);
            p.side = side;
            p.expires_at = Timestamp(expiry);
            p.decision_at = l.state.snapshot.as_of;
            p.data_available_at = p.decision_at;
            p.earliest_execution_at = Timestamp(p.decision_at.0 + 1);
            let now = l.state.snapshot.as_of;
            let day = l.state.snapshot.trading_day;
            apply(&mut l, "submit-expiry", submit(p, day, now));
            assert_eq!(l.state.orders.last().unwrap().status, OrderStatus::Open);
            let before = l.state.clone();
            drop(l);
            let mut l = Ledger::open(temp.path().join("account")).unwrap();
            let cmd = session(b.clone());
            apply(&mut l, "match-expiry", cmd.clone());
            let order = l.state.orders.last().unwrap();
            if expiry <= b.closes_at.0 {
                assert_eq!(order.status, OrderStatus::Expired, "{side:?}/{expiry}");
                assert_eq!(l.state.fills, before.fills);
                assert_eq!(l.state.snapshot.cash, before.snapshot.cash);
                assert_eq!(l.state.snapshot.positions, before.snapshot.positions);
            } else {
                assert_eq!(order.status, OrderStatus::Filled);
                assert_eq!(l.state.fills.len(), before.fills.len() + 1);
            }
            assert_eq!(order.reserved_fee, Cny::ZERO);
            assert!(l.state.snapshot.pending_orders.is_empty());
            let done = l.state.clone();
            drop(l);
            let mut l = Ledger::open(temp.path().join("account")).unwrap();
            assert_eq!(l.state, done);
            assert!(!l.execute("match-expiry", cmd.clone()).unwrap());
            assert!(l.execute("renamed-expiry-session", cmd).is_err());
            assert_eq!(l.state, done);
        }
    }
}

#[test]
fn favorable_open_is_not_an_exception_for_short_validity() {
    for side in [Side::Buy, Side::Sell] {
        let (_temp, mut l) = create();
        if side == Side::Sell {
            buy(&mut l, 100);
            apply(&mut l, "settle", observe(1000, T0 + 2 * DAY, 20261030, 0));
        }
        let mut b = bar(TradingDay(20261102), 5);
        b.low = c(850);
        b.high = c(1150);
        b.open = c(if side == Side::Buy { 900 } else { 1100 });
        let mut p = proposal(&l.state.config, 2);
        p.side = side;
        p.expires_at = Timestamp(b.opens_at.0 + 1);
        p.decision_at = l.state.snapshot.as_of;
        p.data_available_at = p.decision_at;
        p.earliest_execution_at = Timestamp(p.decision_at.0 + 1);
        let now = l.state.snapshot.as_of;
        let day = l.state.snapshot.trading_day;
        apply(&mut l, "short", submit(p, day, now));
        let fills = l.state.fills.clone();
        apply(&mut l, "short-session", session(b));
        assert_eq!(l.state.fills, fills);
        assert_eq!(l.state.orders.last().unwrap().status, OrderStatus::Expired);
    }
}

#[test]
fn intraday_expiry_reservation_cannot_be_released_for_other_opening_reviews() {
    let temp = tempfile::tempdir().unwrap();
    let mut cfg = config();
    cfg.account_limits.max_exposure = c(330000);
    cfg.strategy_limits.max_exposure = c(330000);
    let mut l = Ledger::create(temp.path().join("account"), genesis(cfg)).unwrap();
    buy(&mut l, 100);
    let mut b = bar(TradingDay(20261030), 2);
    b.open = c(1100);
    b.low = c(1000);
    b.high = c(1150);
    b.close = c(1100);
    for id in [2, 3] {
        let mut p = proposal(&l.state.config, id);
        p.limit_price = c(1100);
        p.decision_at = Timestamp(T0 + DAY);
        p.data_available_at = p.decision_at;
        p.earliest_execution_at = Timestamp(T0 + DAY + 1);
        if id == 2 {
            p.expires_at = Timestamp(b.opens_at.0 + 1);
        }
        apply(
            &mut l,
            &format!("buy-{id}"),
            submit(p, TradingDay(20261029), Timestamp(T0 + DAY)),
        );
        assert_eq!(l.state.orders.last().unwrap().status, OrderStatus::Open);
    }
    let cash = l.state.snapshot.cash;
    apply(&mut l, "reservations-at-open", session(b));
    assert_eq!(l.state.orders[1].status, OrderStatus::Expired);
    assert_eq!(l.state.orders[2].status, OrderStatus::Open);
    assert!(l.state.orders[2].reason.contains("总敞口"));
    assert_eq!(l.state.fills.len(), 1);
    assert_eq!(l.state.snapshot.cash, cash);
    assert_eq!(l.state.snapshot.pending_orders.len(), 1);
}

#[test]
fn partial_fill_remaining_expiry_never_adds_later_fills_or_fees_after_restart() {
    let (temp, mut l) = create();
    let next = bar(TradingDay(20261030), 2);
    let mut p = proposal(&l.state.config, 1);
    p.quantity = 200;
    p.expires_at = Timestamp(next.opens_at.0 + 1);
    apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
    let first = session(bar(TradingDay(20261029), 1));
    apply(&mut l, "first-fill", first.clone());
    assert_eq!(l.state.orders[0].status, OrderStatus::PartiallyFilled);
    let cash = l.state.snapshot.cash;
    let fills = l.state.fills.clone();
    drop(l);
    let mut l = Ledger::open(temp.path().join("account")).unwrap();
    let expiry = session(next);
    apply(&mut l, "remaining-expiry", expiry.clone());
    assert_eq!(l.state.orders[0].status, OrderStatus::Expired);
    assert_eq!(l.state.orders[0].remaining, 100);
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert_eq!(l.state.fills, fills);
    assert_eq!(l.state.snapshot.cash, cash);
    let done = l.state.clone();
    drop(l);
    let mut l = Ledger::open(temp.path().join("account")).unwrap();
    assert_eq!(l.state, done);
    assert!(!l.execute("remaining-expiry", expiry).unwrap());
    assert!(!l.execute("first-fill", first).unwrap());
    apply(&mut l, "later-day", session(bar(TradingDay(20261102), 5)));
    assert_eq!(l.state.fills, fills);
    assert_eq!(l.state.snapshot.cash, cash);
    assert_eq!(l.state.snapshot.positions[0].quantity, 100);
}

#[test]
fn delayed_receipt_uses_market_window_not_receipt_time_for_expiry() {
    for quantity in [100, 200] {
        let (temp, mut l) = create();
        let mut b = bar(TradingDay(20261029), 1);
        b.available_at.0 += 2000;
        let mut p = proposal(&l.state.config, 1);
        p.quantity = quantity;
        p.expires_at = Timestamp(b.closes_at.0 + 1);
        apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
        apply(&mut l, "delayed-receipt", session(b.clone()));
        assert_eq!(l.state.fills.len(), 1);
        assert_eq!(l.state.fills[0].quantity, 100);
        assert_eq!(l.state.fills[0].simulated_at, b.available_at);
        assert_eq!(
            l.state.orders[0].status,
            if quantity == 100 {
                OrderStatus::Filled
            } else {
                OrderStatus::Expired
            }
        );
        assert!(l.state.snapshot.pending_orders.is_empty());
        assert_eq!(l.state.snapshot.cash, c(899969));
        let before = l.state.clone();
        drop(l);
        assert_eq!(
            Ledger::open(temp.path().join("account")).unwrap().state,
            before
        );
    }
}
