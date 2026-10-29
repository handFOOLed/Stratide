//! Read a published six-file report, never a Ledger or SQLite connection.
use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fs, io::Read, path::Path};
use stratide_contracts::{Instrument, PaperAccountConfig, PositionLot, TradingDay};
use stratide_ledger::{DataMode, Fill, OrderStatus, PaperOrder};

type Result<T> = std::result::Result<T, String>;
pub const FILES: [&str; 6] = [
    "report.json",
    "events.json",
    "daily.csv",
    "orders.csv",
    "fills.csv",
    "positions.csv",
];

// Missing is different from an explicit unavailable valuation.
fn required_option<'de, D, T>(d: D) -> std::result::Result<Option<T>, D::Error>
where
    D: serde::Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::deserialize(d)
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Daily {
    pub day: TradingDay,
    #[serde(deserialize_with = "required_option")]
    pub nav_fen: Option<i64>,
    pub cash_fen: i64,
    pub available_cash_fen: i64,
    pub reserved_cash_fen: i64,
    pub held_shares: i64,
    pub sellable_shares: i64,
    pub unsettled_shares: i64,
    pub reserved_sell_shares: i64,
    pub pending_orders: usize,
    pub cumulative_fee_fen: i64,
    #[serde(deserialize_with = "required_option")]
    pub realized_pnl_fen: Option<i128>,
    #[serde(deserialize_with = "required_option")]
    pub unrealized_pnl_fen: Option<i128>,
    #[serde(deserialize_with = "required_option")]
    pub remaining_cost_basis_fen: Option<i128>,
    pub external_flow_total_fen: i64,
    #[serde(deserialize_with = "required_option")]
    pub valuation_error: Option<String>,
}

#[derive(Deserialize)]
pub struct Report {
    pub report_schema: u32,
    pub ledger_schema: u32,
    pub mode: DataMode,
    pub paper_only: bool,
    pub source: String,
    pub source_version: String,
    pub evidence_class: String,
    pub timezone: String,
    pub price_semantics: String,
    pub input_sha256: String,
    pub config_sha256: String,
    pub ledger_head: String,
    pub first_day: TradingDay,
    pub last_day: TradingDay,
    pub instrument: Instrument,
    pub config: PaperAccountConfig,
    pub initial_nav_fen: i64,
    #[serde(deserialize_with = "required_option")]
    pub ending_nav_fen: Option<i64>,
    pub ending_cash_fen: i64,
    pub ending_available_cash_fen: i64,
    pub ending_held_shares: i64,
    pub ending_sellable_shares: i64,
    pub ending_unsettled_shares: i64,
    pub ending_pending_orders: usize,
    pub external_flow_total_fen: i64,
    pub total_fee_fen: i64,
    #[serde(deserialize_with = "required_option")]
    pub total_return_bps: Option<i128>,
    #[serde(deserialize_with = "required_option")]
    pub max_daily_observation_drawdown_bps: Option<i128>,
    pub daily: Vec<Daily>,
    pub orders: Vec<PaperOrder>,
    pub fills: Vec<Fill>,
    pub positions: Vec<PositionLot>,
    pub events: Vec<Value>,
    pub risk_rejections: Vec<PaperOrder>,
    pub missing_opening_evidence_sessions: usize,
    pub unverified_status_sessions: usize,
    pub unobserved_calendar_days_including_weekends: i64,
    pub historical_assumptions: Option<Value>,
    pub execution_model: Option<String>,
}

pub struct Snapshot {
    pub report: Report,
    pub metadata: Value,
}

fn require(ok: bool, message: &str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(message.into())
    }
}

