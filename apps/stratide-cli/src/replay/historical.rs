use super::*;

pub(super) const AVAILABILITY: &str = "assumed_historical_eod_availability_not_pit_verified";
pub(super) const EXECUTION: &str = "historical_ex_post_execution_assumption";
const VERSION: &str = "sma5-20-cross-fixed100-v1";
pub(super) const SPEC: &str = "sma5/20;integer-sums;20-session-warmup;strict-relation-cross;buy100-on-up;sell100-on-down;no-optimization;limit=close+/-ceil(2%)-clamped-to-known-day-band-interior;expiry=decision+14d;next-session-IOC;next-open+/-1fen;capacity100-fixed-not-daily-volume";

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct HistoricalMetadata {
    pub availability: String,
    pub execution: String,
    pub strategy: String,
    pub completeness: String,
    pub source_manifest: serde_json::Value,
}

pub(super) fn strategy_version(dataset: &Dataset) -> &'static str {
    if dataset.historical.is_some() {
        VERSION
    } else {
        STRATEGY_VERSION
    }
}

pub(super) fn validate(dataset: &Dataset) -> Result<(), String> {
    let Some(h) = &dataset.historical else {
        return if dataset.schema_version == 1 {
            Ok(())
        } else {
            Err("schema v2 必须带历史假设".into())
        };
    };
    if dataset.schema_version != 2
        || dataset.mode != DataMode::HistoricalReplay
        || dataset.instrument.market != Market::Shanghai
        || dataset.instrument.code != "600000"
        || h.availability != AVAILABILITY
        || h.execution != EXECUTION
        || h.strategy != VERSION
        || h.completeness != "complete_calendar_and_daily_rows"
        || !h.source_manifest.is_object()
        || dataset.sessions.iter().any(|s| {
            s.opening.is_some()
                || s.available_at.0 != local_day_start(s.day).unwrap_or(i64::MIN) + 18 * 3_600_000
                || s.capacity_shares != 100
                || s.rules.settlement != SettlementRule::TPlusOne
                || s.rules.buy_lot != 100
                || s.rules.sell_lot != 100
                || s.rules.tick_size_fen != 1
        })
    {
        return Err("历史 v2 仅支持 600000.SH、18:00 假设可得、固定 SMA5/20 与 next-open v1；禁止独立 opening 字段/前向标签".into());
    }
    Ok(())
}

