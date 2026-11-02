"""Issue #59: four-API, local-only ex-post sidecar. Never writes a V1 store.

Reuse PR58's HTTPS, secret handling, lexical no-link checks, locks and raw IO.
Only the transport is replaced by recorded HTTP in tests.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
from decimal import Decimal, InvalidOperation, localcontext
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
import urllib.error
import http.client as http_client

_spec = importlib.util.spec_from_file_location("warehouse_v1", Path(__file__).with_name("historical_warehouse.py"))
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)
require, Error = v1.require, v1.WarehouseError
now, sha, canonical = v1.now, v1.sha, v1.canonical
ROOT, START, END, SAFE = v1.ROOT, v1.START, v1.END, v1.SAFE
VERSION, SCHEMA = "tushare-historical-sidecar-v2", 2013
FIELDS = {
    "adj_factor": "ts_code,trade_date,adj_factor",
    "suspend_d": "ts_code,trade_date,suspend_type,suspend_timing",
    "stk_limit": "ts_code,trade_date,pre_close,up_limit,down_limit,asset_type,exchange",
    "daily_basic": "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv,limit_status",
}
CAPS = {"adj_factor": None, "suspend_d": 5000, "stk_limit": 5800, "daily_basic": 6000}
# An undocumented cap cannot establish COMPLETE. This sentinel also catches the
# common 6000-row response, and rounded plateaus are treated as suspect below.
ADJ_SENTINEL = 6000
PERMISSION = "Owner Issue #59 / existing 2000-point account / four APIs only"
CONTRACT = dict(version=VERSION, schema=SCHEMA, fields=FIELDS, caps=CAPS, **SAFE,
    coverage="PARTIAL", provider="Tushare", account_points=2000,
    units=dict(turnover_rate="percent", turnover_rate_f="percent", dv_ratio="percent", dv_ttm="percent",
               total_share="10000_shares", float_share="10000_shares", free_share="10000_shares",
               total_mv="10000_CNY", circ_mv="10000_CNY", prices="CNY", adj_factor="source_factor"),
    availability="actual_download_time_only; historical publication/revisions unknown",
    suspension="S=suspended,R=resumed; empty response does not establish tradability",
    limit_prices="reference_only_not_execution_or_tradability", adjustment="explicit_frozen_anchor_ex_post",
    license="existing authorized account; local personal research; no redistribution grant")
OK = ("OK", "EMPTY", "TRUNCATION_SUSPECTED")
HALTS = ("NETWORK_OUTCOME_UNKNOWN", "RATE_LIMITED", "PARTIAL_QUOTA_LIMIT", "PERMISSION_DENIED", "AUTH_DENIED")


class _LongerRead:
    """Keep PR58's fixed HTTPS request/redirect/secret checks, allow slow reads."""
    def __init__(self, delegate):
        self.delegate = delegate

    def open(self, request, timeout=None):
        return self.delegate.open(request, timeout=120)


class TushareHTTP(v1.TushareHTTP):
    def __init__(self, token):
        super().__init__(token)
        self.opener = _LongerRead(self.opener)

DDL = """
CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1), contract TEXT NOT NULL, sha TEXT NOT NULL);
CREATE TABLE metadata(api TEXT NOT NULL, object_key TEXT NOT NULL, row_json TEXT NOT NULL,
 PRIMARY KEY(api,object_key));
CREATE TABLE metadata_source(id INTEGER PRIMARY KEY CHECK(id=1), manifest TEXT NOT NULL, sha TEXT NOT NULL);
CREATE TABLE budget(id INTEGER PRIMARY KEY CHECK(id=1), total_cap INTEGER NOT NULL, plan TEXT NOT NULL, sha TEXT NOT NULL);
CREATE TABLE runs(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,started TEXT NOT NULL,ended TEXT,status TEXT NOT NULL,
 config TEXT NOT NULL,config_sha TEXT NOT NULL);
CREATE TABLE attempts(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES runs(id),
 api TEXT NOT NULL,params TEXT NOT NULL,fields TEXT NOT NULL,credential_source TEXT NOT NULL,
 permission_source TEXT NOT NULL,started TEXT NOT NULL,ended TEXT,status TEXT NOT NULL,
 may_have_sent INTEGER NOT NULL,http_status INTEGER,provider_code INTEGER,row_count INTEGER,
 response_sha TEXT,raw_bytes INTEGER,canonical_sha TEXT,duplicates INTEGER,retry_after TEXT,metadata_sha TEXT);
CREATE INDEX attempts_scope ON attempts(api,params,id);
CREATE TABLE permissions(api TEXT PRIMARY KEY,status TEXT NOT NULL,attempt_id INTEGER NOT NULL REFERENCES attempts(id));
CREATE TABLE versions(id INTEGER PRIMARY KEY,api TEXT NOT NULL,trade_date TEXT NOT NULL,created TEXT NOT NULL,
 status TEXT NOT NULL,reason TEXT NOT NULL,row_count INTEGER NOT NULL,a_share_count INTEGER NOT NULL,
 content_sha TEXT NOT NULL,manifest TEXT NOT NULL,source_sha TEXT NOT NULL);
CREATE INDEX versions_date ON versions(api,trade_date,id DESC);
CREATE TABLE rows(version_id INTEGER NOT NULL REFERENCES versions(id),row_key TEXT NOT NULL,ts_code TEXT NOT NULL,
 trade_date TEXT NOT NULL,row_sha TEXT NOT NULL,row_json TEXT NOT NULL,PRIMARY KEY(version_id,row_key));
CREATE INDEX rows_symbol ON rows(ts_code,trade_date,version_id);
CREATE TABLE sources(version_id INTEGER NOT NULL REFERENCES versions(id),attempt_id INTEGER NOT NULL REFERENCES attempts(id),
 PRIMARY KEY(version_id,attempt_id));
CREATE TABLE checkpoints(api TEXT NOT NULL,trade_date TEXT NOT NULL,version_id INTEGER NOT NULL REFERENCES versions(id),
 PRIMARY KEY(api,trade_date));
CREATE INDEX checkpoints_version ON checkpoints(version_id);
CREATE TABLE rejections(id INTEGER PRIMARY KEY,api TEXT NOT NULL,trade_date TEXT NOT NULL,created TEXT NOT NULL,
 reason TEXT NOT NULL,attempts TEXT NOT NULL,prior_version INTEGER NOT NULL REFERENCES versions(id));
"""