pub fn read_bounded(path: &Path) -> Result<Vec<u8>> {
    const LIMIT: u64 = 64 * 1024 * 1024;
    let metadata = fs::symlink_metadata(path).map_err(|_| "无法读取指定报告文件".to_string())?;
    require(
        metadata.is_file() && metadata.len() <= LIMIT,
        "报告必须是普通文件且不超过 64 MiB",
    )?;
    let mut bytes = Vec::new();
    fs::File::open(path)
        .and_then(|f| f.take(LIMIT + 1).read_to_end(&mut bytes))
        .map_err(|_| "读取报告失败".to_string())?;
    require(bytes.len() as u64 <= LIMIT, "报告超过 64 MiB")?;
    Ok(bytes)
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn valid_hash(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|c| c.is_ascii_hexdigit())
}
fn text<T: ToString>(v: T) -> String {
    v.to_string()
}
fn opt<T: ToString>(v: Option<T>) -> String {
    v.map(text).unwrap_or_default()
}

/// Every financial integer is a decimal STRING on the wire, including quantities
/// and IDs. The browser must never round an i64 through a JS Number.
pub fn safe_json<T: Serialize>(value: T) -> Result<Value> {
    fn walk(v: &mut Value) -> Result<()> {
        match v {
            Value::Number(n) => {
                require(n.is_i64() || n.is_u64(), "不支持非整数/超出报表范围的数值")?;
                *v = Value::String(n.to_string());
            }
            Value::Array(a) => {
                for v in a {
                    walk(v)?;
                }
            }
            Value::Object(o) => {
                for v in o.values_mut() {
                    walk(v)?;
                }
            }
            _ => {}
        }
        Ok(())
    }
    let mut value = serde_json::to_value(value).map_err(|_| "报表数值超出受支持范围")?;
    walk(&mut value)?;
    Ok(value)
}

fn csv_matches(bytes: &[u8], headers: &[&str], expected: Vec<Vec<String>>) -> Result<()> {
    let mut reader = csv::Reader::from_reader(bytes);
    let actual = reader.headers().map_err(|_| "CSV 表头损坏")?;
    require(
        actual.iter().eq(headers.iter().copied()),
        "CSV 表头与支持的六报告版本不符",
    )?;
    let rows = reader
        .records()
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|_| "CSV 内容损坏")?;
    require(
        rows.len() == expected.len(),
        "六报告记录数不一致或报告不完整",
    )?;
    for (row, expected) in rows.iter().zip(expected) {
        require(
            row.iter().eq(expected.iter().map(String::as_str)),
            "六报告内容不一致，拒绝混用快照",
        )?;
    }
    Ok(())
}

