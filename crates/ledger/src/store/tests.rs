use super::*;
use crate::synthetic::*;
use std::process::Command as Process;
mod historical;
mod r1;
mod r2;
use stratide_contracts::*;
use stratide_risk::{FreezeReason, RiskDecision, RiskKernel, RiskScope};

fn c(fen: i64) -> Cny {
    Cny::from_fen(fen).unwrap()
}
fn config() -> PaperAccountConfig {
    let limits = RiskLimits {
        max_order_commitment: c(1_000_000),
        max_exposure: c(1_000_000),
        daily_loss: c(10_000),
        drawdown: c(15_000),
    };
    PaperAccountConfig {
        account_id: "test-paper".into(),
        authorized_principal: c(1_000_000),
        initial_capital: c(1_000_000),
        deployment: DeploymentIdentity {
            group_id: "one".into(),
            strategy_id: "one".into(),
            frozen_version: "v1".into(),
            deployment_id: "d1".into(),
        },
        account_limits: limits,
        strategy_limits: limits,
        max_mark_age_ms: 60_000,
        max_snapshot_age_ms: 60_000,
    }
}
fn create() -> (tempfile::TempDir, Ledger) {
    let temp = tempfile::tempdir().unwrap();
    let ledger = Ledger::create(temp.path().join("account"), genesis(config())).unwrap();
    (temp, ledger)
}
fn apply(l: &mut Ledger, id: &str, command: Command) {
    l.execute(id, command).unwrap();
}
fn buy(l: &mut Ledger, qty: i64) {
    let mut p = proposal(&l.state().config, 1);
    p.quantity = qty;
    apply(l, "submit", submit(p, TradingDay(20261028), Timestamp(T0)));
    apply(
        l,
        "session-29",
        session({
            let mut b = bar(TradingDay(20261029), 1);
            b.capacity_shares = qty;
            b
        }),
    );
    assert_eq!(l.state().orders[0].status, OrderStatus::Filled);
}
fn mark(price: i64, now: i64) -> PositionMark {
    PositionMark {
        instrument: instrument(),
        price: c(price),
        as_of: Timestamp(now),
        available_at: Timestamp(now),
        source: "synthetic_test/mark-v1".into(),
    }
}
fn observe(price: i64, now: i64, day: u32, flow: i64) -> Command {
    Command::Observe {
        now: Timestamp(now),
        day: TradingDay(day),
        marks: vec![mark(price, now)],
        external_flow_fen: flow,
    }
}

#[test]
fn acceptance_intraday_expiry_cannot_use_unordered_full_day_crossing() {
    let (_temp, mut l) = create();
    let b = bar(TradingDay(20261029), 1);
    let mut p = proposal(&l.state.config, 9901);
    p.expires_at = Timestamp(b.opens_at.0 + 1);
    apply(
        &mut l,
        "expiry-submit",
        submit(p, TradingDay(20261028), Timestamp(T0)),
    );
    assert_eq!(l.state.orders[0].status, OrderStatus::Open);
    apply(&mut l, "expiry-session", session(b));
    assert!(
        l.state.fills.is_empty(),
        "full-day high/low cannot prove a crossing before expiry"
    );
    assert_eq!(l.state.orders[0].status, OrderStatus::Expired);
}

#[test]
fn acceptance_missing_bar_can_be_retried_after_evidence_arrives() {
    let (_temp, mut l) = create();
    let p = proposal(&l.state.config, 1);
    apply(
        &mut l,
        "submit-audit",
        submit(p, TradingDay(20261028), Timestamp(T0)),
    );
    let b = bar(TradingDay(20261029), 1);
    let mut missing = session(b.clone());
    if let Command::Match { bar, .. } = &mut missing {
        *bar = None;
    }
    apply(&mut l, "missing-audit", missing);
    assert_eq!(l.state.fills.len(), 0);
    assert!(
        l.execute("valid-audit", session(b)).is_ok(),
        "a failed evidence check must not consume the session"
    );
    assert_eq!(l.state.fills.len(), 1);
}

