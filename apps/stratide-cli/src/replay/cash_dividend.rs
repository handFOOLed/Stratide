use super::*;
use stratide_ledger::cash_dividend::{CashDividendBook, DividendPhase};

pub(super) const VERSION: &str = "cash-dividend-lifecycle-v1";
pub(super) const SPEC: &str = "CASH_DIVIDEND_V1;synthetic-isolation;buy100-first-close;stale-sell100-record-close;cancel-at-ex;fresh-sell100-ex-close;cash-probe10000-next-close;benchmark=buy100-first-close-hold;no-PIT-no-forward-no-live";

pub(super) fn validate(d: &Dataset) -> Result<(), String> {
    if d.mode != DataMode::SyntheticTest
        || d.historical.is_some()
        || !d.source.starts_with("synthetic_test/")
        || d.sessions.iter().any(|s| {
            !s.status_verified
                || s.opening.is_none()
                || s.rules.settlement != SettlementRule::TPlusOne
                || s.rules.buy_lot != 100
                || s.rules.sell_lot != 100
                || s.rules.tick_size_fen != 1
        })
    {
        return Err("schema3 CLI 仅显式 synthetic_test、普通A股T+1/100股/1分与人工opening；真实证据不可直接启用".into());
    }
    let events = d.cash_dividends.as_ref().ok_or("缺冻结现金分红事件")?;
    let first = d.sessions.first().ok_or("缺时序输入")?;
    let last = d.sessions.last().ok_or("缺时序输入")?;
    CashDividendBook::new(
        events.clone(),
        &d.mode,
        Timestamp(first.opens_at.0 - 1),
        first.day,
    )?;
    for e in events {
        if e.instrument != d.instrument
            || e.payment_at > last.available_at
            || !d
                .sessions
                .iter()
                .any(|s| s.day == e.record_day && e.record_at >= s.available_at)
        {
            return Err("事件不在冻结证券/完整会话范围内；登记必须在可核验收盘之后".into());
        }
        for (at, day) in [(e.ex_at, e.ex_day), (e.payment_at, e.payment_day)] {
            let s = d
                .sessions
                .iter()
                .find(|s| s.day == day)
                .ok_or("缺公司行为时点价格")?;
            if at != s.opens_at {
                return Err("CLI V1 仅支持独立模型opening时点除息/支付；禁止借用盘后价格".into());
            }
        }
    }
    Ok(())
}

pub(super) fn commands(
    d: &Dataset,
    p: &Provenance,
    c: &PaperAccountConfig,
) -> Result<Vec<(String, Command)>, String> {
    let benchmark = c.deployment.strategy_id == "dividend-buy-hold";
    let cash_only = c.deployment.strategy_id == "dividend-cash";
    let fee = d.fee_schedule()?;
    // Sort by economic start, not the completed bar's accounting timestamp.
    // No company action may be injected into the unordered intraday interval.
    let mut scheduled: Vec<(i64, u8, String, Command)> = Vec::new();
    let events = d.cash_dividends.as_ref().ok_or("缺冻结事件")?;
    for s in &d.sessions {
        scheduled.push((
            s.opens_at.0,
            1,
            format!("dividend-session-{}", s.day.0),
            Command::Match {
                now: s.available_at,
                day: s.day,
                instrument: d.instrument.clone(),
                bar: Some(d.bar(s, p)?),
                rules: Some(s.rules.to_rules(&d.instrument, s.day)?),
                opening: d.opening(s)?,
            },
        ));
        let signal = if cash_only {
            None
        } else if s.day == d.sessions[0].day {
            Some((1, Side::Buy, 100))
        } else if !benchmark && events.iter().any(|e| e.record_day == s.day) {
            let i = events.iter().position(|e| e.record_day == s.day).unwrap() as u128;
            Some((2 + 10 * i, Side::Sell, 100))
        } else if !benchmark && events.iter().any(|e| e.ex_day == s.day) {
            let i = events.iter().position(|e| e.ex_day == s.day).unwrap() as u128;
            Some((3 + 10 * i, Side::Sell, 100))
        } else if !benchmark
            && d.sessions
                .iter()
                .find(|s| s.day > events[0].ex_day && s.day < events[0].payment_day)
                .is_some_and(|first| first.day == s.day)
        {
            Some((4, Side::Buy, 10_000))
        } else {
            None
        };
        if let Some((id, side, quantity)) = signal {
            let proposal = OrderProposal {
                proposal_id: ProposalId(id),
                account_id: c.account_id.clone(),
                deployment: c.deployment.clone(),
                instrument: d.instrument.clone(),
                side,
                quantity,
                limit_price: money(s.close_fen)?,
                decision_at: s.available_at,
                data_available_at: s.available_at,
                earliest_execution_at: Timestamp(s.available_at.0 + 1),
                expires_at: Timestamp(s.available_at.0 + 7 * DAY_MS),
            };
            scheduled.push((
                s.available_at.0,
                2,
                format!("dividend-signal-{id}"),
                Command::Submit {
                    proposal,
                    now: s.available_at,
                    day: s.day,
                    rules: Some(s.rules.to_rules(&d.instrument, s.day)?),
                    fees: Some(fee.clone()),
                },
            ));
        }
    }
    for e in events {
        for (phase, at, day) in [
            (DividendPhase::Record, e.record_at, e.record_day),
            (DividendPhase::Ex, e.ex_at, e.ex_day),
            (DividendPhase::Payment, e.payment_at, e.payment_day),
        ] {
            let s = d
                .sessions
                .iter()
                .find(|s| s.day == day)
                .ok_or("缺公司行为会话")?;
            let marks = if phase == DividendPhase::Record {
                vec![PositionMark {
                    instrument: d.instrument.clone(),
                    price: money(s.close_fen)?,
                    as_of: s.closes_at,
                    available_at: s.available_at,
                    source: "synthetic_test/record-close-model-v1".into(),
                }]
            } else {
                d.opening(s)?.ok_or("缺模型opening")?.marks
            };
            scheduled.push((
                at.0,
                0,
                format!("dividend-{}-{phase:?}", e.event_id),
                Command::CashDividendV1 {
                    event_id: e.event_id.clone(),
                    phase,
                    now: at,
                    day,
                    marks,
                },
            ));
        }
    }
    scheduled.sort_by_key(|(at, priority, _, _)| (*at, *priority));
    Ok(scheduled
        .into_iter()
        .map(|(_, _, id, cmd)| (id, cmd))
        .collect())
}
