"""Synthetic recorded EOD + CPU transport + libtest loopback, never paid/cloud.

Run only in a disposable standalone checkout with MARKET_TEST_DRIVER pointing to
the compiled stratide-research libtest binary. No Owner state may be reused.
"""
import contextlib
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import market_research as r
import market_eod as m
import local_fusion as legacy
import portfolio_research as rp
import candidates as c
sys.path.insert(0,str(ROOT/"research/timesfm_cpu"))
import cli as cpu
import model
import runtime
spec=importlib.util.spec_from_file_location("cpu_fixture",ROOT/"scripts/test-timesfm-cpu.py")
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
DAY="20261104"
ALL=list(m.h.dates("20260601",DAY))
DAYS=[d for d in ALL if m.h.day(d).weekday()<5][-92:]
CODES=["600000.SH","600001.SH","600002.SH","600003.SH","600004.SH","600005.SH","600006.SH","000001.SZ","000004.SZ","920001.BJ"]
CONFIG=dict(automatic_timesfm=True,automatic_deepseek=True,candidate_count=8,daily_call_limit=8,
            trading_day_call_limit=1,model_version="DeepSeek-V4.1-Flash-1017_ALIAS_MUTABLE")
FIELDS=["symbols","risk_forecasts","baselines","source_refs","quality","as_of","output_contract"]


class Recorded:
    def __call__(self,api,p,fields):
        if api=="stock_basic":
            rows=[dict(ts_code=code,symbol=code[:6],name="合成测试",exchange={"SH":"SSE","SZ":"SZSE","BJ":"BSE"}[code[-2:]],
                market="主板",list_status="L",list_date="20000101",delist_date=None) for code in CODES
                if {"SH":"SSE","SZ":"SZSE","BJ":"BSE"}[code[-2:]]==p["exchange"] and p["list_status"]=="L"]
        elif api=="trade_cal":
            rows=[dict(exchange=p["exchange"],cal_date=d,is_open=int(d in DAYS),pretrade_date=None)
                  for d in m.h.dates(p["start_date"],p["end_date"])]
        elif api=="daily":
            rows=[dict(ts_code=code,trade_date=p["trade_date"],open="10",high="10",low="10",close="10",pre_close="10",
                       change="0",pct_chg="0",vol="20000",amount=str(20000+i)) for i,code in enumerate(CODES)]
        elif api=="adj_factor":
            rows=[dict(ts_code=code,trade_date=p["trade_date"],adj_factor="1") for code in CODES]
        elif api=="daily_basic":
            rows=[dict(ts_code=code,trade_date=p["trade_date"],close="10",turnover_rate="1",total_mv="100") for code in CODES]
        else:rows=[]
        fs=fields.split(",")
        return 200,m.canonical(dict(code=0,data=dict(fields=fs,items=[[row.get(f) for f in fs] for row in rows]))),""


class Server:
    def __init__(self,scenario="success"):
        self.count=0;self.bodies=[];outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                outer.count+=1
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])));outer.bodies.append(body)
                if scenario=="disconnect":self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
                if scenario=="slow":time.sleep(.5)
                user=json.loads(body["messages"][1]["content"])
                response=user["output_contract"]
                if scenario=="bad-weights":response["portfolio"]["cash_weight_bps"]=9999
                value=dict(model="deepseek-flash",usage=dict(prompt_tokens=300,completion_tokens=400,total_tokens=700),
                    choices=[dict(index=0,finish_reason="stop",message=dict(role="assistant",content=json.dumps(response)))])
                raw=json.dumps(value).encode();self.send_response(200);self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
        self.http=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    def __enter__(self):
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();return self
    def __exit__(self,*args):self.http.shutdown();self.http.server_close();self.thread.join()


