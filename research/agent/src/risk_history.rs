//! Local-only ex-post input contract. Does not change Frozen/cloud/Paper eligibility.
use crate::{ensure, risk_portfolio as rp, Result};
use chrono::{DateTime, Timelike, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeSet;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct History {
    pub payload_sha256: String,
    pub payload: Value,
}
impl History {
    pub fn validate(&self, f: &rp::Frozen, code_sha256: &str) -> Result<()> {
        let p = &self.payload;
        ensure(
            rp::sha(p) == self.payload_sha256
                && p["frozen_sha256"] == rp::sha(&serde_json::to_value(f).unwrap()),
            "HISTORY_INPUT_SHA",
        )?;
        ensure(
            p["schema_version"] == 1
                && p["adapter_version"] == "historical-timesfm-v1"
                && p["input_mode"] == "historical_research_only"
                && f.input_mode == "historical_research_only"
                && p["historical_pit_status"] == "NOT_VERIFIED"
                && p["coverage"] == "PARTIAL"
                && p["adjustment"] == "unadjusted_no_factor_application"
                && p["cloud_egress"] == "REAL_MARKET_DATA_EGRESS_DENIED"
                && p["horizon"] == 20
                && p["as_of"] == f.as_of
                && f.readiness_ref == "HISTORICAL_PIT_NOT_VERIFIED"
                && f.calendar_provenance == "EX_POST_EXCHANGE_CONTEXT_ORDINAL_HORIZON"
                && f.schema_version == 1
                && f.scope == rp::SCOPE
                && f.policy == rp::POLICY
                && f.prompt_sha256 == rp::prompt_sha()
                && f.adapter_sha256 == rp::adapter_sha()
                && f.account_facts == "UNKNOWN_NO_ACCOUNT_ORDERS",
            "HISTORY_SCOPE_OR_PIT_MISUSE",
        )?;
        // This local adapter has one model and no Fusion/recording/billing path.
        // A recomputed content hash cannot authorize a different identity.
        let unused_sha = "0".repeat(64);
        ensure(
            f.risk_model.id == "local-timesfm-2.5-cpu"
                && f.risk_model.fingerprint == code_sha256
                && rp::valid_sha(&f.risk_model.fingerprint)
                && f.fusion_model.id == "UNUSED_REAL_EGRESS_DENIED"
                && f.fusion_model.fingerprint == unused_sha,
            "HISTORY_MODEL_PIN",
        )?;
        ensure(
            f.prompt_version == rp::PROMPT
                && f.strategy_version == "historical-timesfm-v1"
                && f.batch_budget_micro == 1
                && f.risk_recording_sha256 == unused_sha
                && f.fusion_recording_sha256 == unused_sha,
            "HISTORY_VERSIONS_OR_UNUSED_FIELDS",
        )?;
        let at = f.as_of.parse::<DateTime<Utc>>().map_err(|_| "RISK_AS_OF")?;
        ensure(at <= Utc::now(), "HISTORY_AS_OF")?;
        let shanghai = at.with_timezone(&chrono_tz::Asia::Shanghai);
        ensure(shanghai.hour() >= 16, "HISTORY_CLOSE_NOT_AVAILABLE")?;
        let day = shanghai.date_naive();
        ensure((1..=8).contains(&f.series.len()), "HISTORY_SYMBOL_COUNT")?;
        let raw = p["series"].as_array().ok_or("HISTORY_RAW_SCHEMA")?;
        let quality = p["quality"].as_array().ok_or("HISTORY_QUALITY")?;
        ensure(
            raw.len() == f.series.len() && quality.len() == raw.len(),
            "HISTORY_RAW_SCHEMA",
        )?;
        ensure(
            f.snapshot_ref == rp::sha(&json!({"series":f.series,"calendar":f.calendar})),
            "SNAPSHOT_INPUT_SHA_MISMATCH",
        )?;
        let n = f.series[0].observations.len();
        ensure(
            (84..=192).contains(&n) && f.calendar.len() == n + 20,
            "HISTORY_CONTEXT_BOUNDS",
        )?;
        ensure(
            f.calendar[n..]
                == (1..=20)
                    .map(|i| format!("session+{i:03}"))
                    .collect::<Vec<_>>(),
            "HISTORY_TARGET_AXIS",
        )?;
        let daily_sources = p["sources"]["daily"]
            .as_object()
            .ok_or("HISTORY_DAILY_SOURCE_BINDING")?;
        ensure(
            daily_sources.len() == f.series.len() * n,
            "HISTORY_DAILY_SOURCE_BINDING",
        )?;
        let mut names = BTreeSet::new();
        for ((s, r), q) in f.series.iter().zip(raw).zip(quality) {
            ensure(
                rp::instrument(&s.instrument)
                    && names.insert(&s.instrument)
                    && r["instrument"] == s.instrument
                    && q["instrument"] == s.instrument
                    && q["ratio"] == 1.0
                    && q["status"] == "PARTIAL"
                    && s.corporate_actions == "EX_POST_NO_DETECTED_ACTION_NOT_VERIFIED",
                "HISTORY_IDENTITY_OR_QUALITY",
            )?;
            let rows = r["rows"].as_array().ok_or("HISTORY_RAW_SCHEMA")?;
            let factors = r["factors"].as_array().ok_or("HISTORY_RAW_SCHEMA")?;
            ensure(
                rows.len() == n && s.observations.len() == n && factors.len() == n,
                "HISTORY_CONTEXT_BOUNDS",
            )?;
            for (i, (o, row)) in s.observations.iter().zip(rows).enumerate() {
                let d = crate::parse_day(&o.trade_day)?;
                let received = o
                    .available_at
                    .parse::<DateTime<Utc>>()
                    .map_err(|_| "HISTORY_RECEIVED_TIME")?;
                let values = &row["values"];
                let price = values["close"]
                    .as_str()
                    .and_then(|v| v.parse::<f64>().ok())
                    .ok_or("HISTORY_PRICE_INVALID")?;
                ensure(
                    o.trade_day == f.calendar[i]
                        && d <= day
                        && (i == 0 || f.calendar[i - 1] < o.trade_day)
                        && o.close_fen > 0
                        && o.close_fen <= 1_000_000_000
                        && price.is_finite()
                        && (price * 100.0 - o.close_fen as f64).abs() < 0.000001
                        && values["ts_code"] == s.instrument
                        && values["trade_date"] == d.format("%Y%m%d").to_string()
                        && row["row_sha256"] == rp::sha(values)
                        && row["source_received_at"] == o.available_at
                        && row["available_at"] == o.available_at
                        && row["historical_available_at"].is_null()
                        && received.date_naive() >= d
                        && rp::valid_sha(row["source_sha256"].as_str().unwrap_or(""))
                        && factors[i]["ts_code"] == s.instrument
                        && factors[i]["trade_date"] == values["trade_date"]
                        && factors[i]["adj_factor"] == factors[0]["adj_factor"],
                    "HISTORY_ROW_BINDING_OR_FUTURE",
                )?;
                let key = format!("{}:{}", s.instrument, d.format("%Y%m%d"));
                let source_sha = daily_sources
                    .get(&key)
                    .and_then(Value::as_str)
                    .ok_or("HISTORY_DAILY_SOURCE_BINDING")?;
                ensure(
                    row["source_sha256"] == source_sha,
                    "HISTORY_DAILY_SOURCE_BINDING",
                )?;
                let source = p["sources"]["daily_manifests"]
                    .get(source_sha)
                    .ok_or("HISTORY_DAILY_SOURCE_BINDING")?;
                let attempts = source["attempts"]
                    .as_array()
                    .ok_or("HISTORY_DAILY_SOURCE_BINDING")?;
                ensure(
                    rp::sha(source) == row["source_sha256"]
                        && !attempts.is_empty()
                        && attempts.iter().all(|a| {
                            rp::valid_sha(a["metadata_sha"].as_str().unwrap_or(""))
                                && rp::valid_sha(a["response_sha"].as_str().unwrap_or(""))
                        })
                        && attempts
                            .iter()
                            .filter_map(|a| a["obtained_at"].as_str())
                            .max()
                            == Some(o.available_at.as_str()),
                    "HISTORY_DAILY_SOURCE_BINDING",
                )?;
            }
            ensure(
                s.observations.last().unwrap().trade_day == day.to_string()
                    && p["context_cutoff"] == day.to_string()
                    && p["context_start"] == s.observations[0].trade_day
                    && s.observations.windows(2).all(|o| {
                        (o[1].close_fen as f64 / o[0].close_fen as f64 - 1.).abs() <= 0.35
                    }),
                "HISTORY_CUTOFF_OR_ACTION_GAP",
            )?;
        }
        ensure(
            f.opportunities.len() == names.len(),
            "HISTORY_OPPORTUNITIES",
        )?;
        let mut opportunities = BTreeSet::new();
        for o in &f.opportunities {
            ensure(
                names.contains(&o.instrument)
                    && opportunities.insert(&o.instrument)
                    && o.status == "UNKNOWN"
                    && o.evidence.is_empty(),
                "HISTORY_OPPORTUNITIES",
            )?;
        }
        Ok(())
    }
}
