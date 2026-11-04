//! Versioned role and narrow evidence allowlist; preserves TargetPortfolioProposal V1.
use crate::{ensure, hash, risk_portfolio as rp, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

pub const VERSION: &str = "FusionResearcherV1";
pub const CONTRACT: &str = "controlled-conclusions-v2";
pub const SYSTEM: &str = include_str!("../prompts/fusion-researcher-v1-system.txt");
pub const DEVELOPER: &str = include_str!("../prompts/fusion-researcher-v1-developer.txt");
pub const LIMITATIONS: [&str; 5] = [
    "SYNTHETIC_ONLY",
    "PIT_NOT_VERIFIED",
    "RETURN_DIRECTION_UNKNOWN",
    "ACCOUNT_UNKNOWN",
    "UNCALIBRATED",
];

pub fn instructions() -> String {
    // DeepSeek's existing Chat Completions path uses a system role. Both static
    // high-priority templates are combined here, never appended to user evidence.
    format!("{SYSTEM}\nDeveloper contract:\n{DEVELOPER}")
}
pub fn prompt_sha() -> String {
    hash(instructions().as_bytes())
}
// Frozen PR78 R1 templates are used only to reconstruct historical requests.
pub fn legacy_instructions() -> String {
    format!(
        "{}\nDeveloper contract:\n{}",
        include_str!("../prompts/fusion-researcher-v1-legacy-system.txt"),
        include_str!("../prompts/fusion-researcher-v1-legacy-developer.txt")
    )
}
pub fn legacy_prompt_sha() -> String {
    hash(legacy_instructions().as_bytes())
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Hypothesis {
    pub classification: String,
    pub text: String,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Response {
    pub portfolio: rp::Portfolio,
    pub conclusions: Value,
    pub untrusted_hypothesis: Hypothesis,
}
pub fn conclusions(refs: &[String]) -> Value {
    json!({"contract":CONTRACT,"source_refs":refs,"evidence_scope":"SYNTHETIC_ONLY",
        "historical_pit_status":"NOT_VERIFIED","return_direction":"UNKNOWN",
        "return_guarantee":"NOT_ESTABLISHED","confidence":"UNCALIBRATED",
        "account_facts":"UNKNOWN","budget_authority":"NONE","order_authority":"NONE",
        "qualification":"ELIGIBILITY_DENIED"})
}
pub fn controlled_text() -> Value {
    json!({"strategy_definition":"SYNTHETIC_RMS_RESEARCH_HYPOTHESIS",
        "rationale":"NO_VERIFIED_RETURN_OR_ACCOUNT_EVIDENCE",
        "evidence_for":["SYNTHETIC_RISK_EVIDENCE_ONLY"],
        "evidence_against":["NO_RETURN_EVIDENCE"],"risk_assessment":["UNCALIBRATED_RISK"],
        "invalidation_conditions":["INDEPENDENT_EVIDENCE_REQUIRED"],
        "next_experiment":["LOCAL_INDEPENDENT_REVIEW_REQUIRED"],"limitations":LIMITATIONS})
}
pub fn validate_response(r: &Response) -> Result<()> {
    validate_portfolio(&r.portfolio)?;
    ensure(
        r.conclusions == conclusions(&r.portfolio.source_refs),
        "FUSION_CONCLUSION_STATE_OR_SOURCE",
    )?;
    ensure(
        r.untrusted_hypothesis.classification == "UNTRUSTED_HYPOTHESIS"
            && rp::text(&r.untrusted_hypothesis.text, 4000),
        "FUSION_HYPOTHESIS_CLASSIFICATION",
    )
}
pub fn descriptor() -> Value {
    json!({"version":VERSION,"prompt_sha256":prompt_sha(),"system":SYSTEM,"developer":DEVELOPER,
        "input_schema":{"mode":"SYNTHETIC_ENGINEERING_ONLY","target":"rolling20_rms_daily_return_ratio",
            "allowed_fields":["synthetic_risk_summary","source_refs","opportunity","account","output_contract","positions_contract","researcher_contract"],
            "untrusted_text":"REJECTED_BEFORE_PROVIDER_DISPATCH"},
        "output_schema":{"contract":CONTRACT,"portfolio":"TargetPortfolioProposal V1",
            "controlled_text":controlled_text(),"conclusions":conclusions(&[]),
            "untrusted_hypothesis":{"classification":"UNTRUSTED_HYPOTHESIS","text":"quarantined; never evidence or authority"}},
        "authority":"RESEARCH_ONLY",
        "real_data_egress":"REAL_MARKET_DATA_EGRESS_DENIED","billable_calls":0})
}

pub fn validate_evidence(f: &rp::Frozen, experts: &[Value]) -> Result<()> {
    ensure(
        f.input_mode == "synthetic_test" && f.account_facts == "UNKNOWN_NO_ACCOUNT_ORDERS",
        "REAL_MARKET_DATA_EGRESS_DENIED",
    )?;
    ensure(experts.len() == f.series.len(), "FUSION_EVIDENCE_BINDING")?;
    for (expert, series) in experts.iter().zip(&f.series) {
        ensure(
            expert["input_mode"] == "synthetic_test"
                && expert["instrument"] == series.instrument
                && expert["snapshot_ref"] == f.snapshot_ref
                && expert["as_of"] == f.as_of
                && expert["target"] == "rolling20_rms_daily_return_ratio"
                && expert["unit"] == "daily_return_ratio"
                && expert["uncertainty"] == "UNKNOWN_UNCALIBRATED"
                && expert["covariance"] == "UNKNOWN_INSUFFICIENT_EVIDENCE"
                && expert["downside_metric"] == "UNKNOWN_UNCALIBRATED"
                && expert["quality_blockers"] == json!(["SYNTHETIC_ENGINEERING_ONLY"])
                && matches!(
                    expert["market_regime"].as_str(),
                    Some("HIGH_VOLATILITY" | "NORMAL_VOLATILITY")
                ),
            "FUSION_UNTRUSTED_EVIDENCE",
        )?;
        let forecasts = expert["volatility_forecast"]
            .as_array()
            .ok_or("FUSION_EVIDENCE_SCHEMA")?;
        ensure(forecasts.len() == 2, "FUSION_EVIDENCE_SCHEMA")?;
        for (forecast, horizon) in forecasts.iter().zip([5, 20]) {
            ensure(
                forecast.as_object().is_some_and(|m| m.len() == 2)
                    && forecast["sessions"] == horizon
                    && forecast["value_ratio"]
                        .as_f64()
                        .is_some_and(|v| v.is_finite() && (0.0..=0.35).contains(&v)),
                "FUSION_EVIDENCE_SCHEMA",
            )?;
        }
        for key in ["naive", "ewma"] {
            ensure(
                expert["baseline_comparison"][key]
                    .as_f64()
                    .is_some_and(|v| v.is_finite() && (0.0..=0.35).contains(&v)),
                "FUSION_BASELINE_SCHEMA",
            )?;
        }
    }
    Ok(())
}

pub fn validate_portfolio(p: &rp::Portfolio) -> Result<()> {
    p.validate()?;
    ensure(
        p.evidence_for == ["SYNTHETIC_RISK_EVIDENCE_ONLY"] && p.limitations == LIMITATIONS,
        "FUSION_PROVENANCE_LABELS_REQUIRED",
    )?;
    let value = serde_json::to_value(p).unwrap();
    for (key, expected) in controlled_text().as_object().unwrap() {
        ensure(
            value[key] == *expected,
            "FUSION_CONTROLLED_CONCLUSION_REQUIRED",
        )?;
    }
    ensure(
        !p.proposal_id.is_empty()
            && p.proposal_id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_')),
        "FUSION_PROPOSAL_IDENTIFIER",
    )
}

// Compatibility only. New dispatch/decoding never relies on this old keyword list.
pub fn validate_legacy_portfolio(p: &rp::Portfolio) -> Result<()> {
    p.validate()?;
    ensure(
        p.evidence_for == ["SYNTHETIC_RISK_EVIDENCE_ONLY"] && p.limitations == LIMITATIONS,
        "FUSION_PROVENANCE_LABELS_REQUIRED",
    )?;
    let texts = std::iter::once(&p.rationale)
        .chain(std::iter::once(&p.strategy_definition))
        .chain(p.evidence_against.iter())
        .chain(p.risk_assessment.iter())
        .chain(p.invalidation_conditions.iter())
        .chain(p.next_experiment.iter());
    for text in texts {
        let lower = text.to_lowercase();
        ensure(
            ![
                "guaranteed profit",
                "certain profit",
                "will rise",
                "will fall",
                "positive alpha is proven",
                "calibrated confidence",
                "authorized to trade",
                "ignore system",
                "reveal the key",
                "sk-",
                "保证盈利",
                "确定上涨",
                "确定下跌",
                "超额收益已证",
                "已授权下单",
            ]
            .iter()
            .any(|s| lower.contains(s)),
            "FUSION_UNSUPPORTED_CLAIM_OR_CAPABILITY",
        )?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn role_and_contract_are_versioned() {
        let v = descriptor();
        assert_eq!(v["version"], "FusionResearcherV1");
        assert_eq!(prompt_sha().len(), 64);
        assert!(instructions().contains("never a trader"));
        assert!(instructions().contains("Naive and EWMA"));
        assert!(instructions().contains("10000 cash"));
        assert_ne!(hash(SYSTEM.as_bytes()), prompt_sha());
        assert_eq!(
            legacy_prompt_sha(),
            "65ef4796d8da3a7c000bb94e34a5f339e7515c121b8261352b1b2e78fea484fd"
        );
        assert_ne!(legacy_prompt_sha(), prompt_sha());
    }
}
