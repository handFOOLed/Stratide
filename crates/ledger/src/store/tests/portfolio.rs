use super::*;
use crate::portfolio::session;
use crate::portfolio::*;

fn at(day: u32, hour: u32) -> Timestamp {
    session(TradingDay(day), hour, 0).unwrap()
}
fn instruments() -> Vec<Instrument> {
    (0..24)
        .map(|n| Instrument {
            market: if n % 2 == 0 {
                Market::Shanghai
            } else {
                Market::Shenzhen
            },
            code: if n % 2 == 0 {
                format!("600{n:03}")
            } else {
                format!("000{n:03}")
            },
        })
        .collect()
}
pub(super) fn setup() -> (tempfile::TempDir, Ledger) {
    let t = tempfile::tempdir().unwrap();
    let mut g = genesis(config());
    g.at = at(20261028, 8);
    g.provenance.mode = DataMode::HistoricalReplay;
    g.provenance.source_version = "paper-eod-assumption-v1:synthetic_test/portfolio".into();
    g.config.max_mark_age_ms = 8 * 3600_000;
    g.config.max_snapshot_age_ms = 8 * 3600_000;
    let mut l = Ledger::create(t.path().join("account"), g).unwrap();
    let symbols = instruments();
    let policy = Policy {
        version: crate::portfolio::VERSION.into(),
        universe: symbols.clone(),
        target_value: c(201_000),
        max_positions: 24,
        max_daily_orders: 24,
        max_candidates: 24,
        max_order_shares: 200,
        capacity_shares: 100,
        capacity_scope: Some(CapacityScope::Batch),
        unverified_eod_assumption: None,
        max_symbol_value: c(400_000),
        max_daily_fees: c(100_000),
        slippage_bps: 100,
        min_amount_thousand_yuan: 10000,
        fees: symbols
            .iter()
            .map(|i| {
                let mut f = fees();
                f.instrument = i.clone();
                f
            })
            .collect(),
        approve_fixed_baseline: true,
        automatic: true,
    };
    apply(
        &mut l,
        "policy",
        Command::ConfigurePortfolioV1 {
            now: at(20261028, 8),
            policy,
        },
    );
    (t, l)
}
pub(super) fn decision(l: &Ledger, day: u32, target_day: u32) -> Command {
    let now = at(day, 8);
    let securities = instruments()
        .into_iter()
        .enumerate()
        .map(|(n, i)| {
            let mut r = rules(TradingDay(day), now);
            r.instrument = i.clone();
            Security {
                instrument: i,
                close: c(1000),
                rules: r,
                supported: n < 20,
                adjustment_factor: None,
                amount_thousand_yuan: 20000,
                reason: if n >= 20 { "BSE_ST_NEW_UNVERIFIED" } else { "" }.into(),
            }
        })
        .collect::<Vec<_>>();
    let selected = securities.iter().map(|s| s.instrument.clone()).collect();
    Command::FreezePortfolioV1 {
        decision: Decision {
            now,
            day: TradingDay(day),
            source_sha256: "a".repeat(64),
            received_at: now,
            calendar_sha256: "b".repeat(64),
            calendar_received_at: now,
            calendar: vec![
                CalendarDay {
                    day: TradingDay(day),
                    sse_open: true,
                    szse_open: true,
                },
                CalendarDay {
                    day: TradingDay(target_day),
                    sse_open: true,
                    szse_open: true,
                },
            ],
            research: Some(Research {
                task_id: "original-1".into(),
                candidate_sha256: "c".repeat(64),
                registration_sha256: "d".repeat(64),
                model_version: "test-only".into(),
                generated_at: now,
                finished_at: now,
                ready_sessions: 84,
                restriction: "RESEARCH_ONLY".into(),
                eligibility: "ELIGIBILITY_DENIED".into(),
                can_execute_forward_paper: false,
                selected,
            }),
            securities,
            marks: l
                .state
                .snapshot
                .positions
                .iter()
                .map(|lot| PositionMark {
                    instrument: lot.instrument.clone(),
                    price: c(1000),
                    as_of: now,
                    available_at: now,
                    source: "synthetic_test".into(),
                })
                .collect(),
            source_ready: true,
            reason: String::new(),
        },
    }
}
pub(super) fn confirm(l: &Ledger) -> Command {
    let day = l
        .state
        .portfolio
        .as_ref()
        .unwrap()
        .batches
        .last()
        .unwrap()
        .target_day
        .unwrap();
    let now = at(day.0, 8);
    let quotes = instruments()
        .into_iter()
        .map(|i| {
            let mut b = bar(day, 1);
            b.instrument = i.clone();
            b.provenance = l.state.provenance.clone();
            b.opens_at = session(day, 1, 30).unwrap();
            b.closes_at = session(day, 7, 0).unwrap();
            b.available_at = now;
            let mut r = rules(day, now);
            r.instrument = i;
            Quote {
                bar: b,
                rules: r,
                corporate_actions_verified: true,
                paper_assumption: None,
                reason: String::new(),
            }
        })
        .collect();
    Command::ConfirmPortfolioV1 {
        confirmation: Confirmation {
            now,
            day,
            source_sha256: "e".repeat(64),
            received_at: now,
            quotes,
        },
    }
}

