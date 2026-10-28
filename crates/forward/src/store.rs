use crate::{hash, model::*, provider, Result};
use fs2::FileExt;
use rusqlite::{params, Connection, OpenFlags, TransactionBehavior};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    path::Path,
    time::Instant,
};

pub struct Journal {
    db: Connection,
    _lock: File,
    entries: Vec<Entry>,
    config: Config,
    started_at: i64,
    poisoned: bool,
}

fn connect(path: &Path, create: bool) -> Result<(Connection, File)> {
    let path = fs::canonicalize(path).map_err(|e| e.to_string())?;
    for name in ["forward.lock", "forward.sqlite"] {
        if fs::symlink_metadata(path.join(name)).is_ok_and(|m| m.file_type().is_symlink()) {
            return Err("观察日志与锁不允许链接".into());
        }
    }
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(path.join("forward.lock"))
        .map_err(|e| e.to_string())?;
    lock.try_lock_exclusive()
        .map_err(|_| "该观察目录已有本机写入者")?;
    let flags = OpenFlags::SQLITE_OPEN_READ_WRITE
        | if create {
            OpenFlags::SQLITE_OPEN_CREATE
        } else {
            OpenFlags::empty()
        };
    let db = Connection::open_with_flags(path.join("forward.sqlite"), flags)
        .map_err(|e| e.to_string())?;
    db.execute_batch("PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;")
        .map_err(|e| e.to_string())?;
    Ok((db, lock))
}
fn digest(previous: &str, seq: i64, payload: &str) -> Result<String> {
    Ok(hash(
        &serde_json::to_vec(&(1, "forward_observation", previous, seq, payload))
            .map_err(|e| e.to_string())?,
    ))
}
impl Journal {
    pub fn create(path: impl AsRef<Path>, config: Config) -> Result<Self> {
        Self::create_at(path.as_ref(), config, now())
    }
    fn create_at(path: &Path, config: Config, started_at: i64) -> Result<Self> {
        config.validate()?;
        local_time(started_at)?;
        fs::create_dir(path).map_err(|e| format!("必须使用新目录；不覆盖已有观察：{e}"))?;
        let (mut db, lock) = connect(path, true)?;
        let event = Event::Initialized {
            config: config.clone(),
            started_at,
            version: VERSION.into(),
            host: format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH),
        };
        let payload = serde_json::to_string(&event).map_err(|e| e.to_string())?;
        let head = digest("", 0, &payload)?;
        let tx = db
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        tx.execute_batch("PRAGMA user_version=1041;
            CREATE TABLE events(seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE checkpoint(id INTEGER PRIMARY KEY CHECK(id=1), seq INTEGER NOT NULL, digest TEXT NOT NULL);
            CREATE TRIGGER no_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only'); END;
            CREATE TRIGGER no_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only'); END;")
            .map_err(|e| e.to_string())?;
        tx.execute("INSERT INTO events VALUES(0,?1,?2)", params![payload, head])
            .map_err(|e| e.to_string())?;
        tx.execute("INSERT INTO checkpoint VALUES(1,0,?1)", [&head])
            .map_err(|e| e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(Self {
            db,
            _lock: lock,
            entries: vec![Entry {
                sequence: 0,
                event,
                digest: head,
            }],
            config,
            started_at,
            poisoned: false,
        })
    }
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let (db, lock) = connect(path.as_ref(), false)?;
        let version: i64 = db
            .pragma_query_value(None, "user_version", |r| r.get(0))
            .map_err(|e| e.to_string())?;
        let integrity: String = db
            .query_row("PRAGMA integrity_check", [], |r| r.get(0))
            .map_err(|e| e.to_string())?;
        if version != 1041 || integrity != "ok" {
            return Err("forward schema/完整性失败；拒绝迁移或重建".into());
        }
        let mut entries: Vec<Entry> = vec![];
        {
            let mut stmt = db
                .prepare("SELECT seq,payload,digest FROM events ORDER BY seq")
                .map_err(|e| e.to_string())?;
            let rows = stmt
                .query_map([], |r| {
                    Ok((
                        r.get::<_, i64>(0)?,
                        r.get::<_, String>(1)?,
                        r.get::<_, String>(2)?,
                    ))
                })
                .map_err(|e| e.to_string())?;
            for row in rows {
                let (seq, payload, head) = row.map_err(|e| e.to_string())?;
                if seq != entries.len() as i64
                    || head != digest(entries.last().map_or("", |e| &e.digest), seq, &payload)?
                {
                    return Err("forward 摘要链/序列损坏；保留文件并停止".into());
                }
                let event: Event = serde_json::from_str(&payload).map_err(|e| e.to_string())?;
                if let Event::CollectionFinished { outcome, .. } = &event {
                    for raw in &outcome.raw {
                        if raw.sha256 != hash(&raw.body) {
                            return Err("原始响应摘要不符".into());
                        }
                    }
                }
                entries.push(Entry {
                    sequence: seq,
                    event,
                    digest: head,
                });
            }
        }
        let checkpoint: (i64, String) = db
            .query_row("SELECT seq,digest FROM checkpoint WHERE id=1", [], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .map_err(|e| e.to_string())?;
        if entries
            .last()
            .is_none_or(|e| checkpoint != (e.sequence, e.digest.clone()))
        {
            return Err("forward 提交尾标不符".into());
        }
        let (config, started_at) = match &entries.first().ok_or("缺少 genesis")?.event {
            Event::Initialized {
                config,
                started_at,
                version,
                ..
            } if version == VERSION => (config.clone(), *started_at),
            _ => return Err("观察 genesis/版本不符".into()),
        };
        config.validate()?;
        let journal = Self {
            db,
            _lock: lock,
            entries,
            config,
            started_at,
            poisoned: false,
        };
        journal.validate_runs()?;
        Ok(journal)
    }
    fn validate_runs(&self) -> Result<()> {
        let mut pending = BTreeMap::new();
        let mut high = self.started_at;
        for entry in self.entries.iter().skip(1) {
            if !matches!(entry.event, Event::ClockFault { .. }) && entry.event.time() < high {
                return Err("观察时钟顺序损坏".into());
            }
            high = high.max(entry.event.time());
            match &entry.event {
                Event::Initialized { .. } => return Err("重复 genesis".into()),
                Event::CollectionStarted {
                    run_id,
                    trade_day,
                    calendar_from,
                    calendar_through,
                    ..
                } => {
                    date(trade_day)?;
                    date(calendar_from)?;
                    date(calendar_through)?;
                    if pending.insert(run_id, entry.sequence).is_some() {
                        return Err("重复 run ID".into());
                    }
                }
                Event::CollectionFinished { run_id, .. } | Event::Interrupted { run_id, .. } => {
                    if pending.remove(run_id).is_none() {
                        return Err("完成记录缺少原始采集意图".into());
                    }
                }
                Event::ClockFault { .. } => (),
            }
        }
        Ok(())
    }
    fn append(&mut self, event: Event) -> Result<i64> {
        if self.poisoned {
            return Err("提交结果不明；必须重启校验".into());
        }
        self.poisoned = true;
        let seq = self.entries.len() as i64;
        let payload = serde_json::to_string(&event).map_err(|e| e.to_string())?;
        let head = digest(self.head(), seq, &payload)?;
        let tx = self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        tx.execute(
            "INSERT INTO events VALUES(?1,?2,?3)",
            params![seq, payload, head],
        )
        .map_err(|e| e.to_string())?;
        tx.execute(
            "UPDATE checkpoint SET seq=?1,digest=?2 WHERE id=1",
            params![seq, head],
        )
        .map_err(|e| e.to_string())?;
        #[cfg(test)]
        fault_point("before_commit");
        tx.commit().map_err(|e| e.to_string())?;
        #[cfg(test)]
        fault_point("after_commit");
        self.entries.push(Entry {
            sequence: seq,
            event,
            digest: head,
        });
        self.poisoned = false;
        Ok(seq)
    }
    pub fn config(&self) -> &Config {
        &self.config
    }
    pub fn entries(&self) -> &[Entry] {
        &self.entries
    }
    pub fn head(&self) -> &str {
        &self.entries.last().unwrap().digest
    }
    fn high_water(&self) -> i64 {
        self.entries
            .iter()
            .map(|e| e.event.time())
            .max()
            .unwrap_or(self.started_at)
    }
    fn halted(&self) -> bool {
        self.entries
            .iter()
            .any(|e| matches!(e.event, Event::ClockFault { .. }))
    }
    fn pending(&self) -> Vec<String> {
        let mut runs = BTreeMap::new();
        for entry in &self.entries {
            match &entry.event {
                Event::CollectionStarted { run_id, .. } => {
                    runs.insert(run_id.clone(), ());
                }
                Event::CollectionFinished { run_id, .. } | Event::Interrupted { run_id, .. } => {
                    runs.remove(run_id);
                }
                _ => (),
            }
        }
        runs.into_keys().collect()
    }
    fn check_clock(&mut self, observed: i64) -> Result<()> {
        if self.halted() {
            return Err("clock_halted：需 Owner 核验时钟；旧日志不会重置".into());
        }
        if observed < self.high_water() {
            self.append(Event::ClockFault {
                detected_at: observed,
                previous_high_water: self.high_water(),
                reason: "wall_clock_regressed".into(),
            })?;
            return Err("clock_halted：本机时钟倒退".into());
        }
        Ok(())
    }
    pub fn collect_once(&mut self, trade_day: Option<&str>) -> Result<String> {
        let observed = now();
        let timer = Instant::now();
        self.check_clock(observed)?;
        for run_id in self.pending() {
            self.append(Event::Interrupted {
                run_id,
                detected_at: observed,
            })?;
        }
        let today = local_day(observed)?;
        let day = trade_day.unwrap_or(&today);
        date(day)?;
        if day > today.as_str() {
            return Err("不采集未来交易日".into());
        }
        let attempts = self.entries.iter().filter(|e| matches!(&e.event, Event::CollectionStarted { observed_at, .. } if local_day(*observed_at).ok().as_ref() == Some(&today))).count();
        if attempts >= 8 {
            return Err("当日本地人工重试上限 8；不自动轮询".into());
        }
        let last_through = self
            .entries
            .iter()
            .rev()
            .find_map(|e| match &e.event {
                Event::CollectionFinished { outcome, .. } => {
                    outcome.calendar.last().map(|d| d.day.clone())
                }
                _ => None,
            })
            .unwrap_or(local_day(self.started_at)?);
        // Query every calendar day since the last successful calendar, including missed days.
        let from = if day < last_through.as_str() {
            day.to_string()
        } else {
            last_through
        };
        let span = (date(&today)? - date(&from)?).num_days();
        let run_id = format!("run-{}-{observed}", self.entries.len());
        self.append(Event::CollectionStarted {
            run_id: run_id.clone(),
            observed_at: observed,
            trade_day: day.into(),
            calendar_from: from.clone(),
            calendar_through: today.clone(),
        })?;
        let mut outcome = if span > 366 {
            Outcome::gap("calendar_gap_exceeds_one_year_manual_review")
        } else {
            provider::collect(&self.config, day, &from, &today)
        };
        let finished = now();
        let elapsed = timer.elapsed().as_millis() as i64;
        if finished < observed || ((finished - observed) - elapsed).abs() > 5_000 {
            // Preserve response diagnostics but never mark it valid forward evidence.
            outcome.status = "clock_changed_during_collection".into();
            outcome.bar = None;
            outcome.available_at = None;
            self.append(Event::ClockFault {
                detected_at: finished,
                previous_high_water: self.high_water(),
                reason: "wall_monotonic_disagreement".into(),
            })?;
        }
        // Clock faults can contain raw wall time but completion remains ordered after start.
        let committed_at = finished.max(observed);
        self.finish(&run_id, day, &today, committed_at, outcome)
    }
    fn finish(
        &mut self,
        run_id: &str,
        day: &str,
        today: &str,
        finished: i64,
        mut outcome: Outcome,
    ) -> Result<String> {
        outcome.late_backfill = day < today || day < local_day(finished)?.as_str();
        if outcome.available_at.is_some() {
            outcome.available_at = Some(finished);
        }
        // A changed trading calendar is unresolved source evidence, not permission to choose.
        let calendar_conflict = self.entries.iter().any(|entry| match &entry.event {
            Event::CollectionFinished { outcome: old, .. } => old.calendar.iter().any(|old_day| {
                outcome
                    .calendar
                    .iter()
                    .any(|new_day| old_day.day == new_day.day && old_day.is_open != new_day.is_open)
            }),
            _ => false,
        });
        if calendar_conflict {
            outcome.status = "calendar_conflict".into();
            outcome.bar = None;
            outcome.available_at = None;
        }
        if let Some(bar) = &outcome.bar {
            for entry in self.entries.iter().rev() {
                if let Event::CollectionFinished { outcome: old, .. } = &entry.event {
                    if let Some(old_bar) = &old.bar {
                        if old_bar.trade_day == bar.trade_day {
                            if bar == old_bar {
                                outcome.duplicate_of = Some(entry.sequence);
                            } else {
                                outcome.revision_of = Some(entry.sequence);
                            }
                            break;
                        }
                    }
                }
            }
        }
        let status = outcome.status.clone();
        self.append(Event::CollectionFinished {
            run_id: run_id.into(),
            finished_at: finished,
            outcome,
        })?;
        Ok(status)
    }
    pub fn status(&self) -> Result<Status<'_>> {
        let days: std::collections::BTreeSet<_> = self
            .entries
            .iter()
            .filter_map(|e| match &e.event {
                Event::CollectionFinished { outcome, .. }
                    if outcome.status == "valid_eod" && !outcome.late_backfill =>
                {
                    outcome.bar.as_ref().map(|b| &b.trade_day)
                }
                _ => None,
            })
            .collect();
        Ok(Status {
            mode: "forward_observation_only_v1",
            config: &self.config,
            started_at: local_time(self.started_at)?,
            head: self.head(),
            event_count: self.entries.len(),
            actual_valid_forward_days: days.len(),
            collection_attempts: self
                .entries
                .iter()
                .filter(|e| matches!(e.event, Event::CollectionStarted { .. }))
                .count(),
            pending_runs: self.pending().len(),
            clock_halted: self.halted(),
            local_source_authorization_recorded: self
                .config
                .local_automation_and_raw_storage_authorized,
            nav_fen: None,
            drawdown_bps: None,
            strategy_proposals: 0,
            simulated_fills: 0,
            pause_reason: PAUSE,
        })
    }
}

#[cfg(test)]
fn fault_point(point: &str) {
    if std::env::var("STRATIDE_FORWARD_FAULT_POINT").as_deref() == Ok(point) {
        std::process::exit(86);
    }
}

#[cfg(test)]
pub(crate) mod test_access {
    use super::*;
    pub fn create_at(path: &Path, config: Config, now: i64) -> Journal {
        Journal::create_at(path, config, now).unwrap()
    }
    pub fn append(j: &mut Journal, event: Event) -> Result<i64> {
        j.append(event)
    }
    pub fn check_clock(j: &mut Journal, now: i64) -> Result<()> {
        j.check_clock(now)
    }
    pub fn finish(
        j: &mut Journal,
        run: &str,
        day: &str,
        today: &str,
        at: i64,
        out: Outcome,
    ) -> Result<String> {
        j.finish(run, day, today, at, out)
    }
}