def number(value, positive=False, nonnegative=False):
    if value is None:
        return None
    require(not isinstance(value, (bool, float)), "FLOAT_OR_BOOL_REJECTED")
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        raise Error("INVALID_NUMBER") from None
    require(n.is_finite() and (not positive or n > 0) and (not nonnegative or n >= 0), "INVALID_NUMBER")
    return str(n)


def security_kind(code):
    require(isinstance(code, str) and re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", code), "INVALID_SECURITY_CODE")
    if re.fullmatch(r"(900\d{3}\.SH|200\d{3}\.SZ)", code):
        return "B_SHARE_CODE_FAMILY"
    try:
        v1.exchange(code)
        return "A_SHARE_CODE_FAMILY"
    except Error:
        return "NON_A_OR_IDENTITY_UNVERIFIED"


def key(row, api):
    # Keep distinct S/R and intraday intervals rather than collapsing by stock.
    return canonical([row["ts_code"], row.get("suspend_type"), row.get("suspend_timing")]
                     if api == "suspend_d" else [row["ts_code"]]).decode()


def validate(api, params, fields, source_rows):
    require(api in FIELDS, "UNAUTHORIZED_API")
    required = {"ts_code", "trade_date"} | {
        "adj_factor": {"adj_factor"}, "suspend_d": {"suspend_type", "suspend_timing"},
        "stk_limit": {"up_limit", "down_limit"}, "daily_basic": {"close", "turnover_rate", "total_mv"},
    }[api]
    require(required <= set(fields), "MISSING_REQUIRED_FIELDS")
    unique, duplicates = {}, 0
    for original in source_rows:
        r = dict(original)
        r["security_kind"] = security_kind(r["ts_code"])
        v1.day(r["trade_date"])
        require(r["trade_date"] == params["trade_date"], "DATE_SCOPE_MISMATCH")
        if params.get("ts_code"):
            require(r["ts_code"] in params["ts_code"].split(","), "PARTITION_SCOPE_MISMATCH")
        if api == "suspend_d":
            require(r["suspend_type"] in ("S", "R") and
                    (not params.get("suspend_type") or r["suspend_type"] == params["suspend_type"]), "SUSPEND_TYPE_MISMATCH")
            require(r["suspend_timing"] is None or isinstance(r["suspend_timing"], str), "INVALID_SUSPEND_TIMING")
        else:
            for f in fields:
                if f not in ("ts_code", "trade_date", "asset_type", "exchange", "limit_status"):
                    r[f] = number(r[f], positive=(api == "adj_factor"),
                                  nonnegative=(api == "stk_limit"))
            if api == "adj_factor":
                require(r["adj_factor"] is not None, "MISSING_ADJ_FACTOR")
            if api == "stk_limit":
                require(r["up_limit"] is not None and r["down_limit"] is not None, "MISSING_LIMIT_PRICE")
                require(Decimal(r["up_limit"]) >= Decimal(r["down_limit"]), "REVERSED_LIMIT_PRICE")
                if r.get("exchange"):
                    if r["exchange"] != {"SH":"SSE", "SZ":"SZSE", "BJ":"BSE"}[r["ts_code"][-2:]]:
                        r["quality_flags"] = ["PROVIDER_EXCHANGE_CODE_CONFLICT"]
        k = key(r, api)
        if k in unique:
            require(unique[k] == r, "CONFLICTING_DUPLICATE_ROW")
            duplicates += 1
        unique[k] = r
    return sorted(unique.values(), key=lambda r: key(r, api)), duplicates


def parse(raw):
    # Classify quota exhaustion separately, preserving raw/provider code privately.
    body = json.loads(raw, parse_float=Decimal,
                      parse_constant=lambda _: (_ for _ in ()).throw(Error("NONFINITE_NUMBER")))
    if isinstance(body, dict) and body.get("code") != 0:
        msg = str(body.get("msg", "")).lower()
        if any(s in msg for s in ("每天", "每日", "日总", "总量", "daily quota", "quota", "额度")):
            return "PARTIAL_QUOTA_LIMIT", body.get("code"), [], []
    return v1.parse_response(raw)


def check_contract(db):
    require(db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA, "SCHEMA_MISMATCH")
    row = db.execute("SELECT * FROM meta WHERE id=1").fetchone()
    require(row and row["contract"].encode() == canonical(CONTRACT) and
            row["sha"] == sha(canonical(CONTRACT)), "SOURCE_METADATA_TAMPERED")


class Sidecar(v1.Warehouse):
    @contextlib.contextmanager
    def write(self):
        self.check_paths(descendants=True)
        with v1.writer_lock(self.root):
            db = v1.connection(self.path)
            owned = False
            try:
                new = db.execute("PRAGMA user_version").fetchone()[0] == 0
                if new:
                    require(not db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), "FOREIGN_DATABASE")
                else:
                    check_contract(db)
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA foreign_keys=ON")
                owned = True
                if new:
                    with db:
                        db.executescript("BEGIN IMMEDIATE;" + DDL)
                        db.execute("INSERT INTO meta VALUES(1,?,?)", (canonical(CONTRACT).decode(), sha(canonical(CONTRACT))))
                        db.execute(f"PRAGMA user_version={SCHEMA}")
                with db:
                    db.execute("UPDATE runs SET status='INTERRUPTED',ended=? WHERE status='RUNNING'", (now(),))
                    for row in db.execute("SELECT * FROM attempts WHERE status='SENDING'").fetchall():
                        db.execute("UPDATE attempts SET status='NETWORK_OUTCOME_UNKNOWN',ended=? WHERE id=?", (now(),row["id"]))
                        self.seal_attempt(db,row["id"])
                yield db
            finally:
                if owned:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.close()

    @contextlib.contextmanager
    def read(self):
        self.check_paths(descendants=True)
        with v1.writer_lock(self.root, readonly=True):
            db = v1.connection(self.path, True)
            try:
                check_contract(db)
                yield db
            finally:
                db.close()

    def import_v1(self, db, root):
        require(not db.execute("SELECT 1 FROM metadata_source").fetchone(), "METADATA_ALREADY_FROZEN")
        source = v1.Warehouse(root)
        require(source.root != self.root, "V1_V2_STORE_COLLISION")
        with source.read() as old:
            objects = {api: source.latest_objects(old, api) for api in ("stock_basic", "trade_cal")}
            receipts = [dict(r) for r in old.execute("SELECT id,api,params,fields,ended,response_sha,metadata_sha FROM attempts WHERE api IN ('stock_basic','trade_cal') AND status IN ('OK','EMPTY') ORDER BY id")]
            manifest = dict(source_contract_sha=sha(canonical(v1.CONTRACT)), source_receipts=receipts,
                            objects_sha=sha(canonical(objects)), frozen_at_utc=now(),
                            catalog="current_snapshot_not_exhaustive_historical_identity", bse_calendar="NOT_VERIFIED")
        self.install_metadata(db, objects, manifest)

    def install_metadata(self, db, objects, manifest):
        objects = {api:sorted(rows,key=lambda r:r["ts_code"] if api=="stock_basic" else r["exchange"]+":"+r["cal_date"])
                   for api,rows in objects.items()}
        manifest = dict(manifest, objects_sha=sha(canonical(objects)))
        with db:
            for api, rows in objects.items():
                for row in rows:
                    k = row["ts_code"] if api == "stock_basic" else row["exchange"]+":"+row["cal_date"]
                    db.execute("INSERT INTO metadata VALUES(?,?,?)",(api,k,canonical(row).decode()))
            db.execute("INSERT INTO metadata_source VALUES(1,?,?)",(canonical(manifest).decode(),sha(canonical(manifest))))

    def objects(self, db, api):
        return [json.loads(r[0]) for r in db.execute("SELECT row_json FROM metadata WHERE api=? ORDER BY object_key",(api,))]

    def open_days(self, db, start=START, end=END):
        calendars = self.objects(db,"trade_cal")
        for e in ("SSE","SZSE"):
            require({r["cal_date"] for r in calendars if r["exchange"] == e} >= set(v1.dates(start,end)), "OFFICIAL_CALENDAR_GAP")
        return sorted({r["cal_date"] for r in calendars if r["is_open"] == "1" and start <= r["cal_date"] <= end})

    def publish(self, db, api, date, rows, attempt_ids, status, reason, fault=None):
        rows = sorted(rows,key=lambda r:key(r,api))
        current = db.execute("SELECT v.* FROM checkpoints c JOIN versions v ON v.id=c.version_id WHERE c.api=? AND c.trade_date=?",(api,date)).fetchone()
        hashed = [(key(r,api),sha(canonical(r))) for r in rows]
        content_sha = sha(canonical(hashed))
        if current:
            old_rows = {r[0]:json.loads(r[1]) for r in db.execute("SELECT row_key,row_json FROM rows WHERE version_id=?",(current["id"],))}
            old_keys = set(old_rows)
            new_rows = {key(r,api):r for r in rows}
            missing_fields = any(set(old_rows[k])-{"quality_flags"}-set(new_rows[k]) for k in old_keys & new_rows.keys())
            # Also protect an admitted PARTIAL known-universe response from losing
            # securities/events on refresh. Empty events cannot erase old facts.
            if (current["status"] == "COMPLETE" and status != "COMPLETE") or not old_keys <= set(new_rows) or missing_fields:
                reason = "MISSING_PRIOR_SOURCE_FIELDS" if missing_fields else ("QUALITY_DOWNGRADE" if old_keys <= set(new_rows) else "MISSING_PRIOR_ROWS")
                with db:
                    db.execute("INSERT INTO rejections(api,trade_date,created,reason,attempts,prior_version) VALUES(?,?,?,?,?,?)",
                               (api,date,now(),reason,canonical(attempt_ids).decode(),current["id"]))
                return "PARTIAL_REFRESH_REJECTED"
        sources = [dict(db.execute("SELECT * FROM attempts WHERE id=?",(a,)).fetchone()) for a in attempt_ids]
        manifest = dict(api=api,fields=FIELDS[api],contract_sha=sha(canonical(CONTRACT)),
                        metadata_source_sha=db.execute("SELECT sha FROM metadata_source").fetchone()[0],
                        revision_of_version=current["id"] if current else None,
                        missing_optional_fields=sorted(set(FIELDS[api].split(","))-set(rows[0]) if rows else []),
                        attempts=[dict(id=a["id"],metadata_sha=a["metadata_sha"],response_sha=a["response_sha"],obtained_at=a["ended"]) for a in sources])
        with db:
            if current and current["content_sha"] == content_sha and current["status"] == status:
                version = current["id"]
            else:
                version = db.execute("INSERT INTO versions(api,trade_date,created,status,reason,row_count,a_share_count,content_sha,manifest,source_sha) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (api,date,now(),status,reason,len(rows),sum(r["security_kind"]=="A_SHARE_CODE_FAMILY" for r in rows),
                     content_sha,canonical(manifest).decode(),sha(canonical(manifest)))).lastrowid
                for i,r in enumerate(rows):
                    db.execute("INSERT INTO rows VALUES(?,?,?,?,?,?)",(version,key(r,api),r["ts_code"],date,sha(canonical(r)),canonical(r).decode()))
                    if fault:
                        fault(i)
            for a in attempt_ids:
                db.execute("INSERT OR IGNORE INTO sources VALUES(?,?)",(version,a))
            # All rows, version, source links and checkpoint commit together.
            db.execute("INSERT INTO checkpoints VALUES(?,?,?) ON CONFLICT(api,trade_date) DO UPDATE SET version_id=excluded.version_id",(api,date,version))
        return status

    def report(self, start=START, end=END):
        v1.historical_range(start,end)
        self.check_paths(descendants=True)
        result = dict(version=VERSION,range=[start,end],network_operation=False,coverage="PARTIAL",**SAFE)
        if not self.path.exists():
            return dict(result,state="NOT_INITIALIZED",requests=0)
        with self.read() as db:
            days = self.open_days(db,start,end)
            result.update(open_days=len(days),requests=db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],
                first_obtained_at=db.execute("SELECT MIN(ended) FROM attempts WHERE response_sha IS NOT NULL").fetchone()[0],
                last_obtained_at=db.execute("SELECT MAX(ended) FROM attempts WHERE response_sha IS NOT NULL").fetchone()[0],
                metadata_source_sha=db.execute("SELECT sha FROM metadata_source").fetchone()[0],
                official_remaining_quota="UNKNOWN_NO_AUTHORIZED_BALANCE_ENDPOINT",bse_calendar="NOT_VERIFIED",
                rejected_refreshes=db.execute("SELECT COUNT(*) FROM rejections").fetchone()[0])
            budget = db.execute("SELECT * FROM budget").fetchone()
            result["budget"] = json.loads(budget["plan"]) if budget else None
            result["total_call_cap"] = budget["total_cap"] if budget else None
            result["apis"] = {}
            for api in FIELDS:
                versions = db.execute("SELECT v.* FROM checkpoints c JOIN versions v ON v.id=c.version_id WHERE c.api=? AND c.trade_date BETWEEN ? AND ? ORDER BY c.trade_date",(api,start,end)).fetchall()
                current_dates = {r["trade_date"] for r in versions}
                attempts = db.execute("SELECT * FROM attempts WHERE api=? ORDER BY id",(api,)).fetchall()
                errors = {}
                for a in attempts:
                    if a["status"] not in OK:
                        errors[a["status"]] = errors.get(a["status"],0)+1
                result["apis"][api] = dict(
                    complete_dates=sum(v["status"]=="COMPLETE" for v in versions),
                    partial_dates=sum(v["status"]=="PARTIAL" for v in versions),
                    blocked_or_unpublished_dates=len(set(days)-current_dates),
                    unpublished_dates=sorted(set(days)-current_dates),
                    partial_date_reasons={r["trade_date"]:r["reason"] for r in versions if r["status"]!="COMPLETE"},
                    rows=sum(r["row_count"] for r in versions),a_share_rows=sum(r["a_share_count"] for r in versions),
                    securities=db.execute("SELECT COUNT(DISTINCT r.ts_code) FROM rows r JOIN checkpoints c ON c.version_id=r.version_id WHERE c.api=? AND c.trade_date BETWEEN ? AND ?",(api,start,end)).fetchone()[0],
                    requests=len(attempts),attempt_states=errors,permission=self.permission(db,api),
                    source_receipts_sha=sha(canonical([dict(a) for a in attempts])),
                    documented_row_cap=CAPS[api])
            result["runs"] = [dict(r) for r in db.execute("SELECT id,kind,started,ended,status FROM runs ORDER BY id")]
        result["disk_bytes"] = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        result["free_disk_bytes"] = shutil.disk_usage(self.root).free
        result["state"] = "RANGE_COLLECTED_COVERAGE_PARTIAL" if all(a["blocked_or_unpublished_dates"]==0 for a in result["apis"].values()) else "CONTINUE_FROM_CHECKPOINT"
        return result

    def query(self, api, start, end, symbols=(), date=None, as_of=None, limit=100, offset=0):
        require(api in FIELDS and 1 <= limit <= 10000 and offset >= 0, "INVALID_QUERY")
        v1.historical_range(start,end)
        if date:
            v1.historical_range(date,date)
            start = end = date
        for code in symbols:
            security_kind(code)
        with self.read() as db:
            conditions, args = ["v.api=?", "v.trade_date BETWEEN ? AND ?"], [api,start,end]
            if as_of is None:
                join = "JOIN checkpoints c ON c.version_id=v.id AND c.api=v.api AND c.trade_date=v.trade_date"
            else:
                require(as_of>0,"INVALID_VERSION")
                join = "JOIN (SELECT trade_date,MAX(id) id FROM versions WHERE api=? AND id<=? GROUP BY trade_date) c ON c.id=v.id"
                args = [api,as_of]+args
            partitions = [dict(trade_date=r["trade_date"],version_id=r["id"],quality=r["status"],reason=r["reason"],
                               row_count=r["row_count"],source_sha=r["source_sha"],sources=json.loads(r["manifest"])["attempts"])
                          for r in db.execute("SELECT v.* FROM versions v "+join+" WHERE "+" AND ".join(conditions)+" ORDER BY v.trade_date",args)]
            missing_dates = sorted(set(self.open_days(db,start,end))-{r["trade_date"] for r in partitions})
            if symbols:
                conditions.append("r.ts_code IN ("+",".join("?" for _ in symbols)+")")
                args += list(symbols)
            sql = "SELECT r.row_json,r.row_sha,v.id,v.status,v.reason,v.source_sha,v.manifest FROM rows r JOIN versions v ON v.id=r.version_id "+join+" WHERE "+" AND ".join(conditions)+" ORDER BY r.trade_date,r.ts_code,r.row_key LIMIT ? OFFSET ?"
            found = db.execute(sql,args+[limit+1,offset]).fetchall()
            data = [dict(data=json.loads(r[0]),row_sha=r[1],version_id=r[2],quality=r[3],reason=r[4],source_sha=r[5],
                         sources=json.loads(r[6])["attempts"]) for r in found[:limit]]
            return dict(api=api,rows=data,has_more=len(found)>limit,offset=offset,next_offset=offset+len(data),
                        partitions=partitions,missing_dates=missing_dates,
                        empty_event_interpretation="NO_REPORTED_EVENTS_NOT_TRADABILITY" if api=="suspend_d" else None,
                        query_sha=sha(canonical(dict(rows=data,partitions=partitions,missing_dates=missing_dates))),coverage="PARTIAL",**SAFE)

    def verify(self):
        attempts_count = version_count = rows_count = 0
        with self.read() as db:
            require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok", "SQLITE_INTEGRITY")
            require(not db.execute("PRAGMA foreign_key_check").fetchall(), "SQLITE_FOREIGN_KEYS")
            require(not db.execute("SELECT 1 FROM checkpoints c JOIN versions v ON v.id=c.version_id WHERE c.api!=v.api OR c.trade_date!=v.trade_date LIMIT 1").fetchone(),"CHECKPOINT_SCOPE")
            metadata = db.execute("SELECT * FROM metadata_source").fetchone()
            require(metadata and sha(metadata["manifest"].encode())==metadata["sha"], "METADATA_SOURCE_HASH")
            objects = {api:self.objects(db,api) for api in ("stock_basic","trade_cal")}
            require(sha(canonical(objects)) == json.loads(metadata["manifest"])["objects_sha"], "METADATA_OBJECTS_HASH")
            budget = db.execute("SELECT * FROM budget").fetchone()
            if budget:
                require(sha(budget["plan"].encode())==budget["sha"] and json.loads(budget["plan"])["total_cap"]==budget["total_cap"], "BUDGET_HASH")
            for run in db.execute("SELECT * FROM runs"):
                require(sha(run["config"].encode())==run["config_sha"], "RUN_HASH")
            for a in db.execute("SELECT * FROM attempts ORDER BY id"):
                attempts_count += 1
                require(v1.attempt_hash(a)==a["metadata_sha"], "ATTEMPT_HASH")
                require(a["api"] in FIELDS and a["fields"]==FIELDS[a["api"]] and a["permission_source"]==PERMISSION,"ATTEMPT_AUTHORIZED_SCOPE")
                if a["response_sha"]:
                    raw = gzip.decompress(self.raw_path(a["id"]).read_bytes())
                    require(len(raw)==a["raw_bytes"] and sha(raw)==a["response_sha"], "RAW_HASH")
                    if a["canonical_sha"]:
                        state,_,fields,rows = parse(raw)
                        require(state=="OK", "CANONICAL_SOURCE_STATE")
                        clean,_ = validate(a["api"],json.loads(a["params"]),fields,rows)
                        require(sha(canonical(clean))==a["canonical_sha"], "CANONICAL_HASH")
            for version in db.execute("SELECT * FROM versions ORDER BY id"):
                version_count += 1
                require(sha(version["manifest"].encode())==version["source_sha"], "MANIFEST_HASH")
                manifest = json.loads(version["manifest"])
                require(manifest["contract_sha"]==sha(canonical(CONTRACT)) and manifest["metadata_source_sha"]==metadata["sha"] and manifest["api"]==version["api"] and manifest["fields"]==FIELDS[version["api"]],"MANIFEST_CONTRACT")
                merged = {}
                for source in manifest["attempts"]:
                    a = db.execute("SELECT * FROM attempts WHERE id=?",(source["id"],)).fetchone()
                    require(a and a["metadata_sha"]==source["metadata_sha"] and a["response_sha"]==source["response_sha"] and a["ended"]==source["obtained_at"], "SOURCE_BINDING")
                    require(a["api"]==version["api"] and json.loads(a["params"])["trade_date"]==version["trade_date"], "SOURCE_SCOPE")
                    state,_,fields,source_rows = parse(gzip.decompress(self.raw_path(a["id"]).read_bytes()))
                    clean,_ = validate(a["api"],json.loads(a["params"]),fields,source_rows)
                    for r in clean:
                        k = key(r,a["api"])
                        require(k not in merged or merged[k]==r, "SOURCE_CONFLICT")
                        merged[k] = r
                hashed = []
                for row in db.execute("SELECT * FROM rows WHERE version_id=? ORDER BY row_key",(version["id"],)):
                    rows_count += 1
                    require(sha(row["row_json"].encode())==row["row_sha"], "ROW_HASH")
                    r = json.loads(row["row_json"])
                    require(key(r,version["api"])==row["row_key"] and r["ts_code"]==row["ts_code"] and r["trade_date"]==row["trade_date"]==version["trade_date"], "ROW_SCOPE")
                    require(merged.pop(row["row_key"],None)==r, "PUBLISHED_SOURCE_MISMATCH")
                    hashed.append((row["row_key"],row["row_sha"]))
                require(not merged and len(hashed)==version["row_count"] and sha(canonical(hashed))==version["content_sha"], "VERSION_CONTENT_HASH")
        return dict(state="VERIFIED_STORAGE_SOURCE_BINDING",attempts=attempts_count,versions=version_count,rows=rows_count,**SAFE)


