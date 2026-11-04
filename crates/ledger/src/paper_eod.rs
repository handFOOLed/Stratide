//! Paper engineering assumption, deliberately separate from an observed opening.
use crate::{DailyBar, DataMode, PaperOrder, Result, State};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use stratide_contracts::{Timestamp, TradingDay, TradingRules};

pub const LABEL: &str = "EX_POST_OPEN_ASSUMPTION";
pub const EXECUTION_MODEL: &str = "next-open-adverse-tick-100-v1";
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FrozenIntents {
    pub execution_model: String,
    pub frozen_at: Timestamp,
    pub decision_day: TradingDay,
    pub target_day: TradingDay,
    pub decision_source_sha256: String,
    pub orders_sha256: String,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Receipt {
    pub label: String,
    pub intents: FrozenIntents,
    pub source_sha256: String,
    pub source_received_at: Timestamp,
    pub accounted_at: Timestamp,
    pub fill_count: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PaperEodBook {
    pub pending: Option<FrozenIntents>,
    pub receipts: Vec<Receipt>,
}

fn sha_valid(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit())
}
fn orders_sha(orders: &[PaperOrder]) -> String {
    format!(
        "{:x}",
        Sha256::digest(
            serde_json::to_vec(&orders.iter().filter(|o| o.active()).collect::<Vec<_>>())
                .expect("orders JSON")
        )
    )
}
pub fn shanghai_day(t: Timestamp) -> Result<(TradingDay, u32)> {
    use chrono::{Datelike, Timelike};
    let d = chrono::DateTime::from_timestamp_millis(t.0)
        .ok_or("PAPER_TIMESTAMP_INVALID")?
        .with_timezone(&chrono::FixedOffset::east_opt(8 * 3600).expect("Shanghai offset"));
    Ok((
        TradingDay(
            u32::try_from(d.year()).map_err(|_| "PAPER_TIMESTAMP_INVALID")? * 10000
                + d.month() * 100
                + d.day(),
        ),
        d.hour(),
    ))
}
impl State {
    pub(crate) fn freeze_paper_intents(
        &mut self,
        now: Timestamp,
        target_day: TradingDay,
        source: &str,
    ) -> Result<()> {
        let (day, hour) = shanghai_day(now)?;
        if self.provenance.mode != DataMode::HistoricalReplay
            || !self
                .provenance
                .source_version
                .starts_with("paper-eod-assumption-v1")
            || !sha_valid(source)
            || !target_day.is_valid()
            || target_day <= day
            || hour < 16
            || now != self.snapshot.as_of
            || day != self.snapshot.trading_day
            || self.paper_eod.as_ref().is_some_and(|b| b.pending.is_some())
            || !self.orders.iter().any(|o| o.active())
            || self.orders.iter().filter(|o| o.active()).any(|o| {
                o.accepted_on != day
                    || o.proposal.decision_at > now
                    || o.proposal.data_available_at > now
            })
        {
            return Err("PAPER_INTENT_FREEZE_REQUIRES_CURRENT_EOD_AND_PRIOR_DAY_ORDERS".into());
        }
        let frozen = FrozenIntents {
            execution_model: EXECUTION_MODEL.into(),
            frozen_at: now,
            decision_day: day,
            target_day,
            decision_source_sha256: source.into(),
            orders_sha256: orders_sha(&self.orders),
        };
        self.paper_eod
            .get_or_insert_with(|| PaperEodBook {
                pending: None,
                receipts: vec![],
            })
            .pending = Some(frozen);
        Ok(())
    }
    pub(crate) fn ex_post_open(
        &mut self,
        now: Timestamp,
        bar: &DailyBar,
        rules: &TradingRules,
        source: &str,
        received: Timestamp,
        actions: bool,
    ) -> Result<()> {
        let intents = self
            .paper_eod
            .as_ref()
            .and_then(|b| b.pending.clone())
            .ok_or("PAPER_PRIOR_FROZEN_INTENTS_REQUIRED")?;
        let (day, hour) = shanghai_day(received)?;
        if !sha_valid(source)
            || intents.execution_model != EXECUTION_MODEL
            || !actions
            || !bar.status_verified
            || intents.target_day != bar.day
            || day != bar.day
            || hour < 16
            || received < bar.closes_at
            || received > now
            || bar.available_at != received
            || intents.frozen_at >= bar.opens_at
            || self.snapshot.as_of != intents.frozen_at
            || orders_sha(&self.orders) != intents.orders_sha256
        {
            return Err("PAPER_OPEN_SOURCE_OR_FROZEN_INTENTS_INVALID".into());
        }
        let before = self.fills.len();
        self.historical_next_open(bar, rules, now)?;
        for fill in &mut self.fills[before..] {
            fill.historical_execution = Some(format!(
                "{LABEL}; next-open adverse one tick; source_sha256={source}; received_at={}",
                received.0
            ));
        }
        let book = self.paper_eod.as_mut().expect("frozen book");
        book.pending = None;
        book.receipts.push(Receipt {
            label: LABEL.into(),
            intents,
            source_sha256: source.into(),
            source_received_at: received,
            accounted_at: now,
            fill_count: self.fills.len() - before,
        });
        Ok(())
    }
}
