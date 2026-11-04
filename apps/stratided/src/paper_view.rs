//! Verified projection of the selected physical paper ledger, never a study NAV.
use crate::snapshot::safe_json;
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, VecDeque},
    path::Path,
};
use stratide_ledger::Ledger;

pub fn load(path: &Path) -> Result<(Value, Value), String> {
    let ledger = Ledger::read(path)?;
    let s = ledger.state();
    if !s
        .provenance
        .source_version
        .starts_with("paper-eod-assumption-v1")
    {
        return Err("CURRENT_PAPER_LEDGER_REQUIRED".into());
    }
    let history = ledger.history()?;
    let mut by_day = BTreeMap::new();
    for entry in &history {
        by_day.insert(entry.state.snapshot.trading_day, &entry.state);
    }
    let pnl = |s: &stratide_ledger::State| {
        s.equity.map(|v| {
            i128::from(v.fen())
                - i128::from(s.config.initial_capital.fen())
                - i128::from(s.snapshot.equity_basis.net_external_flow_total_fen)
        })
    };
    let initial = s.config.initial_capital.fen();
    let returns = |state: &stratide_ledger::State| {
        if state.snapshot.equity_basis.net_external_flow_total_fen != 0 {
            None
        } else {
            pnl(state).map(|n| (n * 10000 / i128::from(initial)).to_string())
        }
    };
    let session = s.equity.map(|v| {
        i128::from(v.fen())
            - i128::from(s.snapshot.equity_basis.net_external_flow_today_fen)
            - i128::from(s.snapshot.equity_basis.day_start_equity.fen())
    });
    let reserved: i64 = s
        .snapshot
        .pending_orders
        .iter()
        .map(|p| p.reserved_cash.fen())
        .sum();
    let fee: i128 = s
        .fills
        .iter()
        .map(|f| i128::from(f.fees.total().expect("verified fees").fen()))
        .sum();
    let mut peak = i128::from(initial);
    let mut max_drawdown = Some(0_i128);
    for state in by_day.values() {
        if let Some(nav) = state.equity {
            let adjusted = i128::from(nav.fen())
                - i128::from(state.snapshot.equity_basis.net_external_flow_total_fen);
            peak = peak.max(adjusted);
            max_drawdown = max_drawdown.map(|d| d.max((peak - adjusted) * 10000 / peak));
        } else {
            max_drawdown = None;
        }
    }
    let account = json!({"account_id":s.config.account_id,"day":s.snapshot.trading_day,"nav_fen":s.equity.map(|v|v.fen()),
        "cash_fen":s.snapshot.cash.fen(),"available_cash_fen":s.snapshot.cash.fen()-reserved,"reserved_cash_fen":reserved,
        "session_pnl_fen":session,"cumulative_pnl_fen":pnl(s),"total_return_bps":returns(s),"max_daily_observation_drawdown_bps":max_drawdown,
        "metrics_reason":"存在外部资金流时不输出简单累计收益率；估值缺失时不输出回撤。日回撤仅覆盖账本已记录日期，包含 Paper 假设，不是连续真实观察。",
        "total_fee_fen":fee,"initial_nav_fen":initial,"external_flow_total_fen":s.snapshot.equity_basis.net_external_flow_total_fen,
        "valuation_error":s.valuation_error,"risk":s.risk,"deployment":s.config.deployment});
    let equity=by_day.values().map(|v|json!({"day":v.snapshot.trading_day,"nav_fen":v.equity.map(|n|n.fen()),"cash_fen":v.snapshot.cash.fen(),
        "cumulative_pnl_fen":pnl(v),"return_bps":returns(v),"valuation_error":v.valuation_error})).collect::<Vec<_>>();
    let mut instruments = BTreeMap::new();
    for lot in &s.snapshot.positions {
        instruments
            .entry(lot.instrument.code.clone())
            .or_insert_with(|| lot.instrument.clone());
    }
    let positions=instruments.values().map(|i| -> Result<Value,String> {
        let lots=s.snapshot.positions.iter().filter(|l|l.instrument==*i).collect::<Vec<_>>();
        let quantity:i64=lots.iter().map(|l|l.quantity).sum();
        let sellable:i64=lots.iter().filter(|l|l.acquired_on<s.snapshot.trading_day).map(|l|l.quantity).sum();
        let reserved_sell:i64=s.snapshot.pending_orders.iter().filter(|p|p.instrument==*i && p.side==stratide_contracts::Side::Sell).map(|p|p.quantity).sum();
        let mark=s.snapshot.marks.iter().find(|m|m.instrument==*i);
        let mut costs:VecDeque<(i64,i128)>=VecDeque::new();
        for fill in s.fills.iter().filter(|f| f.instrument==*i) {
            if fill.side==stratide_contracts::Side::Buy {
                costs.push_back((fill.quantity,i128::from(fill.price.fen())*i128::from(fill.quantity)+i128::from(fill.fees.total()?.fen())));
            } else {
                let mut remaining=fill.quantity;
                while remaining>0 {
                    let lot=costs.front_mut().ok_or("CURRENT_PAPER_COST_BASIS_MISMATCH")?;
                    let take=remaining.min(lot.0);
                    let cost=lot.1*i128::from(take)/i128::from(lot.0);
                    lot.0-=take;lot.1-=cost;remaining-=take;
                    if lot.0==0 {costs.pop_front();}
                }
            }
        }
        if costs.iter().map(|l|l.0).sum::<i64>()!=quantity {return Err("CURRENT_PAPER_COST_BASIS_MISMATCH".into());}
        let basis=costs.iter().map(|l|l.1).sum::<i128>();
        let value=if s.equity.is_some(){mark.map(|m|i128::from(m.price.fen())*i128::from(quantity))}else{None};
        Ok(json!({"instrument":i,"quantity":quantity,"sellable_shares":sellable-reserved_sell,"unsettled_shares":quantity-sellable,"reserved_sell_shares":reserved_sell,
            "market_value_fen":value,"cost_basis_fen":basis,"unrealized_pnl_fen":value.map(|v|v-basis),
            "lots":lots,"deployment":s.config.deployment,"price_series":Value::Null,"price_series_reason":"当前账本只提供可信估值"})
        )
    }).collect::<Result<Vec<_>,_>>()?;
    let fills=s.fills.iter().map(|f|json!({"fill_id":f.event_id,"order_id":f.order_id.0.to_string(),"day":f.day,"instrument":f.instrument,
        "side":f.side,"quantity":f.quantity,"price_fen":f.price.fen(),"fee_fen":f.fees.total().expect("verified fees").fen(),"fees":f.fees,
        "simulated_at":f.simulated_at,"risk_checked_at":f.risk_checked_at,"deployment":s.config.deployment,"execution_assumption":f.historical_execution,"source_version":f.evidence.provenance.source_version})).collect::<Vec<_>>();
    let orders=s.orders.iter().map(|o|json!({"order_id":o.proposal.proposal_id.0.to_string(),"day":o.accepted_on,"instrument":o.proposal.instrument,
        "side":o.proposal.side,"quantity":o.proposal.quantity,"confirmed_filled_shares":s.fills.iter().filter(|f|f.order_id==o.proposal.proposal_id).map(|f|f.quantity).sum::<i64>(),
        "remaining":o.remaining,"limit_fen":o.proposal.limit_price.fen(),"status":o.status,"reason":o.reason,"deployment":o.proposal.deployment})).collect::<Vec<_>>();
    let day = s.snapshot.trading_day.0.to_string();
    let synthetic = s.provenance.source_version.contains("synthetic_test");
    let meta = json!({"mode":if synthetic {"synthetic_test"}else{"ex_post_paper_assumption"},"source":"Owner selected Paper Ledger","source_version":s.provenance.source_version,"as_of":day,
        "first_day":history[0].state.snapshot.trading_day.0.to_string(),"last_day":day,"last_valid_valuation_at":s.equity.map(|_|s.snapshot.as_of.0.to_string()),
        "timezone":"Asia/Shanghai","evidence_class":if synthetic {"engine_test_only"}else{"EX_POST_OPEN_ASSUMPTION"},"snapshot_id":ledger.head(),"report_sha256":ledger.head(),
        "input_sha256":s.provenance.dataset_hash,"ledger_head":ledger.head(),"publication":"authoritative_paper_ledger","refresh_policy":"read_only_latest_transaction",
        "validation":"ledger_replay_and_digest_verified","forward_account":"not_verified","market_freshness":"eod_assumption_not_live",
        "execution_model":"EX_POST_OPEN_ASSUMPTION","gaps":[],"paper_receipts":s.paper_eod});
    Ok((
        meta,
        safe_json(
            json!({"account":account,"equity":equity,"positions":positions,"fills":fills,"orders":orders,
        "strategies":[{"deployment":s.config.deployment,"status":"paper_assumption_only","pnl_fen":Value::Null,"drawdown_bps":Value::Null,"unavailable_reason":"Paper 假设成交，不是策略交易资格"}]}),
        )?,
    ))
}
