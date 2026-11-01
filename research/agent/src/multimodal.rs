//! Restricted V1 fusion contracts. No external time-series or cloud permission.
use crate::{ensure, hash, InputSummary, Result};
use chrono::{DateTime, Utc};
use rusqlite::{Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};

pub const SCOPE: &str = "multimodal_research_v1";
pub const POLICY: &str = "multimodal-research-v1";

pub fn state_root() -> Result<PathBuf> {
    // Same canonical Git authority used by the existing Shadow module. All
    // names/worktrees use one original Agent budget database, never one/name.
    let output = Command::new("git")
        .args(["rev-parse", "--path-format=absolute", "--git-common-dir"])
        .current_dir(crate::eod_snapshot::repository_root())
        .output()
        .map_err(|_| "MULTIMODAL_ROOT_UNAVAILABLE")?;
    ensure(output.status.success(), "MULTIMODAL_ROOT_UNAVAILABLE")?;
    let path = PathBuf::from(
        String::from_utf8(output.stdout)
            .map_err(|_| "MULTIMODAL_ROOT_UNAVAILABLE")?
            .trim(),
    );
    Ok(path
        .parent()
        .ok_or("MULTIMODAL_ROOT_UNAVAILABLE")?
        .join("state/multimodal"))
}

pub fn is_input(input: &InputSummary) -> bool {
    input.scopes.iter().any(|s| s == SCOPE)
}

