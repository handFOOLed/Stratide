//! Explicit artificial fixtures for CLI demonstration and engine tests. These
//! prices, rates, dates and capacities are not verified exchange/market data.
use crate::*;
use sha2::{Digest, Sha256};
use stratide_contracts::*;

pub const T0: i64 = 1_793_170_800_000;
pub const DAY: i64 = 86_400_000;
fn c(fen: i64) -> Cny {
    Cny::from_fen(fen).expect("constant synthetic fen")
}
pub fn instrument() -> Instrument {
    Instrument {
        market: Market::Shanghai,
        code: "600000".into(),
    }
}
pub fn provenance() -> Provenance {
    Provenance {
        mode: DataMode::SyntheticTest,
        source_version: "synthetic_test/artificial-v3".into(),
        dataset_hash: format!("{:x}", Sha256::digest(b"synthetic_test/artificial-v3;600000.SH;CNY-fen;T0=1793170800000;OHLC=1000,1050,950,1000;volume=10000;capacity=100;T+1;lots=100;tick=1;bands=800..1200;commission=300ppm,min1;transfer=10ppm;sell-tax=500ppm;independent-opening-marks-and-rules-at-open;matching-v3;exclusive-expiry-strictly-after-session-close")),
        timezone: "Asia/Shanghai".into(),
        price_semantics: "unadjusted_cny_fen".into(),
    }
}
pub fn genesis(config: PaperAccountConfig) -> Genesis {
    Genesis {
        config,
        provenance: provenance(),
        at: Timestamp(T0),
        day: TradingDay(20261028),
    }
}
pub fn rules(day: TradingDay, now: Timestamp) -> TradingRules {
    TradingRules {
        instrument: instrument(),
        trading_day: day,
        available_at: now,
        source: "synthetic_test/artificial-stock-rules-v1".into(),
        tradable: true,
        settlement: SettlementRule::TPlusOne,
        buy_lot: 100,
        sell_lot: 100,
        allow_odd_lot_liquidation: true,
        tick_size: c(1),
        min_price: c(800),
        max_price: c(1200),
    }
}
pub fn fees() -> FeeSchedule {
    FeeSchedule {
        version: "synthetic-fees-v1".into(),
        source: "synthetic_test/artificial-rates-not-real-tariff".into(),
        instrument: instrument(),
        valid_from: TradingDay(20261028),
        valid_through: TradingDay(20261130),
        commission_ppm: 300,
        minimum_commission: c(1),
        transfer_ppm: 10,
        sell_tax_ppm: 500,
    }
}
pub fn proposal(config: &PaperAccountConfig, id: u128) -> OrderProposal {
    OrderProposal {
        proposal_id: ProposalId(id),
        account_id: config.account_id.clone(),
        deployment: config.deployment.clone(),
        instrument: instrument(),
        side: Side::Buy,
        quantity: 100,
        limit_price: c(1000),
        decision_at: Timestamp(T0),
        data_available_at: Timestamp(T0),
        earliest_execution_at: Timestamp(T0 + 1),
        expires_at: Timestamp(T0 + 10 * DAY),
    }
}
pub fn submit(p: OrderProposal, day: TradingDay, now: Timestamp) -> Command {
    Command::Submit {
        proposal: p,
        day,
        now,
        rules: Some(rules(day, now)),
        fees: Some(fees()),
    }
}
pub fn bar(day: TradingDay, offset: i64) -> DailyBar {
    DailyBar {
        provenance: provenance(),
        instrument: instrument(),
        day,
        opens_at: Timestamp(T0 + offset * DAY - 19_800_000),
        closes_at: Timestamp(T0 + offset * DAY),
        available_at: Timestamp(T0 + offset * DAY),
        open: c(1000),
        high: c(1050),
        low: c(950),
        close: c(1000),
        volume_shares: 10000,
        capacity_shares: 100,
        status_verified: true,
    }
}
pub fn session(b: DailyBar) -> Command {
    let opening = OpeningEvidence {
        marks: vec![PositionMark {
            instrument: b.instrument.clone(),
            price: b.open,
            as_of: b.opens_at,
            available_at: b.opens_at,
            source: "synthetic_test/independent-opening-observation-v2".into(),
        }],
        rules: rules(b.day, b.opens_at),
    };
    Command::Match {
        opening: Some(opening),
        now: b.available_at,
        day: b.day,
        instrument: b.instrument.clone(),
        rules: Some(rules(b.day, b.available_at)),
        bar: Some(b),
    }
}
