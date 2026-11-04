"""Bounded, read-only ex-post history adapter. No provider client or adjustment."""
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys

from model import Rejected, digest, require
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_warehouse as v1
import historical_sidecar as v2

VERSION = "historical-timesfm-v1"
MODE = "historical_research_only"
BLOCKERS = ["HISTORICAL_PIT_NOT_VERIFIED", "CURRENT_CATALOG_NOT_HISTORICAL_IDENTITY",
            "CORPORATE_ACTION_COVERAGE_PARTIAL", "SOURCE_COVERAGE_PARTIAL",
            "FORECAST_SESSION_DATES_UNKNOWN", "REAL_MARKET_DATA_EGRESS_DENIED"]


class Blocked(Rejected):
    def __init__(self, code, coverage=None):
        super().__init__(code)
        self.coverage = coverage or {}


def check(ok, code, coverage=None):
    if not ok:
        raise Blocked(code, coverage)


def iso(day):
    return v1.day(day).isoformat()


def number(value):
    check(isinstance(value, str), "HISTORY_NUMERIC_SCHEMA")
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise Blocked("HISTORY_NUMERIC_SCHEMA") from None
    check(d.is_finite(), "HISTORY_NONFINITE")
    return d


def assemble(descriptor, symbols, as_of, days, catalog, daily, factors, suspensions, versions, metadata):
    """Pure adapter; queries are prefix-only. Future prices never enter this function."""
    check(1 <= len(symbols) <= 8 and len(set(symbols)) == len(symbols), "HISTORY_SYMBOL_COUNT")
    at = dt.datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    check(at.tzinfo is not None and at <= dt.datetime.now(dt.timezone.utc), "HISTORY_AS_OF")
    cutoff = at.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d")
    check(84 <= len(days) <= 192 and days == sorted(set(days)) and days[-1] == cutoff,
          "HISTORY_CONTEXT_CALENDAR")
    check(at.astimezone(dt.timezone(dt.timedelta(hours=8))).hour >= 16, "HISTORY_CLOSE_NOT_AVAILABLE")
    observations, raw_series, quality = [], [], []
    for code in symbols:
        check(re.fullmatch(r"(?:60[0-9]{4}\.SH|00[0-9]{4}\.SZ|30[0-9]{4}\.SZ|68[0-9]{4}\.SH)", code),
              "HISTORY_MARKET_IDENTITY_UNSUPPORTED")
        cat = catalog.get(code)
        check(cat and cat.get("list_date") and cat["list_date"] <= days[0]
              and (not cat.get("delist_date") or cat["delist_date"] > days[-1]), "HISTORY_LISTING_INTERVAL")
        expected_exchange = "SSE" if code.endswith(".SH") else "SZSE"
        check(cat.get("exchange") == expected_exchange, "HISTORY_IDENTITY_MISMATCH")
        rows = [x for x in daily["rows"] if x["values"]["ts_code"] == code]
        dates = [x["values"]["trade_date"] for x in rows]
        coverage = dict(instrument=code, expected=len(days), observed=len(set(dates)&set(days)),
                        ratio=len(set(dates)&set(days))/len(days), missing_dates=sorted(set(days)-set(dates)))
        check(len(dates) == len(set(dates)), "HISTORY_DUPLICATE_DAY", coverage)
        check(dates == days, "HISTORY_MISSING_OR_SUSPENDED_DAY", coverage)
        fs = [x["data"] for x in factors["rows"] if x["data"]["ts_code"] == code]
        check([x["trade_date"] for x in fs] == days, "HISTORY_FACTOR_COVERAGE_GAP", coverage)
        vals = [number(x["adj_factor"]) for x in fs]
        check(all(x > 0 for x in vals), "HISTORY_FACTOR_INVALID", coverage)
        check(len(set(vals)) == 1, "HISTORY_RAW_ACTION_DISCONTINUITY", coverage)
        check(not any(x["data"]["ts_code"] == code and x["data"]["suspend_type"] == "S"
                      for x in suspensions["rows"]), "HISTORY_SUSPENSION_REPORTED", coverage)
        obs, raw = [], []
        previous = None
        for row in rows:
            x = row["values"]
            check(x["ts_code"] == code and x["trade_date"] in days, "HISTORY_IDENTITY_MISMATCH", coverage)
            check(not x.get("quality_flags"), "HISTORY_SOURCE_ROW_QUALITY", coverage)
            op, hi, lo, cl = (number(x[k]) for k in ("open", "high", "low", "close"))
            check(0 < lo <= min(op, cl) <= max(op, cl) <= hi, "HISTORY_PRICE_INVALID", coverage)
            check(number(x["vol"]) > 0 and number(x["amount"]) > 0, "HISTORY_VOLUME_INVALID", coverage)
            pre = number(x["pre_close"])
            check(previous is None or pre == previous, "HISTORY_PRE_CLOSE_ACTION_OR_REVISION", coverage)
            check(previous is None or abs(cl/previous-1) <= Decimal(".35"), "HISTORY_PRICE_JUMP", coverage)
            fen = cl * 100
            check(fen == fen.to_integral_value() and 0 < fen <= 1000000000, "HISTORY_PRICE_PRECISION", coverage)
            sources = row["availability"]["attempts"]
            received = max(s["obtained_at"] for s in sources)
            check(sources and digest(row["availability"]) == row["source_sha"], "HISTORY_SOURCE_SHA", coverage)
            check(dt.datetime.fromisoformat(received.replace("Z", "+00:00")).date() >= v1.day(x["trade_date"]),
                  "HISTORY_RECEIVED_TIME", coverage)
            obs.append(dict(trade_day=iso(x["trade_date"]), available_at=received, close_fen=int(fen)))
            raw.append(dict(values=x, row_sha256=digest(x), version_id=row["version_id"],
                            source_sha256=row["source_sha"], source_received_at=received,
                            available_at=received, historical_available_at=None,
                            partition_quality=row["partition_status"]))
            previous = cl
        observations.append(dict(instrument=code, corporate_actions="EX_POST_NO_DETECTED_ACTION_NOT_VERIFIED", observations=obs))
        raw_series.append(dict(instrument=code, market=expected_exchange, rows=raw,
                               factors=fs, listing=dict(list_date=cat["list_date"],
                               identity_status="CURRENT_CATALOG_EX_POST_NOT_HISTORICAL_MASTER")))
        quality.append(dict(**coverage, status="PARTIAL", reasons=BLOCKERS))
    # Future sessions are ordinal because the old calendar ends at 2026-10-30.
    # Do not invent exchange dates or consult future prices.
    calendar = [iso(d) for d in days] + [f"session+{i:03}" for i in range(1, 21)]
    f = dict(schema_version=1, scope="risk_portfolio_v1", policy="risk-portfolio-v1", input_mode=MODE,
             snapshot_ref=digest(dict(series=observations, calendar=calendar)),
             readiness_ref="HISTORICAL_PIT_NOT_VERIFIED", as_of=at.isoformat().replace("+00:00","Z"),
             strategy_version=VERSION, prompt_version="portfolio-json-v1",
             prompt_sha256=descriptor["prompt_sha256"], adapter_sha256=descriptor["adapter_sha256"],
             calendar=calendar, calendar_provenance="EX_POST_EXCHANGE_CONTEXT_ORDINAL_HORIZON",
             series=observations, opportunities=[dict(instrument=s, status="UNKNOWN", evidence=[]) for s in symbols],
             account_facts="UNKNOWN_NO_ACCOUNT_ORDERS", risk_model=dict(id="local-timesfm-2.5-cpu", fingerprint=descriptor["code_sha256"]),
             fusion_model=dict(id="UNUSED_REAL_EGRESS_DENIED", fingerprint="0"*64), batch_budget_micro=1,
             risk_recording_sha256="0"*64, fusion_recording_sha256="0"*64)
    payload = dict(schema_version=1, adapter_version=VERSION, input_mode=MODE, as_of=f["as_of"],
                   context_start=iso(days[0]), context_cutoff=iso(days[-1]), horizon=20,
                   adjustment="unadjusted_no_factor_application", historical_pit_status="NOT_VERIFIED",
                   availability_semantics="actual_download_only_not_historical_PIT",
                   coverage="PARTIAL", quality=quality, blockers=BLOCKERS,
                   units=dict(prices="CNY_yuan", volume="lot_100_shares", amount="CNY_thousand_yuan"),
                   dataset_versions=versions, metadata=metadata, series=raw_series,
                   sources=dict(daily={x["values"]["ts_code"]+":"+x["values"]["trade_date"]:x["source_sha"] for x in daily["rows"]},
                                daily_manifests={x["source_sha"]:x["availability"] for x in daily["rows"]},
                                adj_factor=factors["partitions"], suspend_d=suspensions["partitions"]),
                   frozen_sha256=digest(f), cloud_egress="REAL_MARKET_DATA_EGRESS_DENIED")
    return f, dict(payload_sha256=digest(payload), payload=payload)


