use std::process::Command as Process;
use stratide_contracts::{Cny, PositionMark, Timestamp, TradingDay};
use stratide_ledger::{synthetic as fixture, Command, OrderStatus, State};
use stratide_risk::{FreezeReason, RiskScope};

fn cli(args: &[&str]) -> std::process::Output {
    Process::new(env!("CARGO_BIN_EXE_stratide-cli"))
        .args(args)
        .output()
        .unwrap()
}
fn success(args: &[&str]) -> State {
    let out = cli(args);
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).unwrap()
}
fn create(path: &str) -> State {
    success(&[
        "paper-create",
        path,
        "--initial-cash-fen",
        "1000000",
        "--max-order-fen",
        "500000",
        "--account-cap-fen",
        "800000",
        "--strategy-cap-fen",
        "500000",
        "--daily-loss-fen",
        "10000",
        "--drawdown-fen",
        "15000",
    ])
}
fn apply(path: &str, file: &std::path::Path, id: &str, cmd: Command) -> State {
    std::fs::write(file, serde_json::to_vec(&cmd).unwrap()).unwrap();
    success(&["paper-apply", path, id, file.to_str().unwrap()])
}
fn observation(price: i64, now: i64, day: u32, flow: i64) -> Command {
    Command::Observe {
        now: Timestamp(now),
        day: TradingDay(day),
        external_flow_fen: flow,
        marks: vec![PositionMark {
            instrument: fixture::instrument(),
            price: Cny::from_fen(price).unwrap(),
            as_of: Timestamp(now),
            available_at: Timestamp(now),
            source: "synthetic_test/CLI-mark-v1".into(),
        }],
    }
}

#[test]
fn actual_cli_create_submit_fill_reopen_retry_and_deterministic_second_run() {
    let temp = tempfile::tempdir().unwrap();
    let mut results = vec![];
    for name in ["a", "b"] {
        let path = temp.path().join(name);
        let path = path.to_str().unwrap();
        let initial = create(path);
        assert_eq!(initial.snapshot.cash.fen(), 1_000_000);
        let submitted = success(&["paper-submit-synthetic", path]);
        assert_eq!(submitted.snapshot.pending_orders.len(), 1);
        assert_eq!(
            submitted.snapshot.pending_orders[0].reserved_cash.fen(),
            100_200
        );
        let filled = success(&["paper-match-synthetic", path]);
        assert_eq!(filled.snapshot.cash.fen(), 899_969);
        assert_eq!(filled.snapshot.positions[0].quantity, 100);
        assert_eq!(filled.fills[0].fees.total().unwrap().fen(), 31);
        assert_eq!(filled.orders[0].status, OrderStatus::Filled);
        // Every call above exited. Production library recovers from disk anew.
        let recovered = success(&["paper-status", path]);
        assert_eq!(filled, recovered);
        assert_eq!(success(&["paper-submit-synthetic", path]), filled);
        assert_eq!(success(&["paper-match-synthetic", path]), filled);
        assert_eq!(cli(&["paper-create", path]).status.code(), Some(2));
        results.push(filled);
    }
    assert_eq!(results[0], results[1]);
}

#[test]
fn real_process_restarts_preserve_peak_flow_rejected_order_locks_and_missing_valuation() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("account");
    let path = path.to_str().unwrap();
    let file = temp.path().join("trusted-command.json");
    create(path);
    success(&["paper-submit-synthetic", path]);
    success(&["paper-match-synthetic", path]);
    let t = fixture::T0 + fixture::DAY;
    let peak = apply(path, &file, "peak", observation(1200, t + 1, 20261029, 0));
    assert_eq!(peak.risk.peak().fen(), 1_019_969);
    let withdrawn = apply(
        path,
        &file,
        "withdraw",
        observation(1200, t + 2, 20261029, -10000),
    );
    assert_eq!(withdrawn.risk.peak(), peak.risk.peak());
    let deposited = apply(
        path,
        &file,
        "deposit",
        observation(1200, t + 3, 20261029, 10000),
    );
    assert_eq!(deposited.risk.peak(), peak.risk.peak());
    let loss = apply(
        path,
        &file,
        "loss-without-proposal",
        observation(800, t + 4, 20261029, 0),
    );
    for scope in [RiskScope::Account, RiskScope::Strategy] {
        assert!(loss.risk.freezes(scope).contains(&FreezeReason::DailyLoss));
        assert!(loss.risk.freezes(scope).contains(&FreezeReason::Drawdown));
    }
    let mut p = fixture::proposal(&loss.config, 2);
    p.decision_at = Timestamp(t + 4);
    p.data_available_at = p.decision_at;
    p.earliest_execution_at = Timestamp(t + 5);
    let rejected = apply(
        path,
        &file,
        "reject-no-cost",
        Command::Submit {
            proposal: p,
            now: Timestamp(t + 4),
            day: TradingDay(20261029),
            rules: None,
            fees: None,
        },
    );
    assert_eq!(rejected.orders[1].status, OrderStatus::Rejected);
    assert_eq!(rejected.risk, loss.risk);
    let missing = apply(
        path,
        &file,
        "missing-marks",
        Command::Observe {
            now: Timestamp(t + 5),
            day: TradingDay(20261029),
            marks: vec![],
            external_flow_fen: 0,
        },
    );
    assert!(missing.valuation_error.is_some());
    assert_eq!(success(&["paper-status", path]), missing);
    let recovered = apply(
        path,
        &file,
        "marks-return",
        observation(1000, t + 6, 20261029, 0),
    );
    assert!(recovered.valuation_error.is_none());
    assert_eq!(recovered.risk, loss.risk);
    let next = apply(
        path,
        &file,
        "next-day",
        observation(1000, t + fixture::DAY, 20261030, 0),
    );
    assert_eq!(next.risk, loss.risk);
}
