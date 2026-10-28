use super::*;

#[test]
fn regression_invalid_proposals_cannot_skip_trusted_loss_observation() {
    let (config, mut snapshot, proposal, context) = fixture();
    snapshot.cash = money(900_000);
    let original = snapshot.clone();
    for defect in 0..6 {
        let mut invalid = proposal.clone();
        match defect {
            0 => invalid.quantity = 0,
            1 => invalid.account_id = "different-account".into(),
            2 => invalid.deployment.frozen_version = "different-version".into(),
            3 => invalid.instrument.code = "bad".into(),
            4 => invalid.data_available_at.0 += 1,
            _ => invalid.quantity = i64::MAX,
        }
        let mut kernel = RiskKernel::new(config.clone()).unwrap();
        assert!(matches!(
            kernel.review_fixture(&snapshot, &invalid, &context),
            RiskDecision::Rejected { .. }
        ));
        for scope in [RiskScope::Account, RiskScope::Strategy] {
            assert!(
                kernel
                    .state()
                    .freezes(scope)
                    .contains(&FreezeReason::DailyLoss),
                "proposal defect {defect} skipped {scope} observation"
            );
        }
        assert_eq!(snapshot, original);
    }
}

#[test]
fn regression_observation_without_proposal_records_loss_and_peak() {
    let (config, mut snapshot, _, context) = fixture();
    let mut kernel = RiskKernel::new(config.clone()).unwrap();
    snapshot.cash = money(1_300_000);
    assert_eq!(
        kernel.observe_account(&snapshot, context.now, context.trading_day),
        Ok(money(1_300_000))
    );
    snapshot.cash = money(1_100_000); // exactly the 200,000-fen drawdown threshold
    assert_eq!(
        kernel.observe_account(&snapshot, context.now, context.trading_day),
        Ok(money(1_100_000))
    );
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        assert!(kernel
            .state()
            .freezes(scope)
            .contains(&FreezeReason::Drawdown));
    }
    let mut loss_kernel = RiskKernel::new(config).unwrap();
    snapshot.cash = money(900_000);
    assert_eq!(
        loss_kernel.observe_account(&snapshot, context.now, context.trading_day),
        Ok(money(900_000))
    );
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        assert!(loss_kernel
            .state()
            .freezes(scope)
            .contains(&FreezeReason::DailyLoss));
    }
}

// Both public entry points must reject the same invalid account before mutation.
fn assert_observation_rejected_unchanged(
    config: &PaperAccountConfig,
    snapshot: &AccountSnapshot,
    proposal: &OrderProposal,
    context: &ReviewContext,
    expected: RejectionReason,
) {
    let mut kernel = RiskKernel::new(config.clone()).unwrap();
    kernel.freeze(RiskScope::Account, FreezeReason::Manual);
    kernel.freeze(RiskScope::Strategy, FreezeReason::DailyLoss);
    let before = kernel.state().clone();
    assert_eq!(
        kernel.observe_account(snapshot, context.now, context.trading_day),
        Err(expected.clone())
    );
    assert_eq!(kernel.state(), &before);
    assert_eq!(
        kernel.review_fixture(snapshot, proposal, context),
        RiskDecision::Rejected {
            proposal_id: proposal.proposal_id,
            reason: expected,
        }
    );
    assert_eq!(kernel.state(), &before);
}

#[test]
fn regression_wrong_identity_or_expired_snapshot_cannot_pollute_state() {
    let (config, mut snapshot, proposal, context) = fixture();
    // This candidate NAV would raise the peak if validation were skipped.
    snapshot.cash = money(1_300_000);
    for defect in 0..5 {
        let mut bad = snapshot.clone();
        let expected = match defect {
            0 => {
                bad.account_id = "different-account".into();
                RejectionReason::IdentityMismatch
            }
            1 => {
                bad.deployment.deployment_id = "different-deployment".into();
                RejectionReason::IdentityMismatch
            }
            2 => {
                bad.as_of.0 -= 60_001;
                RejectionReason::InvalidSnapshot("快照时间/交易日无效或已过期")
            }
            3 => {
                bad.as_of.0 += 1;
                RejectionReason::InvalidSnapshot("快照时间/交易日无效或已过期")
            }
            _ => {
                bad.trading_day = TradingDay(20261027);
                RejectionReason::InvalidSnapshot("快照时间/交易日无效或已过期")
            }
        };
        assert_observation_rejected_unchanged(&config, &bad, &proposal, &context, expected);
    }
    // An expired low NAV must not create an erroneous financial lock either.
    snapshot.cash = money(900_000);
    snapshot.as_of.0 -= 60_001;
    let mut kernel = RiskKernel::new(config).unwrap();
    let before = kernel.state().clone();
    assert!(kernel
        .observe_account(&snapshot, context.now, context.trading_day)
        .is_err());
    assert_eq!(kernel.state(), &before);
}

#[test]
fn regression_bad_or_incomplete_marks_cannot_partially_update_state() {
    let (config, mut snapshot, proposal, context) = fixture();
    add_position(&mut snapshot, &proposal, 100, TradingDay(20261027));
    snapshot.marks[0].price = money(4_000); // valid mark alone would create NAV 1,300,000
    for defect in 0..6 {
        let mut bad = snapshot.clone();
        match defect {
            0 => bad.marks[0].as_of.0 -= 60_001,
            1 => bad.marks[0].available_at.0 += 1,
            2 => bad.marks[0].source.clear(),
            3 => bad.marks.push(bad.marks[0].clone()),
            4 => bad.positions.push(PositionLot {
                instrument: Instrument {
                    market: Market::Shenzhen,
                    code: "000001".into(),
                },
                quantity: 100,
                acquired_on: TradingDay(20261027),
            }), // later holding lacks its mark; earlier mark cannot commit a partial NAV
            _ => bad.marks.clear(),
        }
        assert_observation_rejected_unchanged(
            &config,
            &bad,
            &proposal,
            &context,
            RejectionReason::ValuationUnavailable,
        );
    }
    snapshot.cash = money(i64::MAX);
    assert_observation_rejected_unchanged(
        &config,
        &snapshot,
        &proposal,
        &context,
        RejectionReason::ArithmeticOverflow,
    );
}

