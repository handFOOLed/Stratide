//! Explicit ex-post research bridge. No forward opening or admission authority.
use super::*;
use stratide_ledger::cash_dividend::{sha256_valid, CashDividendBook, DividendPhase};

pub(super) const PROTOCOL: &str = "historical_dividend_scenario_v1";

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Scenario {
    pub protocol: String,
    pub evidence_class: String,
    pub input_kind: String,
    pub assumption_sha256: String,
    pub evidence_bundle_sha256: String,
    pub real_historical_eligibility: String,
    pub real_pit_days_added: u32,
    pub manifest: serde_json::Value,
}

pub(super) fn validate(d: &Dataset) -> Result<(), String> {
    historical::validate(d)?;
    let s = d.scenario.as_ref().ok_or("缺历史情景声明")?;
    if s.protocol != PROTOCOL
        || s.evidence_class != "EXPLORATORY_EX_POST"
        || !matches!(
            s.input_kind.as_str(),
            "synthetic_test" | "frozen_authorized_history"
        )
        || s.real_historical_eligibility != "DENIED"
        || s.real_pit_days_added != 0
        || !sha256_valid(&s.assumption_sha256)
        || !sha256_valid(&s.evidence_bundle_sha256)
        || !s.manifest.is_object()
    {
        return Err("情景协议/来源SHA/真实资格声明无效".into());
    }
    let events = d.cash_dividends.as_ref().ok_or("缺现金分红模型")?;
    if events.len() != 1
        || events[0].record_day != TradingDay(20260715)
        || events[0].ex_day != TradingDay(20260716)
        || events[0].cash_amount_fen != 42
        || events[0].cash_unit != stratide_ledger::cash_dividend::CashUnit::PerShare
        || events[0].source_sha256 != s.evidence_bundle_sha256
    {
        return Err("V1 仅支持7/15登记、7/16除息的42分/股现金分红模型".into());
    }
    let first = &d.sessions[0];
    let last = d.sessions.last().ok_or("缺会话")?;
    if first.day != TradingDay(20260706)
        || last.day > TradingDay(20261028)
        || d.fee.valid_from != TradingDay(20260706)
        || d.fee.valid_through != TradingDay(20261231)
        || (
            d.fee.commission_ppm,
            d.fee.minimum_commission_fen,
            d.fee.transfer_ppm,
            d.fee.sell_tax_ppm,
        ) != (300, 500, 10, 500)
    {
        return Err("固定选窗/既有费用假设越界".into());
    }
    CashDividendBook::new(
        events.clone(),
        &d.mode,
        Timestamp(first.opens_at.0 - 1),
        first.day,
    )?;
    for e in events {
        let record = d
            .sessions
            .iter()
            .find(|x| x.day == e.record_day)
            .ok_or("缺登记日")?;
        if e.instrument != d.instrument
            || e.record_close_at != record.closes_at
            || e.record_at.0 != local_day_start(e.record_day)? + 19 * 3_600_000
            || e.record_at <= record.available_at
            || e.payment_at > last.available_at
        {
            return Err("登记必须在当日18:00模型输入之后19:00锁定".into());
        }
        for (at, day) in [(e.ex_at, e.ex_day), (e.payment_at, e.payment_day)] {
            let session = d
                .sessions
                .iter()
                .find(|x| x.day == day)
                .ok_or("缺除息/支付日")?;
            if at != session.opens_at {
                return Err("历史情景仅在显式事后模型opening执行除息/支付；不接受盘中插入".into());
            }
        }
    }
    Ok(())
}

pub(super) fn configure(
    c: &mut PaperAccountConfig,
    benchmark: bool,
    cash: bool,
) -> Result<(), String> {
    // The six parameters are the already frozen historical research contract.
    if (
        c.initial_capital.fen(),
        c.account_limits.max_order_commitment.fen(),
        c.account_limits.max_exposure.fen(),
        c.strategy_limits.max_exposure.fen(),
        c.account_limits.daily_loss.fen(),
        c.account_limits.drawdown.fen(),
    ) != (10_000_000, 500_000, 2_000_000, 2_000_000, 100_000, 500_000)
        || c.strategy_limits.daily_loss != c.account_limits.daily_loss
        || c.strategy_limits.drawdown != c.account_limits.drawdown
    {
        return Err("情景必须沿用冻结历史六项本金/风险参数".into());
    }
    c.account_id = if cash {
        "scenario-cash"
    } else if benchmark {
        "scenario-buy-hold"
    } else {
        "scenario-sma"
    }
    .into();
    c.deployment.strategy_id = if cash {
        "scenario-cash"
    } else if benchmark {
        "scenario-buy-hold"
    } else {
        "sma-cross"
    }
    .into();
    c.deployment.frozen_version = if cash {
        "cash-no-orders-v1"
    } else if benchmark {
        "first-close-next-open-fixed100-v1"
    } else {
        historical::VERSION
    }
    .into();
    c.deployment.deployment_id = PROTOCOL.into();
    Ok(())
}

