"""Freeze authorized local Tushare history; no raw prices or credentials in stdout.

fetch: HTTPS raw responses using STRATIDE_TUSHARE_TOKEN (never a CLI argument).
prepare: existing raw HTTP envelopes or connected MCP text payload JSON arrays.
Only 600000.SH, SSE, unadjusted fen/shares, explicit recent date range.
"""
import argparse
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

APIS = {"daily": "daily", "calendar": "trade_cal", "limits": "stk_limit", "suspensions": "suspend_d"}
FIELDS = {"daily": "ts_code,trade_date,open,high,low,close,pre_close,vol",
          "calendar": "exchange,cal_date,is_open,pretrade_date",
          "limits": "ts_code,trade_date,up_limit,down_limit",
          "suspensions": "ts_code,trade_date,suspend_timing,suspend_type"}
AVAILABILITY = "assumed_historical_eod_availability_not_pit_verified"


def exact(value, scale):
    v = Decimal(str(value)) * scale
    if not v.is_finite() or v != v.to_integral_value() or v < 0 or v > 2**63 - 1:
        raise ValueError("non-integral/negative/nonfinite/overflow fen or shares")
    return int(v)


def day(value):
    return dt.datetime.strptime(str(value), "%Y%m%d").date()


def stamp(value, hour, minute=0):
    date = day(value)
    instant = dt.datetime.combine(date, dt.time(hour, minute), dt.timezone(dt.timedelta(hours=8)))
    return int(instant.timestamp()) * 1000


def rows(path):
    raw = json.loads(path.read_bytes(), parse_float=Decimal)
    if isinstance(raw, list):  # MCP text payload, NOT HTTP wire bytes.
        return raw
    if raw.get("code") != 0 or not isinstance(raw.get("data"), dict):
        raise ValueError("provider response failed; raw retained locally")
    data = raw["data"]
    if len(data["fields"]) != len(set(data["fields"])):
        raise ValueError("duplicate source fields")
    if any(len(row) != len(data["fields"]) for row in data["items"]):
        raise ValueError("source row length mismatch")
    return [dict(zip(data["fields"], row)) for row in data["items"]]


def index(items, key, start, end, calendar=False):
    result = {}
    for row in items:
        date = str(row[key])
        day(date)
        if not start <= date <= end:
            continue
        if (calendar and row["exchange"] != "SSE") or (not calendar and row["ts_code"] != "600000.SH"):
            raise ValueError("symbol/exchange mismatch")
        if date in result:
            raise ValueError("duplicate source date")
        result[date] = row
    return result


