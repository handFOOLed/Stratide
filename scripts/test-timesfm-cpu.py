"""Synthetic contract/transport fault tests. No test double is a real-model PASS.

Run in an isolated Git checkout: the existing original Agent binding is immutable.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research/timesfm_cpu"))
import cli
import model
import runtime
import worker


class FixtureEngine:
    """Deterministic test transport only; not importable from production Worker."""
    def __init__(self, directory, request):
        self.manifest={"revision":model.REVISION,"files":{"model.safetensors":model.WEIGHT_SHA}}
        self.load_seconds=0
    def predict(self,request):
        return [dict(instrument=s["instrument"],values=[.01]*20) for s in request["series"]],[]


def fixture_response(raw):
    result=worker.execute(model.loads(raw),"unused",engine_factory=FixtureEngine)
    result["request_sha256"]=hashlib.sha256(raw).hexdigest()
    result["isolation"]=dict(mechanism="systemd-cgroup-v2+bubblewrap",memory_max_bytes=model.MEMORY_MAX,memory_swap_max_bytes=0)
    return result


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert cli.common_root()==ROOT,"Use isolated Git checkout, never the Owner checkout"
        cls.tag="cpu-test-"+os.urandom(4).hex()
        cls.owner=ROOT/"state/original-owner-agent"
        if not cls.owner.exists():
            p=subprocess.run([str(ROOT/"target/debug"/("stratided.exe" if os.name=="nt" else "stratided")),"--agent-init-fake",str(cls.owner)],capture_output=True,cwd=ROOT)
            assert p.returncode==0,p.stdout
        exe=ROOT/"target/debug"/("risk-portfolio-agent.exe" if os.name=="nt" else "risk-portfolio-agent")
        p=subprocess.run([str(exe),"init","--agent-dir",str(cls.owner)],capture_output=True,cwd=ROOT)
        assert p.returncode==0,p.stdout
        cls.desc=cli.bridge("descriptor")
        cls.manifest={"synthetic_test_manifest":"NO_REAL_MODEL_TEST"}
        cls.settings=(cls.owner/"settings.json").read_bytes()

    def setUp(self):
        cli.bridge("enable")
        self.name=self.tag+"-"+self._testMethodName.split("_")[1]

    def plan(self,count=1):
        return dict(batch=self.name,frozen=cli.frozen(self.desc,count),manifest_sha256=model.digest(self.manifest),
                    code_sha256=self.desc["code_sha256"],max_context=256,batch_size=1,threads=2)

    def save(self,p):
        path=cli.batch_path(p["batch"])
        path.mkdir(parents=True,exist_ok=True)
        (path/"plan.json").write_text(json.dumps(p),encoding="utf-8")

    def run_once(self,p,runner=fixture_response):
        self.save(p)
        # The installed state, not this fixture, selects WSL or the native model;
        # the manifest is injected so transport faults stay testable on Windows.
        expected=dict(manifest_sha256=model.digest(self.manifest),manifest=self.manifest,
                      model_revision=model.REVISION,weight_sha256=model.WEIGHT_SHA,source="TEST_FIXTURE")
        with patch.object(cli,"model_manifest",return_value=expected),patch.object(runtime,"uses_wsl",return_value=False),\
                patch.object(runtime,"preflight",return_value=[]):
            return cli.once(p["batch"],runner)

    def test_01_production_1_4_8_and_risk_result_v1(self):
        for n in (1,4,8):
            p=self.plan(n)
            p["batch"]+=f"-{n}"
            projection=cli.bridge("project",p)
            self.assertTrue(all(len(s["values"])==64 for s in json.loads(projection["worker_request_json"])["series"]))
            r=self.run_once(p)
            self.assertEqual(r["state"],"completed")
            b=r["result"]["research"]["risk_portfolio"]
            self.assertEqual(len(b["risk_experts"]),n)
            self.assertEqual(b["receipt"]["billing"],"LOCAL_NO_BILLING")
            self.assertFalse(b["paper_allowed"] or b["live_allowed"] or b["can_execute_forward_paper"])
            for s in b["risk_experts"]:
                self.assertEqual(s["forecast_sessions"],p["frozen"]["calendar"][-20:])
                self.assertAlmostEqual(s["volatility_forecast"][1]["value_ratio"],.01)
                self.assertEqual(s["target"],"rolling20_rms_daily_return_ratio")
            self.assertEqual(cli.bridge("decode",dict(plan=p,response=r["result"]["worker_response"])),b)
        self.assertEqual((self.owner/"settings.json").read_bytes(),self.settings)
        with sqlite3.connect(self.owner/"agent.sqlite") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM calls WHERE task_id IN (SELECT id FROM tasks WHERE provider_id='local-timesfm-2.5-cpu')").fetchone()[0],0)

    def test_02_future_observation_rejected(self):
        p=self.plan()
        p["frozen"]["series"][0]["observations"][-1]["available_at"]="2099-01-01T00:00:00Z"
        p["frozen"]["snapshot_ref"]=model.digest({k:p["frozen"][k] for k in ("series","calendar")})
        with self.assertRaisesRegex(model.Rejected,"BAD_OR_FUTURE_OBSERVATION"):
            cli.bridge("project",p)

    def test_03_original_limits_real_readiness_sessions_and_units(self):
        for mutate,code in [
            (lambda f:f.update(input_mode="historical_backfill_ex_post"),"REAL_READINESS_BLOCKED"),
            (lambda f:f["series"].extend(copy.deepcopy(f["series"])*8),"RISK_INPUT_SIZE"),
            (lambda f:f["calendar"].reverse(),"NON_TRADING_OR_UNORDERED_CALENDAR"),
            (lambda f:f["series"][0]["observations"].pop(),"INSUFFICIENT_MODEL_CONTEXT"),
            (lambda f:f["series"][0]["observations"][-1].update(close_fen=999999999),"RETURN_UNITS_OR_ACTION_GAP")]:
            p=self.plan()
            mutate(p["frozen"])
            p["frozen"]["snapshot_ref"]=model.digest({k:p["frozen"][k] for k in ("series","calendar")})
            with self.assertRaisesRegex(model.Rejected,code):cli.bridge("project",p)

    def test_04_negative_nan_duplicate_and_output_schema(self):
        p=self.plan()
        raw=cli.bridge("project",p)["worker_request_json"].encode()
        for x in (-.01,.351,float("nan")):
            with self.assertRaisesRegex(model.Rejected,"FORECAST_UNITS_OR_NEGATIVE"):model.forecasts([x]*20)
        for edit in (lambda r:r["forecasts"][0]["values"].__setitem__(0,-.01),
                     lambda r:r["forecasts"][0].update(instrument="600001.SH"),
                     lambda r:r.update(clamp_count=1),lambda r:r.update(model_revision="3.0"),
                     lambda r:r["isolation"].update(memory_max_bytes=model.MEMORY_MAX+1),
                     lambda r:r["forecasts"][0].update(order="BUY")):
            r=fixture_response(raw)
            edit(r)
            with self.assertRaises(model.Rejected):cli.bridge("decode",dict(plan=p,response=r))
        r=fixture_response(raw)
        r["isolation"]=dict(mechanism="UNISOLATED_DEVELOPMENT_DIAGNOSTIC",memory_max_bytes=None)
        with self.assertRaisesRegex(model.Rejected,"LOCAL_ISOLATION_REQUIRED"):cli.bridge("decode",dict(plan=p,response=r))
        dev=cli.bridge("decode-development",dict(plan=p,response=r))
        self.assertTrue(dev["receipt"]["development_only"])
        self.assertFalse(dev["paper_allowed"] or dev["live_allowed"])
        with self.assertRaisesRegex(model.Rejected,"DUPLICATE_JSON_KEY"):model.loads(b'{"a":1,"a":2}')

    def test_05_missing_and_tampered_weights_never_download(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"state") as tmp,patch("urllib.request.urlopen",side_effect=AssertionError("NETWORK_FORBIDDEN")):
            with self.assertRaisesRegex(model.Rejected,"MODEL_NOT_PROVISIONED"):model.verify_model(tmp)
            root=Path(tmp)
            for name in ("model.safetensors","README.md","config.json","LICENSE"):(root/name).write_text("tampered")
            manifest=dict(model=model.MODEL,revision=model.REVISION,license="Apache-2.0",versions=model.VERSIONS,
                          files={n:model.sha_file(root/n) for n in ("model.safetensors","README.md","config.json","LICENSE")})
            manifest["files"]["model.safetensors"]=model.WEIGHT_SHA
            (root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(model.Rejected,"MODEL_NOT_PROVISIONED"):model.verify_model(tmp)

    def test_06_restart_idempotency_and_changed_pins(self):
        p=self.plan()
        self.save(p)
        t=cli.bridge("begin",p)
        r=self.run_once(p,lambda _:self.fail("abandoned task must not dispatch"))
        self.assertEqual((r["id"],r["state"],r["reason"]),(t["id"],"failed","WORKER_INTERRUPTED_NO_RETRY"))
        self.assertEqual(self.run_once(p)["id"],t["id"])
        changed=copy.deepcopy(p)
        changed["manifest_sha256"]="f"*64
        with self.assertRaisesRegex(model.Rejected,"LOCAL_PIN_CHANGED_NEW_TASK_REQUIRED"):cli.bridge("begin",changed)
        changed=copy.deepcopy(p)
        changed["code_sha256"]="f"*64
        with self.assertRaisesRegex(model.Rejected,"LOCAL_PIN_CHANGED_NEW_TASK_REQUIRED"):cli.bridge("project",changed)

    def test_07_once_success_no_repeat_stop_and_failed_model(self):
        p=self.plan()
        r=self.run_once(p)
        self.assertEqual(self.run_once(p,lambda _:self.fail("duplicate dispatch"))["id"],r["id"])
        p=self.plan();p["batch"]+="-crash"
        def crash(_):raise model.Rejected("MODEL_RUNTIME_FAILED")
        self.assertEqual(self.run_once(p,crash)["state"],"failed")
        p=self.plan();p["batch"]+="-stop"
        def stop(raw):
            cli.bridge("disable")
            return fixture_response(raw)
        self.assertEqual(self.run_once(p,stop)["state"],"cancelled")

    def test_08_default_off_and_unsupported_isolation(self):
        cli.bridge("disable")
        with self.assertRaisesRegex(model.Rejected,"LOCAL_CPU_DISABLED"):cli.bridge("begin",self.plan())
        if sys.platform!="linux":
            with self.assertRaisesRegex(model.Rejected,"LINUX_ISOLATION_UNAVAILABLE"):runtime.command(2)
        self.assertNotIn("TOKEN",runtime.clean_env())
        with patch.dict(os.environ,{"STRATIDE_RESEARCH_KEY_TEST":"secret","TUSHARE_TOKEN":"secret"}):
            self.assertNotIn("TUSHARE_TOKEN",runtime.clean_env())
            self.assertNotIn("STRATIDE_RESEARCH_KEY_TEST",runtime.clean_env())
        with patch.object(runtime.subprocess,"run",return_value=subprocess.CompletedProcess([],0,b"STRATIDE_TIMESFM_RUN=other",b"")) as run:
            runtime.stop_owned("STRATIDE_TIMESFM_RUN=ours")
            self.assertEqual(run.call_count,1)
        with patch.object(runtime.subprocess,"run",return_value=subprocess.CompletedProcess([],0,b"STRATIDE_TIMESFM_RUN=ours",b"")) as run:
            runtime.stop_owned("STRATIDE_TIMESFM_RUN=ours")
            self.assertEqual(run.call_count,2)

        with patch.object(runtime.sys,"platform","linux"),patch.object(runtime.shutil,"which",return_value="/usr/bin/systemctl"):
            for fields,ok in ((b"LoadState=not-found\nActiveState=inactive\n",True),(b"LoadState=loaded\nActiveState=active\n",False)):
                results=[subprocess.CompletedProcess([],5,b"",b""),subprocess.CompletedProcess([],0,fields,b"")]
                with patch.object(runtime.subprocess,"run",side_effect=results):
                    if ok:self.assertEqual(runtime.stop()["state"],"STOPPED")
                    else:
                        with self.assertRaisesRegex(model.Rejected,"WORKER_STOP_FAILED"):runtime.stop()

    def test_09_timeout_crash_output_and_input_limits(self):
        read_fd,write_fd=os.pipe()
        try:
            os.write(write_fd,b'{"x":1}\n.\n');os.close(write_fd);write_fd=None
            self.assertEqual(worker.read_request_line(read_fd),(b'{"x":1}',b'.\n'))
        finally:
            os.close(read_fd)
            if write_fd is not None:os.close(write_fd)
        with self.assertRaisesRegex(model.Rejected,"WORKER_TIMEOUT"):
            runtime.communicate_bounded([sys.executable,"-c","import time;time.sleep(10)"],b"{}",timeout=.15)
        with self.assertRaisesRegex(model.Rejected,"WORKER_EXIT_FAILED"):
            runtime.communicate_bounded([sys.executable,"-c","raise SystemExit(42)"],b"{}")
        with self.assertRaisesRegex(model.Rejected,"WORKER_OUTPUT_LIMIT"):
            runtime.communicate_bounded([sys.executable,"-c","import sys;sys.stdout.write('x'*600000)"],b"{}")
        with self.assertRaisesRegex(model.Rejected,"WORKER_INPUT_LIMIT"):
            runtime.communicate_bounded([sys.executable],b"x"*(model.MAX_INPUT+1))
        children=[]
        def remember(p):children.append(p)
        def bad_cleanup():raise RuntimeError("STOP_FAILED")
        with self.assertRaisesRegex(RuntimeError,"STOP_FAILED"):
            runtime.communicate_bounded([sys.executable,"-c","import time;time.sleep(10)"],b"{}",timeout=.1,
                                        on_spawn=remember,cleanup=bad_cleanup)
        self.assertIsNotNone(children[0].poll())

    def test_10_two_processes_single_worker_and_release(self):
        path=ROOT/"state/test-worker.lock"
        code="import sys,time;sys.path.insert(0,sys.argv[1]);import runtime\nwith runtime.lock(sys.argv[2]):\n print('locked',flush=True);time.sleep(1)"
        args=[sys.executable,"-c",code,str(ROOT/"research/timesfm_cpu"),str(path)]
        a=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(a.stdout.readline().strip(),b"locked")
        b=subprocess.run(args,capture_output=True)
        self.assertNotEqual(b.returncode,0)
        a.communicate(timeout=5)
        with runtime.lock(path):pass

    def test_11_synthetic_10_30_50_100_contexts_without_frozen_expansion(self):
        for n in (10,30,50,100):
            for length in (64,128,256,512):
                request=dict(schema_version=1,input_mode="synthetic_test",horizon=20,max_context=length,batch_size=1,threads=2,repeats=1,
                             series=[dict(instrument=f"synthetic-{i}",values=[.01]*length) for i in range(n)])
                r=worker.execute(request,"unused",FixtureEngine)
                self.assertEqual(len(r["forecasts"]),n)
        request["series"][0]["values"][0]=float("nan")
        with self.assertRaisesRegex(model.Rejected,"WORKER_RMS_UNITS"):model.validate_request(request)

    @unittest.skipUnless(os.name=="nt","Windows diagnostic Job test; Linux cgroup tests are separate")
    def test_12_os_memory_limit_and_terminated_child(self):
        from windows import Job
        code="import json\ntry:\n x=bytearray(256*1024*1024)\n print(json.dumps({'error_code':'ALLOCATION_UNEXPECTED'}))\nexcept MemoryError:\n print(json.dumps({'error_code':'WORKER_OOM'}));raise SystemExit(2)"
        with self.assertRaisesRegex(model.Rejected,"WORKER_OOM"):
            runtime.communicate_bounded([sys.executable,"-c",code],b"{}",on_spawn=lambda p:Job(p,64*1024*1024))
        with tempfile.TemporaryDirectory(dir=ROOT/"state") as tmp:
            pidfile=Path(tmp)/"child.pid"
            code="import subprocess,sys,pathlib,time;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(30)"
            with self.assertRaisesRegex(model.Rejected,"WORKER_TIMEOUT"):
                runtime.communicate_bounded([sys.executable,"-c",code,str(pidfile)],b"{}",timeout=2,on_spawn=Job)
            self.assertTrue(pidfile.is_file())
            import ctypes as c
            from ctypes import wintypes as w
            kernel=c.WinDLL("kernel32",use_last_error=True)
            kernel.OpenProcess.restype=w.HANDLE
            kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
            kernel.CloseHandle.argtypes=[w.HANDLE]
            handle=kernel.OpenProcess(0x100000|0x1000,False,int(pidfile.read_text()))
            if handle:
                self.assertEqual(kernel.WaitForSingleObject(handle,2000),0)
                kernel.CloseHandle(handle)
            else:self.assertEqual(c.get_last_error(),87)


if __name__=="__main__":unittest.main(verbosity=2)