/// Recheck the ACTUAL claimed task at the original reserve/dispatch boundary,
/// including when it was claimed by the legacy global Agent tick path.
pub fn validate_source(
    c: &Connection,
    trigger: Option<&str>,
    input: &InputSummary,
    now: DateTime<Utc>,
) -> Result<()> {
    let summary = validate_input(input, now)?;
    let key = trigger
        .and_then(|t| t.strip_prefix("multimodal-v1:"))
        .ok_or("MULTIMODAL_TRIGGER_INVALID")?;
    let (name, task_key) = key.split_once(':').ok_or("MULTIMODAL_TRIGGER_INVALID")?;
    ensure(
        crate::eod_snapshot::valid_name(name) && task_key == summary.task_id,
        "MULTIMODAL_TRIGGER_INVALID",
    )?;
    require_enabled(c, trigger)?;
    let path = state_root()?.join(name).join("config.json");
    crate::eod_snapshot::no_links(&path)?;
    ensure(
        fs::metadata(&path).is_ok_and(|m| m.is_file() && m.len() <= 8192),
        "MULTIMODAL_CONFIG",
    )?;
    let mut config: Value =
        serde_json::from_slice(&fs::read(&path).map_err(|_| "MULTIMODAL_CONFIG")?)
            .map_err(|_| "MULTIMODAL_CONFIG")?;
    let binding = config["binding_sha256"]
        .as_str()
        .ok_or("MULTIMODAL_CONFIG")?
        .to_string();
    config
        .as_object_mut()
        .ok_or("MULTIMODAL_CONFIG")?
        .remove("binding_sha256");
    ensure(
        hash(&serde_json::to_vec(&config).map_err(|_| "MULTIMODAL_CONFIG")?) == binding
            && config["schema_version"] == 1
            && config["policy"] == POLICY
            && config["name"] == name
            && config["agent_dir"] == ".agent"
            && config["source_identity_sha256"] == summary.source_identity
            && config["checkout_root"]
                == crate::eod_snapshot::repository_root()
                    .to_string_lossy()
                    .as_ref(),
        "MULTIMODAL_BINDING_CHANGED",
    )?;
    for (key, expected) in [
        (format!("mm_binding:{name}"), binding),
        (
            format!("mm_source_owner:{}", summary.source_identity),
            name.to_string(),
        ),
        (
            format!("mm_task_owner:{}", summary.task_id),
            name.to_string(),
        ),
    ] {
        let value: Option<String> = c
            .query_row("SELECT value FROM meta WHERE key=?1", [key], |r| r.get(0))
            .optional()?;
        ensure(
            value.as_deref() == Some(expected.as_str()),
            "MULTIMODAL_BINDING_CHANGED",
        )?;
    }
    let source = crate::eod_snapshot::SnapshotSource::named(
        config["snapshot_store_name"]
            .as_str()
            .ok_or("MULTIMODAL_CONFIG")?,
    )?;
    let (current, identity) = source.read_with_identity(now.timestamp_millis())?;
    ensure(
        hash(&serde_json::to_vec(&identity).map_err(|_| "MULTIMODAL_SOURCE_IDENTITY_CHANGED")?)
            == summary.source_identity,
        "MULTIMODAL_SOURCE_IDENTITY_CHANGED",
    )?;
    ensure(
        current.summary["snapshot_sha256"] == summary.input_snapshot_sha256
            && current.source_day == input.source_day
            && current.mode == input.mode,
        "MULTIMODAL_SNAPSHOT_CHANGED",
    )?;
    let market = now.with_timezone(&chrono_tz::Asia::Shanghai);
    ensure(
        chrono::Timelike::hour(&market) >= 16
            && market.format("%Y%m%d").to_string() == summary.source_day,
        "MISSED_OR_STALE",
    )?;
    for field in ["observed_at", "received_at", "available_at"] {
        let time = DateTime::from_timestamp_millis(
            current.summary[field]
                .as_i64()
                .ok_or("SNAPSHOT_TIME_INVALID")?,
        )
        .ok_or("SNAPSHOT_TIME_INVALID")?
        .with_timezone(&chrono_tz::Asia::Shanghai);
        ensure(
            time.date_naive() == market.date_naive() && chrono::Timelike::hour(&time) >= 16,
            "MISSED_OR_STALE",
        )?;
    }
    if let Some(receipt) = &summary.research_readiness_receipt {
        ensure(
            config["readiness_store_name"] == receipt.store_name,
            "MULTIMODAL_READINESS_BINDING",
        )?;
        // Fixed read-only verifier, no caller-selected program/path or shell.
        // Python replays the receipt, retained per-day PR33 versions and raw
        // original journal. Rust supplies THIS persisted task and its clock at
        // BOTH existing reserve and dispatch checks. No new Provider scope.
        let mut child = Command::new("python")
            .args(["-I", "-B"])
            .arg(
                crate::eod_snapshot::repository_root()
                    .join("scripts/forward-research-readiness.py"),
            )
            .arg("gate")
            .current_dir(crate::eod_snapshot::repository_root())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| "MULTIMODAL_READINESS_VERIFIER_UNAVAILABLE")?;
        let bytes = serde_json::to_vec(&json!({
            "reference": receipt, "now_ms": now.timestamp_millis(),
            "input_snapshot_sha256":summary.input_snapshot_sha256,
            "source_identity_sha256":summary.source_identity,
            "source_day":summary.source_day,"input_mode":input.mode
        }))
        .map_err(|_| "MULTIMODAL_READINESS_BINDING")?;
        let sent = child
            .stdin
            .take()
            .is_some_and(|mut stdin| stdin.write_all(&bytes).is_ok());
        let output = child
            .wait_with_output()
            .map_err(|_| "MULTIMODAL_READINESS_VERIFIER_UNAVAILABLE")?;
        let checked: Value = serde_json::from_slice(&output.stdout).unwrap_or(Value::Null);
        ensure(
            sent && output.status.success()
                && checked
                    == json!({"verified":true,"contract":receipt.contract,
                    "store_name":receipt.store_name,"receipt_sha256":receipt.receipt_sha256,
                    "evidence_head_sha256":receipt.evidence_head_sha256}),
            "MULTIMODAL_READINESS_REJECTED",
        )?;
    }
    Ok(())
}

fn sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn utc(value: &str) -> Result<DateTime<Utc>> {
    let time = DateTime::parse_from_rfc3339(value).map_err(|_| "EXPERT_TIMEZONE_INVALID")?;
    ensure(
        value.ends_with('Z') && value.len() == 24 && time.offset().local_minus_utc() == 0,
        "EXPERT_TIMEZONE_INVALID",
    )?;
    Ok(time.with_timezone(&Utc))
}

