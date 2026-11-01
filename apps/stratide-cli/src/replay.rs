use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};
use stratide_contracts::*;
use stratide_ledger::{
    Command, DailyBar, DataMode, FeeSchedule, Genesis, Ledger, OpeningEvidence, Provenance,
};

pub(super) mod benchmark;
mod cash_dividend;
mod historical;
mod report;

const DAY_MS: i64 = 86_400_000;
const STRATEGY_VERSION: &str = "first-buy-second-sell-third-risk-probe-v1";
const STRATEGY_SPEC: &str = "v1;session-index-0:buy-100;session-index-2:sell-100;session-index-3:buy-10000;only-status-verified;limit=available-close;earliest=available+1ms;expiry=available+7d;one-instrument";

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Dataset {
    schema_version: u32,
    mode: DataMode,
    source: String,
    license: String,
    source_version: String,
    timezone: String,
    price_semantics: String,
    instrument: Instrument,
    fee: FeeInput,
    sessions: Vec<Session>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    historical: Option<historical::HistoricalMetadata>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    cash_dividends: Option<Vec<stratide_ledger::cash_dividend::CashDividendV1>>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct FeeInput {
    version: String,
    source: String,
    valid_from: TradingDay,
    valid_through: TradingDay,
    commission_ppm: u32,
    minimum_commission_fen: i64,
    transfer_ppm: u32,
    sell_tax_ppm: u32,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RulesInput {
    available_at: Timestamp,
    source: String,
    tradable: bool,
    settlement: SettlementRule,
    buy_lot: i64,
    sell_lot: i64,
    allow_odd_lot_liquidation: bool,
    tick_size_fen: i64,
    min_price_fen: i64,
    max_price_fen: i64,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct OpeningInput {
    price_fen: i64,
    as_of: Timestamp,
    available_at: Timestamp,
    source: String,
    rules: RulesInput,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Session {
    day: TradingDay,
    opens_at: Timestamp,
    closes_at: Timestamp,
    available_at: Timestamp,
    open_fen: i64,
    high_fen: i64,
    low_fen: i64,
    close_fen: i64,
    volume_shares: i64,
    capacity_shares: i64,
    status_verified: bool,
    opening: Option<OpeningInput>,
    rules: RulesInput,
}

fn money(fen: i64) -> Result<Cny, String> {
    Cny::from_fen(fen).map_err(|e| e.to_string())
}

fn days_from_civil(day: TradingDay) -> Result<i64, String> {
    if !day.is_valid() {
        return Err("交易日不是有效公历日期".into());
    }
    let mut y = i64::from(day.0 / 10_000);
    let m = i64::from(day.0 / 100 % 100);
    let d = i64::from(day.0 % 100);
    if m <= 2 {
        y -= 1;
    }
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = m + if m > 2 { -3 } else { 9 };
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    Ok(era * 146_097 + doe - 719_468)
}

fn local_day_start(day: TradingDay) -> Result<i64, String> {
    days_from_civil(day)?
        .checked_mul(DAY_MS)
        .and_then(|v| v.checked_sub(8 * 3_600_000))
        .ok_or_else(|| "交易日时间溢出".into())
}

impl RulesInput {
    fn to_rules(&self, instrument: &Instrument, day: TradingDay) -> Result<TradingRules, String> {
        Ok(TradingRules {
            instrument: instrument.clone(),
            trading_day: day,
            available_at: self.available_at,
            source: self.source.clone(),
            tradable: self.tradable,
            settlement: self.settlement,
            buy_lot: self.buy_lot,
            sell_lot: self.sell_lot,
            allow_odd_lot_liquidation: self.allow_odd_lot_liquidation,
            tick_size: money(self.tick_size_fen)?,
            min_price: money(self.min_price_fen)?,
            max_price: money(self.max_price_fen)?,
        })
    }
}

impl Dataset {
    fn validate(&self) -> Result<(), String> {
        if !matches!(self.schema_version, 1..=3)
            || self.sessions.is_empty()
            || !self.instrument.is_valid()
            || self.source.trim().is_empty()
            || self.license.trim().is_empty()
            || self.source_version.trim().is_empty()
            || self.timezone != "Asia/Shanghai"
            || self.price_semantics != "unadjusted_cny_fen"
        {
            return Err("输入 schema/来源/许可/证券/时区/未复权价格语义不完整".into());
        }
        if self.schema_version == 3 {
            cash_dividend::validate(self)?;
        } else {
            if self.cash_dividends.is_some() {
                return Err("分红必须显式 opt-in schema v3 / ledger v4".into());
            }
            historical::validate(self)?;
        }
        if self.mode == DataMode::HistoricalReplay && self.source.contains("synthetic") {
            return Err("人工合成来源不得标为 historical_replay".into());
        }
        let fee = self.fee_schedule()?;
        let mut last_day = None;
        let mut last_available = None;
        for s in &self.sessions {
            let start = local_day_start(s.day)?;
            if last_day.is_some_and(|d| s.day <= d)
                || s.opens_at.0 != start + 9 * 3_600_000 + 30 * 60_000
                || s.closes_at.0 != start + 15 * 3_600_000
                || s.opens_at >= s.closes_at
                || s.available_at < s.closes_at
                || s.available_at.0 - s.closes_at.0 > 7 * DAY_MS
                || last_available.is_some_and(|t| s.opens_at <= t)
                || s.volume_shares < 0
                || s.capacity_shares < 0
                || s.capacity_shares > s.volume_shares
                || s.open_fen <= 0
                || s.low_fen <= 0
                || s.low_fen > s.open_fen
                || s.high_fen < s.open_fen
                || s.high_fen < s.close_fen
                || s.close_fen < s.low_fen
            {
                return Err(format!(
                    "{}：日期乱序/重复、时间可得性或 OHLC/容量无效",
                    s.day.0
                ));
            }
            fee.validate(&self.instrument, s.day)?;
            let r = s.rules.to_rules(&self.instrument, s.day)?;
            if r.source.trim().is_empty()
                || r.available_at > s.available_at
                || r.available_at.0 < start
                || r.available_at.0 < 0
                || r.tick_size == Cny::ZERO
                || r.min_price == Cny::ZERO
                || r.max_price < r.min_price
                || r.buy_lot <= 0
                || r.sell_lot <= 0
                || [s.open_fen, s.high_fen, s.low_fen, s.close_fen]
                    .iter()
                    .any(|p| {
                        *p < r.min_price.fen()
                            || *p > r.max_price.fen()
                            || *p % r.tick_size.fen() != 0
                    })
            {
                return Err(format!("{}：收盘规则/价格带证据无效", s.day.0));
            }
            if let Some(o) = &s.opening {
                let opening_rules = o.rules.to_rules(&self.instrument, s.day)?;
                if o.price_fen != s.open_fen
                    || o.source.trim().is_empty()
                    || o.as_of != s.opens_at
                    || o.available_at < o.as_of
                    || o.available_at > s.opens_at
                    || o.rules.available_at > s.opens_at
                    || o.rules.source.trim().is_empty()
                    || o.rules.available_at.0 < start
                    || opening_rules.settlement != r.settlement
                    || opening_rules.buy_lot != r.buy_lot
                    || opening_rules.sell_lot != r.sell_lot
                    || opening_rules.allow_odd_lot_liquidation != r.allow_odd_lot_liquidation
                    || opening_rules.tick_size != r.tick_size
                    || opening_rules.min_price != r.min_price
                    || opening_rules.max_price != r.max_price
                {
                    return Err(format!("{}：独立开盘证据晚到或不相容", s.day.0));
                }
            }
            last_day = Some(s.day);
            last_available = Some(s.available_at);
        }
        Ok(())
    }

    fn fee_schedule(&self) -> Result<FeeSchedule, String> {
        Ok(FeeSchedule {
            version: self.fee.version.clone(),
            source: self.fee.source.clone(),
            instrument: self.instrument.clone(),
            valid_from: self.fee.valid_from,
            valid_through: self.fee.valid_through,
            commission_ppm: self.fee.commission_ppm,
            minimum_commission: money(self.fee.minimum_commission_fen)?,
            transfer_ppm: self.fee.transfer_ppm,
            sell_tax_ppm: self.fee.sell_tax_ppm,
        })
    }

    fn bar(&self, s: &Session, provenance: &Provenance) -> Result<DailyBar, String> {
        Ok(DailyBar {
            provenance: provenance.clone(),
            instrument: self.instrument.clone(),
            day: s.day,
            opens_at: s.opens_at,
            closes_at: s.closes_at,
            available_at: s.available_at,
            open: money(s.open_fen)?,
            high: money(s.high_fen)?,
            low: money(s.low_fen)?,
            close: money(s.close_fen)?,
            volume_shares: s.volume_shares,
            capacity_shares: s.capacity_shares,
            status_verified: s.status_verified,
        })
    }

    fn opening(&self, s: &Session) -> Result<Option<OpeningEvidence>, String> {
        s.opening
            .as_ref()
            .map(|o| {
                Ok(OpeningEvidence {
                    marks: vec![PositionMark {
                        instrument: self.instrument.clone(),
                        price: money(o.price_fen)?,
                        as_of: o.as_of,
                        available_at: o.available_at,
                        source: o.source.clone(),
                    }],
                    rules: o.rules.to_rules(&self.instrument, s.day)?,
                })
            })
            .transpose()
    }
}

fn load(path: &str, expected: &str) -> Result<(Dataset, Provenance), String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    let hash = format!("{:x}", Sha256::digest(&bytes));
    if expected.len() != 64 || expected != hash {
        return Err(format!("输入 SHA-256 不匹配：实际 {hash}"));
    }
    let dataset: Dataset = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    dataset.validate()?;
    let provenance = Provenance {
        mode: dataset.mode.clone(),
        source_version: format!(
            "{} | {} | {}",
            dataset.source, dataset.source_version, dataset.license
        ),
        dataset_hash: hash,
        timezone: dataset.timezone.clone(),
        price_semantics: dataset.price_semantics.clone(),
    };
    Ok((dataset, provenance))
}

pub fn run(args: &[String]) -> Result<(), String> {
    let is_dividend = args
        .first()
        .is_some_and(|s| s.starts_with("paper-dividend-"));
    let is_benchmark = args
        .first()
        .is_some_and(|s| s == "paper-dividend-benchmark");
    let is_cash_benchmark = args
        .first()
        .is_some_and(|s| s == "paper-dividend-cash-benchmark");
    let is_replay = args
        .first()
        .is_some_and(|s| s == "paper-replay" || s == "paper-dividend-replay")
        || is_benchmark
        || is_cash_benchmark;
    if args.len() < 6 || args[4] != "--sha256" {
        return Err("用法：paper-replay/paper-report <输入JSON> <账本目录> <报表目录> --sha256 <SHA256> [六项资金风险参数]".into());
    }
    let (dataset, provenance) = load(&args[1], &args[5])?;
    if is_dividend != dataset.cash_dividends.is_some() {
        return Err(
            "分红隔离输入须使用 paper-dividend-replay/report/benchmark；旧模式禁止注入".into(),
        );
    }
    let ledger_path = Path::new(&args[2]);
    let config = if is_replay {
        let mut c = super::config(&args[6..])?;
        c.account_id = "replay-account".into();
        c.deployment = DeploymentIdentity {
            group_id: "replay-group".into(),
            strategy_id: if dataset.historical.is_some() {
                "sma-cross"
            } else {
                "two-signal-example"
            }
            .into(),
            frozen_version: historical::strategy_version(&dataset).into(),
            deployment_id: if dataset.historical.is_some() {
                "historical-sma-v1"
            } else {
                "replay-v1"
            }
            .into(),
        };
        c.max_snapshot_age_ms = 7 * DAY_MS;
        c.max_mark_age_ms = 7 * DAY_MS;
        if is_dividend {
            c.account_id = if is_cash_benchmark {
                "dividend-cash-account"
            } else if is_benchmark {
                "dividend-benchmark-account"
            } else {
                "dividend-model-account"
            }
            .into();
            c.deployment.strategy_id = if is_cash_benchmark {
                "dividend-cash"
            } else if is_benchmark {
                "dividend-buy-hold"
            } else {
                "dividend-lifecycle-probe"
            }
            .into();
            c.deployment.frozen_version = cash_dividend::VERSION.into();
            c.deployment.deployment_id = if is_cash_benchmark {
                "dividend-cash-v1"
            } else if is_benchmark {
                "dividend-buy-hold-v1"
            } else {
                "dividend-lifecycle-v1"
            }
            .into();
        }
        Some(c)
    } else {
        if args.len() != 6 {
            return Err("paper-report 不接受资金或策略配置改写".into());
        }
        None
    };
    let mut ledger = if ledger_path.exists() {
        Ledger::open(ledger_path)?
    } else if let Some(c) = &config {
        if let Some(parent) = ledger_path.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("账本父目录不可用：{e}"))?;
        }
        let genesis = Genesis {
            config: c.clone(),
            provenance: provenance.clone(),
            at: Timestamp(dataset.sessions[0].opens_at.0 - 1),
            day: dataset.sessions[0].day,
        };
        if let Some(events) = &dataset.cash_dividends {
            Ledger::create_cash_dividend_v4(ledger_path, genesis, events.clone())?
        } else {
            Ledger::create(ledger_path, genesis)?
        }
    } else {
        return Err("报告账本不存在".into());
    };
    if ledger.state().provenance != provenance
        || config.as_ref().is_some_and(|c| ledger.state().config != *c)
        || is_dividend != (ledger.schema_version() == 4)
        || dataset.cash_dividends.as_ref().is_some_and(|events| {
            ledger
                .state()
                .cash_dividends
                .as_ref()
                .is_none_or(|b| b.events.iter().map(|a| &a.event).ne(events.iter()))
        })
    {
        return Err("账本输入哈希/来源或本金/风险配置不匹配，禁止续算".into());
    }
    let commands = if is_dividend {
        cash_dividend::commands(&dataset, &provenance, &ledger.state().config)?
    } else {
        commands(&dataset, &provenance, &ledger.state().config)?
    };
    if is_replay {
        for (id, command) in &commands {
            ledger.execute(id, command.clone())?;
        }
    }
    report::export(&dataset, &ledger, &commands, Path::new(&args[3]))?;
    println!(
        "模式：{:?}；输入 SHA-256：{}；账本尾摘要：{}；报告：{}",
        dataset.mode,
        provenance.dataset_hash,
        ledger.head(),
        args[3]
    );
    Ok(())
}

fn commands(
    dataset: &Dataset,
    provenance: &Provenance,
    config: &PaperAccountConfig,
) -> Result<Vec<(String, Command)>, String> {
    if dataset.historical.is_some() {
        return historical::commands(dataset, provenance, config);
    }
    let fee = dataset.fee_schedule()?;
    let mut commands = Vec::new();
    for (index, session) in dataset.sessions.iter().enumerate() {
        let bar = dataset.bar(session, provenance)?;
        let rules = session.rules.to_rules(&dataset.instrument, session.day)?;
        commands.push((
            format!("replay-session-{}", session.day.0),
            Command::Match {
                now: session.available_at,
                day: session.day,
                instrument: dataset.instrument.clone(),
                bar: Some(bar.clone()),
                rules: Some(rules.clone()),
                opening: dataset.opening(session)?,
            },
        ));
        if session.status_verified && (index == 0 || index == 2 || index == 3) {
            let side = if index == 2 { Side::Sell } else { Side::Buy };
            let proposal = OrderProposal {
                proposal_id: ProposalId(if index == 0 { 1 } else { index as u128 }),
                account_id: config.account_id.clone(),
                deployment: config.deployment.clone(),
                instrument: dataset.instrument.clone(),
                side,
                quantity: if index == 3 { 10_000 } else { 100 },
                limit_price: bar.close,
                decision_at: session.available_at,
                data_available_at: session.available_at,
                earliest_execution_at: Timestamp(
                    session.available_at.0.checked_add(1).ok_or("时间溢出")?,
                ),
                expires_at: Timestamp(
                    session
                        .available_at
                        .0
                        .checked_add(7 * DAY_MS)
                        .ok_or("时间溢出")?,
                ),
            };
            commands.push((
                format!("replay-signal-{}", session.day.0),
                Command::Submit {
                    proposal,
                    now: session.available_at,
                    day: session.day,
                    rules: Some(rules),
                    fees: Some(fee.clone()),
                },
            ));
        }
    }
    Ok(commands)
}
