"""Issue #57: local ex-post history, never a forward observer or trading input gate.

Only the transport is injectable. Parsing, versioning, transactions and queries
are shared by offline tests and the explicit foreground HTTPS commands.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
from decimal import Decimal, InvalidOperation, localcontext
import gzip
import hashlib
import http.client as http_client
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "tushare-historical-warehouse-v1"
SCHEMA = 2012
START, END = "20211101", "20261030"
SAMPLES = ("20211101", "20221101", "20231101", "20241101", "20261030")
EXCHANGES = ("SSE", "SZSE", "BSE")
STATUSES = ("L", "D", "P", "G", "UN")
CAP = 6000
DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount,ah_vol,ah_amount"
STOCK_FIELDS = "ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs,act_name,act_ent_type"
CAL_FIELDS = "exchange,cal_date,is_open,pretrade_date"
FIELDS = dict(daily=DAILY_FIELDS, stock_basic=STOCK_FIELDS, trade_cal=CAL_FIELDS)
SAFE = dict(data_mode="historical_backfill_ex_post", historical_pit_status="NOT_VERIFIED",
            forward_research_readiness="BLOCKED", paper_allowed=False, live_allowed=False,
            provider_published_at=None, historical_received_at=None)
CONTRACT = dict(version=VERSION, schema=SCHEMA, **SAFE, provider="Tushare",
                fields=FIELDS, adjustment="unadjusted", price_unit="CNY_yuan",
                vol_unit="lot_100_shares", amount_unit="CNY_thousand_yuan",
                pre_close_semantics="provider_ex_rights_previous_close",
                availability="obtained_at_is_actual_download_time_not_historical_availability",
                catalog="current_snapshot_not_historical_membership_or_names",
                license="Owner-authorized existing Tushare account; personal local research; no redistribution grant")
PERMISSION_SOURCE = "Owner Issue #57 / existing account / only stock_basic,trade_cal,daily"
REFRESH_REJECTED = "PARTIAL_REFRESH_REJECTED_"


class WarehouseError(Exception):
    """Messages are fixed local reason codes, never remote errors or secrets."""


def require(condition, reason):
    if not condition:
        raise WarehouseError(reason)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def unfloat(value):
    if isinstance(value, Decimal):
        require(value.is_finite(), "NONFINITE_NUMBER")
        return str(value)
    if isinstance(value, list):
        return [unfloat(v) for v in value]
    if isinstance(value, dict):
        return {k: unfloat(v) for k, v in value.items()}
    require(not isinstance(value, float), "FLOAT_NOT_ALLOWED")
    return value


def day(value):
    require(isinstance(value, str) and bool(re.fullmatch(r"\d{8}", value)), "INVALID_DATE")
    try:
        return dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        raise WarehouseError("INVALID_DATE") from None


def dates(start, end):
    a, b = day(start), day(end)
    require(a <= b, "INVALID_RANGE")
    return [(a + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range((b-a).days+1)]


def historical_range(start, end):
    dates(start, end)
    # V1 has an explicit published historical endpoint. No intraday/clock bypass.
    require(START <= start <= end <= END, "OUTSIDE_AUTHORIZED_COMPLETED_HISTORY")
    require(day(end) < dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date(), "UNFINISHED_DAY")


def exchange(code):
    require(isinstance(code, str) and bool(re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", code)), "INVALID_STOCK_CODE")
    # A shares/CDR only, not B shares, funds, indices or bonds. BJ old/new codes coexist.
    prefix, suffix = code.split(".")
    allowed = {"SH": ("6", "689"), "SZ": ("0", "3"), "BJ": ("4", "8", "920")}
    require(prefix.startswith(allowed[suffix]), "NOT_A_SHARE_CODE")
    return {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}[suffix]


def decimal_text(value, positive=False):
    require(not isinstance(value, (bool, float)) and value is not None, "INVALID_NUMERIC_TYPE")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise WarehouseError("INVALID_NUMBER") from None
    require(result.is_finite() and result >= 0 and (not positive or result > 0), "INVALID_PRICE_OR_VOLUME")
    return str(result)


def exact_scaled(value, scale):
    """Optional conversions reject precision loss; normalized data stays source text."""
    text = decimal_text(value)
    with localcontext() as ctx:
        ctx.prec = max(40, len(text) + len(str(scale)) + 8)
        result = Decimal(text) * Decimal(scale)
        require(result == result.to_integral_value() and result <= 2**63-1, "NOT_EXACTLY_REPRESENTABLE")
        return int(result)


def parse_response(raw):
    try:
        body = json.loads(raw, parse_float=Decimal,
                          parse_constant=lambda _: (_ for _ in ()).throw(WarehouseError("NONFINITE_NUMBER")))
    except (ValueError, UnicodeError):
        raise WarehouseError("INVALID_RESPONSE_JSON") from None
    require(isinstance(body, dict) and isinstance(body.get("code"), int), "INVALID_ENVELOPE")
    if body["code"] != 0:
        # Provider message is used for classification, never persisted or displayed.
        msg = str(body.get("msg", ""))
        if any(v in msg for v in ("每分钟", "每小时", "每天", "频次", "频率", "访问次数", "rate limit")):
            return "RATE_LIMITED", body["code"], [], []
        if any(v in msg.lower() for v in ("token", "认证", "鉴权", "登录")):
            return "AUTH_DENIED", body["code"], [], []
        if any(v in msg for v in ("权限", "积分", "无权")):
            return "PERMISSION_DENIED", body["code"], [], []
        return "PROVIDER_ERROR", body["code"], [], []
    data = body.get("data")
    require(isinstance(data, dict), "EMPTY_REMOTE_RESPONSE")
    fields, items = data.get("fields"), data.get("items")
    require(isinstance(fields, list) and all(isinstance(f, str) for f in fields)
            and len(fields) == len(set(fields)), "INVALID_FIELD_SET")
    require(isinstance(items, list) and all(isinstance(r, list) and len(r) == len(fields) for r in items), "INVALID_ROW_SHAPE")
    rows = [unfloat(dict(zip(fields, row))) for row in items]
    return "OK", 0, fields, rows


def validate(api, params, fields, rows):
    required = {
        "daily": set("ts_code,trade_date,open,high,low,close,pre_close,vol,amount".split(",")),
        "stock_basic": set("ts_code,symbol,name,exchange,market,list_status,list_date,delist_date".split(",")),
        "trade_cal": set(CAL_FIELDS.split(",")),
    }[api]
    require(required <= set(fields), "MISSING_REQUIRED_FIELDS")
    unique, duplicate_count = {}, 0
    for original in rows:
        r = dict(original)
        if api == "daily":
            exchange(r["ts_code"])
            require(r["trade_date"] == params["trade_date"], "DATE_SCOPE_MISMATCH")
            day(r["trade_date"])
            if params.get("ts_code"):
                require(r["ts_code"] in params["ts_code"].split(","), "PARTITION_SCOPE_MISMATCH")
            for f in ("open", "high", "low", "close", "vol", "amount"):
                r[f] = decimal_text(r[f], positive=f not in ("vol", "amount"))
            if r["pre_close"] is None:
                r["quality_flags"] = ["PRE_CLOSE_UNVERIFIED_NULL_FROM_PROVIDER"]
            else:
                r["pre_close"] = decimal_text(r["pre_close"], positive=True)
            for f in ("ah_vol", "ah_amount"):
                if r.get(f) is not None:
                    r[f] = decimal_text(r[f])
            lo, hi, op, cl = (Decimal(r[f]) for f in ("low", "high", "open", "close"))
            require(lo <= min(op, cl) <= max(op, cl) <= hi, "INVALID_OHLC")
            key = (r["ts_code"], r["trade_date"])
        elif api == "stock_basic":
            # Real retired catalogs include legacy temporary codes (e.g. a T
            # prefix) outside this authorized five-year universe. Preserve the
            # complete raw catalog, exclude pre-window retirements from its view.
            if r.get("delist_date") and day(r["delist_date"]) < day(START):
                continue
            # stock_basic also returns B shares. Keep them in raw, explicitly
            # exclude their known code families from the A-share research view.
            if isinstance(r["ts_code"],str) and re.fullmatch(r"(900\d{3}\.SH|200\d{3}\.SZ)",r["ts_code"]):
                continue
            require(exchange(r["ts_code"]) == params["exchange"] == r["exchange"], "EXCHANGE_SCOPE_MISMATCH")
            require(isinstance(r["symbol"],str) and bool(re.fullmatch(r"\d{6}",r["symbol"]))
                    and (r["exchange"]=="BSE" or r["symbol"]==r["ts_code"][:6])
                    and r["list_status"] == params["list_status"], "CATALOG_SCOPE_MISMATCH")
            if params.get("ts_code"):
                require(r["ts_code"] in params["ts_code"].split(","), "PARTITION_SCOPE_MISMATCH")
            require(isinstance(r["name"], str) and bool(r["name"]), "INVALID_CATALOG_NAME")
            for f in ("list_date", "delist_date"):
                if r.get(f):
                    day(r[f])
            if r.get("list_date") and r.get("delist_date"):
                require(r["list_date"] <= r["delist_date"], "INVALID_LISTING_INTERVAL")
            key = r["ts_code"]
        else:
            require(r["exchange"] == params["exchange"], "EXCHANGE_SCOPE_MISMATCH")
            day(r["cal_date"])
            require(params["start_date"] <= r["cal_date"] <= params["end_date"], "DATE_SCOPE_MISMATCH")
            r["is_open"] = str(r["is_open"])
            require(r["is_open"] in ("0", "1"), "INVALID_OPEN_FLAG")
            if r.get("pretrade_date"):
                day(r["pretrade_date"])
                require(r["pretrade_date"] < r["cal_date"], "INVALID_CALENDAR_PREDECESSOR")
            key = (r["exchange"], r["cal_date"])
        if key in unique:
            require(unique[key] == r, "CONFLICTING_DUPLICATE_ROW")
            duplicate_count += 1
        else:
            unique[key] = r
    return sorted(unique.values(), key=lambda r: canonical(r)), duplicate_count


def credential(source="auto"):
    if source == "existing-tushare-mcp-config":
        # Explicit reuse of the already connected first-party Tushare service.
        # Read in this process only; do not copy URL/token to state or env/argv.
        import tomllib
        import urllib.parse
        try:
            config = tomllib.loads((Path.home()/".codex"/"config.toml").read_text(encoding="utf-8"))
            url = urllib.parse.urlsplit(config["mcp_servers"]["tushare"]["url"])
            require(url.scheme == "https" and url.hostname == "api.tushare.pro"
                    and url.path == "/mcp/" and url.username is None, "CREDENTIAL_SOURCE_NOT_TUSHARE")
            values = urllib.parse.parse_qs(url.query).get("token",[])
            require(len(values)==1 and bool(values[0].strip()) and len(values[0])<=1024, "CREDENTIAL_UNAVAILABLE")
            return values[0].strip(), "existing-tushare-mcp-config:local-read-only"
        except (OSError,KeyError,ValueError,TypeError):
            raise WarehouseError("CREDENTIAL_UNAVAILABLE") from None
    token = os.environ.get("STRATIDE_TUSHARE_TOKEN", "").strip()
    if token:
        require(len(token) <= 1024, "CREDENTIAL_UNAVAILABLE")
        return token, "process-env:STRATIDE_TUSHARE_TOKEN"
    require(os.name == "nt", "CREDENTIAL_UNAVAILABLE")
    # Same existing repository-scoped target as EOD Operator; read only, no import
    # of its service or state. Never read the old plaintext token document.
    import ctypes as ct
    from ctypes import wintypes as w
    import subprocess
    result = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=ROOT, capture_output=True, check=True)
    common = Path(os.fsdecode(result.stdout).strip()).resolve().parent
    target = "Stratide/" + sha(str(common).casefold().encode()) + "/tushare-daily-trade-cal-v1"

    class Entry(ct.Structure):
        _fields_ = [("Flags", w.DWORD), ("Type", w.DWORD), ("TargetName", w.LPWSTR),
                    ("Comment", w.LPWSTR), ("LastWritten", w.FILETIME),
                    ("CredentialBlobSize", w.DWORD), ("CredentialBlob", ct.POINTER(ct.c_ubyte)),
                    ("Persist", w.DWORD), ("AttributeCount", w.DWORD), ("Attributes", ct.c_void_p),
                    ("TargetAlias", w.LPWSTR), ("UserName", w.LPWSTR)]

    dll = ct.WinDLL("Advapi32.dll", use_last_error=True)
    dll.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ct.POINTER(ct.POINTER(Entry))]
    dll.CredReadW.restype = w.BOOL
    dll.CredFree.argtypes = [ct.c_void_p]
    entry = ct.POINTER(Entry)()
    require(dll.CredReadW(target, 1, 0, ct.byref(entry)), "CREDENTIAL_UNAVAILABLE")
    try:
        token = ct.string_at(entry.contents.CredentialBlob, entry.contents.CredentialBlobSize).decode("utf-16-le").strip()
    finally:
        dll.CredFree(entry)
    require(bool(token) and len(token) <= 1024, "CREDENTIAL_UNAVAILABLE")
    return token, "existing-windows-credential-manager:repository-tushare"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise WarehouseError("AUTHENTICATED_REDIRECT_DENIED")


class TushareHTTP:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect)

    def __call__(self, api, params, fields):
        request = urllib.request.Request("https://api.tushare.pro",
                                         data=canonical(dict(api_name=api, params=params, fields=fields, token=self.token)),
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            response = self.opener.open(request, timeout=40)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            raw = response.read(16_000_001)
            require(len(raw) <= 16_000_000, "RESPONSE_TOO_LARGE")
            # A secret echoed by a remote error must not enter raw/logs either.
            require(self.token.encode() not in raw, "SECRET_ECHO_REJECTED")
            retry_after = response.headers.get("Retry-After", "")
            return response.code, raw, retry_after


DDL = """
CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1), contract TEXT NOT NULL, sha TEXT NOT NULL);
CREATE TABLE runs(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
                  status TEXT NOT NULL, config TEXT NOT NULL, config_sha TEXT NOT NULL);