#[test]
fn acceptance_closing_mark_cannot_retroactively_block_intraday_fill() {
    let (_temp, mut l) = create();
    buy(&mut l, 100);
    let mut p = proposal(&l.state.config, 2);
    p.decision_at = Timestamp(T0 + DAY);
    p.data_available_at = p.decision_at;
    p.earliest_execution_at = Timestamp(T0 + DAY + 1);
    apply(
        &mut l,
        "submit-second-audit",
        submit(p, TradingDay(20261029), Timestamp(T0 + DAY)),
    );
    assert_eq!(l.state.orders[1].status, OrderStatus::Open);
    let mut b = bar(TradingDay(20261030), 2);
    b.low = c(800);
    b.close = c(800);
    apply(&mut l, "down-day-audit", session(b));
    assert_eq!(
        l.state.orders[1].status,
        OrderStatus::Filled,
        "a close-derived loss lock cannot decide an earlier intraday fill"
    );
}

#[test]
fn stale_approvals_cannot_double_reserve_cash_or_sellable_shares() {
    let (_temp, mut l) = create();
    let old = l.state.snapshot.clone();
    let mut a = proposal(&l.state.config, 1);
    a.quantity = 600;
    let mut b = a.clone();
    b.proposal_id = ProposalId(2);
    for p in [&a, &b] {
        let cmd = submit(p.clone(), TradingDay(20261028), Timestamp(T0));
        let Command::Submit { rules, fees, .. } = cmd else {
            unreachable!()
        };
        let mut k = RiskKernel::new(config()).unwrap();
        let context = l.state.context(p, rules, fees.as_ref(), None);
        assert!(matches!(
            k.review(&old, p, &context),
            RiskDecision::Accepted(_)
        ));
    }
    apply(&mut l, "a", submit(a, TradingDay(20261028), Timestamp(T0)));
    apply(&mut l, "b", submit(b, TradingDay(20261028), Timestamp(T0)));
    assert_eq!(l.state.orders[0].status, OrderStatus::Open);
    assert_eq!(l.state.orders[1].status, OrderStatus::Rejected);
    assert!(l.state.orders[1].reason.contains("可用资金不足"));
    assert_eq!(l.state.snapshot.pending_orders.len(), 1);
    apply(
        &mut l,
        "fill",
        session({
            let mut b = bar(TradingDay(20261029), 1);
            b.capacity_shares = 600;
            b
        }),
    );
    apply(&mut l, "next-day", observe(1000, T0 + 2 * DAY, 20261030, 0));
    for id in [3, 4] {
        let mut p = proposal(&l.state.config, id);
        p.side = Side::Sell;
        p.quantity = 600;
        p.decision_at = Timestamp(T0 + 2 * DAY);
        p.data_available_at = p.decision_at;
        p.earliest_execution_at = Timestamp(p.decision_at.0 + 1);
        apply(
            &mut l,
            &format!("sell-{id}"),
            submit(p, TradingDay(20261030), Timestamp(T0 + 2 * DAY)),
        );
    }
    assert_eq!(l.state.orders[2].status, OrderStatus::Open);
    assert_eq!(l.state.orders[3].status, OrderStatus::Rejected);
    assert!(l.state.orders[3].reason.contains("持仓不足"));
}

#[test]
fn partial_fills_event_order_idempotency_restart_and_exact_accounting() {
    let (temp, mut l) = create();
    let mut p = proposal(&l.state.config, 1);
    p.quantity = 200;
    let cmd = submit(p.clone(), TradingDay(20261028), Timestamp(T0));
    apply(&mut l, "s", cmd.clone());
    assert!(!l.execute("s", cmd.clone()).unwrap());
    apply(&mut l, "same-order-new-event", cmd);
    assert_eq!(l.state.snapshot.pending_orders.len(), 1);
    let fill = session(bar(TradingDay(20261029), 1));
    apply(&mut l, "f", fill.clone());
    assert_eq!(l.state.orders[0].status, OrderStatus::PartiallyFilled);
    assert_eq!(l.state.orders[0].remaining, 100);
    assert_eq!(l.state.snapshot.cash, c(899_969));
    assert_eq!(l.state.snapshot.pending_orders[0].reserved_cash, c(100_369));
    let before = l.state.clone();
    drop(l);
    let mut l = Ledger::open(temp.path().join("account")).unwrap();
    assert_eq!(l.state, before);
    assert!(!l.execute("f", fill.clone()).unwrap());
    assert!(l.execute("renamed-session", fill).is_err());
    apply(&mut l, "f2", session(bar(TradingDay(20261030), 2)));
    assert_eq!(l.state.orders[0].status, OrderStatus::Filled);
    assert_eq!(l.state.fills.len(), 2);
    assert_eq!(l.state.snapshot.cash, c(799_938));
    assert!(l.state.snapshot.pending_orders.is_empty());
    let mut changed = p;
    changed.limit_price = c(999);
    assert!(l
        .execute(
            "conflict",
            submit(changed, TradingDay(20261030), Timestamp(T0 + 2 * DAY))
        )
        .is_err());
    l.state.validate().unwrap();
}

