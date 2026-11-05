//! Owner-frozen paper hypothesis policy. These are trusted IO contracts, never
//! strategy/LLM permissions. Financial state remains in the original Ledger.
use crate::{DailyBar, FeeSchedule};
use serde::{Deserialize, Serialize};
use stratide_contracts::*;

pub const VERSION: &str = "fixed-ticket-paper-v1";
pub const LABEL: &str = "UNVERIFIED_PAPER_HYPOTHESIS";
pub const ASSUMPTION: &str = "no-detected-action-mainboard-v1";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum CapacityScope {
    Batch,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UnverifiedEodPolicy {
    pub version: String,
    /// Separate Owner cap, never above the existing strategy/account limits.
    pub max_exposure: Cny,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Policy {
    pub version: String,
    pub universe: Vec<Instrument>,
    pub target_value: Cny,
    pub max_positions: usize,
    pub max_daily_orders: usize,
    pub max_candidates: usize,
    pub max_order_shares: i64,
    pub capacity_shares: i64,
    // Omission preserves already-written PR88 events; new Owner CLI policy
    // requires Batch. Legacy events retain their original per-order semantics.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capacity_scope: Option<CapacityScope>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub unverified_eod_assumption: Option<UnverifiedEodPolicy>,
    pub max_symbol_value: Cny,
    pub max_daily_fees: Cny,
    pub slippage_bps: u32,
    pub min_amount_thousand_yuan: u64,
    pub fees: Vec<FeeSchedule>,
    /// Owner accepts a transparent fixed ticket baseline, NOT model weights.
    pub approve_fixed_baseline: bool,
    pub automatic: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CalendarDay {
    pub day: TradingDay,
    pub sse_open: bool,
    pub szse_open: bool,
}

/// Projection verified against #83's original Agent task/Registry by the local
/// runner. No free text, model weights, authority/config or executable code.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Research {
    pub task_id: String,
    pub candidate_sha256: String,
    pub registration_sha256: String,
    pub model_version: String,
    pub generated_at: Timestamp,
    pub finished_at: Timestamp,
    pub ready_sessions: usize,
    pub restriction: String,
    pub eligibility: String,
    pub can_execute_forward_paper: bool,
    pub selected: Vec<Instrument>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Security {
    pub instrument: Instrument,
    pub close: Cny,
    pub rules: TradingRules,
    pub supported: bool,
    pub amount_thousand_yuan: u64,
    pub reason: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adjustment_factor: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Decision {
    pub now: Timestamp,
    pub day: TradingDay,
    pub source_sha256: String,
    pub received_at: Timestamp,
    pub calendar_sha256: String,
    pub calendar_received_at: Timestamp,
    /// Every calendar day, including closures, from T through next session.
    pub calendar: Vec<CalendarDay>,
    pub research: Option<Research>,
    pub securities: Vec<Security>,
    pub marks: Vec<PositionMark>,
    pub source_ready: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Quote {
    pub bar: DailyBar,
    pub rules: TradingRules,
    pub corporate_actions_verified: bool,
    pub reason: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub paper_assumption: Option<EodAssumption>,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct EodAssumption {
    pub pre_close: Cny,
    pub adjustment_factor: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Recovery {
    pub label: String,
    pub previous_day: TradingDay,
    pub valuation: Confirmation,
    pub equity: Cny,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Confirmation {
    pub now: Timestamp,
    pub day: TradingDay,
    pub source_sha256: String,
    pub received_at: Timestamp,
    /// Unordered delivery; execution always follows the frozen proposal order.
    pub quotes: Vec<Quote>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Batch {
    pub decision: Decision,
    pub target_day: Option<TradingDay>,
    pub policy_sha256: String,
    pub label: String,
    pub reason: String,
    pub proposal_ids: Vec<ProposalId>,
    pub rejections: Vec<(Instrument, String)>,
    pub finalized_at: Option<Timestamp>,
    pub confirmation: Option<Confirmation>,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Book {
    pub policy: Policy,
    pub approved_at: Timestamp,
    pub automatic: bool,
    pub pending: Option<usize>,
    pub batches: Vec<Batch>,
    pub last_event_at: Timestamp,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub recoveries: Vec<Recovery>,
}

pub fn digest<T: Serialize>(value: &T) -> String {
    use sha2::{Digest, Sha256};
    format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(value).expect("portfolio JSON"))
    )
}

pub fn session(day: TradingDay, hour: u32, minute: u32) -> crate::Result<Timestamp> {
    let date =
        chrono::NaiveDate::from_ymd_opt((day.0 / 10000) as i32, day.0 / 100 % 100, day.0 % 100)
            .ok_or("PORTFOLIO_INVALID_DAY")?;
    Ok(Timestamp(
        date.and_hms_opt(hour, minute, 0)
            .expect("session constants")
            .and_utc()
            .timestamp_millis(),
    ))
}

pub fn deadline(day: TradingDay) -> crate::Result<Timestamp> {
    // Frozen 18:00 Shanghai, matching the market collector's default cutoff.
    session(day, 10, 0)
}
