"""Read schema-1041 observations without opening the forward writer or fetching data.

Uses the chain/raw/normalization protocol from verify-forward-readonly.py and
crates/forward. Local hashes attest consistency, not external origin or PIT.
"""
import datetime as dt
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime

VERSION = "stratide-forward-v1/tushare-http-v1"
AVAILABILITY = "validated_in_process_precommit_wall_time; not_exact_durable_visibility_or_commit_time"
ZONE = dt.timezone(dt.timedelta(hours=8))


class Rejected(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "AMBIGUOUS_JSON")
        result[key] = value
    return result


def loads(data, **kwargs):
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, "NONFINITE_JSON"), **kwargs)


def day(ms):
    require(type(ms) is int, "INVALID_TIMESTAMP")
    return dt.datetime.fromtimestamp(ms / 1000, ZONE).strftime("%Y%m%d")


def date(value):
    result = dt.datetime.strptime(value, "%Y%m%d").date()
    require(result.strftime("%Y%m%d") == value, "INVALID_SOURCE_DAY")
    return result


def no_links(path):
    for part in (path, *path.parents):
        require(not part.is_symlink() and not part.is_junction(), "LINK_PATH_DENIED")


def read_observer(path):
    path = Path(path).absolute()
    no_links(path)
    path = path.resolve(strict=True)
    # The existing observer uses DELETE mode. Do not copy a live WAL or create SHM.
    require(not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")),
            "SOURCE_BUSY_OR_WAL_UNSUPPORTED")
    before = sha(path.read_bytes())
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "SOURCE_INTEGRITY")
        require(db.execute("PRAGMA user_version").fetchone()[0] == 1041, "SOURCE_SCHEMA")
        rows = db.execute("SELECT seq,payload,digest FROM events ORDER BY seq").fetchall()
        checkpoint = db.execute("SELECT seq,digest FROM checkpoint").fetchall()
        require(rows and checkpoint == [(rows[-1][0], rows[-1][2])], "SOURCE_CHECKPOINT")
    content = verify_rows(rows)
    require(before == sha(path.read_bytes()), "SOURCE_CHANGED_DURING_READ")
    return content, before


def response(raw):
    body = bytes(raw["body"])
    require(sha(body) == raw["sha256"], "RAW_SHA_MISMATCH")
    value = loads(body, parse_float=Decimal)
    require(raw["http_status"] == 200 and value["code"] == 0, "RAW_RESPONSE_NOT_SUCCESS")
    fields = value["data"]["fields"]
    require(all(isinstance(f, str) for f in fields) and len(set(fields)) == len(fields), "RAW_FIELDS")
    return [dict(zip(fields, row, strict=True)) for row in value["data"]["items"]]


def exact(value):
    try:
        result = Decimal(str(value)) * 100
    except InvalidOperation:
        raise Rejected("RAW_UNIT_INVALID") from None
    require(result.is_finite() and result == result.to_integral_value()
            and 0 <= result <= 9223372036854775807, "RAW_UNIT_INVALID")
    return int(result)


