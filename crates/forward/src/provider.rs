use crate::{hash, model::*, Result};
use chrono::{DateTime, Timelike};
use serde::Serialize;
use serde_json::{json, Value};
use std::{collections::BTreeMap, time::Duration};

fn fetch(api: &str, params: Value, fields: &str, token: &str) -> Result<RawResponse> {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(20)))
        .max_redirects(0)
        .http_status_as_error(false)
        .build()
        .into();
    let request = json!({"api_name": api, "token": token, "params": params, "fields": fields});
    let mut response = agent
        .post(ENDPOINT)
        .header("Content-Type", "application/json")
        .send(request.to_string().as_bytes())
        .map_err(|_| "network_timeout_or_tls_error")?;
    let http_status = response.status().as_u16();
    let server_date = response
        .headers()
        .get("date")
        .and_then(|h| h.to_str().ok())
        .map(str::to_owned);
    let body = response
        .body_mut()
        .with_config()
        .limit(1_048_576)
        .read_to_vec()
        .map_err(|_| "response_read_or_size_error")?;
    // Never retain an upstream error page reflecting the secret; do not log error text.
    if body.windows(token.len()).any(|w| w == token.as_bytes())
        || server_date.as_ref().is_some_and(|s| s.contains(token))
    {
        return Err("response_reflected_secret_discarded".into());
    }
    Ok(RawResponse {
        api: api.into(),
        http_status,
        sha256: hash(&body),
        received_at: now(),
        server_date,
        body,
    })
}

fn token() -> Result<String> {
    std::env::var("STRATIDE_TUSHARE_TOKEN")
        .ok()
        .filter(|s| !s.trim().is_empty())
        .ok_or_else(|| "blocked_missing_stratide_tushare_token".into())
}

fn rows(raw: &RawResponse) -> Result<Vec<BTreeMap<String, Value>>> {
    if raw.http_status != 200 {
        return Err(match raw.http_status {
            429 => "rate_limited",
            401 | 403 => "permission_denied",
            _ => "http_error",
        }
        .into());
    }
    let value: Value = serde_json::from_slice(&raw.body).map_err(|_| "invalid_response_json")?;
    match value["code"].as_i64() {
        Some(0) => (),
        Some(2002) => return Err("permission_denied_2002".into()),
        Some(code) => return Err(format!("provider_error_code_{code}")),
        None => return Err("missing_provider_code".into()),
    }
    let fields = value["data"]["fields"].as_array().ok_or("missing_fields")?;
    let names: Vec<String> = fields
        .iter()
        .map(|f| f.as_str().map(str::to_owned).ok_or("invalid_field"))
        .collect::<std::result::Result<_, _>>()?;
    if names
        .iter()
        .collect::<std::collections::BTreeSet<_>>()
        .len()
        != names.len()
    {
        return Err("duplicate_fields".into());
    }
    value["data"]["items"]
        .as_array()
        .ok_or("missing_items")?
        .iter()
        .map(|r| {
            let values = r.as_array().ok_or("invalid_row")?;
            if values.len() != names.len() {
                return Err("field_count_changed".into());
            }
            Ok(names.iter().cloned().zip(values.iter().cloned()).collect())
        })
        .collect()
}

fn text<'a>(row: &'a BTreeMap<String, Value>, key: &str) -> Result<&'a str> {
    row.get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("missing_field_{key}"))
}

/// Lexical base-10 conversion. No floating point, rounding, scientific notation or truncation.
pub(crate) fn scaled(value: &Value, scale: i64) -> Result<i64> {
    let s = match value {
        Value::Number(n) => n.to_string(),
        Value::String(s) => s.clone(),
        _ => return Err("invalid_decimal".into()),
    };
    let mut parts = s.split('.');
    let whole = parts.next().ok_or("invalid_decimal")?;
    let fraction = parts.next().unwrap_or("");
    if parts.next().is_some()
        || whole.is_empty()
        || !whole.bytes().all(|c| c.is_ascii_digit())
        || !fraction.bytes().all(|c| c.is_ascii_digit())
        || fraction.len() > 12
    {
        return Err("unsupported_decimal_precision_or_notation".into());
    }
    let denominator = 10_i128.pow(fraction.len() as u32);
    let whole = whole.parse::<i128>().map_err(|_| "decimal_overflow")?;
    let frac = if fraction.is_empty() {
        0
    } else {
        fraction.parse::<i128>().map_err(|_| "decimal_overflow")?
    };
    let n = whole
        .checked_mul(denominator)
        .and_then(|n| n.checked_add(frac))
        .and_then(|n| n.checked_mul(i128::from(scale)))
        .ok_or("decimal_overflow")?;
    if n % denominator != 0 {
        return Err("sub_fen_or_fractional_share_rejected".into());
    }
    i64::try_from(n / denominator).map_err(|_| "decimal_overflow".into())
}

pub(crate) fn parse_calendar(
    raw: &RawResponse,
    config: &Config,
    from: &str,
    through: &str,
) -> Result<Vec<CalendarDay>> {
    let rows = rows(raw)?;
    let mut calendar = BTreeMap::new();
    for row in rows {
        let day = text(&row, "cal_date")?;
        date(day)?;
        if text(&row, "exchange")? != config.exchange() || day < from || day > through {
            return Err("calendar_identity_mismatch".into());
        }
        let is_open = match row.get("is_open").and_then(Value::as_i64) {
            Some(0) => false,
            Some(1) => true,
            _ => return Err("calendar_status_unknown".into()),
        };
        if calendar
            .insert(
                day.to_string(),
                CalendarDay {
                    day: day.into(),
                    is_open,
                },
            )
            .is_some()
        {
            return Err("duplicate_calendar_day".into());
        }
    }
    let expected = (date(through)? - date(from)?).num_days() + 1;
    if expected < 1 || calendar.len() as i64 != expected {
        return Err("calendar_incomplete".into());
    }
    Ok(calendar.into_values().collect())
}

