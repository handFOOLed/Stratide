//! Owner-authenticated research budget edit.
//!
//! This is the only local write path for the research hard caps. It replaces
//! the trusted Agent `settings.json` budget block atomically, keeps the
//! first-configured currency/timezone identity immutable and records an audit
//! trail in the Agent store. It never touches the calls ledger: settled usage,
//! unsettled holds and BILLING_OVERRUN_REQUIRES_OWNER keep their existing
//! semantics, so a new cap only binds reservations made after this edit.
use crate::{
    budget,
    config::{Budget, Settings},
    ensure, hash, Agent, Result,
};
use chrono::{DateTime, SecondsFormat, Utc};
use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::Path,
};

pub const AUDIT_PREFIX: &str = "budget_audit:";
const SOURCE: &str = "owner_web";
const IDENTITY_KEY: &str = "budget_identity";
const MAX_MICRO: i64 = 1_000_000_000_000;
const MAX_SETTINGS_BYTES: u64 = 128 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    daily_limit_micro: String,
    monthly_limit_micro: String,
    confirm_below_committed: bool,
    #[serde(default)]
    currency: Option<String>,
    #[serde(default)]
    timezone: Option<String>,
}

/// Validate, atomically persist and audit an Owner budget change.
pub fn update(agent: &Agent, body: &Value, now: DateTime<Utc>) -> Result<Value> {
    let input: Input = serde_json::from_value(body.clone()).map_err(|_| "BUDGET_INPUT_INVALID")?;
    let daily_limit_micro = limit(&input.daily_limit_micro)?;
    let monthly_limit_micro = limit(&input.monthly_limit_micro)?;
    ensure(
        daily_limit_micro <= monthly_limit_micro,
        "BUDGET_INPUT_INVALID",
    )?;

    let path = agent.settings_path();
    let mut conn = agent.store().connect()?;
    let tx = conn.transaction_with_behavior(TransactionBehavior::Immediate)?;
    // One read supplies both the parsed settings and the sha256 that the atomic
    // replacement re-checks immediately before rename.
    let original = read_settings(path)?;
    let original_sha256 = original.as_deref().map(hash);
    let mut settings: Settings = match original {
        Some(bytes) => serde_json::from_slice(&bytes).map_err(|_| "BUDGET_CONFIG_INVALID")?,
        None => Settings::default(),
    };
    let old_budget = settings.budget.clone();
    let (currency, timezone) = identity(&tx, old_budget.as_ref(), &input)?;
    let new_budget = Budget {
        currency,
        timezone,
        daily_limit_micro,
        monthly_limit_micro,
    };
    if agent.uses_market_budget(&settings) {
        crate::market_research::validate_budget(&new_budget)?;
    }

    // Committed = settled for the current day/month plus every unsettled hold
    // (the same worst-case amount reserve() keeps until Owner invoice
    // reconciliation). Lowering a cap below that needs explicit confirmation.
    let committed = budget::view(&tx, Some(&new_budget), now)?;
    let held = i128::from(micro_field(&committed, "reserved_micro"));
    let below_committed = i128::from(daily_limit_micro)
        < i128::from(micro_field(&committed, "daily_settled_micro")) + held
        || i128::from(monthly_limit_micro)
            < i128::from(micro_field(&committed, "monthly_settled_micro")) + held;
    ensure(
        !below_committed || input.confirm_below_committed,
        "BUDGET_BELOW_COMMITTED",
    )?;

    settings.budget = Some(new_budget.clone());
    settings.validate()?;
    let identity = format!("{}|{}", new_budget.currency, new_budget.timezone);
    tx.execute(
        "INSERT OR IGNORE INTO meta(key,value) VALUES(?1,?2)",
        params![IDENTITY_KEY, identity],
    )?;
    let at = now.to_rfc3339_opts(SecondsFormat::Nanos, true);
    let audit = json!({
        "old": budget_record(old_budget.as_ref()),
        "new": budget_record(Some(&new_budget)),
        "at": at,
        "source": SOURCE,
    });
    tx.execute(
        "INSERT INTO meta(key,value) VALUES(?1,?2) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![format!("{AUDIT_PREFIX}{at}"), audit.to_string()],
    )?;
    write_atomic(
        path,
        &serde_json::to_vec_pretty(&settings).expect("settings JSON"),
        original_sha256,
    )?;
    tx.commit().map_err(|_| "BUDGET_SAVE_RESULT_UNKNOWN")?;

    Ok(json!({"budget": committed}))
}

fn limit(raw: &str) -> Result<i64> {
    let value = raw.parse::<i64>().map_err(|_| "BUDGET_INPUT_INVALID")?;
    ensure((1..=MAX_MICRO).contains(&value), "BUDGET_INPUT_INVALID")?;
    Ok(value)
}

fn micro_field(view: &Value, field: &str) -> i64 {
    view[field]
        .as_str()
        .expect("budget view micro field is a decimal string")
        .parse::<i64>()
        .expect("budget view micro field is an i64")
}

