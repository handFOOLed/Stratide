use super::{days_from_civil, historical, Dataset, STRATEGY_SPEC};
use serde::Serialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, VecDeque},
    path::Path,
};
use stratide_contracts::{Cny, Side, TradingDay};
use stratide_ledger::{Command, Fill, Ledger, OrderStatus, State};

mod publish;

#[derive(Serialize)]
struct Daily {
    day: u32,
    nav_fen: Option<i64>,
    cash_fen: i64,
    available_cash_fen: i64,
    reserved_cash_fen: i64,
    held_shares: i64,
    sellable_shares: i64,
    unsettled_shares: i64,
    reserved_sell_shares: i64,
    pending_orders: usize,
    cumulative_fee_fen: i64,
    realized_pnl_fen: Option<i128>,
    unrealized_pnl_fen: Option<i128>,
    remaining_cost_basis_fen: Option<i128>,
    external_flow_total_fen: i64,
    valuation_error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    cash_dividend: Option<stratide_ledger::cash_dividend::DividendTotals>,
}

struct Lot {
    shares: i64,
    cost_fen: i128,
}

fn accounting(state: &State) -> (Option<i128>, Option<i128>, Option<i128>) {
    let mut lots: VecDeque<Lot> = VecDeque::new();
    let mut realized = 0_i128;
    for fill in &state.fills {
        let gross = i128::from(fill.price.fen()) * i128::from(fill.quantity);
        let fees = match fill.fees.total() {
            Ok(f) => i128::from(f.fen()),
            Err(_) => return (None, None, None),
        };
        if fill.side == Side::Buy {
            lots.push_back(Lot {
                shares: fill.quantity,
                cost_fen: gross + fees,
            });
        } else {
            let mut remaining = fill.quantity;
            let mut cost = 0_i128;
            while remaining > 0 {
                let Some(lot) = lots.front_mut() else {
                    return (None, None, None);
                };
                let take = remaining.min(lot.shares);
                let taken_cost = if take == lot.shares {
                    lot.cost_fen
                } else {
                    lot.cost_fen * i128::from(take) / i128::from(lot.shares)
                };
                lot.shares -= take;
                lot.cost_fen -= taken_cost;
                remaining -= take;
                cost += taken_cost;
                if lot.shares == 0 {
                    lots.pop_front();
                }
            }
            realized += gross - fees - cost;
        }
    }
    let held: i64 = state.snapshot.positions.iter().map(|l| l.quantity).sum();
    if lots.iter().map(|l| l.shares).sum::<i64>() != held {
        return (None, None, None);
    }
    let basis = lots.iter().map(|l| l.cost_fen).sum::<i128>();
    let mark = state.snapshot.positions.first().and_then(|p| {
        state
            .snapshot
            .marks
            .iter()
            .find(|m| m.instrument == p.instrument)
    });
    let unrealized = if held == 0 {
        Some(0)
    } else if state.equity.is_none() {
        None
    } else {
        mark.map(|m| i128::from(m.price.fen()) * i128::from(held) - basis)
    };
    (Some(realized), unrealized, Some(basis))
}

