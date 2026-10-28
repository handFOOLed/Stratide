use super::*;

mod observation;

fn money(fen: i64) -> Cny {
    Cny::from_fen(fen).unwrap()
}

// All prices/rules/lots below are synthetic_test, never real market/fill evidence.
fn fixture() -> (
    PaperAccountConfig,
    AccountSnapshot,
    OrderProposal,
    ReviewContext,
) {
    let deployment = DeploymentIdentity {
        group_id: "synthetic-group".into(),
        strategy_id: "synthetic-strategy".into(),
        frozen_version: "synthetic-v1".into(),
        deployment_id: "synthetic-deployment".into(),
    };
    let limits = RiskLimits {
        max_order_commitment: money(1_000_000),
        max_exposure: money(1_000_000),
        daily_loss: money(100_000),
        drawdown: money(200_000),
    };
    let config = PaperAccountConfig {
        account_id: "synthetic-account".into(),
        authorized_principal: money(1_000_000),
        initial_capital: money(1_000_000),
        deployment: deployment.clone(),
        account_limits: limits,
        strategy_limits: limits,
        max_snapshot_age_ms: 60_000,
        max_mark_age_ms: 60_000,
    };
    // 2026-10-28 10:00:00 Asia/Shanghai, represented as UTC epoch milliseconds.
    let now = Timestamp(1_793_152_800_000);
    let day = TradingDay(20261028);
    let snapshot = config.initialize(now, day).unwrap();
    let instrument = Instrument {
        market: Market::Shanghai,
        code: "600000".into(),
    };
    let proposal = OrderProposal {
        proposal_id: ProposalId(1),
        account_id: config.account_id.clone(),
        deployment,
        instrument: instrument.clone(),
        side: Side::Buy,
        quantity: 100,
        limit_price: money(1_000),
        decision_at: now,
        data_available_at: now,
        earliest_execution_at: Timestamp(now.0 + 1),
        expires_at: Timestamp(now.0 + 60_000),
    };
    let mut context = ReviewContext {
        now,
        trading_day: day,
        rules: Some(TradingRules {
            instrument,
            trading_day: day,
            available_at: now,
            source: "synthetic_test/rules-v1".into(),
            tradable: true,
            settlement: SettlementRule::TPlusOne,
            buy_lot: 100,
            sell_lot: 100,
            allow_odd_lot_liquidation: true,
            tick_size: money(1),
            min_price: money(900),
            max_price: money(1_100),
        }),
        cost: None,
    };
    context.cost = Some(CostEstimate {
        proposal: proposal.clone(),
        rules: context.rules.clone().unwrap(),
        valid_until: proposal.expires_at,
        proposal_id: proposal.proposal_id,
        maximum_fee: money(500),
        source: "synthetic_test/cost-bound-v1".into(),
    });
    (config, snapshot, proposal, context)
}

fn add_position(
    s: &mut AccountSnapshot,
    p: &OrderProposal,
    quantity: i64,
    acquired_on: TradingDay,
) {
    s.positions.push(PositionLot {
        instrument: p.instrument.clone(),
        quantity,
        acquired_on,
    });
    if !s.marks.iter().any(|m| m.instrument == p.instrument) {
        s.marks.push(PositionMark {
            instrument: p.instrument.clone(),
            price: p.limit_price,
            as_of: s.as_of,
            available_at: s.as_of,
            source: "synthetic_test/mark-v1".into(),
        });
    }
    s.cash = money(s.cash.fen() - p.limit_price.fen() * quantity);
}

fn rejection(
    config: PaperAccountConfig,
    s: &AccountSnapshot,
    p: &OrderProposal,
    c: &ReviewContext,
) -> RejectionReason {
    match RiskKernel::new(config).unwrap().review_fixture(s, p, c) {
        RiskDecision::Rejected {
            proposal_id,
            reason,
        } => {
            assert_eq!(proposal_id, p.proposal_id);
            reason
        }
        result => panic!("expected rejection, got {result:?}"),
    }
}

#[test]
fn explicit_initial_capital_and_authorization_are_required() {
    let (mut config, snapshot, _, _) = fixture();
    assert_eq!(snapshot.cash, config.initial_capital);
    assert!(snapshot.positions.is_empty());
    config.initial_capital = Cny::ZERO;
    assert!(config
        .initialize(Timestamp(0), TradingDay(20261028))
        .is_err());
    config.initial_capital = money(1_000_001);
    assert!(RiskKernel::new(config).is_err());
    assert!(Cny::from_fen(-1).is_err());
}

