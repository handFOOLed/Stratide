use serde::{Deserialize, Serialize};
use std::fmt;

/// Nonnegative CNY in integer fen (CNY 0.01). No rounding or floating point.
#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[serde(try_from = "i64", into = "i64")]
pub struct Cny(i64);

impl TryFrom<i64> for Cny {
    type Error = InvalidMoney;
    fn try_from(value: i64) -> Result<Self, Self::Error> {
        Self::from_fen(value)
    }
}
impl From<Cny> for i64 {
    fn from(value: Cny) -> Self {
        value.fen()
    }
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
pub struct InvalidMoney;

impl fmt::Display for InvalidMoney {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("金额必须是非负整数分，且不能溢出 i64")
    }
}
impl std::error::Error for InvalidMoney {}

impl Cny {
    pub const ZERO: Self = Self(0);

    pub fn from_fen(fen: i64) -> Result<Self, InvalidMoney> {
        (fen >= 0).then_some(Self(fen)).ok_or(InvalidMoney)
    }

    pub fn fen(self) -> i64 {
        self.0
    }

    pub fn checked_add(self, other: Self) -> Result<Self, InvalidMoney> {
        self.0.checked_add(other.0).map(Self).ok_or(InvalidMoney)
    }

    pub fn checked_mul(self, shares: i64) -> Result<Self, InvalidMoney> {
        if shares < 0 {
            return Err(InvalidMoney);
        }
        self.0.checked_mul(shares).map(Self).ok_or(InvalidMoney)
    }
}

impl fmt::Display for Cny {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{:02} 元", self.0 / 100, self.0 % 100)
    }
}

/// UTC milliseconds since Unix epoch; negative values are rejected by the kernel.
#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Timestamp(pub i64);

/// Exchange-local Gregorian YYYYMMDD, supplied by the trusted session/calendar owner.
#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct TradingDay(pub u32);

