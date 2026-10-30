//! Explicit, read-only PR #33 store projection. Never opens the observer or a Provider.
use crate::{ensure, hash, parse_day, InputSummary, Result};
use rusqlite::{Connection, OpenFlags};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
};

pub const SCOPE: &str = "forward_eod_research_summary_v1";
pub const VERSION: &str = "eod-agent-input-v1";
pub const MAX_SYNC_AGE_MS: i64 = 24 * 60 * 60 * 1000;
const MAX_STORE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_CONTENT_BYTES: usize = 8 * 1024 * 1024;
const AVAILABILITY: &str =
    "validated_in_process_precommit_wall_time; not_exact_durable_visibility_or_commit_time";

pub fn repository_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
}

pub fn valid_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 64
        && (name.as_bytes()[0].is_ascii_lowercase() || name.as_bytes()[0].is_ascii_digit())
        && name
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
}

// Check ancestors before resolving; canonicalize alone would conceal junctions.
pub fn no_links(path: &Path) -> Result<()> {
    for part in path.ancestors() {
        if let Ok(meta) = fs::symlink_metadata(part) {
            let mut linked = meta.file_type().is_symlink();
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                linked |= meta.file_attributes() & 0x400 != 0;
            }
            ensure(!linked, "SNAPSHOT_LINK_PATH_DENIED")?;
        }
    }
    Ok(())
}

#[derive(Clone)]
pub struct SnapshotSource {
    path: PathBuf,
}
impl SnapshotSource {
    pub fn named(name: &str) -> Result<Self> {
        ensure(valid_name(name), "SNAPSHOT_STORE_NAME")?;
        Ok(Self {
            path: repository_root()
                .join("state/data-sync")
                .join(name)
                .join("snapshots.sqlite"),
        })
    }

    pub fn read(&self, now_ms: i64) -> Result<InputSummary> {
        self.read_store(now_ms).map_err(|error| {
            if error.0 == "AGENT_STORAGE_UNAVAILABLE" {
                "SNAPSHOT_STORE_UNAVAILABLE".into()
            } else {
                error
            }
        })
    }

    fn read_store(&self, now_ms: i64) -> Result<InputSummary> {
        no_links(&self.path)?;
        let meta = fs::metadata(&self.path).map_err(|_| "SNAPSHOT_STORE_MISSING")?;
        ensure(
            meta.is_file() && meta.len() <= MAX_STORE_BYTES,
            "SNAPSHOT_STORE_SIZE",
        )?;
        for suffix in ["-wal", "-shm", "-journal"] {
            let side = self
                .path
                .with_file_name(format!("snapshots.sqlite{suffix}"));
            no_links(&side)?;
            if let Ok(m) = fs::metadata(&side) {
                ensure(
                    m.is_file() && m.len() <= MAX_STORE_BYTES,
                    "SNAPSHOT_STORE_SIZE",
                )?;
                ensure(suffix != "-journal", "SNAPSHOT_STORE_JOURNAL")?;
            }
        }
        ensure(
            !self.path.with_file_name("snapshots.sqlite-wal").exists()
                || self.path.with_file_name("snapshots.sqlite-shm").is_file(),
            "SNAPSHOT_WAL_INCOMPLETE",
        )?;
        // No immutable=1: committed content may still be in the live store WAL.
        let c = Connection::open_with_flags(&self.path, OpenFlags::SQLITE_OPEN_READ_ONLY)
            .map_err(|_| "SNAPSHOT_STORE_UNAVAILABLE")?;
        c.execute_batch("PRAGMA query_only=ON; BEGIN;")?;
        let version: i64 = c.pragma_query_value(None, "user_version", |r| r.get(0))?;
        let journal: String = c.pragma_query_value(None, "journal_mode", |r| r.get(0))?;
        ensure(version == 1050 && journal == "wal", "SNAPSHOT_STORE_SCHEMA")?;
        let checks: Vec<String> = c
            .prepare("PRAGMA quick_check")?
            .query_map([], |r| r.get(0))?
            .collect::<std::result::Result<_, _>>()?;
        ensure(checks == ["ok"], "SNAPSHOT_STORE_INTEGRITY")?;
        let (binding, key, attempt): (String, String, String) = c.query_row(
            "SELECT binding,current_sha,attempt FROM control WHERE id=1",
            [],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )?;
        let size: i64 = c.query_row(
            "SELECT length(CAST(content AS BLOB)) FROM snapshots WHERE sha=?1",
            [&key],
            |r| r.get(0),
        )?;
        ensure(
            size > 0 && size <= MAX_CONTENT_BYTES as i64,
            "SNAPSHOT_CONTENT_SIZE",
        )?;
        let content: String =
            c.query_row("SELECT content FROM snapshots WHERE sha=?1", [&key], |r| {
                r.get(0)
            })?;
        let value: Value =
            serde_json::from_str(&content).map_err(|_| "SNAPSHOT_CONTENT_INVALID")?;
        // PR #33 uses sorted compact UTF-8 JSON, with integer monetary/time fields.
        // Reject noncanonical encodings rather than hash different Python/Rust JSON.
        ensure(
            serde_json::to_string(&value).is_ok_and(|s| s == content)
                && hash(content.as_bytes()) == key,
            "SNAPSHOT_HASH_MISMATCH",
        )?;
        let binding = serde_json::from_str(&binding).map_err(|_| "SNAPSHOT_BINDING_INVALID")?;
        let attempt = serde_json::from_str(&attempt).map_err(|_| "SNAPSHOT_SYNC_INVALID")?;
        project(&key, &value, &binding, &attempt, now_ms)
    }
}