#[test]
fn normal_buy_is_bound_repeatable_and_does_not_fill_or_reserve() {
    let (config, snapshot, proposal, context) = fixture();
    let original = snapshot.clone();
    let mut kernel = RiskKernel::new(config).unwrap();
    let first = kernel.review_fixture(&snapshot, &proposal, &context);
    assert_eq!(first, kernel.review_fixture(&snapshot, &proposal, &context));
    let RiskDecision::Accepted(approval) = first else {
        panic!("buy rejected")
    };
    assert_eq!(approval.proposal(), &proposal);
    assert_eq!(approval.snapshot_revision(), 0);
    assert_eq!(approval.maximum_cash_debit(), money(100_500));
    assert_eq!(approval.account_equity(), snapshot.cash);
    assert_eq!(snapshot, original);
}

#[test]
fn buys_include_fees_and_cash_boundary_is_exact() {
    let (config, mut s, p, c) = fixture();
    s.cash = money(100_499);
    s.equity_basis.day_start_equity = s.cash;
    s.equity_basis.cash_flow_adjusted_peak = s.cash;
    let mut config = config;
    config.initial_capital = s.cash;
    let mut kernel = RiskKernel::new(config.clone()).unwrap();
    assert_eq!(
        kernel.review_fixture(&s, &p, &c),
        RiskDecision::Rejected {
            proposal_id: p.proposal_id,
            reason: RejectionReason::InsufficientCash {
                required: money(100_500),
                available: money(100_499)
            },
        }
    );
    s.cash = money(100_500);
    assert!(matches!(
        kernel.review_fixture(&s, &p, &c),
        RiskDecision::Accepted(_)
    ));
}

#[test]
fn no_position_and_overselling_are_rejected() {
    let (config, mut s, mut p, c) = fixture();
    p.side = Side::Sell;
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::InsufficientPosition {
            requested: 100,
            available: 0
        }
    );
    add_position(&mut s, &p, 100, TradingDay(20261027));
    p.quantity = 200;
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::InsufficientPosition {
            requested: 200,
            available: 100
        }
    );
}

#[test]
fn t_plus_one_only_releases_earlier_day_lots() {
    let (config, mut s, mut p, c) = fixture();
    p.side = Side::Sell;
    let day = s.trading_day;
    add_position(&mut s, &p, 100, day);
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::TPlusOne {
            requested: 100,
            sellable: 0
        }
    );
    add_position(&mut s, &p, 100, TradingDay(20261027));
    assert!(matches!(
        RiskKernel::new(config.clone())
            .unwrap()
            .review_fixture(&s, &p, &c),
        RiskDecision::Accepted(_)
    ));
    p.quantity = 200;
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::TPlusOne {
            requested: 200,
            sellable: 100
        }
    );
}

#[test]
fn settlement_is_instrument_specific_and_unknown_rules_fail_closed() {
    let (config, mut s, mut p, mut c) = fixture();
    p.side = Side::Sell;
    let day = s.trading_day;
    add_position(&mut s, &p, 100, day);
    c.rules.as_mut().unwrap().settlement = SettlementRule::SameDay;
    assert!(matches!(
        RiskKernel::new(config.clone())
            .unwrap()
            .review_fixture(&s, &p, &c),
        RiskDecision::Accepted(_)
    ));
    c.rules.as_mut().unwrap().settlement = SettlementRule::Unknown;
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::UnsupportedSettlement
    );
    c.rules = None;
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::MissingMarketEvidence
    );
}

#[test]
fn invalid_quantity_id_symbol_price_and_overflows_fail_closed() {
    let (config, s, p, c) = fixture();
    for quantity in [0, -1, i64::MIN] {
        let mut bad = p.clone();
        bad.quantity = quantity;
        assert!(matches!(
            rejection(config.clone(), &s, &bad, &c),
            RejectionReason::InvalidProposal(_)
        ));
    }
    let mut bad = p.clone();
    bad.quantity = i64::MAX;
    assert_eq!(
        rejection(config.clone(), &s, &bad, &c),
        RejectionReason::ArithmeticOverflow
    );
    bad = p.clone();
    bad.proposal_id = ProposalId(0);
    assert!(matches!(
        rejection(config.clone(), &s, &bad, &c),
        RejectionReason::InvalidProposal(_)
    ));
    bad = p.clone();
    bad.instrument.code = "60000X".into();
    assert!(matches!(
        rejection(config.clone(), &s, &bad, &c),
        RejectionReason::InvalidProposal(_)
    ));
    bad = p.clone();
    bad.limit_price = Cny::ZERO;
    assert!(matches!(
        rejection(config.clone(), &s, &bad, &c),
        RejectionReason::InvalidProposal(_)
    ));
    let mut cost_overflow = c;
    cost_overflow.cost.as_mut().unwrap().maximum_fee = money(i64::MAX);
    assert_eq!(
        rejection(config, &s, &p, &cost_overflow),
        RejectionReason::ArithmeticOverflow
    );
}

