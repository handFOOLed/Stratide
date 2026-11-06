"""Offline production-path E2E: no credentials, paid services or old state writes."""
import contextlib
import datetime as dt
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("historical_warehouse", ROOT / "research/historical_warehouse.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
A, B = "20211101", "20211119"
ALL_DAYS = h.dates(A,B)
OPEN = [d for d in ALL_DAYS if h.day(d).weekday()<5]
CODES = ("600000.SH","000001.SZ","920001.BJ")
SAMPLE = (OPEN[0],OPEN[6],OPEN[-1])


def wire(fields,rows,code=0,msg=""):
    data = dict(code=code,msg=msg,data=dict(fields=fields,items=[[r.get(f) for f in fields] for r in rows]))
    # Fake HTTP bytes contain JSON decimal numbers, not Python float arithmetic.
    raw=json.dumps(data,ensure_ascii=False,separators=(",",":"),default=str)
    for v in ("10.01","10.50","9.50","10.10","9.98","100.23","1000.123","10.20"):
        raw=raw.replace('"'+v+'"',v)
    return raw.encode()


def catalog():
    return [dict(ts_code=CODES[0],symbol="600000",name="existing",exchange="SSE",market="主板",list_status="L",list_date="19990101",delist_date=None),
            dict(ts_code=CODES[1],symbol="000001",name="delisted",exchange="SZSE",market="主板",list_status="D",list_date="19910101",delist_date="20211110"),
            dict(ts_code=CODES[2],symbol="920001",name="new",exchange="BSE",market="北交所",list_status="L",list_date="20211111",delist_date=None)]


def daily_rows(date):
    if date not in OPEN:
        return []
    return [dict(ts_code=r["ts_code"],trade_date=date,open="10.01",high="10.50",low="9.50",close="10.10",pre_close="9.98",
                 change="0.12",pct_chg="1.2024",vol="100.23",amount="1000.123") for r in catalog()
            if r["list_date"]<=date and (not r["delist_date"] or date<=r["delist_date"])]


class HTTP:
    def __init__(self):
        self.calls=[]
        self.denied=set()
        self.failure=None
        self.revision=False
        self.empty_dates=set()
        self.missing=False

    def __call__(self,api,params,fields):
        self.calls.append((api,dict(params)))
        if api in self.denied:
            return 200,wire([],[],code=2002,msg="抱歉，您没有接口访问权限，需要更多积分"),""
        if self.failure:
            error=self.failure
            self.failure=None
            if isinstance(error,Exception):
                raise error
            return error
        if api=="stock_basic":
            rows=[r for r in catalog() if r["exchange"]==params["exchange"] and r["list_status"]==params["list_status"]
                  and (not params.get("ts_code") or r["ts_code"]==params["ts_code"])]
        elif api=="trade_cal":
            rows=[]
            for d in h.dates(params["start_date"],params["end_date"]):
                prev=h.day(d)-dt.timedelta(days=1)
                while prev.weekday()>=5:
                    prev-=dt.timedelta(days=1)
                rows.append(dict(exchange=params["exchange"],cal_date=d,is_open=int(d in OPEN),pretrade_date=prev.strftime("%Y%m%d")))
        else:
            rows=daily_rows(params["trade_date"])
            if params.get("ts_code"):
                rows=[r for r in rows if r["ts_code"] in params["ts_code"].split(",")]
            if params["trade_date"] in self.empty_dates:
                rows=[]
            if self.missing:
                rows=[r for r in rows if r["ts_code"]!=CODES[0]]
            if self.revision:
                rows=[dict(r,close="10.20") for r in rows]
        return 200,wire(fields.split(","),rows),""


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="warehouse-",dir=TEST_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.w=h.Warehouse(Path(self.temp.name))
        self.http=HTTP()

    def run_download(self,kind="preflight",**kwargs):
        with self.w.write() as db:
            download=h.Download(self.w,db,kind,A,B,self.http,"offline-recorded-no-credential",sleep=lambda _:None,
                                min_free_bytes=0,max_calls=100,total_cap=1000,**kwargs)
            return download.preflight(SAMPLE) if kind=="preflight" else download.backfill()

    def test_01_full_15_session_three_security_lifecycles(self):
        self.assertEqual(self.run_download()["state"],"PREFLIGHT_PASSED")
        self.run_download("backfill")
        report=self.w.report(A,B)
        self.assertEqual(report["complete_dates"],15)
        self.assertEqual(report["row_count"],sum(len(daily_rows(d)) for d in OPEN))
        self.assertEqual(report["coverage"],"PARTIAL")
        self.assertEqual(report["per_exchange"]["BSE"]["calendar_coverage"],"PARTIAL")
        self.assertFalse(report["paper_allowed"])
        query=self.w.query(A,B,CODES,limit=100)
        self.assertEqual(query["rows"][0]["values"]["open"],"10.01")
        self.assertEqual(query["rows"][0]["values"]["amount"],"1000.123")
        self.assertIsNone(query["rows"][0]["historical_received_at"])
        self.assertEqual(self.w.verify()["sqlite_integrity"],"ok")
        self.assertEqual(self.w.query(A,B,trade_date=OPEN[0])["count"],2)
        before=len(self.http.calls)
        self.run_download("backfill")
        self.assertEqual(len(self.http.calls),before)
        self.assertEqual(self.w.report(A,B)["row_count"],report["row_count"])

    def test_02_decimal_ohlc_schema_and_units(self):
        raw=wire(h.DAILY_FIELDS.split(","),daily_rows(OPEN[0]))
        status,_,fields,rows=h.parse_response(raw)
        self.assertEqual(status,"OK")
        self.assertEqual(rows[0]["open"],"10.01")
        clean,_=h.validate("daily",dict(trade_date=OPEN[0]),fields,rows)
        self.assertEqual(h.exact_scaled(clean[0]["vol"],100),10023)
        self.assertEqual(h.exact_scaled(clean[0]["amount"],1000),1000123)
        for value in ("0.001","NaN","Infinity","-1"):
            with self.assertRaises(h.WarehouseError):
                h.exact_scaled(value,100)
        for mutation in (dict(high="1"),dict(open=10.01),dict(vol="NaN"),dict(amount="-1"),dict(ts_code="000001.SH"),dict(trade_date=OPEN[1])):
            with self.assertRaises(h.WarehouseError):
                h.validate("daily",dict(trade_date=OPEN[0]),fields,[dict(rows[0],**mutation)])
        with self.assertRaises(h.WarehouseError):
            h.validate("daily",dict(trade_date=OPEN[0]),[f for f in fields if f!="amount"],rows)
        with self.w.write() as db:
            changed=dict(h.CONTRACT,vol_unit="shares")
            db.execute("UPDATE meta SET contract=?,sha=?",(h.canonical(changed).decode(),h.sha(h.canonical(changed))));db.commit()
        with self.assertRaisesRegex(h.WarehouseError,"SOURCE_METADATA_TAMPERED"):
            self.w.verify()

    def test_03_missing_token_zero_requests_or_store_creation(self):
        with mock.patch.object(h,"credential",side_effect=h.WarehouseError("CREDENTIAL_UNAVAILABLE")),mock.patch.object(h,"TushareHTTP") as http:
            with self.assertRaisesRegex(h.WarehouseError,"CREDENTIAL_UNAVAILABLE"):
                h.cli(["preflight","--store","test-no-token"])
            http.assert_not_called()
        self.assertFalse((ROOT/"state/historical-warehouse/test-no-token").exists())

    def test_04_permission_denial_one_probe_then_persistently_skip(self):
        self.http.denied={"stock_basic","trade_cal","daily"}
        result=self.run_download()
        self.assertEqual(result["state"],"BLOCKED_DAILY_PERMISSION")
        self.assertEqual([a for a,p in self.http.calls],["stock_basic","trade_cal","daily"])
        self.run_download()
        self.assertEqual(len(self.http.calls),3)
        self.assertEqual(self.w.report(A,B)["complete_dates"],0)

    def test_05_total_and_run_caps_zero_unauthorized(self):
        with self.w.write() as db:
            with self.assertRaisesRegex(h.WarehouseError,"INVALID_CALL_CAP"):
                h.Download(self.w,db,"preflight",A,B,self.http,"offline",max_calls=0)
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",max_calls=1,total_cap=1,min_free_bytes=0,sleep=lambda _:None)
            with self.assertRaisesRegex(h.WarehouseError,"UNAUTHORIZED_API"):
                d.request("daily_basic",{})
            d.request("daily",dict(trade_date=OPEN[0]))
            with self.assertRaisesRegex(h.WarehouseError,"CALL_CAP_REACHED"):
                d.request("daily",dict(trade_date=OPEN[1]))
        self.assertEqual(len(self.http.calls),1)
        # A fresh CLI run without a cap flag must not recalculate a larger cap
        # after the previous batch exhausted its persisted total allowance.
        with mock.patch.object(h,"ROOT",self.w.root.parent),mock.patch.object(h,"Warehouse",return_value=self.w),mock.patch.object(h,"credential",return_value=("offline","offline")),mock.patch.object(h,"TushareHTTP",return_value=self.http),contextlib.redirect_stdout(__import__('io').StringIO()) as output:
            result=h.cli(["preflight","--start",A,"--end",B])
        self.assertEqual(result,2)
        self.assertEqual(json.loads(output.getvalue())["state"],"CALL_CAP_REACHED")
        self.assertEqual(len(self.http.calls),1)

    def test_06_timeout_unknown_and_explicit_resume(self):
        self.run_download()
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",max_calls=20,min_free_bytes=0,sleep=lambda _:None)
            self.http.failure=TimeoutError()
            with self.assertRaisesRegex(h.WarehouseError,"NETWORK_OUTCOME_UNKNOWN"):
                d.daily(OPEN[1])
            self.http.failure=h.http_client.IncompleteRead(b"partial-body")
            with self.assertRaisesRegex(h.WarehouseError,"NETWORK_OUTCOME_UNKNOWN"):
                d.daily(OPEN[2])
            d.finish("NETWORK_OUTCOME_UNKNOWN")
        self.assertEqual(self.w.report(A,B)["complete_dates"],3)
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",max_calls=20,min_free_bytes=0,sleep=lambda _:None)
            d.backfill(retry_failed=True)
        with self.w.read() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE status='NETWORK_OUTCOME_UNKNOWN'").fetchone()[0],2)
        self.assertEqual(self.w.report(A,B)["complete_dates"],15)

    def test_07_http_429_persisted_cooldown_and_no_internal_retry(self):
        sleeps=[]
        with self.w.write() as db:
            d=h.Download(self.w,db,"preflight",A,B,self.http,"offline",min_free_bytes=0,sleep=sleeps.append)
            self.http.failure=(429,b'{"code":429}',"60")
            result=d.request("daily",dict(trade_date=OPEN[0]))
            self.assertEqual(result["status"],"RATE_LIMITED")
            self.assertEqual(len(self.http.calls),1)
            d.finish("RATE_LIMITED")
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",min_free_bytes=0,sleep=sleeps.append)
            d.request("daily",dict(trade_date=OPEN[0]))
        self.assertTrue(any(s>=59 for s in sleeps),sleeps)

    def test_08_cap_partition_merge_keeps_partial_unknown_universe(self):
        self.run_download()
        original=self.http
        full=[dict(daily_rows(OPEN[1])[0],ts_code=f"{600000+i:06d}.SH") for i in range(256)]
        def capped(api,params,fields):
            if api!="daily":
                return original(api,params,fields)
            original.calls.append((api,dict(params)))
            rr=[r for r in full if r["ts_code"] in params["ts_code"].split(",")] if params.get("ts_code") else (full*24)[:6000]
            return 200,wire(fields.split(","),rr),""
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,capped,"offline",min_free_bytes=0,sleep=lambda _:None)
            self.assertEqual(d.daily(OPEN[1]),"PARTIAL")
        q=self.w.query(A,B,trade_date=OPEN[1],limit=10000)
        self.assertEqual(q["count"],256)
        self.assertEqual(q["rows"][0]["partition_status"],"PARTIAL")
        self.assertEqual(self.w.verify()["sqlite_integrity"],"ok")
        with self.w.read() as db:
            self.assertEqual(db.execute("SELECT duplicates FROM attempts WHERE status='TRUNCATION_SUSPECTED'").fetchone()[0],5744)
        self.assertEqual(sum(1 for api,p in original.calls if api=="daily" and p.get("ts_code") and p["trade_date"]==OPEN[1]),2)

    def test_09_empty_unknown_missing_not_filled(self):
        self.run_download()
        self.http.empty_dates.add(OPEN[1])
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",min_free_bytes=0,sleep=lambda _:None)
            self.assertEqual(d.daily(OPEN[1]),"PARTIAL")
            self.http.missing=True
            d.daily(OPEN[2])
        report=self.w.report(A,B)
        self.assertEqual(report["partial_dates"],1)
        self.assertGreater(report["missing_or_not_trading_unverified"],0)
        self.assertEqual(self.w.query(A,B,trade_date=OPEN[1])["count"],0)

    def test_10_same_day_revision_old_version_and_raw_survive(self):
        self.run_download()
        q=self.w.query(A,B,trade_date=OPEN[0])
        old_version=q["rows"][0]["version_id"]
        before={p.name:h.sha(p.read_bytes()) for p in (self.w.root/"raw").iterdir()}
        self.http.revision=True
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",min_free_bytes=0,sleep=lambda _:None)
            d.daily(OPEN[0],refresh=True)
        self.assertEqual(self.w.query(A,B,trade_date=OPEN[0])["rows"][0]["values"]["close"],"10.20")
        self.assertEqual(self.w.query(A,B,trade_date=OPEN[0],as_of_version=old_version)["rows"][0]["values"]["close"],"10.10")
        self.assertEqual(self.w.report(A,B)["source_revision_rows"],2)
        # A provider reverting to an earlier value is a new observation/version,
        # not a jump back to an old checkpoint that disagrees with latest query.
        self.http.revision=False
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",min_free_bytes=0,sleep=lambda _:None)
            d.daily(OPEN[0],refresh=True)
        reverted=self.w.query(A,B,trade_date=OPEN[0])
        self.assertEqual(reverted["rows"][0]["values"]["close"],"10.10")
        self.assertGreater(reverted["rows"][0]["version_id"],old_version)
        self.assertIsNotNone(reverted["rows"][0]["availability"]["revision_of_version"])
        with self.assertRaisesRegex(h.WarehouseError,"AS_OF_VERSION_NOT_FOUND"):
            self.w.query(A,B,as_of_version=1000000)
        for name,digest in before.items():
            self.assertEqual(h.sha((self.w.root/"raw"/name).read_bytes()),digest)
        self.w.verify()

    def test_11_conflicting_duplicate_and_bad_raw_no_checkpoint(self):
        with self.w.write() as db:
            def broken(api,params,fields):
                rows=daily_rows(OPEN[0]);rows.append(dict(rows[0],close="10.20"))
                return 200,wire(fields.split(","),rows),""
            d=h.Download(self.w,db,"preflight",A,B,broken,"offline",min_free_bytes=0)
            with self.assertRaisesRegex(h.WarehouseError,"CONFLICTING_DUPLICATE_ROW"):
                d.daily(OPEN[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0],0)
        self.assertEqual(len(list((self.w.root/"raw").glob("*.gz"))),1)

    def test_12_kill_mid_transaction_restart_and_no_false_complete(self):
        self.run_download()
        script="""import sys,os,importlib.util,json
from pathlib import Path
s=importlib.util.spec_from_file_location('t',sys.argv[1]);t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
w=t.h.Warehouse(Path(sys.argv[2]))
with w.write() as db:
 d=t.h.Download(w,db,'resume',t.A,t.B,t.HTTP(),'offline',min_free_bytes=0,sleep=lambda _:None)
 d.daily(t.OPEN[1],fault=lambda i:os._exit(73))
"""
        result=subprocess.run([sys.executable,"-I","-B","-c",script,str(Path(__file__).resolve()),str(self.w.root)],capture_output=True)
        self.assertEqual(result.returncode,73,result.stderr.decode())
        # Read-only refuses stale DB with live crash WAL; writer is the recovery path.
        with self.w.write() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0],3)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM day_rows WHERE trade_date=?",(OPEN[1],)).fetchone()[0],0)
        interrupted=self.w.report(A,B)
        self.assertEqual(interrupted["uncommitted_successful_dates"],1)
        self.assertEqual(interrupted["attempted_full_market_dates"],4)
        self.assertEqual(interrupted["unattempted_known_open_dates"],11)
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",max_calls=20,min_free_bytes=0,sleep=lambda _:None)
            d.backfill(retry_failed=True)
        self.assertEqual(self.w.report(A,B)["complete_dates"],15)
        self.w.verify()

    def test_13_two_processes_one_writer_before_any_network(self):
        child="""import sys,importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('h',sys.argv[1]);h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
try:
 with h.Warehouse(Path(sys.argv[2])).write(): print('UNEXPECTED_WRITER')
except h.WarehouseError as e: print(str(e));sys.exit(2)
"""
        with self.w.write():
            r=subprocess.run([sys.executable,"-I","-B","-c",child,str(ROOT/"research/historical_warehouse.py"),str(self.w.root)],capture_output=True,text=True)
            self.assertEqual(r.returncode,2,r.stdout+r.stderr)
            self.assertIn("WAREHOUSE_WRITER_BUSY",r.stdout)

    def test_14_read_only_commands_no_network_bytes_mtime_unchanged(self):
        self.run_download()
        before=fingerprint(self.w.root)
        with mock.patch.object(h,"TushareHTTP",side_effect=AssertionError("unexpected network")),mock.patch.object(h,"credential",side_effect=AssertionError("unexpected credential")):
            self.w.report(A,B);self.w.query(A,B);self.w.verify()
        self.assertEqual(fingerprint(self.w.root),before)
        self.assertFalse((self.w.root/"warehouse.sqlite-shm").exists())

    def test_15_attempt_metadata_and_raw_tampering_rejected(self):
        self.run_download()
        with self.w.write() as db:
            db.execute("UPDATE attempts SET params='{}' WHERE id=1");db.commit()
        with self.assertRaisesRegex(h.WarehouseError,"ATTEMPT_METADATA_TAMPERED"):
            self.w.verify()

    def test_16_insufficient_disk_and_unfinished_dates_zero_requests(self):
        with self.w.write() as db:
            d=h.Download(self.w,db,"preflight",A,B,self.http,"offline",min_free_bytes=10**30)
            with self.assertRaisesRegex(h.WarehouseError,"INSUFFICIENT_DISK"):
                d.request("daily",dict(trade_date=OPEN[0]))
            self.assertEqual(len(self.http.calls),0)
        with self.assertRaisesRegex(h.WarehouseError,"OUTSIDE_AUTHORIZED_COMPLETED_HISTORY"):
            h.historical_range(A,"20261102")

    def test_17_calendar_denied_no_weekday_inference_or_batch_requests(self):
        self.http.denied={"stock_basic","trade_cal"}
        self.run_download()
        before=len(self.http.calls)
        with self.w.write() as db:
            d=h.Download(self.w,db,"backfill",A,B,self.http,"offline",min_free_bytes=0)
            with self.assertRaisesRegex(h.WarehouseError,"OFFICIAL_CALENDAR_UNAVAILABLE"):
                d.backfill()
        self.assertEqual(len(self.http.calls),before)

    def test_18_real_catalog_legacy_t_code_and_b_shares_raw_preserved(self):
        # Regression from the first real SSE D response, without copying names
        # or raw market payload: this T code retired long before the window.
        rows=[dict(catalog()[0],ts_code="T600018.SH",symbol="T600018",list_status="D",delist_date="20061020"),
              dict(catalog()[0],ts_code="900001.SH",symbol="900001")]
        raw=wire(h.STOCK_FIELDS.split(","),rows)
        _,_,fields,parsed=h.parse_response(raw)
        clean,_=h.validate("stock_basic",dict(exchange="SSE",list_status="D"),fields,parsed)
        self.assertEqual(clean,[])
        self.assertEqual(len(h.parse_response(raw)[3]),2)
        alias=dict(catalog()[2],ts_code="874865.BJ",symbol="920085",list_status="UN",list_date=None)
        clean,_=h.validate("stock_basic",dict(exchange="BSE",list_status="UN"),h.STOCK_FIELDS.split(","),[alias])
        self.assertEqual(clean[0]["symbol"],"920085")

    def test_19_cli_readonly_all_commands_do_not_create_or_change_files(self):
        self.run_download()
        before=fingerprint(self.w.root)
        with mock.patch.object(h,"ROOT",self.w.root.parent),mock.patch.object(h,"Warehouse",return_value=self.w),mock.patch.object(h,"credential",side_effect=AssertionError("credential read")),mock.patch.object(h,"TushareHTTP",side_effect=AssertionError("network")),contextlib.redirect_stdout(__import__('io').StringIO()):
            for action in ("plan","status","report","verify","query"):
                self.assertEqual(h.cli([action,"--start",A,"--end",B]),0)
        self.assertEqual(fingerprint(self.w.root),before)

    def test_20_live_writer_fences_readonly_no_partial_snapshot(self):
        self.run_download()
        child="""import sys,importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('h',sys.argv[1]);h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
try: h.Warehouse(Path(sys.argv[2])).report('20211101','20211119')
except h.WarehouseError as e: print(str(e));sys.exit(2)
sys.exit(9)
"""
        with self.w.write():
            r=subprocess.run([sys.executable,"-I","-B","-c",child,str(ROOT/"research/historical_warehouse.py"),str(self.w.root)],capture_output=True,text=True)
            self.assertEqual(r.returncode,2,r.stdout+r.stderr)
            self.assertIn("WAREHOUSE_WRITER_BUSY",r.stdout)

    def test_21_provider_null_pre_close_is_flagged_not_fabricated(self):
        self.run_download()
        def null_previous(api,params,fields):
            rows=[dict(r,pre_close=None) for r in daily_rows(params["trade_date"])]
            return 200,wire(fields.split(","),rows),""
        with self.w.write() as db:
            d=h.Download(self.w,db,"resume",A,B,null_previous,"offline",min_free_bytes=0,sleep=lambda _:None)
            self.assertEqual(d.daily(OPEN[1]),"PARTIAL")
        q=self.w.query(A,B,trade_date=OPEN[1])
        self.assertIsNone(q["rows"][0]["values"]["pre_close"])
        self.assertIn("PRE_CLOSE_UNVERIFIED_NULL_FROM_PROVIDER",q["rows"][0]["values"]["quality_flags"])
        self.assertFalse(q["paper_allowed"])
        self.w.verify()

    def test_22_real_transport_secret_echo_never_enters_raw_or_sqlite(self):
        token="synthetic-issue57-transport-secret"
        class Response:
            code=200
            headers={}
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,size): return token.encode()
        opener=mock.Mock()
        opener.open.return_value=Response()
        with mock.patch.object(h.urllib.request,"build_opener",return_value=opener):
            transport=h.TushareHTTP(token)
            with self.w.write() as db:
                d=h.Download(self.w,db,"preflight",A,B,transport,"offline",min_free_bytes=0,sleep=lambda _:None)
                result=d.request("daily",dict(trade_date=OPEN[0]))
                self.assertEqual(result["status"],"SECRET_ECHO_REJECTED")
        self.assertFalse(list((self.w.root/"raw").glob("*.gz")))
        self.assertNotIn(token.encode(),self.w.path.read_bytes())
        req=opener.open.call_args[0][0]
        self.assertEqual(req.full_url,"https://api.tushare.pro")
        self.assertEqual(json.loads(req.data)["token"],token)
        with self.assertRaisesRegex(h.WarehouseError,"AUTHENTICATED_REDIRECT_DENIED"):
            h.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_23_cli_failed_validation_has_nonzero_exit(self):
        self.http.failure=(200,b'{"code":0,"data":{"fields":[],"items":[[1]]}}',"")
        with mock.patch.object(h,"ROOT",self.w.root.parent),mock.patch.object(h,"Warehouse",return_value=self.w),mock.patch.object(h,"credential",return_value=("offline-synthetic","offline")),mock.patch.object(h,"TushareHTTP",return_value=self.http),contextlib.redirect_stdout(__import__('io').StringIO()) as output:
            result=h.cli(["preflight","--start",A,"--end",B])
        self.assertEqual(result,2)
        self.assertEqual(json.loads(output.getvalue())["state"],"INVALID_ROW_SHAPE")

    def test_24_bar_must_match_its_own_exchange_calendar(self):
        self.run_download()
        with self.w.write() as db:
            # Recorded transport supplies a conflicting SSE/SZSE holiday. A
            # market-wide union of open dates must not authorize the SSE row.
            row=dict(exchange="SSE",cal_date=OPEN[1],is_open="0",pretrade_date=OPEN[0])
            d=h.Download(self.w,db,"resume",A,B,self.http,"offline",min_free_bytes=0,sleep=lambda _:None)
            # Keep production source binding in a separate synthetic response.
            def calendar_response(api,params,fields): return 200,wire(fields.split(","),[row]),""
            d.transport=calendar_response
            a=d.request("trade_cal",dict(exchange="SSE",start_date=OPEN[1],end_date=OPEN[1]))
            self.w.publish_objects(db,"trade_cal",a["rows"],a["id"])
            d.transport=self.http
            with self.assertRaisesRegex(h.WarehouseError,"DAILY_ON_CLOSED_EXCHANGE"):
                d.daily(OPEN[1])
            self.assertFalse(db.execute("SELECT 1 FROM checkpoints WHERE trade_date=?",(OPEN[1],)).fetchone())

    def test_25_incomplete_refresh_keeps_complete_view_and_asof(self):
        for mode in ("empty","null","missing","truncated"):
            with self.subTest(refresh=mode):
                self.w=h.Warehouse(Path(self.temp.name)/mode)
                self.http=HTTP()
                self.run_download()
                before=self.w.query(A,B,trade_date=OPEN[0])
                original_version=before["rows"][0]["version_id"]
                frozen=self.w.query(A,B,trade_date=OPEN[0],as_of_version=original_version)
                before_sha=h.sha(h.canonical(before))
                raw_before={p.name:h.sha(p.read_bytes()) for p in (self.w.root/"raw").iterdir()}
                original=self.http
                def incomplete(api,params,fields):
                    if api!="daily":return original(api,params,fields)
                    original.calls.append((api,dict(params)))
                    rows=daily_rows(params["trade_date"])
                    if mode=="empty":rows=[]
                    elif mode=="null":rows=[dict(r,pre_close=None) for r in rows]
                    elif mode=="missing":rows=rows[:1]
                    elif not params.get("ts_code"):rows=(rows*3000)[:6000]
                    return 200,wire(fields.split(","),rows),""
                with self.w.write() as db:
                    d=h.Download(self.w,db,"resume",A,B,incomplete,"offline",min_free_bytes=0,sleep=lambda _:None)
                    state=d.daily(OPEN[0],refresh=True)
                    d.finish("BACKFILL_FINISHED")
                after=self.w.query(A,B,trade_date=OPEN[0])
                self.assertEqual(h.sha(h.canonical(after)),before_sha,"incomplete refresh degraded the admitted view")
                self.assertEqual(state,"PARTIAL_REFRESH_REJECTED")
                self.assertEqual(self.w.query(A,B,trade_date=OPEN[0],as_of_version=original_version),frozen)
                report=self.w.report(A,B)
                self.assertEqual(report["complete_dates"],3)
                self.assertEqual(report["versions"],3)
                self.assertGreater(report["rejected_refresh_attempts"],0)
                with self.w.read() as db:
                    rejected=db.execute("SELECT * FROM attempts WHERE status LIKE 'PARTIAL_REFRESH_REJECTED_%'").fetchall()
                    self.assertTrue(rejected)
                    for attempt in rejected:
                        self.assertEqual(attempt["metadata_sha"],h.attempt_hash(attempt))
                        self.assertTrue(self.w.raw_path(attempt["id"]).is_file())
                for name,digest in raw_before.items():self.assertEqual(h.sha((self.w.root/"raw"/name).read_bytes()),digest)
                # A later full valid revision is still admitted atomically.
                self.http=HTTP();self.http.revision=True
                with self.w.write() as db:
                    d=h.Download(self.w,db,"resume",A,B,self.http,"offline",min_free_bytes=0,sleep=lambda _:None)
                    self.assertEqual(d.daily(OPEN[0],refresh=True),"COMPLETE")
                revised=self.w.query(A,B,trade_date=OPEN[0])
                self.assertEqual(revised["count"],2)
                self.assertEqual(revised["rows"][0]["values"]["close"],"10.20")
                self.assertGreater(revised["rows"][0]["version_id"],original_version)
                self.assertEqual(self.w.query(A,B,trade_date=OPEN[0],as_of_version=original_version),frozen)
                self.w.verify()

    def synthetic_old_store(self,name):
        folder=Path(self.temp.name)/name
        folder.mkdir(parents=True)
        db=sqlite3.connect(folder/"observer.sqlite")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA user_version=1041")
        db.execute("CREATE TABLE old_evidence(value TEXT)")
        db.execute("INSERT INTO old_evidence VALUES('synthetic-preserve-me')")
        db.commit();db.close()
        (folder/"sentinel.txt").write_text("synthetic-only",encoding="utf-8")
        return folder

    def file_link(self,source,link):
        self.assertTrue(source.resolve().is_relative_to(TEST_ROOT.resolve()))
        self.assertTrue(link.absolute().is_relative_to(TEST_ROOT.resolve()))
        try:os.symlink(source,link)
        except OSError as e:
            if os.name=="nt" and e.winerror==1314:
                self.skipTest("Windows SeCreateSymbolicLinkPrivilege unavailable (1314); requires privileged rerun")
            raise
        self.addCleanup(lambda:link.unlink() if link.is_symlink() else None)

    def test_26_sqlite_symlink_rejected_before_foreign_journal_change(self):
        old=self.synthetic_old_store("old-file-link")
        w=h.Warehouse(Path(self.temp.name)/"linked-db")
        w.root.mkdir()
        self.file_link(old/"observer.sqlite",w.path)
        before=fingerprint(old)
        reason="NO_REJECTION"
        try:
            with w.write():pass
        except h.WarehouseError as e:reason=str(e)
        self.assertEqual(fingerprint(old),before,"foreign SQLite changed before schema rejection")
        self.assertEqual(reason,"WAREHOUSE_LINK_DENIED")

    def assert_cli_link_rejected(self,project,old):
        before=fingerprint(old)
        real_connect=h.sqlite3.connect
        real_download=h.Download
        def fast_download(*args,**kwargs):
            kwargs["sleep"]=lambda _:None
            return real_download(*args,**kwargs)
        for action in ("preflight","backfill","resume"):
            with self.subTest(action=action),mock.patch.object(h,"ROOT",project),mock.patch.object(h,"credential",return_value=("offline","offline")) as cred,mock.patch.object(h,"TushareHTTP",return_value=self.http) as transport,mock.patch.object(h.sqlite3,"connect",wraps=real_connect) as connect,mock.patch.object(h,"Download",side_effect=fast_download),contextlib.redirect_stdout(__import__('io').StringIO()):
                reason="NO_REJECTION"
                try:h.cli([action,"--start",A,"--end",B])
                except h.WarehouseError as e:reason=str(e)
                except (sqlite3.Error,OSError) as e:reason=type(e).__name__
                self.assertEqual(reason,"WAREHOUSE_LINK_DENIED",f"{action}: connects={connect.call_count}, credential_reads={cred.call_count}, transport_builds={transport.call_count}, old_changed={fingerprint(old)!=before}")
                self.assertEqual(connect.call_count,0)
                cred.assert_not_called();transport.assert_not_called()
                self.assertEqual(fingerprint(old),before)

    def test_27_cli_internal_file_links_rejected_before_any_io(self):
        old=self.synthetic_old_store("old-cli-links")
        for i,name in enumerate(("warehouse.sqlite","writer.lock","warehouse.sqlite-wal","warehouse.sqlite-shm","warehouse.sqlite-journal","raw/00000001.json.gz","raw/00000001.json.pending")):
            project=Path(self.temp.name)/f"cli-link-{i}"
            store=project/"state/historical-warehouse/main"
            link=store/name;link.parent.mkdir(parents=True)
            self.file_link(old/"observer.sqlite",link)
            self.assert_cli_link_rejected(project,old)

    @unittest.skipUnless(os.name=="nt","native Windows junction test")
    def test_28_windows_raw_junction_rejected_before_any_io(self):
        old=self.synthetic_old_store("old-junction-target")
        project=Path(self.temp.name)/"cli-junction"
        store=project/"state/historical-warehouse/main"
        store.mkdir(parents=True)
        link=store/"raw"
        # All paths are freshly created beneath this test's workspace temp dir.
        self.assertTrue(old.resolve().is_relative_to(TEST_ROOT.resolve()))
        self.assertTrue(store.resolve().is_relative_to(TEST_ROOT.resolve()))
        result=subprocess.run(["cmd","/c","mklink","/J",str(link),str(old)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
        self.addCleanup(lambda:link.rmdir() if link.is_junction() else None)
        self.assertTrue(link.is_junction())
        self.assert_cli_link_rejected(project,old)

    def test_29_foreign_regular_database_rejected_without_wal_mutation(self):
        old=self.synthetic_old_store("old-regular")
        w=h.Warehouse(old)
        (old/"observer.sqlite").rename(w.path)
        before=fingerprint(old)
        with self.assertRaises(h.WarehouseError):
            with w.write():pass
        self.assertEqual(fingerprint(old),{**before,"writer.lock":fingerprint(old)["writer.lock"]})
        with contextlib.closing(sqlite3.connect(w.path)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0],"delete")

    def test_30_cli_refresh_reports_rejection_without_losing_current_data(self):
        self.run_download()
        before=self.w.query(A,B,trade_date=A)
        self.http.empty_dates.add(A)
        real_download=h.Download
        def fast_download(*args,**kwargs):
            kwargs["sleep"]=lambda _:None
            return real_download(*args,**kwargs)
        with mock.patch.object(h,"ROOT",self.w.root.parent),mock.patch.object(h,"Warehouse",return_value=self.w),mock.patch.object(h,"credential",return_value=("offline","offline")),mock.patch.object(h,"TushareHTTP",return_value=self.http),mock.patch.object(h,"Download",side_effect=fast_download),contextlib.redirect_stdout(__import__('io').StringIO()) as output,contextlib.redirect_stderr(__import__('io').StringIO()):
            result=h.cli(["backfill","--start",A,"--end",A,"--refresh","--max-calls","1","--total-call-cap","1000"])
        self.assertEqual(result,2)
        payload=json.loads(output.getvalue())
        self.assertEqual(payload["state"],"PARTIAL_REFRESH_REJECTED")
        self.assertEqual(payload["report"]["complete_dates"],1)
        self.assertEqual(payload["report"]["rejected_refresh_attempts"],1)
        self.assertEqual(self.w.query(A,B,trade_date=A),before)


class IdleWalCheckpoint(unittest.TestCase):
    def test_checkpoint_if_idle_truncates_a_leftover_wal(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            warehouse = h.Warehouse(root)
            (root / "writer.lock").write_bytes(b"0")
            db = sqlite3.connect(warehouse.path)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("CREATE TABLE probe(x INTEGER)")
            db.execute("INSERT INTO probe VALUES (1)")
            db.commit()
            wal = Path(str(warehouse.path) + "-wal")
            self.assertGreater(wal.stat().st_size, 0)
            warehouse.checkpoint_if_idle()
            self.assertEqual(wal.stat().st_size, 0)
            self.assertEqual(db.execute("SELECT x FROM probe").fetchone()[0], 1)
            db.close()

    def test_checkpoint_if_idle_does_not_create_a_database(self):
        with tempfile.TemporaryDirectory() as raw:
            warehouse = h.Warehouse(Path(raw))
            warehouse.checkpoint_if_idle()
            self.assertFalse(warehouse.path.exists())

    def test_checkpoint_if_idle_reports_a_busy_lock(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            warehouse = h.Warehouse(root)
            (root / "writer.lock").write_bytes(b"0")
            db = sqlite3.connect(warehouse.path)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("CREATE TABLE probe(x INTEGER)")
            db.execute("INSERT INTO probe VALUES (1)")
            db.commit()
            with h.writer_lock(root):
                with self.assertRaises(h.WarehouseError) as caught:
                    warehouse.checkpoint_if_idle()
            self.assertEqual(str(caught.exception), "WAREHOUSE_WRITER_BUSY")
            db.close()


def fingerprint(root):
    return {str(p.relative_to(root)):(p.stat().st_size,p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest())
            for p in root.rglob("*") if p.is_file()}


TEST_ROOT=ROOT/"state"/"historical-warehouse-tests"
if __name__=="__main__":
    TEST_ROOT.mkdir(parents=True,exist_ok=True)
    unittest.main(verbosity=2)
