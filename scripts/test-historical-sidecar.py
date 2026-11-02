"""Recorded HTTP through production parsing/storage/query; no live credentials."""
import contextlib
import datetime as dt
from decimal import Decimal
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("historical_sidecar",ROOT/"research/historical_sidecar.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
A,B = "20211101","20211224"
DAYS = h.v1.dates(A,B)
OPEN = [d for d in DAYS if h.v1.day(d).weekday()<5]
CODES = ("600000.SH","000001.SZ","920001.BJ","600001.SH")


def objects():
    return dict(stock_basic=[dict(ts_code=c,list_date="20200101",delist_date="20211201" if c==CODES[-1] else None) for c in CODES],
        trade_cal=[dict(exchange=e,cal_date=d,is_open="1" if d in OPEN else "0",pretrade_date=None) for e in ("SSE","SZSE") for d in DAYS])


def wire(api,rows,code=0,msg=""):
    fields = h.FIELDS[api].split(",")
    body = dict(code=code,msg=msg,data=dict(fields=fields,items=[[r.get(f) for f in fields] for r in rows]))
    # Decimal-bearing JSON literals exercise the real parse_float path.
    return json.dumps(body).replace('"-3.125"','-3.125').replace('"123.4567890123456789"','123.4567890123456789').encode()


def row(api,date,code):
    r = dict(ts_code=code,trade_date=date)
    if api=="adj_factor":
        r["adj_factor"] = "1.25"
    elif api=="suspend_d":
        r.update(suspend_type="S",suspend_timing="09:30-10:00")
    elif api=="stk_limit":
        r.update(pre_close="10",up_limit="11",down_limit="9",asset_type="STK",exchange={"SH":"SSE","SZ":"SZSE","BJ":"BSE"}[code[-2:]])
    else:
        r.update({f:None for f in h.FIELDS[api].split(",")[2:]})
        r.update(close="10",pe="-3.125",pe_ttm=None,pb="0",turnover_rate="1.25",total_share="123.4567890123456789",total_mv="125.75")
    return r


class Recorded:
    def __init__(self):
        self.calls=[]
        self.hook=None

    def __call__(self,api,params,fields):
        self.calls.append((api,dict(params)))
        if self.hook:
            reply=self.hook(api,params)
            if reply is not None:
                return reply
        codes=params.get("ts_code",",").split(",") if params.get("ts_code") else CODES
        rows=[row(api,params["trade_date"],c) for c in codes if c in CODES]
        if api=="suspend_d":
            for r in rows:
                r["suspend_type"]=params.get("suspend_type","S")
            # Legitimate zero-event days remain zero events, not tradability.
            if params["trade_date"]==OPEN[1]:
                rows=[]
        return 200,wire(api,rows),""


class Suite(unittest.TestCase):
    def setUp(self):
        parent=ROOT/"state"/"historical-sidecar-tests"
        parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent)
        self.root=Path(self.temp.name)/"warehouse"
        self.w=h.Sidecar(self.root)
        self.t=Recorded()
        with self.w.write() as db:
            self.w.install_metadata(db,objects(),dict(source="recorded_http_test_not_market_evidence"))

    def tearDown(self):
        self.temp.cleanup()

    def download(self,db,kind="preflight",**kw):
        return h.Download(self.w,db,kind,self.t,"recorded-http",A,B,sleep=lambda _:None,**kw)

    def preflight(self):
        with self.w.write() as db:
            result=self.download(db).preflight()
        self.assertEqual(result["state"],"PREFLIGHT_PASSED")

    def test_40_days_four_apis_decimal_null_units_and_queries(self):
        self.preflight()
        marks=[]
        with self.w.write() as db:
            r=self.download(db,"backfill",progress=marks.append).backfill()
        self.assertEqual(r["state"],"RANGE_COLLECTED_COVERAGE_PARTIAL")
        report=self.w.report(A,B)
        self.assertEqual(report["open_days"],40)
        self.assertTrue(all(r["blocked_or_unpublished_dates"]==0 for r in report["apis"].values()))
        self.assertEqual(report["apis"]["adj_factor"]["complete_dates"],40)
        self.assertEqual([m["percent"] for m in marks],[25,50,75,100])
        q=self.w.query("daily_basic",A,B,(CODES[0],),limit=100)
        self.assertEqual(len(q["rows"]),40)
        data=q["rows"][0]["data"]
        self.assertEqual(data["pe"],"-3.125")
        self.assertIsNone(data["pe_ttm"])
        self.assertEqual(data["pb"],"0")
        self.assertEqual(data["total_share"],"123.4567890123456789")
        self.assertEqual(h.CONTRACT["units"]["total_mv"],"10000_CNY")
        self.assertEqual(self.w.query("suspend_d",A,B,date=OPEN[1])["rows"],[])
        event_query=self.w.query("suspend_d",A,B,date=OPEN[1])
        self.assertEqual(len(event_query["partitions"]),1)
        self.assertEqual(event_query["missing_dates"],[])
        self.assertEqual(event_query["empty_event_interpretation"],"NO_REPORTED_EVENTS_NOT_TRADABILITY")
        self.assertEqual(self.w.verify()["state"],"VERIFIED_STORAGE_SOURCE_BINDING")

    def test_resume_complete_and_partial_dates_zero_requests(self):
        self.preflight()
        with self.w.write() as db:
            self.download(db,"backfill").backfill()
        before=len(self.t.calls)
        with self.w.write() as db:
            result=self.download(db,"resume").backfill()
        self.assertEqual(result["requests_this_run"],0)
        self.assertEqual(len(self.t.calls),before)

    def test_documented_caps_and_bounded_partitions(self):
        self.preflight()
        for api in h.FIELDS:
            if h.CAPS[api] is None:continue
            cap=h.CAPS[api]
            calls=[]
            def hook(a,p):
                if a==api and not p.get("ts_code"):
                    r=row(a,OPEN[2],CODES[0])
                    if a=="suspend_d":r["suspend_type"]=p["suspend_type"]
                    return 200,wire(a,[r]*cap),""
                calls.append(p)
            self.t.hook=hook
            with self.w.write() as db:
                state=self.download(db,"resume").collect(api,OPEN[2])
            self.assertEqual(state,"PARTIAL")
            self.assertTrue(any(p.get("ts_code") for p in calls))
        self.assertEqual(self.w.verify()["state"],"VERIFIED_STORAGE_SOURCE_BINDING")

    def test_refresh_revision_rollback_and_reduced_universe(self):
        self.preflight()
        old=self.w.query("daily_basic",A,B,date=OPEN[-1],limit=100)
        ceiling=max(r["version_id"] for r in old["rows"])
        def revision(api,p):
            if api=="daily_basic":
                rows=[row(api,p["trade_date"],c) for c in CODES]
                rows[0]["pe"]="-9"
                return 200,wire(api,rows),""
        self.t.hook=revision
        with self.w.write() as db:
            self.download(db,"resume").collect("daily_basic",OPEN[-1],True)
        self.assertEqual(self.w.query("daily_basic",A,B,date=OPEN[-1],as_of=ceiling)["query_sha"],old["query_sha"])
        current=self.w.query("daily_basic",A,B,date=OPEN[-1])
        self.t.hook=lambda api,p:(200,wire(api,[row(api,p["trade_date"],CODES[0])]),"") if api=="daily_basic" else None
        with self.w.write() as db:
            self.assertEqual(self.download(db,"resume").collect("daily_basic",OPEN[-1],True),"PARTIAL_REFRESH_REJECTED")
        self.assertEqual(self.w.query("daily_basic",A,B,date=OPEN[-1])["query_sha"],current["query_sha"])
        self.t.hook=None
        with self.w.write() as db:
            self.download(db,"resume").collect("daily_basic",OPEN[-1],True)
        self.assertEqual([r["data"] for r in old["rows"]],[r["data"] for r in self.w.query("daily_basic",A,B,date=OPEN[-1])["rows"]])
        self.w.verify()

    def test_capped_response_codes_outside_catalog_survive_multiple_partitions(self):
        self.preflight()
        codes=[str(600000+i)+".SH" for i in range(201)]
        parts=[]
        def capped(api,p):
            if api!="stk_limit":return None
            if p.get("ts_code"):
                parts.append(p["ts_code"].split(","))
                rows=[row(api,p["trade_date"],c) for c in codes if c in p["ts_code"].split(",")]
            else:
                rows=[row(api,p["trade_date"],codes[i%len(codes)]) for i in range(h.CAPS[api])]
            return 200,wire(api,rows),""
        self.t.hook=capped
        with self.w.write() as db:
            self.assertEqual(self.download(db,"resume").collect("stk_limit",OPEN[2]),"PARTIAL")
        q=self.w.query("stk_limit",A,B,date=OPEN[2],limit=300)
        self.assertEqual({r["data"]["ts_code"] for r in q["rows"]},set(codes))
        self.assertGreater(len(parts),1)
        self.assertTrue(all(len(p)<=200 for p in parts))
        self.w.verify()

    def test_unknown_429_quota_permission_and_no_blind_retry(self):
        self.preflight()
        for api,reply,expected in (
            ("adj_factor",TimeoutError(),"NETWORK_OUTCOME_UNKNOWN"),
            ("suspend_d",(429,b"{}","0"),"RATE_LIMITED"),
            ("stk_limit",(200,wire("stk_limit",[],code=-2001,msg="每天额度已用完"),"0"),"PARTIAL_QUOTA_LIMIT"),
            ("daily_basic",(200,wire("daily_basic",[],code=-2002,msg="积分权限不足"),""),"PERMISSION_DENIED")):
            def fail(a,p):
                if a==api:
                    if isinstance(reply,Exception):raise reply
                    return reply
            self.t.hook=fail
            with self.w.write() as db:
                d=self.download(db,"resume")
                result=d.request(api,dict(trade_date=OPEN[0]))
                self.assertEqual(result["status"],expected)
                d.finish(expected)
                if expected=="NETWORK_OUTCOME_UNKNOWN":
                    before=len(self.t.calls)
                    with self.assertRaisesRegex(h.Error,"REQUIRES_EXPLICIT_RETRY"):
                        d.successful_request(api,dict(trade_date=OPEN[0]))
                    self.assertEqual(len(self.t.calls),before)
        self.t.hook=None
        with self.w.write() as db:
            d=self.download(db,"resume")
            d.backfill()
            # Failed scopes weren't resent, and denied API isn't called again.
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE api='daily_basic' AND params=?",(h.canonical(dict(trade_date=OPEN[0])).decode(),)).fetchone()[0],1)

    def test_bad_types_scope_conflicts_non_a_and_suspend_intervals(self):
        for api in h.FIELDS:
            r=row(api,A,CODES[0])
            with self.assertRaises(h.Error):
                h.validate(api,dict(trade_date=OPEN[1]),h.FIELDS[api].split(","),[r])
        r=row("adj_factor",A,CODES[0]);r["adj_factor"]="0"
        with self.assertRaises(h.Error):h.validate("adj_factor",dict(trade_date=A),list(r),[r])
        r=row("daily_basic",A,CODES[0]);other=dict(r,pe="5")
        with self.assertRaisesRegex(h.Error,"CONFLICTING"):
            h.validate("daily_basic",dict(trade_date=A),list(r),[r,other])
        r=row("stk_limit",A,"900001.SH")
        clean,_=h.validate("stk_limit",dict(trade_date=A),list(r),[r])
        self.assertEqual(clean[0]["security_kind"],"B_SHARE_CODE_FAMILY")
        self.assertEqual(h.security_kind("510300.SH"),"NON_A_OR_IDENTITY_UNVERIFIED")
        r=row("stk_limit",A,"920001.BJ");r["exchange"]="SSE"
        clean,_=h.validate("stk_limit",dict(trade_date=A),list(r),[r])
        self.assertEqual(clean[0]["exchange"],"SSE")
        self.assertIn("PROVIDER_EXCHANGE_CODE_CONFLICT",clean[0]["quality_flags"])
        r=row("suspend_d",A,CODES[0]);r2=dict(r,suspend_timing="13:00-14:00")
        clean,_=h.validate("suspend_d",dict(trade_date=A),list(r),[r,r2])
        self.assertEqual(len(clean),2)

    def test_readonly_no_network_credentials_or_mtime(self):
        self.preflight()
        snapshot=lambda:{str(p.relative_to(self.root)):(p.stat().st_mtime_ns,h.sha(p.read_bytes())) for p in self.root.rglob("*") if p.is_file()}
        before=snapshot()
        with mock.patch.object(h.v1,"credential",side_effect=AssertionError("credential read")),mock.patch.object(h.v1.TushareHTTP,"__call__",side_effect=AssertionError("network")):
            self.w.report(A,B);self.w.query("daily_basic",A,B);self.w.verify()
        self.assertEqual(snapshot(),before)

    def test_foreign_sqlite_and_internal_links(self):
        path=Path(self.temp.name)/"foreign"
        path.mkdir()
        db=sqlite3.connect(path/"warehouse.sqlite")
        db.execute("CREATE TABLE private(value TEXT)");db.commit();db.close()
        before=(path/"warehouse.sqlite").read_bytes()
        with self.assertRaises(h.Error):
            with h.Sidecar(path).write():pass
        self.assertEqual((path/"warehouse.sqlite").read_bytes(),before)
        external=Path(self.temp.name)/"outside";external.mkdir()
        raw=self.root/"raw";raw.mkdir(exist_ok=True)
        link=raw/"escape"
        # Windows directory junction needs no developer-mode symlink privilege.
        if os.name=="nt":
            subprocess.run(["cmd","/c","mklink","/J",str(link),str(external)],capture_output=True,check=True)
        else:link.symlink_to(external,target_is_directory=True)
        try:
            with self.assertRaisesRegex(h.Error,"LINK_DENIED"):
                with self.w.write():pass
            with self.assertRaisesRegex(h.Error,"LINK_DENIED"):self.w.report(A,B)
        finally:
            if os.name=="nt":os.rmdir(link)
            else:link.unlink()

    def test_two_process_writer_and_crash_transaction(self):
        module=str(ROOT/"research/historical_sidecar.py")
        setup="import importlib.util,os; from pathlib import Path; s=importlib.util.spec_from_file_location('h',"+repr(module)+"); h=importlib.util.module_from_spec(s); s.loader.exec_module(h); w=h.Sidecar(Path("+repr(str(self.root))+")); "
        with self.w.write():
            result=subprocess.run([sys.executable,"-I","-B","-c",setup+"\nwith w.write():pass"],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b"WAREHOUSE_WRITER_BUSY",result.stderr)
        self.preflight()
        # Acquire real attempts before forcing the row transaction to die.
        with self.w.write() as db:
            d=self.download(db,"resume")
            result=d.request("daily_basic",dict(trade_date=OPEN[0]))
            d.finish("TEST_PREPARED")
        code=setup+"\nwith w.write() as db:\n a=db.execute(\"SELECT * FROM attempts WHERE id=?\",("+str(result["id"])+",)).fetchone(); raw=__import__('gzip').decompress(w.raw_path(a['id']).read_bytes()); _,_,f,r=h.parse(raw); rows,_=h.validate('daily_basic',{'trade_date':'"+OPEN[0]+"'},f,r); w.publish(db,'daily_basic','"+OPEN[0]+"',rows,[a['id']],'COMPLETE','RECORDED',lambda _:os._exit(73))"
        crashed=subprocess.run([sys.executable,"-I","-B","-c",code],capture_output=True)
        self.assertEqual(crashed.returncode,73,crashed.stderr)
        with self.w.write() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM checkpoints WHERE trade_date=?",(OPEN[0],)).fetchone()[0],0)
            state=self.download(db,"resume").collect("daily_basic",OPEN[0])
            self.assertEqual(state,"COMPLETE")
        self.w.verify()

    def test_budget_persists_and_cannot_auto_expand(self):
        with self.w.write() as db:
            d=self.download(db,total_cap=8,max_calls=1)
            d.request("adj_factor",dict(trade_date=A,ts_code=CODES[0]))
            with self.assertRaisesRegex(h.Error,"CALL_CAP_REACHED"):d.request("adj_factor",dict(trade_date=OPEN[1]))
            with self.assertRaisesRegex(h.Error,"PERSISTED_CAP"):self.download(db,total_cap=9)

    def test_frozen_anchor_join_uses_v1_readonly_and_ignores_later_revision(self):
        self.preflight()
        with self.w.write() as db:
            d=self.download(db,"resume")
            for date in OPEN[:20]:d.collect("adj_factor",date)
            d.finish("RECORDED")
            factor_version=db.execute("SELECT MAX(id) FROM versions").fetchone()[0]
        old_root=Path(self.temp.name)/"v1"
        old=h.v1.Warehouse(old_root)
        def daily_http(api,params,fields):
            fs=h.v1.DAILY_FIELDS.split(",")
            data=dict(ts_code=CODES[0],trade_date=params["trade_date"],open="10",high="11",low="9",close="10",pre_close="10",vol="1",amount="1")
            return 200,json.dumps(dict(code=0,data=dict(fields=fs,items=[[data.get(f) for f in fs]]))).encode(),""
        with old.write() as db:
            d=h.v1.Download(old,db,"preflight",A,B,daily_http,"recorded",max_calls=30,sleep=lambda _:None)
            for date in OPEN[:20]:d.daily(date)
            d.finish("RECORDED")
            daily_version=db.execute("SELECT MAX(id) FROM day_versions").fetchone()[0]
        snapshot=lambda:{str(p.relative_to(old_root)):(p.stat().st_mtime_ns,h.sha(p.read_bytes())) for p in old_root.rglob("*") if p.is_file()}
        before=snapshot()
        first=h.adjusted(self.w,old_root,CODES[0],OPEN[0],OPEN[19],OPEN[-1],factor_version,daily_version)
        self.assertEqual(len(first["rows"]),20)
        def revised(api,p):
            if api=="adj_factor" and p["trade_date"]==OPEN[-1]:
                rs=[dict(row(api,p["trade_date"],c),adj_factor="2.5") for c in CODES]
                return 200,wire(api,rs),""
        self.t.hook=revised
        with self.w.write() as db:
            self.download(db,"resume").collect("adj_factor",OPEN[-1],True)
            revised_version=db.execute("SELECT MAX(id) FROM versions").fetchone()[0]
        frozen=h.adjusted(self.w,old_root,CODES[0],OPEN[0],OPEN[19],OPEN[-1],factor_version,daily_version)
        changed=h.adjusted(self.w,old_root,CODES[0],OPEN[0],OPEN[19],OPEN[-1],revised_version,daily_version)
        self.assertEqual(first["query_sha"],frozen["query_sha"])
        self.assertNotEqual(first["query_sha"],changed["query_sha"])
        self.assertEqual(before,snapshot())

    def test_missing_optional_fields_cannot_reduce_admitted_view(self):
        self.preflight()
        old=self.w.query("daily_basic",A,B,date=OPEN[-1])
        def missing(api,p):
            if api=="daily_basic":
                fs=[f for f in h.FIELDS[api].split(",") if f!="pe"]
                rs=[row(api,p["trade_date"],c) for c in CODES]
                return 200,json.dumps(dict(code=0,data=dict(fields=fs,items=[[r.get(f) for f in fs] for r in rs]))).encode(),""
        self.t.hook=missing
        with self.w.write() as db:
            self.assertEqual(self.download(db,"resume").collect("daily_basic",OPEN[-1],True),"PARTIAL_REFRESH_REJECTED")
        self.assertEqual(old["query_sha"],self.w.query("daily_basic",A,B,date=OPEN[-1])["query_sha"])

    def test_readonly_cli_routes_and_checkpoint_source_scope(self):
        self.preflight()
        cli_root=Path(self.temp.name)/"state/historical-sidecar/main"
        shutil.copytree(self.root,cli_root)
        snapshot=lambda:{str(p.relative_to(cli_root)):(p.stat().st_mtime_ns,h.sha(p.read_bytes())) for p in cli_root.rglob("*") if p.is_file()}
        before=snapshot()
        with mock.patch.object(h,"ROOT",Path(self.temp.name)),mock.patch.object(h.v1,"credential",side_effect=AssertionError("credential read")),mock.patch.object(h.v1.TushareHTTP,"__call__",side_effect=AssertionError("network")):
            for action in ("plan","status","report","verify","query"):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(h.cli([action,"--start",A,"--end",B]),0)
        self.assertEqual(before,snapshot())
        with self.w.write() as db:
            factor_id=db.execute("SELECT version_id FROM checkpoints WHERE api='adj_factor'").fetchone()[0]
            db.execute("UPDATE checkpoints SET version_id=? WHERE api='daily_basic'",(factor_id,));db.commit()
        with self.assertRaisesRegex(h.Error,"CHECKPOINT_SCOPE"):self.w.verify()

    def test_quota_cooldown_refuses_waiting_day_or_new_call(self):
        self.preflight()
        self.t.hook=lambda api,p:(200,wire(api,[],code=-1,msg="每天总量上限"),"")
        with self.w.write() as db:
            d=self.download(db,"resume")
            self.assertEqual(d.request("daily_basic",dict(trade_date=A))["status"],"PARTIAL_QUOTA_LIMIT")
            before=len(self.t.calls)
            with self.assertRaisesRegex(h.Error,"QUOTA_COOLDOWN_ACTIVE"):d.request("daily_basic",dict(trade_date=OPEN[1]))
            self.assertEqual(before,len(self.t.calls))

    def test_slow_http_extends_timeout_preserving_fixed_transport_and_unknown_halt(self):
        client=h.TushareHTTP("synthetic-local-test-secret")
        class Response:
            code=200
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return wire("adj_factor",[])
        with mock.patch.object(client.opener.delegate,"open",return_value=Response()) as opened:
            http,body,_=client("adj_factor",dict(trade_date=A),h.FIELDS["adj_factor"])
            self.assertEqual(http,200)
            self.assertEqual(opened.call_args.kwargs["timeout"],120)
            self.assertEqual(opened.call_args.args[0].full_url,"https://api.tushare.pro")
        with self.w.write() as db,mock.patch.object(client.opener.delegate,"open",side_effect=TimeoutError()):
            d=self.download(db)
            d.transport=client
            result=d.request("adj_factor",dict(trade_date=A))
            self.assertEqual(result["status"],"NETWORK_OUTCOME_UNKNOWN")
            with self.assertRaisesRegex(h.Error,"REQUIRES_EXPLICIT_RETRY"):
                d.successful_request("adj_factor",dict(trade_date=A))

    def test_verify_cli_rejects_partition_quality_and_count_tampering_readonly(self):
        self.preflight()
        def conflicted(api,p):
            if api=="stk_limit":
                rows=[row(api,p["trade_date"],c) for c in CODES]
                rows[2]["exchange"]="SSE"
                return 200,wire(api,rows),""
        self.t.hook=conflicted
        with self.w.write() as db:
            self.download(db,"resume").collect("stk_limit",OPEN[2])
            # Frozen pre-fix factor manifest: keep its old labels, without a rule tag.
            version=db.execute("SELECT * FROM versions WHERE api='adj_factor'").fetchone()
            manifest=json.loads(version["manifest"]);manifest.pop("quality_rules",None)
            db.execute("UPDATE versions SET status='PARTIAL',reason=?,manifest=?,source_sha=? WHERE id=?",
                       ("TRUNCATION_OR_UNIVERSE_UNVERIFIED_UNDOCUMENTED_CAP",h.canonical(manifest).decode(),h.sha(h.canonical(manifest)),version["id"]));db.commit()
        self.w.verify()
        # A disposable checkout lets the actual CLI exercise its exit handling.
        checkout=Path(self.temp.name)/"cli"
        for name in ("research/historical_sidecar.py","research/historical_warehouse.py","scripts/historical-sidecar.py"):
            target=checkout/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        store=checkout/"state/historical-sidecar/main"
        shutil.copytree(self.root,store)
        fixture=h.Sidecar(store)
        with fixture.read() as db:
            versions=[dict(db.execute("SELECT * FROM versions WHERE api=? AND trade_date=?",(api,OPEN[2] if api=="stk_limit" else OPEN[-1])).fetchone()) for api in h.FIELDS]
        snapshot=lambda:{str(p.relative_to(store)):(p.stat().st_mtime_ns,h.sha(p.read_bytes())) for p in store.rglob("*") if p.is_file()}
        for version in versions:
            changes=dict(status="COMPLETE" if version["status"]=="PARTIAL" else "PARTIAL",
                         reason="TAMPERED_REASON",a_share_count=version["a_share_count"]+1,row_count=version["row_count"]+1)
            for column,value in changes.items():
                with self.subTest(api=version["api"],field=column):
                    with fixture.write() as db:
                        db.execute(f"UPDATE versions SET {column}=? WHERE id=?",(value,version["id"]));db.commit()
                    before=snapshot()
                    try:
                        result=subprocess.run([sys.executable,"-I","-B",str(checkout/"scripts/historical-sidecar.py"),"verify"],capture_output=True)
                        self.assertEqual(result.returncode,2,result.stdout.decode())
                        self.assertEqual(json.loads(result.stdout)["state"],"BLOCKED")
                        self.assertEqual(json.loads(result.stdout)["reason"],"PARTITION_QUALITY_MISMATCH" if column in ("status","reason") else "PARTITION_COUNT_MISMATCH")
                        self.assertEqual(snapshot(),before)
                    finally:
                        with fixture.write() as db:
                            db.execute(f"UPDATE versions SET {column}=? WHERE id=?",(version[column],version["id"]));db.commit()

    def test_adj_factor_documented_scope_has_no_invented_numeric_cap(self):
        for date,count in ((OPEN[2],1000),(OPEN[3],6000)):
            with self.subTest(rows=count):
                self.t.hook=lambda api,p:(200,wire(api,[row(api,p["trade_date"],str(600000+i)+".SH") for i in range(count)]),"")
                with self.w.write() as db:
                    d=self.download(db,"resume")
                    response=d.request("adj_factor",dict(trade_date=date))
                    self.assertEqual(response["status"],"OK")
                    self.assertEqual(d.collect("adj_factor",date),"COMPLETE")
                    self.assertEqual(d.calls,1)
                result=self.w.query("adj_factor",A,B,date=date,limit=10000)
                self.assertEqual(len(result["rows"]),count)
                self.assertEqual(result["partitions"][0]["reason"],"SOURCE_RESPONSE_COMPLETE_BY_DOCUMENTED_SCOPE")
                self.assertEqual(result["coverage"],"PARTIAL")
                self.assertEqual(result["historical_pit_status"],"NOT_VERIFIED")
                self.assertFalse(result["paper_allowed"] or result["live_allowed"])
        self.w.verify()


if __name__=="__main__":
    unittest.main(verbosity=2)
