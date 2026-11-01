//! CASH_DIVIDEND_V1: immutable modeled events, one ledger, no real-account gate.
use crate::{model::*, State};
use serde::{Deserialize, Serialize};
use stratide_contracts::*;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DividendPhase {
    Record,
    Ex,
    Payment,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CashUnit {
    PerShare,
    PerTenShares,
}

/// Only modeled withholding fully funded by the same gross receivable. Deferred
/// real A-share holding-period tax is deliberately NOT represented by zero.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DividendTax {
    pub version: String,
    pub basis: String,
    pub identity: String,
    pub withholding_ppm: u32,
    pub rounding: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CashDividendV1 {
    pub schema: String,
    pub event_id: String,
    pub version: String,
    pub instrument: Instrument,
    pub mode: DataMode,
    pub evidence_basis: String,
    pub fact_status: String,
    pub source_sha256: String,
    pub source_available_at: Timestamp,
    pub announcement_at: Timestamp,
    pub record_day: TradingDay,
    pub record_close_at: Timestamp,
    pub record_at: Timestamp,
    pub ex_day: TradingDay,
    pub ex_at: Timestamp,
    pub payment_day: TradingDay,
    pub payment_at: Timestamp,
    pub currency: String,
    pub cash_amount_fen: i64,
    pub cash_unit: CashUnit,
    pub tax: DividendTax,
    pub historical_pit: String,
    pub real_account_eligible: bool,
}

/// Shanghai-local day for a UTC epoch millisecond timestamp. This conversion
/// validates declared event dates without a wall-clock or timezone dependency.
pub fn local_day(t: Timestamp) -> Result<TradingDay> {
    let z =
        t.0.checked_add(28_800_000)
            .ok_or("时间溢出")?
            .div_euclid(86_400_000)
            + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = mp + if mp < 10 { 3 } else { -9 };
    y += i64::from(m <= 2);
    let value = u32::try_from(y * 10_000 + m * 100 + d).map_err(|_| "日期溢出")?;
    let day = TradingDay(value);
    if t.0 < 0 || !day.is_valid() {
        return Err("事件时间/日期无效".into());
    }
    Ok(day)
}

pub fn sha256_valid(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl CashDividendV1 {
    pub fn validate(&self, mode: &DataMode) -> Result<()> {
        let synthetic = *mode == DataMode::SyntheticTest;
        if self.schema != "CASH_DIVIDEND_V1"
            || self.mode != *mode
            || self.evidence_basis != if synthetic { "synthetic_assumption" } else { "historical_ex_post_assumption" }
            || self.fact_status != if synthetic { "SYNTHETIC_MODEL" } else { "EX_POST_MODEL_ONLY" }
            || self.real_account_eligible
            || self.historical_pit != "NOT_VERIFIED"
            || self.event_id.trim().is_empty()
            || self.version.trim().is_empty()
            || self.instrument.market != Market::Shanghai
            || !self.instrument.is_valid()
            || !self.instrument.code.starts_with("60")
            || !sha256_valid(&self.source_sha256)
            || self.currency != "CNY"
            || self.cash_amount_fen <= 0
            || self.tax.version.trim().is_empty()
            || self.tax.basis != if synthetic { "synthetic_assumption" } else { "historical_ex_post_assumption" }
            || self.tax.identity != "modeled_withholding_only_not_real_account"
            || self.tax.withholding_ppm > 1_000_000
            || self.tax.rounding != "ceil_per_event_fen_v1"
            || self.announcement_at.0 < 0
            || self.announcement_at > self.record_close_at
            || self.source_available_at < self.announcement_at
            || (synthetic && self.source_available_at > self.record_at)
            || self.record_at <= self.record_close_at
            || self.record_at >= self.ex_at
            || self.ex_at > self.payment_at
            || self.record_day >= self.ex_day
            || self.ex_day > self.payment_day
            || local_day(self.record_at)? != self.record_day
            || local_day(self.record_close_at)? != self.record_day
            || self.record_close_at.0.rem_euclid(86_400_000) != 25_200_000 // 15:00 Shanghai
            || local_day(self.ex_at)? != self.ex_day
            || local_day(self.payment_at)? != self.payment_day
        {
            return Err("CASH_DIVIDEND_V1：仅普通沪市A股显式隔离模型；来源/单位/日期/税务不完整或真实资格被拒绝".into());
        }
        self.per_share_fen()?;
        Ok(())
    }

    pub fn per_share_fen(&self) -> Result<i64> {
        let divisor = if self.cash_unit == CashUnit::PerShare {
            1
        } else {
            10
        };
        if self.cash_amount_fen <= 0 || self.cash_amount_fen % divisor != 0 {
            return Err("每股股息含无法表示的分数分；禁止取整补造".into());
        }
        Ok(self.cash_amount_fen / divisor)
    }

    pub fn amounts(&self, shares: i64) -> Result<(i64, i64)> {
        if shares < 0 {
            return Err("权益股数不可为负".into());
        }
        let gross = self
            .per_share_fen()?
            .checked_mul(shares)
            .ok_or("股息溢出")?;
        let tax = (i128::from(gross) * i128::from(self.tax.withholding_ppm) + 999_999) / 1_000_000;
        Ok((gross, i64::try_from(tax).map_err(|_| "股息税溢出")?))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DividendAccount {
    pub event: CashDividendV1,
    pub entitled_shares: Option<i64>,
    pub recognized: bool,
    pub paid: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CashDividendBook {
    pub events: Vec<DividendAccount>,
}

#[derive(Debug, Clone, Copy, Default, Serialize, PartialEq, Eq)]
pub struct DividendTotals {
    pub receivable_fen: i64,
    pub liability_fen: i64,
    pub gross_income_fen: i64,
    pub tax_expense_fen: i64,
    pub cash_paid_fen: i64,
}

impl DividendAccount {
    pub fn next(&self) -> Option<(DividendPhase, Timestamp, TradingDay)> {
        let e = &self.event;
        if self.entitled_shares.is_none() {
            Some((DividendPhase::Record, e.record_at, e.record_day))
        } else if !self.recognized {
            Some((DividendPhase::Ex, e.ex_at, e.ex_day))
        } else if !self.paid {
            Some((DividendPhase::Payment, e.payment_at, e.payment_day))
        } else {
            None
        }
    }
}

impl CashDividendBook {
    pub fn new(
        events: Vec<CashDividendV1>,
        mode: &DataMode,
        at: Timestamp,
        day: TradingDay,
    ) -> Result<Self> {
        if events.is_empty() {
            return Err("v4 需显式冻结分红事件，不能升级旧账本".into());
        }
        for (i, e) in events.iter().enumerate() {
            e.validate(mode)?;
            if e.record_at <= at
                || e.record_day < day
                || events[..i].iter().any(|old| old.event_id == e.event_id)
                || events[..i]
                    .iter()
                    .any(|old| old.instrument != e.instrument || old.payment_at >= e.record_at)
            {
                return Err("重复/冲突事件或登记时点早于新账本；V1仅支持同证券按时间排列、生命周期不重叠的事件".into());
            }
        }
        Ok(Self {
            events: events
                .into_iter()
                .map(|event| DividendAccount {
                    event,
                    entitled_shares: None,
                    recognized: false,
                    paid: false,
                })
                .collect(),
        })
    }

    pub fn totals(&self) -> Result<DividendTotals> {
        let mut t = DividendTotals::default();
        for a in &self.events {
            if a.paid && !a.recognized || a.recognized && a.entitled_shares.is_none() {
                return Err("权益/应收/到账阶段损坏".into());
            }
            let (gross, tax) = a.event.amounts(a.entitled_shares.unwrap_or(0))?;
            if a.recognized {
                t.gross_income_fen = add(t.gross_income_fen, gross)?;
                t.tax_expense_fen = add(t.tax_expense_fen, tax)?;
                if a.paid {
                    t.cash_paid_fen = add(t.cash_paid_fen, gross - tax)?;
                } else {
                    t.receivable_fen = add(t.receivable_fen, gross)?;
                    t.liability_fen = add(t.liability_fen, tax)?;
                }
            }
        }
        Ok(t)
    }

    pub(crate) fn guard_clock(&self, now: Timestamp) -> Result<()> {
        if self
            .events
            .iter()
            .filter_map(DividendAccount::next)
            .any(|(_, at, _)| at <= now)
        {
            return Err("须先处理到期登记/除息/到账；禁止跳过后回填权益或未来现金".into());
        }
        Ok(())
    }
}

impl State {
    pub fn dividend_totals(&self) -> Result<DividendTotals> {
        self.cash_dividends
            .as_ref()
            .map(CashDividendBook::totals)
            .unwrap_or(Ok(DividendTotals::default()))
    }
}
