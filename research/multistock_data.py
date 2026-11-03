"""Bounded, read-only consumption of admitted PR58/60 versions; never downloads."""
from __future__ import annotations

from collections import Counter
import contextlib
from decimal import Decimal
import json
from pathlib import Path

import historical_sidecar as sidecar

v1 = sidecar.v1
require, Error, sha, canonical = v1.require, v1.WarehouseError, v1.sha, v1.canonical
APIS = ("daily", "adj_factor", "daily_basic", "suspend_d", "stk_limit")
DAILY_SQL = """SELECT d.row_json,d.row_sha FROM day_rows r
 JOIN daily_rows d ON d.ts_code=r.ts_code AND d.trade_date=r.trade_date AND d.row_sha=r.row_sha
 WHERE r.version_id=? ORDER BY r.ts_code"""
SIDECAR_SQL = "SELECT row_json,row_sha FROM rows WHERE version_id=? ORDER BY row_key"


def file_receipts(roots):
    """Only known database/lock sidecars, no raw walk, checksum or state-wide mtime scan."""
    out = []
    for root in roots:
        receipt = {}
        for name in ("warehouse.sqlite", "writer.lock", "warehouse.sqlite-wal",
                     "warehouse.sqlite-shm", "warehouse.sqlite-journal"):
            p = Path(root) / name
            receipt[name] = dict(bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns) if p.exists() else None
        out.append(receipt)
    return out