fn validate_csv(files: &[Vec<u8>], r: &Report) -> Result<()> {
    let events: Vec<Value> = serde_json::from_slice(&files[1]).map_err(|_| "events.json 损坏")?;
    require(
        events == r.events,
        "events.json 与 report.json 不属于同一完整快照",
    )?;
    csv_matches(
        &files[2],
        &[
            "day",
            "nav_fen",
            "cash_fen",
            "available_cash_fen",
            "reserved_cash_fen",
            "held_shares",
            "sellable_shares",
            "unsettled_shares",
            "reserved_sell_shares",
            "pending_orders",
            "cumulative_fee_fen",
            "realized_pnl_fen",
            "unrealized_pnl_fen",
            "remaining_cost_basis_fen",
            "external_flow_total_fen",
            "valuation_error",
        ],
        r.daily
            .iter()
            .map(|d| {
                vec![
                    text(d.day.0),
                    opt(d.nav_fen),
                    text(d.cash_fen),
                    text(d.available_cash_fen),
                    text(d.reserved_cash_fen),
                    text(d.held_shares),
                    text(d.sellable_shares),
                    text(d.unsettled_shares),
                    text(d.reserved_sell_shares),
                    text(d.pending_orders),
                    text(d.cumulative_fee_fen),
                    opt(d.realized_pnl_fen),
                    opt(d.unrealized_pnl_fen),
                    opt(d.remaining_cost_basis_fen),
                    text(d.external_flow_total_fen),
                    d.valuation_error.clone().unwrap_or_default(),
                ]
            })
            .collect(),
    )?;
    csv_matches(
        &files[3],
        &[
            "proposal_id",
            "day",
            "side",
            "quantity",
            "limit_fen",
            "status",
            "remaining",
            "reason",
        ],
        r.orders
            .iter()
            .map(|o| {
                vec![
                    text(o.proposal.proposal_id.0),
                    text(o.accepted_on.0),
                    format!("{:?}", o.proposal.side),
                    text(o.proposal.quantity),
                    text(o.proposal.limit_price.fen()),
                    format!("{:?}", o.status),
                    text(o.remaining),
                    o.reason.clone(),
                ]
            })
            .collect(),
    )?;
    let historical = r.fills.iter().any(|f| f.historical_execution.is_some());
    let mut headers = vec![
        "fill_id",
        "order_id",
        "day",
        "side",
        "quantity",
        "price_fen",
        "commission_fen",
        "transfer_fen",
        "tax_fen",
        "total_fee_fen",
        "simulated_at",
        "risk_checked_at",
        "market_opens_at",
        "market_closes_at",
        "bar_available_at",
        "source_version",
        "input_sha256",
    ];
    // A historical run with zero fills still has this column.
    if historical || matches!(r.mode, DataMode::HistoricalReplay) {
        headers.push("execution_assumption");
    }
    csv_matches(
        &files[4],
        &headers,
        r.fills
            .iter()
            .map(|f| {
                let mut row = vec![
                    f.event_id.clone(),
                    text(f.order_id.0),
                    text(f.day.0),
                    format!("{:?}", f.side),
                    text(f.quantity),
                    text(f.price.fen()),
                    text(f.fees.commission.fen()),
                    text(f.fees.transfer.fen()),
                    text(f.fees.tax.fen()),
                    text(f.fees.total().expect("validated fees").fen()),
                    text(f.simulated_at.0),
                    text(f.risk_checked_at.0),
                    text(f.evidence.opens_at.0),
                    text(f.evidence.closes_at.0),
                    text(f.evidence.available_at.0),
                    f.evidence.provenance.source_version.clone(),
                    f.evidence.provenance.dataset_hash.clone(),
                ];
                if headers.len() == 18 {
                    row.push(
                        f.historical_execution
                            .clone()
                            .unwrap_or_else(|| "unavailable".into()),
                    );
                }
                row
            })
            .collect(),
    )?;
    csv_matches(
        &files[5],
        &["market", "code", "acquired_on", "shares"],
        r.positions
            .iter()
            .map(|p| {
                vec![
                    format!("{:?}", p.instrument.market),
                    p.instrument.code.clone(),
                    text(p.acquired_on.0),
                    text(p.quantity),
                ]
            })
            .collect(),
    )
}

