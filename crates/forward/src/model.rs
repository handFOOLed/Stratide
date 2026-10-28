use crate::Result;
use chrono::{DateTime, FixedOffset, NaiveDate, Utc};
use serde::{Deserialize, Serialize};

pub const ENDPOINT: &str = "https://api.tushare.pro";
pub const VERSION: &str = "stratide-forward-v1/tushare-http-v1";
pub const TIMEZONE: &str = "Asia/Shanghai";
pub const PAUSE: &str = "observe_only_no_independent_opening_rules_or_cost_evidence";
pub const AVAILABILITY_SEMANTICS: &str =
    "validated_in_process_precommit_wall_time; not_exact_durable_visibility_or_commit_time";

/// No principal or risk defaults: this is an observation identity, not a funded account.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub observation_id: String,
    pub instrument: String,
    pub strategy_version: String,
    pub source: String,
    pub license_note: String,
    pub local_automation_and_raw_storage_authorized: bool,
}
impl Config {
    pub fn validate(&self) -> Result<()> {
        let (code, suffix) = self
            .instrument
            .split_once('.')
            .ok_or("证券应为 600000.SH / 000001.SZ")?;
        if code.len() != 6
            || !code.bytes().all(|b| b.is_ascii_digit())
            || !matches!(suffix, "SH" | "SZ")
            || self.source != "tushare_pro"
            || self.observation_id.trim().is_empty()
            || self.strategy_version.trim().is_empty()
            || self.license_note.trim().is_empty()
        {
            return Err("观察配置/单一来源或证券无效".into());
        }
        Ok(())
    }
    pub fn exchange(&self) -> &str {
        if self.instrument.ends_with(".SH") {
            "SSE"
        } else {
            "SZSE"
        }
    }
}

pub(crate) fn now() -> i64 {
    Utc::now().timestamp_millis()
}
pub fn local_time(ms: i64) -> Result<String> {
    Ok(DateTime::from_timestamp_millis(ms)
        .ok_or("无效时刻")?
        .with_timezone(&FixedOffset::east_opt(8 * 3600).unwrap())
        .to_rfc3339())
}
pub fn local_day(ms: i64) -> Result<String> {
    Ok(DateTime::from_timestamp_millis(ms)
        .ok_or("无效时刻")?
        .with_timezone(&FixedOffset::east_opt(8 * 3600).unwrap())
        .format("%Y%m%d")
        .to_string())
}
pub(crate) fn date(day: &str) -> Result<NaiveDate> {
    let d = NaiveDate::parse_from_str(day, "%Y%m%d").map_err(|_| "交易日应为 YYYYMMDD")?;
    if d.format("%Y%m%d").to_string() != day {
        return Err("日期格式无效".into());
    }
    Ok(d)
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct RawResponse {
    pub api: String,
    pub http_status: u16,
    pub sha256: String,
    pub received_at: i64,
    pub server_date: Option<String>,
    /// Exact decoded HTTP entity bytes, without token/request headers. Included in chain.
    pub body: Vec<u8>,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Bar {
    pub trade_day: String,
    pub open_fen: i64,
    pub high_fen: i64,
    pub low_fen: i64,
    pub close_fen: i64,
    pub volume_shares: i64,
    pub source_volume_unit: String,
    pub price_semantics: String,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CalendarDay {
    pub day: String,
    pub is_open: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Outcome {
    pub status: String,
    pub raw: Vec<RawResponse>,
    pub calendar: Vec<CalendarDay>,
    pub bar: Option<Bar>,
    pub provider_published_at: Option<i64>,
    /// Validation-complete wall time sampled before appending/committing the
    /// outcome; not a commit timestamp or proof another reader could see it then.
    pub available_at: Option<i64>,
    pub duplicate_of: Option<i64>,
    pub revision_of: Option<i64>,
    pub late_backfill: bool,
}
impl Outcome {
    pub(crate) fn gap(status: &str) -> Self {
        Self {
            status: status.into(),
            raw: vec![],
            calendar: vec![],
            bar: None,
            provider_published_at: None,
            available_at: None,
            duplicate_of: None,
            revision_of: None,
            late_backfill: false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "event", rename_all = "snake_case")]
pub enum Event {
    Initialized {
        config: Config,
        started_at: i64,
        version: String,
        host: String,
    },
    CollectionStarted {
        run_id: String,
        observed_at: i64,
        trade_day: String,
        calendar_from: String,
        calendar_through: String,
    },
    CollectionFinished {
        run_id: String,
        finished_at: i64,
        outcome: Outcome,
    },
    Interrupted {
        run_id: String,
        detected_at: i64,
    },
    ClockFault {
        detected_at: i64,
        previous_high_water: i64,
        reason: String,
    },
}
impl Event {
    pub(crate) fn time(&self) -> i64 {
        match self {
            Self::Initialized { started_at, .. } => *started_at,
            Self::CollectionStarted { observed_at, .. } => *observed_at,
            Self::CollectionFinished { finished_at, .. } => *finished_at,
            Self::Interrupted { detected_at, .. } | Self::ClockFault { detected_at, .. } => {
                *detected_at
            }
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entry {
    pub sequence: i64,
    pub event: Event,
    pub digest: String,
}

#[derive(Serialize)]
pub struct Status<'a> {
    pub mode: &'static str,
    pub config: &'a Config,
    pub started_at: String,
    pub head: &'a str,
    pub event_count: usize,
    pub actual_valid_forward_days: usize,
    pub collection_attempts: usize,
    pub pending_runs: usize,
    pub clock_halted: bool,
    pub local_source_authorization_recorded: bool,
    pub nav_fen: Option<i64>,
    pub drawdown_bps: Option<i64>,
    pub strategy_proposals: usize,
    pub simulated_fills: usize,
    pub pause_reason: &'static str,
}
