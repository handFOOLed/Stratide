//! Trusted paper account observation and mandatory proposal review.
//! No order submission, fill, ledger write or unlock API.
//! The caller is trusted Rust core; strategy Workers may supply only OrderProposal.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fmt;
use stratide_contracts::*;

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum FreezeReason {
    DailyLoss,
    Drawdown,
    OrderUncertainty,
    Manual,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
pub enum RiskScope {
    Account,
    Strategy,
}

impl fmt::Display for RiskScope {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Account => "账户",
            Self::Strategy => "策略",
        })
    }
}

impl fmt::Display for FreezeReason {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::DailyLoss => "每日净值亏损触发",
            Self::Drawdown => "净值回撤触发",
            Self::OrderUncertainty => "订单状态不确定",
            Self::Manual => "人工冻结",
        })
    }
}

/// Checkpoint persisted with the paper ledger by stratide-ledger. Calling
/// clone/restore alone is NOT disk recovery and confers no execution authority.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct RiskState {
    account_id: String,
    deployment: DeploymentIdentity,
    cash_flow_adjusted_peak: Cny,
    account_freezes: BTreeSet<FreezeReason>,
    strategy_freezes: BTreeSet<FreezeReason>,
}

impl RiskState {
    pub fn peak(&self) -> Cny {
        self.cash_flow_adjusted_peak
    }
    pub fn freezes(&self, scope: RiskScope) -> &BTreeSet<FreezeReason> {
        match scope {
            RiskScope::Account => &self.account_freezes,
            RiskScope::Strategy => &self.strategy_freezes,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RejectionReason {
    InvalidProposal(&'static str),
    IdentityMismatch,
    InvalidSnapshot(&'static str),
    DataNotAvailable,
    ProposalExpired,
    ArithmeticOverflow,
    MissingMarketEvidence,
    InvalidMarketEvidence,
    UnsupportedSettlement,
    MarketNotTradable,
    InvalidLot,
    InvalidPrice,
    MissingCostEvidence,
    FeesExceedProceeds {
        fees: Cny,
        proceeds: Cny,
    },
    ValuationUnavailable,
    AlreadyPending,
    InsufficientCash {
        required: Cny,
        available: Cny,
    },
    InsufficientPosition {
        requested: i64,
        available: i64,
    },
    TPlusOne {
        requested: i64,
        sellable: i64,
    },
    LimitExceeded {
        scope: RiskScope,
        kind: &'static str,
    },
    Frozen {
        scope: RiskScope,
        reason: FreezeReason,
    },
}

impl fmt::Display for RejectionReason {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidProposal(reason) => write!(f, "提案无效：{reason}"),
            Self::IdentityMismatch => f.write_str("账户/策略组/策略/冻结版本/部署身份不匹配"),
            Self::InvalidSnapshot(reason) => write!(f, "可信账户快照无效：{reason}"),
            Self::DataNotAvailable => f.write_str("决策使用了当时尚不可得的数据"),
            Self::ProposalExpired => f.write_str("提案已过期，必须重新决策"),
            Self::ArithmeticOverflow => f.write_str("金额或股数运算溢出，拒绝审查"),
            Self::MissingMarketEvidence => f.write_str("缺少该证券/交易日的可信市场规则证据"),
            Self::InvalidMarketEvidence => {
                f.write_str("市场规则证据不完整、过时或与证券/交易日不符")
            }
            Self::UnsupportedSettlement => f.write_str("无法确认交收可卖规则，保守拒绝"),
            Self::MarketNotTradable => f.write_str("市场证据表明当前不可交易（如停牌）"),
            Self::InvalidLot => f.write_str("数量不符合显式交易单位或零股卖出规则"),
            Self::InvalidPrice => f.write_str("价格不符合显式价格单位或价格区间"),
            Self::MissingCostEvidence => f.write_str("缺少绑定本提案的可信全额费用预留依据"),
            Self::FeesExceedProceeds { fees, proceeds } => write!(
                f,
                "卖出费用上界 {fees} 超过所得 {proceeds}；本切片不支持额外消耗现金的卖单"
            ),
            Self::ValuationUnavailable => f.write_str("全账户估值缺失、陈旧或不可信，不能判定风险"),
            Self::AlreadyPending => f.write_str("同一提案已经有未完成委托，不得重复使用"),
            Self::InsufficientCash {
                required,
                available,
            } => {
                write!(
                    f,
                    "可用资金不足：需要 {required}，扣除预留后仅有 {available}"
                )
            }
            Self::InsufficientPosition {
                requested,
                available,
            } => {
                write!(
                    f,
                    "持仓不足：申请卖出 {requested} 股，扣除预留后仅有 {available} 股"
                )
            }
            Self::TPlusOne {
                requested,
                sellable,
            } => {
                write!(
                    f,
                    "T+1 限制：申请卖出 {requested} 股，当前仅有 {sellable} 股可卖"
                )
            }
            Self::LimitExceeded { scope, kind } => write!(f, "{scope}层级超过{kind}上限"),
            Self::Frozen { scope, reason } => {
                write!(f, "{scope}风险冻结（{reason}），该提案不获许可")
            }
        }
    }
}

impl std::error::Error for RejectionReason {}

impl From<InvalidMoney> for RejectionReason {
    fn from(_: InvalidMoney) -> Self {
        Self::ArithmeticOverflow
    }
}

/// Only RiskKernel can construct this. It is neither Clone nor a spend/fill authority.
/// The ledger must re-review current state and atomically reserve;
/// snapshot revision/expiry alone do not prevent two approvals double-spending cash.
#[derive(Debug, PartialEq, Eq)]
pub struct Approval {
    proposal: OrderProposal,
    snapshot_revision: u64,
    reviewed_at: Timestamp,
    maximum_cash_debit: Cny,
    account_equity: Cny,
}

impl Approval {
    pub fn proposal(&self) -> &OrderProposal {
        &self.proposal
    }
    pub fn snapshot_revision(&self) -> u64 {
        self.snapshot_revision
    }
    pub fn reviewed_at(&self) -> Timestamp {
        self.reviewed_at
    }
    pub fn maximum_cash_debit(&self) -> Cny {
        self.maximum_cash_debit
    }
    pub fn account_equity(&self) -> Cny {
        self.account_equity
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum RiskDecision {
    Accepted(Box<Approval>),
    Rejected {
        proposal_id: ProposalId,
        reason: RejectionReason,
    },
}

pub struct RiskKernel {
    config: PaperAccountConfig,
    state: RiskState,
}

/// Private result of complete account validation and financial-state observation.
/// It is only passed to the private proposal checker, never an execution authority.
struct ObservedAccount {
    equity: Cny,
    exposure: Cny,
    reserved_cash: Cny,
    available_cash: i64,
}

impl RiskKernel {
    /// Only for a NEW explicitly funded in-memory paper run, never recovery.
    pub fn new(config: PaperAccountConfig) -> Result<Self, &'static str> {
        config.validate()?;
        let state = RiskState {
            account_id: config.account_id.clone(),
            deployment: config.deployment.clone(),
            cash_flow_adjusted_peak: config.initial_capital,
            account_freezes: BTreeSet::new(),
            strategy_freezes: BTreeSet::new(),
        };
        Ok(Self { config, state })
    }

    pub fn restore(config: PaperAccountConfig, state: RiskState) -> Result<Self, &'static str> {
        config.validate()?;
        if state.account_id != config.account_id || state.deployment != config.deployment {
            return Err("风险状态身份不匹配，不可通过重命名/重新部署绕过冻结");
        }
        Ok(Self { config, state })
    }

    pub fn state(&self) -> &RiskState {
        &self.state
    }

    /// Trusted management only. No corresponding automatic clearing operation.
    pub fn freeze(&mut self, scope: RiskScope, reason: FreezeReason) {
        match scope {
            RiskScope::Account => &mut self.state.account_freezes,
            RiskScope::Strategy => &mut self.state.strategy_freezes,
        }
        .insert(reason);
    }

    /// Observe trusted account NAV even when no proposal exists. Only trusted core
    /// supplies the snapshot, current UTC time and exchange-local trading day.
    /// Validate the complete account/valuation/basis before changing any risk state.
    /// Errors leave RiskState unchanged; Ok reports NAV even when financial locks latch.
    /// PR-02 must persist these updates independently of any later proposal decision.
    pub fn observe_account(
        &mut self,
        snapshot: &AccountSnapshot,
        now: Timestamp,
        day: TradingDay,
    ) -> Result<Cny, RejectionReason> {
        self.observe_snapshot(snapshot, now, day)
            .map(|observed| observed.equity)
    }

    fn observe_snapshot(
        &mut self,
        s: &AccountSnapshot,
        now: Timestamp,
        day: TradingDay,
    ) -> Result<ObservedAccount, RejectionReason> {
        use RejectionReason::*;
        if s.account_id != self.config.account_id || s.deployment != self.config.deployment {
            return Err(IdentityMismatch);
        }
        if now.0 < 0
            || !day.is_valid()
            || s.trading_day != day
            || s.as_of.0 < 0
            || s.as_of > now
            || now.0 - s.as_of.0 > self.config.max_snapshot_age_ms
        {
            return Err(InvalidSnapshot("快照时间/交易日无效或已过期"));
        }
        let mut reserved_cash = Cny::ZERO;
        let mut pending_ids = BTreeSet::new();
        for pending in &s.pending_orders {
            if pending.proposal_id.0 == 0
                || !pending_ids.insert(pending.proposal_id.0)
                || !pending.instrument.is_valid()
                || pending.quantity <= 0
                || (pending.side == Side::Buy && pending.reserved_cash == Cny::ZERO)
                || (pending.side == Side::Sell && pending.reserved_cash != Cny::ZERO)
            {
                return Err(InvalidSnapshot("未完成订单无效或重复"));
            }
            reserved_cash = reserved_cash.checked_add(pending.reserved_cash)?;
        }
        let available_cash = s
            .cash
            .fen()
            .checked_sub(reserved_cash.fen())
            .filter(|v| *v >= 0)
            .ok_or(InvalidSnapshot("现金预留超过账户现金"))?;

        let mut exposure = Cny::ZERO;
        for lot in &s.positions {
            if !lot.instrument.is_valid()
                || lot.quantity <= 0
                || !lot.acquired_on.is_valid()
                || lot.acquired_on > day
            {
                return Err(InvalidSnapshot("持仓数量、身份或取得日期无效"));
            }
            let mark = s
                .marks
                .iter()
                .find(|m| m.instrument == lot.instrument)
                .ok_or(ValuationUnavailable)?;
            if mark.price == Cny::ZERO
                || mark.source.trim().is_empty()
                || mark.as_of.0 < 0
                || mark.as_of > mark.available_at
                || mark.available_at > s.as_of
                || now.0 - mark.as_of.0 > self.config.max_mark_age_ms
            {
                return Err(ValuationUnavailable);
            }
            exposure = exposure.checked_add(mark.price.checked_mul(lot.quantity)?)?;
        }
        for (index, mark) in s.marks.iter().enumerate() {
            if s.marks[..index]
                .iter()
                .any(|m| m.instrument == mark.instrument)
            {
                return Err(ValuationUnavailable);
            }
        }
        // Reject over-reserved inventory anywhere in the one trusted account.
        for pending in s.pending_orders.iter().filter(|o| o.side == Side::Sell) {
            let owned = sum_shares(
                s.positions
                    .iter()
                    .filter(|l| l.instrument == pending.instrument)
                    .map(|l| l.quantity),
            )?;
            let reserved = sum_shares(
                s.pending_orders
                    .iter()
                    .filter(|o| o.side == Side::Sell && o.instrument == pending.instrument)
                    .map(|o| o.quantity),
            )?;
            if reserved > owned {
                return Err(InvalidSnapshot("卖出预留超过实际持仓"));
            }
        }
        let equity = s.cash.checked_add(exposure)?;
        self.observe_equity(equity, &s.equity_basis)?;

        Ok(ObservedAccount {
            equity,
            exposure,
            reserved_cash,
            available_cash,
        })
    }

    /// The sole proposal review entry point. Account validation/observation always runs
    /// before any proposal rejection; callers cannot skip it to obtain an Approval.
    /// Never changes cash, holdings or pending commitments in the immutable snapshot.
    pub fn review(
        &mut self,
        snapshot: &AccountSnapshot,
        proposal: &OrderProposal,
        context: &ReviewContext,
    ) -> RiskDecision {
        let result = self
            .observe_snapshot(snapshot, context.now, context.trading_day)
            .and_then(|observed| self.check(snapshot, proposal, context, observed));
        match result {
            Ok(approval) => RiskDecision::Accepted(Box::new(approval)),
            Err(reason) => RiskDecision::Rejected {
                proposal_id: proposal.proposal_id,
                reason,
            },
        }
    }

    fn check(
        &self,
        s: &AccountSnapshot,
        p: &OrderProposal,
        c: &ReviewContext,
        observed: ObservedAccount,
    ) -> Result<Approval, RejectionReason> {
        use RejectionReason::*;
        let ObservedAccount {
            equity,
            exposure,
            reserved_cash,
            available_cash,
        } = observed;
        if p.account_id != self.config.account_id || p.deployment != self.config.deployment {
            return Err(IdentityMismatch);
        }
        if p.proposal_id.0 == 0
            || !p.instrument.is_valid()
            || p.quantity <= 0
            || p.limit_price == Cny::ZERO
        {
            return Err(InvalidProposal("订单 ID、证券、正整数股数或价格无效"));
        }
        if c.now.0 < 0
            || p.decision_at.0 < 0
            || p.data_available_at.0 < 0
            || p.decision_at > c.now
            || p.earliest_execution_at <= p.decision_at
            || p.earliest_execution_at >= p.expires_at
        {
            return Err(InvalidProposal("决策/最早执行/到期时间无效"));
        }
        if p.data_available_at > p.decision_at {
            return Err(DataNotAvailable);
        }
        if c.now >= p.expires_at {
            return Err(ProposalExpired);
        }
        let rules = c.rules.as_ref().ok_or(MissingMarketEvidence)?;
        if rules.instrument != p.instrument
            || rules.trading_day != c.trading_day
            || rules.source.trim().is_empty()
            || rules.available_at.0 < 0
            || rules.available_at > c.now
            || c.now.0 - rules.available_at.0 > self.config.max_snapshot_age_ms
            || rules.buy_lot <= 0
            || rules.sell_lot <= 0
            || rules.tick_size == Cny::ZERO
            || rules.min_price == Cny::ZERO
            || rules.max_price < rules.min_price
        {
            return Err(InvalidMarketEvidence);
        }
        if rules.settlement == SettlementRule::Unknown {
            return Err(UnsupportedSettlement);
        }
        if !rules.tradable {
            return Err(MarketNotTradable);
        }
        if p.limit_price < rules.min_price
            || p.limit_price > rules.max_price
            || p.limit_price.fen() % rules.tick_size.fen() != 0
        {
            return Err(InvalidPrice);
        }
        let cost = c
            .cost
            .as_ref()
            .filter(|cost| {
                cost.proposal_id == p.proposal_id
                    && cost.proposal == *p
                    && cost.rules == *rules
                    && cost.valid_until > c.now
                    && !cost.source.trim().is_empty()
            })
            .ok_or(MissingCostEvidence)?;
        let gross = p.limit_price.checked_mul(p.quantity)?;
        let commitment = gross.checked_add(cost.maximum_fee)?;

        if s.pending_orders
            .iter()
            .any(|order| order.proposal_id == p.proposal_id)
        {
            return Err(AlreadyPending);
        }

        // Uncertainty/manual locks deny both sides. Financial locks permit only
        // independently verified long-position reductions, with all other checks intact.
        for scope in [RiskScope::Account, RiskScope::Strategy] {
            if let Some(reason) = self.state.freezes(scope).iter().find(|reason| {
                p.side == Side::Buy
                    || matches!(
                        reason,
                        FreezeReason::OrderUncertainty | FreezeReason::Manual
                    )
            }) {
                return Err(Frozen {
                    scope,
                    reason: *reason,
                });
            }
        }
        match p.side {
            Side::Buy => {
                if p.quantity % rules.buy_lot != 0 {
                    return Err(InvalidLot);
                }
                if commitment.fen() > available_cash {
                    return Err(InsufficientCash {
                        required: commitment,
                        available: Cny::from_fen(available_cash)?,
                    });
                }
                let projected = exposure
                    .checked_add(reserved_cash)?
                    .checked_add(commitment)?;
                for (scope, limits) in [
                    (RiskScope::Account, self.config.account_limits),
                    (RiskScope::Strategy, self.config.strategy_limits),
                ] {
                    if projected > limits.max_exposure {
                        return Err(LimitExceeded {
                            scope,
                            kind: "总敞口（含待成交预留）",
                        });
                    }
                }
            }
            Side::Sell => {
                let owned = sum_shares(
                    s.positions
                        .iter()
                        .filter(|l| l.instrument == p.instrument)
                        .map(|l| l.quantity),
                )?;
                let settled = sum_shares(
                    s.positions
                        .iter()
                        .filter(|l| {
                            l.instrument == p.instrument
                                && (rules.settlement == SettlementRule::SameDay
                                    || l.acquired_on < c.trading_day)
                        })
                        .map(|l| l.quantity),
                )?;
                let reserved = sum_shares(
                    s.pending_orders
                        .iter()
                        .filter(|o| o.side == Side::Sell && o.instrument == p.instrument)
                        .map(|o| o.quantity),
                )?;
                if reserved > settled {
                    return Err(InvalidSnapshot("已预留卖出股份不满足当前交收规则"));
                }
                if p.quantity > owned - reserved {
                    return Err(InsufficientPosition {
                        requested: p.quantity,
                        available: owned - reserved,
                    });
                }
                let sellable = settled - reserved;
                if p.quantity > sellable {
                    return Err(TPlusOne {
                        requested: p.quantity,
                        sellable,
                    });
                }
                if p.quantity % rules.sell_lot != 0
                    && !(rules.allow_odd_lot_liquidation && p.quantity == sellable)
                {
                    return Err(InvalidLot);
                }
                // Sell commitments currently reserve shares only. Reject net-debit
                // sells so pending sell costs cannot consume unreserved shared cash.
                if gross < cost.maximum_fee {
                    return Err(FeesExceedProceeds {
                        fees: cost.maximum_fee,
                        proceeds: gross,
                    });
                }
            }
        }
        for (scope, limits) in [
            (RiskScope::Account, self.config.account_limits),
            (RiskScope::Strategy, self.config.strategy_limits),
        ] {
            if commitment > limits.max_order_commitment {
                return Err(LimitExceeded {
                    scope,
                    kind: "单笔承诺金额",
                });
            }
        }
        Ok(Approval {
            proposal: p.clone(),
            snapshot_revision: s.revision,
            reviewed_at: c.now,
            maximum_cash_debit: if p.side == Side::Buy {
                commitment
            } else {
                Cny::ZERO
            },
            account_equity: equity,
        })
    }

    fn observe_equity(&mut self, equity: Cny, basis: &EquityBasis) -> Result<(), RejectionReason> {
        if basis.day_start_equity == Cny::ZERO || basis.cash_flow_adjusted_peak == Cny::ZERO {
            return Err(RejectionReason::ValuationUnavailable);
        }
        let adjust = |flow: i64| -> Result<i64, RejectionReason> {
            let value = i128::from(equity.fen()) - i128::from(flow);
            i64::try_from(value)
                .ok()
                .filter(|v| *v >= 0)
                .ok_or(RejectionReason::ValuationUnavailable)
        };
        let daily = adjust(basis.net_external_flow_today_fen)?;
        let total = Cny::from_fen(adjust(basis.net_external_flow_total_fen)?)?;
        self.state.cash_flow_adjusted_peak = self
            .state
            .cash_flow_adjusted_peak
            .max(basis.cash_flow_adjusted_peak)
            .max(total);
        let loss = basis.day_start_equity.fen().saturating_sub(daily);
        let drawdown = self.state.cash_flow_adjusted_peak.fen() - total.fen();
        // One strategy owns the whole current paper account; reuse one NAV, no extra cash.
        for (scope, limits) in [
            (RiskScope::Account, self.config.account_limits),
            (RiskScope::Strategy, self.config.strategy_limits),
        ] {
            if loss >= limits.daily_loss.fen() {
                self.freeze(scope, FreezeReason::DailyLoss);
            }
            if drawdown >= limits.drawdown.fen() {
                self.freeze(scope, FreezeReason::Drawdown);
            }
        }
        Ok(())
    }
}

fn sum_shares(mut values: impl Iterator<Item = i64>) -> Result<i64, RejectionReason> {
    values.try_fold(0_i64, |sum, v| {
        sum.checked_add(v)
            .ok_or(RejectionReason::ArithmeticOverflow)
    })
}

#[cfg(test)]
mod tests;