def prepare(source, out, start, end):
    extraction = json.loads((source / "extraction.json").read_bytes())
    if extraction["params"]["ts_code"] != "600000.SH" or extraction["params"]["exchange"] != "SSE":
        raise ValueError("source query scope mismatch")
    if not extraction["params"]["start_date"] <= start <= end <= extraction["params"]["end_date"]:
        raise ValueError("selected range outside frozen query")
    extracted = dt.datetime.fromisoformat(extraction["extracted_at_utc"].replace("Z", "+00:00"))
    if extracted.tzinfo is None or int(extracted.timestamp()) * 1000 < stamp(end, 18):
        raise ValueError("extraction must be actually after selected historical EOD")
    cal = index(rows(source / "calendar.json"), "cal_date", start, end, True)
    dates = {(day(start) + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range((day(end)-day(start)).days+1)}
    if set(cal) != dates or any(str(r["is_open"]) not in ("0", "1") for r in cal.values()):
        raise ValueError("incomplete/unknown calendar")
    opened = sorted(d for d, r in cal.items() if str(r["is_open"]) == "1")
    daily = index(rows(source / "daily.json"), "trade_date", start, end)
    limits = index(rows(source / "limits.json"), "trade_date", start, end)
    suspensions = {str(r["trade_date"]) for r in rows(source / "suspensions.json")
                   if r["ts_code"] == "600000.SH" and start <= str(r["trade_date"]) <= end}
    if not opened or set(daily) != set(opened):
        raise ValueError("missing/extra daily rows; not silently classified as suspension")
    sessions = []
    previous_close = None
    for i, date in enumerate(opened):
        if i and str(cal[date]["pretrade_date"]) != opened[i-1]:
            raise ValueError("calendar predecessor mismatch")
        r = daily[date]
        prices = {f"{k}_fen": exact(r[k], 100) for k in ("open", "high", "low", "close")}
        if min(prices.values()) <= 0 or not prices["low_fen"] <= min(prices["open_fen"], prices["close_fen"]) <= max(prices["open_fen"], prices["close_fen"]) <= prices["high_fen"]:
            raise ValueError("invalid OHLC")
        if previous_close is not None and exact(r["pre_close"], 100) != previous_close:
            raise ValueError("corporate-action/adjustment discontinuity; unsupported accounting, choose an explicit clean window")
        previous_close = prices["close_fen"]
        if date not in limits:
            raise ValueError("missing price band; cannot verify historical trading rules")
        lower, upper = exact(limits[date]["down_limit"], 100), exact(limits[date]["up_limit"], 100)
        if not 0 < lower < upper or not all(lower <= p <= upper for p in prices.values()):
            raise ValueError("price band conflict")
        volume = exact(r["vol"], 100)
        if volume < 100:
            raise ValueError("invalid/insufficient source volume, no zero fill")
        available = stamp(date, 18)
        sessions.append(dict(day=int(date), opens_at=stamp(date, 9, 30), closes_at=stamp(date, 15),
                             available_at=available, **prices, volume_shares=volume, capacity_shares=100,
                             status_verified=True, opening=None,
                             rules=dict(available_at=available, source="historical stk_limit + suspend_d; SSE-20260706 ordinary-A model (not PIT)",
                                        tradable=date not in suspensions, settlement="TPlusOne", buy_lot=100,
                                        sell_lot=100, allow_odd_lot_liquidation=True, tick_size_fen=1,
                                        min_price_fen=lower, max_price_fen=upper)))
    hashes = {key: hashlib.sha256((source / f"{key}.json").read_bytes()).hexdigest() for key in APIS}
    manifest = dict(extraction=extraction, raw_sha256=hashes, api_fields=FIELDS, adapter_version="historical-data-v1",
                    selected_start=start, selected_end=end,
                    sessions=len(sessions), calendar_days=len(cal), units="CNY yuan*100 -> integer fen; vol lots*100 -> integer shares",
                    actual_per_bar_received_at=None, provider_historical_published_at=None,
                    limitations=["revision history unavailable; not verified PIT", "ordinary SSE A rules; no auction queue/capacity proof",
                                 "no corporate actions ledger; pre_close discontinuities blocked", "MCP payloads are not local HTTPS wire bytes"])
    dataset = dict(schema_version=2, mode="historical_replay", source="Tushare personal local research",
                   license="Owner-declared personal noncommercial local research; no redistribution grant",
                   source_version="tushare-daily-trade_cal-stk_limit-suspend_d/adapter-v1",
                   timezone="Asia/Shanghai", price_semantics="unadjusted_cny_fen", instrument=dict(market="Shanghai", code="600000"),
                   fee=dict(version="paper-cost-assumption-20260706-v1", source="explicit model: inclusive commission 300ppm min500fen; transfer10ppm; sell tax500ppm; per-fill ceil fen, not broker tariff",
                            valid_from=20260706, valid_through=20261231, commission_ppm=300,
                            minimum_commission_fen=500, transfer_ppm=10, sell_tax_ppm=500),
                   historical=dict(availability=AVAILABILITY, execution="historical_ex_post_execution_assumption",
                                   strategy="sma5-20-cross-fixed100-v1", completeness="complete_calendar_and_daily_rows", source_manifest=manifest),
                   sessions=sessions)
    payload = (json.dumps(dataset, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out.mkdir(parents=True)  # Never overwrite any input/run/report directory.
    (out / "dataset.json").write_bytes(payload)
    summary = dict(mode="historical_replay", first_day=opened[0], last_day=opened[-1], rows=len(sessions),
                   input_sha256=hashlib.sha256(payload).hexdigest(), raw_sha256=hashes)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("authenticated redirects disabled")


def fetch(out, start, end):
    token = os.environ.get("STRATIDE_TUSHARE_TOKEN", "").strip()
    if not token:
        raise ValueError("BLOCKED: STRATIDE_TUSHARE_TOKEN not configured; never pass token in commands")
    out.mkdir(parents=True)
    for key, api in APIS.items():
        params = dict(start_date=start, end_date=end)
        params.update({"exchange": "SSE"} if key == "calendar" else {"ts_code": "600000.SH"})
        request = urllib.request.Request("https://api.tushare.pro", data=json.dumps(dict(api_name=api, token=token, params=params, fields=FIELDS[key])).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000 or token.encode() in raw:
            raise ValueError("response size/secret-echo rejected; not saved")
        (out / f"{key}.json").write_bytes(raw)
        rows(out / f"{key}.json")
    meta = dict(source="local_https_tushare", response_kind="HTTP_body_bytes", apis=list(APIS.values()),
                extracted_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                params=dict(ts_code="600000.SH", exchange="SSE", start_date=start, end_date=end))
    (out / "extraction.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("Frozen four local HTTPS source bodies; no prices or credentials printed")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("fetch", "prepare"))
    p.add_argument("--source-dir", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    a = p.parse_args()
    day(a.start); day(a.end)
    if a.start > a.end or a.start < "20260706" or a.end > "20261231":
        raise ValueError("v1 supported rule/fee dates: 20260706..20261231")
    # Keep data under a known gitignored runtime root; verify via Git, no guess.
    import subprocess
    if subprocess.run(["git", "check-ignore", "--quiet", str(a.out / "dataset.json")]).returncode != 0:
        raise ValueError("output must be in a gitignored local directory")
    if a.action == "fetch":
        fetch(a.out, a.start, a.end)
    elif a.source_dir:
        prepare(a.source_dir, a.out, a.start, a.end)
    else:
        raise ValueError("prepare requires --source-dir")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        # Provider messages / request objects are never printed (may echo secrets).
        print(f"BLOCKED historical input: {type(error).__name__}", file=sys.stderr)
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        sys.exit(2)
