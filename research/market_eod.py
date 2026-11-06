"""Issue #82: incremental market coverage in the existing V1 warehouse/journal.

No model, order, position or trading permission is created here. Native V1 day
versions retain their ex-post contract; MarketDaySnapshot adds actual receipt
times and a current, dated catalog, never historical PIT membership.
"""
import argparse
import contextlib
import datetime as dt
from decimal import Decimal
import gzip
import json
import os
from pathlib import Path
import re
import sys
import time

import historical_sidecar as side

h = side.v1
require, Error = h.require, h.WarehouseError
canonical, sha = h.canonical, h.sha
VERSION = "market-day-snapshot-v1"
TZ = dt.timezone(dt.timedelta(hours=8))
FIELDS = {**h.FIELDS, **{a: side.FIELDS[a] for a in ("adj_factor", "suspend_d", "daily_basic")}}
PERMISSION = "Owner Issue #82 / existing Tushare account / local personal EOD research"
GOOD = ("OK", "EMPTY", "TRUNCATION_SUSPECTED")
SAFE = dict(historical_pit_status="NOT_VERIFIED", opening_source="BLOCKED",
            paper_allowed=False, live_allowed=False, cloud_egress=False)
RULES = "crates/contracts/src/paper.rs; research/timesfm_cpu/history.py (identity only; no trading admission)"
DDL = """
CREATE TABLE IF NOT EXISTS market_control(id INTEGER PRIMARY KEY CHECK(id=1),config TEXT NOT NULL,
 config_sha TEXT NOT NULL,enabled INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS market_catalogs(source_day TEXT PRIMARY KEY,content TEXT NOT NULL,sha TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS market_snapshots(id INTEGER PRIMARY KEY,source_day TEXT NOT NULL,
 content TEXT NOT NULL,sha TEXT NOT NULL UNIQUE);
CREATE INDEX IF NOT EXISTS market_snapshot_date ON market_snapshots(source_day,id DESC);
"""


def instant(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "TIMEZONE_REQUIRED")
    return result


def common_root():
    # Same repository-wide location used by the EOD Operator and research stores.
    import shadow
    return shadow.common_root()


def default_root():
    return common_root() / "state/historical-warehouse/market-eod"


def supported(row):
    return (row["exchange"] in ("SSE", "SZSE") and
            re.fullmatch(r"(?:60\d{4}\.SH|68\d{4}\.SH|00\d{4}\.SZ|30\d{4}\.SZ)", row["ts_code"]) is not None)


def validate(api, params, fields, rows):
    if api == "trade_cal":
        return h.validate(api, params, fields, rows)
    if api in side.FIELDS:
        return side.validate(api, params, fields, rows)
    if api == "stock_basic":
        require(set("ts_code,symbol,name,exchange,market,list_status,list_date,delist_date".split(",")) <= set(fields),
                "MISSING_REQUIRED_FIELDS")
    unique, duplicates = {}, 0
    for row in rows:
        code = row["ts_code"]
        require(isinstance(code, str) and bool(code), "INVALID_STOCK_CODE")
        if code in unique:
            require(unique[code][0] == row, "CONFLICTING_DUPLICATE_ROW")
            duplicates += 1
            continue
        if api == "stock_basic":
            require(row["exchange"] == params["exchange"] and row["list_status"] == params["list_status"],
                    "CATALOG_SCOPE_MISMATCH")
            require(isinstance(row["name"], str) and bool(row["name"]), "INVALID_CATALOG_NAME")
            if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", code):
                require(row["exchange"] == {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}[code[-2:]],
                        "CATALOG_EXCHANGE_IDENTITY_MISMATCH")
            for field in ("list_date", "delist_date"):
                if row[field]:
                    h.day(row[field])
            require(not row["list_date"] or not row["delist_date"] or row["list_date"] <= row["delist_date"],
                    "INVALID_LISTING_INTERVAL")
            cleaned = dict(row)
        else:
            # An invalid row is counted/rejected at the provider boundary, and
            # never inserted into the native V1 daily price tables.
            require(row["trade_date"] == params["trade_date"], "DATE_SCOPE_MISMATCH")
            if params.get("ts_code"):
                require(code in params["ts_code"].split(","), "PARTITION_SCOPE_MISMATCH")
            try:
                cleaned = h.validate(api, params, fields, [row])[0][0]
            except Error as error:
                cleaned = dict(ts_code=code, trade_date=row["trade_date"], rejection=str(error))
        unique[code] = (row, cleaned)
    return [unique[c][1] for c in sorted(unique)], duplicates