fn ms(v: &Value) -> Result<i64> {
    v.as_i64()
        .filter(|n| *n > 0)
        .ok_or_else(|| "SNAPSHOT_TIME_INVALID".into())
}
fn source_day(v: &Value) -> Result<String> {
    let raw = v.as_str().ok_or("SNAPSHOT_SOURCE_DAY")?;
    ensure(
        raw.len() == 8 && raw.bytes().all(|b| b.is_ascii_digit()),
        "SNAPSHOT_SOURCE_DAY",
    )?;
    let day = format!("{}-{}-{}", &raw[..4], &raw[4..6], &raw[6..]);
    parse_day(&day).map_err(|_| crate::Error::from("SNAPSHOT_SOURCE_DAY"))?;
    Ok(day)
}

fn project(
    key: &str,
    v: &Value,
    binding: &Value,
    attempt: &Value,
    now_ms: i64,
) -> Result<InputSummary> {
    ensure(
        v["schema_version"] == 1
            && v["can_research"] == true
            && v["can_execute_forward_paper"] == false
            && v["live_allowed"] == false
            && v["historical_pit"] == "NOT_VERIFIED"
            && v["available_at_semantics"] == AVAILABILITY
            && v["opening_source"] == "BLOCKED"
            && v["blockers"] == json!([])
            && v["pending_runs"] == 0,
        "SNAPSHOT_CONTRACT",
    )?;
    let mode = v["data_mode"].as_str().ok_or("SNAPSHOT_MODE")?;
    ensure(
        matches!(mode, "synthetic_test" | "forward_observed_eod")
            && v["data_mode"] == binding["data_mode"]
            && v["journal_genesis"] == binding["journal_genesis"]
            && matches!(
                binding["source"]["kind"].as_str(),
                Some("authorized_observer" | "repository_synthetic_fixture")
            )
            && (binding["source"]["kind"] != "repository_synthetic_fixture"
                || mode == "synthetic_test"),
        "SNAPSHOT_SOURCE_BINDING",
    )?;
    let chain = v["journal_chain"]
        .as_array()
        .ok_or("SNAPSHOT_SOURCE_BINDING")?;
    ensure(
        !chain.is_empty()
            && chain.first() == Some(&v["journal_genesis"])
            && chain.last() == Some(&v["journal_head"])
            && v["event_count"].as_u64() == Some(chain.len() as u64),
        "SNAPSHOT_SOURCE_BINDING",
    )?;
    ensure(
        attempt["state"] == "succeeded"
            && attempt["error_code"].is_null()
            && attempt["blockers"] == json!([])
            && attempt["journal_head"] == v["journal_head"],
        "SNAPSHOT_SYNC_NOT_SUCCEEDED",
    )?;
    let started = ms(&attempt["started_at"])?;
    let finished = ms(&attempt["finished_at"])?;
    ensure(
        started <= finished && finished <= now_ms && now_ms - started <= MAX_SYNC_AGE_MS,
        "SNAPSHOT_SYNC_STALE_OR_CLOCK",
    )?;
    let bars = v["bars"].as_array().ok_or("SNAPSHOT_SOURCE_DAY")?;
    ensure(
        !bars.is_empty()
            && v["valid_eod_days"].as_u64() == Some(bars.len() as u64)
            && bars
                .windows(2)
                .all(|w| w[0]["bar"]["trade_day"].as_str() < w[1]["bar"]["trade_day"].as_str()),
        "SNAPSHOT_SOURCE_DAY",
    )?;
    let last = bars.last().unwrap();
    ensure(
        last["bar"]["trade_day"] == v["last_valid_source_day"],
        "SNAPSHOT_SOURCE_DAY",
    )?;
    let day = source_day(&v["last_valid_source_day"])?;
    let observed = ms(&last["observed_at"])?;
    let received = ms(&last["received_at"])?;
    let available = ms(&last["available_at"])?;
    let asof = ms(&v["as_of_journal_event_at"])?;
    let available_day = chrono::DateTime::from_timestamp_millis(available)
        .ok_or("SNAPSHOT_TIME_INVALID")?
        .with_timezone(&chrono_tz::Asia::Shanghai)
        .format("%Y-%m-%d")
        .to_string();
    ensure(
        observed <= received
            && received <= available
            && available <= asof
            && asof <= started
            && day <= available_day
            && last["provider_published_at"].is_null(),
        "SNAPSHOT_TIME_INVALID",
    )?;
    ensure(
        v["on_day_valid_eod_days"]
            .as_u64()
            .is_some_and(|n| n <= bars.len() as u64),
        "SNAPSHOT_QUALITY_INVALID",
    )?;
    let warnings = v["warnings"].as_array().ok_or("SNAPSHOT_QUALITY_INVALID")?;
    ensure(
        warnings.iter().all(|w| {
            matches!(
                w.as_str(),
                Some(
                    "INTERRUPTED_COLLECTION"
                        | "LATE_BACKFILL"
                        | "REVISED_EOD"
                        | "COLLECTION_ERROR"
                        | "MISSING_ON_DAY_EOD"
                )
            )
        }),
        "SNAPSHOT_QUALITY_INVALID",
    )?;
    let coverage = v["coverage"].as_array().ok_or("SNAPSHOT_QUALITY_INVALID")?;
    let gaps = v["gaps"].as_array().ok_or("SNAPSHOT_QUALITY_INVALID")?;
    for row in coverage.iter().chain(gaps) {
        source_day(&row["source_day"])?;
        ensure(
            matches!(
                row["state"].as_str(),
                Some("valid_eod" | "market_closed" | "missing_valid_eod" | "calendar_unknown")
            ),
            "SNAPSHOT_QUALITY_INVALID",
        )?;
    }
    let safe_rows = |rows: &[Value]| -> Vec<Value> {
        rows.iter()
            .rev()
            .take(16)
            .rev()
            .map(|r| json!({"source_day":r["source_day"],"state":r["state"]}))
            .collect()
    };
    let summary = json!({
        "snapshot_id":format!("eod-v1:{key}"), "snapshot_sha256":key,
        "data_mode":mode, "last_valid_source_day":v["last_valid_source_day"],
        "as_of_journal_event_at":asof, "observed_at":observed, "received_at":received,
        "available_at":available, "provider_published_at":null,
        "available_at_semantics":AVAILABILITY,
        "valid_eod_days":v["valid_eod_days"], "on_day_valid_eod_days":v["on_day_valid_eod_days"],
        "quality":{"coverage":safe_rows(coverage),"coverage_count":coverage.len(),
            "gaps":safe_rows(gaps),"gap_count":gaps.len(),"warnings":warnings,"blockers":[],
            "historical_pit":"NOT_VERIFIED","opening_source":"BLOCKED",
            "source_checked_only_at_latest_sync":true,"calendar_after_snapshot":"UNKNOWN_NOT_FETCHED",
            "sync_policy":"latest_succeeded_within_24h"},
        "restriction":"RESEARCH_ONLY", "eod_eligible":false,
        "can_execute_forward_paper":false,"live_allowed":false
    });
    ensure(
        serde_json::to_vec(&summary).is_ok_and(|b| b.len() <= 8192),
        "SNAPSHOT_SUMMARY_SIZE",
    )?;
    Ok(InputSummary {
        version: format!("{VERSION}:{key}"),
        source_day: day,
        mode: mode.into(),
        scopes: vec!["owner_task".into(), SCOPE.into()],
        summary,
        eod_eligible: false,
    })
}
