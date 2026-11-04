"""Synthetic-only frozen evaluation/counterproofs in a disposable standalone checkout."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import risk_evaluation as e
import evidence_audit as audit

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
hist=module("history_fixture",ROOT/"scripts/test-timesfm-history.py")
independent=module("independent_risk_check",ROOT/"scripts/verify-risk-evaluation.py")

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert e.cpu.common_root()==ROOT,"Disposable standalone checkout required"
        hist.Tests.setUpClass()
        cls.w,cls.s=hist.Tests.w,hist.Tests.s
        # Explicit fixture provenance; never claim this generated source is real.
        with cls.s.write() as db:
            row=db.execute("SELECT manifest FROM metadata_source WHERE id=1").fetchone()
            meta=json.loads(row[0]);meta["source"]="synthetic_test"
            raw=e.data.canonical(meta)
            with db:
                db.execute("UPDATE metadata_source SET manifest=?,sha=? WHERE id=1",(raw.decode(),e.data.sha(raw)))
        cls.p=e.read(ROOT/"config/risk-evaluation-v1.json")
        cls.p.update(protocol_version="risk-oos-v1-synthetic-fixture",symbols=hist.CODES[:3],source_end=hist.B,
            splits=[dict(name="development",**{"from":"20220301","through":"20220430"}),
                    dict(name="validation",**{"from":"20220501","through":"20220630"}),
                    dict(name="test",**{"from":"20220701","through":"20220831"})])
        cls.config=ROOT/"state/test-risk-protocol.json"
        cls.config.write_text(json.dumps(cls.p))
        cls.manifest={"synthetic_fixture":True}
        cls.counter=0

    @classmethod
    def tearDownClass(cls):hist.Tests.tearDownClass()

    def frozen(self):
        Tests.counter+=1
        out=ROOT/"state"/("oos-test-"+str(Tests.counter))
        with patch.object(e.model,"verify_model",return_value=self.manifest):
            result=e.freeze(self.config,[self.w.root,self.s.root],out)
        return out,result

    def run_fixture(self,out,runner=hist.fixture.fixture_response):
        with patch.object(e.model,"verify_model",return_value=self.manifest):
            return e.run(out,runner)

    def test_01_full_freeze_run_independent_metrics_and_repeat(self):
        out,f=self.frozen();result=self.run_fixture(out)
        report=e.read(out/"report.json")
        self.assertEqual(report["classification"],"SYNTHETIC_TEST_ONLY")
        self.assertEqual(report["REAL_OOS"],"NOT_VERIFIED")
        self.assertGreater(report["counts"]["SCORED"],0)
        self.assertTrue(independent.verify(out)["verified"])
        self.assertEqual(self.run_fixture(out,lambda _:self.fail("Repeated inference")),result)
        self.assertTrue(e.verify(out)["verified"])
        for split in report["splits"].values():
            self.assertEqual(split["status"],"STRUCTURALLY_UNREACHABLE")
            self.assertEqual(split["sample_evidence_status"],"INSUFFICIENT_EVIDENCE")
            self.assertGreater(split["metrics"]["timesfm"]["20"]["points"],0)

    def test_02_future_quality_never_enters_prediction(self):
        out,_=self.frozen();f,pin=e.load_frozen(out)
        origin=next(x for x in f["origins"] if not x["exclusion"])
        with e.data.Dataset(self.w.root,self.s.root,start=self.p["source_start"],end=self.p["source_end"]) as ds:
            source=e.Source(ds)
            a=ROOT/"state/future-a";b=ROOT/"state/future-b";a.mkdir();b.mkdir()
            before=e.evaluate_sample(a,f,pin,source,origin,self.p["symbols"][0],hist.fixture.fixture_response)
            original=source.prefix
            def changed(descriptor,symbol,days):
                if len(days)>self.p["context_closes"]: raise e.history.Blocked("HISTORY_PRICE_JUMP")
                return original(descriptor,symbol,days)
            with patch.object(source,"prefix",side_effect=changed):
                after=e.evaluate_sample(b,f,pin,source,origin,self.p["symbols"][0],hist.fixture.fixture_response)
            self.assertEqual(before["state"],"SCORED")
            self.assertEqual(after["state"],"TARGET_BLOCKED")
            self.assertEqual(before["prediction_sha256"],after["prediction_sha256"])
            self.assertEqual(before["request_sha256"],after["request_sha256"])

    def test_03_pin_changes_and_protocol_cannot_reuse_outputs(self):
        out,first=self.frozen()
        changed=copy.deepcopy(self.p);changed["context_closes"]=85;changed["symbols"]=changed["symbols"][:2]
        new=ROOT/"state/changed-protocol.json";new.write_text(json.dumps(changed))
        with patch.object(e.model,"verify_model",return_value=self.manifest):
            other=e.freeze(new,[self.w.root,self.s.root],ROOT/"state/changed-freeze")
        self.assertNotEqual(first["pin"],other["pin"])
        with patch.object(e,"code_sha",return_value="0"*64),patch.object(e.model,"verify_model",return_value=self.manifest):
            with self.assertRaisesRegex(e.model.Rejected,"PIN_CHANGED"):e.run(out)
        with self.assertRaises(FileExistsError):self.frozen_collision(out)

    def frozen_collision(self,out):
        with patch.object(e.model,"verify_model",return_value=self.manifest):e.freeze(self.config,[self.w.root,self.s.root],out)

    def test_04_interruption_is_durable_no_automatic_rerun(self):
        out,_=self.frozen()
        def interrupt(_):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_fixture(out,interrupt)
        with self.assertRaisesRegex(e.model.Rejected,"INTERRUPTED"):self.run_fixture(out)
        self.assertEqual(e.summary(out)["state"],"INTERRUPTED")

    def test_05_arithmetic_tamper_fails_even_after_resealing(self):
        out,_=self.frozen();self.run_fixture(out)
        report=e.read(out/"report.json")
        report["splits"]["test"]["metrics"]["timesfm"]["20"]["mae"]+=.1
        (out/"report.json").write_text(json.dumps(report))
        with self.assertRaisesRegex(e.model.Rejected,"REPORT_SHA"):e.verify(out)
        seal=e.read(out/"seal.json");seal["files"]["report.json"]=e.model.sha_file(out/"report.json")
        (out/"seal.json").write_text(json.dumps(seal))
        self.assertTrue(e.verify(out)["verified"])
        with self.assertRaisesRegex(ValueError,"ARITHMETIC"):independent.verify(out)

    def test_06_failure_is_kept_coverage_is_not_success(self):
        out,_=self.frozen()
        def failure(_):raise e.model.Rejected("WORKER_TIMEOUT")
        self.run_fixture(out,failure)
        report=e.read(out/"report.json")
        self.assertEqual(report["REAL_OOS"],"NOT_VERIFIED")
        self.assertGreater(report["counts"]["PREDICTION_FAILED"],0)
        for s in report["splits"].values():self.assertEqual(s["coverage"],0)

    def test_07_forward_modes_and_gaps_are_not_synthetic_continuity(self):
        content=dict(data_mode="forward_observed_eod",as_of_journal_event_at=1793281197419,
            coverage=[dict(source_day="20261028",state="valid_eod")],attempts=[],versions=[
                dict(bar=dict(trade_day="20261028"),late_backfill=False,duplicate_of=None,revision_of=None,available_at=1793192840090),
                dict(bar=dict(trade_day="20261029"),late_backfill=True,duplicate_of=None,revision_of=None,available_at=1793367600000)],
            blockers=[],raw_sha256=[],journal_head="a"*64,event_count=5)
        result=audit.accumulate(content,{"20261028":True,"20261029":True,"20261030":True},"20261101","20261102")
        self.assertEqual([x["state"] for x in result["days"]],["ON_TIME","LATE_BACKFILL","MISSED","NOT_VERIFIED","NOT_VERIFIED"])
        self.assertEqual(result["cumulative_continuity"],"NOT_VERIFIED")
        content["versions"][1]["late_backfill"]=False
        content["data_mode"]="synthetic_test"
        self.assertEqual(audit.accumulate(content,{"20261028":True,"20261029":True},"20261029","20261102")["cumulative_continuity"],"NOT_VERIFIED")
        self.assertTrue(all(x["status"]=="BLOCKED" for x in audit.blockers()["matrix"]))
        gaps=audit.blockers()
        self.assertFalse(gaps["engineering_merge_blocked"])
        self.assertFalse(gaps["eod_paper_integration_blocked"])
        self.assertEqual(gaps["forward_paper"],"NOT_VERIFIED")
        for item in gaps["matrix"]:
            self.assertEqual(item["scope"],"REAL_DATA_EGRESS_AUTHORIZATION" if item["dependency"]=="real_fusion" else "EVIDENCE_CLAIM_ONLY")

    def test_08_independent_quality_oracle_rejects_captured_faults(self):
        out,_=self.frozen();self.run_fixture(out)
        report=e.read(out/"report.json");row=next(x for x in report["samples"] if x["state"]=="SCORED")
        raw=e.read(out/"samples"/row["sample_id"]/"prefix-source.json")
        self.assertFalse(independent.source_reasons(raw))
        for change,code in ((lambda v:v["daily"]["rows"].pop(),"HISTORY_MISSING_OR_SUSPENDED_DAY"),
                            (lambda v:v["daily"]["rows"].append(v["daily"]["rows"][-1]),"HISTORY_DUPLICATE_DAY"),
                            (lambda v:v["factors"]["rows"][1]["data"].update(adj_factor="2"),"HISTORY_RAW_ACTION_DISCONTINUITY"),
                            (lambda v:v["suspensions"]["rows"].append(dict(data=dict(ts_code=v["symbol"],suspend_type="S"))),"HISTORY_SUSPENSION_REPORTED")):
            bad=copy.deepcopy(raw);change(bad)
            self.assertIn(code,independent.source_reasons(bad))

    def test_09_zero_relative_error_and_no_cross_split_targets(self):
        scores=e.sample_scores({m:[0.0]*20 for m in e.MODELS},[0.0]*20)
        self.assertEqual(scores["timesfm"]["20"]["smape"],0)
        bad=copy.deepcopy(self.p);bad["target"]="price_direction"
        with self.assertRaisesRegex(e.model.Rejected,"PROTOCOL_CONTRACT"):e.protocol(bad)
        calendar={(x,d):"1" for x in ("SSE","SZSE") for d in ("20220315",)}
        with self.assertRaisesRegex(e.model.Rejected,"CALENDAR_GAP"):e.schedule(self.p,calendar)

    def test_10_pending_collector_day_is_blocked_and_operator_needs_actual_ref(self):
        content=dict(data_mode="forward_observed_eod",as_of_journal_event_at=1793281197419,
            coverage=[dict(source_day="20261028",state="missing_valid_eod")],attempts=[],versions=[],pending_days=["20261028"],
            blockers=["PENDING_COLLECTION"],raw_sha256=[],journal_head="a"*64,event_count=2)
        result=audit.accumulate(content,{"20261028":True},"20261028","20261102")
        self.assertEqual(result["days"][0]["state"],"BLOCKED")
        self.assertEqual(result["days"][0]["reason"],"PENDING_COLLECTION")
        import sqlite3
        dbpath=ROOT/"state/operator-no-refs.sqlite"
        identity=dict(policy="eod-operator-v1",source=dict(fixture="synthetic_test"))
        payload=dict(kind="initialized",at=1,data=dict(identity=identity))
        key=e.j.sha(e.j.canonical(identity))
        digest=e.j.sha(e.j.canonical([1090,key,"",0,payload]))
        with sqlite3.connect(dbpath) as db:
            db.execute("PRAGMA user_version=1090")
            db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,payload TEXT,digest TEXT)")
            db.execute("INSERT INTO events VALUES(?,?,?)",(0,json.dumps(payload),digest))
        checked=audit.operator_audit(dbpath,content)
        self.assertTrue(checked["journal_chain_verified"])
        self.assertFalse(checked["observer_prefix_refs_verified"])
        self.assertEqual(checked["state"],"NOT_VERIFIED")

    def test_11_code_change_during_run_cannot_seal_old_pin(self):
        out,_=self.frozen();original=e.code_sha();changed=[False]
        def runner(raw):
            changed[0]=True
            return hist.fixture.fixture_response(raw)
        with patch.object(e,"code_sha",side_effect=lambda:"0"*64 if changed[0] else original):
            with self.assertRaisesRegex(e.model.Rejected,"CODE_CHANGED_DURING_RUN"):
                self.run_fixture(out,runner)
        self.assertFalse((out/"seal.json").exists())
        self.assertEqual(e.summary(out)["state"],"INTERRUPTED")

    def test_12_perfect_data_cannot_reach_frozen_protocol_threshold(self):
        p=e.read(ROOT/"config/risk-evaluation-v1.json")
        scores=e.sample_scores({m:[0.01]*20 for m in e.MODELS},[0.01]*20)
        records=[dict(split=s["name"],origin=s["from"][:4]+f"{month:02}15",state="SCORED",
                      sample_id=f"{s['name']}-{month}-{symbol}",scores=scores)
                 for s in p["splits"] for month in range(1,13) for symbol in p["symbols"]]
        for result in e.aggregate(records,p).values():
            self.assertEqual(result["coverage"],1)
            self.assertEqual(result["distinct_origins"],12)
            self.assertEqual(result["status"],"STRUCTURALLY_UNREACHABLE")
            self.assertEqual(result["protocol_capacity"],dict(status="STRUCTURALLY_UNREACHABLE",
                maximum_monthly_origins=12,required_complete_origins=20))
        self.assertEqual(p["minimum_complete_origins_per_split"],20)

    def test_13_capacity_is_separate_from_observed_missingness_and_legacy_seals(self):
        p=copy.deepcopy(self.p)
        p["minimum_complete_origins_per_split"]=2
        scores=e.sample_scores({m:[0.01]*20 for m in e.MODELS},[0.01]*20)
        records=[dict(split="development",origin="20220315",state="SCORED",sample_id="one",scores=scores)]
        result=e.aggregate(records,p)["development"]
        self.assertEqual(result["protocol_capacity"]["status"],"POTENTIALLY_REACHABLE")
        self.assertEqual(result["status"],"INSUFFICIENT_EVIDENCE")
        records.append(dict(records[0],origin="20220415",sample_id="two"))
        result=e.aggregate(records,p)["development"]
        self.assertEqual(result["status"],"EX_POST_RESEARCH_ONLY")
        self.assertEqual(result["sample_evidence_status"],"MINIMUM_ORIGINS_MET")
        out,_=self.frozen();self.run_fixture(out)
        report=e.read(out/"report.json")
        independent.verify_capacity(report,self.p)
        bad=copy.deepcopy(report);bad["splits"]["test"]["protocol_capacity"]["maximum_monthly_origins"]=20
        with self.assertRaisesRegex(ValueError,"INDEPENDENT_PROTOCOL_CAPACITY"):
            independent.verify_capacity(bad,self.p)
        # Recreate the old schema as a synthetic historical artifact, then seal it.
        report["schema_version"]=1;report.pop("protocol_capacity");report["hypothesis_verdict"]="INSUFFICIENT_EVIDENCE"
        for split in report["splits"].values():
            split.pop("protocol_capacity");split.pop("sample_evidence_status");split["status"]="INSUFFICIENT_EVIDENCE"
        (out/"report.json").write_text(json.dumps(report))
        seal=e.read(out/"seal.json");seal["files"]["report.json"]=e.model.sha_file(out/"report.json")
        (out/"seal.json").write_text(json.dumps(seal))
        before={p.name:p.read_bytes() for p in out.glob("*.json")}
        checked=independent.verify(out)
        self.assertEqual(checked["stored_report_schema_version"],1)
        self.assertEqual(e.verify(out)["hypothesis_verdict"],"STRUCTURALLY_UNREACHABLE")
        self.assertEqual(before,{p.name:p.read_bytes() for p in out.glob("*.json")})

if __name__=="__main__":unittest.main()