#[test]
fn t_plus_one_lots_sell_costs_and_shared_liquidity() {
    let (_temp, mut l) = create();
    buy(&mut l, 100);
    let mut sell = proposal(&l.state.config, 2);
    sell.side = Side::Sell;
    sell.decision_at = Timestamp(T0 + DAY);
    sell.data_available_at = sell.decision_at;
    sell.earliest_execution_at = Timestamp(T0 + DAY + 1);
    apply(
        &mut l,
        "t1",
        submit(sell.clone(), TradingDay(20261029), Timestamp(T0 + DAY)),
    );
    assert!(l.state.orders[1].reason.contains("T+1"));
    apply(&mut l, "day30", observe(1000, T0 + 2 * DAY, 20261030, 0));
    sell.proposal_id = ProposalId(3);
    sell.decision_at = Timestamp(T0 + 2 * DAY);
    sell.data_available_at = sell.decision_at;
    sell.earliest_execution_at = Timestamp(T0 + 2 * DAY + 1);
    apply(
        &mut l,
        "sell",
        submit(sell, TradingDay(20261030), Timestamp(T0 + 2 * DAY)),
    );
    // Monday after Friday; no invented weekend settlement/session.
    apply(&mut l, "sell-fill", session(bar(TradingDay(20261102), 5)));
    assert!(l.state.snapshot.positions.is_empty());
    assert_eq!(l.state.snapshot.cash, c(999_888)); // buy 31, sell 31+50
    let (_temp2, mut shared) = create();
    for id in [1, 2] {
        let p = proposal(&shared.state.config, id);
        apply(
            &mut shared,
            &format!("s{id}"),
            submit(p, TradingDay(20261028), Timestamp(T0)),
        );
    }
    apply(
        &mut shared,
        "one-session",
        session(bar(TradingDay(20261029), 1)),
    );
    assert_eq!(shared.state.fills.len(), 1);
    assert_eq!(shared.state.orders[1].status, OrderStatus::Open);
}

#[test]
fn independent_observation_rejection_peak_flows_and_financial_locks_survive_disk() {
    let (temp, mut l) = create();
    buy(&mut l, 200);
    apply(&mut l, "peak", observe(1200, T0 + DAY + 1, 20261029, 0));
    assert_eq!(l.state.risk.peak(), c(1_039_938));
    apply(
        &mut l,
        "withdraw",
        observe(1200, T0 + DAY + 2, 20261029, -10000),
    );
    apply(
        &mut l,
        "deposit",
        observe(1200, T0 + DAY + 3, 20261029, 10000),
    );
    assert_eq!(l.state.risk.peak(), c(1_039_938));
    let p = proposal(&l.state.config, 2);
    // Reject missing cost while the NEW mark has already caused a drawdown.
    apply(
        &mut l,
        "loss-no-proposal",
        observe(900, T0 + DAY + 4, 20261029, 0),
    );
    apply(
        &mut l,
        "reject-no-cost",
        Command::Submit {
            proposal: p,
            now: Timestamp(T0 + DAY + 4),
            day: TradingDay(20261029),
            rules: None,
            fees: None,
        },
    );
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        assert!(l
            .state
            .risk
            .freezes(scope)
            .contains(&FreezeReason::Drawdown));
        assert!(l
            .state
            .risk
            .freezes(scope)
            .contains(&FreezeReason::DailyLoss));
    }
    let before = l.state.clone();
    drop(l);
    let mut l = Ledger::open(temp.path().join("account")).unwrap();
    assert_eq!(l.state, before);
    apply(
        &mut l,
        "next-day-recovery",
        observe(1100, T0 + 2 * DAY, 20261030, 0),
    );
    assert!(l
        .state
        .risk
        .freezes(RiskScope::Account)
        .contains(&FreezeReason::DailyLoss));
    assert_eq!(l.state.risk.peak(), c(1_039_938));
}

