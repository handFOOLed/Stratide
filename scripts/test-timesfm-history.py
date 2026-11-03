"""Offline regression; recorded fixtures are not a real-market/model acceptance."""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research/timesfm_cpu"))
import cli, history as h, model, runtime
v1,v2=h.v1,h.v2
spec=importlib.util.spec_from_file_location("cpu_fixture",ROOT/"scripts/test-timesfm-cpu.py")
fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
A,B="20211101","20220930"
ALL=list(v1.dates(A,B)); DAYS=[d for d in ALL if v1.day(d).weekday()<5]
CODES=["600000.SH","000001.SZ","600519.SH","600001.SH","600002.SH","600003.SH","600004.SH","600005.SH"]
CUTOFF=DAYS[83]
ASOF=h.iso(CUTOFF)+"T08:00:00Z"

class Recorded:
    factor_day=None
    suspend_day=None
    def __call__(self,api,p,fields):
        if api=="stock_basic":
            rows=[dict(ts_code=c,symbol=c[:6],name="recorded",exchange=e,market="main",list_status="L",
                       list_date="20000101",delist_date=None) for c in CODES
                  if (e:=("SSE" if c.endswith(".SH") else "SZSE"))==p["exchange"]
                  and p["list_status"]=="L" and (not p.get("ts_code") or p["ts_code"]==c)]
        elif api=="trade_cal":
            rows=[dict(exchange=p["exchange"],cal_date=d,is_open=int(d in DAYS),pretrade_date=None)
                  for d in v1.dates(p["start_date"],p["end_date"])]
        elif api=="daily":
            d=p["trade_date"]; i=DAYS.index(d)
            rows=[dict(ts_code=c,trade_date=d,open=str(10+i/100),high="20",low="9",
                       close=f"{10+i/100:.2f}",pre_close=f"{10+(i-1)/100:.2f}",vol="100",amount="100")
                  for c in CODES]
        elif api=="adj_factor":
            rows=[dict(ts_code=c,trade_date=p["trade_date"],adj_factor="2" if p["trade_date"]==self.factor_day else "1")
                  for c in CODES]
        else:
            rows=[dict(ts_code=CODES[0],trade_date=p["trade_date"],suspend_type="S",suspend_timing=None)] if p["trade_date"]==self.suspend_day and p["suspend_type"]=="S" else []
        fs=fields.split(",")
        return 200,json.dumps(dict(code=0,msg="",data=dict(fields=fs,items=[[x.get(f) for f in fs] for x in rows]))).encode(),""

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert cli.common_root()==ROOT,"Disposable standalone checkout required"
        (ROOT/"state").mkdir(exist_ok=True)
        cls.owner=ROOT/"state/history-test-owner"
        commands=[]
        if not cls.owner.exists():
            commands.append([str(ROOT/"target/debug/stratided"),"--agent-init-fake",str(cls.owner)])
        commands.append([str(ROOT/"target/debug/risk-portfolio-agent"),"init","--agent-dir",str(cls.owner)])
        for args in commands:
            q=subprocess.run(args,cwd=ROOT,capture_output=True); assert q.returncode==0,q.stdout
        cls.desc=cli.bridge("descriptor")
        cls.manifest={"fixture":"NO_REAL_MODEL"}
        cls.tag="hist-"+os.urandom(4).hex()
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT/"state")
        cls.w=v1.Warehouse(Path(cls.temp.name)/"v1")
        cls.s=v2.Sidecar(Path(cls.temp.name)/"v2")
        cls.t=Recorded()
        with cls.w.write() as db:
            d=v1.Download(cls.w,db,"fixture",A,B,cls.t,"recorded",max_calls=1000,total_cap=1000,min_free_bytes=0,sleep=lambda _:None)
            d.metadata()
            for day in DAYS:d.daily(day)
            d.finish("DONE")
        with cls.s.write() as db:
            cls.s.import_v1(db,cls.w.root)
            d=v2.Download(cls.s,db,"fixture",cls.t,"recorded",A,B,total_cap=1000,sleep=lambda _:None)
            for day in DAYS:
                for api in ("adj_factor","suspend_d"):d.collect(api,day)
            d.finish("DONE")

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def plan(self):
        f,hist=h.read(self.desc,self.w.root,self.s.root,CODES,ASOF)
        return dict(batch=self.tag+"-"+self._testMethodName.split("_")[1],frozen=f,history=hist,
                    manifest_sha256=model.digest(self.manifest),code_sha256=self.desc["code_sha256"],
                    max_context=256,batch_size=1,threads=2)

    def save(self,p):
        path=cli.batch_path(p["batch"]); path.mkdir(parents=True,exist_ok=True)
        (path/"plan.json").write_text(json.dumps(p))

    def test_01_local_task_persist_decode_and_egress(self):
        cli.bridge("enable")
        p=self.plan(); self.save(p)
        request=json.loads(cli.bridge("project",p)["worker_request_json"])
        self.assertEqual(request["input_mode"],h.MODE)
        model.validate_request(request)
        with patch.object(cli,"verify_model",return_value=self.manifest),patch.object(runtime,"command",return_value=[]):
            result=cli.once(p["batch"],fixture.fixture_response)
            self.assertEqual(result["state"],"completed")
            again=cli.once(p["batch"],lambda _:self.fail("Duplicate inference"))
            self.assertEqual(result,again)
        bundle=result["result"]["research"]["risk_portfolio"]
        self.assertEqual(bundle["historical_research"]["historical_pit_status"],"NOT_VERIFIED")
        self.assertFalse(bundle["paper_allowed"] or bundle["live_allowed"] or bundle["can_execute_forward_paper"])
        cli.bridge("verify-result",result["result"])
        with patch.object(cli,"verify_model",return_value=self.manifest):
            saved=h.archive(p["batch"])
            self.assertEqual(h.archived(p["batch"]),saved)
            self.assertEqual(h.archive(p["batch"]),saved)
        bad=copy.deepcopy(result["result"]); bad["attempt"]=2
        with self.assertRaisesRegex(model.Rejected,"LOCAL_RESULT_SHA"):cli.bridge("verify-result",bad)
        q=subprocess.run([str(ROOT/"target/debug/local-fusion-agent"),"preflight",p["batch"]],capture_output=True,cwd=ROOT)
        self.assertEqual(json.loads(q.stdout)["error_code"],"REAL_MARKET_DATA_EGRESS_DENIED")
        with sqlite3.connect(self.owner/"agent.sqlite") as db:
            self.assertEqual(db.execute("select count(*) from calls").fetchone()[0],0)
            self.assertEqual(db.execute("select count(*) from tasks where trigger_key=?",
                             ("timesfm-cpu-v1:"+p["batch"],)).fetchone()[0],1)
        p["history"]["payload"]["as_of"]="2000-01-01T00:00:00Z"
        with self.assertRaises(model.Rejected):cli.bridge("project",p)

    def test_02_future_prices_factors_do_not_change_prefix(self):
        before=self.plan()
        # Accepted future revisions exercise actual version selection and read-only queries.
        with self.w.write() as db:
            d=v1.Download(self.w,db,"future",A,B,self.t,"recorded",max_calls=10,total_cap=1000,min_free_bytes=0,sleep=lambda _:None)
            result=d.request("daily",dict(trade_date=DAYS[-1]))
            rows=[dict(x,close="12.00",high="20") for x in result["rows"]]
            self.w.publish_day(db,DAYS[-1],rows,[result["id"]],"COMPLETE","RECORDED_FUTURE_MUTATION")
            d.finish("DONE")
        self.t.factor_day=DAYS[-1]
        with self.s.write() as db:
            d=v2.Download(self.s,db,"future",self.t,"recorded",A,B,sleep=lambda _:None)
            d.collect("adj_factor",DAYS[-1],refresh=True); d.finish("DONE")
        self.t.factor_day=None
        after=self.plan()
        self.assertEqual(before,after)
        self.assertEqual(cli.bridge("project",before),cli.bridge("project",after))

    def test_03_hash_pit_adjustment_and_identity_rejections(self):
        p=self.plan()
        for edit in (lambda x:x["history"]["payload"].update(historical_pit_status="VERIFIED"),
                     lambda x:x["history"]["payload"].update(adjustment="qfq"),
                     lambda x:x["frozen"]["series"][0]["observations"][-1].update(close_fen=1234567),
                     lambda x:x["frozen"].update(as_of="2022-02-28T08:00:00Z")):
            bad=copy.deepcopy(p);edit(bad)
            with self.assertRaises(model.Rejected):cli.bridge("project",bad)
        bad=copy.deepcopy(p);bad["history"]["payload_sha256"]="0"*64
        with self.assertRaisesRegex(model.Rejected,"HISTORY_INPUT_SHA"):cli.bridge("project",bad)

    def test_04_adapter_credible_data_failures(self):
        p=self.plan(); payload=p["history"]["payload"]
        daily=self.w.query(DAYS[0],CUTOFF,CODES,limit=2000)
        factor=self.s.query("adj_factor",DAYS[0],CUTOFF,CODES,limit=2000)
        susp=self.s.query("suspend_d",DAYS[0],CUTOFF,CODES,limit=2000)
        catalog={x["ts_code"]:x for x in self.catalog()}
        def call(d=daily,f=factor,s=susp,c=catalog):
            return h.assemble(self.desc,CODES,ASOF,DAYS[:84],c,d,f,s,payload["dataset_versions"],payload["metadata"])
        for field,value,code in (("close","0","HISTORY_PRICE_INVALID"),("vol","0","HISTORY_VOLUME_INVALID"),
                                 ("pre_close","9","HISTORY_PRE_CLOSE_ACTION_OR_REVISION"),("ts_code","999999.SZ","HISTORY_MISSING_OR_SUSPENDED_DAY")):
            bad=copy.deepcopy(daily);bad["rows"][len(CODES)+1]["values"][field]=value
            with self.assertRaisesRegex(h.Blocked,code):call(d=bad)
        bad=copy.deepcopy(daily);bad["rows"].pop(3)
        with self.assertRaisesRegex(h.Blocked,"HISTORY_MISSING_OR_SUSPENDED_DAY") as got:call(d=bad)
        self.assertLess(got.exception.coverage["ratio"],1)
        bad=copy.deepcopy(daily);bad["rows"].insert(3,bad["rows"][3])
        with self.assertRaisesRegex(h.Blocked,"HISTORY_DUPLICATE_DAY"):call(d=bad)
        bad=copy.deepcopy(factor);bad["rows"][3]["data"]["adj_factor"]="2"
        with self.assertRaisesRegex(h.Blocked,"HISTORY_RAW_ACTION_DISCONTINUITY"):call(f=bad)
        bad=copy.deepcopy(susp);bad["rows"].append(dict(data=dict(ts_code=CODES[0],suspend_type="S")))
        with self.assertRaisesRegex(h.Blocked,"HISTORY_SUSPENSION_REPORTED"):call(s=bad)
        bad=copy.deepcopy(catalog);bad[CODES[0]]["list_date"]=CUTOFF
        with self.assertRaisesRegex(h.Blocked,"HISTORY_LISTING_INTERVAL"):call(c=bad)

    def catalog(self):
        with self.w.read() as db:return self.w.latest_objects(db,"stock_basic")

    def test_05_data_asof_model_changes_cannot_reuse_task(self):
        p=self.plan(); old=cli.bridge("project",p)["provider_hash"]
        q=copy.deepcopy(p);q["manifest_sha256"]="1"*64
        self.assertNotEqual(cli.bridge("project",q)["provider_hash"],old)
        f,hist=h.read(self.desc,self.w.root,self.s.root,CODES,h.iso(DAYS[84])+"T08:00:00Z")
        q=copy.deepcopy(p);q.update(frozen=f,history=hist)
        self.assertNotEqual(cli.bridge("project",q)["provider_hash"],old)
        bad=copy.deepcopy(p);bad.pop("history")
        with self.assertRaisesRegex(model.Rejected,"REAL_READINESS_BLOCKED"):cli.bridge("project",bad)

    def test_07_history_interrupt_cancel_and_failure(self):
        for label in ("interrupt","timeout","oom","cancel"):
            cli.bridge("enable")
            p=self.plan();p["batch"]+="-"+label;self.save(p)
            if label=="interrupt":
                cli.bridge("begin",p)
                runner=lambda _:self.fail("Interrupted task retried")
            elif label=="cancel":
                def runner(raw):
                    cli.bridge("disable")
                    return fixture.fixture_response(raw)
            else:
                def runner(raw):
                    raise model.Rejected("WORKER_TIMEOUT" if label=="timeout" else "WORKER_OOM")
            with patch.object(cli,"verify_model",return_value=self.manifest),patch.object(runtime,"command",return_value=[]):
                got=cli.once(p["batch"],runner)
            self.assertEqual(got["state"],"cancelled" if label=="cancel" else "failed")
            self.assertIsNone(got["result"])
            if label=="interrupt":self.assertEqual(got["reason"],"WORKER_INTERRUPTED_NO_RETRY")

    def test_08_sqlite_only_reads_keep_boundaries(self):
        before=[(x.read_bytes(),x.stat().st_mtime_ns) for x in (self.w.path,self.s.path)]
        self.plan()
        after=[(x.read_bytes(),x.stat().st_mtime_ns) for x in (self.w.path,self.s.path)]
        self.assertEqual(before,after)
        # Raw is never consumed by this mode; default full inspection still rejects it.
        link=self.w.root/"raw"/"unread-link";link.symlink_to(self.s.path)
        try:
            self.w.query(DAYS[0],CUTOFF,CODES,limit=2000,inspect_raw_paths=False)
            with self.assertRaisesRegex(v1.WarehouseError,"WAREHOUSE_LINK_DENIED"):
                self.w.query(DAYS[0],CUTOFF,CODES,limit=2000)
        finally:link.unlink()
        original=self.w.path;real=original.with_suffix(".saved")
        original.rename(real);original.symlink_to(real)
        try:
            with self.assertRaisesRegex(v1.WarehouseError,"WAREHOUSE_LINK_DENIED"):
                self.w.query(DAYS[0],CUTOFF,CODES,limit=2000,inspect_raw_paths=False)
        finally:original.unlink();real.rename(original)

    def test_09_eight_series_max_context_fits_contract(self):
        p=self.plan()
        f,hist=h.read(self.desc,self.w.root,self.s.root,CODES,h.iso(DAYS[191])+"T08:00:00Z",context=192)
        p.update(frozen=f,history=hist)
        self.assertLess(len(json.dumps(p).encode()),2097152)
        request=json.loads(cli.bridge("project",p)["worker_request_json"])
        self.assertEqual(len(request["series"]),8)
        self.assertEqual(len(request["series"][0]["values"]),172)

    def test_06_old_synthetic_mode_still_works(self):
        p=dict(batch="legacy-fixture",frozen=cli.frozen(self.desc),manifest_sha256="1"*64,
               code_sha256=self.desc["code_sha256"],max_context=256,batch_size=1,threads=2)
        p["frozen"]["input_mode"]="historical_backfill_ex_post"
        with self.assertRaisesRegex(model.Rejected,"REAL_READINESS_BLOCKED"):cli.bridge("project",p)
        p["frozen"]["input_mode"]="synthetic_test"
        raw=cli.bridge("project",p)["worker_request_json"].encode()
        self.assertEqual(cli.bridge("decode",dict(plan=p,response=fixture.fixture_response(raw)))["risk_experts"][0]["input_mode"],"synthetic_test")
        p["code_sha256"]="26c92639fd78b143c4bd400988f447f29fcb52294319734555bae14efe669f2a"
        # Read-only prior implementation receipts remain verifiable; fresh work requires new code.
        cli.bridge("evaluate-project",p)
        with self.assertRaisesRegex(model.Rejected,"LOCAL_PIN_CHANGED"):cli.bridge("project",p)

if __name__=="__main__":unittest.main(verbosity=2)