class Download:
    def __init__(self, w, db, kind, transport, credential_source, start=START, end=END,
                 rpm=60, max_calls=None, total_cap=None, sleep=time.sleep, progress=None):
        v1.historical_range(start,end)
        require(0 < rpm <= 120,"RATE_CAP_120_BELOW_2000_TIER_200")
        self.w,self.db,self.transport,self.credential_source = w,db,transport,credential_source
        self.start,self.end,self.kind = start,end,kind
        self.days = w.open_days(db,start,end)
        require(bool(self.days), "NO_OPEN_DAYS")
        previous = db.execute("SELECT * FROM budget").fetchone()
        if previous:
            require(total_cap is None or total_cap==previous["total_cap"],"PERSISTED_CAP_CANNOT_EXPAND_ON_RESUME")
            self.total_cap = previous["total_cap"]
        else:
            # 5 calls/day includes separate S/R. Reserve bounded code partitions
            # for one capped API; all expansion still checks remaining hard cap.
            batches = math.ceil(len(w.objects(db,"stock_basic"))/200)
            base = len(self.days)*5+8
            reserve = max(100, math.ceil(base*.15), batches*10)
            self.total_cap = total_cap if total_cap is not None else base+reserve
            require(8 <= self.total_cap <= 50000, "INVALID_TOTAL_CAP")
            plan = dict(total_cap=self.total_cap,open_days=len(self.days),base_calls=base,
                        reserve_calls=self.total_cap-base,worker_count=1,account_points=2000,
                        official_rpm=200,official_daily_calls_per_api=100000,remaining_provider_quota="UNKNOWN",
                        origin="Owner Issue #59; official table doc_id=290; actual errors authoritative")
            with db:
                db.execute("INSERT INTO budget VALUES(1,?,?,?)",(self.total_cap,canonical(plan).decode(),sha(canonical(plan))))
        used = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        self.max_calls = max_calls if max_calls is not None else self.total_cap-used
        require(self.max_calls > 0, "CALL_CAP_REACHED")
        self.rpm,self.sleep,self.progress,self.calls = rpm,sleep,progress,0
        self.retry_failed = False
        config = dict(start=start,end=end,rpm=rpm,total_cap=self.total_cap,max_calls=self.max_calls,
                      credential_source=credential_source,permission_source=PERMISSION,version=VERSION)
        with db:
            self.run = db.execute("INSERT INTO runs(kind,started,status,config,config_sha) VALUES(?,?,'RUNNING',?,?)",
                                 (kind,now(),canonical(config).decode(),sha(canonical(config)))).lastrowid

    def request(self, api, params):
        require(api in FIELDS, "UNAUTHORIZED_API")
        require(self.w.permission(self.db,api) not in ("PERMISSION_DENIED","AUTH_DENIED"), "PERSISTED_PERMISSION_DENIED")
        require(self.calls < self.max_calls and self.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]<self.total_cap,"CALL_CAP_REACHED")
        require(shutil.disk_usage(self.w.root).free >= 1024**3, "INSUFFICIENT_DISK")
        prior = self.db.execute("SELECT * FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
        if prior:
            instant = dt.datetime.now(dt.timezone.utc)
            wait = max(0,60/self.rpm-(instant-dt.datetime.fromisoformat(prior["started"])).total_seconds())
            if prior["status"] in ("RATE_LIMITED","PARTIAL_QUOTA_LIMIT"):
                seconds = int(prior["retry_after"]) if prior["retry_after"] else (86400 if prior["status"]=="PARTIAL_QUOTA_LIMIT" else 60)
                wait = max(wait,seconds-(instant-dt.datetime.fromisoformat(prior["ended"])).total_seconds())
                require(wait<=60,"QUOTA_COOLDOWN_ACTIVE" if prior["status"]=="PARTIAL_QUOTA_LIMIT" else "RATE_COOLDOWN_ACTIVE")
            self.sleep(max(0,wait))
        with self.db:
            attempt = self.db.execute("INSERT INTO attempts(run_id,api,params,fields,credential_source,permission_source,started,status,may_have_sent) VALUES(?,?,?,?,?,?,?,'SENDING',1)",
                (self.run,api,canonical(params).decode(),FIELDS[api],self.credential_source,PERMISSION,now())).lastrowid
        self.calls += 1
        status,http,code,raw,source_rows,clean,duplicates,retry,cs = "NETWORK_OUTCOME_UNKNOWN",None,None,None,[],[],0,"",None
        try:
            http,raw,retry = self.transport(api,params,FIELDS[api])
            self.w.save_raw(attempt,raw)
            if http == 429:
                status = "RATE_LIMITED"
            elif http in (401,403):
                status = "AUTH_DENIED" if http==401 else "PERMISSION_DENIED"
            elif http != 200:
                status = "HTTP_ERROR"
            else:
                status,code,fields,source_rows = parse(raw)
                if status == "OK":
                    clean,duplicates = validate(api,params,fields,source_rows)
                    cap = CAPS[api] or ADJ_SENTINEL
                    suspected = len(source_rows)>=cap or (api=="adj_factor" and len(source_rows)>=1000 and len(source_rows)%1000==0)
                    status = "TRUNCATION_SUSPECTED" if suspected else ("OK" if source_rows else "EMPTY")
                    cs = sha(canonical(clean))
        except Error as e:
            status = str(e)
        except (OSError,TimeoutError,urllib.error.URLError,http_client.HTTPException):
            status = "NETWORK_OUTCOME_UNKNOWN"
        except (ValueError,TypeError,KeyError):
            status = "INVALID_RESPONSE_FORMAT"
        with self.db:
            self.db.execute("UPDATE attempts SET ended=?,status=?,http_status=?,provider_code=?,row_count=?,response_sha=?,raw_bytes=?,canonical_sha=?,duplicates=?,retry_after=? WHERE id=?",
                (now(),status,http,code,len(source_rows) if raw is not None else None,
                 sha(raw) if raw is not None else None,len(raw) if raw is not None else None,cs,duplicates,
                 str(retry)[:32] if str(retry).isdigit() else "",attempt))
            self.w.seal_attempt(self.db,attempt)
            if status in OK+("PERMISSION_DENIED","AUTH_DENIED"):
                permission = "ALLOWED_OBSERVED" if status in OK else status
                self.db.execute("INSERT INTO permissions VALUES(?,?,?) ON CONFLICT(api) DO UPDATE SET status=excluded.status,attempt_id=excluded.attempt_id",(api,permission,attempt))
        return dict(id=attempt,status=status,rows=clean)

    def successful_request(self, api, params):
        # Reuse a fully received exact request after a crash/partial S/R day.
        a = self.db.execute("SELECT * FROM attempts WHERE api=? AND params=? ORDER BY id DESC LIMIT 1",(api,canonical(params).decode())).fetchone()
        if a and a["status"] in OK:
            raw = gzip.decompress(self.w.raw_path(a["id"]).read_bytes())
            require(sha(raw)==a["response_sha"],"RAW_HASH")
            _,_,fields,rows = parse(raw)
            clean,_ = validate(api,params,fields,rows)
            return dict(id=a["id"],status=a["status"],rows=clean)
        require(not a or a["status"]!="NETWORK_OUTCOME_UNKNOWN" or self.retry_failed,
                "NETWORK_OUTCOME_UNKNOWN_REQUIRES_EXPLICIT_RETRY")
        return self.request(api,params)

    def collect(self, api, date, refresh=False, fault=None):
        current = self.db.execute("SELECT v.status FROM checkpoints c JOIN versions v ON v.id=c.version_id WHERE c.api=? AND c.trade_date=?",(api,date)).fetchone()
        if current and not refresh:
            return "SKIPPED_ADMITTED"
        results = []
        # suspend_d default-type behavior is not assumed; explicitly cover S/R.
        for typ in (("S","R") if api=="suspend_d" else (None,)):
            params = dict(trade_date=date)
            if typ:
                params["suspend_type"] = typ
            result = self.request(api,params) if refresh else self.successful_request(api,params)
            require(result["status"] in OK,result["status"])
            results.append(result)
        rows = [r for result in results for r in result["rows"]]
        ids = [r["id"] for r in results]
        state,reason = "COMPLETE","RESPONSE_BELOW_DOCUMENTED_CAP_UNIVERSE_UNVERIFIED"
        if api=="suspend_d":
            reason = "S_AND_R_RESPONSES_NOT_PROOF_OF_TRADABILITY"
        elif not rows:
            state,reason = "PARTIAL","EMPTY_OPEN_DAY_UNVERIFIED"
        elif api=="adj_factor":
            state,reason = "PARTIAL","TRUNCATION_OR_UNIVERSE_UNVERIFIED_UNDOCUMENTED_CAP"
        if any(r.get("quality_flags") for r in rows):
            state,reason = "PARTIAL","SOURCE_EXCHANGE_CODE_CONFLICT"
        if any(r["status"]=="TRUNCATION_SUSPECTED" for r in results):
            state,reason = "PARTIAL","TRUNCATION_OR_UNIVERSE_UNVERIFIED"
            catalog = self.w.objects(self.db,"stock_basic")
            codes = sorted({r["ts_code"] for r in catalog if r.get("list_date") and r["list_date"]<=date and
                            (not r.get("delist_date") or date<=r["delist_date"])}|{r["ts_code"] for r in rows})
            batches = math.ceil(len(codes)/200)*(2 if api=="suspend_d" else 1)
            used = self.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            require(used+batches<=self.total_cap and self.calls+batches<=self.max_calls,"PARTITION_REQUIRES_MORE_RESERVED_CALLS")
            merged = {}
            for typ in (("S","R") if api=="suspend_d" else (None,)):
                for i in range(0,len(codes),200):
                    params = dict(trade_date=date,ts_code=",".join(codes[i:i+200]))
                    if typ:
                        params["suspend_type"] = typ
                    part = self.request(api,params) if refresh else self.successful_request(api,params)
                    require(part["status"] in ("OK","EMPTY"),part["status"])
                    ids.append(part["id"])
                    for r in part["rows"]:
                        k = key(r,api)
                        require(k not in merged or merged[k]==r,"PARTITION_CONFLICT")
                        merged[k] = r
            require(all(merged.get(key(r,api))==r for r in rows),"PARTITION_RESPONSE_CONFLICT")
            rows = sorted(merged.values(),key=lambda r:key(r,api))
            reason = "PARTITIONED_KNOWN_UNIVERSE_UNVERIFIED"
        return self.w.publish(self.db,api,date,rows,ids,state,reason,fault)

    def finish(self, state):
        with self.db:
            self.db.execute("UPDATE runs SET ended=?,status=? WHERE id=?",(now(),state,self.run))
        return dict(run_id=self.run,state=state,requests_this_run=self.calls,network_operation=True,**SAFE)

    def preflight(self):
        probes = []
        for api in FIELDS:
            if self.w.permission(self.db,api) in ("PERMISSION_DENIED","AUTH_DENIED"):
                probes.append(dict(api=api,status="PERSISTED_PERMISSION_DENIED"))
                continue
            # One narrow ended day; second date measures real full-market shape.
            result = self.successful_request(api,dict(trade_date=self.days[0],ts_code="600000.SH"))
            probes.append(dict(api=api,status=result["status"],attempt_id=result["id"]))
            if result["status"] in ("PERMISSION_DENIED","AUTH_DENIED"):
                continue
            require(result["status"] in OK,result["status"])
            self.collect(api,self.days[-1])
        result = self.finish("PREFLIGHT_PASSED" if all(self.w.permission(self.db,a)=="ALLOWED_OBSERVED" for a in FIELDS) else "PARTIAL_PREFLIGHT_PERMISSION")
        result["probes"] = probes
        return result

    def backfill(self, retry_failed=False, refresh=False):
        self.retry_failed = retry_failed
        require(self.db.execute("SELECT 1 FROM runs WHERE kind='preflight' AND status IN ('PREFLIGHT_PASSED','PARTIAL_PREFLIGHT_PERMISSION')").fetchone(),"PREFLIGHT_REQUIRED")
        total = len(self.days)*len(FIELDS)
        done = self.db.execute("SELECT COUNT(*) FROM checkpoints WHERE trade_date BETWEEN ? AND ?",(self.start,self.end)).fetchone()[0]
        next_mark = (done*4//total+1)*25
        blocked = False
        for date in self.days:
            for api in FIELDS:
                if self.w.permission(self.db,api) in ("PERMISSION_DENIED","AUTH_DENIED"):
                    blocked = True
                    continue
                failed = self.db.execute("SELECT status FROM attempts WHERE api=? AND json_extract(params,'$.trade_date')=? ORDER BY id DESC LIMIT 1",(api,date)).fetchone()
                if failed and failed[0] not in OK and not retry_failed:
                    blocked = True
                    continue
                state = self.collect(api,date,refresh)
                if state=="PARTIAL_REFRESH_REJECTED":
                    blocked = True
                if state!="SKIPPED_ADMITTED":
                    done = self.db.execute("SELECT COUNT(*) FROM checkpoints WHERE trade_date BETWEEN ? AND ?",(self.start,self.end)).fetchone()[0]
                    while next_mark<=100 and done*100>=total*next_mark:
                        if self.progress:
                            self.progress(dict(percent=next_mark,admitted_api_dates=done,target_api_dates=total,requests_this_run=self.calls,at_utc=now()))
                        next_mark += 25
        return self.finish("PARTIAL_BLOCKED_CONTINUE_FROM_CHECKPOINT" if blocked else "RANGE_COLLECTED_COVERAGE_PARTIAL")


def adjusted(sidecar, old_root, code, start, end, anchor, factor_version, daily_version, mode="qfq"):
    """Frozen version ceilings include anchor; later downloads cannot alter it."""
    v1.historical_range(start,end)
    v1.historical_range(anchor,anchor)
    require(mode in ("qfq","hfq") and factor_version>0 and daily_version>0,"EXPLICIT_FROZEN_VERSIONS_REQUIRED")
    factors = sidecar.query("adj_factor",min(start,anchor),max(end,anchor),(code,),as_of=factor_version,limit=10000)
    fs = {r["data"]["trade_date"]:r for r in factors["rows"]}
    require(anchor in fs,"FROZEN_ANCHOR_UNAVAILABLE")
    old = v1.Warehouse(old_root).query(start,end,(code,),as_of_version=daily_version,limit=10000)
    rows = []
    with localcontext() as ctx:
        ctx.prec = 50
        base = Decimal(fs[anchor]["data"]["adj_factor"])
        for r in old["rows"]:
            data = r["values"]
            date = data["trade_date"]
            require(date in fs,"FACTOR_GAP")
            factor = Decimal(fs[date]["data"]["adj_factor"])
            multiplier = factor/base if mode=="qfq" else factor
            rows.append(dict(ts_code=code,trade_date=date,prices={f:str(Decimal(data[f])*multiplier) for f in ("open","high","low","close")},
                             factor_row_sha=fs[date]["row_sha"],daily_source=r.get("source_sha"),anchor_date=anchor))
    return dict(mode=mode,rows=rows,factor_version_ceiling=factor_version,daily_version_ceiling=daily_version,
                anchor_factor_source=fs[anchor]["source_sha"],query_sha=sha(canonical(rows)),**SAFE)


def cli(argv=None):
    p = argparse.ArgumentParser(description="历史仓库 V2；四 API 本地 ex-post sidecar。")
    p.add_argument("action",choices=("plan","preflight","backfill","resume","status","report","verify","query","adjusted"))
    p.add_argument("--store",default="main")
    p.add_argument("--v1-root",type=Path,help="已有 V1 仓库，只读；只用于首次冻结目录/日历或显式复权查询")
    p.add_argument("--start",default=START); p.add_argument("--end",default=END)
    p.add_argument("--rpm",type=float,default=60); p.add_argument("--max-calls",type=int)
    p.add_argument("--total-call-cap",type=int)
    p.add_argument("--credential-source",choices=("auto","existing-tushare-mcp-config"),default="auto")
    p.add_argument("--retry-failed",action="store_true"); p.add_argument("--refresh",action="store_true")
    p.add_argument("--api",choices=tuple(FIELDS),default="adj_factor")
    p.add_argument("--symbols",default=""); p.add_argument("--trade-date")
    p.add_argument("--as-of-version",type=int); p.add_argument("--daily-version",type=int)
    p.add_argument("--anchor-date"); p.add_argument("--adjustment",choices=("qfq","hfq"),default="qfq")
    p.add_argument("--limit",type=int,default=100); p.add_argument("--offset",type=int,default=0)
    args = p.parse_args(argv)
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",args.store),"INVALID_STORE_NAME")
    v1.historical_range(args.start,args.end)
    w = Sidecar(ROOT/"state"/"historical-sidecar"/args.store)
    w.check_paths(descendants=True)
    if args.action in ("plan","status","report"):
        result = w.report(args.start,args.end)
        if args.action=="plan":
            result.update(authorization=PERMISSION,worker_count=1,default_rpm=60,hard_rpm_cap=120,official_2000_tier_rpm=200)
    elif args.action=="verify":
        result = w.verify()
    elif args.action=="query":
        result = w.query(args.api,args.start,args.end,tuple(filter(None,args.symbols.split(","))),args.trade_date,args.as_of_version,args.limit,args.offset)
    elif args.action=="adjusted":
        require(args.v1_root and args.anchor_date and args.as_of_version and args.daily_version and len(args.symbols.split(","))==1,"EXPLICIT_ANCHOR_SOURCE_AND_VERSIONS_REQUIRED")
        result = adjusted(w,args.v1_root,args.symbols,args.start,args.end,args.anchor_date,args.as_of_version,args.daily_version,args.adjustment)
    else:
        token,source = v1.credential(args.credential_source)
        with w.write() as db:
            if not db.execute("SELECT 1 FROM metadata_source").fetchone():
                require(args.v1_root is not None,"EXISTING_V1_METADATA_REQUIRED")
                w.import_v1(db,args.v1_root)
            download = Download(w,db,args.action,TushareHTTP(token),source,args.start,args.end,args.rpm,args.max_calls,args.total_call_cap,
                                progress=lambda v:print(json.dumps(v,sort_keys=True),file=sys.stderr,flush=True))
            download.retry_failed = args.retry_failed
            try:
                result = download.preflight() if args.action=="preflight" else download.backfill(args.retry_failed,args.refresh)
            except Error as e:
                result = download.finish(str(e))
        result["report"] = w.report(args.start,args.end)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
    if args.action in ("preflight","backfill","resume"):
        return 0 if result["state"] in ("PREFLIGHT_PASSED","RANGE_COLLECTED_COVERAGE_PARTIAL") else 2
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(cli())
    except Error as e:
        print(json.dumps(dict(state="BLOCKED",reason=str(e),**SAFE)),flush=True)
        raise SystemExit(2)
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):
        print(json.dumps(dict(state="BLOCKED",reason="LOCAL_IO_OR_SCHEMA_ERROR",**SAFE)),flush=True)
        raise SystemExit(2)
