"""PR17: real request/decoder/Owner CNY Store, libtest loopback only; no paid API."""
import copy
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import localcontext
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import autonomous_research as a
import cloud_structured as cloud
spec=importlib.util.spec_from_file_location("pr16",ROOT/"scripts/test-cloud-structured.py")
pr16=importlib.util.module_from_spec(spec);spec.loader.exec_module(pr16)


def libtest():
    binaries=sorted((p for p in (ROOT/"target/debug/deps").glob("stratide_research-*.exe" if os.name=="nt" else "stratide_research-*") if p.is_file() and os.access(p,os.X_OK)),key=lambda p:p.stat().st_mtime_ns)
    if not binaries:raise RuntimeError("Build stratide-research --lib tests first")
    return binaries[-1]


def driver(name,root,**kwargs):
    env=os.environ.copy();env["STRATIDE_STRUCTURED_TEST"]=json.dumps(dict(experiment=str(root),**kwargs))
    run=subprocess.run([str(libtest()),"--exact",f"structured_tests::{name}","--nocapture"],env=env,
        cwd=ROOT,capture_output=True,timeout=30)
    if run.returncode:raise AssertionError(run.stderr.decode(errors="replace"))
    return run


def loopback(root,wire,status=200):
    bodies=[]
    payload=a.canonical(wire)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            assert self.headers["Authorization"]=="Bearer sk-syntheticTESTcredential1234567890"
            bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(status);self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=HTTPServer(("127.0.0.1",0),Handler);server.timeout=10
    thread=threading.Thread(target=server.handle_request,daemon=True);thread.start()
    try:
        run=driver("process_driver",root,port=server.server_port)
        thread.join(12)
        assert len(bodies)==1
        assert b"sk-syntheticTESTcredential1234567890" not in run.stdout
        assert bodies[0]["model"]=="deepseek-flash" and bodies[0]["thinking"]==dict(type="disabled")
        assert bodies[0]["max_tokens"]==4096 and "max_completion_tokens" not in bodies[0]
        user=json.loads(bodies[0]["messages"][1]["content"])
        assert user==cloud.request(a.read(root/"plan.json"),1)
        assert set(user["research_boundary"])=={"mode","max_positions","candidate_limit"}
        assert "dataset_versions" not in json.dumps(user) and str(ROOT) not in json.dumps(user)
        assert "tools" not in bodies[0] and "functions" not in bodies[0]
        return dict(loopback_http_calls=1,real_provider_calls=0,request_body_sha=a.sha(a.canonical(bodies[0])))
    finally:server.server_close()