#[test]
fn regression_invalid_equity_basis_cannot_partially_commit_state() {
    let (config, mut snapshot, proposal, context) = fixture();
    snapshot.cash = money(1_300_000);
    for defect in 0..5 {
        let mut bad = snapshot.clone();
        match defect {
            0 => bad.equity_basis.day_start_equity = Cny::ZERO,
            1 => bad.equity_basis.cash_flow_adjusted_peak = Cny::ZERO,
            2 => bad.equity_basis.net_external_flow_today_fen = i64::MIN,
            3 => bad.equity_basis.net_external_flow_total_fen = i64::MIN,
            _ => bad.equity_basis.net_external_flow_total_fen = 1_300_001,
        }
        assert_observation_rejected_unchanged(
            &config,
            &bad,
            &proposal,
            &context,
            RejectionReason::ValuationUnavailable,
        );
    }
}

#[test]
fn regression_restore_repeat_and_next_day_observation_preserve_locks_and_peak() {
    let (config, mut snapshot, mut proposal, mut context) = fixture();
    let mut kernel = RiskKernel::new(config.clone()).unwrap();
    snapshot.cash = money(1_300_000);
    kernel
        .observe_account(&snapshot, context.now, context.trading_day)
        .unwrap();
    let peak_checkpoint = kernel.state().clone();
    let mut restored = RiskKernel::restore(config.clone(), peak_checkpoint.clone()).unwrap();
    restored
        .observe_account(&snapshot, context.now, context.trading_day)
        .unwrap();
    assert_eq!(restored.state(), &peak_checkpoint);
    snapshot.cash = money(900_000);
    restored
        .observe_account(&snapshot, context.now, context.trading_day)
        .unwrap();
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        assert!(restored
            .state()
            .freezes(scope)
            .contains(&FreezeReason::DailyLoss));
        assert!(restored
            .state()
            .freezes(scope)
            .contains(&FreezeReason::Drawdown));
    }
    let locked_checkpoint = restored.state().clone();
    restored = RiskKernel::restore(config, locked_checkpoint.clone()).unwrap();
    snapshot.cash = money(1_000_000);
    snapshot.trading_day = TradingDay(20261029);
    snapshot.as_of.0 += 86_400_000;
    snapshot.equity_basis.day_start_equity = snapshot.cash;
    context.now = snapshot.as_of;
    context.trading_day = snapshot.trading_day;
    let original = snapshot.clone();
    for _ in 0..2 {
        assert_eq!(
            restored.observe_account(&snapshot, context.now, context.trading_day),
            Ok(snapshot.cash)
        );
        assert_eq!(restored.state(), &locked_checkpoint);
    }
    proposal.proposal_id = ProposalId(2); // a fresh proposal cannot reset account history
    proposal.decision_at = context.now;
    proposal.data_available_at = context.now;
    proposal.earliest_execution_at = Timestamp(context.now.0 + 1);
    proposal.expires_at = Timestamp(context.now.0 + 60_000);
    context.rules.as_mut().unwrap().trading_day = context.trading_day;
    context.rules.as_mut().unwrap().available_at = context.now;
    context.cost.as_mut().unwrap().proposal_id = proposal.proposal_id;
    assert!(matches!(
        restored.review_fixture(&snapshot, &proposal, &context),
        RiskDecision::Rejected {
            reason: RejectionReason::Frozen {
                scope: RiskScope::Account,
                reason: FreezeReason::DailyLoss
            },
            ..
        }
    ));
    assert_eq!(restored.state(), &locked_checkpoint);
    assert_eq!(snapshot, original);
}

#[test]
fn regression_missing_market_evidence_still_latches_trusted_loss() {
    let (config, mut snapshot, proposal, mut context) = fixture();
    let mut kernel = RiskKernel::new(config).unwrap();
    snapshot.cash = money(900_000);
    context.rules = None;
    assert!(matches!(
        kernel.review_fixture(&snapshot, &proposal, &context),
        RiskDecision::Rejected {
            reason: RejectionReason::MissingMarketEvidence,
            ..
        }
    ));
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        assert!(
            kernel
                .state()
                .freezes(scope)
                .contains(&FreezeReason::DailyLoss),
            "missing {scope} daily-loss latch"
        );
    }
    snapshot.cash = money(1_000_000);
    let (_, _, _, valid_context) = fixture();
    assert!(matches!(
        kernel.review_fixture(&snapshot, &proposal, &valid_context),
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
fn regression_missing_cost_evidence_still_records_trusted_peak() {
    let (config, mut snapshot, proposal, mut context) = fixture();
    let mut kernel = RiskKernel::new(config).unwrap();
    snapshot.cash = money(1_300_000);
    context.cost = None;
    assert!(matches!(
        kernel.review_fixture(&snapshot, &proposal, &context),
        RiskDecision::Rejected {
            reason: RejectionReason::MissingCostEvidence,
            ..
        }
    ));
    snapshot.cash = money(1_000_000);
    let (_, _, _, valid_context) = fixture();
    assert!(matches!(
        kernel.review_fixture(&snapshot, &proposal, &valid_context),
        RiskDecision::Rejected {
            reason: RejectionReason::Frozen {
                scope: RiskScope::Account,
                reason: FreezeReason::Drawdown
            },
            ..
        }
    ));
}