fn validate(r: &Report) -> Result<()> {
    require(
        r.report_schema == 1 && r.ledger_schema == 3 && r.paper_only,
        "仅支持 paper-only 六报告 schema 1 / ledger 3",
    )?;
    require(
        !r.source.trim().is_empty()
            && !r.source_version.trim().is_empty()
            && r.timezone == "Asia/Shanghai"
            && r.price_semantics == "unadjusted_cny_fen"
            && [&r.input_sha256, &r.config_sha256, &r.ledger_head]
                .into_iter()
                .all(|s| valid_hash(s)),
        "报告来源、单位、时区或摘要缺失",
    )?;
    let evidence = match r.mode {
        DataMode::SyntheticTest => "engine_test_only",
        DataMode::HistoricalReplay => "exploratory_historical_replay_not_pit_verified",
    };
    require(r.evidence_class == evidence, "数据模式和证据等级冲突")?;
    require(
        r.config.initial_capital.fen() == r.initial_nav_fen
            && r.initial_nav_fen > 0
            && r.initial_nav_fen <= r.config.authorized_principal.fen()
            && r.config.deployment.is_valid()
            && !r.config.account_id.trim().is_empty(),
        "账户身份或已授权模拟本金冲突",
    )?;
    require(
        hash(&serde_json::to_vec(&r.config).map_err(|_| "配置损坏")?) == r.config_sha256,
        "配置摘要不匹配",
    )?;
    require(
        !r.daily.is_empty()
            && r.daily.first().unwrap().day == r.first_day
            && r.daily.last().unwrap().day == r.last_day,
        "每日数据为空或区间不一致",
    )?;
    let mut previous = None;
    for d in &r.daily {
        require(
            [
                d.realized_pnl_fen,
                d.unrealized_pnl_fen,
                d.remaining_cost_basis_fen,
                cumulative(r, d),
            ]
            .into_iter()
            .flatten()
            .all(|n| i64::try_from(n).is_ok()),
            "报表金额超出支持的整数分范围",
        )?;
        require(
            d.day.is_valid() && previous.is_none_or(|p| p < d.day),
            "估值日期无效、重复或逆序",
        )?;
        previous = Some(d.day);
        require(
            [
                d.cash_fen,
                d.available_cash_fen,
                d.reserved_cash_fen,
                d.held_shares,
                d.sellable_shares,
                d.unsettled_shares,
                d.reserved_sell_shares,
                d.cumulative_fee_fen,
            ]
            .iter()
            .all(|v| *v >= 0)
                && i128::from(d.available_cash_fen) + i128::from(d.reserved_cash_fen)
                    == i128::from(d.cash_fen)
                && i128::from(d.sellable_shares)
                    + i128::from(d.unsettled_shares)
                    + i128::from(d.reserved_sell_shares)
                    == i128::from(d.held_shares),
            "每日资金/股数/预留不守恒",
        )?;
        if let Some(nav) = d.nav_fen {
            require(
                nav >= d.cash_fen && d.valuation_error.is_none(),
                "估值与现金/缺口状态冲突",
            )?;
            require(
                (d.held_shares == 0) == (nav == d.cash_fen),
                "持仓数量与报告市值冲突",
            )?;
            if let (Some(realized), Some(unrealized)) = (d.realized_pnl_fen, d.unrealized_pnl_fen) {
                require(
                    realized.checked_add(unrealized)
                        == Some(
                            i128::from(nav)
                                - i128::from(r.initial_nav_fen)
                                - i128::from(d.external_flow_total_fen),
                        ),
                    "每日 P&L 与 NAV 不一致",
                )?;
            }
        } else {
            require(
                d.valuation_error
                    .as_ref()
                    .is_some_and(|s| !s.trim().is_empty()),
                "空估值必须保留缺失原因",
            )?;
        }
    }
    let last = r.daily.last().unwrap();
    let expected_return = if last.external_flow_total_fen == 0 {
        cumulative(r, last).map(|p| p * 10_000 / i128::from(r.initial_nav_fen))
    } else {
        None
    };
    let mut peak = i128::from(r.initial_nav_fen);
    let mut expected_drawdown = Some(0_i128);
    for d in &r.daily {
        if let Some(nav) = d
            .nav_fen
            .and_then(|n| n.checked_sub(d.external_flow_total_fen))
        {
            peak = peak.max(i128::from(nav));
            expected_drawdown =
                expected_drawdown.map(|m| m.max((peak - i128::from(nav)) * 10_000 / peak));
        } else {
            expected_drawdown = None;
        }
    }
    require(
        r.total_return_bps == expected_return
            && r.max_daily_observation_drawdown_bps == expected_drawdown,
        "收益/回撤摘要与每日记录不一致",
    )?;
    require(
        [r.total_return_bps, r.max_daily_observation_drawdown_bps]
            .into_iter()
            .flatten()
            .all(|n| i64::try_from(n).is_ok()),
        "报表指标超出支持范围",
    )?;
    require(
        last.nav_fen == r.ending_nav_fen
            && last.cash_fen == r.ending_cash_fen
            && last.available_cash_fen == r.ending_available_cash_fen
            && last.held_shares == r.ending_held_shares
            && last.sellable_shares == r.ending_sellable_shares
            && last.unsettled_shares == r.ending_unsettled_shares
            && last.pending_orders == r.ending_pending_orders
            && last.external_flow_total_fen == r.external_flow_total_fen
            && last.cumulative_fee_fen == r.total_fee_fen,
        "账户摘要与末日记录不一致",
    )?;
    let held: i128 = r.positions.iter().map(|p| i128::from(p.quantity)).sum();
    require(
        held == i128::from(last.held_shares)
            && r.positions.iter().all(|p| {
                p.quantity > 0
                    && p.instrument == r.instrument
                    && p.acquired_on.is_valid()
                    && p.acquired_on <= r.last_day
            }),
        "持仓与账户末日不一致",
    )?;
    let mut ids = BTreeSet::new();
    for o in &r.orders {
        require(
            ids.insert(o.proposal.proposal_id.0)
                && o.proposal.account_id == r.config.account_id
                && o.proposal.deployment == r.config.deployment
                && o.proposal.instrument == r.instrument
                && o.proposal.quantity > 0
                && o.remaining >= 0
                && o.remaining <= o.proposal.quantity
                && o.accepted_on.is_valid(),
            "订单身份/数量/归属不一致",
        )?;
        let filled: i128 = r
            .fills
            .iter()
            .filter(|f| f.order_id == o.proposal.proposal_id)
            .map(|f| i128::from(f.quantity))
            .sum();
        require(
            filled + i128::from(o.remaining) == i128::from(o.proposal.quantity)
                && match o.status {
                    OrderStatus::Filled => o.remaining == 0,
                    OrderStatus::Rejected | OrderStatus::Open => filled == 0,
                    OrderStatus::PartiallyFilled => filled > 0 && o.remaining > 0,
                    OrderStatus::Expired => o.remaining > 0,
                },
            "订单状态不能作为已确认成交",
        )?;
    }
    require(
        r.orders.iter().filter(|o| o.active()).count() == last.pending_orders
            && r.orders
                .iter()
                .filter(|o| o.status == OrderStatus::Rejected)
                .eq(r.risk_rejections.iter()),
        "订单摘要不一致",
    )?;
    let mut fill_ids = BTreeSet::new();
    let mut fee_total = 0_i128;
    for f in &r.fills {
        let o = r
            .orders
            .iter()
            .find(|o| o.proposal.proposal_id == f.order_id)
            .ok_or("成交缺少所属订单")?;
        let fee = f.fees.total()?;
        require(
            fill_ids.insert(&f.event_id)
                && f.quantity > 0
                && f.price.fen() > 0
                && f.instrument == r.instrument
                && f.side == o.proposal.side
                && f.day.is_valid()
                && f.day > o.accepted_on
                && f.evidence.provenance.mode == r.mode
                && f.evidence.provenance.dataset_hash == r.input_sha256
                && f.fees.commission.fen() >= 0
                && f.fees.transfer.fen() >= 0
                && f.fees.tax.fen() >= 0,
            "模拟成交证据/归属不一致",
        )?;
        fee_total += i128::from(fee.fen());
    }
    require(
        fee_total == i128::from(r.total_fee_fen),
        "成交实付费用合计不一致",
    )?;
    let last_event = r.events.last().ok_or("缺少已发布事件")?;
    require(
        last_event["ledger_digest"].as_str() == Some(&r.ledger_head)
            && last_event["cash_fen"].as_i64() == Some(last.cash_fen),
        "事件尾与账户摘要不一致",
    )?;
    Ok(())
}

