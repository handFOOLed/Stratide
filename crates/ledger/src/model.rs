use serde::{Deserialize, Serialize};
use stratide_contracts::*;
use stratide_risk::RiskState;

pub type Result<T> = std::result::Result<T, String>;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DataMode {
    SyntheticTest,
    HistoricalReplay,
}

/// Mandatory provenance for every run. No forward-observation claim is supported.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Provenance {
    pub mode: DataMode,
    pub source_version: String,
    pub dataset_hash: String,
    pub timezone: String,
    pub price_semantics: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FeeSchedule {
    pub version: String,
    pub source: String,
    pub instrument: Instrument,
    pub valid_from: TradingDay,
    pub valid_through: TradingDay,
    pub commission_ppm: u32,
    pub minimum_commission: Cny,
    pub transfer_ppm: u32,
    pub sell_tax_ppm: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Fees {
    pub commission: Cny,
    pub transfer: Cny,
    pub tax: Cny,
}

impl Fees {
    pub fn total(&self) -> Result<Cny> {
        self.commission
            .checked_add(self.transfer)
            .and_then(|v| v.checked_add(self.tax))
            .map_err(|e| e.to_string())
    }
}

impl FeeSchedule {
    pub fn validate(&self, instrument: &Instrument, day: TradingDay) -> Result<()> {
        if self.version.trim().is_empty()
            || self.source.trim().is_empty()
            || self.instrument != *instrument
            || !self.valid_from.is_valid()
            || !self.valid_through.is_valid()
            || day < self.valid_from
            || day > self.valid_through
            || [self.commission_ppm, self.transfer_ppm, self.sell_tax_ppm]
                .iter()
                .any(|v| *v > 1_000_000)
        {
            return Err("缺少适用的版本化费率/生效日期证据".into());
        }
        Ok(())
    }

    /// Rounded UP in integer fen. Each partial execution incurs its own minimum.
    pub fn fees(&self, gross: Cny, side: Side) -> Result<Fees> {
        let rate = |ppm: u32| -> Result<Cny> {
            let n = (i128::from(gross.fen()) * i128::from(ppm) + 999_999) / 1_000_000;
            money(i64::try_from(n).map_err(|_| "费用溢出")?)
        };
        Ok(Fees {
            commission: rate(self.commission_ppm)?.max(self.minimum_commission),
            transfer: rate(self.transfer_ppm)?,
            tax: rate(if side == Side::Sell {
                self.sell_tax_ppm
            } else {
                0
            })?,
        })
    }

    /// Worst case: every share separately charged. Deliberately conservative and
    /// bounds any number of partial fills, per-fill minimum and rounding included.
    pub fn upper_bound(&self, p: &OrderProposal, rules: &TradingRules) -> Result<Cny> {
        let unit_price = if p.side == Side::Buy {
            p.limit_price
        } else {
            rules.max_price
        };
        self.fees(unit_price, p.side)?
            .total()?
            .checked_mul(p.quantity)
            .map_err(|e| e.to_string())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum OrderStatus {
    Open,
    PartiallyFilled,
    Filled,
    Rejected,
    Expired,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PaperOrder {
    pub proposal: OrderProposal,
    pub accepted_on: TradingDay,
    pub remaining: i64,
    pub status: OrderStatus,
    pub reason: String,
    pub fee_schedule: Option<FeeSchedule>,
    pub reserved_fee: Cny,
}

impl PaperOrder {
    pub fn active(&self) -> bool {
        matches!(
            self.status,
            OrderStatus::Open | OrderStatus::PartiallyFilled
        )
    }
}

/// A completed daily session from the trusted input owner. capacity_shares is an
/// explicit conservative liquidity assumption, shared by ALL orders in this session.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DailyBar {
    pub provenance: Provenance,
    pub instrument: Instrument,
    pub day: TradingDay,
    pub opens_at: Timestamp,
    pub closes_at: Timestamp,
    pub available_at: Timestamp,
    pub open: Cny,
    pub high: Cny,
    pub low: Cny,
    pub close: Cny,
    pub volume_shares: i64,
    pub capacity_shares: i64,
    pub status_verified: bool,
}

/// Independent opening observations. A completed daily bar is NOT evidence that
/// its open price/portfolio marks/rules were available to risk at session open.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OpeningEvidence {
    pub marks: Vec<PositionMark>,
    pub rules: TradingRules,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Fill {
    pub event_id: String,
    pub order_id: ProposalId,
    pub instrument: Instrument,
    pub side: Side,
    pub quantity: i64,
    pub price: Cny,
    pub fees: Fees,
    pub day: TradingDay,
    /// Simulation accounting time; never a claimed real exchange execution time.
    pub simulated_at: Timestamp,
    /// Opening risk qualification (modeled for historical_execution), NOT a fill instant.
    /// The original daily-crossing model requires the
    /// exclusive expires_at to be strictly AFTER evidence.closes_at, so its
    /// entire [opens_at, closes_at] evidence window precedes order expiry.
    pub risk_checked_at: Timestamp,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub opening_evidence: Option<OpeningEvidence>,
    /// Only the isolated historical reducer sets this; never opening evidence.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub historical_execution: Option<String>,
    pub evidence: DailyBar,
    pub fee_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct State {
    pub config: PaperAccountConfig,
    pub provenance: Provenance,
    pub snapshot: AccountSnapshot,
    pub risk: RiskState,
    pub orders: Vec<PaperOrder>,
    pub fills: Vec<Fill>,
    pub sessions: Vec<(Instrument, TradingDay)>,
    pub equity: Option<Cny>,
    pub valuation_error: Option<String>,
    /// Present only in explicitly created v4 isolation ledgers. Omitted v3 bytes
    /// and hashes are unchanged; no existing ledger is migrated.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cash_dividends: Option<crate::cash_dividend::CashDividendBook>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub paper_eod: Option<crate::paper_eod::PaperEodBook>,
}

/// Trusted-core commands. No Worker/control-network API is exposed by this crate.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum Command {
    FreezePaperIntentsV1 {
        now: Timestamp,
        target_day: TradingDay,
        decision_source_sha256: String,
    },
    ExPostOpenAssumptionV1 {
        now: Timestamp,
        bar: DailyBar,
        rules: TradingRules,
        source_sha256: String,
        source_received_at: Timestamp,
        corporate_actions_verified: bool,
    },
    CashDividendV1 {
        event_id: String,
        phase: crate::cash_dividend::DividendPhase,
        now: Timestamp,
        day: TradingDay,
        marks: Vec<PositionMark>,
    },
    /// Ex-post historical model, NOT a prospective opening observation. Fixed
    /// v1: next-open +/- one adverse tick, 100-share session capacity, no OHLC
    /// crossing or full-day volume eligibility. Never accepted in synthetic mode.
    HistoricalNextOpenV1 {
        now: Timestamp,
        bar: DailyBar,
        rules: TradingRules,
    },
    Observe {
        now: Timestamp,
        day: TradingDay,
        marks: Vec<PositionMark>,
        external_flow_fen: i64,
    },
    Submit {
        proposal: OrderProposal,
        now: Timestamp,
        day: TradingDay,
        rules: Option<TradingRules>,
        fees: Option<FeeSchedule>,
    },
    Match {
        now: Timestamp,
        day: TradingDay,
        instrument: Instrument,
        bar: Option<DailyBar>,
        rules: Option<TradingRules>,
        #[serde(default)]
        opening: Option<OpeningEvidence>,
    },
    Freeze {
        scope: stratide_risk::RiskScope,
        reason: stratide_risk::FreezeReason,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Genesis {
    pub config: PaperAccountConfig,
    pub provenance: Provenance,
    pub at: Timestamp,
    pub day: TradingDay,
}

pub(crate) fn money(fen: i64) -> Result<Cny> {
    Cny::from_fen(fen).map_err(|e| e.to_string())
}
pub(crate) fn add(a: i64, b: i64) -> Result<i64> {
    a.checked_add(b).ok_or_else(|| "整数运算溢出".into())
}