#[derive(Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Authority {
    pub restriction: String,
    pub eligibility: String,
    pub can_execute_forward_paper: bool,
    pub live_allowed: bool,
}
impl Authority {
    fn validate(&self) -> Result<()> {
        ensure(
            self.restriction == "RESEARCH_ONLY"
                && self.eligibility == "ELIGIBILITY_DENIED"
                && !self.can_execute_forward_paper
                && !self.live_allowed,
            "EXPERT_AUTHORITY_INVALID",
        )
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Metrics {
    expected_return_ratio: String,
    volatility_ratio: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    ewma_mean_ratio: Option<String>,
}
impl Metrics {
    fn validate(&self) -> Result<()> {
        for value in [&self.expected_return_ratio, &self.volatility_ratio]
            .into_iter()
            .chain(self.ewma_mean_ratio.as_ref())
        {
            let n = value.parse::<f64>().map_err(|_| "EXPERT_NUMBER_INVALID")?;
            ensure(
                !value.is_empty()
                    && value.len() <= 32
                    && n.is_finite()
                    && (-1.0..=1.0).contains(&n)
                    && value
                        .bytes()
                        .all(|c| c.is_ascii_digit() || c == b'-' || c == b'.'),
                "EXPERT_NUMBER_BOUND",
            )?;
        }
        ensure(
            self.volatility_ratio.parse::<f64>().is_ok_and(|n| n >= 0.0),
            "EXPERT_NUMBER_BOUND",
        )
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TrainingRange {
    first_day: String,
    last_day: String,
    samples: u32,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LocalCost {
    billing: String,
    elapsed_ms: u64,
    input_tokens: Option<u64>,
    output_tokens: Option<u64>,
    cloud_cost: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExpertResult {
    schema_version: u32,
    contract: String,
    expert_kind: String,
    model_id: String,
    model_version: String,
    role: String,
    task_id: String,
    input_mode: String,
    instrument: String,
    target: String,
    horizon_sessions: u32,
    input_snapshot_sha256: String,
    source_identity: String,
    as_of: String,
    observed_at: String,
    generated_at: String,
    training_range: TrainingRange,
    units: String,
    missing_policy: String,
    result: Metrics,
    output_sha256: String,
    uncertainty: String,
    evidence_refs: Vec<String>,
    quality: String,
    limitations: Vec<String>,
    cost: LocalCost,
    authority: Authority,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FusionInput {
    contract: String,
    pub task_id: String,
    pub input_snapshot_sha256: String,
    pub source_identity: String,
    pub source_day: String,
    instrument: String,
    target: String,
    horizon_sessions: u32,
    as_of: String,
    baseline: ExpertResult,
    time_series: ExpertResult,
    conflict: String,
    quality_blockers: Vec<String>,
    uncertainty: String,
    tradable_at: String,
    authority: Authority,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    research_readiness_receipt: Option<ReadinessReference>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadinessReference {
    contract: String,
    store_name: String,
    receipt_sha256: String,
    evidence_head_sha256: String,
}

pub fn validate_input(input: &InputSummary, now: DateTime<Utc>) -> Result<FusionInput> {
    ensure(
        input.scopes == ["owner_task", SCOPE]
            && !input.eod_eligible
            && matches!(
                input.mode.as_str(),
                "synthetic_test" | "forward_observed_eod"
            ),
        "MULTIMODAL_INPUT_CONTRACT",
    )?;
    let bytes = serde_json::to_vec(&input.summary).map_err(|_| "MULTIMODAL_INPUT_CONTRACT")?;
    ensure(
        bytes.len() <= 20000 && input.version == format!("{SCOPE}:{}", hash(&bytes)),
        "MULTIMODAL_INPUT_SHA",
    )?;
    let s: FusionInput = serde_json::from_slice(&bytes).map_err(|_| "MULTIMODAL_INPUT_SCHEMA")?;
    ensure(
        input.mode != "forward_observed_eod" || s.research_readiness_receipt.is_some(),
        "CORPORATE_ACTION_PIT_NOT_VERIFIED",
    )?;
    if let Some(receipt) = &s.research_readiness_receipt {
        ensure(
            receipt.contract == "forward-research-readiness-v1"
                && crate::eod_snapshot::valid_name(&receipt.store_name)
                && sha(&receipt.receipt_sha256)
                && sha(&receipt.evidence_head_sha256),
            "MULTIMODAL_READINESS_BINDING",
        )?;
    }
    s.authority.validate()?;
    ensure(
        s.contract == SCOPE
            && sha(&s.task_id)
            && sha(&s.input_snapshot_sha256)
            && sha(&s.source_identity)
            && s.instrument == "600000.SH"
            && s.target == "next_session_return_ratio"
            && s.horizon_sessions == 1
            && s.source_day == input.source_day.replace('-', "")
            && s.uncertainty == "UNKNOWN_UNCALIBRATED"
            && s.tradable_at == "UNKNOWN_OPENING_SOURCE_BLOCKED"
            && s.quality_blockers
                == [
                    "EXTERNAL_TIMESERIES_NOT_CONFIGURED",
                    "CORPORATE_ACTION_PIT_NOT_VERIFIED",
                    "OPENING_SOURCE_BLOCKED",
                ],
        "MULTIMODAL_INPUT_CONTRACT",
    )?;
    let asof = utc(&s.as_of)?;
    ensure(asof <= now, "EXPERT_FUTURE_TIME")?;
    for (kind, r) in [("baseline", &s.baseline), ("time_series", &s.time_series)] {
        r.authority.validate()?;
        r.result.validate()?;
        ensure(
            r.schema_version == 1
                && r.contract == "expert-result-v1"
                && r.expert_kind == kind
                && r.task_id == s.task_id
                && r.input_mode == input.mode
                && r.instrument == s.instrument
                && r.target == s.target
                && r.horizon_sessions == 1
                && r.input_snapshot_sha256 == s.input_snapshot_sha256
                && r.source_identity == s.source_identity
                && r.as_of == s.as_of
                && r.authority == s.authority
                && utc(&r.observed_at)? <= asof
                && asof <= utc(&r.generated_at)?
                && utc(&r.generated_at)? <= now
                && r.units == "ratio_per_exchange_session"
                && r.missing_policy == "REJECT_NO_IMPUTATION"
                && r.uncertainty == "UNKNOWN_UNCALIBRATED"
                && r.training_range.samples == 21
                && r.training_range.first_day.len() == 8
                && r.training_range.last_day == s.source_day
                && r.training_range.first_day < r.training_range.last_day
                && r.evidence_refs.len() == 2
                && r.evidence_refs[0] == s.input_snapshot_sha256
                && r.evidence_refs.iter().all(|v| sha(v))
                && r.output_sha256
                    == hash(
                        &serde_json::to_vec(
                            &serde_json::to_value(&r.result)
                                .map_err(|_| "EXPERT_RESULT_INVALID")?,
                        )
                        .map_err(|_| "EXPERT_RESULT_INVALID")?,
                    )
                && r.limitations
                    == [
                        "EXTERNAL_TIMESERIES_NOT_CONFIGURED",
                        "NO_CALIBRATED_PROBABILITY",
                        "CORPORATE_ACTION_PIT_NOT_VERIFIED",
                        "OPENING_SOURCE_BLOCKED",
                    ]
                && r.cost.billing == "LOCAL_NO_BILLING"
                && r.cost.elapsed_ms <= 60000
                && r.cost.input_tokens.is_none()
                && r.cost.output_tokens.is_none()
                && r.cost.cloud_cost == "UNKNOWN_NOT_BILLED",
            "EXPERT_IDENTITY_OR_AUTHORITY",
        )?;
        ensure(
            if kind == "baseline" {
                r.model_id == "naive-ewma"
                    && r.model_version == "1"
                    && r.role == "comparator"
                    && r.quality == "DETERMINISTIC_BASELINE"
                    && r.result.ewma_mean_ratio.is_some()
            } else {
                matches!(
                    r.model_id.as_str(),
                    "local-test-shrinkage" | "local-test-momentum"
                ) && r.model_version == "1"
                    && r.role == "temporal_evidence"
                    && r.quality == "LOCAL_TEST_EXPERT"
                    && r.result.ewma_mean_ratio.is_none()
            },
            "EXPERT_MODEL_NOT_CONFIGURED",
        )?;
    }
    let differs =
        s.baseline.result.expected_return_ratio != s.time_series.result.expected_return_ratio;
    ensure(
        s.conflict
            == if differs {
                "DIRECTION_DIFFERS_FROM_NAIVE"
            } else {
                "NO_NUMERIC_DISAGREEMENT"
            },
        "EXPERT_CONFLICT_INVALID",
    )?;
    Ok(s)
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Fusion {
    pub hypothesis: String,
    pub evidence_for: Vec<String>,
    pub evidence_against: Vec<String>,
    pub risks: Vec<String>,
    pub falsification: Vec<String>,
    pub next_experiment: Vec<String>,
    pub limitations: Vec<String>,
}

impl Fusion {
    pub fn validate(&self) -> Result<()> {
        let lists = [
            &self.evidence_for,
            &self.evidence_against,
            &self.risks,
            &self.falsification,
            &self.next_experiment,
            &self.limitations,
        ];
        ensure(
            !self.hypothesis.trim().is_empty()
                && self.hypothesis.len() <= 2048
                && lists.iter().all(|v| {
                    !v.is_empty()
                        && v.len() <= 6
                        && v.iter().all(|s| !s.trim().is_empty() && s.len() <= 1024)
                })
                && serde_json::to_vec(self).is_ok_and(|v| v.len() <= 12000),
            "FUSION_OUTPUT_INVALID",
        )?;
        for text in std::iter::once(&self.hypothesis).chain(lists.into_iter().flatten()) {
            let text = text.to_ascii_lowercase();
            ensure(
                ![
                    "http:",
                    "https:",
                    "file:",
                    ":\\",
                    "\\\\",
                    "$(",
                    "`",
                    "<script",
                    "<img",
                    "powershell",
                    "cmd.exe",
                    "python ",
                    "bash ",
                    "sh -",
                    "#!/",
                    "/etc/",
                    "/tmp/",
                    "../",
                    "rm ",
                    "curl ",
                    "wget ",
                    "invoke-expression",
                ]
                .iter()
                .any(|s| text.contains(s))
                    && !text.split_whitespace().any(|s| s.starts_with('/'))
                    && !text.chars().any(|c| c.is_control()),
                "FUSION_COMMAND_OR_URL_REJECTED",
            )?;
        }
        Ok(())
    }
    pub fn fixture(input: &Value) -> Result<Self> {
        let summary: InputSummary = serde_json::from_value(input["published_summary"].clone())
            .map_err(|_| "MULTIMODAL_INPUT_SCHEMA")?;
        let s: FusionInput =
            serde_json::from_value(summary.summary).map_err(|_| "MULTIMODAL_INPUT_SCHEMA")?;
        Ok(Self {
            hypothesis: format!("本地 fake 可证伪假设：该窗口的 {} 时序统计偏移可在后续合成前缀中比较，不能据此认定 alpha。", s.time_series.model_id),
            evidence_for: vec![format!("时序下一会话收益比例 {}；Naive 比例 {}；源 SHA {}。", s.time_series.result.expected_return_ratio, s.baseline.result.expected_return_ratio, s.input_snapshot_sha256)],
            evidence_against: vec![format!("{}；统计差异未通过独立时间隔离验证。", s.conflict)],
            risks: vec!["波动估计有样本误差；公司行为 PIT 与实际开盘未验证。".into()],
            falsification: vec!["冻结后续合成标签，若时序误差不低于 Naive 则否定比较假设。".into()],
            next_experiment: vec!["按时间正序前缀比较绝对误差并记录拒答率；由 Owner 审阅。".into()],
            limitations: vec!["LOCAL_TEST_EXPERT 与原 Agent fake，UNKNOWN_UNCALIBRATED；文本不计价格预测正确率。".into()],
        })
    }
}

/// Called inside the original create/dispatch transactions, so Owner disable
/// cannot slip between the last check and a newly committed send boundary.
pub fn require_enabled(c: &Connection, trigger: Option<&str>) -> Result<()> {
    if let Some(key) = trigger.and_then(|t| t.strip_prefix("multimodal-v1:")) {
        let name = key.split(':').next().ok_or("MULTIMODAL_TRIGGER_INVALID")?;
        ensure(
            crate::eod_snapshot::valid_name(name),
            "MULTIMODAL_TRIGGER_INVALID",
        )?;
        let enabled: Option<String> = c
            .query_row(
                "SELECT value FROM meta WHERE key=?1",
                [format!("mm_enabled:{name}")],
                |r| r.get(0),
            )
            .optional()?;
        ensure(enabled.as_deref() == Some("true"), "OWNER_DISABLED")?;
    }
    Ok(())
}

pub fn public_contract() -> Value {
    json!({"scope":SCOPE,"mode":"LOCAL_FAKE_ONLY","external_timeseries":"EXTERNAL_TIMESERIES_NOT_CONFIGURED","public_requests":0})
}

#[cfg(test)]
mod tests {
    use super::*;

    fn good() -> Value {
        json!({"hypothesis":"可证伪的合成研究假设", "evidence_for":["已核验数值证据"],
            "evidence_against":["与 Naive 的差异未经独立验证"], "risks":["样本有限"],
            "falsification":["后续前缀误差不低于 Naive 则否定"],
            "next_experiment":["保留后续合成标签"], "limitations":["UNKNOWN_UNCALIBRATED"]})
    }

    #[test]
    fn fusion_strict_schema_rejects_authority_finance_and_tools() {
        for key in [
            "authority",
            "command",
            "script",
            "url",
            "budget",
            "positions",
            "risk_limit",
            "calibrated_interval",
        ] {
            let mut value = good();
            value[key] = json!("TRADE");
            assert!(serde_json::from_value::<Fusion>(value).is_err(), "{key}");
        }
        serde_json::from_value::<Fusion>(good())
            .unwrap()
            .validate()
            .unwrap();
    }

    #[test]
    fn fusion_rejects_paths_commands_urls_oversize_and_missing_fields() {
        for text in [
            "https://provider.example.com/x",
            "C:\\secrets",
            "/tmp/secrets",
            "$(Get-Content secrets)",
            "<script>alert(1)</script>",
        ] {
            let mut value = good();
            value["hypothesis"] = json!(text);
            assert_eq!(
                serde_json::from_value::<Fusion>(value)
                    .unwrap()
                    .validate()
                    .unwrap_err()
                    .0,
                "FUSION_COMMAND_OR_URL_REJECTED"
            );
        }
        let mut value = good();
        value["hypothesis"] = json!("x".repeat(20000));
        assert!(serde_json::from_value::<Fusion>(value)
            .unwrap()
            .validate()
            .is_err());
        let mut value = good();
        value.as_object_mut().unwrap().remove("falsification");
        assert!(serde_json::from_value::<Fusion>(value).is_err());
    }

    #[test]
    fn expert_numbers_and_timezone_are_bounded() {
        for value in ["NaN", "inf", "2", "-2", "$(cmd)"] {
            assert!(Metrics {
                expected_return_ratio: value.into(),
                volatility_ratio: "0.01".into(),
                ewma_mean_ratio: None
            }
            .validate()
            .is_err());
        }
        for time in [
            "2026-11-01T17:00:00",
            "2026-11-01T17:00:00+08:00",
            "2026-13-01T17:00:00.000Z",
        ] {
            assert!(utc(time).is_err());
        }
        assert!(utc("2026-11-01T09:00:00.000Z").is_ok());
    }
}