#[test]
fn no_same_day_future_stale_unverified_suspended_limit_touch_or_missing_data_fills() {
    for case in 0..10 {
        let (_temp, mut l) = create();
        let p = proposal(&l.state.config, 1);
        apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
        let mut b = bar(TradingDay(20261029), 1);
        match case {
            0 => {
                b.day = TradingDay(20261028);
                b.opens_at = Timestamp(T0 - 10000);
                b.closes_at = Timestamp(T0);
                b.available_at = Timestamp(T0);
            }
            1 => b.available_at = Timestamp(b.closes_at.0 + 1),
            2 => b.status_verified = false,
            3 => {
                b.low = c(1000);
                b.high = c(1000);
            }
            4 => b.low = c(1000), // touch, no strict crossing
            5 => b.provenance.source_version = "unapproved".into(),
            6 => b.high = c(1201),
            _ => {}
        }
        let mut command = session(b);
        if let Command::Match {
            now, bar, rules, ..
        } = &mut command
        {
            if case == 1 {
                *now = Timestamp(T0 + DAY);
            }
            if case == 7 {
                *bar = None;
            }
            if case == 8 {
                rules.as_mut().unwrap().tradable = false;
            }
            if case == 9 {
                now.0 += 60001;
            }
        }
        apply(&mut l, "m", command);
        assert!(l.state.fills.is_empty(), "case {case}");
        assert_eq!(l.state.snapshot.cash, c(1_000_000));
    }
}

#[test]
fn expiry_releases_reservations_but_never_clears_uncertainty_or_loss_locks() {
    let (_temp, mut l) = create();
    let mut p = proposal(&l.state.config, 1);
    p.expires_at = Timestamp(T0 + DAY);
    apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
    apply(
        &mut l,
        "freeze",
        Command::Freeze {
            scope: RiskScope::Account,
            reason: FreezeReason::OrderUncertainty,
        },
    );
    apply(&mut l, "m", session(bar(TradingDay(20261029), 1)));
    assert_eq!(l.state.orders[0].status, OrderStatus::Expired);
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert!(l.state.fills.is_empty());
    assert!(l
        .state
        .risk
        .freezes(RiskScope::Account)
        .contains(&FreezeReason::OrderUncertainty));
}

#[test]
fn fee_expiry_and_updated_risk_block_previously_accepted_buy() {
    for kind in 0..2 {
        let (_temp, mut l) = create();
        let p = proposal(&l.state.config, 1);
        let mut cmd = submit(p, TradingDay(20261028), Timestamp(T0));
        if kind == 0 {
            if let Command::Submit { fees, .. } = &mut cmd {
                fees.as_mut().unwrap().valid_through = TradingDay(20261028);
            }
        }
        apply(&mut l, "s", cmd);
        if kind == 1 {
            apply(
                &mut l,
                "lock",
                Command::Freeze {
                    scope: RiskScope::Strategy,
                    reason: FreezeReason::DailyLoss,
                },
            );
        }
        apply(&mut l, "m", session(bar(TradingDay(20261029), 1)));
        assert!(l.state.fills.is_empty());
        assert_eq!(l.state.orders[0].status, OrderStatus::Open);
    }
}

#[test]
fn corrupted_empty_old_or_missing_ledger_never_initializes() {
    for kind in 0..9 {
        let (temp, mut l) = create();
        apply(
            &mut l,
            "lock",
            Command::Freeze {
                scope: RiskScope::Account,
                reason: FreezeReason::DailyLoss,
            },
        );
        let path = temp.path().join("account");
        drop(l);
        match kind {
            0 => fs::write(path.join("ledger.sqlite"), []).unwrap(),
            1 => fs::write(path.join("ledger.sqlite"), b"partial-corruption").unwrap(),
            2 => {
                let db = Connection::open(path.join("ledger.sqlite")).unwrap();
                db.execute_batch("PRAGMA user_version=99").unwrap();
            }
            3 => {
                let db = Connection::open(path.join("ledger.sqlite")).unwrap();
                db.execute("UPDATE events SET payload='{}'", []).unwrap();
            }
            4 => {
                let db = Connection::open(path.join("ledger.sqlite")).unwrap();
                db.execute("UPDATE events SET digest='bad'", []).unwrap();
            }
            5 => fs::remove_file(path.join("ledger.sqlite")).unwrap(),
            6 => {
                let db = Connection::open(path.join("ledger.sqlite")).unwrap();
                db.execute("DELETE FROM events WHERE seq=1", []).unwrap();
            }
            7 => {
                let db = Connection::open(path.join("ledger.sqlite")).unwrap();
                db.execute_batch("DROP TABLE checkpoint").unwrap();
            }
            8 => {
                let db = Connection::open(path.join("ledger.sqlite")).unwrap();
                db.execute("UPDATE events SET seq=3 WHERE seq=1", [])
                    .unwrap();
            }
            _ => unreachable!(),
        }
        assert!(Ledger::open(&path).is_err(), "case {kind}");
        assert!(Ledger::create(&path, genesis(config())).is_err());
    }
}

