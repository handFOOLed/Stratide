//! Paper engineering assumption, deliberately separate from an observed opening.
use crate::{Command, DailyBar, DataMode, FeeSchedule, PaperOrder, Result, State};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use stratide_contracts::{
    OrderProposal, PositionMark, ProposalId, Timestamp, TradingDay, TradingRules,
};

pub const LABEL: &str = "EX_POST_OPEN_ASSUMPTION";
pub const EXECUTION_MODEL: &str = "next-open-adverse-tick-100-v1";
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PaperIntent {
    pub now: Timestamp,
    pub target_day: TradingDay,
    pub decision_source_sha256: String,
    pub proposal: OrderProposal,
    pub rules: TradingRules,
    pub fees: FeeSchedule,
    pub marks: Vec<PositionMark>,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FrozenIntents {
    pub execution_model: String,
    // Old FreezePaperIntentsV1 events retain their original serialized hashes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub confirmation_deadline: Option<Timestamp>,
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
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub no_fills: Vec<NoFillReceipt>,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum NoFillReason {
    DataUnavailable,
    UnsealedLegacyIntent,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NoFillReceipt {
    pub label: String,
    pub reason: NoFillReason,
    pub deadline: Timestamp,
    pub finalized_at: Timestamp,
    pub intents: Option<FrozenIntents>,
    pub order_ids: Vec<ProposalId>,
}

fn session_at(day: TradingDay, utc_hour: u32, minute: u32) -> Result<Timestamp> {
    let date =
        chrono::NaiveDate::from_ymd_opt((day.0 / 10000) as i32, day.0 / 100 % 100, day.0 % 100)
            .ok_or("PAPER_TARGET_DAY_INVALID")?;
    Ok(Timestamp(
        date.and_hms_opt(utc_hour, minute, 0)
            .expect("fixed session time")
            .and_utc()
            .timestamp_millis(),
    ))
}
/// The existing EOD collection window closes at 17:15 Shanghai. This is a
/// precommitted paper deadline, never a provider delivery-time guarantee.
pub fn confirmation_deadline(day: TradingDay) -> Result<Timestamp> {
    session_at(day, 9, 15)
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
    pub(crate) fn submit_paper_intent(&mut self, intent: &PaperIntent) -> Result<()> {
        let (day, hour) = shanghai_day(intent.now)?;
        let opens = session_at(intent.target_day, 1, 30)?;
        if self.provenance.mode != DataMode::HistoricalReplay
            || !self
                .provenance
                .source_version
                .starts_with("paper-eod-assumption-v1")
            || !sha_valid(&intent.decision_source_sha256)
            || !intent.target_day.is_valid()
            || intent.target_day <= day
            || hour < 16
            || intent.proposal.decision_at != intent.now
            || intent.proposal.earliest_execution_at > opens
            || intent.proposal.expires_at <= opens
            || self.orders.iter().any(|o| o.active())
            || self
                .orders
                .iter()
                .any(|o| o.proposal.proposal_id == intent.proposal.proposal_id)
        {
            return Err("PAPER_ATOMIC_INTENT_WINDOW_OR_EXISTING_ORDER_INVALID".into());
        }
        self.apply(&Command::Observe {
            now: intent.now,
            day,
            marks: intent.marks.clone(),
            external_flow_fen: 0,
        })?;
        self.apply(&Command::Submit {
            proposal: intent.proposal.clone(),
            now: intent.now,
            day,
            rules: Some(intent.rules.clone()),
            fees: Some(intent.fees.clone()),
        })?;
        // A risk rejection is a durable terminal order, including any observed
        // financial lock. It has no reservation and must never be frozen.
        if self.orders.last().expect("new proposal appended").active() {
            self.freeze_paper_intents(
                intent.now,
                intent.target_day,
                &intent.decision_source_sha256,
            )?;
            self.paper_eod
                .as_mut()
                .expect("frozen book")
                .pending
                .as_mut()
                .expect("frozen intent")
                .confirmation_deadline = Some(confirmation_deadline(intent.target_day)?);
        }
        Ok(())
    }
    pub(crate) fn expire_paper_intents(&mut self, now: Timestamp) -> Result<()> {
        if !self
            .provenance
            .source_version
            .starts_with("paper-eod-assumption-v1")
            || now < self.snapshot.as_of
        {
            return Err("PAPER_EXPIRY_ACCOUNT_OR_CLOCK_INVALID".into());
        }
        let pending = self.paper_eod.as_ref().and_then(|b| b.pending.clone());
        let active = self
            .orders
            .iter()
            .filter(|o| o.active())
            .collect::<Vec<_>>();
        let latest = active
            .iter()
            .map(|o| o.accepted_on)
            .max()
            .ok_or("PAPER_NO_ACTIVE_INTENTS")?;
        let (deadline, reason) = if let Some(intents) = &pending {
            if orders_sha(&self.orders) != intents.orders_sha256 {
                return Err("PAPER_FROZEN_ORDERS_CHANGED".into());
            }
            let deadline = match intents.confirmation_deadline {
                Some(d) => d,
                None => confirmation_deadline(intents.target_day)?,
            };
            (deadline, NoFillReason::DataUnavailable)
        } else {
            // R1 legacy :submit without :freeze cannot ever execute in this
            // dedicated account. Once that decision day has ended, expire ALL
            // orphan orders rather than carrying or replaying them into today.
            (
                session_at(latest, 16, 0)?,
                NoFillReason::UnsealedLegacyIntent,
            )
        };
        if now < deadline {
            return Err("PAPER_NO_FILL_DEADLINE_NOT_REACHED".into());
        }
        let order_ids = active.iter().map(|o| o.proposal.proposal_id).collect();
        for index in 0..self.orders.len() {
            if self.orders[index].active() {
                self.expire(index);
                self.orders[index].reason = match reason {
                    NoFillReason::DataUnavailable => {
                        "NO_FILL / DATA_UNAVAILABLE：确认窗口已结束，整批意图到期，未模拟成交"
                    }
                    NoFillReason::UnsealedLegacyIntent => {
                        "NO_FILL / UNSEALED_LEGACY_INTENT：旧未冻结意图已过决策日，未模拟成交"
                    }
                }
                .into();
            }
        }
        // No marks, clock advance, NAV point, fill, or financial-lock reset.
        let book = self.paper_eod.get_or_insert_with(|| PaperEodBook {
            pending: None,
            receipts: vec![],
            no_fills: vec![],
        });
        book.pending = None;
        book.no_fills.push(NoFillReceipt {
            label: "NO_FILL".into(),
            reason,
            deadline,
            finalized_at: now,
            intents: pending,
            order_ids,
        });
        Ok(())
    }
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
            confirmation_deadline: None,
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
                no_fills: vec![],
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
            || intents
                .confirmation_deadline
                .is_some_and(|deadline| now >= deadline)
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