class Suite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent=ROOT/"state/deepseek-tests";parent.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=parent);cls.sources=Path(cls.temp.name)
        cls.dates,_=pr16.prior.make_fixture(cls.sources)
        cls.base=a.OUTPUT/cls.sources.name;cls.counter=0

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        if cls.base.exists():shutil.rmtree(cls.base)

    def experiment(self):
        Suite.counter+=1;root=self.base/str(Suite.counter);owner=self.sources/f"owner-{Suite.counter}"
        driver("process_driver_init_cny",root,initialize_cny=str(owner))
        key=self.sources/f"credential-{Suite.counter}.md";key.write_text("API Key: sk-syntheticTESTcredential1234567890",encoding="utf-8")
        now=datetime.now(timezone.utc)
        cfg=dict(version=1,key_file=str(key),grant_version="deepseek-synthetic-grant-v1",synthetic_only=True,
            provider_terms_reviewed=True,authorized_at=now.isoformat(),price_reviewed_at=now.isoformat(),
            price_valid_until=(now+timedelta(days=1)).isoformat(),max_call_micro=100000)
        path=self.sources/f"config-{Suite.counter}.json";path.write_bytes(a.canonical(cfg))
        cloud_config=cloud.configuration(root,owner,"authorized_cloud",deepseek_config=path)
        dates=self.dates;config=a.m.default_config(dates[0],dates[-1]);config["max_positions"]=2
        config["windows"]=[dict(name="development",role="development",start=dates[0],end=dates[69]),
            dict(name="validation",role="validation",start=dates[70],end=dates[79]),
            dict(name="exposed",role="evaluation",start=dates[80],end=dates[-1],train_end=dates[79])]
        ds=a.m.data.Dataset(self.sources/"v1",self.sources/"v2",dates[0],dates[-1],90,360)
        with localcontext() as ctx:
            ctx.prec=50;a.initialize(ds,config,root,authorized=True,cloud=cloud_config)
        return root,owner,key

    def wire(self,root,content=None):
        value=json.loads(pr16.wire(cloud.expected_source(a.read(root/"plan.json"),1)))
        value.update(model="deepseek-flash",system_fingerprint="synthetic-fp-1")
        value["choices"][0]["logprobs"]=None
        value["usage"].update(prompt_cache_hit_tokens=1000,prompt_cache_miss_tokens=3096,
            prompt_tokens_details=dict(cached_tokens=1000),completion_tokens_details=dict(reasoning_tokens=0))
        if content is not None:value["choices"][0]["message"]["content"]=content
        return value

    def once(self,root):
        with localcontext() as ctx:ctx.prec=50;return a.once(root)

    def enable(self,root):cloud.rust("enable-deepseek",root,"APPROVE_ONE_SYNTHETIC_DEEPSEEK_REQUEST")

    def test_default_off_preflight_no_key_read_no_network_and_explicit_once(self):
        root,owner,key=self.experiment()
        key.write_text("invalid unread credential",encoding="utf-8")
        before=(owner/"settings.json").read_bytes()
        result=self.once(root)
        self.assertEqual(result["status"]["state"],"BLOCKED")
        self.assertEqual(cloud.rust("preflight",root)["enabled"],False)
        self.assertEqual(before,(owner/"settings.json").read_bytes())
        with closing(sqlite3.connect(owner/"agent.sqlite")) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM calls").fetchone()[0],0)
        with self.assertRaisesRegex(a.Error,"OPT_IN_REQUIRED"):cloud.rust("enable-deepseek",root,"no")
        self.assertTrue(a.verify(root)["verified"])

    def test_https_request_loopback_ast_freeze_pr62_evaluate_and_readonly_audit(self):
        root,owner,key=self.experiment();self.enable(root)
        evidence=loopback(root,self.wire(root))
        self.assertEqual(evidence["real_provider_calls"],0)
        result=self.once(root)
        self.assertEqual(result["status"]["state"],"COMPLETED")
        record=a.read(root/"round-01/proposals.json")
        self.assertEqual(len(record["proposals"]),4)
        self.assertEqual(record["cloud_receipt"]["real_provider_calls"],0)
        self.assertEqual(record["cloud_receipt"]["provider_metadata"]["verification"],"LOOPBACK_NOT_REAL_PROVIDER")
        self.assertEqual(record["cloud_receipt"]["currency"],"CNY")
        self.assertEqual(cloud.report(root)["loopback_calls"],1)
        self.assertEqual(cloud.report(root)["real_provider_calls"],0)
        self.assertTrue(a.verify(root)["verified"])
        cloud.rust("disable-deepseek",root);key.unlink()
        # Read-only consumers do not launch the Agent, inspect credentials or open sources.
        with mock.patch.object(cloud,"rust",side_effect=AssertionError("audit attempted dispatch")),mock.patch.object(a.m.data,"Dataset",side_effect=AssertionError("audit opened sources")):
            self.assertTrue(a.verify(root)["verified"]);a.status(root);a.history(root);a.report(root)
        self.assertEqual(self.once(root)["status"]["state"],"COMPLETED")
        with closing(sqlite3.connect(owner/"agent.sqlite")) as db:
            state,maximum,settled=db.execute("SELECT state,maximum_micro,settled_micro FROM calls").fetchone()
        self.assertEqual((state,maximum,settled),("usage_received",98304,0))

    def test_blank_truncation_refusal_partial_and_invalid_source_keep_cost_and_audit(self):
        for variant in ("blank","length","refusal","partial","forged"):
            root,owner,_=self.experiment();self.enable(root);wire=self.wire(root)
            if variant=="blank":wire["choices"][0]["message"]["content"]="   "
            elif variant=="length":wire["choices"][0]["finish_reason"]="length"
            else:
                response=json.loads(wire["choices"][0]["message"]["content"])
                if variant=="refusal":response.update(candidates=[],refusal="No supported hypothesis")
                elif variant=="partial":response["candidates"][0]["ast"]["score"]["op"]="shell"
                else:response["source"]["model_sha"]="f"*64
                wire["choices"][0]["message"]["content"]=json.dumps(response)
            loopback(root,wire);self.once(root)
            self.assertTrue(a.verify(root)["verified"])
            record=a.read(root/"round-01/proposals.json")
            self.assertEqual(len(record["proposals"]),3 if variant=="partial" else 0)
            with closing(sqlite3.connect(owner/"agent.sqlite")) as db:self.assertEqual(db.execute("SELECT state FROM calls").fetchone()[0],"usage_received")

    def test_missing_usage_unknown_and_recording_cannot_replace_https(self):
        root,owner,_=self.experiment();self.enable(root);wire=self.wire(root);del wire["usage"]
        loopback(root,wire);result=self.once(root)
        self.assertEqual(result["status"]["state"],"OUTCOME_UNKNOWN")
        self.assertEqual(cloud.report(root)["possible_real_provider_calls"],1)
        self.assertIsNone(cloud.report(root)["external_data_sends"])
        self.once(root);self.assertTrue(a.verify(root)["verified"])
        with closing(sqlite3.connect(owner/"agent.sqlite")) as db:self.assertEqual(db.execute("SELECT COUNT(*),state,maximum_micro FROM calls").fetchone(),(1,"outcome_uncertain",98304))
        with self.assertRaisesRegex(a.Error,"DEEPSEEK_RECORDING_NOT_ALLOWED"):
            cloud.freeze_transport(root,a.read(root/"plan.json"),1,recording=self.sources/"not-used.json")

    def test_original_invoice_settlement_does_not_resign_frozen_research(self):
        root,owner,_=self.experiment();self.enable(root);loopback(root,self.wire(root));self.once(root)
        archive=(root/"round-01/archive.json").read_bytes()
        daemon=ROOT/"target/debug"/("stratided.exe" if os.name=="nt" else "stratided")
        run=subprocess.run([str(daemon),"--agent-settle",str(owner),"1","12345","SYNTHETIC-INVOICE-ONLY"],capture_output=True,cwd=ROOT)
        self.assertEqual(run.returncode,0)
        self.assertTrue(a.verify(root)["verified"])
        self.assertEqual(archive,(root/"round-01/archive.json").read_bytes())


if __name__=="__main__":unittest.main(verbosity=2)