#[test]
fn invalid_lots_ticks_price_bands_suspensions_and_evidence_are_rejected() {
    let (config, s, mut p, c) = fixture();
    p.quantity = 101;
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::InvalidLot
    );
    p.quantity = 100;
    p.limit_price = money(1_101);
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::InvalidPrice
    );
    p.limit_price = money(1_001);
    let mut changed = c.clone();
    changed.rules.as_mut().unwrap().tick_size = money(5);
    assert_eq!(
        rejection(config.clone(), &s, &p, &changed),
        RejectionReason::InvalidPrice
    );
    changed = c.clone();
    changed.rules.as_mut().unwrap().tradable = false;
    assert_eq!(
        rejection(config.clone(), &s, &p, &changed),
        RejectionReason::MarketNotTradable
    );
    for mutate in 0..3 {
        changed = c.clone();
        let rule = changed.rules.as_mut().unwrap();
        match mutate {
            0 => rule.instrument.market = Market::Shenzhen,
            1 => rule.source.clear(),
            _ => rule.trading_day = TradingDay(20261027),
        }
        assert_eq!(
            rejection(config.clone(), &s, &p, &changed),
            RejectionReason::InvalidMarketEvidence
        );
    }
}

#[test]
fn fee_evidence_must_be_present_and_bound_to_proposal() {
    let (config, s, p, mut c) = fixture();
    c.cost.as_mut().unwrap().proposal_id = ProposalId(2);
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::MissingCostEvidence
    );
    c.cost = None;
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::MissingCostEvidence
    );
}

#[test]
fn pending_buys_reserve_shared_cash_and_exposure() {
    let (config, mut s, p, c) = fixture();
    s.pending_orders.push(PendingOrder {
        proposal_id: ProposalId(2),
        instrument: p.instrument.clone(),
        side: Side::Buy,
        quantity: 900,
        reserved_cash: money(900_000),
    });
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::InsufficientCash {
            required: money(100_500),
            available: money(100_000)
        }
    );
    s.pending_orders[0].reserved_cash = money(800_000);
    let mut config = config;
    config.strategy_limits.max_exposure = money(900_000);
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::LimitExceeded {
            scope: RiskScope::Strategy,
            kind: "总敞口（含待成交预留）"
        }
    );
}

#[test]
fn pending_sells_and_duplicate_ids_cannot_be_reused() {
    let (config, mut s, mut p, c) = fixture();
    p.side = Side::Sell;
    add_position(&mut s, &p, 100, TradingDay(20261027));
    s.pending_orders.push(PendingOrder {
        proposal_id: ProposalId(2),
        instrument: p.instrument.clone(),
        side: Side::Sell,
        quantity: 100,
        reserved_cash: Cny::ZERO,
    });
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::InsufficientPosition {
            requested: 100,
            available: 0
        }
    );
    s.pending_orders[0].proposal_id = p.proposal_id;
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::AlreadyPending
    );
    s.pending_orders.push(s.pending_orders[0].clone());
    assert!(matches!(
        rejection(config, &s, &p, &c),
        RejectionReason::InvalidSnapshot(_)
    ));
}

#[test]
fn both_risk_layers_enforce_order_and_exposure_caps() {
    let (config, s, p, c) = fixture();
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        for order_cap in [true, false] {
            let mut config = config.clone();
            if scope == RiskScope::Account && !order_cap {
                config.strategy_limits.max_exposure = money(100_499);
            }
            let limits = match scope {
                RiskScope::Account => &mut config.account_limits,
                RiskScope::Strategy => &mut config.strategy_limits,
            };
            if order_cap {
                limits.max_order_commitment = money(100_499)
            } else {
                limits.max_exposure = money(100_499)
            }
            assert!(
                matches!(rejection(config, &s, &p, &c), RejectionReason::LimitExceeded { scope: rejected, .. } if rejected == scope)
            );
        }
    }
}