def _read(descriptor, v1_root, v2_root, symbols, as_of, context=84):
    check(84 <= context <= 192, "HISTORY_CONTEXT_BOUNDS")
    check(1 <= len(symbols) <= 8 and len(set(symbols)) == len(symbols), "HISTORY_SYMBOL_COUNT")
    w, s = v1.Warehouse(v1_root), v2.Sidecar(v2_root)
    cutoff = dt.datetime.fromisoformat(as_of.replace("Z","+00:00")).astimezone(dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d")
    with w.read(inspect_raw_paths=False) as db:
        cal = w.latest_objects(db,"trade_cal")
        catalog = {x["ts_code"]:x for x in w.latest_objects(db,"stock_basic") if x["ts_code"] in symbols}
        dates = [d for d in v1.dates(v1.START, cutoff)]
        exchange_days = []
        for e in sorted({"SSE" if c.endswith(".SH") else "SZSE" for c in symbols}):
            rows = [x for x in cal if x["exchange"] == e and x["cal_date"] <= cutoff]
            check({x["cal_date"] for x in rows} >= set(dates), "HISTORY_CALENDAR_GAP")
            chosen = sorted(x["cal_date"] for x in rows if x["is_open"] == "1")[-context:]
            exchange_days.append(chosen)
        check(all(x == exchange_days[0] for x in exchange_days), "HISTORY_CROSS_MARKET_CALENDAR")
        days = exchange_days[0]
        check(len(days) == context, "HISTORY_CONTEXT_UNAVAILABLE")
        upper = db.execute("SELECT MAX(id) FROM day_versions WHERE trade_date BETWEEN ? AND ?",(days[0],cutoff)).fetchone()[0]
    daily = w.query(days[0],cutoff,symbols,as_of_version=upper,limit=2000,inspect_raw_paths=False)
    check(not daily["has_more"], "HISTORY_QUERY_TRUNCATED")
    with s.read(inspect_raw_paths=False) as db:
        bound = db.execute("SELECT MAX(id) FROM versions WHERE api IN ('adj_factor','suspend_d') AND trade_date BETWEEN ? AND ?",(days[0],cutoff)).fetchone()[0]
        check(bound is not None, "HISTORY_SIDECAR_MISSING")
        meta = db.execute("SELECT sha FROM metadata_source").fetchone()[0]
    factor = s.query("adj_factor",days[0],cutoff,symbols,as_of=bound,limit=2000,inspect_raw_paths=False)
    susp = s.query("suspend_d",days[0],cutoff,symbols,as_of=bound,limit=2000,inspect_raw_paths=False)
    for query in (factor,susp):
        check(not query["has_more"] and not query["missing_dates"], "HISTORY_SIDECAR_COVERAGE_GAP")
        check(all(x["quality"] in ("COMPLETE","PARTIAL") for x in query["partitions"]), "HISTORY_PARTITION_BLOCKED")
    # Retain only the selected calendar/catalog evidence, no future membership labels.
    metadata = dict(calendar_sha256=digest([x for x in cal if x["cal_date"] in days]),
                    sidecar_metadata_sha256=meta, contract_v1_sha256=digest(v1.CONTRACT),
                    contract_v2_sha256=digest(v2.CONTRACT))
    return assemble(descriptor,symbols,as_of,days,catalog,daily,factor,susp,
                    dict(daily=upper,sidecar=bound),metadata)


def read(*args, **kwargs):
    try:
        return _read(*args, **kwargs)
    except (v1.WarehouseError, v2.Error) as e:
        raise Blocked(str(e)) from None


def market_day(root, date, symbols, as_of):
    """Read the qualified current EOD source only; does not run a Worker/model.

    Historical `_read` retains its frozen V1/V2 semantics and PIT restrictions.
    This gate is the source boundary for subsequent market-wide research.
    """
    import market_eod
    try:
        return market_eod.Market(root).research_source(date, symbols, as_of)
    except market_eod.Error as error:
        raise Blocked(str(error)) from None

def provenance(value, store_name):
    import cli
    check(store_name is None, "HISTORY_LOCAL_SOURCE_ONLY")
    plan = value["input"]["summary"]["plan"]
    check(plan.get("history") and value == cli.task(plan["batch"], detailed=True), "HISTORY_ORIGINAL_TASK_REQUIRED")
    cli.verify(plan["batch"])
    return dict(snapshot_sha256=plan["frozen"]["snapshot_ref"], source_day=value["input"]["source_day"],
                data_mode=MODE, research_task_id=value["id"], input_summary_version=value["input"]["version"],
                frozen_input_sha256=digest(value["input"]), historical_input_sha256=plan["history"]["payload_sha256"],
                historical_pit_status="NOT_VERIFIED", coverage="PARTIAL",
                snapshot_verification="ORIGINAL_LOCAL_HISTORICAL_CPU_TASK_VERIFIED_NOT_PIT",
                task_origin="ORIGINAL_AGENT_SQLITE_VERIFIED_BY_RUNNER", restriction="RESEARCH_ONLY",
                cloud_egress="REAL_MARKET_DATA_EGRESS_DENIED", eod_eligible=False,
                can_execute_forward_paper=False, live_allowed=False)


def registry_name(name):
    return "local-cpu-" + digest(dict(batch=name))[:32]


def archive(name):
    import cli, candidates as c
    cli.verify(name)
    value = cli.task(name,detailed=True)
    path = cli.batch_path(name)
    c.write(path/"task-export.json",value)
    registry = c.Registry(registry_name(name),create=True)
    with registry.locked():
        registration = registry.register(None,path/"task-export.json")
        record = dict(registry=registry_name(name),registration_sha256=registration["registration_sha256"],
                      task_detail_sha256=c.digest(value))
        if (path/"archive.json").exists():
            check(c.read(path/"archive.json") == record,"HISTORY_ARCHIVE_CHANGED")
        else:
            c.write(path/"archive.json",record)
    return record


def archived(name):
    import cli, candidates as c
    value = cli.task(name,detailed=True)
    saved = c.read(cli.batch_path(name)/"archive.json")
    material = c.Registry(registry_name(name)).registration(saved["registration_sha256"])["material"]
    check(saved["registry"] == registry_name(name) and saved["task_detail_sha256"] == c.digest(value)
          and material == dict(schema_version=1,owner_input=None,saved_agent_task=value,
                               authority="research_only",template=None,snapshot_provenance=provenance(value,None)),
          "HISTORY_ARCHIVE_CHANGED")
    return saved
