use serde_json::Value;
use std::path::PathBuf;
use stratided::App;

#[test]
fn cloud_summary_is_a_versioned_projection_without_account_identity_cash_or_private_strategy_payloads(
) {
    let report =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../docs/evidence/m0-pr03/sample-report");
    let summary = App::load(Some(&report), None).agent_summary();
    assert_eq!(summary.mode, "synthetic_test");
    assert!(!summary.eod_eligible);
    assert!(summary.version.starts_with("paper-summary-v1:"));
    assert_eq!(summary.summary["simulated_fills"], "2");
    for field in [
        "account_id",
        "cash_fen",
        "positions",
        "lots",
        "orders",
        "fills",
        "group_id",
        "strategy_id",
        "events",
        "risk",
        "api_key",
        "holdout_answers",
    ] {
        assert_eq!(
            summary.summary.get(field),
            None,
            "field must not enter cloud context: {field}"
        );
    }
    assert_eq!(
        summary.summary["mode"],
        Value::String("synthetic_test".into())
    );
    assert_eq!(
        App::load(None, None).agent_summary().scopes,
        vec!["owner_task"]
    );
}
