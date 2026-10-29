use sha2::{Digest, Sha256};
use std::{fs, path::Path, process::Command};

const HASH: &str = "e6897a41eedf0a49ea36c4870586cae9b964e05799d4010fd34adcb57fefb5fe";
const CONFIG: [&str; 12] = [
    "--initial-cash-fen",
    "1000000",
    "--max-order-fen",
    "500000",
    "--account-cap-fen",
    "800000",
    "--strategy-cap-fen",
    "500000",
    "--daily-loss-fen",
    "100000",
    "--drawdown-fen",
    "200000",
];

fn input() -> std::path::PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../samples/m0-pr03-synthetic.json")
}

fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_stratide-cli"))
        .args(args)
        .output()
        .unwrap()
}

fn replay(input: &Path, ledger: &Path, report: &Path, hash: &str) -> std::process::Output {
    let mut args = vec![
        "paper-replay",
        input.to_str().unwrap(),
        ledger.to_str().unwrap(),
        report.to_str().unwrap(),
        "--sha256",
        hash,
    ];
    args.extend(CONFIG);
    cli(&args)
}

fn assert_ok(output: &std::process::Output) {
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn independent_directories_and_restarts_produce_identical_paper_reports() {
    let temp = tempfile::tempdir().unwrap();
    let input = input();
    assert_eq!(
        format!("{:x}", Sha256::digest(fs::read(&input).unwrap())),
        HASH
    );
    let a = temp.path().join("a");
    let b = temp.path().join("b");
    let ra = temp.path().join("report-a");
    let rb = temp.path().join("report-b");
    assert_ok(&replay(&input, &a, &ra, HASH));
    assert_ok(&replay(&input, &b, &rb, HASH));
    let names = [
        "report.json",
        "daily.csv",
        "orders.csv",
        "fills.csv",
        "positions.csv",
        "events.json",
    ];
    let before: Vec<_> = names
        .iter()
        .map(|name| fs::read(ra.join(name)).unwrap())
        .collect();
    for (name, bytes) in names.iter().zip(&before) {
        assert_eq!(&fs::read(rb.join(name)).unwrap(), bytes);
    }
    assert_ok(&replay(&input, &a, &ra, HASH));
    for (name, bytes) in names.iter().zip(&before) {
        assert_eq!(&fs::read(ra.join(name)).unwrap(), bytes);
    }
    let report: serde_json::Value = serde_json::from_slice(&before[0]).unwrap();
    assert_eq!(report["ending_nav_fen"], 992893);
    assert_eq!(report["ending_cash_fen"], 992893);
    assert_eq!(report["total_fee_fen"], 107);
    assert_eq!(report["realized_pnl_fen"], -7107);
    assert_eq!(report["unrealized_pnl_fen"], 0);
    assert_eq!(report["max_daily_observation_drawdown_bps"], 71);
    assert_eq!(report["fills"].as_array().unwrap().len(), 2);
    assert_eq!(report["risk_rejections"].as_array().unwrap().len(), 1);
    let head = report["ledger_head"].clone();
    let prior_v3: serde_json::Value = serde_json::from_slice(
        &fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../docs/evidence/m0-pr03/sample-report/report.json"),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(
        head, prior_v3["ledger_head"],
        "historical branch must preserve prior v3 digest/reducer semantics"
    );
    assert_eq!(
        head,
        serde_json::from_slice::<serde_json::Value>(&fs::read(rb.join("report.json")).unwrap())
            .unwrap()["ledger_head"]
    );
    assert_ok(&cli(&[
        "paper-report",
        input.to_str().unwrap(),
        a.to_str().unwrap(),
        ra.to_str().unwrap(),
        "--sha256",
        HASH,
    ]));
}

#[test]
fn bad_hash_future_data_and_absent_opening_evidence_cannot_make_a_fill() {
    let temp = tempfile::tempdir().unwrap();
    let input = input();
    let ledger = temp.path().join("bad-hash");
    let report = temp.path().join("out");
    assert_eq!(
        replay(&input, &ledger, &report, &"0".repeat(64))
            .status
            .code(),
        Some(2)
    );
    assert!(!ledger.exists());
    let mut data: serde_json::Value = serde_json::from_slice(&fs::read(&input).unwrap()).unwrap();
    data["sessions"][0]["available_at"] =
        serde_json::json!(data["sessions"][1]["opens_at"].as_i64().unwrap() + 1);
    let late = temp.path().join("late.json");
    fs::write(&late, serde_json::to_vec(&data).unwrap()).unwrap();
    let hash = format!("{:x}", Sha256::digest(fs::read(&late).unwrap()));
    assert_eq!(
        replay(&late, &ledger, &report, &hash).status.code(),
        Some(2)
    );
    assert!(!ledger.exists());
    let mut data: serde_json::Value = serde_json::from_slice(&fs::read(&input).unwrap()).unwrap();
    data["sessions"][1]["day"] = data["sessions"][0]["day"].clone();
    let repeated_day = temp.path().join("repeated-day.json");
    fs::write(&repeated_day, serde_json::to_vec(&data).unwrap()).unwrap();
    let hash = format!("{:x}", Sha256::digest(fs::read(&repeated_day).unwrap()));
    assert_eq!(
        replay(&repeated_day, &ledger, &report, &hash).status.code(),
        Some(2)
    );
    assert!(!ledger.exists());
    let mut data: serde_json::Value = serde_json::from_slice(&fs::read(&input).unwrap()).unwrap();
    data["sessions"][1]["opening"] = serde_json::Value::Null;
    let no_open = temp.path().join("no-opening.json");
    fs::write(&no_open, serde_json::to_vec(&data).unwrap()).unwrap();
    let hash = format!("{:x}", Sha256::digest(fs::read(&no_open).unwrap()));
    assert_ok(&replay(&no_open, &ledger, &report, &hash));
    let value: serde_json::Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    assert!(value["fills"]
        .as_array()
        .unwrap()
        .iter()
        .all(|f| f["day"] != 20261029));
    assert_eq!(value["missing_opening_evidence_sessions"], 1);
    assert_eq!(value["realized_pnl_fen"], 0);
}

#[test]
fn unverified_session_is_an_explicit_nav_gap_and_never_generates_its_close_signal() {
    let temp = tempfile::tempdir().unwrap();
    let mut data: serde_json::Value = serde_json::from_slice(&fs::read(input()).unwrap()).unwrap();
    data["sessions"][2]["status_verified"] = serde_json::Value::Bool(false);
    let input = temp.path().join("unverified.json");
    fs::write(&input, serde_json::to_vec(&data).unwrap()).unwrap();
    let hash = format!("{:x}", Sha256::digest(fs::read(&input).unwrap()));
    let report_dir = temp.path().join("report");
    assert_ok(&replay(
        &input,
        &temp.path().join("ledger"),
        &report_dir,
        &hash,
    ));
    let report: serde_json::Value =
        serde_json::from_slice(&fs::read(report_dir.join("report.json")).unwrap()).unwrap();
    assert_eq!(report["daily"][2]["nav_fen"], serde_json::Value::Null);
    assert_eq!(report["unverified_status_sessions"], 1);
    assert!(report["orders"]
        .as_array()
        .unwrap()
        .iter()
        .all(|o| o["accepted_on"] != 20261030));
}

#[test]
fn legacy_v3_synthetic_demo_cannot_be_relabelled_as_replay_report() {
    let temp = tempfile::tempdir().unwrap();
    let ledger = temp.path().join("legacy-v3");
    let mut create = vec!["paper-create", ledger.to_str().unwrap()];
    create.extend(CONFIG);
    assert_ok(&cli(&create));
    let report = temp.path().join("report");
    let out = cli(&[
        "paper-report",
        input().to_str().unwrap(),
        ledger.to_str().unwrap(),
        report.to_str().unwrap(),
        "--sha256",
        HASH,
    ]);
    assert_eq!(out.status.code(), Some(2));
    assert!(!report.exists());
    assert!(String::from_utf8_lossy(&out.stderr).contains("不匹配"));
}

#[test]
fn interrupted_export_resumes_in_same_directory_and_preserves_partial_evidence() {
    let temp = tempfile::tempdir().unwrap();
    let ledger = temp.path().join("ledger");
    let baseline = temp.path().join("baseline");
    let interrupted = temp.path().join("interrupted");
    assert_ok(&replay(&input(), &ledger, &baseline, HASH));
    let state_before = cli(&["paper-status", ledger.to_str().unwrap()]).stdout;
    fs::create_dir(&interrupted).unwrap();
    fs::copy(
        baseline.join("events.json"),
        interrupted.join("events.json"),
    )
    .unwrap();
    fs::write(interrupted.join("daily.csv"), []).unwrap();
    assert_ok(&replay(&input(), &ledger, &interrupted, HASH));
    for name in [
        "events.json",
        "daily.csv",
        "orders.csv",
        "fills.csv",
        "positions.csv",
        "report.json",
    ] {
        assert_eq!(
            fs::read(interrupted.join(name)).unwrap(),
            fs::read(baseline.join(name)).unwrap()
        );
    }
    assert_eq!(
        cli(&["paper-status", ledger.to_str().unwrap()]).stdout,
        state_before
    );
    let archives: Vec<_> = fs::read_dir(temp.path())
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| {
            p.file_name()
                .unwrap()
                .to_string_lossy()
                .ends_with(".interrupted")
        })
        .collect();
    assert_eq!(archives.len(), 1);
    assert_eq!(
        fs::read(archives[0].join("events.json")).unwrap(),
        fs::read(baseline.join("events.json")).unwrap()
    );
    assert_eq!(
        fs::metadata(archives[0].join("daily.csv")).unwrap().len(),
        0
    );
}