CREATE TABLE attempts(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
 api TEXT NOT NULL, params TEXT NOT NULL, fields TEXT NOT NULL, credential_source TEXT NOT NULL,
 permission_source TEXT NOT NULL, started TEXT NOT NULL, ended TEXT, status TEXT NOT NULL,
 may_have_sent INTEGER NOT NULL, http_status INTEGER, provider_code INTEGER, row_count INTEGER,
 response_sha TEXT, raw_bytes INTEGER, canonical_sha TEXT, duplicates INTEGER, retry_after TEXT,
 metadata_sha TEXT);
CREATE INDEX attempts_scope ON attempts(api,params,id);
CREATE TABLE permissions(api TEXT PRIMARY KEY, status TEXT NOT NULL, attempt_id INTEGER NOT NULL REFERENCES attempts(id));
CREATE TABLE objects(api TEXT NOT NULL, object_key TEXT NOT NULL, row_sha TEXT NOT NULL,
 row_json TEXT NOT NULL, attempt_id INTEGER NOT NULL REFERENCES attempts(id),
 PRIMARY KEY(api,object_key,attempt_id));
CREATE INDEX objects_latest ON objects(api,object_key,attempt_id DESC);
CREATE TABLE daily_rows(ts_code TEXT NOT NULL, trade_date TEXT NOT NULL, row_sha TEXT NOT NULL,
 open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
 pre_close TEXT, vol TEXT NOT NULL, amount TEXT NOT NULL, row_json TEXT NOT NULL,
 PRIMARY KEY(ts_code,trade_date,row_sha));