#[test]
fn shared_cash_24_securities_partial_missing_actions_limits_restart_and_repeat() {
    let (t, mut l) = setup();
    let cmd = decision(&l, 20261028, 20261029);
    apply(&mut l, "batch", cmd.clone());
    let book = l.state.portfolio.as_ref().unwrap();
    assert_eq!(book.batches[0].rejections.len(), 4);
    assert!(l
        .state
        .orders
        .iter()
        .any(|o| o.status == OrderStatus::Rejected)); // shared cash, not 24 capitals
    let reserved: i64 = l
        .state
        .snapshot
        .pending_orders
        .iter()
        .map(|o| o.reserved_cash.fen())
        .sum();
    assert!(reserved > 0 && reserved <= l.state.snapshot.cash.fen());
    assert!(!l.execute("batch", cmd.clone()).unwrap());
    assert!(l.execute("fresh-id", cmd).is_err());
    assert!(Ledger::open(t.path().join("account")).is_err());
    let mut confirmation = confirm(&l);
    if let Command::ConfirmPortfolioV1 { confirmation: c } = &mut confirmation {
        let first = l
            .state
            .orders
            .iter()
            .find(|o| o.active())
            .unwrap()
            .proposal
            .instrument
            .clone();
        c.quotes.retain(|q| q.bar.instrument != first);
        c.quotes[1].corporate_actions_verified = false;
        c.quotes[2].rules.tradable = false;
        c.quotes[3].bar.open = c.quotes[3].rules.max_price;
        c.quotes.reverse();
    }
    serde_json::to_value(l.state()).unwrap(); // CLI projection must handle proposal IDs without feature unification
    let path = t.path().join("account");
    drop(l);
    let mut l = Ledger::open(&path).unwrap();
    apply(&mut l, "confirm", confirmation.clone());
    assert!(!l.state.fills.is_empty());
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert!(l.state.orders.iter().all(|o| o.reserved_fee == Cny::ZERO));
    assert!(l.state.fills.iter().all(|f| f.quantity == 100
        && f.historical_execution
            .as_ref()
            .unwrap()
            .contains("EX_POST_OPEN_ASSUMPTION")));
    let cost: i64 = l
        .state
        .fills
        .iter()
        .map(|f| f.price.fen() * f.quantity + f.fees.total().unwrap().fen())
        .sum();
    assert_eq!(
        l.state.snapshot.cash.fen() + cost,
        l.state.config.initial_capital.fen()
    );
    assert_eq!(
        l.state
            .snapshot
            .positions
            .iter()
            .map(|p| p.quantity)
            .sum::<i64>(),
        l.state.fills.iter().map(|f| f.quantity).sum::<i64>()
    );
    assert!(!l.execute("confirm", confirmation.clone()).unwrap());
    assert!(l.execute("new-confirm", confirmation).is_err());
    let state = l.state.clone();
    drop(l);
    assert_eq!(Ledger::open(&path).unwrap().state, state);
}