pub(super) fn commands(
    dataset: &Dataset,
    provenance: &Provenance,
    config: &PaperAccountConfig,
) -> Result<Vec<(String, Command)>, String> {
    let mut result = Vec::new();
    let fee = dataset.fee_schedule()?;
    let mut closes = Vec::new();
    let mut previous_above = None;
    for s in &dataset.sessions {
        let bar = dataset.bar(s, provenance)?;
        let rules = s.rules.to_rules(&dataset.instrument, s.day)?;
        result.push((
            format!("replay-session-{}", s.day.0),
            Command::HistoricalNextOpenV1 {
                now: s.available_at,
                bar,
                rules: rules.clone(),
            },
        ));
        if !s.status_verified {
            closes.clear();
            previous_above = None;
            continue;
        }
        closes.push(i128::from(s.close_fen));
        if closes.len() < 20 {
            continue;
        }
        let n = closes.len();
        let fast: i128 = closes[n - 5..].iter().sum();
        let slow: i128 = closes[n - 20..].iter().sum();
        let above = fast * 4 > slow;
        let crossed = previous_above.is_some_and(|a| a != above);
        previous_above = Some(above);
        if !crossed {
            continue;
        }
        let side = if above { Side::Buy } else { Side::Sell };
        let offset = (s.close_fen + 49) / 50;
        let limit = if above {
            s.close_fen
                .checked_add(offset)
                .ok_or("限价溢出")?
                .min(s.rules.max_price_fen - 1)
        } else {
            (s.close_fen - offset).max(s.rules.min_price_fen + 1)
        };
        let p = OrderProposal {
            proposal_id: ProposalId(u128::from(s.day.0)),
            account_id: config.account_id.clone(),
            deployment: config.deployment.clone(),
            instrument: dataset.instrument.clone(),
            side,
            quantity: 100,
            limit_price: money(limit)?,
            decision_at: s.available_at,
            data_available_at: s.available_at,
            earliest_execution_at: Timestamp(s.available_at.0.checked_add(1).ok_or("时间溢出")?),
            expires_at: Timestamp(
                s.available_at
                    .0
                    .checked_add(14 * DAY_MS)
                    .ok_or("时间溢出")?,
            ),
        };
        result.push((
            format!("replay-signal-{}", s.day.0),
            Command::Submit {
                proposal: p,
                now: s.available_at,
                day: s.day,
                rules: Some(rules),
                fees: Some(fee.clone()),
            },
        ));
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    // Explicit artificial data used ONLY for engine correctness, not the real
    // historical smoke. No market row is committed in this fixture.
    fn fixture() -> Dataset {
        let path =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../samples/m0-pr03-synthetic.json");
        let mut d: Dataset = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
        d.schema_version = 2;
        d.mode = DataMode::HistoricalReplay;
        d.source = "unit-fixture-not-market-evidence".into();
        d.fee.valid_from = TradingDay(20261001);
        d.historical = Some(HistoricalMetadata {
            availability: AVAILABILITY.into(),
            execution: EXECUTION.into(),
            strategy: VERSION.into(),
            completeness: "complete_calendar_and_daily_rows".into(),
            source_manifest: serde_json::json!({"fixture":"synthetic_test; no source authenticity claim"}),
        });
        let template = d.sessions[0].clone();
        d.sessions = (0..40)
            .map(|i| {
                let mut s = template.clone();
                s.day = TradingDay(if i < 31 {
                    20261001 + i
                } else {
                    20261101 + i - 31
                });
                let start = local_day_start(s.day).unwrap();
                s.opens_at = Timestamp(start + 9 * 3_600_000 + 30 * 60_000);
                s.closes_at = Timestamp(start + 15 * 3_600_000);
                s.available_at = Timestamp(start + 18 * 3_600_000);
                s.close_fen = if i < 20 {
                    1000
                } else if i < 25 {
                    1100
                } else {
                    900
                };
                s.low_fen = 850;
                s.high_fen = 1150;
                s.open_fen = 1000;
                s.opening = None;
                s.rules.available_at = s.available_at;
                s.rules.min_price_fen = 800;
                s.rules.max_price_fen = 1200;
                s
            })
            .collect();
        d.validate().unwrap();
        d
    }

    fn config() -> PaperAccountConfig {
        super::super::super::config(
            &[
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
            ]
            .map(str::to_string),
        )
        .unwrap()
    }

    fn proposals(d: &Dataset) -> Vec<OrderProposal> {
        commands(d, &stratide_ledger::synthetic::provenance(), &config())
            .unwrap()
            .into_iter()
            .filter_map(|(_, c)| {
                if let Command::Submit { proposal, .. } = c {
                    Some(proposal)
                } else {
                    None
                }
            })
            .collect()
    }

    #[test]
    fn future_prices_and_appended_sessions_cannot_change_frozen_today_signal() {
        let d = fixture();
        let p = proposals(&d);
        assert_eq!(p.len(), 2);
        assert_eq!(p[0].decision_at, d.sessions[20].available_at);
        assert_eq!(p[0].side, Side::Buy);
        assert_eq!(p[1].side, Side::Sell);
        let mut prefix = d.clone();
        prefix.sessions.truncate(21);
        assert_eq!(proposals(&prefix), p[..1]);
        let mut changed = d.clone();
        changed.sessions[21].open_fen = 1050;
        changed.sessions[21].high_fen = 1190;
        changed.sessions[21].low_fen = 810;
        changed.sessions[21].close_fen = 820;
        changed.validate().unwrap();
        assert_eq!(proposals(&changed)[0], p[0]);
        prefix.sessions.truncate(20);
        assert!(proposals(&prefix).is_empty()); // No warmup backfill.
    }

    #[test]
    fn historical_adapter_cannot_supply_forward_opening_or_change_assumption_labels() {
        let mut d = fixture();
        d.sessions[0].opening = Some(OpeningInput {
            price_fen: 1000,
            as_of: d.sessions[0].opens_at,
            available_at: d.sessions[0].opens_at,
            source: "invented-from-history".into(),
            rules: d.sessions[0].rules.clone(),
        });
        assert!(d.validate().is_err());
        d.sessions[0].opening = None;
        d.historical.as_mut().unwrap().availability = "verified_pit".into();
        assert!(d.validate().is_err());
    }
}