#[test]
fn suspended_or_single_price_session_still_observes_unrealized_loss() {
    for suspended in [false, true] {
        let (_temp, mut l) = create();
        buy(&mut l, 100);
        let mut b = bar(TradingDay(20261030), 2);
        b.open = c(800);
        b.low = c(800);
        b.close = c(800);
        b.high = if suspended { c(850) } else { c(800) };
        let mut cmd = session(b);
        if suspended {
            if let Command::Match { rules, .. } = &mut cmd {
                rules.as_mut().unwrap().tradable = false;
            }
        }
        apply(&mut l, "loss-session", cmd);
        assert_eq!(l.state.fills.len(), 1);
        assert!(l
            .state
            .risk
            .freezes(RiskScope::Account)
            .contains(&FreezeReason::DailyLoss));
    }
}

#[test]
fn writer_exclusion_is_real_process_and_lock_releases_on_exit() {
    let (temp, l) = create();
    let path = temp.path().join("account");
    let result = child(&path, "lock-probe", None);
    assert_eq!(
        result.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(Ledger::open(&path).is_err());
    drop(l);
    assert!(Ledger::open(path).is_ok());
}

#[test]
fn failed_storage_write_poisons_handle_and_preserves_committed_locks() {
    let (temp, mut l) = create();
    apply(
        &mut l,
        "lock",
        Command::Freeze {
            scope: RiskScope::Account,
            reason: FreezeReason::DailyLoss,
        },
    );
    let before = l.state.clone();
    l.db.execute_batch("PRAGMA query_only=ON").unwrap();
    let cmd = submit(
        proposal(&l.state.config, 1),
        TradingDay(20261028),
        Timestamp(T0),
    );
    assert!(l.execute("write-fails", cmd.clone()).is_err());
    assert!(l.poisoned);
    assert!(l.execute("retry", cmd).is_err());
    assert_eq!(l.state, before);
    drop(l);
    let recovered = Ledger::open(temp.path().join("account")).unwrap();
    assert_eq!(recovered.state, before);
}

#[test]
fn opening_nav_overflow_blocks_fill_without_discarding_closing_loss_lock() {
    let temp = tempfile::tempdir().unwrap();
    let mut cfg = config();
    cfg.initial_capital = c(i64::MAX);
    cfg.authorized_principal = cfg.initial_capital;
    cfg.account_limits.max_exposure = cfg.initial_capital;
    cfg.strategy_limits.max_exposure = cfg.initial_capital;
    let path = temp.path().join("account");
    let mut l = Ledger::create(&path, genesis(cfg)).unwrap();
    buy(&mut l, 100);
    apply(&mut l, "day30", observe(1000, T0 + 2 * DAY, 20261030, 0));
    let mut p = proposal(&l.state.config, 2);
    p.side = Side::Sell;
    p.limit_price = c(1100);
    p.decision_at = Timestamp(T0 + 2 * DAY);
    p.data_available_at = p.decision_at;
    p.earliest_execution_at = Timestamp(p.decision_at.0 + 1);
    apply(
        &mut l,
        "sell",
        submit(p, TradingDay(20261030), Timestamp(T0 + 2 * DAY)),
    );
    let cash = l.state.snapshot.cash;
    let mut b = bar(TradingDay(20261102), 5);
    b.open = c(1100);
    b.high = c(1150);
    b.low = c(800);
    b.close = c(800);
    apply(&mut l, "overflow", session(b));
    assert_eq!(l.state.snapshot.cash, cash);
    assert_eq!(l.state.fills.len(), 1);
    assert_eq!(l.state.snapshot.positions[0].quantity, 100);
    // v2 sees the overflow already in the independent OPENING NAV, before any
    // sell accounting. It still observes/persists the subsequent closing loss.
    assert!(l.state.orders[1].reason.contains("全账户估值未知"));
    assert!(l
        .state
        .risk
        .freezes(RiskScope::Account)
        .contains(&FreezeReason::DailyLoss));
    let before = l.state.clone();
    drop(l);
    assert_eq!(Ledger::open(path).unwrap().state, before);
}

fn child(path: &Path, action: &str, point: Option<&str>) -> std::process::Output {
    let mut process = Process::new(std::env::current_exe().unwrap());
    process
        .args(["--exact", "store::tests::crash_child", "--nocapture"])
        .env("STRATIDE_CHILD_PATH", path)
        .env("STRATIDE_CHILD_ACTION", action);
    if let Some(point) = point {
        process.env("STRATIDE_TEST_CRASH_AT", point);
    }
    process.output().unwrap()
}

#[test]
fn crash_child() {
    let Ok(path) = std::env::var("STRATIDE_CHILD_PATH") else {
        return;
    };
    let action = std::env::var("STRATIDE_CHILD_ACTION").unwrap();
    if action == "lock-probe" {
        assert!(Ledger::open(path).is_err());
        return;
    }
    let mut l = Ledger::open(path).unwrap();
    match action.as_str() {
        "submit" => {
            let p = proposal(&l.state.config, 1);
            apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
        }
        "fill" => apply(&mut l, "f", session(bar(TradingDay(20261029), 1))),
        "expire" => apply(&mut l, "expiry", session(bar(TradingDay(20261029), 1))),
        "observe" => apply(&mut l, "loss", observe(800, T0 + DAY + 1, 20261029, 0)),
        _ => panic!("unknown child action"),
    }
}

#[test]
fn process_death_before_after_reservation_fill_expiry_and_lock_commits_is_atomic() {
    for action in ["submit", "fill", "observe", "expire"] {
        for point in [
            "before_transaction",
            "before_reservation",
            "after_reservation",
            "before_commit",
            "after_commit",
        ] {
            let (temp, mut l) = create();
            let path = temp.path().join("account");
            if action == "fill" {
                let p = proposal(&l.state.config, 1);
                apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
            }
            if action == "observe" {
                buy(&mut l, 100);
            }
            if action == "expire" {
                let mut p = proposal(&l.state.config, 1);
                p.expires_at = Timestamp(bar(TradingDay(20261029), 1).opens_at.0 + 1);
                apply(&mut l, "s", submit(p, TradingDay(20261028), Timestamp(T0)));
            }
            let before = l.state.clone();
            drop(l);
            let result = child(&path, action, Some(point));
            assert_eq!(
                result.status.code(),
                Some(86),
                "{action}/{point}: {}",
                String::from_utf8_lossy(&result.stderr)
            );
            let mut l = Ledger::open(&path).unwrap();
            if point != "after_commit" {
                assert_eq!(l.state, before, "{action}/{point}");
            }
            let (id, cmd) = match action {
                "submit" => (
                    "s",
                    submit(
                        proposal(&l.state.config, 1),
                        TradingDay(20261028),
                        Timestamp(T0),
                    ),
                ),
                "fill" => ("f", session(bar(TradingDay(20261029), 1))),
                "expire" => ("expiry", session(bar(TradingDay(20261029), 1))),
                _ => ("loss", observe(800, T0 + DAY + 1, 20261029, 0)),
            };
            assert_eq!(l.execute(id, cmd.clone()).unwrap(), point != "after_commit");
            assert!(!l.execute(id, cmd).unwrap());
            l.state.validate().unwrap();
            match action {
                "submit" => assert_eq!(l.state.snapshot.pending_orders.len(), 1),
                "fill" => {
                    assert_eq!(l.state.fills.len(), 1);
                    assert_eq!(l.state.snapshot.cash, c(899_969));
                }
                "expire" => {
                    assert!(l.state.fills.is_empty());
                    assert!(l.state.snapshot.pending_orders.is_empty());
                    assert_eq!(l.state.snapshot.cash, c(1_000_000));
                    assert_eq!(l.state.orders[0].status, OrderStatus::Expired);
                }
                _ => assert!(l
                    .state
                    .risk
                    .freezes(RiskScope::Account)
                    .contains(&FreezeReason::DailyLoss)),
            }
        }
    }
}