def verify_rows(rows):
    entries, previous = [], ""
    for n, payload, digest in rows:
        encoded = json.dumps([1, "forward_observation", previous, n, payload],
                             ensure_ascii=False, separators=(",", ":")).encode()
        require(n == len(entries) and sha(encoded) == digest, "SOURCE_CHAIN")
        entries.append(loads(payload))
        previous = digest
    require(entries, "SOURCE_EMPTY")
    genesis = entries[0]
    require(genesis["event"] == "initialized" and genesis["version"] == VERSION, "SOURCE_VERSION")
    config = genesis["config"]
    require(set(config) == {"observation_id", "instrument", "strategy_version", "source", "license_note",
                            "local_automation_and_raw_storage_authorized"}, "SOURCE_CONFIG")
    instrument = config["instrument"]
    require(len(instrument) == 9 and instrument[:6].isascii() and instrument[:6].isdigit()
            and instrument[6:] in (".SH", ".SZ") and config["source"] == "tushare_pro", "SOURCE_IDENTITY")
    require(config["local_automation_and_raw_storage_authorized"] is True, "SOURCE_NOT_AUTHORIZED")
    require(all(isinstance(config[k], str) and config[k].strip()
                for k in ("observation_id", "strategy_version", "license_note")), "SOURCE_CONFIG")
    exchange = "SSE" if instrument.endswith(".SH") else "SZSE"
    high = genesis["started_at"]
    day(high)
    starts, seen, calendar, versions, all_bars = {}, set(), {}, [], {}
    blockers, warnings = set(), set()
    raw_hashes, attempts = [], []
    forward_days = set()
    for n, event in enumerate(entries[1:], 1):
        kind = event["event"]
        require(kind in ("collection_started", "collection_finished", "interrupted", "clock_fault"), "SOURCE_EVENT")
        at = event[{"collection_started": "observed_at", "collection_finished": "finished_at",
                    "interrupted": "detected_at", "clock_fault": "detected_at"}[kind]]
        day(at)
        if kind == "clock_fault":
            blockers.add("SOURCE_CLOCK_FAULT")
            continue
        require(at >= high, "SOURCE_TIME_ORDER")
        high = at
        run = event["run_id"]
        if kind == "collection_started":
            require(run not in seen, "SOURCE_DUPLICATE_RUN")
            seen.add(run)
            for field in ("trade_day", "calendar_from", "calendar_through"):
                date(event[field])
            require(event["calendar_from"] <= event["trade_day"] <= event["calendar_through"]
                    and event["trade_day"] <= day(at), "SOURCE_REQUEST_DATES")
            starts[run] = event
            continue
        require(run in starts, "SOURCE_RUN_ORDER")
        started = starts.pop(run)
        if kind == "interrupted":
            warnings.add("INTERRUPTED_COLLECTION")
            continue
        out = event["outcome"]
        refs = {}
        for raw in out["raw"]:
            require(raw["api"] in ("trade_cal", "daily") and raw["api"] not in refs, "RAW_API")
            require(started["observed_at"] <= raw["received_at"] <= at, "RAW_TIME_ORDER")
            require(sha(bytes(raw["body"])) == raw["sha256"], "RAW_SHA_MISMATCH")
            refs[raw["api"]] = raw
            raw_hashes.append(dict(sequence=n, api=raw["api"], sha256=raw["sha256"],
                                   received_at=raw["received_at"]))
        if out["calendar"]:
            cal = response(refs["trade_cal"])
            for row in cal:
                date(row["cal_date"])
                require(row["exchange"] == exchange and type(row["is_open"]) is int
                        and row["is_open"] in (0, 1)
                        and started["calendar_from"] <= row["cal_date"] <= started["calendar_through"], "RAW_CALENDAR_IDENTITY")
            normalized = sorted((r["cal_date"], bool(r["is_open"])) for r in cal)
            expected = sorted((r["day"], r["is_open"]) for r in out["calendar"])
            require(normalized == expected and len({r[0] for r in normalized}) == len(normalized)
                    and len(normalized) == (date(started["calendar_through"]) - date(started["calendar_from"])).days + 1,
                    "RAW_CALENDAR_MISMATCH")
            for key, opened in normalized:
                if key in calendar and calendar[key] != opened:
                    blockers.add("CALENDAR_CONFLICT")
                calendar[key] = opened
        late = started["trade_day"] < day(started["observed_at"]) or started["trade_day"] < day(at)
        require(out["late_backfill"] is late, "LATE_BACKFILL_MISMATCH")
        attempts.append(dict(sequence=n, trade_day=started["trade_day"], status=out["status"],
                             late_backfill=late, duplicate_of=out["duplicate_of"], revision_of=out["revision_of"]))
        if out["status"] == "calendar_conflict":
            blockers.add("CALENDAR_CONFLICT")
        bar = out["bar"]
        if bar is not None:
            daily = response(refs["daily"])
            require(len(daily) == 1, "RAW_DAILY_COUNT")
            raw_bar = daily[0]
            require(raw_bar["ts_code"] == instrument and raw_bar["trade_date"] == bar["trade_day"]
                    == started["trade_day"], "RAW_BAR_IDENTITY")
            require(all(exact(raw_bar[f]) == bar[f + "_fen"] for f in ("open", "high", "low", "close"))
                    and exact(raw_bar["vol"]) == bar["volume_shares"]
                    and bar["price_semantics"] == "unadjusted_cny_fen"
                    and bar["source_volume_unit"] == "hand_100_shares", "RAW_BAR_MISMATCH")
            require(0 < bar["low_fen"] <= min(bar["open_fen"], bar["close_fen"])
                    <= max(bar["open_fen"], bar["close_fen"]) <= bar["high_fen"], "INVALID_OHLC")
            old = all_bars.get(bar["trade_day"])
            duplicate = old[0] if old and old[1] == bar else None
            revision = old[0] if old and old[1] != bar else None
            require((out["duplicate_of"], out["revision_of"]) == (duplicate, revision), "REVISION_LINK_MISMATCH")
            all_bars[bar["trade_day"]] = (n, bar)
        if out["status"] != "valid_eod":
            if out["status"] == "market_closed":
                require(bar is None and any(d["day"] == started["trade_day"] and d["is_open"] is False
                                             for d in out["calendar"]), "CLOSED_CALENDAR_MISMATCH")
            else:
                warnings.add("COLLECTION_ERROR")
            continue
        require(bar is not None and any(d["day"] == bar["trade_day"] and d["is_open"] is True
                                       for d in out["calendar"])
                and out["available_at"] == at and out["provider_published_at"] is None, "EOD_TIME_OR_CALENDAR")
        require(set(refs) == {"trade_cal", "daily"}, "EOD_RAW_MISSING")
        for raw in refs.values():
            server = parsedate_to_datetime(raw["server_date"])
            require(server.tzinfo is not None and abs(server.timestamp() * 1000 - raw["received_at"]) <= 300000,
                    "RAW_CLOCK_UNVERIFIED")
        versions.append(dict(sequence=n, bar=bar, observed_at=started["observed_at"],
                             received_at=max(r["received_at"] for r in refs.values()),
                             available_at=out["available_at"], provider_published_at=None,
                             late_backfill=late, duplicate_of=out["duplicate_of"], revision_of=out["revision_of"]))
        if late:
            warnings.add("LATE_BACKFILL")
        else:
            forward_days.add(bar["trade_day"])
        if out["revision_of"] is not None:
            warnings.add("REVISED_EOD")
    if starts:
        blockers.add("PENDING_COLLECTION")
    first, last = date(day(genesis["started_at"])), date(day(high))
    coverage = []
    for offset in range((last - first).days + 1):
        key = (first + dt.timedelta(days=offset)).strftime("%Y%m%d")
        state = ("calendar_unknown" if key not in calendar else "market_closed" if not calendar[key]
                 else "valid_eod" if key in forward_days else "missing_valid_eod")
        coverage.append(dict(source_day=key, state=state))
    if any(r["state"] == "calendar_unknown" for r in coverage):
        blockers.add("CALENDAR_UNKNOWN")
    if any(r["state"] == "missing_valid_eod" for r in coverage):
        warnings.add("MISSING_ON_DAY_EOD")
    if not versions:
        blockers.add("NO_VALID_EOD")
    # Fixture provenance cannot be promoted by a mutable outer JSON mode field.
    mode = "synthetic_test" if genesis["host"] == "synthetic_test" else "forward_observed_eod"
    selected = {v["bar"]["trade_day"]: v for v in versions}
    return dict(schema_version=1, data_mode=mode, source=config["source"], endpoint_version=VERSION,
                instrument=instrument, journal_genesis=rows[0][2], journal_head=rows[-1][2],
                event_count=len(rows), journal_chain=[r[2] for r in rows], as_of_journal_event_at=high,
                last_valid_source_day=max(selected, default=None),
                available_at_semantics=AVAILABILITY, raw_sha256=raw_hashes,
                bars=[selected[k] for k in sorted(selected)], versions=versions, attempts=attempts,
                coverage=coverage, gaps=[r for r in coverage if r["state"] not in ("valid_eod", "market_closed")],
                valid_eod_days=len(selected), on_day_valid_eod_days=len(forward_days), pending_runs=len(starts),
                warnings=sorted(warnings), blockers=sorted(blockers), can_research=not blockers,
                can_execute_forward_paper=False, live_allowed=False,
                historical_pit="NOT_VERIFIED", opening_source="BLOCKED")