fn budget_record(budget: Option<&Budget>) -> Value {
    match budget {
        Some(budget) => json!({
            "currency": budget.currency,
            "timezone": budget.timezone,
            "daily_limit_micro": budget.daily_limit_micro.to_string(),
            "monthly_limit_micro": budget.monthly_limit_micro.to_string(),
        }),
        None => Value::Null,
    }
}

/// Currency and timezone are fixed by the first configuration (or by the
/// store identity written when that configuration first loaded). Later edits
/// may only repeat them, never change them.
fn identity(c: &Connection, current: Option<&Budget>, input: &Input) -> Result<(String, String)> {
    let stored: Option<String> = c.query_row("SELECT value FROM meta WHERE key=?1", [IDENTITY_KEY], |row| row.get(0)).optional()?;
    let configured = current.map(|budget| format!("{}|{}", budget.currency, budget.timezone));
    if let (Some(stored), Some(configured)) = (&stored, &configured) {
        ensure(stored == configured, "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE")?;
    }
    if let Some(locked) = stored.or(configured) {
        let (currency, timezone) = locked
            .split_once('|')
            .ok_or("BUDGET_CURRENCY_TIMEZONE_IMMUTABLE")?;
        if let Some(requested) = &input.currency {
            ensure(requested == currency, "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE")?;
        }
        if let Some(requested) = &input.timezone {
            ensure(requested == timezone, "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE")?;
        }
        return Ok((currency.to_string(), timezone.to_string()));
    }
    let install = Settings::local_default();
    let install_budget = install.budget.expect("install default budget");
    let currency = input.currency.clone().unwrap_or(install_budget.currency);
    let timezone = input.timezone.clone().unwrap_or(install_budget.timezone);
    ensure(
        currency.len() == 3 && currency.bytes().all(|b| b.is_ascii_uppercase()),
        "BUDGET_INPUT_INVALID",
    )?;
    ensure(
        timezone.parse::<chrono_tz::Tz>().is_ok(),
        "BUDGET_INPUT_INVALID",
    )?;
    Ok((currency, timezone))
}

fn read_settings(path: &Path) -> Result<Option<Vec<u8>>> {
    match fs::symlink_metadata(path) {
        Ok(meta) => {
            ensure(
                !is_link(&meta) && meta.is_file() && meta.len() <= MAX_SETTINGS_BYTES,
                "BUDGET_CONFIG_INVALID",
            )?;
            Ok(Some(fs::read(path).map_err(|_| "BUDGET_CONFIG_INVALID")?))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(_) => Err("BUDGET_CONFIG_INVALID".into()),
    }
}

#[cfg(windows)]
fn is_link(meta: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    meta.file_type().is_symlink() || meta.file_attributes() & 0x400 != 0
}

#[cfg(not(windows))]
fn is_link(meta: &fs::Metadata) -> bool {
    meta.file_type().is_symlink()
}

/// Same-directory create_new + sync_all + hash re-check + rename. A stale
/// hash means another writer (manual edit or another process) changed the file
/// after this request read it, so the replacement is abandoned.
fn write_atomic(path: &Path, bytes: &[u8], original_sha256: Option<String>) -> Result<()> {
    let pending = path.with_extension(format!("json.budget-pending-{}", crate::nonce()?));
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&pending)
        .map_err(|_| "BUDGET_CONFIG_INVALID")?;
    file.write_all(bytes).map_err(|_| "BUDGET_CONFIG_INVALID")?;
    file.sync_all().map_err(|_| "BUDGET_CONFIG_INVALID")?;
    drop(file);
    ensure(
        read_settings(path)?.as_deref().map(hash) == original_sha256,
        "BUDGET_CONFLICT_REREAD",
    )?;
    fs::rename(&pending, path).map_err(|_| "BUDGET_CONFIG_INVALID")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stale_original_hash_aborts_before_rename() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("settings.json");
        fs::write(&path, b"original").unwrap();
        let stale = Some(hash(b"original"));
        fs::write(&path, b"owner-hand-edit").unwrap();
        assert_eq!(
            write_atomic(&path, b"replacement", stale).unwrap_err().0,
            "BUDGET_CONFLICT_REREAD"
        );
        assert_eq!(fs::read(&path).unwrap(), b"owner-hand-edit");
    }

    #[test]
    fn missing_original_is_created_but_an_appearing_file_conflicts() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("settings.json");
        fs::write(&path, b"appeared").unwrap();
        assert_eq!(
            write_atomic(&path, b"replacement", None).unwrap_err().0,
            "BUDGET_CONFLICT_REREAD"
        );
        assert_eq!(fs::read(&path).unwrap(), b"appeared");
        fs::remove_file(&path).unwrap();
        write_atomic(&path, b"replacement", None).unwrap();
        assert_eq!(fs::read(&path).unwrap(), b"replacement");
    }
}