fn daily(
    day: TradingDay,
    state: &State,
    t_plus_one: bool,
    completed: bool,
) -> Result<Daily, String> {
    let held = state
        .snapshot
        .positions
        .iter()
        .try_fold(0_i64, |n, l| n.checked_add(l.quantity))
        .ok_or("持仓溢出")?;
    let unsettled = if t_plus_one {
        state
            .snapshot
            .positions
            .iter()
            .filter(|l| l.acquired_on >= day)
            .map(|l| l.quantity)
            .sum()
    } else {
        0
    };
    let reserved_sell: i64 = state
        .snapshot
        .pending_orders
        .iter()
        .filter(|o| o.side == Side::Sell)
        .map(|o| o.quantity)
        .sum();
    let reserved_cash: i64 = state
        .snapshot
        .pending_orders
        .iter()
        .map(|o| o.reserved_cash.fen())
        .sum();
    let sellable = held
        .checked_sub(unsettled)
        .and_then(|v| v.checked_sub(reserved_sell))
        .ok_or("可卖数量溢出")?;
    let available_cash = state
        .snapshot
        .cash
        .fen()
        .checked_sub(reserved_cash)
        .ok_or("可用现金溢出")?;
    if sellable < 0 || available_cash < 0 {
        return Err("报表预留超过资金/可卖持仓".into());
    }
    let fees = state
        .fills
        .iter()
        .try_fold(0_i64, |n, f| -> Result<i64, String> {
            n.checked_add(f.fees.total()?.fen())
                .ok_or_else(|| "费用溢出".to_string())
        })?;
    let (realized, unrealized, basis) = accounting(state);
    Ok(Daily {
        day: day.0,
        nav_fen: if completed {
            state.equity.map(Cny::fen)
        } else {
            None
        },
        cash_fen: state.snapshot.cash.fen(),
        available_cash_fen: available_cash,
        reserved_cash_fen: reserved_cash,
        held_shares: held,
        sellable_shares: sellable,
        unsettled_shares: unsettled,
        reserved_sell_shares: reserved_sell,
        pending_orders: state.snapshot.pending_orders.len(),
        cumulative_fee_fen: fees,
        realized_pnl_fen: realized,
        unrealized_pnl_fen: if completed { unrealized } else { None },
        remaining_cost_basis_fen: basis,
        external_flow_total_fen: state.snapshot.equity_basis.net_external_flow_total_fen,
        cash_dividend: if state.cash_dividends.is_some() {
            Some(state.dividend_totals()?)
        } else {
            None
        },
        valuation_error: if completed {
            state.valuation_error.clone()
        } else {
            Some(
                "当日行情状态未核验；账本未推进，NAV unavailable；资金/持仓仅为上次已确认状态"
                    .into(),
            )
        },
    })
}

fn csv_cell(s: &str) -> String {
    let safe = if s.starts_with(['=', '+', '-', '@', '\t']) {
        format!("'{s}")
    } else {
        s.into()
    };
    format!("\"{}\"", safe.replace('"', "\"\""))
}
fn opt<T: ToString>(v: Option<T>) -> String {
    v.map(|x| x.to_string()).unwrap_or_default()
}