impl TradingDay {
    pub fn is_valid(self) -> bool {
        let year = self.0 / 10_000;
        let month = self.0 / 100 % 100;
        let day = self.0 % 100;
        let leap =
            year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
        let days = match month {
            2 if leap => 29,
            2 => 28,
            4 | 6 | 9 | 11 => 30,
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            _ => return false,
        };
        (1970..=9999).contains(&year) && (1..=days).contains(&day)
    }
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct DeploymentIdentity {
    pub group_id: String,
    pub strategy_id: String,
    /// Frozen code/parameter artifact version; not a display name.
    pub frozen_version: String,
    pub deployment_id: String,
}

impl DeploymentIdentity {
    pub fn is_valid(&self) -> bool {
        [
            &self.group_id,
            &self.strategy_id,
            &self.frozen_version,
            &self.deployment_id,
        ]
        .iter()
        .all(|s| !s.trim().is_empty())
    }
}

/// Unique within an account for its entire eventual ledger lifetime. Zero is invalid.
/// The ledger durably deduplicates IDs; reviewing an ID alone does not consume it.
#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ProposalId(pub u128);

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
pub enum Market {
    Shanghai,
    Shenzhen,
    Beijing,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct Instrument {
    pub market: Market,
    pub code: String,
}

impl Instrument {
    /// Syntax only. Listing, asset class and market membership need trusted evidence.
    pub fn is_valid(&self) -> bool {
        self.code.len() == 6 && self.code.bytes().all(|b| b.is_ascii_digit())
    }
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    Buy,
    Sell,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct OrderProposal {
    pub proposal_id: ProposalId,
    pub account_id: String,
    pub deployment: DeploymentIdentity,
    pub instrument: Instrument,
    pub side: Side,
    /// Signed at the proposal boundary so zero/negative requests can be rejected.
    pub quantity: i64,
    pub limit_price: Cny,
    pub decision_at: Timestamp,
    pub data_available_at: Timestamp,
    /// Strictly after the decision. Not an actual execution timestamp or fill.
    pub earliest_execution_at: Timestamp,
    pub expires_at: Timestamp,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
pub struct RiskLimits {
    /// Fee-inclusive commitment per proposal, including sells.
    pub max_order_commitment: Cny,
    /// Marked holdings + pending buy reservations + proposed buy cost (conservative).
    pub max_exposure: Cny,
    /// Explicit absolute CNY thresholds; no illustrative percentages become defaults.
    pub daily_loss: Cny,
    pub drawdown: Cny,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct PaperAccountConfig {
    pub account_id: String,
    pub authorized_principal: Cny,
    pub initial_capital: Cny,
    pub deployment: DeploymentIdentity,
    pub account_limits: RiskLimits,
    pub strategy_limits: RiskLimits,
    pub max_snapshot_age_ms: i64,
    pub max_mark_age_ms: i64,
}

impl PaperAccountConfig {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.account_id.trim().is_empty() || !self.deployment.is_valid() {
            return Err("账户或策略身份为空");
        }
        if self.initial_capital == Cny::ZERO || self.initial_capital > self.authorized_principal {
            return Err("模拟初始本金必须为正且不超过显式授权本金");
        }
        if self.max_snapshot_age_ms <= 0 || self.max_mark_age_ms <= 0 {
            return Err("必须显式配置正数快照/估值有效期");
        }
        for limits in [self.account_limits, self.strategy_limits] {
            if limits.daily_loss == Cny::ZERO || limits.drawdown == Cny::ZERO {
                return Err("必须显式配置正数亏损和回撤阈值");
            }
        }
        if self.strategy_limits.max_exposure > self.account_limits.max_exposure
            || self.account_limits.max_exposure > self.authorized_principal
        {
            return Err("策略敞口上限不得超过账户上限，账户上限不得超过授权本金");
        }
        Ok(())
    }

    /// New in-memory paper account only. Never use this to recover an existing ledger.
    pub fn initialize(
        &self,
        at: Timestamp,
        day: TradingDay,
    ) -> Result<AccountSnapshot, &'static str> {
        self.validate()?;
        if at.0 < 0 || !day.is_valid() {
            return Err("账户初始化时间或交易日无效");
        }
        Ok(AccountSnapshot {
            account_id: self.account_id.clone(),
            deployment: self.deployment.clone(),
            revision: 0,
            as_of: at,
            trading_day: day,
            cash: self.initial_capital,
            positions: vec![],
            pending_orders: vec![],
            marks: vec![],
            equity_basis: EquityBasis {
                day_start_equity: self.initial_capital,
                cash_flow_adjusted_peak: self.initial_capital,
                net_external_flow_today_fen: 0,
                net_external_flow_total_fen: 0,
            },
        })
    }
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct PositionLot {
    pub instrument: Instrument,
    pub quantity: i64,
    pub acquired_on: TradingDay,
}

/// Trusted existing commitments, not inferred from earlier review results.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct PendingOrder {
    pub proposal_id: ProposalId,
    pub instrument: Instrument,
    pub side: Side,
    pub quantity: i64,
    /// Included in snapshot cash, not extra cash. Buy amount includes all fee reserves.
    /// Sells reserve shares and have zero reserved_cash.
    pub reserved_cash: Cny,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct PositionMark {
    pub instrument: Instrument,
    pub price: Cny,
    pub as_of: Timestamp,
    pub available_at: Timestamp,
    pub source: String,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct EquityBasis {
    pub day_start_equity: Cny,
    /// Historical maximum of NAV minus cumulative external flows since initialization.
    pub cash_flow_adjusted_peak: Cny,
    /// Signed, trusted external contributions/withdrawals; never dividends/trading P&L.
    pub net_external_flow_today_fen: i64,
    pub net_external_flow_total_fen: i64,
}

/// Trusted single-account/single-strategy ledger projection. Not a Worker request.
/// The ledger owns authority, atomic reservations, cash-flow baselines and persistence.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct AccountSnapshot {
    pub account_id: String,
    pub deployment: DeploymentIdentity,
    pub revision: u64,
    pub as_of: Timestamp,
    pub trading_day: TradingDay,
    pub cash: Cny,
    pub positions: Vec<PositionLot>,
    pub pending_orders: Vec<PendingOrder>,
    pub marks: Vec<PositionMark>,
    pub equity_basis: EquityBasis,
}

#[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq)]
pub enum SettlementRule {
    SameDay,
    TPlusOne,
    Unknown,
}

/// Explicit trusted per-instrument/session evidence, not exchange rules guessed by code.
/// source must identify a versioned rule/market-status/price-band input.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct TradingRules {
    pub instrument: Instrument,
    pub trading_day: TradingDay,
    pub available_at: Timestamp,
    pub source: String,
    pub tradable: bool,
    pub settlement: SettlementRule,
    pub buy_lot: i64,
    pub sell_lot: i64,
    pub allow_odd_lot_liquidation: bool,
    pub tick_size: Cny,
    pub min_price: Cny,
    pub max_price: Cny,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct CostEstimate {
    /// Complete trusted binding; reusing an ID cannot authorize changed fields.
    pub proposal: OrderProposal,
    pub rules: TradingRules,
    pub valid_until: Timestamp,
    pub proposal_id: ProposalId,
    /// Conservative upper bound for this entire proposal, including all costs/taxes.
    pub maximum_fee: Cny,
    pub source: String,
}

/// Supplied by trusted core, separately from the proposal. No fetching/real feed in PR-01.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct ReviewContext {
    pub now: Timestamp,
    pub trading_day: TradingDay,
    pub rules: Option<TradingRules>,
    pub cost: Option<CostEstimate>,
}