#[test]
fn no_lookahead_reordered_delivery_and_close_does_not_select_fills() {
    let (_t, mut a) = setup();
    let (_u, mut b) = setup();
    apply(&mut a, "batch", decision(&b, 20261028, 20261029));
    let db = decision(&b, 20261028, 20261029);
    apply(&mut b, "batch", db);
    let ca = confirm(&a);
    let mut cb = ca.clone();
    if let Command::ConfirmPortfolioV1 { confirmation: v } = &mut cb {
        v.quotes.reverse();
        for q in &mut v.quotes {
            q.bar.close = c(1190);
            q.bar.high = c(1200);
            q.bar.low = c(1);
            q.bar.volume_shares = 1;
        }
    }
    apply(&mut a, "confirm", ca);
    apply(&mut b, "confirm", cb);
    assert_eq!(a.state.snapshot.cash, b.state.snapshot.cash);
    assert_eq!(a.state.snapshot.positions, b.state.snapshot.positions);
    assert_eq!(
        a.state
            .fills
            .iter()
            .map(|f| (&f.instrument, f.price, f.quantity))
            .collect::<Vec<_>>(),
        b.state
            .fills
            .iter()
            .map(|f| (&f.instrument, f.price, f.quantity))
            .collect::<Vec<_>>()
    );
}

#[test]
fn future_research_bad_calendar_pause_and_expiry_never_trade() {
    for mode in ["future", "calendar", "warmup", "source"] {
        let (_t, mut l) = setup();
        let mut cmd = decision(&l, 20261028, 20261029);
        if let Command::FreezePortfolioV1 { decision: d } = &mut cmd {
            match mode {
                "future" => d.research.as_mut().unwrap().finished_at = at(20261029, 8),
                "calendar" => d.calendar[1].day = TradingDay(20261030),
                "warmup" => d.research.as_mut().unwrap().ready_sessions = 83,
                "source" => d.source_ready = false,
                _ => unreachable!(),
            }
        }
        apply(&mut l, "blocked", cmd);
        assert!(l.state.orders.is_empty());
        assert!(l.state.portfolio.as_ref().unwrap().pending.is_none());
    }
    let (_t, mut l) = setup();
    let cmd = decision(&l, 20261028, 20261029);
    apply(&mut l, "batch", cmd);
    apply(
        &mut l,
        "pause",
        Command::PausePortfolioV1 {
            now: at(20261028, 9),
            automatic: false,
        },
    );
    let mut cmd = confirm(&l);
    if let Command::ConfirmPortfolioV1 { confirmation: c } = &mut cmd {
        c.now = deadline(c.day).unwrap();
        c.quotes.clear();
    }
    apply(&mut l, "expiry", cmd);
    assert!(l.state.fills.is_empty());
    assert!(l.state.snapshot.pending_orders.is_empty());
    assert!(l
        .execute(
            "backdate",
            Command::PausePortfolioV1 {
                now: at(20261028, 9),
                automatic: true
            }
        )
        .is_err());
}

#[test]
fn crash_portfolio_child() {
    let Ok(path) = std::env::var("PORTFOLIO_CRASH_PATH") else {
        return;
    };
    let mut l = Ledger::open(path).unwrap();
    let cmd = if std::env::var("PORTFOLIO_CRASH_ACTION").unwrap() == "freeze" {
        decision(&l, 20261028, 20261029)
    } else {
        confirm(&l)
    };
    apply(&mut l, "crash-event", cmd);
}

#[test]
fn batch_capacity_is_consumed_once_across_securities() {
    let (_t, mut l) = setup();
    let d = decision(&l, 20261028, 20261029);
    apply(&mut l, "batch", d);
    assert!(l.state.orders.iter().filter(|o| o.active()).count() >= 2);
    let c = confirm(&l);
    apply(&mut l, "confirm", c);
    assert_eq!(l.state.fills.iter().map(|f| f.quantity).sum::<i64>(), 100);
    assert_eq!(l.state.fills.len(), 1);
    assert!(l.state.snapshot.pending_orders.is_empty());
}