def driver(day,server,*,env_extra=None,popen=False):
    env=dict(os.environ,STRATIDE_MARKET_TEST_DRIVER="1",STRATIDE_MARKET_TEST_PORT=str(server.http.server_port))
    if env_extra:env.update(env_extra)
    command=[os.environ["MARKET_TEST_DRIVER"],"market_research::tests::process_driver","--exact","--nocapture"]
    if popen:
        p=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        p.stdin.write(json.dumps(dict(source_day=day)).encode());p.stdin.close();p.stdin=None;return p
    p=subprocess.run(command,input=json.dumps(dict(source_day=day)).encode(),cwd=ROOT,env=env,capture_output=True,timeout=20)
    assert p.returncode==0,p.stdout.decode()+p.stderr.decode()
    return json.loads(next(line.removeprefix("MARKET_RESULT=") for line in p.stdout.decode().splitlines() if line.startswith("MARKET_RESULT=")))


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert cpu.common_root()==ROOT,"Disposable standalone checkout required"
        reuse=os.environ.get("MARKET_TEST_REUSE_FIXTURE")=="1"
        assert not reuse or ROOT.name=="issue83-acceptance","Reuse only the explicit disposable fixture"
        assert reuse or not (rp.root()/"agent-binding.json").exists(),"Never reuse Owner state"
        (ROOT/"state").mkdir(exist_ok=True)
        key=ROOT/"state/test-key.md";key.write_text("sk-"+"Q"*32)
        now=dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=5)
        cfg=ROOT/"state/test-provider.json"
        cfg.write_text(json.dumps(dict(version=1,key_file=str(key),grant_version="deepseek-synthetic-fusion-grant-v1",
            synthetic_only=True,provider_terms_reviewed=True,authorized_at=now.isoformat(),price_reviewed_at=now.isoformat(),
            price_valid_until=(now+dt.timedelta(days=1)).isoformat(),max_call_micro=100000)))
        if not reuse:
            legacy.bridge("init-cny");legacy.bridge("configure",cfg);r.bridge("install-model")
        cls.market=m.Market(ROOT/"state/recorded-market")
        if not reuse:
            cls.market.initialize(DAYS[0],data_mode="synthetic_test");cls.market.control(True)
        original=m.Download.__init__
        def init(download,*args,**kwargs):kwargs["sleep"]=lambda _:None;original(download,*args,**kwargs)
        with patch.object(m.Download,"__init__",init):
            for day in ([] if reuse else DAYS):
                at=m.h.day(day).isoformat()+"T08:10:00Z"
                with patch.object(m.h,"now",return_value=at):
                    result=cls.market.once(transport=Recorded(),clock=lambda:at)
                    assert result["state"]=="READY",result
        cls.manifest={"fixture":"NO_REAL_MODEL"}
        cls.index=0
        if reuse:
            with r.database(True) as db:
                db.execute("DELETE FROM calls")
                db.execute("DELETE FROM tasks")
                db.execute("DELETE FROM meta WHERE key LIKE 'market_research_%' OR key LIKE 'market_research_%:%'")

    def setUp(self):
        r.bridge("configure",CONFIG)
        r.bridge("revoke")
        self.day=DAYS[-1-Tests.index];Tests.index+=1
        self.asof=m.h.day(self.day).isoformat()+"T08:11:00Z"

    def grant(self,**changes):
        scope=dict(provider="deepseek",recipient="https://api.deepseek.com/chat/completions",purpose="market_strategy_research",
            source_category="tushare_market_eod",fields=FIELDS,max_symbols=8,horizon=20,context_sessions=84,provider_terms_reviewed=True,
            valid_until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat())
        scope.update(changes);return r.bridge("grant",dict(confirmed=True,scope=scope))

    @contextlib.contextmanager
    def local_worker(self):
        """Fixture model/manifest; the installed state, not this suite, picks WSL."""
        expected=dict(manifest_sha256=model.digest(self.manifest),manifest=self.manifest,
            model_revision=model.REVISION,weight_sha256=model.WEIGHT_SHA,source="TEST_FIXTURE")
        with patch.object(cpu,"planning_manifest",return_value=expected),\
                patch.object(cpu,"model_manifest",return_value=expected),\
                patch.object(runtime,"uses_wsl",return_value=False),\
                patch.object(runtime,"preflight",return_value=[]):
            yield

    def prepare(self,fail_cpu=False):
        days,snapshots,sources=r.prefix(self.market,self.day,self.asof)
        screen=r.screen(days,snapshots,sources,self.asof,8)
        self.assertEqual(len(screen["selected"]),8)
        run=dict(state="SCREENED",source_day=self.day,data_mode="synthetic_test",as_of=self.asof,
            config=CONFIG,config_sha256=rp.digest(CONFIG),batch="market-"+self.day,screen=screen,
            screen_sha256=rp.digest(screen),events=["EOD_RECEIVED","SCREENED"],**rp.SAFE)
        with self.local_worker():
            plan=r.freeze_cpu(self.market,days,snapshots,sources,screen["selected"],self.asof,run["batch"])
        run["plan_sha256"]=rp.digest(plan);r.save(self.day,run)
        cpu.bridge("enable")
        with self.local_worker():
            def partial(raw):
                response=fixture.fixture_response(raw);response["forecasts"].pop();return response
            local=cpu.once(run["batch"],partial if fail_cpu else fixture.fixture_response)
        self.assertEqual(local["state"],"failed" if fail_cpu else "completed")
        if fail_cpu:return run,plan
        run["state"]="TIMESFM_DONE";run["events"].append("TIMESFM_DONE");r.save(self.day,run)
        return run,plan

    def test_01_screen_freeze_loopback_and_restart_no_duplicate(self):
        run,plan=self.prepare()
        self.grant()
        with Server() as server:
            value=driver(self.day,server)
            self.assertEqual(value["status"],"completed",value)
            self.assertEqual(len(value["calls"]),1)
            self.assertEqual(driver(self.day,server),value)
            self.assertEqual(server.count,1)
            body=server.bodies[0];user=json.loads(body["messages"][1]["content"])
            self.assertEqual(set(user["payload"]),set(FIELDS)-{"as_of","output_contract"})
            for secret_field in ("close_fen","raw_series","key_file","positions_ledger","cash_balance","api_key"):
                self.assertNotIn(secret_field,json.dumps(body))
            self.assertEqual(value["result"]["research"]["risk_portfolio"]["receipt"]["grant_version"],1)
        with self.local_worker(),patch.object(r,"bridge",side_effect=lambda a,v=None:value if a in ("once","task") else self.fail(a)):
            # Restore latest date for the real Operator consumer, using this run.
            result=r.once(self.market)
        self.assertEqual(result["state"],"CANDIDATE_FROZEN",result)
        with patch.object(r,"bridge",side_effect=AssertionError("Duplicate cloud")):
            self.assertEqual(r.once(self.market)["state"],"CANDIDATE_FROZEN")

    def test_02_unauthorized_revoked_expired_and_scope_rejected_no_calls(self):
        self.prepare()
        with Server() as server:
            for change in ({"fields":FIELDS[:-1]},{"purpose":"orders"},{"valid_until":"2000-01-01T00:00:00Z"}):
                with self.assertRaisesRegex(r.j.Rejected,"REAL_MARKET_DATA_EGRESS_DENIED"):self.grant(**change)
            denied=driver(self.day,server);self.assertEqual(denied["error_code"],"REAL_MARKET_DATA_EGRESS_DENIED")
            self.grant();r.bridge("revoke")
            self.assertEqual(driver(self.day,server)["error_code"],"REAL_MARKET_DATA_EGRESS_DENIED")
            self.assertEqual(server.count,0)

    def test_03_unknown_provider_is_terminal_and_reserved(self):
        self.prepare();self.grant()
        with Server("disconnect") as server:
            value=driver(self.day,server);self.assertEqual(value["status"],"outcome_uncertain",value)
            self.assertEqual(driver(self.day,server)["status"],"outcome_uncertain")
            self.assertEqual(server.count,1)
            self.assertEqual(value["calls"][0]["state"],"outcome_uncertain")
            self.assertEqual(value["calls"][0]["maximum_micro"],"98304")

    def test_04_shared_budget_exhaustion_zero_http(self):
        self.prepare();self.grant()
        with r.database(True) as db:
            prior=db.execute("SELECT id FROM tasks ORDER BY id LIMIT 1").fetchone()[0]
            db.execute("INSERT INTO calls(task_id,day,month,maximum_micro,price_version,state,created_at) VALUES(?,? ,? ,4900000,'test-held','outcome_uncertain',?)",
                (prior,"2020-01-01","2020-01",self.asof))
        try:
            with Server() as server:
                value=driver(self.day,server);self.assertEqual(value["status"],"failed",value)
                self.assertIn("BUDGET_EXHAUSTED",value["reason"]);self.assertEqual(server.count,0)
        finally:
            with r.database(True) as db:db.execute("DELETE FROM calls WHERE price_version='test-held'")

    def test_05_partial_cpu_failure_and_future_input_rejected(self):
        days,snapshots,sources=r.prefix(self.market,self.day,self.asof)
        damaged=copy.deepcopy(sources);damaged[2]["daily"]=[x for x in damaged[2]["daily"] if x["ts_code"]!=CODES[0]]
        screened=r.screen(days,snapshots,damaged,self.asof,8)
        self.assertIn(dict(instrument=CODES[0],reason="CONTINUOUS_HISTORY_OR_ACTION_EVIDENCE_MISSING"),screened["rejected"])
        with self.assertRaisesRegex(r.j.Rejected,"SOURCE_NOT_AVAILABLE"):
            r.prefix(self.market,self.day,m.h.day(self.day).isoformat()+"T07:00:00Z")
        snapshots[-1]["late_backfill"]=True
        # Missing samples are excluded before any Worker invocation.
        self.assertEqual(screened["universe_count"],10)

    def test_06_concurrent_agent_processes_pay_once(self):
        self.prepare();self.grant()
        with Server("slow") as server:
            first=driver(self.day,server,popen=True)
            deadline=time.time()+5
            while server.count==0 and time.time()<deadline:time.sleep(.02)
            second=driver(self.day,server)
            try:output=first.communicate(timeout=10)[0].decode()
            finally:
                if first.poll() is None:first.kill();first.communicate()
            self.assertIn('"status":"completed"',output)
            self.assertTrue(second.get("error_code")=="AGENT_ALREADY_RUNNING" or second.get("status")=="completed",second)
            self.assertEqual(server.count,1)

    def test_07_partial_timesfm_result_cannot_enter_cloud(self):
        run,plan=self.prepare(fail_cpu=True);self.grant()
        with Server() as server:
            value=driver(self.day,server)
            self.assertEqual(value["state"],"BLOCKED",value)
            self.assertEqual(server.count,0)
        self.assertEqual(cpu.task(run["batch"])["state"],"failed")
        with r.database() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM calls c JOIN tasks t ON t.id=c.task_id WHERE t.trigger_key=?",(r.POLICY+":"+self.day,)).fetchone()[0],0)

    def test_08_crash_after_dispatch_unknown_never_resends(self):
        self.prepare();self.grant()
        marker=rp.root()/("rp-test-market-crash-"+os.urandom(4).hex());marker.mkdir()
        with Server() as server:
            first=driver(self.day,server,env_extra={"STRATIDE_RP_TEST_FAULT":json.dumps(dict(point="after_dispatch",batch=marker.name))},popen=True)
            try:
                deadline=time.time()+8
                while not (marker/"test-marker").exists() and time.time()<deadline:time.sleep(.02)
                self.assertTrue((marker/"test-marker").exists())
            finally:first.kill();first.communicate(timeout=5)
            value=driver(self.day,server)
            self.assertEqual(value["status"],"outcome_uncertain",value)
            self.assertEqual(value["calls"][0]["state"],"outcome_uncertain")
            self.assertEqual(server.count,0)

    def test_09_wsl_worker_block_is_bounded_and_never_reaches_cloud(self):
        # The installed Windows chain reaches TimesFM through WSL; a missing or
        # failed Worker must block research only, then be retried after a bounded
        # cooldown without a second freeze or any paid dispatch. The original
        # watch always follows the latest frozen market day, so this test does too.
        day=self.market.report()["latest"]["source_day"]
        as_of=m.h.day(day).isoformat()+"T08:11:00Z"
        days,snapshots,sources=r.prefix(self.market,day,as_of)
        screen=r.screen(days,snapshots,sources,as_of,8)
        with r.database(True) as db:
            db.execute("DELETE FROM meta WHERE key=?",(r.RUN+day,))
        run=dict(state="SCREENED",source_day=day,data_mode="synthetic_test",as_of=as_of,
            config=CONFIG,config_sha256=rp.digest(CONFIG),batch="market-"+day,screen=screen,
            screen_sha256=rp.digest(screen),events=["EOD_RECEIVED","SCREENED"],**rp.SAFE)
        r.save(day,run)
        with patch.object(r,"freeze_cpu",side_effect=model.Rejected("TIMESFM_WSL_MODEL_MISSING")) as freeze,\
                patch.object(r,"bridge",side_effect=AssertionError("no cloud dispatch")):
            blocked=r.once(self.market)
            self.assertEqual(blocked["state"],"BLOCKED",blocked)
            self.assertEqual(blocked["reason"],"TIMESFM_WSL_MODEL_MISSING")
            self.assertEqual(blocked["cloud_status"],"CLOUD_RESEARCH_BLOCKED")
            self.assertIn("blocked_at",blocked)
            self.assertEqual(r.once(self.market)["reason"],"TIMESFM_WSL_MODEL_MISSING")
            self.assertEqual(freeze.call_count,1,"cooldown must not re-freeze the same day")
            stale=dict(blocked,blocked_at="2000-01-01T00:00:00Z")
            r.save(day,stale)
            self.assertEqual(r.once(self.market)["reason"],"TIMESFM_WSL_MODEL_MISSING")
            self.assertEqual(freeze.call_count,2,"an expired cooldown retries once")
        # The frozen EOD snapshot is untouched and stays usable for research.
        self.assertEqual(self.market.report()["latest"]["source_day"],day)


if __name__=="__main__":unittest.main(verbosity=2)