fn cumulative(r: &Report, d: &Daily) -> Option<i128> {
    d.nav_fen.map(|n| {
        i128::from(n) - i128::from(r.initial_nav_fen) - i128::from(d.external_flow_total_fen)
    })
}

impl Snapshot {
    pub fn load(path: &Path) -> Result<Self> {
        require(
            fs::symlink_metadata(path)
                .map_err(|_| "指定报告目录不存在")?
                .is_dir(),
            "必须指定已发布的普通报告目录",
        )?;
        let files = FILES
            .iter()
            .map(|name| read_bounded(&path.join(name)))
            .collect::<Result<Vec<_>>>()?;
        let r: Report = serde_json::from_slice(&files[0])
            .map_err(|_| "report.json 缺损、不支持的模式或字段类型错误")?;
        validate(&r)?;
        validate_csv(&files, &r)?;
        // Re-read the fixed six paths before accepting; a concurrently replaced
        // publication is rejected, never assembled into an account in memory.
        for (name, before) in FILES.iter().zip(&files) {
            require(
                read_bounded(&path.join(name))? == *before,
                "报告在读取期间变化，请在发布结束后重启",
            )?;
        }
        let mut digest = Sha256::new();
        for (name, bytes) in FILES.iter().zip(&files) {
            digest.update(name.as_bytes());
            digest.update(Sha256::digest(bytes));
        }
        let valid_day = r.daily.iter().rfind(|d| d.nav_fen.is_some()).map(|d| d.day);
        let offset = FixedOffset::east_opt(8 * 3600).unwrap();
        let valid_at = valid_day.and_then(|day| {
            r.events.iter().rev().find_map(|e| {
                let ts = e["account_as_of"].as_i64()?;
                let date = DateTime::from_timestamp_millis(ts)?
                    .with_timezone(&offset)
                    .format("%Y%m%d")
                    .to_string();
                (date == day.0.to_string() && e["nav_fen"].as_i64().is_some())
                    .then_some(ts.to_string())
            })
        });
        let metadata = json!({
            "mode": r.mode, "source": r.source, "source_version": r.source_version,
            "as_of": valid_day.map(|d| d.0.to_string()), "last_day": r.last_day.0.to_string(),
            "first_day": r.first_day.0.to_string(), "last_valid_valuation_at": valid_at,
            "timezone": r.timezone, "evidence_class": r.evidence_class,
            "snapshot_id": format!("{:x}", digest.finalize()), "report_sha256": hash(&files[0]),
            "input_sha256": r.input_sha256, "ledger_head": r.ledger_head,
            "publication": "last_published_snapshot", "refresh_policy": "explicit_process_restart",
            "validation": "six_report_consistency_checked_not_ledger_requalification",
            "forward_account": "not_available", "market_freshness": "snapshot_only_not_live",
            "missing_opening_evidence_sessions": r.missing_opening_evidence_sessions.to_string(),
            "unverified_status_sessions": r.unverified_status_sessions.to_string(),
            "unobserved_calendar_days_including_weekends": r.unobserved_calendar_days_including_weekends.to_string(),
            "execution_model": r.execution_model, "historical_assumptions": safe_json(&r.historical_assumptions)?,
            "gaps": r.daily.iter().filter(|d| d.nav_fen.is_none()).map(|d| json!({"day": d.day.0.to_string(), "reason": d.valuation_error})).collect::<Vec<_>>()
        });
        let snapshot = Self {
            report: r,
            metadata,
        };
        // Ensure all public projections can be represented before publishing.
        for route in [
            "account",
            "equity",
            "positions",
            "strategies",
            "fills",
            "orders",
        ] {
            snapshot.data(route)?;
        }
        Ok(snapshot)
    }