#[test]
fn unknown_nav_recovers_current_valuation_without_old_trades_or_unlocking_losses() {
    for recovery_price in [1000, 800] {
        let (t, mut l) = setup();
        let d = decision(&l, 20261028, 20261029);
        apply(&mut l, "d28", d);
        let c29 = confirm(&l);
        apply(&mut l, "c29", c29);
        let d29 = decision(&l, 20261029, 20261030);
        apply(&mut l, "d29", d29);
        let held = l.state.snapshot.positions[0].instrument.clone();
        let mut missing = confirm(&l);
        if let Command::ConfirmPortfolioV1 { confirmation: c } = &mut missing {
            c.quotes.retain(|q| q.bar.instrument != held);
        }
        apply(&mut l, "missing", missing);
        assert!(l.state.valuation_error.is_some());
        if recovery_price == 800 {
            apply(
                &mut l,
                "prior-manual-lock",
                Command::Freeze {
                    scope: RiskScope::Account,
                    reason: FreezeReason::Manual,
                },
            );
        }
        let original = l.state.clone();
        let mut v = match confirm(&l) {
            Command::ConfirmPortfolioV1 { confirmation } => confirmation,
            _ => unreachable!(),
        };
        v.day = TradingDay(20261102);
        v.now = at(20261102, 8);
        v.received_at = v.now;
        for q in &mut v.quotes {
            q.bar.day = v.day;
            q.bar.opens_at = session(v.day, 1, 30).unwrap();
            q.bar.closes_at = session(v.day, 7, 0).unwrap();
            q.bar.available_at = v.now;
            q.bar.close = c(recovery_price);
            q.rules.trading_day = v.day;
            q.rules.available_at = v.now;
        }
        let mut bad = v.clone();
        bad.quotes.clear();
        assert!(l
            .execute(
                "bad-recovery",
                Command::RecoverPortfolioValuationV1 { valuation: bad }
            )
            .is_err());
        assert_eq!(l.state, original);
        let path = t.path().join("account");
        drop(l);
        let mut l = Ledger::open(&path).unwrap();
        let cmd = Command::RecoverPortfolioValuationV1 { valuation: v };
        apply(&mut l, "recover", cmd.clone());
        assert!(!l.execute("recover", cmd).unwrap());
        assert!(l.state.valuation_error.is_none());
        assert_eq!(l.state.snapshot.cash, original.snapshot.cash);
        assert_eq!(l.state.snapshot.positions, original.snapshot.positions);
        assert_eq!(l.state.orders, original.orders);
        assert_eq!(l.state.fills, original.fills);
        assert_eq!(
            l.state.portfolio.as_ref().unwrap().recoveries[0].label,
            "NO_TRADE_REBASE"
        );
        assert!(l
            .history()
            .unwrap()
            .iter()
            .any(|e| e.event_id == "missing" && e.state.equity.is_none()));
        if recovery_price == 800 {
            assert!(l
                .state
                .risk
                .freezes(RiskScope::Account)
                .contains(&FreezeReason::Manual));
            assert!(l
                .state
                .risk
                .freezes(RiskScope::Account)
                .contains(&FreezeReason::DailyLoss));
            assert!(l
                .state
                .risk
                .freezes(RiskScope::Account)
                .contains(&FreezeReason::Drawdown));
        }
        let d = decision(&l, 20261102, 20261103);
        apply(&mut l, "fresh-day", d);
        if recovery_price == 1000 {
            assert!(l.state.orders.iter().any(|o| o.active()));
        } else {
            assert!(l
                .state
                .orders
                .iter()
                .filter(|o| o.accepted_on == TradingDay(20261102))
                .all(|o| o.status == OrderStatus::Rejected));
        }
        let state = l.state.clone();
        drop(l);
        assert_eq!(Ledger::open(path).unwrap().state, state);
    }
}