#[test]
fn identity_changes_cannot_reuse_account_or_risk_state() {
    let (config, s, p, c) = fixture();
    let state = RiskKernel::new(config.clone()).unwrap().state().clone();
    for field in 0..5 {
        let mut bad = p.clone();
        match field {
            0 => bad.account_id.push('x'),
            1 => bad.deployment.group_id.push('x'),
            2 => bad.deployment.strategy_id.push('x'),
            3 => bad.deployment.frozen_version.push('x'),
            _ => bad.deployment.deployment_id.push('x'),
        }
        assert_eq!(
            rejection(config.clone(), &s, &bad, &c),
            RejectionReason::IdentityMismatch
        );
    }
    let mut renamed = config;
    renamed.deployment.strategy_id.push('x');
    assert!(RiskKernel::restore(renamed, state).is_err());
}

#[test]
fn financial_freezes_deny_buys_but_allow_verified_settled_reduction() {
    let (config, mut s, mut p, c) = fixture();
    add_position(&mut s, &p, 100, TradingDay(20261027));
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        let mut kernel = RiskKernel::new(config.clone()).unwrap();
        kernel.freeze(scope, FreezeReason::DailyLoss);
        assert_eq!(
            kernel.review_fixture(&s, &p, &c),
            RiskDecision::Rejected {
                proposal_id: p.proposal_id,
                reason: RejectionReason::Frozen {
                    scope,
                    reason: FreezeReason::DailyLoss
                },
            }
        );
        p.side = Side::Sell;
        assert!(matches!(
            kernel.review_fixture(&s, &p, &c),
            RiskDecision::Accepted(_)
        ));
        p.side = Side::Buy;
    }
}

#[test]
fn uncertainty_and_manual_freezes_deny_both_sides() {
    let (config, mut s, mut p, c) = fixture();
    add_position(&mut s, &p, 100, TradingDay(20261027));
    for reason in [FreezeReason::OrderUncertainty, FreezeReason::Manual] {
        let mut kernel = RiskKernel::new(config.clone()).unwrap();
        kernel.freeze(RiskScope::Account, reason);
        for side in [Side::Buy, Side::Sell] {
            p.side = side;
            assert!(matches!(
                kernel.review_fixture(&s, &p, &c),
                RiskDecision::Rejected {
                    reason: RejectionReason::Frozen { .. },
                    ..
                }
            ));
        }
    }
}

#[test]
fn sell_fees_cannot_create_an_unreserved_cash_debit() {
    let (config, mut s, mut p, mut c) = fixture();
    add_position(&mut s, &p, 100, TradingDay(20261027));
    p.side = Side::Sell;
    c.cost.as_mut().unwrap().maximum_fee = money(100_001);
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::FeesExceedProceeds {
            fees: money(100_001),
            proceeds: money(100_000),
        }
    );
}

#[test]
fn unrealized_nav_loss_latches_at_threshold_and_memory_restore_retains_it() {
    let (config, mut s, mut p, mut c) = fixture();
    add_position(&mut s, &p, 500, TradingDay(20261027));
    // No new fill; a trusted synthetic mark loses 1000 CNY in unrealized value.
    s.marks[0].price = money(800);
    let original = s.clone();
    let mut kernel = RiskKernel::new(config.clone()).unwrap();
    let first = kernel.review_fixture(&s, &p, &c);
    assert!(matches!(
        first,
        RiskDecision::Rejected {
            reason: RejectionReason::Frozen {
                scope: RiskScope::Account,
                reason: FreezeReason::DailyLoss
            },
            ..
        }
    ));
    assert_eq!(first, kernel.review_fixture(&s, &p, &c));
    assert_eq!(s, original);
    let mut restored = RiskKernel::restore(config, kernel.state().clone()).unwrap();
    s.marks[0].price = money(1_000);
    assert!(matches!(
        restored.review_fixture(&s, &p, &c),
        RiskDecision::Rejected {
            reason: RejectionReason::Frozen { .. },
            ..
        }
    ));
    s.trading_day = TradingDay(20261029);
    s.as_of.0 += 86_400_000;
    s.marks[0].as_of = s.as_of;
    s.marks[0].available_at = s.as_of;
    c.trading_day = s.trading_day;
    c.now = s.as_of;
    c.rules.as_mut().unwrap().trading_day = s.trading_day;
    c.rules.as_mut().unwrap().available_at = s.as_of;
    p.decision_at = s.as_of;
    p.data_available_at = s.as_of;
    p.earliest_execution_at = Timestamp(s.as_of.0 + 1);
    p.expires_at = Timestamp(s.as_of.0 + 60_000);
    assert!(matches!(
        restored.review_fixture(&s, &p, &c),
        RiskDecision::Rejected {
            reason: RejectionReason::Frozen {
                scope: RiskScope::Account,
                reason: FreezeReason::DailyLoss
            },
            ..
        }
    ));
}