CREATE INDEX daily_date ON daily_rows(trade_date,ts_code);
CREATE TABLE day_versions(id INTEGER PRIMARY KEY, trade_date TEXT NOT NULL, created TEXT NOT NULL,
 status TEXT NOT NULL, reason TEXT NOT NULL, row_count INTEGER NOT NULL, content_sha TEXT NOT NULL,
 source_sha TEXT NOT NULL, manifest TEXT NOT NULL);
CREATE INDEX day_versions_date ON day_versions(trade_date,id DESC);
CREATE TABLE day_rows(version_id INTEGER NOT NULL REFERENCES day_versions(id), ts_code TEXT NOT NULL,
 trade_date TEXT NOT NULL, row_sha TEXT NOT NULL,
 PRIMARY KEY(version_id,ts_code), FOREIGN KEY(ts_code,trade_date,row_sha) REFERENCES daily_rows(ts_code,trade_date,row_sha));
CREATE INDEX day_rows_symbol ON day_rows(ts_code,trade_date,version_id);
CREATE TABLE day_sources(version_id INTEGER NOT NULL REFERENCES day_versions(id),
 attempt_id INTEGER NOT NULL REFERENCES attempts(id), PRIMARY KEY(version_id,attempt_id));
CREATE TABLE checkpoints(trade_date TEXT PRIMARY KEY, version_id INTEGER NOT NULL REFERENCES day_versions(id));
CREATE INDEX checkpoints_version ON checkpoints(version_id);
"""


@contextlib.contextmanager
def writer_lock(root, readonly=False):
    no_links(root)
    no_links(root/"writer.lock")
    if not readonly:
        root.mkdir(parents=True, exist_ok=True)
    require(not readonly or (root/"writer.lock").is_file(), "WAREHOUSE_NOT_INITIALIZED")
    with (root / "writer.lock").open("rb" if readonly else "a+b") as lock:
        if not readonly and lock.tell() == 0:
            lock.write(b"0"); lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise WarehouseError("WAREHOUSE_WRITER_BUSY") from None
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def connection(path, readonly=False):
    for p in (path,*(Path(str(path)+suffix) for suffix in ("-wal","-shm","-journal"))):
        no_links(p)
    if readonly:
        require(path.is_file(), "WAREHOUSE_NOT_INITIALIZED")
        # immutable avoids SQLite creating/updating SHM on a read. Reject live or
        # uncheckpointed WAL instead of silently reading a stale main database.
        require(not Path(str(path) + "-wal").exists() or Path(str(path) + "-wal").stat().st_size == 0,
                "WRITER_ACTIVE_OR_RECOVERY_REQUIRED")
        db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        db.execute("PRAGMA query_only=ON")
    else:
        db = sqlite3.connect(path, timeout=2)
    db.row_factory = sqlite3.Row
    return db


def check_contract(db):
    require(db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA, "SCHEMA_MISMATCH")
    row = db.execute("SELECT * FROM meta WHERE id=1").fetchone()
    require(row is not None and row["contract"].encode() == canonical(CONTRACT)
            and row["sha"] == sha(canonical(CONTRACT)), "SOURCE_METADATA_TAMPERED")


def attempt_hash(row):
    return sha(canonical({k: row[k] for k in row.keys() if k != "metadata_sha"}))


def no_links(path):
    """Same no-follow boundary as the existing journal reader, including junctions."""
    path=Path(path).absolute()
    for part in (path,*path.parents):
        require(not part.is_symlink() and not part.is_junction(),"WAREHOUSE_LINK_DENIED")


class Warehouse:
    def __init__(self, root):
        # Preserve the lexical path so a linked root is rejected, not resolved away.
        self.root = Path(root).absolute()
        self.path = self.root / "warehouse.sqlite"

    def check_paths(self, descendants=False):
        for path in (self.root,self.path,self.root/"writer.lock",self.root/"raw",
                     *(Path(str(self.path)+suffix) for suffix in ("-wal","-shm","-journal"))):
            no_links(path)
        if descendants and self.root.is_dir():
            pending=[self.root]
            while pending:
                for path in pending.pop().iterdir():
                    no_links(path)
                    if path.is_dir():pending.append(path)

    @contextlib.contextmanager
    def write(self):
        self.check_paths(descendants=True)
        with writer_lock(self.root):
            db = connection(self.path)
            owned=False
            try:
                new=db.execute("PRAGMA user_version").fetchone()[0] == 0
                if new:
                    # Only initialize a new empty file, never migrate an Observer/Agent DB.
                    require(not db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), "FOREIGN_DATABASE")
                else:
                    check_contract(db)
                # Never change a foreign database's journal mode before validation.
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA foreign_keys=ON")
                owned=True
                if new:
                    with db:
                        db.executescript("BEGIN IMMEDIATE;" + DDL)
                        db.execute("INSERT INTO meta VALUES(1,?,?)", (canonical(CONTRACT).decode(), sha(canonical(CONTRACT))))
                        db.execute(f"PRAGMA user_version={SCHEMA}")
                check_contract(db)
                # A crash may have sent its request. Persist unknown, never count success.
                with db:
                    db.execute("UPDATE runs SET status='INTERRUPTED',ended=? WHERE status='RUNNING'", (now(),))
                    for row in db.execute("SELECT * FROM attempts WHERE status='SENDING'").fetchall():
                        db.execute("UPDATE attempts SET status='NETWORK_OUTCOME_UNKNOWN',ended=? WHERE id=?", (now(), row["id"]))
                        self.seal_attempt(db, row["id"])
                yield db
            finally:
                if owned:db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.close()

    @contextlib.contextmanager
    def read(self):
        self.check_paths(descendants=True)
        # Read an existing lock without creating/writing it, fencing the race
        # between WAL inspection and an immutable read of a changing main file.
        with writer_lock(self.root,readonly=True):
            db = connection(self.path, True)
            try:
                check_contract(db)
                yield db
            finally:
                db.close()

    def seal_attempt(self, db, attempt_id):
        row = db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        db.execute("UPDATE attempts SET metadata_sha=? WHERE id=?", (attempt_hash(row), attempt_id))

    def raw_path(self, attempt_id):
        path=self.root / "raw" / f"{attempt_id:08d}.json.gz"
        no_links(path)
        return path

    def save_raw(self, attempt_id, raw):
        self.check_paths()
        target = self.raw_path(attempt_id)
        pending = target.with_suffix(".pending")
        no_links(pending)
        target.parent.mkdir(exist_ok=True)
        with pending.open("xb") as f:
            f.write(gzip.compress(raw, mtime=0)); f.flush(); os.fsync(f.fileno())
        no_links(target)
        os.replace(pending, target)

    def latest_objects(self, db, api):
        return [json.loads(r[0]) for r in db.execute("""SELECT o.row_json FROM objects o JOIN
            (SELECT object_key,MAX(attempt_id) a FROM objects WHERE api=? GROUP BY object_key) x
            ON o.api=? AND o.object_key=x.object_key AND o.attempt_id=x.a ORDER BY o.object_key""", (api, api))]

    def permission(self, db, api):
        row = db.execute("SELECT status FROM permissions WHERE api=?", (api,)).fetchone()
        return row[0] if row else "UNVERIFIED"

    def publish_objects(self, db, api, rows, attempt_id):
        with db:
            for r in rows:
                key = r["ts_code"] if api == "stock_basic" else r["exchange"] + ":" + r["cal_date"]
                data = canonical(r)
                db.execute("INSERT INTO objects VALUES(?,?,?,?,?)", (api, key, sha(data), data.decode(), attempt_id))

    def publish_day(self, db, date, rows, attempts, status, reason, fault=None):
        # Source hashes bind request/time/credential source/units to immutable raw.
        sources = [dict(db.execute("SELECT * FROM attempts WHERE id=?", (a,)).fetchone()) for a in attempts]
        current = db.execute("SELECT v.* FROM checkpoints c JOIN day_versions v ON v.id=c.version_id WHERE c.trade_date=?", (date,)).fetchone()
        if current and current["status"]=="COMPLETE":
            previous_codes={r[0] for r in db.execute("SELECT ts_code FROM day_rows WHERE version_id=?",(current["id"],))}
            if status=="COMPLETE" and not previous_codes <= {r["ts_code"] for r in rows}:
                status,reason="PARTIAL","MISSING_PRIOR_SYMBOLS"
            if status!="COMPLETE":
                # Only the new attempt is classified. The admitted version, its
                # manifest, checkpoint and old frozen inputs remain untouched.
                with db:
                    for a in attempts:
                        db.execute("UPDATE attempts SET status=? WHERE id=?",(REFRESH_REJECTED+reason,a))
                        self.seal_attempt(db,a)
                return dict(version_id=current["id"],status="PARTIAL_REFRESH_REJECTED",reason=reason)
        manifest = dict(contract_sha=sha(canonical(CONTRACT)), revision_of_version=current["id"] if current else None,
                        revision_relation="SOURCE_REVISION_OR_CONFLICT" if current else "INITIAL_DOWNLOAD",
                        attempts=[dict(id=r["id"], metadata_sha=r["metadata_sha"],
                         response_sha=r["response_sha"], obtained_at=r["ended"]) for r in sources])
        hashed_rows = sorted((r["ts_code"], sha(canonical(r))) for r in rows)
        content_sha = sha(canonical(hashed_rows))
        with db:
            old = current if current and current["content_sha"]==content_sha and current["status"]==status else None
            if old:
                version = old[0]
            else:
                version = db.execute("INSERT INTO day_versions(trade_date,created,status,reason,row_count,content_sha,source_sha,manifest) VALUES(?,?,?,?,?,?,?,?)",
                                     (date, now(), status, reason, len(rows), content_sha, sha(canonical(manifest)), canonical(manifest).decode())).lastrowid
                for i, r in enumerate(rows):
                    data, rh = canonical(r).decode(), sha(canonical(r))
                    db.execute("INSERT OR IGNORE INTO daily_rows VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (r["ts_code"], date, rh, *(r[f] for f in ("open", "high", "low", "close", "pre_close", "vol", "amount")), data))
                    db.execute("INSERT INTO day_rows VALUES(?,?,?,?)", (version, r["ts_code"], date, rh))
                    if fault:
                        fault(i)
            for a in attempts:
                db.execute("INSERT OR IGNORE INTO day_sources VALUES(?,?)", (version, a))
            # Publishing version, all its rows and checkpoint is one transaction.
            db.execute("INSERT INTO checkpoints VALUES(?,?) ON CONFLICT(trade_date) DO UPDATE SET version_id=excluded.version_id", (date, version))
        return dict(version_id=version,status=status,reason=reason)

    def calendar(self, db):
        return {(r["exchange"], r["cal_date"]): r for r in self.latest_objects(db, "trade_cal")}

    def report(self, start=START, end=END):
        historical_range(start, end)
        self.check_paths(descendants=True)
        base = dict(version=VERSION, start=start, end=end, **SAFE)
        if not self.path.exists():
            return dict(base, state="UNINITIALIZED", coverage="UNVERIFIED", calendar_dates=len(dates(start, end)),
                        complete_dates=0, requests=0, remaining_request_estimate=None)
        with self.read() as db:
            cal = self.calendar(db)
            days = dates(start, end)
            opened = {d for (e, d), r in cal.items() if start <= d <= end and r["is_open"] == "1"}
            checkpoints = {r["trade_date"]: dict(r) for r in db.execute("""SELECT v.* FROM checkpoints c JOIN day_versions v ON v.id=c.version_id
                           WHERE c.trade_date BETWEEN ? AND ? ORDER BY c.trade_date""", (start, end))}
            complete = {d for d, r in checkpoints.items() if r["status"] == "COMPLETE"}
            failed_dates, attempted_dates = set(), set()
            for r in db.execute("SELECT params,status FROM attempts WHERE api='daily'"):
                params = json.loads(r["params"])
                d = params["trade_date"]
                if start <= d <= end and not params.get("ts_code"):
                    attempted_dates.add(d)
                    if r["status"] not in ("OK","EMPTY","TRUNCATION_SUSPECTED"):
                        failed_dates.add(d)
            catalog = self.latest_objects(db, "stock_basic")
            known_codes = {r["ts_code"] for r in catalog}
            actual_codes = {r[0] for r in db.execute("SELECT DISTINCT dr.ts_code FROM day_rows dr JOIN checkpoints c ON c.version_id=dr.version_id WHERE dr.trade_date BETWEEN ? AND ?", (start,end))}
            unmatched_codes = actual_codes-known_codes
            per_exchange = {}
            missing_total = 0
            for e in EXCHANGES:
                known = [r for r in catalog if r["exchange"] == e and r.get("list_date") and r["list_date"] <= end
                         and (not r.get("delist_date") or r["delist_date"] >= start)]
                found = db.execute("""SELECT COUNT(*) rows,COUNT(DISTINCT r.ts_code) symbols FROM checkpoints c JOIN day_rows r ON r.version_id=c.version_id
                                  WHERE r.trade_date BETWEEN ? AND ? AND r.ts_code LIKE ?""", (start, end, "%"+{"SSE":".SH","SZSE":".SZ","BSE":".BJ"}[e])).fetchone()
                # Missing is a candidate gap, not a suspension or fabricated zero.
                expected = sum(1 for r in known for d in complete if (e, d) in cal and cal[e,d]["is_open"] == "1"
                               and r["list_date"] <= d and (not r.get("delist_date") or d <= r["delist_date"]))
                # Exact anti-join uses the latest catalog snapshot; explicitly UNVERIFIED.
                missing = 0
                for r in known:
                    expected_days = {d for d in complete if (e,d) in cal and cal[e,d]["is_open"] == "1" and r["list_date"] <= d
                                     and (not r.get("delist_date") or d <= r["delist_date"])}
                    actual = {x[0] for x in db.execute("SELECT dr.trade_date FROM day_rows dr JOIN checkpoints c ON dr.version_id=c.version_id WHERE dr.ts_code=? AND dr.trade_date BETWEEN ? AND ?", (r["ts_code"],start,end))}
                    missing += len(expected_days - actual)
                missing_total += missing
                per_exchange[e] = dict(catalog_symbols=len(known), daily_rows=found["rows"], daily_symbols=found["symbols"],
                                       catalog_unmatched_daily_symbols=sum(exchange(code)==e for code in unmatched_codes),
                                       calendar_days=sum((e,d) in cal for d in days),
                                       calendar_coverage="COVERAGE_COMPLETE" if all((e,d) in cal for d in days) else "PARTIAL",
                                       snapshot_expected_symbol_days_unverified=expected if any((e,d) in cal for d in days) else None,
                                       missing_or_not_trading_unverified=missing if any((e,d) in cal for d in days) else None)
            req = db.execute("SELECT COUNT(*),MIN(CASE WHEN response_sha IS NOT NULL THEN ended END),MAX(CASE WHEN response_sha IS NOT NULL THEN ended END),COALESCE(SUM(raw_bytes),0) FROM attempts").fetchone()
            states = {r[0]: r[1] for r in db.execute("SELECT status,COUNT(*) FROM attempts GROUP BY status")}
            permissions = {r["api"]: dict(r) for r in db.execute("SELECT * FROM permissions ORDER BY api")}
            raw_bytes = req[3]
            sample = db.execute("SELECT COUNT(*),COALESCE(SUM(row_count),0) FROM day_versions WHERE status='COMPLETE'").fetchone()
            remaining = len(opened - complete) if opened else None
            disk_bytes = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
            estimate = (int((disk_bytes / sample[0]) * remaining * 1.5) if remaining is not None and sample[0] else None)
            full_calendar = all((e,d) in cal for e in ("SSE","SZSE") for d in days)
            recommended_cap = req[0]+remaining+max(20,(remaining+9)//10) if remaining is not None else None
            stock_queries = [dict(api=r["api"],params=json.loads(r["params"]),status=r["status"],rows=r["row_count"],
                                 normalized_rows=db.execute("SELECT COUNT(*) FROM objects WHERE attempt_id=?",(r["id"],)).fetchone()[0],response_sha=r["response_sha"])
                             for r in db.execute("SELECT * FROM attempts WHERE api!='daily' ORDER BY id")]
            previous_batch = db.execute("SELECT config FROM runs WHERE kind IN ('backfill','resume') ORDER BY id DESC LIMIT 1").fetchone()
            persisted_cap = json.loads(previous_batch[0])["total_cap"] if previous_batch else None
            return dict(base, state="COMPLETE" if full_calendar and opened and complete >= opened else ("PARTIAL" if checkpoints else "BLOCKED"),
                        # No historical master / BJ code-change history in Phase 1.
                        coverage="PARTIAL" if checkpoints else "UNVERIFIED", historical_universe="UNVERIFIED",
                        calendar_dates=len(days), known_open_dates=len(opened), complete_dates=len(complete),
                        downloaded_dates=len(checkpoints), partial_dates=len(checkpoints)-len(complete),
                        failed_dates=len(failed_dates-set(checkpoints)), dates_with_failed_attempts=len(failed_dates),
                        attempted_full_market_dates=len(attempted_dates),
                        uncommitted_successful_dates=len(attempted_dates-set(checkpoints)-failed_dates),
                        unattempted_known_open_dates=len(opened-attempted_dates),
                        missing_known_open_dates=sorted(opened-complete), calendar_unknown_dates=sum(not any((e,d) in cal for e in EXCHANGES) for d in days),
                        row_count=sum(r["row_count"] for r in checkpoints.values()), per_exchange=per_exchange,
                        missing_or_not_trading_unverified=missing_total, requests=req[0], request_statuses=states,
                        first_obtained_at=req[1], last_obtained_at=req[2], raw_response_bytes=raw_bytes,
                        disk_bytes=disk_bytes, recommended_batch_total_call_cap=recommended_cap,
                        persisted_batch_total_call_cap=persisted_cap,
                        free_disk_bytes=shutil.disk_usage(self.root).free, permissions=permissions,
                        metadata_queries=stock_queries, remaining_request_estimate=remaining,
                        estimated_additional_disk_bytes=estimate, estimate_basis="actual on-disk raw+SQLite+indexes per sampled date x remaining x1.5; includes metadata overhead; truncation can add requests",
                        truncation_attempts=db.execute("SELECT COUNT(*) FROM attempts WHERE api='daily' AND row_count>=?",(CAP,)).fetchone()[0],
                        rejected_refresh_attempts=sum(n for status,n in states.items() if status.startswith(REFRESH_REJECTED)),
                        rejected_refresh_reasons={status[len(REFRESH_REJECTED):]:n for status,n in states.items() if status.startswith(REFRESH_REJECTED)},
                        truncation_suspected_dates=sum(r["reason"] in ("TRUNCATION_SUSPECTED","PARTITIONED_KNOWN_UNIVERSE_UNVERIFIED") for r in checkpoints.values()),
                        catalog_symbol_aliases_unverified=sum(r["symbol"]!=r["ts_code"][:6] for r in catalog),
                        catalog_unmatched_daily_symbols=len(unmatched_codes),
                        source_field_unverified_dates=sum(r["reason"]=="SOURCE_FIELD_UNVERIFIED" for r in checkpoints.values()),
                        source_revision_rows=db.execute("SELECT COUNT(*) FROM (SELECT 1 FROM daily_rows GROUP BY ts_code,trade_date HAVING COUNT(*)>1)").fetchone()[0],
                        versions=db.execute("SELECT COUNT(*) FROM day_versions").fetchone()[0], resumable=True,
                        limitations=["CURRENT_CATALOG_NOT_HISTORICAL_MASTER", "BSE_CALENDAR_UNVERIFIED_UNLESS_ACTUALLY_RETURNED",
                                     "HISTORICAL_CODE_MAPPING_NOT_VERIFIED", "MISSING_OR_NOT_TRADING_UNVERIFIED",
                                     "NO_CORPORATE_ACTION_OR_SUSPENSION_VERIFICATION", "NO_HISTORICAL_PIT"])

    def query(self, start, end, symbols=(), trade_date=None, as_of_version=None, limit=100):
        historical_range(start,end)
        require(1 <= limit <= 10000, "QUERY_LIMIT_1_TO_10000")
        for code in symbols:
            exchange(code)
        if trade_date:
            require(start <= trade_date <= end, "DATE_SCOPE_MISMATCH")
        with self.read() as db:
            args = [start,end]
            if as_of_version is not None:
                require(as_of_version > 0, "INVALID_VERSION")
                require(db.execute("SELECT 1 FROM day_versions WHERE id=?",(as_of_version,)).fetchone() is not None,
                        "AS_OF_VERSION_NOT_FOUND")
                args.append(as_of_version)
                # Every stored day_version was admitted. Rejected refreshes keep
                # only attempts/raw, so historical selection shares that policy.
                cte="WITH chosen AS (SELECT trade_date,MAX(id) id FROM day_versions v WHERE v.trade_date BETWEEN ? AND ? AND v.id<=? GROUP BY trade_date) "
            else:
                cte="WITH chosen AS (SELECT trade_date,version_id id FROM checkpoints WHERE trade_date BETWEEN ? AND ?) "
            sql = cte + """SELECT d.row_json,v.id version_id,v.status,v.source_sha,v.manifest FROM chosen c
                 JOIN day_versions v ON v.id=c.id JOIN day_rows dr ON dr.version_id=v.id
                 JOIN daily_rows d ON d.ts_code=dr.ts_code AND d.trade_date=dr.trade_date AND d.row_sha=dr.row_sha WHERE 1=1"""
            if symbols:
                sql += " AND d.ts_code IN (" + ",".join("?" for _ in symbols) + ")"; args.extend(symbols)
            if trade_date:
                sql += " AND d.trade_date=?"; args.append(trade_date)
            sql += " ORDER BY d.trade_date,d.ts_code LIMIT ?"; args.append(limit+1)
            rows = db.execute(sql,args).fetchall()
            result = [dict(values=json.loads(r["row_json"]), version_id=r["version_id"], partition_status=r["status"],
                           source_sha=r["source_sha"], availability=json.loads(r["manifest"]), **SAFE) for r in rows[:limit]]
            return dict(rows=result, count=len(result), has_more=len(rows)>limit, contract=CONTRACT,
                        as_of_version=as_of_version, selection="latest_explicitly_versioned_ex_post", **SAFE)

    def verify(self):
        with self.read() as db:
            require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLITE_INTEGRITY_FAILED")
            require(not db.execute("PRAGMA foreign_key_check").fetchall(), "FOREIGN_KEY_FAILED")
            attempts = {}
            for r in db.execute("SELECT * FROM attempts ORDER BY id"):
                require(r["metadata_sha"] == attempt_hash(r), "ATTEMPT_METADATA_TAMPERED")
                require(r["permission_source"] == PERMISSION_SOURCE and r["api"] in FIELDS and r["fields"] == FIELDS[r["api"]], "SOURCE_METADATA_TAMPERED")
                if r["response_sha"]:
                    raw = gzip.decompress(self.raw_path(r["id"]).read_bytes())
                    require(sha(raw) == r["response_sha"] and len(raw) == r["raw_bytes"], "RAW_HASH_MISMATCH")
                    if r["status"] in ("OK", "EMPTY", "TRUNCATION_SUSPECTED") or r["status"].startswith(REFRESH_REJECTED):
                        status, code, fields, rows = parse_response(raw)
                        require(status == "OK" and code == r["provider_code"] and len(rows) == r["row_count"], "RAW_ENVELOPE_MISMATCH")
                        clean, dup = validate(r["api"],json.loads(r["params"]),fields,rows)
                        require(sha(canonical(clean)) == r["canonical_sha"] and dup == r["duplicates"], "CANONICAL_HASH_MISMATCH")
                attempts[r["id"]] = r
            object_count, object_sources = 0, {}
            for r in db.execute("SELECT * FROM objects"):
                require(sha(r["row_json"].encode()) == r["row_sha"], "OBJECT_HASH_MISMATCH")
                a = attempts[r["attempt_id"]]
                if a["id"] not in object_sources:
                    raw = gzip.decompress(self.raw_path(a["id"]).read_bytes())
                    _,_,fields,rows = parse_response(raw)
                    clean,_ = validate(a["api"],json.loads(a["params"]),fields,rows)
                    object_sources[a["id"]] = {sha(canonical(x)) for x in clean}
                require(r["row_sha"] in object_sources[a["id"]], "OBJECT_SOURCE_MISMATCH")
                object_count += 1
            # Stream row versions; don't load millions of records in memory.
            row_count, null_pre_close = 0, 0
            cal = self.calendar(db)
            for r in db.execute("SELECT * FROM daily_rows"):
                data = json.loads(r["row_json"])
                require(sha(r["row_json"].encode()) == r["row_sha"], "ROW_HASH_MISMATCH")
                require(all(data[f] == r[f] for f in ("ts_code","trade_date","open","high","low","close","pre_close","vol","amount")), "NORMALIZED_ROW_MISMATCH")
                official = cal.get((exchange(r["ts_code"]),r["trade_date"]))
                require(official is None or official["is_open"]=="1", "DAILY_ON_CLOSED_EXCHANGE")
                null_pre_close += r["pre_close"] is None
                row_count += 1
            for v in db.execute("SELECT * FROM day_versions"):
                require(sha(v["manifest"].encode()) == v["source_sha"], "VERSION_SOURCE_TAMPERED")
                m = json.loads(v["manifest"])
                require(m["contract_sha"] == sha(canonical(CONTRACT)), "SOURCE_METADATA_TAMPERED")
                rows = db.execute("SELECT ts_code,row_sha FROM day_rows WHERE version_id=? ORDER BY ts_code", (v["id"],)).fetchall()
                require(len(rows) == v["row_count"] and sha(canonical([list(r) for r in rows])) == v["content_sha"], "PARTITION_HASH_MISMATCH")
                for a in m["attempts"]:
                    original = attempts[a["id"]]
                    require(a["metadata_sha"] == original["metadata_sha"] and a["response_sha"] == original["response_sha"]
                            and a["obtained_at"] == original["ended"], "VERSION_ATTEMPT_TAMPERED")
                # Reconstruct exactly what the source attempts published, including
                # partition recovery, so changing all normalized hashes cannot pass.
                reconstructed = {}
                for a in m["attempts"]:
                    original = attempts[a["id"]]
                    _,_,fields,rawrows = parse_response(gzip.decompress(self.raw_path(a["id"]).read_bytes()))
                    clean,_ = validate("daily",json.loads(original["params"]),fields,rawrows)
                    for r in clean:
                        reconstructed[r["ts_code"]] = sha(canonical(r))
                require(sorted(reconstructed.items()) == [tuple(r) for r in rows], "VERSION_RAW_ROW_MISMATCH")
            for r in db.execute("SELECT c.trade_date,v.trade_date FROM checkpoints c JOIN day_versions v ON v.id=c.version_id"):
                require(r[0] == r[1], "CHECKPOINT_DATE_MISMATCH")
            return dict(state="VERIFIED_STORAGE_ONLY", sqlite_integrity="ok", attempts=len(attempts),
                        object_rows=object_count, daily_row_versions=row_count,null_pre_close_row_versions=null_pre_close, **SAFE)


class Download:
    def __init__(self, warehouse, db, kind, start, end, transport, credential_source,
                 max_calls=25, total_cap=1600, rpm=10, min_free_bytes=1_073_741_824,
                 sleep=time.sleep, monotonic=time.monotonic, progress=None):
        historical_range(start,end)
        require(1 <= max_calls <= total_cap <= 10000, "INVALID_CALL_CAP")
        require(0 < rpm <= 30, "RATE_CAP_30_PER_MINUTE")
        self.w, self.db, self.start, self.end = warehouse, db, start, end
        self.transport, self.credential_source = transport, credential_source
        self.max_calls, self.total_cap, self.rpm = max_calls, total_cap, rpm
        self.min_free_bytes, self.sleep, self.monotonic = min_free_bytes, sleep, monotonic
        self.calls, self.last, self.stop_reason = 0, None, None
        self.progress = progress
        config = dict(start=start,end=end,max_calls=max_calls,total_cap=total_cap,rpm=rpm,
                      credential_source=credential_source,permission_source=PERMISSION_SOURCE,version=VERSION)
        with db:
            self.run = db.execute("INSERT INTO runs(kind,started,status,config,config_sha) VALUES(?,?,'RUNNING',?,?)",
                                  (kind,now(),canonical(config).decode(),sha(canonical(config)))).lastrowid

    def finish(self, status):
        with self.db:
            self.db.execute("UPDATE runs SET ended=?,status=? WHERE id=?", (now(),status,self.run))
        return dict(run_id=self.run,requests_this_run=self.calls,state=status,network_operation=True, **SAFE)

    def request(self, api, params):
        require(api in FIELDS, "UNAUTHORIZED_API")
        permission = self.w.permission(self.db,api)
        require(permission not in ("PERMISSION_DENIED","AUTH_DENIED"), permission)
        total = self.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        require(self.calls < self.max_calls and total < self.total_cap, "CALL_CAP_REACHED")
        require(shutil.disk_usage(self.w.root).free >= self.min_free_bytes, "INSUFFICIENT_DISK")
        # Persist throttling across processes/resume, not only within this instance.
        prior = self.db.execute("SELECT started,ended,status,retry_after FROM attempts ORDER BY id DESC LIMIT 1").fetchone()
        if prior:
            instant = dt.datetime.now(dt.timezone.utc)
            elapsed = (instant-dt.datetime.fromisoformat(prior["started"])).total_seconds()
            wait = max(0,60/self.rpm-elapsed)
            if prior["status"] == "RATE_LIMITED":
                seconds = int(prior["retry_after"]) if prior["retry_after"] else 60
                elapsed = (instant-dt.datetime.fromisoformat(prior["ended"])).total_seconds()
                wait = max(wait,seconds-elapsed)
            self.sleep(wait)
        with self.db:
            a = self.db.execute("""INSERT INTO attempts(run_id,api,params,fields,credential_source,permission_source,started,status,may_have_sent)
                                VALUES(?,?,?,?,?,?,?,'SENDING',1)""",
                                (self.run,api,canonical(params).decode(),FIELDS[api],self.credential_source,PERMISSION_SOURCE,now())).lastrowid
        self.calls += 1
        status, http, code, rows, fields, raw, retry_after = "NETWORK_OUTCOME_UNKNOWN",None,None,[],[],None,""
        clean, duplicates, canonical_sha = [],0,None
        try:
            http, raw, retry_after = self.transport(api,params,FIELDS[api])
            self.w.save_raw(a,raw)
            if http == 429:
                status = "RATE_LIMITED"
            elif http in (401,403):
                status = "AUTH_DENIED" if http == 401 else "PERMISSION_DENIED"
            elif http != 200:
                status = "HTTP_ERROR"
            elif not raw:
                status = "EMPTY_REMOTE_RESPONSE"
            else:
                status, code, fields, rows = parse_response(raw)
                if status == "OK":
                    clean,duplicates = validate(api,params,fields,rows)
                    canonical_sha = sha(canonical(clean))
                    status = "TRUNCATION_SUSPECTED" if len(rows) >= CAP else ("OK" if rows else "EMPTY")
        except WarehouseError as e:
            status = str(e)
        except (OSError,TimeoutError,urllib.error.URLError,http_client.HTTPException):
            status = "NETWORK_OUTCOME_UNKNOWN"
        with self.db:
            self.db.execute("""UPDATE attempts SET ended=?,status=?,http_status=?,provider_code=?,row_count=?,response_sha=?,raw_bytes=?,
                            canonical_sha=?,duplicates=?,retry_after=? WHERE id=?""",
                            (now(),status,http,code,len(rows) if raw is not None else None,sha(raw) if raw is not None else None,
                             len(raw) if raw is not None else None,canonical_sha,duplicates,str(retry_after)[:32] if str(retry_after).isdigit() else "",a))
            self.w.seal_attempt(self.db,a)
            if status in ("OK","EMPTY","TRUNCATION_SUSPECTED","PERMISSION_DENIED","AUTH_DENIED"):
                effective = "ALLOWED_OBSERVED" if status in ("OK","EMPTY","TRUNCATION_SUSPECTED") else status
                self.db.execute("INSERT INTO permissions VALUES(?,?,?) ON CONFLICT(api) DO UPDATE SET status=excluded.status,attempt_id=excluded.attempt_id", (api,effective,a))
        if status == "RATE_LIMITED":
            # Stop this run; explicit resume only, with persisted cooldown below.
            self.stop_reason = "RATE_LIMITED"
        return dict(id=a,status=status,rows=clean)

    def metadata(self):
        # First unknown permission is one narrow probe. A denial is persistent.
        for api in ("stock_basic","trade_cal"):
            if self.w.permission(self.db,api) in ("PERMISSION_DENIED","AUTH_DENIED"):
                continue
            if self.w.permission(self.db,api) == "UNVERIFIED":
                params = (dict(exchange="SSE",list_status="L",ts_code="600000.SH") if api == "stock_basic"
                          else dict(exchange="SSE",start_date=self.start,end_date=self.start))
                result = self.request(api,params)
                if result["status"] in ("PERMISSION_DENIED","AUTH_DENIED"):
                    continue
                require(result["status"] in ("OK","EMPTY"), result["status"])
                self.w.publish_objects(self.db,api,result["rows"],result["id"])
            if api == "stock_basic":
                combinations = [dict(exchange=e,list_status=s) for e in EXCHANGES for s in STATUSES]
            else:
                # BSE is not a documented trade_cal parameter. Preserve official
                # SSE/SZSE source instead of inventing independent BSE coverage.
                combinations = [dict(exchange=e,start_date=self.start,end_date=self.end) for e in ("SSE","SZSE")]
            for params in combinations:
                previous = self.db.execute("SELECT status FROM attempts WHERE api=? AND params=? ORDER BY id DESC LIMIT 1", (api,canonical(params).decode())).fetchone()
                if previous and previous[0] in ("OK","EMPTY"):
                    continue
                result = self.request(api,params)
                if result["status"] in ("PERMISSION_DENIED","AUTH_DENIED"):
                    break
                require(result["status"] in ("OK","EMPTY","TRUNCATION_SUSPECTED"), result["status"])
                self.w.publish_objects(self.db,api,result["rows"],result["id"])
                # catalog cap: retain evidence and declare gap. Cannot prove an
                # exhaustive ts_code partition without a historical master.

    def daily(self,date,refresh=False,fault=None):
        historical_range(date,date)
        checkpoint = self.db.execute("SELECT v.status FROM checkpoints c JOIN day_versions v ON v.id=c.version_id WHERE c.trade_date=?", (date,)).fetchone()
        if checkpoint and checkpoint[0] == "COMPLETE" and not refresh:
            return "SKIPPED_COMPLETE"
        cal = self.w.calendar(self.db)
        official = [r for (e,d),r in cal.items() if d==date]
        if official:
            require(any(r["is_open"]=="1" for r in official), "CALENDAR_CLOSED")
        result = self.request("daily",dict(trade_date=date))
        require(result["status"] in ("OK","EMPTY","TRUNCATION_SUSPECTED"),result["status"])
        attempts, rows = [result["id"]], result["rows"]
        for r in rows:
            market_calendar = cal.get((exchange(r["ts_code"]),date))
            require(market_calendar is None or market_calendar["is_open"]=="1", "DAILY_ON_CLOSED_EXCHANGE")
        state,reason = "COMPLETE","DATE_RESPONSE_BELOW_CAP"
        if not rows:
            state,reason = "PARTIAL","EMPTY_OPEN_DAY_UNVERIFIED"
        elif any(r.get("quality_flags") for r in rows):
            state,reason = "PARTIAL","SOURCE_FIELD_UNVERIFIED"
        if result["status"] == "TRUNCATION_SUSPECTED":
            state,reason = "PARTIAL","TRUNCATION_SUSPECTED"
            catalog = self.w.latest_objects(self.db,"stock_basic")
            codes = sorted({r["ts_code"] for r in catalog if r.get("list_date") and r["list_date"]<=date
                            and (not r.get("delist_date") or date<=r["delist_date"])} | {r["ts_code"] for r in rows})
            # Bounded ts_code partitions are the documented daily multi-code API.
            # Retain unknown codes from the capped response, never discard them.
            if codes:
                merged = {}
                for i in range(0,len(codes),200):
                    part = self.request("daily",dict(trade_date=date,ts_code=",".join(codes[i:i+200])))
                    require(part["status"] in ("OK","EMPTY"),part["status"])
                    attempts.append(part["id"])
                    for r in part["rows"]:
                        require(r["ts_code"] not in merged or merged[r["ts_code"]]==r,"PARTITION_CONFLICT")
                        merged[r["ts_code"]] = r
                require(all(r["ts_code"] in merged and merged[r["ts_code"]]==r for r in rows),"PARTITION_RESPONSE_CONFLICT")
                rows = sorted(merged.values(),key=canonical)
                # The Phase-1 current catalog cannot certify all past securities.
                # Partition result is usable but never claims exhaustive market.
                reason = "PARTITIONED_KNOWN_UNIVERSE_UNVERIFIED"
        publication=self.w.publish_day(self.db,date,rows,attempts,state,reason,fault=fault)
        return publication["status"]

    def preflight(self,samples=SAMPLES):
        self.metadata()
        if self.w.permission(self.db,"daily") in ("PERMISSION_DENIED","AUTH_DENIED"):
            return self.finish("BLOCKED_DAILY_PERMISSION")
        if self.w.permission(self.db,"daily") == "UNVERIFIED":
            probe = self.request("daily",dict(trade_date=self.start,ts_code="600000.SH"))
            if probe["status"] in ("PERMISSION_DENIED","AUTH_DENIED"):
                return self.finish("BLOCKED_DAILY_PERMISSION")
            require(probe["status"] in ("OK","EMPTY"),probe["status"])
        completed = 0
        for date in samples:
            if not self.start <= date <= self.end:
                continue
            try:
                state = self.daily(date)
                completed += state in ("COMPLETE","SKIPPED_COMPLETE")
            except WarehouseError as e:
                if str(e) in ("PERMISSION_DENIED","AUTH_DENIED"):
                    break
                raise
        return self.finish("PREFLIGHT_PASSED" if completed>=3 else "PARTIAL_PREFLIGHT")

    def backfill(self,refresh=False,retry_failed=False):
        require(self.db.execute("SELECT 1 FROM runs WHERE kind='preflight' AND status='PREFLIGHT_PASSED'").fetchone(), "PREFLIGHT_3_DATES_REQUIRED")
        require(self.w.permission(self.db,"daily")=="ALLOWED_OBSERVED","DAILY_PERMISSION_NOT_CONFIRMED")
        cal = self.w.calendar(self.db)
        available = {d for (e,d),r in cal.items() if r["is_open"]=="1" and self.start<=d<=self.end}
        require(bool(available),"OFFICIAL_CALENDAR_UNAVAILABLE")
        rejected_refresh=False
        # No weekday inference or hundreds of probes if calendar access is denied.
        for date in sorted(available):
            if not retry_failed:
                failed = self.db.execute("SELECT status FROM attempts WHERE api='daily' AND params=? ORDER BY id DESC LIMIT 1", (canonical(dict(trade_date=date)).decode(),)).fetchone()
                if failed and failed[0] not in ("OK","EMPTY","TRUNCATION_SUSPECTED"):
                    continue
            state = self.daily(date,refresh=refresh)
            rejected_refresh |= state=="PARTIAL_REFRESH_REJECTED"
            if self.progress and state != "SKIPPED_COMPLETE":
                self.progress(dict(trade_date=date,state=state,requests_this_run=self.calls,at_utc=now()))
        return self.finish("PARTIAL_REFRESH_REJECTED" if rejected_refresh else "BACKFILL_FINISHED")


def cli(argv=None):
    p=argparse.ArgumentParser(description="历史仓库 V1；仅显式 preflight/backfill/resume 联网，其他命令严格只读。")
    p.add_argument("action",choices=("plan","preflight","backfill","resume","verify","status","report","query"))
    p.add_argument("--store",default="main",help="独立 worktree 的 state/historical-warehouse 下的仓库名")
    p.add_argument("--start",default=START); p.add_argument("--end",default=END)
    p.add_argument("--max-calls",type=int,default=None); p.add_argument("--total-call-cap",type=int,default=None)
    p.add_argument("--rpm",type=float,default=10); p.add_argument("--min-free-mib",type=int,default=1024)
    p.add_argument("--credential-source",choices=("auto","existing-tushare-mcp-config"),default="auto",
                   help="auto: process env then existing Windows credential; optional explicit reuse of connected Tushare MCP account")
    p.add_argument("--retry-failed",action="store_true"); p.add_argument("--refresh",action="store_true")
    p.add_argument("--symbols",default=""); p.add_argument("--trade-date"); p.add_argument("--as-of-version",type=int)
    p.add_argument("--limit",type=int,default=100)
    args=p.parse_args(argv)
    require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",args.store)),"INVALID_STORE_NAME")
    historical_range(args.start,args.end)
    root=ROOT/"state"/"historical-warehouse"/args.store
    # Fixed private root, with no link escape into an old Observer or Agent store.
    require(root.resolve()==root.absolute(),"LINKED_WAREHOUSE_ROOT_DENIED")
    w=Warehouse(root)
    w.check_paths(descendants=True)
    if args.action in ("plan","status","report"):
        result=w.report(args.start,args.end)
        if args.action=="plan":
            result.update(default_rpm=10,hard_rpm_cap=30,default_total_call_cap=1600,
                          preflight_max_calls=32,network_operation=False,authorization=PERMISSION_SOURCE)
    elif args.action=="verify":
        result=w.verify()
    elif args.action=="query":
        result=w.query(args.start,args.end,tuple(filter(None,args.symbols.split(","))),args.trade_date,args.as_of_version,args.limit)
    else:
        estimate=w.report(args.start,args.end)
        total_cap=args.total_call_cap if args.total_call_cap is not None else (estimate.get("persisted_batch_total_call_cap") or
                  (1600 if args.action=="preflight" else (estimate.get("recommended_batch_total_call_cap") or 1600)))
        token,source=credential(args.credential_source)  # Before creating store/run/checkpoint; no token => zero requests.
        # HTTP credential is not exposed to report/query, SQLite, argv or stdout.
        with w.write() as db:
            require(args.min_free_mib>=64,"MIN_FREE_SPACE_TOO_SMALL")
            available_calls=max(1,total_cap-estimate.get("requests",0))
            max_calls=args.max_calls if args.max_calls is not None else (min(32,available_calls) if args.action=="preflight" else available_calls)
            if args.action!="preflight" and estimate.get("estimated_additional_disk_bytes") is not None:
                require(estimate["free_disk_bytes"]>=estimate["estimated_additional_disk_bytes"]+args.min_free_mib*1024**2,"INSUFFICIENT_ESTIMATED_DISK")
            download=Download(w,db,args.action,args.start,args.end,TushareHTTP(token),source,max_calls=max_calls,
                              total_cap=total_cap,rpm=args.rpm,min_free_bytes=args.min_free_mib*1024**2,
                              progress=lambda value:print(json.dumps(value,sort_keys=True),file=sys.stderr,flush=True))
            try:
                result=download.preflight() if args.action=="preflight" else download.backfill(args.refresh,args.retry_failed)
            except WarehouseError as e:
                result=download.finish(str(e))
        result["report"]=w.report(args.start,args.end)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
    if args.action in ("preflight","backfill","resume"):
        return 0 if result.get("state") in ("PREFLIGHT_PASSED","BACKFILL_FINISHED") else 2
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(cli())
    except WarehouseError as e:
        print(json.dumps(dict(state="BLOCKED",reason=str(e),**SAFE)),flush=True)
        raise SystemExit(2)
    except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):
        print(json.dumps(dict(state="BLOCKED",reason="LOCAL_IO_OR_SCHEMA_ERROR",**SAFE)),flush=True)
        raise SystemExit(2)
