use std::{fs, process::Command};

fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_stratide-cli"))
        .args(args)
        .env_remove("STRATIDE_TUSHARE_TOKEN")
        .output()
        .unwrap()
}
#[test]
fn real_cli_process_restart_blocked_attempts_and_report_no_money_mutation() {
    let temp = tempfile::tempdir().unwrap();
    let journal = temp.path().join("observer");
    let report = temp.path().join("report");
    let config = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../samples/m1-pr04a-observer.json");
    let dir = journal.to_str().unwrap();
    let rpt = report.to_str().unwrap();
    assert!(cli(&["forward-init", dir, config.to_str().unwrap()])
        .status
        .success());
    let out = cli(&["forward-collect-once", dir]);
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stdout).contains("blocked_source_license_unverified"));
    let status: serde_json::Value =
        serde_json::from_slice(&cli(&["forward-status", dir]).stdout).unwrap();
    assert_eq!(status["collection_attempts"], 1);
    assert_eq!(status["actual_valid_forward_days"], 0);
    assert_eq!(status["simulated_fills"], 0);
    assert!(status["nav_fen"].is_null());
    assert!(!journal.join("ledger.sqlite").exists());
    let audit = cli(&["forward-eod-at", dir, "20261028", "0"]);
    assert!(audit.status.success());
    let audit: serde_json::Value = serde_json::from_slice(&audit.stdout).unwrap();
    assert!(audit["view"].is_null());
    assert!(audit["clock_uncertainty"].is_null());
    assert_eq!(
        audit["available_at_semantics"],
        stratide_forward::AVAILABILITY_SEMANTICS
    );
    assert!(cli(&["forward-report", dir, rpt]).status.success());
    let csv = fs::read(report.join("daily.csv")).unwrap();
    assert!(cli(&["forward-report", dir, rpt]).status.success());
    assert_eq!(csv, fs::read(report.join("daily.csv")).unwrap());
    assert_eq!(cli(&["forward-collect-once", dir]).status.code(), Some(2));
    assert_eq!(cli(&["forward-report", dir, rpt]).status.code(), Some(2));
    assert_eq!(
        cli(&["forward-init", dir, config.to_str().unwrap()])
            .status
            .code(),
        Some(2)
    );
    assert_eq!(cli(&["forward-source-check", dir]).status.code(), Some(2));
}

#[test]
fn eod_step_publishes_diagnostics_and_does_not_automatically_retry_after_restart() {
    let temp = tempfile::tempdir().unwrap();
    let journal = temp.path().join("observer");
    let reports = temp.path().join("reports");
    let config = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../samples/m1-pr04a-observer.json");
    let dir = journal.to_str().unwrap();
    let root = reports.to_str().unwrap();
    assert!(cli(&["forward-init", dir, config.to_str().unwrap()])
        .status
        .success());
    let first = cli(&["forward-eod-step", dir, root]);
    let one: serde_json::Value = serde_json::from_slice(&first.stdout).unwrap();
    let second = cli(&["forward-eod-step", dir, root]);
    let two: serde_json::Value = serde_json::from_slice(&second.stdout).unwrap();
    assert_eq!(one["head"], two["head"]);
    assert_eq!(two["step"]["collected"], false);
    assert_eq!(first.status.code(), second.status.code());
    let report = reports.join(two["head"].as_str().unwrap());
    assert!(report.join("events.json").exists());
    let r: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    assert_eq!(r["schema_version"], 2);
    assert!(r["status"]["collection_attempts"].as_u64().unwrap() <= 1);
    assert_eq!(r["status"]["actual_valid_forward_days"], 0);
    assert!(r["status"]["nav_fen"].is_null());
    assert!(!journal.join("ledger.sqlite").exists());
    assert_eq!(
        cli(&["forward-eod-step", dir, root, "--now", "20261029"])
            .status
            .code(),
        Some(2)
    );
}
