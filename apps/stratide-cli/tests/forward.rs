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