class Download(h.Download):
    fields = FIELDS
    permission_source = PERMISSION
    check_range = staticmethod(h.dates)
    validate_rows = staticmethod(validate)
    parse = staticmethod(side.parse)

    def budget_used(self):
        return self.db.execute("SELECT COUNT(*) FROM attempts WHERE started>=?", (self.session_start,)).fetchone()[0]

    def before_request(self, wait=0):
        config, enabled = self.w.config(self.db)
        require(enabled, "DISABLED")
        require(instant(h.now()).astimezone(TZ) + dt.timedelta(seconds=wait) <= self.deadline, "DEADLINE_REACHED")

    def truncated(self, api, count):
        return count >= ({"suspend_d": 5000}.get(api, 6000)) if api != "adj_factor" else False

    def fetch(self, api, params, *, retry=False):
        # Reuse committed requests after process death, including catalog parts.
        rows = self.db.execute("SELECT * FROM attempts WHERE api=? AND params=? AND started>=? ORDER BY id",
                               (api, canonical(params).decode(), self.session_start)).fetchall()
        if rows:
            old = rows[-1]
            if old["status"] in GOOD and not retry:
                return self.w.response(self.db, old["id"])
            require(old["status"] not in ("AUTH_DENIED", "PERMISSION_DENIED", "PARTIAL_QUOTA_LIMIT"), old["status"])
            require(len(rows) < 3, "ATTEMPT_LIMIT_REACHED")
            wait = max(300, int(old["retry_after"] or "0"))
            require((instant(h.now()) - instant(old["ended"])).total_seconds() >= wait, "WAITING_RETRY")
        result = self.request(api, params)
        require(result["status"] in GOOD, result["status"])
        return result


