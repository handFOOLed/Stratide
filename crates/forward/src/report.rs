use crate::{model::*, Journal, Result};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs::{self, File},
    io::Write,
    path::Path,
};

#[derive(Serialize)]
struct Daily {
    calendar_day: String,
    exchange: String,
    calendar_source: String,
    calendar_received_at: Option<String>,
    is_open: Option<bool>,
    run_id: Option<String>,
    observed_at: Option<String>,
    received_at: Option<String>,
    available_at: Option<String>,
    provider_published_at: Option<String>,
    status: String,
    attempt: usize,
    duplicate_of: Option<i64>,
    revision_of: Option<i64>,
    late_backfill: bool,
    daily_raw_sha256: Option<String>,
    calendar_raw_sha256: Option<String>,
    raw_daily_json: Option<String>,
    open_fen: Option<i64>,
    high_fen: Option<i64>,
    low_fen: Option<i64>,
    close_fen: Option<i64>,
    volume_shares: Option<i64>,
    price_semantics: &'static str,
    source_volume_unit: &'static str,
    source: &'static str,
    endpoint: &'static str,
    timezone: &'static str,
    strategy_proposals: usize,
    simulated_fills: usize,
    nav_fen: Option<i64>,
    drawdown_bps: Option<i64>,
    pause_reason: &'static str,
}
fn empty(day: &str, exchange: &str) -> Daily {
    Daily {
        calendar_day: day.into(),
        exchange: exchange.into(),
        calendar_source: "unavailable".into(),
        calendar_received_at: None,
        is_open: None,
        run_id: None,
        observed_at: None,
        received_at: None,
        available_at: None,
        provider_published_at: None,
        status: "no_collection_calendar_unknown".into(),
        attempt: 0,
        duplicate_of: None,
        revision_of: None,
        late_backfill: false,
        daily_raw_sha256: None,
        calendar_raw_sha256: None,
        raw_daily_json: None,
        open_fen: None,
        high_fen: None,
        low_fen: None,
        close_fen: None,
        volume_shares: None,
        price_semantics: "unadjusted_cny_fen",
        source_volume_unit: "hand_100_shares",
        source: "tushare_pro",
        endpoint: ENDPOINT,
        timezone: TIMEZONE,
        strategy_proposals: 0,
        simulated_fills: 0,
        nav_fen: None,
        drawdown_bps: None,
        pause_reason: PAUSE,
    }
}
impl Journal {
    pub fn report(&self, destination: impl AsRef<Path>) -> Result<()> {
        let destination = destination.as_ref();
        let mut calendar: BTreeMap<String, (Option<bool>, Option<String>, i64)> = BTreeMap::new();
        let mut runs = BTreeMap::new();
        let mut attempts = BTreeMap::new();
        let mut rows = vec![];
        for entry in self.entries() {
            match &entry.event {
                Event::CollectionStarted {
                    run_id,
                    observed_at,
                    trade_day,
                    ..
                } => {
                    let n = attempts.entry(trade_day.clone()).or_insert(0);
                    *n += 1;
                    let mut row = empty(trade_day, self.config().exchange());
                    row.run_id = Some(run_id.clone());
                    row.observed_at = Some(local_time(*observed_at)?);
                    row.status = "incomplete_collection_no_committed_response".into();
                    row.attempt = *n;
                    rows.push(row);
                    runs.insert(run_id.clone(), rows.len() - 1);
                }
                Event::CollectionFinished {
                    run_id, outcome, ..
                } => {
                    let row = &mut rows[*runs.get(run_id).ok_or("报告完成记录没有开始事件")?];
                    row.status = outcome.status.clone();
                    row.received_at = outcome
                        .raw
                        .iter()
                        .map(|r| r.received_at)
                        .max()
                        .map(local_time)
                        .transpose()?;
                    row.available_at = outcome.available_at.map(local_time).transpose()?;
                    row.provider_published_at =
                        outcome.provider_published_at.map(local_time).transpose()?;
                    row.duplicate_of = outcome.duplicate_of;
                    row.revision_of = outcome.revision_of;
                    row.late_backfill = outcome.late_backfill;
                    row.daily_raw_sha256 = outcome
                        .raw
                        .iter()
                        .find(|r| r.api == "daily")
                        .map(|r| r.sha256.clone());
                    row.calendar_raw_sha256 = outcome
                        .raw
                        .iter()
                        .find(|r| r.api == "trade_cal")
                        .map(|r| r.sha256.clone());
                    row.calendar_received_at = outcome
                        .raw
                        .iter()
                        .find(|r| r.api == "trade_cal")
                        .map(|r| local_time(r.received_at))
                        .transpose()?;
                    row.raw_daily_json = outcome
                        .raw
                        .iter()
                        .find(|r| r.api == "daily")
                        .and_then(|r| String::from_utf8(r.body.clone()).ok());
                    row.is_open = outcome
                        .calendar
                        .iter()
                        .find(|d| d.day == row.calendar_day)
                        .map(|d| d.is_open);
                    if row.is_open.is_some() {
                        row.calendar_source = "tushare_pro/trade_cal".into();
                    }
                    if let Some(bar) = &outcome.bar {
                        row.open_fen = Some(bar.open_fen);
                        row.high_fen = Some(bar.high_fen);
                        row.low_fen = Some(bar.low_fen);
                        row.close_fen = Some(bar.close_fen);
                        row.volume_shares = Some(bar.volume_shares);
                    }
                    for d in &outcome.calendar {
                        let received = outcome
                            .raw
                            .iter()
                            .find(|r| r.api == "trade_cal")
                            .map_or(entry.event.time(), |r| r.received_at);
                        let evidence = calendar.entry(d.day.clone()).or_insert((
                            Some(d.is_open),
                            row.calendar_raw_sha256.clone(),
                            received,
                        ));
                        if evidence.0 != Some(d.is_open) {
                            evidence.0 = None;
                        }
                    }
                }
                Event::Interrupted { run_id, .. } => {
                    rows[*runs.get(run_id).ok_or("中断记录没有开始事件")?].status =
                        "interrupted_response_unknown".into();
                }
                _ => (),
            }
        }
        let status = self.status()?;
        let mut day = date(&local_day(self.entries()[0].event.time())?)?;
        let last = date(&local_day(
            self.entries().iter().map(|e| e.event.time()).max().unwrap(),
        )?)?;
        while day <= last {
            let key = day.format("%Y%m%d").to_string();
            if !rows.iter().any(|r| r.calendar_day == key) {
                rows.push(empty(&key, self.config().exchange()));
            }
            day = day.succ_opt().ok_or("日期溢出")?;
        }
        for row in &mut rows {
            if let Some((open, sha, received)) = calendar.get(&row.calendar_day) {
                // Existing attempt facts retain their own calendar provenance; later lookup
                // only classifies unobserved dates, with its actual later receipt timestamp.
                if row.attempt != 0 {
                    continue;
                }
                row.is_open = *open;
                row.calendar_source = "tushare_pro/trade_cal".into();
                row.calendar_received_at = Some(local_time(*received)?);
                if row.calendar_raw_sha256.is_none() {
                    row.calendar_raw_sha256 = sha.clone();
                }
                if row.attempt == 0 {
                    row.status = match open {
                        Some(true) => "gap_no_collection_on_open_day",
                        Some(false) => "market_closed_no_collection",
                        None => "calendar_conflict",
                    }
                    .into();
                }
            }
        }
        rows.sort_by(|a, b| (&a.calendar_day, a.attempt).cmp(&(&b.calendar_day, b.attempt)));
        let mut csv = csv::Writer::from_writer(Vec::new());
        for row in &rows {
            csv.serialize(row).map_err(|e| e.to_string())?;
        }
        let csv = csv.into_inner().map_err(|e| e.to_string())?;
        let report = serde_json::json!({ "schema_version": 1, "status": status, "days_and_attempts": rows,
            "raw_values_and_responses": "events.json (exact response bytes in raw.body; verify sha256)",
            "metrics_unavailable_reason": "observation identity has no funded paper ledger, strategy or fills",
            "endpoint_version": VERSION,
            "integrity_limit": "local chain + SQLite checkpoint; not an external time attestation or protection against total privileged rewrite/rollback" });
        let files = [
            (
                "report.json",
                serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?,
            ),
            ("daily.csv", csv),
            (
                "events.json",
                serde_json::to_vec_pretty(self.entries()).map_err(|e| e.to_string())?,
            ),
        ];
        // Immutable per-head report publication. Crash leaves a separate incomplete staging dir.
        if destination.exists() {
            if fs::symlink_metadata(destination)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink()
                || fs::read_dir(destination)
                    .map_err(|e| e.to_string())?
                    .count()
                    != files.len()
            {
                return Err("已有报告不完整/冲突；保留它并显式选择新目录".into());
            }
            for (name, bytes) in &files {
                let p = destination.join(name);
                if fs::symlink_metadata(&p)
                    .map_err(|e| e.to_string())?
                    .file_type()
                    .is_symlink()
                    || fs::read(&p).map_err(|e| e.to_string())? != *bytes
                {
                    return Err("已有报告与当前日志 HEAD 不符；不覆盖旧报告".into());
                }
            }
            return Ok(());
        }
        let parent = destination
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        let staging = tempfile::Builder::new()
            .prefix(".forward-report-")
            .tempdir_in(parent)
            .map_err(|e| e.to_string())?;
        for (name, bytes) in &files {
            let mut f = File::create(staging.path().join(name)).map_err(|e| e.to_string())?;
            f.write_all(bytes)
                .and_then(|_| f.sync_all())
                .map_err(|e| e.to_string())?;
        }
        // Do not delete staging if publication fails: it may be the only report evidence.
        let staged = staging.keep();
        if destination.exists() {
            return Err(format!("报告目标已出现；保留暂存 {}", staged.display()));
        }
        fs::rename(&staged, destination)
            .map_err(|e| format!("报告未发布；保留 {}：{e}", staged.display()))?;
        Ok(())
    }
}