    pub fn data(&self, route: &str) -> Result<Value> {
        let r = &self.report;
        let d = r.daily.last().unwrap();
        match route {
            "account" => {
                let session_pnl = r.daily.iter().rev().nth(1).and_then(|p| Some(
                    i128::from(d.nav_fen?) - i128::from(p.nav_fen?)
                    - (i128::from(d.external_flow_total_fen) - i128::from(p.external_flow_total_fen))));
                safe_json(json!({"account_id": r.config.account_id, "day": d.day,
                    "nav_fen": d.nav_fen, "cash_fen": d.cash_fen, "available_cash_fen": d.available_cash_fen,
                    "reserved_cash_fen": d.reserved_cash_fen, "session_pnl_fen": session_pnl.map(|n| n.to_string()),
                    "cumulative_pnl_fen": cumulative(r, d).map(|n| n.to_string()), "total_return_bps": r.total_return_bps,
                    "max_daily_observation_drawdown_bps": r.max_daily_observation_drawdown_bps,
                    "total_fee_fen": r.total_fee_fen, "valuation_error": d.valuation_error,
                    "initial_nav_fen": r.initial_nav_fen, "external_flow_total_fen": d.external_flow_total_fen,
                    "risk": r.events.last().map(|e| &e["risk"]), "deployment": r.config.deployment}))
            }
            "equity" => safe_json(r.daily.iter().map(|d| json!({"day": d.day, "nav_fen": d.nav_fen,
                "cash_fen": d.cash_fen, "cumulative_pnl_fen": cumulative(r, d).map(|n| n.to_string()),
                "return_bps": if d.external_flow_total_fen == 0 { cumulative(r, d).map(|p| (p * 10_000 / i128::from(r.initial_nav_fen)).to_string()) } else { None },
                "valuation_error": d.valuation_error})).collect::<Vec<_>>()),
            "positions" => safe_json(if r.positions.is_empty() { vec![] } else { vec![json!({
                "instrument": r.instrument, "quantity": d.held_shares, "sellable_shares": d.sellable_shares,
                "unsettled_shares": d.unsettled_shares, "reserved_sell_shares": d.reserved_sell_shares,
                "market_value_fen": d.nav_fen.map(|n| i128::from(n) - i128::from(d.cash_fen)),
                "cost_basis_fen": d.remaining_cost_basis_fen, "unrealized_pnl_fen": d.unrealized_pnl_fen,
                "lots": r.positions, "deployment": r.config.deployment,
                "price_series": null, "price_series_reason": "六报告未提供可核验的持仓行情序列"
            })] }),
            "strategies" => safe_json(vec![json!({"deployment": r.config.deployment,
                "status": "snapshot_record_only", "pnl_fen": null, "drawdown_bps": null,
                "unavailable_reason": "只读报告记录该策略归属，未连接运行状态或独立策略绩效服务"})]),
            "fills" => safe_json(r.fills.iter().map(|f| json!({
                "fill_id": f.event_id, "order_id": f.order_id.0.to_string(), "day": f.day,
                "instrument": f.instrument, "side": f.side, "quantity": f.quantity,
                "price_fen": f.price.fen(), "fee_fen": f.fees.total().expect("validated fees").fen(),
                "fees": f.fees, "simulated_at": f.simulated_at, "risk_checked_at": f.risk_checked_at,
                "deployment": r.config.deployment, "execution_assumption": f.historical_execution,
                "source_version": f.evidence.provenance.source_version,
            })).collect::<Vec<_>>()),
            "orders" => safe_json(r.orders.iter().map(|o| json!({
                "order_id": o.proposal.proposal_id.0.to_string(), "day": o.accepted_on, "instrument": o.proposal.instrument,
                "side": o.proposal.side, "quantity": o.proposal.quantity, "remaining": o.remaining,
                "limit_fen": o.proposal.limit_price.fen(), "status": o.status, "reason": o.reason,
                "deployment": o.proposal.deployment,
                "confirmed_filled_shares": r.fills.iter().filter(|f| f.order_id == o.proposal.proposal_id).map(|f| i128::from(f.quantity)).sum::<i128>(),
            })).collect::<Vec<_>>()),
            _ => Err("未知 API".into()),
        }
    }
}