class Market(h.Warehouse):
    @contextlib.contextmanager
    def write(self):
        with super().write() as db:
            db.executescript(DDL)
            yield db

    def config(self, db):
        row = db.execute("SELECT * FROM market_control WHERE id=1").fetchone()
        require(row is not None and sha(row["config"].encode()) == row["config_sha"], "MARKET_CONFIG_REQUIRED")
        value = json.loads(row["config"])
        require(value["version"] == VERSION, "MARKET_CONFIG_VERSION")
        return value, bool(row["enabled"])

    def initialize(self, start_date, start_at="16:10", cutoff="18:00", rpm=10, min_coverage_bps=10000,
                   *, data_mode="tushare_incremental_eod"):
        h.day(start_date)
        begin, end = dt.time.fromisoformat(start_at), dt.time.fromisoformat(cutoff)
        require(dt.time(16) <= begin < end, "COLLECTION_WINDOW_AFTER_1600_REQUIRED")
        require(1 <= rpm <= 30 and 1 <= min_coverage_bps <= 10000, "INVALID_COLLECTION_POLICY")
        config = dict(version=VERSION, start_date=start_date, start_at=begin.isoformat(), cutoff=end.isoformat(),
                      rpm=rpm, min_coverage_bps=min_coverage_bps, data_mode=data_mode,
                      max_attempts_per_scope=3, retry_seconds=300, license="PERSONAL_LOCAL_NO_REDISTRIBUTION")
        with self.write() as db:
            require(db.execute("SELECT 1 FROM market_control").fetchone() is None, "ALREADY_INITIALIZED")
            with db:
                db.execute("INSERT INTO market_control VALUES(1,?,?,0)", (canonical(config).decode(), sha(canonical(config))))
        return dict(state="DISABLED", **SAFE)

    def control(self, enabled):
        with self.write() as db:
            self.config(db)
            with db:
                db.execute("UPDATE market_control SET enabled=? WHERE id=1", (int(enabled),))
        return dict(state="ENABLED" if enabled else "DISABLED", **SAFE)

    def reference(self, db, attempt_id):
        row = db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        require(row is not None and row["metadata_sha"] == h.attempt_hash(row), "REQUEST_METADATA_SHA")
        return dict(id=attempt_id, api=row["api"], params=json.loads(row["params"]), status=row["status"],
                    response_sha256=row["response_sha"], metadata_sha256=row["metadata_sha"],
                    received_at=row["ended"], available_at=row["ended"], row_count=row["row_count"],
                    duplicates=row["duplicates"])

    def response(self, db, attempt_id):
        ref = self.reference(db, attempt_id)
        require(ref["status"] in GOOD, ref["status"])
        raw = gzip.decompress(self.raw_path(attempt_id).read_bytes())
        require(sha(raw) == ref["response_sha256"], "RAW_SHA_MISMATCH")
        state, _, fields, original = side.parse(raw)
        require(state == "OK", "RAW_RESPONSE_STATE")
        rows, _ = validate(ref["api"], ref["params"], fields, original)
        saved = db.execute("SELECT canonical_sha FROM attempts WHERE id=?", (attempt_id,)).fetchone()[0]
        require(sha(canonical(rows)) == saved, "NORMALIZED_SOURCE_SHA")
        return dict(id=attempt_id, status=ref["status"], rows=rows)

    def calendar(self, db, download, today):
        receipts, values = [], {}
        horizon = (h.day(today) + dt.timedelta(days=40)).strftime("%Y%m%d")
        for exchange in ("SSE", "SZSE"):
            result = download.fetch("trade_cal", dict(exchange=exchange, start_date=download.start, end_date=horizon))
            require(result["status"] != "TRUNCATION_SUSPECTED", "CALENDAR_TRUNCATED")
            days = {r["cal_date"]: r["is_open"] for r in result["rows"]}
            require(set(days) == set(h.dates(download.start, horizon)), "CALENDAR_GAP")
            receipts.append(result["id"])
            values[exchange] = days
            if not db.execute("SELECT 1 FROM objects WHERE attempt_id=?", (result["id"],)).fetchone():
                self.publish_objects(db, "trade_cal", result["rows"], result["id"])
        require(values["SSE"] == values["SZSE"], "CALENDAR_CONFLICT")
        return {day: opened for day, opened in values["SSE"].items() if day <= today}, receipts

    def catalog(self, db, download, today):
        old = db.execute("SELECT content,sha FROM market_catalogs WHERE source_day=?", (today,)).fetchone()
        if old:
            require(sha(old[0].encode()) == old[1], "CATALOG_SHA")
            value = json.loads(old[0])
            require("scopes" in value, "CATALOG_SCOPE_NOT_VERIFIED")
            return value
        sources, rows, blockers = [], {}, []
        for exchange in h.EXCHANGES:
            for status in h.STATUSES:
                result = download.fetch("stock_basic", dict(exchange=exchange, list_status=status))
                sources.append(result["id"])
                if result["status"] == "TRUNCATION_SUSPECTED":
                    blockers.append("CATALOG_TRUNCATED:" + exchange + ":" + status)
                for row in result["rows"]:
                    code = row["ts_code"]
                    require(code not in rows, "CATALOG_CONFLICTING_STATUS")
                    rows[code] = row
        # B shares are outside the A-share denominator; retain their count and raw.
        excluded = [c for c in rows if re.fullmatch(r"(?:900\d{3}\.SH|200\d{3}\.SZ)", c)]
        rows = {c: r for c, r in rows.items() if c not in excluded}
        prior = db.execute("SELECT source_day,content,sha FROM market_catalogs WHERE source_day<? ORDER BY source_day DESC LIMIT 1",
                           (today,)).fetchone()
        missing, comparison = {}, None
        if prior:
            require(sha(prior[1].encode()) == prior[2], "CATALOG_SHA")
            previous = json.loads(prior[1])
            comparison = dict(source_day=prior[0], sha256=prior[2])
            # An absent code is not evidence of delisting. A returned D/P row
            # or another explicit status transition retains the code identity.
            missing = {r["ts_code"]: r for r in previous["rows"]
                       if r["list_status"] in ("L", "P") and r["ts_code"] not in rows
                       and (not r["delist_date"] or today < r["delist_date"])}
        scopes = {}
        for exchange in h.EXCHANGES:
            listed = sum(r["exchange"] == exchange and r["list_status"] == "L" for r in rows.values())
            lost = sum(r["exchange"] == exchange for r in missing.values())
            reasons = []
            if listed == 0:
                reasons.append("LISTED_SCOPE_EMPTY")
            if lost:
                reasons.append("PRIOR_SECURITIES_DISAPPEARED")
            if any(b.startswith("CATALOG_TRUNCATED:" + exchange + ":") for b in blockers):
                reasons.append("TRUNCATED_SCOPE")
            scopes[exchange] = dict(state="NOT_VERIFIED" if reasons else "VERIFIED", listed_rows=listed,
                                    current_rows=sum(r["exchange"] == exchange for r in rows.values()),
                                    missing_prior_rows=lost, reasons=reasons)
            blockers.extend("CATALOG_" + reason + ":" + exchange for reason in reasons)
        # Retain previously known identities as an explicit gap, never shrink
        # the market denominator merely because the provider omitted a block.
        rows.update(missing)
        value = dict(version=VERSION, source_day=today, sources=sources, blockers=sorted(blockers),
                     state="NOT_VERIFIED" if blockers else "VERIFIED", scopes=scopes,
                     missing_symbols=sorted(missing), comparison=comparison,
                     rows=[rows[c] for c in sorted(rows)], excluded_b_shares=len(excluded),
                     membership="CURRENT_DATED_CATALOG_NOT_HISTORICAL_PIT")
        with db:
            db.execute("INSERT INTO market_catalogs VALUES(?,?,?)", (today, canonical(value).decode(), sha(canonical(value))))
        return value

    def batch(self, db, download, api, date, catalog, retry):
        results = [self.batch_scope(db, download, api, dict(trade_date=date, suspend_type=kind), catalog, retry)
                   for kind in ("S", "R")] if api == "suspend_d" else [
                   self.batch_scope(db, download, api, dict(trade_date=date), catalog, retry)]
        rows = sorted((r for part, _, _ in results for r in part), key=canonical)
        sources = [a for _, ids, _ in results for a in ids]
        state = ("PARTITIONED_CURRENT_CATALOG" if any(s == "PARTITIONED_CURRENT_CATALOG" for _, _, s in results)
                 else results[0][2] if api != "suspend_d" else "OK" if rows else "EMPTY")
        return rows, sources, state

    def batch_scope(self, db, download, api, params, catalog, retry):
        result = download.fetch(api, params, retry=retry)
        sources = [result["id"]]
        if result["status"] != "TRUNCATION_SUSPECTED" or api not in ("daily", "suspend_d"):
            return result["rows"], sources, result["status"]
        # Documented multi-code requests, never one request per security. The
        # complete dated catalog is the denominator, not the first capped page.
        codes = sorted({r["ts_code"] for r in catalog["rows"]
                        if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", r["ts_code"])} |
                       {r["ts_code"] for r in result["rows"]})
        merged = {}
        for offset in range(0, len(codes), 200):
            part = download.fetch(api, dict(params, ts_code=",".join(codes[offset:offset+200])))
            require(part["status"] != "TRUNCATION_SUSPECTED", "PARTITION_TRUNCATED")
            sources.append(part["id"])
            for row in part["rows"]:
                key = side.key(row, api) if api == "suspend_d" else row["ts_code"]
                require(key not in merged or merged[key] == row, "PARTITION_CONFLICT")
                merged[key] = row
        for row in result["rows"]:
            key = side.key(row, api) if api == "suspend_d" else row["ts_code"]
            require(merged.get(key) == row, "PARTITION_RESPONSE_CONFLICT")
        return [merged[k] for k in sorted(merged)], sources, "PARTITIONED_CURRENT_CATALOG"

    def load_snapshot(self, db, date):
        row = db.execute("SELECT content,sha FROM market_snapshots WHERE source_day=? ORDER BY id DESC LIMIT 1", (date,)).fetchone()
        if row is None:
            return None
        require(sha(row[0].encode()) == row[1], "SNAPSHOT_SHA")
        value = json.loads(row[0])
        # R1 scope evidence cannot be reconstructed by relabelling a frozen
        # pre-R1 snapshot. Keep its bytes, but reject it as current admission.
        require("catalog_scopes" in value, "CATALOG_SCOPE_NOT_VERIFIED")
        for ref in value["sources"]:
            require(self.reference(db, ref["id"]) == ref, "SNAPSHOT_SOURCE_CHANGED")
        return dict(snapshot_sha256=row[1], **value)

    def publish(self, db, date, config, catalog, cal_sources, data, refs, states):
        prices = {r["ts_code"]: r for r in data["daily"] if "rejection" not in r}
        invalid = {r["ts_code"]: r["rejection"] for r in data["daily"] if "rejection" in r}
        factors = {r["ts_code"]: r for r in data["adj_factor"]}
        basics = {r["ts_code"]: r for r in data["daily_basic"]}
        suspended = {r["ts_code"] for r in data["suspend_d"] if r["suspend_type"] == "S"}
        full_suspended = {r["ts_code"] for r in data["suspend_d"] if r["suspend_type"] == "S" and r["suspend_timing"] in (None, "", "全天")}
        classes, expected, candidates, eligible = [], set(), set(), []
        anomalies, gaps = [], []
        for row in catalog["rows"]:
            code = row["ts_code"]
            capable = supported(row)
            reasons = []
            if code in catalog["missing_symbols"]:
                category, reasons = "CATALOG_MISSING", ["ABSENT_FROM_CURRENT_CATALOG"]
                if row["list_date"] and row["list_date"] <= date and (not row["delist_date"] or date < row["delist_date"]):
                    expected.add(code)
                    gaps.append(code)
            elif row["delist_date"] and date >= row["delist_date"]:
                category = "DELISTED"
            elif row["list_status"] in ("UN", "G"):
                category = "NOT_LISTED"
            elif not row["list_date"] or (row["list_status"] == "D" and not row["delist_date"]):
                category, reasons = "LISTING_UNVERIFIED", ["LISTING_INTERVAL_MISSING"]
            elif date < row["list_date"]:
                category = "NOT_LISTED"
            else:
                expected.add(code)
                if code not in prices and code not in full_suspended:
                    gaps.append(code)
                if capable and code not in suspended and row["list_date"] != date:
                    candidates.add(code)
                if not capable:
                    category, reasons = "UNSUPPORTED", ["MARKET_IDENTITY_OR_RULES_UNSUPPORTED"]
                elif code in invalid:
                    category, reasons = "ANOMALOUS", [invalid[code]]
                    anomalies.append(code)
                elif code in suspended or row["list_status"] == "P":
                    category, reasons = "SUSPENDED", ["SUSPENSION_REPORTED"]
                elif code not in prices:
                    category, reasons = "MISSING", ["DAILY_ROW_MISSING_NOT_PROOF_OF_SUSPENSION"]
                elif row["list_date"] == date:
                    category, reasons = "NEW_LISTING", ["NEW_LISTING_CONTEXT_REQUIRED"]
                else:
                    price = prices[code]
                    if price.get("quality_flags") or Decimal(price["vol"]) <= 0 or Decimal(price["amount"]) <= 0:
                        reasons.append("DAILY_QUALITY_UNVERIFIED")
                    if code not in factors:
                        reasons.append("ADJ_FACTOR_MISSING")
                    if states["suspend_d"] not in GOOD + ("PARTITIONED_CURRENT_CATALOG",):
                        reasons.append("SUSPENSION_SOURCE_BLOCKED")
                    if code in basics:
                        if basics[code]["close"] is None:
                            reasons.append("DAILY_BASIC_CLOSE_MISSING")
                        elif Decimal(basics[code]["close"]) != Decimal(price["close"]):
                            reasons.append("DAILY_BASIC_CLOSE_CONFLICT")
                    category = "ANOMALOUS" if reasons else "QUOTED"
                    if reasons:
                        anomalies.append(code)
                    else:
                        eligible.append(code)
            classes.append(dict(ts_code=code, name=row["name"], exchange=row["exchange"],
                                list_status=row["list_status"], list_date=row["list_date"], delist_date=row["delist_date"],
                                category=category, supported=capable, reasons=reasons,
                                rule_source=RULES if capable else "UNSUPPORTED_NO_TRADING_RULE_ADMISSION"))
        unknown = sorted((set(prices) | set(invalid)) - {r["ts_code"] for r in catalog["rows"]})
        explained = (set(prices) | full_suspended) & expected
        coverage = len(explained) * 10000 // len(expected) if expected else 0
        blockers = list(catalog["blockers"])
        if any(r["category"] == "LISTING_UNVERIFIED" for r in classes):
            blockers.append("LISTING_INTERVAL_UNVERIFIED")
        if not expected:
            blockers.append("EMPTY_EXPECTED_UNIVERSE")
        if coverage < config["min_coverage_bps"]:
            blockers.append("MARKET_COVERAGE_BELOW_THRESHOLD")
        if anomalies or invalid:
            blockers.append("ANOMALOUS_SOURCE_ROWS")
        if unknown:
            blockers.append("UNCATALOGUED_DAILY_SYMBOLS")
        for api in ("daily", "adj_factor", "suspend_d"):
            if states[api] not in GOOD + ("PARTITIONED_CURRENT_CATALOG",):
                blockers.append(api.upper() + "_SOURCE_BLOCKED")
        sources = [self.reference(db, a) for a in sorted(set(catalog["sources"] + cal_sources + sum(refs.values(), [])))]
        received = max(r["available_at"] for r in sources)
        available = h.now()
        require(instant(available) >= instant(received), "SNAPSHOT_CLOCK_BEFORE_SOURCE")
        daily_rows = sorted(prices.values(), key=lambda r: r["ts_code"])
        native = self.publish_day(db, date, daily_rows, refs["daily"], "PARTIAL" if blockers else "COMPLETE",
                                  "MARKET_SNAPSHOT_BLOCKED" if blockers else "MARKET_COVERAGE_VERIFIED_CURRENT_CATALOG")
        from collections import Counter
        value = dict(schema_version=1, kind="MarketDaySnapshot", version=VERSION, source_day=date,
                     data_mode=config["data_mode"], state="BLOCKED" if blockers else "READY", **SAFE,
                     received_at=received, available_at=available, provider_published_at=None,
                     late_backfill=instant(available).astimezone(TZ).strftime("%Y%m%d") > date,
                     availability="ACTUAL_RECEIPT_ONLY_DAILY_OPEN_IS_NOT_T_PLUS_1_OBSERVED_PRICE",
                     catalog_source_day=catalog["source_day"], catalog_sha256=sha(canonical(catalog)),
                     catalog_state=catalog["state"], catalog_scopes=catalog["scopes"],
                     catalog_missing_symbols=catalog["missing_symbols"],
                     market_denominator_verified=catalog["state"] == "VERIFIED",
                     catalog_membership=catalog["membership"], native_day_version=native["version_id"],
                     rule_sources=[dict(path=p, sha256=sha((h.ROOT / p).read_bytes())) for p in
                                   ("crates/contracts/src/paper.rs", "research/timesfm_cpu/history.py")],
                     trading_rules_status="REFERENCE_ONLY_NOT_EXECUTION_QUALIFIED",
                     catalog_total=len(classes), excluded_b_shares=catalog["excluded_b_shares"],
                     expected_market=len(expected), actual_quoted=len(set(prices) & expected),
                     market_explained=len(explained), market_coverage_bps=coverage,
                     completeness_threshold_bps=config["min_coverage_bps"], research_denominator=len(candidates),
                     research_qualified_before_market_gate=len(eligible),
                     eligible_symbols=[] if blockers else sorted(eligible),
                     categories=dict(sorted(Counter(r["category"] for r in classes).items())), securities=classes,
                     missing_symbols=sorted(gaps), anomalous_symbols=sorted(set(anomalies) | set(invalid)),
                     unknown_symbols=unknown, source_states=states,
                     suspend_query_types=sorted({r["params"]["suspend_type"] for r in sources
                         if r["api"] == "suspend_d" and r["status"] in GOOD}),
                     source_coverage={api: dict(rows=len(data[api]),
                         missing_quoted=sorted(set(prices) - {r["ts_code"] for r in data[api]}))
                         for api in ("adj_factor", "daily_basic")},
                     sources=sources, blockers=sorted(set(blockers)))
        with db:
            db.execute("INSERT OR IGNORE INTO market_snapshots(source_day,content,sha) VALUES(?,?,?)",
                       (date, canonical(value).decode(), sha(canonical(value))))
        return value

    def once(self, *, transport=None, clock=h.now, token_source="auto", fault=lambda point: None):
        with self.write() as db:
            config, enabled = self.config(db)
            if not enabled:
                return dict(state="DISABLED", **SAFE)
            local = instant(clock()).astimezone(TZ)
            today = local.strftime("%Y%m%d")
            old = self.load_snapshot(db, today)
            if old and old["state"] == "READY":
                pending = False
                for row in self.latest_objects(db, "trade_cal"):
                    if row["exchange"] == "SSE" and row["is_open"] == "1" and config["start_date"] <= row["cal_date"] < today:
                        previous = self.load_snapshot(db, row["cal_date"])
                        pending |= previous is None or previous["state"] != "READY"
                if not pending:
                    return dict(state="ALREADY_FROZEN", snapshot_sha256=old["snapshot_sha256"], **SAFE)
            require(config["start_date"] <= today, "START_DATE_IN_FUTURE")
            if transport is None:
                token, source = h.credential(token_source)
                transport = h.TushareHTTP(token)
            else:
                source = "offline-recorded-test-transport"
            download = Download(self, db, "market-eod", config["start_date"], today, transport, source,
                                max_calls=90, total_cap=10000, rpm=config["rpm"])
            download.session_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc).isoformat()
            # No fixed clock window: each run is bounded, and today's snapshot is
            # only requested after the market has closed.
            download.deadline = local + dt.timedelta(minutes=30)
            try:
                calendar, cal_refs = self.calendar(db, download, today)
                if calendar[today] == "0":
                    download.finish("MARKET_CLOSED")
                    return dict(state="MARKET_CLOSED", **SAFE)
                catalog = self.catalog(db, download, today)
                state = "READY"
                published = 0
                waiting = None
                for date, opened in sorted(calendar.items()):
                    if opened == "0":
                        continue
                    if date == today:
                        if local.time() < dt.time(15, 5):
                            waiting = "WAITING_FOR_MARKET_CLOSE"
                            continue
                    previous = self.load_snapshot(db, date)
                    if previous and previous["state"] == "READY":
                        continue
                    data, refs, states = {}, {}, {}
                    for api in ("daily", "adj_factor", "suspend_d", "daily_basic"):
                        try:
                            data[api], refs[api], states[api] = self.batch(db, download, api, date, catalog, previous is not None)
                        except Error as error:
                            # Optional/required support permission is explicit in
                            # the snapshot; only daily failure stops publication.
                            if api == "daily" or str(error) not in ("PERMISSION_DENIED", "AUTH_DENIED", "PARTIAL_QUOTA_LIMIT"):
                                raise
                            denied = db.execute("SELECT id FROM attempts WHERE api=? ORDER BY id DESC LIMIT 1", (api,)).fetchone()
                            data[api], refs[api], states[api] = [], [denied[0]] if denied else [], str(error)
                    fault("before_snapshot")
                    snapshot = self.publish(db, date, config, catalog, cal_refs, data, refs, states)
                    fault("after_snapshot")
                    published += 1
                    if snapshot["state"] == "BLOCKED":
                        state = "BLOCKED"
                download.finish(state)
                if published == 0 and waiting is not None:
                    return dict(state=waiting, requests_this_run=download.calls, **SAFE)
                return dict(state=state, requests_this_run=download.calls, **SAFE)
            except Error as error:
                download.finish(str(error))
                return dict(state=str(error), requests_this_run=download.calls, **SAFE)

    def backfill(self, sessions=84, *, transport=None, clock=h.now, token_source="auto"):
        """Collect past sessions, then continue from the latest trading day.

        Each run stays inside the normal per-run call cap, so a wide range is
        filled across several rounds.
        """
        require(1 <= sessions <= 250, "INVALID_BACKFILL_SESSIONS")
        with self.write() as db:
            config, enabled = self.config(db)
            require(enabled, "MARKET_DISABLED")
            today = instant(clock()).astimezone(TZ).date()
            # ~1.45 calendar days per trading day covers weekends and holidays.
            floor = (today - dt.timedelta(days=int(sessions * 1.45) + 7)).strftime("%Y%m%d")
            if config["start_date"] > floor:
                config["start_date"] = floor
                blob = canonical(config).decode()
                with db:
                    db.execute("UPDATE market_control SET config=?,config_sha=? WHERE id=1",
                               (blob, sha(blob.encode())))
        outcome = self.once(transport=transport, clock=clock, token_source=token_source)
        report = self.report()
        return dict(outcome, target_start=floor, sessions=sessions,
                    remaining=len(report["gaps"]),
                    sessions_ready=report["sessions_ready"],
                    last_successful_date=report["last_successful_date"])

    def backfill_rounds(self, sessions=84, rounds=6, *, transport=None, clock=h.now,
                        token_source="auto"):
        require(1 <= rounds <= 12, "INVALID_BACKFILL_ROUNDS")
        history, outcome = [], None
        progress = self.root.parents[2] / "backfill.progress.json"
        for _ in range(rounds):
            outcome = self.backfill(sessions, transport=transport, clock=clock,
                                    token_source=token_source)
            history.append(dict(state=outcome["state"],
                                requests=outcome.get("requests_this_run", 0),
                                remaining=outcome["remaining"]))
            # The collector holds the warehouse writer lock for a whole batch, so
            # the dashboard reads this small file instead of the database.
            progress.write_text(json.dumps(dict(
                sessions=sessions,
                sessions_ready=outcome["sessions_ready"],
                remaining=outcome["remaining"],
                state=outcome["state"],
                updated_at=instant(h.now()).astimezone(TZ).isoformat(),
            )), encoding="utf-8")
            if outcome["remaining"] == 0 or history[-1]["requests"] == 0:
                break
        return dict(state="COMPLETE" if outcome["remaining"] == 0 else "PARTIAL",
                    sessions=sessions, remaining=outcome["remaining"],
                    last_successful_date=outcome["last_successful_date"],
                    target_start=outcome["target_start"], rounds=history)

    def report(self):
        with self.read(inspect_raw_paths=False) as db:
            config, enabled = self.config(db)
            dates = [r[0] for r in db.execute("SELECT DISTINCT source_day FROM market_snapshots ORDER BY source_day")]
            snapshots = [self.load_snapshot(db, date) for date in dates]
            run = db.execute("SELECT status,started,ended FROM runs WHERE kind='market-eod' ORDER BY id DESC LIMIT 1").fetchone()
            latest = snapshots[-1] if snapshots else None
            by_date = {s["source_day"]: s for s in snapshots}
            calendar = {r["cal_date"]: r["is_open"] for r in self.latest_objects(db, "trade_cal") if r["exchange"] == "SSE"}
            gaps = [dict(source_day=date, missing=len(by_date[date]["missing_symbols"]) if date in by_date else None,
                         blockers=by_date[date]["blockers"] if date in by_date else ["NO_FROZEN_MARKET_SNAPSHOT"])
                    for date in sorted(calendar) if calendar[date] == "1" and date <= instant(h.now()).astimezone(TZ).strftime("%Y%m%d") and
                    (date not in by_date or by_date[date]["state"] != "READY")]
            ready_sessions = sum(
                1 for date in dates
                if self.load_snapshot(db, date)["state"] == "READY")
            return dict(version=VERSION, state=run["status"] if run else "NOT_COLLECTED", enabled=enabled,
                        sessions_ready=ready_sessions, **SAFE,
                        data_mode=config["data_mode"], config=config, last_run=dict(run) if run else None,
                        last_successful_date=max((s["source_day"] for s in snapshots if s["state"] == "READY"), default=None),
                        latest=latest, gaps=gaps,
                        interface_permissions={r["api"]: r["status"] for r in db.execute("SELECT * FROM permissions")},
                        network_operation=False)

    def research_source(self, date, symbols, as_of):
        require(symbols and len(symbols) == len(set(symbols)), "SYMBOL_SELECTION_REQUIRED")
        with self.read(inspect_raw_paths=False) as db:
            snapshot = self.load_snapshot(db, date)
            require(snapshot is not None and snapshot["state"] == "READY", "MARKET_DAY_NOT_QUALIFIED")
            require(instant(as_of) >= instant(snapshot["available_at"]), "SOURCE_NOT_AVAILABLE_AT_DECISION")
            require(set(symbols) <= set(snapshot["eligible_symbols"]), "SECURITY_NOT_ELIGIBLE")
            parts = {}
            for ref in snapshot["sources"]:
                if ref["status"] not in GOOD:
                    require(ref["api"] == "daily_basic", "SOURCE_PERMISSION_BLOCKED")
                    continue
                rows = self.response(db, ref["id"])["rows"]
                if ref["api"] in ("daily", "adj_factor", "suspend_d", "daily_basic"):
                    parts.setdefault(ref["api"], {}).update({canonical(r).decode(): r for r in rows if r["ts_code"] in symbols})
            return dict(snapshot_sha256=snapshot["snapshot_sha256"], source_day=date,
                        data_mode=snapshot["data_mode"], available_at=snapshot["available_at"], **SAFE,
                        sources={api: sorted(rows.values(), key=canonical) for api, rows in parts.items()})