#[test]
fn multiday_tplusone_sells_cash_fees_and_unknown_whole_account_marks() {
    let (_t, mut l) = setup();
    let d = decision(&l, 20261028, 20261029);
    apply(&mut l, "d28", d);
    let c29 = confirm(&l);
    apply(&mut l, "c29", c29);
    assert!(l
        .state
        .orders
        .iter()
        .any(|o| o.status == OrderStatus::Expired && o.remaining == 100)); // partial IOC
    let mut d29 = decision(&l, 20261029, 20261030);
    if let Command::FreezePortfolioV1 { decision: d } = &mut d29 {
        d.research.as_mut().unwrap().selected.clear();
    }
    apply(&mut l, "d29", d29);
    let sells = l
        .state
        .orders
        .iter()
        .filter(|o| o.accepted_on == TradingDay(20261029))
        .collect::<Vec<_>>();
    assert!(!sells.is_empty());
    assert!(sells.iter().all(|o| o.status == OrderStatus::Rejected)); // acquired today is not sellable
    let mut d30 = decision(&l, 20261030, 20261102);
    if let Command::FreezePortfolioV1 { decision: d } = &mut d30 {
        d.research.as_mut().unwrap().selected.clear();
        d.calendar = vec![
            CalendarDay {
                day: TradingDay(20261030),
                sse_open: true,
                szse_open: true,
            },
            CalendarDay {
                day: TradingDay(20261031),
                sse_open: false,
                szse_open: false,
            },
            CalendarDay {
                day: TradingDay(20261101),
                sse_open: false,
                szse_open: false,
            },
            CalendarDay {
                day: TradingDay(20261102),
                sse_open: true,
                szse_open: true,
            },
        ];
    }
    apply(&mut l, "d30", d30);
    assert!(l
        .state
        .orders
        .iter()
        .any(|o| o.active() && o.proposal.side == Side::Sell));
    let c02 = confirm(&l);
    apply(&mut l, "c02", c02);
    assert!(l.state.snapshot.positions.is_empty());
    assert!(l.state.snapshot.pending_orders.is_empty());
    let mut cash = l.state.config.initial_capital.fen();
    for f in &l.state.fills {
        let gross = f.price.fen() * f.quantity;
        let fees = f.fees.total().unwrap().fen();
        cash += if f.side == Side::Buy {
            -gross - fees
        } else {
            gross - fees
        };
    }
    assert_eq!(l.state.snapshot.cash.fen(), cash);
    let d = decision(&l, 20261102, 20261103);
    apply(&mut l, "d02", d);
    let c03 = confirm(&l);
    apply(&mut l, "c03", c03);
    let d = decision(&l, 20261103, 20261104);
    apply(&mut l, "d03", d);
    let mut c04 = confirm(&l);
    if let Command::ConfirmPortfolioV1 { confirmation: c } = &mut c04 {
        let holding = l.state.snapshot.positions[0].instrument.clone();
        c.quotes.retain(|q| q.bar.instrument != holding);
    }
    let before = l.state.fills.len();
    apply(&mut l, "c04", c04);
    assert_eq!(l.state.fills.len(), before);
    assert!(l.state.valuation_error.is_some()); // unknown account NAV denies every new fill
}

#[test]
fn atomic_batch_crash_before_and_after_commit_recovers_exactly_once() {
    for action in ["freeze", "confirm"] {
        for point in ["after_reservation", "before_commit", "after_commit"] {
            let (t, mut l) = setup();
            if action == "confirm" {
                let cmd = decision(&l, 20261028, 20261029);
                apply(&mut l, "batch", cmd);
            }
            let before = l.state.clone();
            let cmd = if action == "freeze" {
                decision(&l, 20261028, 20261029)
            } else {
                confirm(&l)
            };
            drop(l);
            let path = t.path().join("account");
            let output = Process::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "store::tests::portfolio::crash_portfolio_child",
                    "--nocapture",
                ])
                .env("PORTFOLIO_CRASH_PATH", &path)
                .env("PORTFOLIO_CRASH_ACTION", action)
                .env("STRATIDE_TEST_CRASH_AT", point)
                .output()
                .unwrap();
            assert_eq!(
                output.status.code(),
                Some(86),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            let mut l = Ledger::open(&path).unwrap();
            if point != "after_commit" {
                assert_eq!(l.state, before);
            }
            assert_eq!(
                l.execute("crash-event", cmd.clone()).unwrap(),
                point != "after_commit"
            );
            assert!(!l.execute("crash-event", cmd).unwrap());
            l.state.validate().unwrap();
        }
    }
}
