//! A separate fixed-entry research comparator. All money, fees, reservations,
//! execution and risk remain in the existing ledger; no strategy ledger writes.
use super::*;
use serde_json::json;

pub(crate) fn run(args: &[String]) -> Result<(), String> {
    if args.len() < 9
        || args[3] != "--sha256"
        || args[5] != "--start-index"
        || args[7] != "--end-index"
    {
        return Err("paper-benchmark <input> <new-dir> --sha256 <sha> --start-index <inclusive> --end-index <exclusive> <six capital/risk flags>".into());
    }
    let (dataset, mut provenance) = load(&args[1], &args[4])?;
    if dataset.historical.is_none() || dataset.scenario.is_some() {
        return Err("研究基准仅支持带历史假设的 v2 输入".into());
    }
    let start: usize = args[6].parse().map_err(|_| "invalid start index")?;
    let end: usize = args[8].parse().map_err(|_| "invalid end index")?;
    if start >= end || end > dataset.sessions.len() {
        return Err("基准窗口为空或超出冻结输入".into());
    }
    let mut config = crate::config(&args[9..])?;
    if config.initial_capital.fen() > 10_000_000 {
        return Err("研究基准初始本金不得超过 Issue #11 授权的模拟本金".into());
    }
    config.account_id = "benchmark-account".into();
    config.deployment = DeploymentIdentity {
        group_id: "benchmark-group".into(),
        strategy_id: "independent-buy-hold".into(),
        frozen_version: "first-close-next-open-fixed100-v1".into(),
        deployment_id: format!("benchmark-{start}-{end}"),
    };
    config.max_snapshot_age_ms = 7 * DAY_MS;
    config.max_mark_age_ms = 7 * DAY_MS;
    provenance.source_version.push_str(&format!(
        " | independent-buy-hold-v1;window={start}..{end};first-close-only"
    ));
    let out = Path::new(&args[2]);
    // Exclusive new root: preserve incomplete runs as well as complete evidence.
    fs::create_dir(out).map_err(|e| format!("基准要求全新目录：{e}"))?;
    let first = &dataset.sessions[start];
    let mut ledger = Ledger::create(
        out.join("ledger"),
        Genesis {
            config: config.clone(),
            provenance: provenance.clone(),
            at: Timestamp(first.opens_at.0 - 1),
            day: first.day,
        },
    )?;
    let fee = dataset.fee_schedule()?;
    let mut daily = Vec::new();
    for (index, session) in dataset.sessions[start..end].iter().enumerate() {
        let rules = session.rules.to_rules(&dataset.instrument, session.day)?;
        ledger.execute(
            &format!("benchmark-session-{}", session.day.0),
            Command::HistoricalNextOpenV1 {
                now: session.available_at,
                bar: dataset.bar(session, &provenance)?,
                rules: rules.clone(),
            },
        )?;
        if index == 0 && session.status_verified {
            // Frozen calendar entry; independent of SMA signals and performance.
            let limit = session
                .close_fen
                .checked_add((session.close_fen + 49) / 50)
                .ok_or("基准限价溢出")?
                .min(session.rules.max_price_fen - 1);
            ledger.execute(
                "benchmark-once-only-entry",
                Command::Submit {
                    proposal: OrderProposal {
                        proposal_id: ProposalId(1),
                        account_id: config.account_id.clone(),
                        deployment: config.deployment.clone(),
                        instrument: dataset.instrument.clone(),
                        side: Side::Buy,
                        quantity: 100,
                        limit_price: money(limit)?,
                        decision_at: session.available_at,
                        data_available_at: session.available_at,
                        earliest_execution_at: Timestamp(session.available_at.0 + 1),
                        expires_at: Timestamp(session.available_at.0 + 14 * DAY_MS),
                    },
                    now: session.available_at,
                    day: session.day,
                    rules: Some(rules),
                    fees: Some(fee.clone()),
                },
            )?;
        }
        let state = ledger.state();
        daily.push(json!({
            "day": session.day, "nav_fen": state.equity,
            "cash_fen": state.snapshot.cash,
            "held_shares": state.snapshot.positions.iter().map(|p| p.quantity).sum::<i64>(),
            "pending_orders": state.snapshot.pending_orders.len(),
            "valuation_error": state.valuation_error,
        }));
    }
    let state = ledger.state();
    let result = json!({
        "benchmark_version": "first-close-next-open-fixed100-v1",
        "kind": "independent_engine_backtest_not_risk_matched_alpha",
        "status": if state.fills.len() == 1 { "EVALUATED" } else { "NOT_EVALUATED" },
        "reason": if state.fills.len() == 1 { None } else { Some("single precommitted entry did not fill; never choose a later entry") },
        "input_sha256": provenance.dataset_hash, "start_index": start, "end_index": end,
        "initial_nav_fen": config.initial_capital, "config": config,
        "fee_assumption": dataset.fee, "execution_model": "next-open-adverse-tick-100-v1",
        "ledger_head": ledger.head(), "daily": daily,
        "orders": state.orders, "fills": state.fills, "risk": state.risk,
        "assumptions": "historical ex-post; first session cash; first close submits once; next open adverse 1 fen; no terminal sale; no PIT/real execution claim",
    });
    fs::write(
        out.join("benchmark.json"),
        serde_json::to_vec_pretty(&result).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    println!("独立固定入场基准已生成；非风险匹配 alpha，非真实成交");
    Ok(())
}