#[test]
fn strategy_loss_and_account_drawdown_are_separate_checks() {
    let (mut config, mut s, p, c) = fixture();
    config.strategy_limits.daily_loss = money(50_000);
    s.cash = money(950_000);
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::Frozen {
            scope: RiskScope::Strategy,
            reason: FreezeReason::DailyLoss
        }
    );
    config.strategy_limits.daily_loss = money(100_000);
    s.cash = money(1_000_000);
    s.equity_basis.cash_flow_adjusted_peak = money(1_200_000);
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::Frozen {
            scope: RiskScope::Account,
            reason: FreezeReason::Drawdown
        }
    );
}

#[test]
fn deposits_and_withdrawals_are_not_trading_profit_or_loss() {
    let (config, s, p, c) = fixture();
    for flow in [250_000, -250_000] {
        let mut s = s.clone();
        s.cash = money(s.cash.fen() + flow);
        s.equity_basis.net_external_flow_today_fen = flow;
        s.equity_basis.net_external_flow_total_fen = flow;
        let mut kernel = RiskKernel::new(config.clone()).unwrap();
        assert!(matches!(
            kernel.review_fixture(&s, &p, &c),
            RiskDecision::Accepted(_)
        ));
        assert!(kernel.state().freezes(RiskScope::Account).is_empty());
    }
}

#[test]
fn deposits_cannot_hide_losses_and_observed_peak_cannot_be_lowered() {
    let (config, mut s, p, c) = fixture();
    // Deposit 1000 CNY and lose 1000 CNY: unadjusted cash is unchanged, loss is not.
    s.equity_basis.net_external_flow_today_fen = 100_000;
    s.equity_basis.net_external_flow_total_fen = 100_000;
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::Frozen {
            scope: RiskScope::Account,
            reason: FreezeReason::DailyLoss,
        }
    );
    s.equity_basis.net_external_flow_today_fen = 0;
    s.equity_basis.net_external_flow_total_fen = 0;
    s.cash = money(1_200_000);
    let mut kernel = RiskKernel::new(config).unwrap();
    assert!(matches!(
        kernel.review_fixture(&s, &p, &c),
        RiskDecision::Accepted(_)
    ));
    // Even though supplied historical peak is still initial capital, observed peak stays.
    s.cash = money(1_000_000);
    assert!(matches!(
        kernel.review_fixture(&s, &p, &c),
        RiskDecision::Rejected {
            reason: RejectionReason::Frozen {
                scope: RiskScope::Account,
                reason: FreezeReason::Drawdown
            },
            ..
        }
    ));
}

#[test]
fn missing_stale_duplicate_and_future_marks_never_imply_zero_loss() {
    let (config, mut s, p, c) = fixture();
    add_position(&mut s, &p, 100, TradingDay(20261027));
    for defect in 0..4 {
        let mut bad = s.clone();
        match defect {
            0 => bad.marks.clear(),
            1 => bad.marks[0].as_of.0 -= 60_001,
            2 => bad.marks.push(bad.marks[0].clone()),
            _ => bad.marks[0].available_at.0 += 1,
        }
        assert_eq!(
            rejection(config.clone(), &bad, &p, &c),
            RejectionReason::ValuationUnavailable
        );
    }
}

#[test]
fn future_data_expiry_and_invalid_snapshot_are_rejected() {
    let (config, s, p, c) = fixture();
    let mut bad = p.clone();
    bad.data_available_at.0 += 1;
    assert_eq!(
        rejection(config.clone(), &s, &bad, &c),
        RejectionReason::DataNotAvailable
    );
    let mut expired = c.clone();
    expired.now = p.expires_at;
    assert_eq!(
        rejection(config.clone(), &s, &p, &expired),
        RejectionReason::ProposalExpired
    );
    bad = p.clone();
    bad.earliest_execution_at = bad.decision_at;
    assert!(matches!(
        rejection(config.clone(), &s, &bad, &c),
        RejectionReason::InvalidProposal(_)
    ));
    let mut old = s;
    old.as_of.0 -= 60_001;
    assert!(matches!(
        rejection(config.clone(), &old, &p, &c),
        RejectionReason::InvalidSnapshot(_)
    ));
    old.as_of = c.now;
    old.trading_day = TradingDay(20260230);
    assert!(matches!(
        rejection(config, &old, &p, &c),
        RejectionReason::InvalidSnapshot(_)
    ));
}

