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
    pub available_at_semantics: &'static str,
    pub bar: &'a Bar,
    pub late_backfill: bool,
    pub opening_execution_eligible: bool,
}

/// A rollback has no trustworthy wall-clock occurrence timestamp. Sequence
/// proves only that it was appended after this previously ordered prefix.
#[derive(Debug, Serialize)]
pub struct ClockUncertainty {
    pub fault_sequence: i64,
    pub ordered_prefix_last_sequence: i64,
    pub ordered_prefix_high_water: i64,
    pub reported_detected_at: i64,
    pub interpretation: &'static str,
}

pub(crate) fn ready(outcome: &Outcome, day: &str) -> bool {
    !outcome.late_backfill
        && (outcome.status == "market_closed"
            || (outcome.status == "valid_eod"
                && outcome.bar.as_ref().is_some_and(|b| b.trade_day == day)))
}

impl Journal {
    /// A persisted post-publication intent consumes the daily automatic slot,
    /// including an unknown/interrupted outcome across restarts.
    /// Explicit collect-once remains the bounded manual retry/backfill path.
    pub fn eod_step(&mut self) -> Result<EodStep> {
        self.eod_step_at(now())
    }

    pub(crate) fn eod_step_at(&mut self, at: i64) -> Result<EodStep> {
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
        let mut latest_run = None;
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
                        latest_run = Some(run_id);
                        latest = Some(EodStep {
                            trade_day: day.clone(),
                            ready: false,
                            status:
                                "already_attempted_today:incomplete_collection_response_unknown"
                                    .into(),
                            collected: false,
                        });
                    }
                }
                Event::CollectionFinished {
                    run_id, outcome, ..
                } if latest_run == Some(run_id) => {
                    latest = Some(EodStep {
                        trade_day: day.clone(),
                        ready: ready(outcome, &day),
                        status: format!("already_attempted_today:{}", outcome.status),
                        collected: false,
                    });
                }
                Event::Interrupted { run_id, .. } if latest_run == Some(run_id) => {
                    latest = Some(EodStep {
                        trade_day: day.clone(),
                        ready: false,
                        status: "already_attempted_today:interrupted_response_unknown".into(),
                        collected: false,
                    });
                }
                _ => (),
            }
        }
        // The durable intent is enough: an unknown response must never trigger
        // an automatic retry. Early probes/backfills still do not consume EOD.
        Ok(latest)
    }

    pub fn clock_uncertainty(&self) -> Option<ClockUncertainty> {
        self.entries().iter().find_map(|entry| match &entry.event {
            Event::ClockFault { detected_at, previous_high_water, .. } => Some(ClockUncertainty {
                fault_sequence: entry.sequence,
                ordered_prefix_last_sequence: entry.sequence - 1,
                ordered_prefix_high_water: *previous_high_water,
                reported_detected_at: *detected_at,
                interpretation: "historical_ordered_prefix_only; later_wall_time_uncertain; detected_at_is_not_fault_occurrence_time",
            }),
            _ => None,
        })
    }

    /// Select the version actually available by this instant. Later revisions,
    /// calendar conflicts and clock faults cannot be used to rewrite this view.
    /// EOD open is deliberately never eligible as contemporaneous opening data.
    pub fn eod_as_of(&self, day: &str, decision_at: i64) -> Result<Option<EodView<'_>>> {
        date(day)?;
        local_time(decision_at)?;
        let mut selected = None;
        let mut calendar = None;
        for entry in self.entries() {
            if let Event::ClockFault {
                previous_high_water,
                ..
            } = &entry.event
            {
                // Never place a later event into the past using its regressed
                // wall clock. Preserve the prior prefix through its frontier;
                // beyond that frontier temporal ordering is unproven.
                if decision_at > *previous_high_water {
                    return Ok(None);
                }
                break;
            }
            if entry.event.time() > decision_at {
                continue;
            }
            if let Event::CollectionFinished {
                outcome,
                finished_at,
                ..
            } = &entry.event
            {
                // Same per-date conflict rule as the continuity report;
                // a different date's conflict cannot erase this day's EOD.
                for d in outcome.calendar.iter().filter(|d| d.day == day) {
                    if calendar.is_some_and(|open| open != d.is_open) {
                        return Ok(None);
                    }
                    calendar = Some(d.is_open);
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
                            available_at_semantics: AVAILABILITY_SEMANTICS,
                            bar,
                            late_backfill: outcome.late_backfill,
                            opening_execution_eligible: false,
                        });
                    }
                }
            }
        }
        Ok(selected)
    }
}