/// Optional, explicitly selected independent evaluation. It never feeds account
/// projections and does not inherit or grant an independent PASS classification.
pub fn research(path: &Path) -> Result<Value> {
    let raw: Value =
        serde_json::from_slice(&read_bounded(path)?).map_err(|_| "研究报告 JSON 损坏")?;
    require(
        raw["evaluation_schema"] == 1
            && raw["research_evidence"].is_string()
            && raw["engineering"].is_string()
            && raw["windows"].is_object(),
        "不支持的研究结果格式",
    )?;
    let windows = raw["windows"].as_object().unwrap().iter().map(|(name, w)| json!({
        "name": name, "first_day": w["first_day"], "last_day": w["last_day"], "days": w["days"],
        "net_pnl_fen": w["net_pnl_fen"], "net_return": w["net_return"], "fills": w["fills"],
        "missing_nav_days": w["missing_nav_days"], "valuation_reason": w["valuation_reason"]
    })).collect::<Vec<_>>();
    safe_json(
        json!({"kind": "independent_research_result", "account_inclusion": false,
        "research_evidence": raw["research_evidence"], "engineering": raw["engineering"],
        "independent_acceptance": raw["independent_acceptance"], "data_coverage": raw["data_coverage"],
        "strategy_version": raw["strategy_version"], "input_sha256": raw["input_sha256"],
        "windows": windows, "verification": "stored_result_not_independent_certification"}),
    )
}
