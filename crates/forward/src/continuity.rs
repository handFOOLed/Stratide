//! Daily operation and point-in-time reads of the existing observation journal.
use crate::{model::*, Journal, Result};
use chrono::Timelike;
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct EodStep {
    pub trade_day: String,
    pub status: String,
    pub collected: bool,
    pub ready: bool,
}

/// A read view, never an execution quote or permission to submit an order.
#[derive(Debug, Serialize)]
pub struct EodView<'a> {
    pub sequence: i64,
    pub available_at: i64,
    pub bar: &'a Bar,
    pub late_backfill: bool,
    pub opening_execution_eligible: bool,
}

pub(crate) fn ready(outcome: &Outcome, day: &str) -> bool {
    !outcome.late_backfill
        && (outcome.status == "market_closed"
            || (outcome.status == "valid_eod"
                && outcome.bar.as_ref().is_some_and(|b| b.trade_day == day)))
}

impl Journal {
    /// At most one completed automatic attempt per local day, across restarts.
    /// Explicit collect-once remains the bounded manual retry/backfill path.
    pub fn eod_step(&mut self) -> Result<EodStep> {
        let at = now();
        self.prepare_collection(at)?;
        if let Some(step) = self.eod_existing_step(at)? {
            return Ok(step);
        }
        let day = local_day(at)?;
        let status = self.collect_once(None)?;
        Ok(EodStep {
            ready: self.entries().last().is_some_and(|e| match &e.event {
                Event::CollectionFinished { outcome, .. } => ready(outcome, &day),
                _ => false,
            }),
            trade_day: day,
            status,
            collected: true,
        })
    }

    pub(crate) fn eod_existing_step(&self, at: i64) -> Result<Option<EodStep>> {
        let day = local_day(at)?;
        // Do not spend an attempt or request even a calendar before publication.
        let local =
            chrono::DateTime::parse_from_rfc3339(&local_time(at)?).map_err(|e| e.to_string())?;
        if local.hour() < 16 {
            return Ok(Some(EodStep {
                trade_day: day,
                status: "waiting_eod_publication_window".into(),
                collected: false,
                ready: false,
            }));
        }
        let mut starts = std::collections::BTreeMap::new();
        let mut latest = None;
        for entry in self.entries() {
            match &entry.event {
                Event::CollectionStarted {
                    run_id,
                    observed_at,
                    trade_day,
                    ..
                } => {
                    let local = chrono::DateTime::parse_from_rfc3339(&local_time(*observed_at)?)
                        .map_err(|e| e.to_string())?;
                    if trade_day == &day && local_day(*observed_at)? == day && local.hour() >= 16 {
                        starts.insert(run_id, *observed_at);
                    }
                }
                Event::CollectionFinished {
                    run_id, outcome, ..
                } if starts.contains_key(run_id) => {
                    latest = Some(outcome);
                }
                _ => (),
            }
        }
        // A completed post-publication attempt for today consumes the automatic
        // slot. Early probes and yesterday's backfills must not suppress EOD.
        Ok(latest.map(|outcome| EodStep {
            trade_day: day.clone(),
            ready: ready(outcome, &day),
            status: format!("already_attempted_today:{}", outcome.status),
            collected: false,
        }))
    }

    /// Select the version actually available by this instant. Later revisions,
    /// calendar conflicts and clock faults cannot be used to rewrite this view.
    /// EOD open is deliberately never eligible as contemporaneous opening data.
    pub fn eod_as_of(&self, day: &str, decision_at: i64) -> Result<Option<EodView<'_>>> {
        date(day)?;
        local_time(decision_at)?;
        let mut selected = None;
        for entry in self.entries() {
            if entry.event.time() > decision_at {
                continue;
            }
            match &entry.event {
                Event::ClockFault { .. } => return Ok(None),
                Event::CollectionFinished {
                    outcome,
                    finished_at,
                    ..
                } => {
                    if outcome.status == "calendar_conflict"
                        && outcome.calendar.iter().any(|d| d.day == day)
                    {
                        return Ok(None);
                    }
                    if outcome.status != "valid_eod" {
                        continue;
                    }
                    if let (Some(bar), Some(available_at)) = (&outcome.bar, outcome.available_at) {
                        if bar.trade_day == day
                            && available_at <= decision_at
                            && available_at >= *finished_at
                            && outcome.raw.iter().all(|r| r.received_at <= available_at)
                        {
                            selected = Some(EodView {
                                sequence: entry.sequence,
                                available_at,
                                bar,
                                late_backfill: outcome.late_backfill,
                                opening_execution_eligible: false,
                            });
                        }
                    }
                }
                _ => (),
            }
        }
        Ok(selected)
    }
}