pub(super) fn export(
    dataset: &Dataset,
    ledger: &Ledger,
    expected: &[(String, Command)],
    out: &Path,
) -> Result<(), String> {
    let history = ledger.history()?;
    if history.len() != expected.len() + 1
        || history
            .iter()
            .skip(1)
            .zip(expected)
            .any(|(entry, (id, command))| {
                entry.event_id != *id || entry.command.as_ref() != Some(command)
            })
    {
        return Err("账本事件与冻结输入/固定策略不一致或回放未完成；拒绝导出".into());
    }
    let mut final_by_day: BTreeMap<u32, (&State, bool)> = BTreeMap::new();
    let mut events = Vec::new();
    let mut previous_fills = 0;
    let mut previous_orders = 0;
    let mut dividend_actions = Vec::new();
    for entry in &history {
        if let Some(command) = &entry.command {
            match command {
                Command::Match {
                    day, instrument, ..
                } => {
                    let completed = entry.state.sessions.contains(&(instrument.clone(), *day));
                    final_by_day.insert(day.0, (&entry.state, completed));
                }
                Command::HistoricalNextOpenV1 { bar, .. } => {
                    let completed = bar.status_verified
                        && entry
                            .state
                            .sessions
                            .contains(&(bar.instrument.clone(), bar.day));
                    final_by_day.insert(bar.day.0, (&entry.state, completed));
                }
                Command::Submit { day, .. } | Command::CashDividendV1 { day, .. } => {
                    let completed = final_by_day.get(&day.0).is_some_and(|(_, c)| *c);
                    final_by_day.insert(day.0, (&entry.state, completed));
                }
                _ => {}
            }
            let mut event = json!({
                "seq": entry.seq, "event_id": entry.event_id, "ledger_digest": entry.digest,
                "command": command, "account_as_of": entry.state.snapshot.as_of,
                "cash_fen": entry.state.snapshot.cash.fen(), "nav_fen": entry.state.equity.map(Cny::fen),
                "new_orders": &entry.state.orders[previous_orders..],
                "new_fills": &entry.state.fills[previous_fills..],
                "risk": entry.state.risk, "valuation_error": entry.state.valuation_error,
            });
            if let Some(book) = &entry.state.cash_dividends {
                event["cash_dividend"] = serde_json::to_value(entry.state.dividend_totals()?)
                    .map_err(|e| e.to_string())?;
                event["held_shares"] = json!(entry
                    .state
                    .snapshot
                    .positions
                    .iter()
                    .map(|p| p.quantity)
                    .sum::<i64>());
                if let Command::CashDividendV1 {
                    event_id,
                    phase,
                    now,
                    day,
                    ..
                } = command
                {
                    let a = book
                        .events
                        .iter()
                        .find(|a| a.event.event_id == *event_id)
                        .ok_or("审计缺公司行为")?;
                    let (gross, tax) = a.event.amounts(a.entitled_shares.ok_or("审计缺权益")?)?;
                    dividend_actions.push(json!({
                        "ledger_seq": entry.seq, "ledger_event_id": entry.event_id, "ledger_digest": entry.digest,
                        "event": a.event, "phase": phase, "at": now, "day": day,
                        "entitled_shares": a.entitled_shares, "gross_fen": gross, "tax_fen": tax, "net_fen": gross - tax,
                        "recognized": a.recognized, "paid": a.paid,
                        "totals": entry.state.dividend_totals()?, "cash_fen": entry.state.snapshot.cash,
                        "nav_fen": entry.state.equity, "valuation_error": entry.state.valuation_error,
                    }));
                }
            }
            events.push(event);
            previous_orders = entry.state.orders.len();
            previous_fills = entry.state.fills.len();
        }
    }
    let mut daily_rows = Vec::new();
    for s in &dataset.sessions {
        let (state, completed) = final_by_day.get(&s.day.0).ok_or("缺少每日账本状态")?;
        daily_rows.push(daily(
            s.day,
            state,
            s.rules.settlement == stratide_contracts::SettlementRule::TPlusOne,
            *completed,
        )?);
    }
    let final_state = ledger.state();
    let last = daily_rows.last().ok_or("无每日观察")?;
    let initial = final_state.config.initial_capital.fen();
    let flow = final_state
        .snapshot
        .equity_basis
        .net_external_flow_total_fen;
    let adjusted_last = last.nav_fen.and_then(|v| v.checked_sub(flow));
    let total_return_bps = if flow == 0 {
        adjusted_last.map(|v| (i128::from(v) - i128::from(initial)) * 10_000 / i128::from(initial))
    } else {
        None
    };
    let mut peak = i128::from(initial);
    let mut max_drawdown_bps = Some(0_i128);
    for row in &daily_rows {
        if let Some(nav) = row
            .nav_fen
            .and_then(|v| v.checked_sub(row.external_flow_total_fen))
        {
            let nav = i128::from(nav);
            peak = peak.max(nav);
            max_drawdown_bps = max_drawdown_bps.map(|m| m.max((peak - nav) * 10_000 / peak));
        } else {
            max_drawdown_bps = None;
        }
    }
    let total_fees = last.cumulative_fee_fen;
    let first_buy: Option<&Fill> = final_state.fills.iter().find(|f| f.side == Side::Buy);
    let buy_hold_nav = if dataset.cash_dividends.is_none() && flow == 0 && last.nav_fen.is_some() {
        first_buy.and_then(|f| {
            let final_mark = final_state
                .snapshot
                .marks
                .iter()
                .find(|m| m.instrument == f.instrument)?;
            let entry = f
                .price
                .fen()
                .checked_mul(f.quantity)?
                .checked_add(f.fees.total().ok()?.fen())?;
            initial
                .checked_sub(entry)?
                .checked_add(final_mark.price.fen().checked_mul(f.quantity)?)
        })
    } else {
        None
    };
    let missing_opening_sessions = dataset
        .sessions
        .iter()
        .filter(|s| s.opening.is_none())
        .count();
    let unverified_status_sessions = dataset
        .sessions
        .iter()
        .filter(|s| !s.status_verified)
        .count();
    let no_fill_sessions = dataset
        .sessions
        .iter()
        .filter(|s| !final_state.fills.iter().any(|f| f.day == s.day))
        .count();
    let mut unobserved_calendar_days = 0_i64;
    for pair in dataset.sessions.windows(2) {
        unobserved_calendar_days +=
            days_from_civil(pair[1].day)? - days_from_civil(pair[0].day)? - 1;
    }
    let config_hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&final_state.config).map_err(|e| e.to_string())?)
    );
    let summary = json!({
        "report_schema": 1, "ledger_schema": 3, "mode": dataset.mode,
        "evidence_class": if dataset.mode == stratide_ledger::DataMode::SyntheticTest { "engine_test_only" } else { "exploratory_historical_replay_not_pit_verified" },
        "paper_only": true, "source": dataset.source, "license": dataset.license,
        "source_version": dataset.source_version, "input_sha256": final_state.provenance.dataset_hash,
        "timezone": dataset.timezone, "price_semantics": dataset.price_semantics,
        "instrument": dataset.instrument, "first_day": dataset.sessions.first().unwrap().day,
        "last_day": dataset.sessions.last().unwrap().day,
        "strategy_version": if dataset.cash_dividends.is_some() { super::cash_dividend::VERSION } else { historical::strategy_version(dataset) },
        "strategy_spec_sha256": format!("{:x}", Sha256::digest(if dataset.cash_dividends.is_some() { super::cash_dividend::SPEC } else if dataset.historical.is_some() { historical::SPEC } else { STRATEGY_SPEC }.as_bytes())),
        "config_sha256": config_hash,
        "config": final_state.config, "ledger_head": ledger.head(),
        "initial_nav_fen": initial, "ending_nav_fen": last.nav_fen,
        "ending_cash_fen": last.cash_fen, "ending_available_cash_fen": last.available_cash_fen,
        "ending_held_shares": last.held_shares, "ending_sellable_shares": last.sellable_shares,
        "ending_unsettled_shares": last.unsettled_shares, "ending_pending_orders": last.pending_orders,
        "external_flow_total_fen": flow, "total_fee_fen": total_fees,
        "realized_pnl_fen": last.realized_pnl_fen,
        "unrealized_pnl_fen": last.unrealized_pnl_fen,
        "remaining_cost_basis_fen": last.remaining_cost_basis_fen,
        "total_return_bps": total_return_bps, "max_daily_observation_drawdown_bps": max_drawdown_bps,
        "cash_benchmark_nav_fen": if flow == 0 { Some(initial) } else { None },
        "buy_hold_benchmark_nav_fen": buy_hold_nav,
        "buy_hold_benchmark_note": "仅在本策略首笔模拟买入确已成交时，以相同股数/入场价/买入费用持有至末日收盘；不估算离场费，不代表可执行独立策略",
        "missing_opening_evidence_sessions": missing_opening_sessions,
        "unverified_status_sessions": unverified_status_sessions,
        "no_fill_sessions": no_fill_sessions,
        "unobserved_calendar_days_including_weekends": unobserved_calendar_days,
        "risk_rejections": final_state.orders.iter().filter(|o| o.status == OrderStatus::Rejected).collect::<Vec<_>>(),
        "daily": daily_rows, "orders": final_state.orders, "fills": final_state.fills,
        "positions": final_state.snapshot.positions, "events": events,
    });
    let mut summary = summary;
    if let Some(book) = &final_state.cash_dividends {
        summary["report_schema"] = json!(2);
        summary["ledger_schema"] = json!(4);
        summary["cash_dividend_protocol"] = json!("CASH_DIVIDEND_V1");
        summary["cash_dividend"] =
            serde_json::to_value(final_state.dividend_totals()?).map_err(|e| e.to_string())?;
        summary["frozen_cash_dividends"] = serde_json::to_value(book).map_err(|e| e.to_string())?;
        summary["cash_dividend_actions"] = json!(dividend_actions);
        summary["historical_pit"] = json!("NOT_VERIFIED");
        summary["eligibility"] = json!("ELIGIBILITY_DENIED");
        summary["opening_source"] = json!("BLOCKED");
        summary["buy_hold_benchmark_note"] = json!("分红模式须另运行 paper-dividend-benchmark，独立账本使用相同股息/税/风险/成交模型；Python逐日复算，不使用旧无股息近似值");
    }
    if let Some(historical) = &dataset.historical {
        summary["historical_assumptions"] =
            serde_json::to_value(historical).map_err(|e| e.to_string())?;
        summary["execution_model"] = json!("next-open-adverse-tick-100-v1");
        summary["fee_assumption"] =
            serde_json::to_value(&dataset.fee).map_err(|e| e.to_string())?;
        summary["forward_opening_evidence_claimed"] = json!(false);
        summary["historical_model_sessions"] = json!(dataset.sessions.len());
    }
    if let Some(scenario) = &dataset.scenario {
        summary["historical_dividend_scenario"] =
            serde_json::to_value(scenario).map_err(|e| e.to_string())?;
        summary["evidence_class"] = json!("EXPLORATORY_EX_POST");
        summary["scenario_engineering_status"] = json!("REPLAY_COMPLETE_PENDING_PYTHON_AUDIT");
        summary["real_historical_eligibility"] = json!("DENIED");
        summary["real_blockers"] = json!([
            "PIT_NOT_VERIFIED",
            "TAX_ACCOUNT_UNKNOWN",
            "PAYMENT_UNKNOWN",
            "REAL_PROVIDER_NOT_VERIFIED",
            "OPENING_SOURCE_BLOCKED"
        ]);
        summary["research_evidence"] = json!("INSUFFICIENT_EVIDENCE");
        summary["real_pit_days_added"] = json!(0);
        summary["strategy_version"] = json!(final_state.config.deployment.frozen_version);
        summary["strategy_spec_sha256"] = json!(format!(
            "{:x}",
            Sha256::digest(
                super::historical_dividend::strategy_spec(&final_state.config).as_bytes()
            )
        ));
        summary["buy_hold_benchmark_note"] = json!("独立 paper-historical-dividend-benchmark/cash-benchmark v4账本；首日收盘仅提交一次、下一开盘不利一分；全部为EX_POST_MODEL_ONLY");
    }
    let report_json = serde_json::to_vec_pretty(&summary).map_err(|e| e.to_string())?;
    let events_json = serde_json::to_vec_pretty(&events).map_err(|e| e.to_string())?;
    let mut daily_csv = String::from("day,nav_fen,cash_fen,available_cash_fen,reserved_cash_fen,held_shares,sellable_shares,unsettled_shares,reserved_sell_shares,pending_orders,cumulative_fee_fen,realized_pnl_fen,unrealized_pnl_fen,remaining_cost_basis_fen,external_flow_total_fen,valuation_error\n");
    if dataset.cash_dividends.is_some() {
        daily_csv.pop();
        daily_csv.push_str(",receivable_fen,liability_fen,dividend_gross_income_fen,dividend_tax_expense_fen,dividend_cash_paid_fen\n");
    }
    for d in &daily_rows {
        daily_csv.push_str(&format!(
            "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n",
            d.day,
            opt(d.nav_fen),
            d.cash_fen,
            d.available_cash_fen,
            d.reserved_cash_fen,
            d.held_shares,
            d.sellable_shares,
            d.unsettled_shares,
            d.reserved_sell_shares,
            d.pending_orders,
            d.cumulative_fee_fen,
            opt(d.realized_pnl_fen),
            opt(d.unrealized_pnl_fen),
            opt(d.remaining_cost_basis_fen),
            d.external_flow_total_fen,
            csv_cell(d.valuation_error.as_deref().unwrap_or(""))
        ));
        if let Some(t) = d.cash_dividend {
            daily_csv.pop();
            daily_csv.push_str(&format!(
                ",{},{},{},{},{}\n",
                t.receivable_fen,
                t.liability_fen,
                t.gross_income_fen,
                t.tax_expense_fen,
                t.cash_paid_fen
            ));
        }
    }
    let mut orders_csv =
        String::from("proposal_id,day,side,quantity,limit_fen,status,remaining,reason\n");
    for o in &final_state.orders {
        orders_csv.push_str(&format!(
            "{},{},{:?},{},{},{:?},{},{}\n",
            o.proposal.proposal_id.0,
            o.accepted_on.0,
            o.proposal.side,
            o.proposal.quantity,
            o.proposal.limit_price.fen(),
            o.status,
            o.remaining,
            csv_cell(&o.reason)
        ));
    }
    let mut fills_csv = String::from("fill_id,order_id,day,side,quantity,price_fen,commission_fen,transfer_fen,tax_fen,total_fee_fen,simulated_at,risk_checked_at,market_opens_at,market_closes_at,bar_available_at,source_version,input_sha256\n");
    if dataset.historical.is_some() {
        fills_csv.pop();
        fills_csv.push_str(",execution_assumption\n");
    }
    for f in &final_state.fills {
        fills_csv.push_str(&format!(
            "{},{},{},{:?},{},{},{},{},{},{},{},{},{},{},{},{},{}\n",
            csv_cell(&f.event_id),
            f.order_id.0,
            f.day.0,
            f.side,
            f.quantity,
            f.price.fen(),
            f.fees.commission.fen(),
            f.fees.transfer.fen(),
            f.fees.tax.fen(),
            f.fees.total()?.fen(),
            f.simulated_at.0,
            f.risk_checked_at.0,
            f.evidence.opens_at.0,
            f.evidence.closes_at.0,
            f.evidence.available_at.0,
            csv_cell(&f.evidence.provenance.source_version),
            f.evidence.provenance.dataset_hash
        ));
        if dataset.historical.is_some() {
            fills_csv.pop();
            fills_csv.push_str(&format!(
                ",{}\n",
                csv_cell(f.historical_execution.as_deref().unwrap_or("unavailable"))
            ));
        }
    }
    let mut positions_csv = String::from("market,code,acquired_on,shares\n");
    for p in &final_state.snapshot.positions {
        positions_csv.push_str(&format!(
            "{:?},{},{},{}\n",
            p.instrument.market, p.instrument.code, p.acquired_on.0, p.quantity
        ));
    }
    let mut files = vec![
        ("events.json", events_json),
        ("daily.csv", daily_csv.into_bytes()),
        ("orders.csv", orders_csv.into_bytes()),
        ("fills.csv", fills_csv.into_bytes()),
        ("positions.csv", positions_csv.into_bytes()),
        ("report.json", report_json),
    ];
    if dataset.cash_dividends.is_some() {
        files.push((
            "cash-dividends.json",
            serde_json::to_vec_pretty(&dividend_actions).map_err(|e| e.to_string())?,
        ));
    }
    publish::publish(out, &files)
}