class Dataset:
    def __init__(self, v1_root, v2_root, start=v1.START, end=v1.END,
                 v1_version=None, v2_version=None, max_rows_per_partition=25000):
        v1.historical_range(start, end)
        self.roots = [Path(v1_root).absolute(), Path(v2_root).absolute()]
        require(self.roots[0] != self.roots[1], "V1_V2_STORE_COLLISION")
        self.start, self.end = start, end
        self.bounds = [v1_version, v2_version]
        self.row_cap = max_rows_per_partition

    def __enter__(self):
        self.stack = contextlib.ExitStack()
        try:
            self.dbs = []
            for root, check in zip(self.roots, (v1.check_contract, sidecar.check_contract)):
                # Reuse the owning lexical no-link, writer and immutable/WAL rules.
                # No recursive raw inspection: those inputs were already accepted.
                v1.Warehouse(root).check_paths(descendants=False)
                self.stack.enter_context(v1.writer_lock(root, readonly=True))
                db = v1.connection(root / "warehouse.sqlite", readonly=True)
                self.stack.callback(db.close)
                check(db)
                db.execute("PRAGMA cache_size=-8192")
                db.execute("PRAGMA threads=1")
                self.dbs.append(db)
            self._freeze()
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)

    def _freeze(self):
        old, new = self.dbs
        frozen_objects = {api: sidecar.Sidecar(self.roots[1]).objects(new, api)
                          for api in ("stock_basic", "trade_cal")}
        meta = new.execute("SELECT * FROM metadata_source WHERE id=1").fetchone()
        require(meta and sha(meta["manifest"].encode()) == meta["sha"], "METADATA_SOURCE_BINDING")
        metadata = json.loads(meta["manifest"])
        require(metadata["objects_sha"] == sha(canonical(frozen_objects)), "METADATA_OBJECTS_BINDING")
        require(metadata["source_contract_sha"] == sha(canonical(v1.CONTRACT)), "V1_METADATA_CONTRACT")
        # Frozen V2 metadata, rather than a subsequently refreshed current catalog,
        # owns this experiment's calendar/identity limitations. Bind its old receipts
        # to the accepted V1 attempts without scanning any raw/object row history.
        receipts = metadata.get("source_receipts", [])
        for receipt in receipts:
            r=old.execute("SELECT api,response_sha,metadata_sha,ended FROM attempts WHERE id=?",(receipt["id"],)).fetchone()
            require(r and all(r[k] == receipt[k] for k in r.keys()), "V1_V2_METADATA_RECEIPT")
        self.origin = ("SYNTHETIC" if "synthetic" in metadata.get("source", "").lower()
                       else "REAL_LOCAL_HISTORY" if receipts and metadata.get("frozen_at_utc") else "UNKNOWN_LOCAL_SOURCE")
        self.catalog = {r["ts_code"]: r for r in frozen_objects["stock_basic"]}
        self.calendar = {(r["exchange"], r["cal_date"]): r["is_open"] for r in frozen_objects["trade_cal"]}
        self.days = sorted({d for (e,d), is_open in self.calendar.items()
                            if e in ("SSE", "SZSE") and is_open == "1" and self.start <= d <= self.end})
        require(self.days, "NO_SOURCE_CALENDAR")
        self.partitions = {api: {} for api in APIS}
        self.version_bounds = []
        for i, (db, table) in enumerate(zip(self.dbs, ("day_versions", "versions"))):
            bound = self.bounds[i]
            if bound is None:
                bound = db.execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]
            require(bound and db.execute(f"SELECT 1 FROM {table} WHERE id=?", (bound,)).fetchone(), "VERSION_BOUND_NOT_FOUND")
            self.version_bounds.append(bound)
            group = "trade_date" if i == 0 else "api,trade_date"
            rows = db.execute(f"""SELECT v.* FROM {table} v JOIN
                (SELECT MAX(id) id FROM {table} WHERE trade_date BETWEEN ? AND ? AND id<=? GROUP BY {group}) c
                ON v.id=c.id ORDER BY v.trade_date,v.id""", (self.start, self.end, bound))
            for row in rows:
                r = dict(row)
                api = "daily" if i == 0 else r["api"]
                require(api in APIS and r["status"] in ("COMPLETE", "PARTIAL"), "UNADMITTED_PARTITION")
                require(r["row_count"] <= self.row_cap, "PARTITION_RESOURCE_LIMIT")
                manifest = json.loads(r.pop("manifest"))
                require(sha(canonical(manifest)) == r["source_sha"], "PARTITION_SOURCE_BINDING")
                # Reuse accepted content hashes; do not re-verify raw responses or old row hashes.
                r["manifest"] = manifest
                if api == "adj_factor":
                    r["interpretation"] = ("SOURCE_RESPONSE_COMPLETE_BY_DOCUMENTED_SCOPE" if r["status"] == "COMPLETE"
                        else "LEGACY_ADMISSION_LABEL_PRESERVED_NO_NUMERIC_CAP_INFERRED")
                self.partitions[api][r["trade_date"]] = r
        self.refs = dict(version_bounds=dict(v1=self.version_bounds[0], v2=self.version_bounds[1]),
            metadata_source_sha=meta["sha"], metadata_objects_sha=metadata["objects_sha"],
            partitions=self.partitions, calendar_sha=sha(canonical(frozen_objects["trade_cal"])),
            prior_acceptance=["https://github.com/handFOOLed/Stratide/pull/58", "https://github.com/handFOOLed/Stratide/pull/60"],
            baseline_validation="REUSE_PREVIOUSLY_ACCEPTED_SOURCE_BINDING_NO_RAW_REVERIFY")
        self.source_sha = sha(canonical(self.refs))
        self.query_sha = sha(canonical(dict(source_sha=self.source_sha, start=self.start, end=self.end,
            daily_sql=DAILY_SQL, sidecar_sql=SIDECAR_SQL, join="exact_ts_code_trade_date_no_imputation_v1")))

    def inspect(self):
        return dict(**v1.SAFE, source_origin=self.origin, coverage="PARTIAL", source_sha=self.source_sha,
            query_sha=self.query_sha, range=[self.start,self.end], sessions=len(self.days),
            version_bounds=self.refs["version_bounds"], metadata_source_sha=self.refs["metadata_source_sha"],
            apis={api: dict(partitions=len(parts), rows=sum(p["row_count"] for p in parts.values()),
                missing_session_partitions=len(set(self.days)-parts.keys()),
                statuses=dict(Counter(p["status"] for p in parts.values())),
                reasons=dict(Counter(p["reason"] for p in parts.values()))) for api,parts in self.partitions.items()},
            bse_calendar="NOT_VERIFIED", historical_identity="NOT_VERIFIED", tradability="UNKNOWN",
            units=dict(daily=v1.CONTRACT, sidecar=sidecar.CONTRACT),
            resource_limits=dict(rows_per_partition=self.row_cap, sqlite_cache_mib_per_store=8, sqlite_threads=1))

    def _rows(self, api, date, symbols):
        p = self.partitions[api].get(date)
        if p is None:
            return []
        args = [p["id"]]
        if api == "daily":
            sql = DAILY_SQL
            if symbols:
                sql = sql.replace(" ORDER BY", " AND r.ts_code IN (" + ",".join("?" for _ in symbols) + ") ORDER BY")
        else:
            sql = SIDECAR_SQL
            if symbols:
                sql = sql.replace(" ORDER BY", " AND ts_code IN (" + ",".join("?" for _ in symbols) + ") ORDER BY")
        args.extend(symbols)
        cursor = self.dbs[0 if api == "daily" else 1].execute(sql, args)
        result = []
        while batch := cursor.fetchmany(1024):
            for row in batch:
                r = json.loads(row["row_json"])
                require(r["trade_date"] == date, "ROW_DATE_BINDING")
                r["_row_sha"] = row["row_sha"]
                result.append(r)
            require(len(result) <= self.row_cap, "PARTITION_RESOURCE_LIMIT")
        return result

    def read_day(self, date, symbols=()):
        require(self.start <= date <= self.end, "DATE_OUTSIDE_FROZEN_RANGE")
        require(len(symbols) <= 200, "SYMBOL_BATCH_LIMIT_200")
        data = {api: self._rows(api,date,symbols) for api in APIS}
        maps = {api: {r["ts_code"]: r for r in data[api]} for api in APIS if api != "suspend_d"}
        events = {}
        for r in data["suspend_d"]:
            events.setdefault(r["ts_code"],[]).append(r)
        joined = []
        for r in data["daily"]:
            code = r["ts_code"]
            exchange = {"SH":"SSE","SZ":"SZSE","BJ":"BSE"}.get(code[-2:], "UNKNOWN")
            factor_row, basic, limit = (maps[api].get(code) for api in ("adj_factor","daily_basic","stk_limit"))
            factor = factor_row.get("adj_factor") if factor_row else None
            flags = ["HISTORICAL_IDENTITY_NOT_VERIFIED", "TRADABILITY_NOT_CERTIFIED"]
            if exchange == "BSE":
                flags.append("BSE_CALENDAR_NOT_VERIFIED")
            elif self.calendar.get((exchange,date)) != "1":
                flags.append("CALENDAR_NOT_CONFIRMED")
            if not (code.startswith(("600","601","603","605","688")) and code.endswith(".SH") or
                    code.startswith(("000","001","002","003","300","301")) and code.endswith(".SZ")):
                flags.append("NON_A_OR_IDENTITY_UNVERIFIED")
            if factor is None:
                flags.append("FACTOR_NULL")
            if basic is None:
                flags.append("DAILY_BASIC_NULL")
            if limit is None:
                flags.append("LIMIT_NULL")
            elif limit.get("exchange") and limit["exchange"] != exchange:
                flags.append("SOURCE_EXCHANGE_CONFLICT")
            if basic and basic.get("close") is not None and Decimal(basic["close"]) != Decimal(r["close"]):
                flags.append("BASIC_CLOSE_CONFLICT")
                basic = None
            joined.append(dict(ts_code=code, trade_date=date, exchange=exchange, daily=r,
                factor=factor, factor_source=factor_row, daily_basic=basic, limit=limit,
                suspension_events=events.get(code,[]) if date in self.partitions["suspend_d"] else None,
                tradability="UNKNOWN", quality=flags,
                versions={api: self.partitions[api][date]["id"] if date in self.partitions[api] else None for api in APIS}))
        codes = set(maps["daily"])
        return dict(trade_date=date, rows=joined, partitions={api: self.partitions[api].get(date) for api in APIS},
            sidecar_rows={api:len(data[api]) for api in APIS if api != "daily"},
            sidecar_without_daily={api:sum(r["ts_code"] not in codes for r in data[api]) for api in APIS if api != "daily"})