pub(super) fn strategy_spec(c: &PaperAccountConfig) -> &'static str {
    match c.deployment.strategy_id.as_str() {
        "scenario-cash" => "cash-no-orders-v1;same-v4-dividend-clock;no-owner-flow",
        "scenario-buy-hold" => "first-close-next-open-fixed100-v1;one-entry;limit=close+ceil(2%)-band-interior;expiry=14d;next-session-IOC;next-open+1fen;no-terminal-sale;same-v4-dividend-clock",
        _ => historical::SPEC,
    }
}

pub(super) fn commands(
    d: &Dataset,
    p: &Provenance,
    c: &PaperAccountConfig,
) -> Result<Vec<(String, Command)>, String> {
    // Keep the original SMA implementation, warmup, limit and expiry unchanged.
    let mut base = historical::commands(d, p, c)?;
    if c.deployment.strategy_id == "scenario-cash"
        || c.deployment.strategy_id == "scenario-buy-hold"
    {
        base.retain(|(_, cmd)| !matches!(cmd, Command::Submit { .. }));
        if c.deployment.strategy_id == "scenario-buy-hold" {
            let s = &d.sessions[0];
            base.push((
                "scenario-benchmark-once".into(),
                Command::Submit {
                    proposal: OrderProposal {
                        proposal_id: ProposalId(1),
                        account_id: c.account_id.clone(),
                        deployment: c.deployment.clone(),
                        instrument: d.instrument.clone(),
                        side: Side::Buy,
                        quantity: 100,
                        limit_price: money(
                            s.close_fen
                                .checked_add(s.close_fen.checked_add(49).ok_or("限价溢出")? / 50)
                                .ok_or("限价溢出")?
                                .min(s.rules.max_price_fen - 1),
                        )?,
                        decision_at: s.available_at,
                        data_available_at: s.available_at,
                        earliest_execution_at: Timestamp(s.available_at.0 + 1),
                        expires_at: Timestamp(s.available_at.0 + 14 * DAY_MS),
                    },
                    now: s.available_at,
                    day: s.day,
                    rules: Some(s.rules.to_rules(&d.instrument, s.day)?),
                    fees: Some(d.fee_schedule()?),
                },
            ));
        }
    }
    let mut scheduled: Vec<_> = base
        .into_iter()
        .map(|(id, cmd)| {
            let at = match &cmd {
                Command::HistoricalNextOpenV1 { bar, .. } => bar.opens_at.0,
                Command::Submit { now, .. } => now.0,
                _ => unreachable!(),
            };
            (at, 1_u8, id, cmd)
        })
        .collect();
    for e in d.cash_dividends.as_ref().ok_or("缺事件")? {
        for (phase, at, day) in [
            (DividendPhase::Record, e.record_at, e.record_day),
            (DividendPhase::Ex, e.ex_at, e.ex_day),
            (DividendPhase::Payment, e.payment_at, e.payment_day),
        ] {
            let s = d
                .sessions
                .iter()
                .find(|s| s.day == day)
                .ok_or("缺事件会话")?;
            let record = phase == DividendPhase::Record;
            scheduled.push((at.0, 0, format!("scenario-{}-{phase:?}", e.event_id), Command::CashDividendV1 {
                event_id: e.event_id.clone(), phase, now: at, day,
                marks: vec![PositionMark { instrument: d.instrument.clone(), price: money(if record { s.close_fen } else { s.open_fen })?,
                    as_of: if record { s.closes_at } else { s.opens_at },
                    available_at: if record { s.available_at } else { s.opens_at },
                    source: "historical_ex_post_assumption/EX_POST_MODEL_ONLY; not historical receipt or forward opening".into(),
                }],
            }));
        }
    }
    scheduled.sort_by_key(|(at, priority, _, _)| (*at, *priority));
    Ok(scheduled
        .into_iter()
        .map(|(_, _, id, cmd)| (id, cmd))
        .collect())
}
