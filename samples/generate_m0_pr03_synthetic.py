"""Create the fixed artificial M0-PR03 input. No market data is downloaded."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHANGHAI = timezone(timedelta(hours=8))
OUT = Path(__file__).with_name("m0-pr03-synthetic.json")


def ms(day, hour, minute):
    return int(datetime.fromisoformat(day).replace(
        hour=hour, minute=minute, tzinfo=SHANGHAI
    ).timestamp() * 1000)


def rules(at):
    return dict(available_at=at, source="synthetic_test/explicit-rules-v1",
                tradable=True, settlement="TPlusOne", buy_lot=100,
                sell_lot=100, allow_odd_lot_liquidation=True,
                tick_size_fen=1, min_price_fen=800, max_price_fen=1200)


rows = [
    ("2026-10-28", 1000, 1050, 950, 1000),
    ("2026-10-29", 1000, 1050, 950, 980),
    ("2026-10-30", 980, 1010, 900, 930),
    ("2026-11-02", 930, 1000, 900, 970),
]
sessions = []
for day, opening_price, high, low, close in rows:
    opening = ms(day, 9, 30)
    closing = ms(day, 15, 0)
    sessions.append(dict(
        day=int(day.replace("-", "")), opens_at=opening, closes_at=closing,
        available_at=closing + 1000, open_fen=opening_price,
        high_fen=high, low_fen=low, close_fen=close,
        volume_shares=10000, capacity_shares=100, status_verified=True,
        opening=dict(price_fen=opening_price, as_of=opening,
                     available_at=opening, source="synthetic_test/independent-opening-v1",
                     rules=rules(opening)), rules=rules(opening),
    ))

dataset = dict(
    schema_version=1, mode="synthetic_test", source="synthetic_test/hand-authored",
    license="generated-in-repository-no-market-data", source_version="fixture-v1",
    timezone="Asia/Shanghai", price_semantics="unadjusted_cny_fen",
    instrument=dict(market="Shanghai", code="600000"),
    fee=dict(version="artificial-fees-v1", source="synthetic_test/not-a-real-tariff",
             valid_from=20261028, valid_through=20261130,
             commission_ppm=300, minimum_commission_fen=1,
             transfer_ppm=10, sell_tax_ppm=500),
    sessions=sessions,
)
OUT.write_bytes((json.dumps(dataset, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
print(OUT)
