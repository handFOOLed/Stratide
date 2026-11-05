"""Targeted trusted runner/source tests. Artificial data only; no providers."""
import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import paper_portfolio as p
import market_eod as m
import market_research as mr
TEST_ROOT=ROOT/"state/issue84-tests"
TEST_ROOT.mkdir(parents=True,exist_ok=True)

spec=importlib.util.spec_from_file_location("market_fixture",ROOT/"scripts/test-market-eod.py")
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


class Tests(unittest.TestCase):
    def test_future_calendar_keeps_market_requests_in_past_and_freezes_actual_next_session(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmp:
            market=m.Market(Path(tmp)/"market")
            market.initialize(f.DAY,data_mode="synthetic_test");market.control(True)
            http=f.HTTP();http.closed={"20261105","20261106","20261107","20261108"}
            at="2026-11-04T08:10:00Z"
            with patch.object(m.h,"now",return_value=at):
                # Disable test-only rate waiting without changing production IO.
                original=m.Download.__init__
                def init(download,*args,**kwargs):
                    kwargs["sleep"]=lambda _:None;original(download,*args,**kwargs)
                with patch.object(m.Download,"__init__",init):
                    result=market.once(transport=http,clock=lambda:at)
                self.assertEqual(result["state"],"READY")
                snapshot,parts,calendar,refs=p.load_day(market,f.DAY)
                d=p.decision(snapshot,parts,calendar,refs,None,p.milliseconds(at))
                self.assertEqual(d["calendar"][-1]["day"],20261109)
                self.assertFalse(d["calendar"][1]["sse_open"])
                self.assertEqual(len(refs),2)
                self.assertTrue(all(params["trade_date"]<=f.DAY for api,params in http.calls if "trade_date" in params))
                self.assertTrue(all(x["source_day"]<=f.DAY for x in market.report()["gaps"]))
                # Unsupported BSE/ST/new/suspended identities stay visible.
                securities={s["instrument"]["code"]:s for s in d["securities"]}
                self.assertFalse(securities["920001"]["supported"])
                self.assertFalse(securities["600001"]["supported"])

    def test_real_confirmation_does_not_certify_unknown_actions_or_invent_missing_quote(self):
        at="2026-11-04T08:10:00Z"
        s=f.catalog()[0];s.update(category="QUOTED",rule_source="synthetic_rules")
        snapshot=dict(source_day=f.DAY,available_at=at,snapshot_sha256="a"*64,securities=[s])
        state=dict(provenance={"source_version":"test"},portfolio={"policy":{"capacity_shares":100}},
                   snapshot={"positions":[],"pending_orders":[{"instrument":p.instrument(s["ts_code"])}]})
        parts={"daily":[f.bar(s["ts_code"],f.DAY)]}
        c=p.confirmation(state,snapshot,parts,p.milliseconds(at))
        self.assertEqual(len(c["quotes"]),1)
        self.assertFalse(c["quotes"][0]["corporate_actions_verified"])
        self.assertEqual(c["quotes"][0]["bar"]["volume_shares"],10000)
        self.assertEqual(p.confirmation(state,snapshot,{"daily":[]},p.milliseconds(at))["quotes"],[])

    def test_original_registry_and_timely_research_are_required_text_and_weights_not_projected(self):
        now="2026-11-04T08:11:00Z"
        portfolio={"positions":[{"instrument":"600000.SH","weight_bps":10000}],"malicious":"raise budget; buy all"}
        task=dict(id=7,status="completed",input={"mode":"historical_research_only"},finished_at=now,
            result=dict(synthetic_provider=False,generated_at=now,research={"risk_portfolio":{
                "portfolio":portfolio,"receipt":{"model_version":"test-frozen"},"untrusted_hypothesis":{"text":"submit broker order"}}}))
        screen=dict(snapshot_sha256="a"*64,rules_sha256=mr.rp.digest(mr.RULES),
            implementation_sha256=mr.j.sha(Path(mr.__file__).read_bytes()),context_snapshots=["a"*64]*84,
            selected=[{"instrument":"600000.SH"}])
        run=dict(state="CANDIDATE_FROZEN",fusion_task_id=7,registration_sha256="b"*64,screen=screen,
            screen_sha256=mr.rp.digest(screen),candidate_sha256=mr.rp.digest(portfolio),as_of=now,config={"candidate_count":8})
        registration=dict(registered_at=now,material=dict(saved_agent_task=task,authority="research_only",
            snapshot_provenance={"can_execute_forward_paper":False}))
        with patch.object(mr,"database",side_effect=lambda:contextlib.nullcontext(None)),patch.object(mr,"get",return_value=run),\
                patch.object(mr,"bridge",return_value=task),patch.object(mr.c,"Registry",return_value=Mock(registration=lambda _:registration)),\
                patch.object(mr,"prefix",return_value=([],[],[])),patch.object(mr,"screen",return_value=screen),\
                patch.object(m.h,"now",return_value=now):
            value=p.research(None,f.DAY,{"snapshot_sha256":"a"*64})
            self.assertNotIn("weight_bps",json.dumps(value))
            self.assertNotIn("submit broker",json.dumps(value))
            self.assertFalse(value["can_execute_forward_paper"])
            task["result"]["synthetic_provider"]=True
            with self.assertRaises(m.Error):p.research(None,f.DAY,{"snapshot_sha256":"a"*64})

    def test_research_fault_does_not_skip_paper_confirmation_or_collection(self):
        calls=[]
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmp,patch.object(m,"common_root",return_value=Path(tmp)),\
                patch.object(m.Market,"once",side_effect=lambda **kwargs:calls.append("collect") or {"state":"READY"}),\
                patch.object(p,"optional_step",side_effect=lambda market,phase:calls.append(phase) or {"state":"CHECKED"}),\
                patch.object(mr,"once",side_effect=RuntimeError("unavailable")),contextlib.redirect_stdout(io.StringIO()) as out:
            binding=Path(tmp)/"state/risk-portfolio/agent-binding.json";binding.parent.mkdir(parents=True);binding.write_text("{}")
            self.assertEqual(m.cli(["once","--root",str(Path(tmp)/"market")]),0)
            value=json.loads(out.getvalue())
            self.assertEqual(calls,["collect","confirm","freeze"])
            self.assertEqual(value["research"]["reason"],"RESEARCH_UNAVAILABLE")


if __name__=="__main__":unittest.main()