def optional_paper_step(market, phase):
    # Include import/initialization in the optional boundary. Explicit process
    # stops (BaseException) still leave the foreground watch immediately.
    try:
        import paper_portfolio
        return paper_portfolio.optional_step(market, phase)
    except Exception as error:
        import traceback
        traceback.print_exc(file=sys.stderr)
        return dict(state="BLOCKED", reason="PAPER_MODULE_UNAVAILABLE",
                    detail=dict(type=type(error).__name__, message=str(error)[:200]))


def cli(argv=None):
    parser = argparse.ArgumentParser(description="全市场 EOD；复用原仓库和 journal，无研究/交易派发。")
    parser.add_argument("action", choices=("init", "enable", "disable", "once", "watch", "backfill", "status", "report", "verify"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--start-date")
    parser.add_argument("--start-at", default="16:10")
    parser.add_argument("--cutoff", default="18:00")
    parser.add_argument("--rpm", type=int, default=10)
    parser.add_argument("--min-coverage-bps", type=int, default=10000)
    parser.add_argument("--credential-source", choices=("auto", "existing-tushare-mcp-config"), default="auto")
    parser.add_argument("--sessions", type=int, default=84)
    parser.add_argument("--rounds", type=int, default=6)
    args = parser.parse_args(argv)
    try:
        market = Market(args.root if args.root else default_root())
        if args.action == "init":
            result = market.initialize(args.start_date or dt.datetime.now(TZ).strftime("%Y%m%d"), args.start_at,
                                       args.cutoff, args.rpm, args.min_coverage_bps)
        elif args.action in ("enable", "disable"):
            result = market.control(args.action == "enable")
        elif args.action == "backfill":
            result = market.backfill_rounds(args.sessions, args.rounds, token_source=args.credential_source)
        elif args.action in ("once", "watch"):
            while True:
                result = market.once(token_source=args.credential_source)
                # First successful collection enables the default simulated policy
                # once; later cycles only read the frozen policy. A policy fault is
                # isolated so it cannot stop market collection.
                try:
                    import paper_portfolio
                    if paper_portfolio.binding_path().is_file():
                        result["paper_policy"] = paper_portfolio.ensure_policy(market)
                except Exception as error:
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    result["paper_policy"] = dict(
                        state="BLOCKED", reason="PAPER_POLICY_ENSURE_FAILED",
                        detail=dict(type=type(error).__name__, message=str(error)[:200]))
                # Settle the prior frozen Paper batch before optional research;
                # Agent faults cannot starve ledger expiry or future collection.
                result["paper_confirmation"] = optional_paper_step(market, "confirm")
                # Optional research is a separate failure boundary AFTER the
                # collector committed its result. Even an unavailable Agent DB
                # must not stop future EOD polls. Explicit stops still propagate.
                try:
                    if (common_root() / "state/risk-portfolio/agent-binding.json").is_file():
                        import market_research
                        result["research"] = market_research.once(market)
                except Exception:
                    # Do not depend on that same failed DB to report the fault,
                    # or expose exception text containing private paths/payloads.
                    result["research"] = dict(state="BLOCKED", reason="RESEARCH_UNAVAILABLE")
                result["paper_decision"] = optional_paper_step(market, "freeze")
                if args.action == "once":
                    break
                print(json.dumps(result, ensure_ascii=False), flush=True)
                # A blocked or incomplete attempt is retried, not hammered.
                time.sleep(300 if result.get("state") in ("BLOCKED", "NETWORK_OUTCOME_UNKNOWN") else 30)
        else:
            if args.action == "status":
                # Status stays readonly. A free lock plus a dirty WAL is recovery,
                # not a license to read an uncheckpointed snapshot.
                try:
                    market.checkpoint_if_idle()
                except Error:
                    pass
            result = market.report()
            if args.action == "verify":
                with market.read(inspect_raw_paths=False) as db:
                    for row in db.execute("SELECT id FROM attempts ORDER BY id"):
                        ref = market.reference(db, row[0])
                        if ref["status"] in GOOD:
                            market.response(db, row[0])
                result = dict(state="VERIFIED_LOCAL_INTEGRITY", last_successful_date=result["last_successful_date"], **SAFE)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (Error, OSError, ValueError) as error:
        # Provider errors are fixed codes from the shared transport/parser.
        code = str(error) if isinstance(error, Error) else "LOCAL_IO_OR_CONFIG_ERROR"
        print(json.dumps(dict(state="BLOCKED", reason=code, **SAFE), ensure_ascii=False))
        return 1
    return 0
