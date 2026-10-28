use std::process::Command;

fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_stratide-cli"))
        .args(args)
        .output()
        .unwrap()
}

#[test]
fn synthetic_demo_is_deterministic_and_does_not_claim_fills() {
    let args = [
        "risk-demo",
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
    let first = cli(&args);
    let second = cli(&args);
    assert!(
        first.status.success(),
        "{}",
        String::from_utf8_lossy(&first.stderr)
    );
    assert_eq!(first.stdout, second.stdout);
    let output = String::from_utf8(first.stdout).unwrap();
    for text in [
        "synthetic_test",
        "接受提案；不是成交",
        "可用资金不足",
        "持仓不足",
        "风险冻结",
        "审查未改变资金或仓位",
    ] {
        assert!(output.contains(text), "missing {text}: {output}");
    }
}

#[test]
fn missing_negative_fractional_or_overflowing_principal_is_not_defaulted() {
    for args in [
        vec!["risk-demo"],
        vec!["risk-demo", "--initial-cash-fen", "-1"],
        vec!["risk-demo", "--initial-cash-fen", "1.5"],
        vec!["risk-demo", "--initial-cash-fen", "9223372036854775808"],
    ] {
        let output = cli(&args);
        assert_eq!(output.status.code(), Some(2));
        assert!(output.stdout.is_empty());
        assert!(!output.stderr.is_empty());
    }
}
