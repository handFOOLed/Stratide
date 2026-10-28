use super::*;

fn next_buy(l: &mut Ledger) {
    let mut p = proposal(&l.state.config, 2);
    p.decision_at = Timestamp(T0 + DAY);
    p.data_available_at = p.decision_at;
    p.earliest_execution_at = Timestamp(T0 + DAY + 1);
    apply(
        l,
        "next-buy",
        submit(p, TradingDay(20261029), Timestamp(T0 + DAY)),
    );
    assert_eq!(l.state.orders[1].status, OrderStatus::Open);
}

#[test]
fn closing_price_only_changes_post_execution_nav_not_fill_eligibility() {
    let mut results = vec![];
    for close in [800, 1000] {
        let (temp, mut l) = create();
        buy(&mut l, 100);
        next_buy(&mut l);
        let mut b = bar(TradingDay(20261030), 2);
        b.low = c(800);
        b.close = c(close);
        let open = b.opens_at;
        let accounted_at = b.available_at;
        apply(&mut l, "close-invariance", session(b));
        assert_eq!(l.state.orders[1].status, OrderStatus::Filled);
        let f = &l.state.fills[1];
        assert_eq!(f.risk_checked_at, open);
        assert_eq!(f.simulated_at, accounted_at);
        assert!(f
            .opening_evidence
            .marks
            .iter()
            .all(|m| m.available_at <= f.risk_checked_at));
        assert_eq!(
            l.state
                .risk
                .freezes(RiskScope::Account)
                .contains(&FreezeReason::DailyLoss),
            close == 800
        );
        let before = l.state.clone();
        drop(l);
        let recovered = Ledger::open(temp.path().join("account")).unwrap();
        assert_eq!(recovered.state, before);
        results.push((
            recovered.state.snapshot.cash,
            recovered.state.fills[1].quantity,
            recovered.state.fills[1].fees.clone(),
            recovered.state.equity,
        ));
    }
    assert_eq!(results[0].0, results[1].0);
    assert_eq!(results[0].1, results[1].1);
    assert_eq!(results[0].2, results[1].2);
    assert_ne!(results[0].3, results[1].3);
}

#[test]
fn genuine_opening_loss_blocks_buy_even_when_close_recovers() {
    let (_temp, mut l) = create();
    buy(&mut l, 100);
    next_buy(&mut l);
    let mut b = bar(TradingDay(20261030), 2);
    b.open = c(800);
    b.low = c(800);
    b.close = c(1000);
    apply(&mut l, "opening-loss", session(b));
    assert_eq!(l.state.fills.len(), 1);
    assert_eq!(l.state.orders[1].status, OrderStatus::Open);
    assert!(l.state.orders[1].reason.contains("执行前风控拒绝"));
    assert!(l
        .state
        .risk
        .freezes(RiskScope::Account)
        .contains(&FreezeReason::DailyLoss));
}

#[test]
fn missing_future_or_stale_opening_evidence_never_gets_invented_from_daily_bar() {
    for kind in 0..3 {
        let (_temp, mut l) = create();
        buy(&mut l, 100);
        next_buy(&mut l);
        let mut b = bar(TradingDay(20261030), 2);
        b.low = c(800);
        b.close = c(800);
        let mut cmd = session(b);
        if let Command::Match { opening, .. } = &mut cmd {
            match kind {
                0 => *opening = None,
                1 => opening.as_mut().unwrap().marks[0].available_at = Timestamp(T0 + 2 * DAY),
                _ => opening.as_mut().unwrap().rules.available_at.0 -= 60_001,
            }
        }
        apply(&mut l, "no-opening-proof", cmd);
        assert_eq!(l.state.fills.len(), 1);
        // A valid closing mark must still trigger independent risk observation.
        assert!(l
            .state
            .risk
            .freezes(RiskScope::Account)
            .contains(&FreezeReason::DailyLoss));
    }
}

#[test]
fn committed_close_observation_cannot_be_rolled_back_to_replay_opening_risk() {
    let (_temp, mut l) = create();
    buy(&mut l, 100);
    next_buy(&mut l);
    apply(
        &mut l,
        "observed-close",
        observe(800, T0 + 2 * DAY, 20261030, 0),
    );
    let locked = l.state.risk.clone();
    let mut b = bar(TradingDay(20261030), 2);
    b.low = c(800);
    b.close = c(800);
    apply(&mut l, "late-retrospective-fill", session(b));
    assert_eq!(l.state.fills.len(), 1);
    assert_eq!(l.state.risk, locked);
    assert!(l.state.orders[1].reason.contains("不能回溯"));
}

#[test]
fn incomplete_bar_or_rules_retry_survives_restart_without_reusing_valid_capacity() {
    for kind in 0..3 {
        let (temp, mut l) = create();
        let p = proposal(&l.state.config, 1);
        apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
        let good = session(bar(TradingDay(20261029), 1));
        let mut bad = good.clone();
        if let Command::Match { bar, rules, .. } = &mut bad {
            match kind {
                0 => *bar = None,
                1 => *rules = None,
                _ => bar.as_mut().unwrap().status_verified = false,
            }
        }
        let at = l.state.snapshot.as_of;
        let risk = l.state.risk.clone();
        let pending = l.state.snapshot.pending_orders.clone();
        apply(&mut l, "incomplete", bad.clone());
        assert_eq!(l.state.snapshot.as_of, at);
        assert_eq!(l.state.risk, risk);
        assert_eq!(l.state.snapshot.pending_orders, pending);
        assert!(l.state.sessions.is_empty());
        drop(l);
        let mut l = Ledger::open(temp.path().join("account")).unwrap();
        apply(&mut l, "valid", good.clone());
        assert_eq!(l.state.fills.len(), 1);
        let before = l.state.clone();
        assert!(!l.execute("incomplete", bad).unwrap());
        assert!(!l.execute("valid", good.clone()).unwrap());
        assert!(l.execute("another-valid-id", good).is_err());
        assert_eq!(l.state, before);
    }
}

#[test]
fn v1_ledger_is_preserved_and_rejected_without_automatic_reinterpretation() {
    let (temp, l) = create();
    drop(l);
    let path = temp.path().join("account");
    let db = Connection::open(path.join("ledger.sqlite")).unwrap();
    db.execute_batch("PRAGMA user_version=1").unwrap();
    drop(db);
    let original = fs::read(path.join("ledger.sqlite")).unwrap();
    let error = Ledger::open(&path)
        .err()
        .expect("v1 must not be replayed with v2 matching");
    assert!(error.contains("v2"));
    assert_eq!(fs::read(path.join("ledger.sqlite")).unwrap(), original);
    assert!(Ledger::create(&path, genesis(config())).is_err());
}