#[test]
fn overflowing_nav_and_invalid_flow_adjustment_fail_closed() {
    let (config, mut s, p, c) = fixture();
    add_position(&mut s, &p, 100, TradingDay(20261027));
    s.cash = money(i64::MAX);
    assert_eq!(
        rejection(config.clone(), &s, &p, &c),
        RejectionReason::ArithmeticOverflow
    );
    s.cash = money(900_000);
    s.equity_basis.net_external_flow_total_fen = i64::MIN;
    assert_eq!(
        rejection(config, &s, &p, &c),
        RejectionReason::ValuationUnavailable
    );
}

#[test]
fn invalid_positions_and_overreservations_fail_closed() {
    let (config, s, p, c) = fixture();
    for quantity in [0, -1] {
        let mut bad = s.clone();
        bad.positions.push(PositionLot {
            instrument: p.instrument.clone(),
            quantity,
            acquired_on: TradingDay(20261027),
        });
        assert!(matches!(
            rejection(config.clone(), &bad, &p, &c),
            RejectionReason::InvalidSnapshot(_)
        ));
    }
    let mut bad = s;
    bad.pending_orders.push(PendingOrder {
        proposal_id: ProposalId(2),
        instrument: p.instrument.clone(),
        side: Side::Buy,
        quantity: 100,
        reserved_cash: money(1_000_001),
    });
    assert!(matches!(
        rejection(config, &bad, &p, &c),
        RejectionReason::InvalidSnapshot(_)
    ));
}

// Existing financial scenarios use a newly issued trusted estimate for their
// intentionally edited proposal/rules. Binding attacks below call review directly.
trait FixtureReview {
    fn review_fixture(
        &mut self,
        s: &AccountSnapshot,
        p: &OrderProposal,
        c: &ReviewContext,
    ) -> RiskDecision;
}
impl FixtureReview for RiskKernel {
    fn review_fixture(
        &mut self,
        s: &AccountSnapshot,
        p: &OrderProposal,
        c: &ReviewContext,
    ) -> RiskDecision {
        let mut c = c.clone();
        if let (Some(cost), Some(rules)) = (&mut c.cost, &c.rules) {
            cost.proposal = p.clone();
            cost.rules = rules.clone();
            cost.valid_until = p.expires_at;
        }
        self.review(s, p, &c)
    }
}

#[test]
fn cost_is_bound_to_every_proposal_and_rule_field_and_expiry() {
    let (config, snapshot, p, c) = fixture();
    let mut variants = vec![];
    let mut q = p.clone();
    q.quantity += 100;
    variants.push(q);
    let mut q = p.clone();
    q.side = Side::Sell;
    variants.push(q);
    let mut q = p.clone();
    q.limit_price = money(1001);
    variants.push(q);
    let mut q = p.clone();
    q.instrument.code = "600001".into();
    variants.push(q);
    for q in variants {
        let mut context = c.clone();
        context.rules.as_mut().unwrap().instrument = q.instrument.clone();
        assert!(matches!(
            RiskKernel::new(config.clone())
                .unwrap()
                .review(&snapshot, &q, &context),
            RiskDecision::Rejected {
                reason: RejectionReason::MissingCostEvidence,
                ..
            }
        ));
    }
    let mut context = c.clone();
    context.rules.as_mut().unwrap().buy_lot = 200;
    assert!(matches!(
        RiskKernel::new(config.clone())
            .unwrap()
            .review(&snapshot, &p, &context),
        RiskDecision::Rejected {
            reason: RejectionReason::MissingCostEvidence,
            ..
        }
    ));
    let mut context = c;
    context.cost.as_mut().unwrap().valid_until = context.now;
    assert!(matches!(
        RiskKernel::new(config)
            .unwrap()
            .review(&snapshot, &p, &context),
        RiskDecision::Rejected {
            reason: RejectionReason::MissingCostEvidence,
            ..
        }
    ));
}