pub(crate) fn parse_bar(raw: &RawResponse, config: &Config, day: &str) -> Result<Bar> {
    let rows = rows(raw)?;
    if rows.is_empty() {
        return Err("missing_daily_not_proof_of_suspension".into());
    }
    if rows.len() != 1 {
        return Err("unexpected_daily_row_count".into());
    }
    let row = &rows[0];
    if text(row, "ts_code")? != config.instrument || text(row, "trade_date")? != day {
        return Err("daily_identity_mismatch".into());
    }
    let number = |k: &str| scaled(row.get(k).ok_or_else(|| format!("missing_field_{k}"))?, 100);
    let bar = Bar {
        trade_day: day.into(),
        open_fen: number("open")?,
        high_fen: number("high")?,
        low_fen: number("low")?,
        close_fen: number("close")?,
        volume_shares: number("vol")?,
        source_volume_unit: "hand_100_shares".into(),
        price_semantics: "unadjusted_cny_fen".into(),
    };
    if bar.low_fen <= 0
        || bar.high_fen < bar.low_fen
        || bar.open_fen < bar.low_fen
        || bar.open_fen > bar.high_fen
        || bar.close_fen < bar.low_fen
        || bar.close_fen > bar.high_fen
    {
        return Err("invalid_ohlc".into());
    }
    Ok(bar)
}

pub(crate) fn clock_verified(raw: &RawResponse) -> bool {
    raw.server_date
        .as_deref()
        .and_then(|s| DateTime::parse_from_rfc2822(s).ok())
        .is_some_and(|d| (d.timestamp_millis() - raw.received_at).abs() <= 300_000)
}

pub(crate) fn collect(config: &Config, day: &str, from: &str, through: &str) -> Outcome {
    if !config.local_automation_and_raw_storage_authorized {
        return Outcome::gap("blocked_source_license_unverified");
    }
    let token = match token() {
        Ok(t) => t,
        Err(e) => return Outcome::gap(&e),
    };
    let mut outcome = Outcome::gap("collecting");
    let result = (|| -> Result<()> {
        let cal = fetch(
            "trade_cal",
            json!({"exchange": config.exchange(), "start_date": from, "end_date": through}),
            "exchange,cal_date,is_open,pretrade_date",
            &token,
        )?;
        outcome.raw.push(cal);
        outcome.calendar = parse_calendar(&outcome.raw[0], config, from, through)?;
        if !outcome
            .calendar
            .iter()
            .find(|d| d.day == day)
            .ok_or("calendar_missing_target")?
            .is_open
        {
            outcome.status = "market_closed".into();
            return Ok(());
        }
        let local = local_time(now())?;
        let local = DateTime::parse_from_rfc3339(&local).map_err(|_| "clock_error")?;
        if day == through && local.hour() < 16 {
            outcome.status = "not_ready_publication_window".into();
            return Ok(());
        }
        let daily = fetch(
            "daily",
            json!({"ts_code": config.instrument, "trade_date": day}),
            "ts_code,trade_date,open,high,low,close,vol",
            &token,
        )?;
        outcome.raw.push(daily);
        outcome.bar = Some(parse_bar(outcome.raw.last().unwrap(), config, day)?);
        outcome.available_at = outcome.raw.iter().map(|r| r.received_at).max();
        outcome.status = if outcome.raw.iter().all(clock_verified) {
            "valid_eod"
        } else {
            "clock_unverified"
        }
        .into();
        Ok(())
    })();
    if let Err(error) = result {
        outcome.status = error;
        outcome.bar = None;
        outcome.available_at = None;
    }
    outcome
}

#[derive(Serialize)]
pub struct Probe {
    pub api: String,
    pub status: String,
    pub received_at: Option<i64>,
    pub sha256: Option<String>,
    pub rows: Option<usize>,
    pub clock_verified: bool,
    pub raw_retained: bool,
    pub license_verified: bool,
}
/// Owner-triggered minimal access check. Only counts/hashes leave memory; no journal import.
pub fn source_check(config: &Config) -> Result<Vec<Probe>> {
    config.validate()?;
    let token = token()?;
    let day = local_day(now())?;
    let mut probes = vec![];
    for (api, params, fields) in [
        (
            "daily",
            json!({"ts_code": config.instrument, "trade_date": day}),
            "ts_code,trade_date,open,high,low,close,vol",
        ),
        (
            "trade_cal",
            json!({"exchange": config.exchange(), "start_date": day, "end_date": day}),
            "exchange,cal_date,is_open,pretrade_date",
        ),
    ] {
        let mut probe = Probe {
            api: api.into(),
            status: "not_run".into(),
            received_at: None,
            sha256: None,
            rows: None,
            raw_retained: false,
            license_verified: false,
            clock_verified: false,
        };
        match fetch(api, params, fields, &token) {
            Err(e) => probe.status = e,
            Ok(raw) => {
                probe.received_at = Some(raw.received_at);
                probe.sha256 = Some(raw.sha256.clone());
                probe.clock_verified = clock_verified(&raw);
                match rows(&raw) {
                    Ok(rows) => {
                        probe.rows = Some(rows.len());
                        let validation = if api == "daily" {
                            parse_bar(&raw, config, &day).map(|_| ())
                        } else {
                            parse_calendar(&raw, config, &day, &day).map(|_| ())
                        };
                        probe.status = match validation {
                            Ok(()) => "access_ok_not_license_verification".into(),
                            Err(e) => e,
                        };
                    }
                    Err(e) => probe.status = e,
                }
            }
        }
        probes.push(probe);
    }
    Ok(probes)
}
