"""Targeted trusted runner/source tests. Artificial data only; no providers."""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import subprocess
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
    def test_runner_cli_ledger_eod_assumption_then_missing_nav_and_cross_day_recovery(self):
        # The test-only CLI child supplies a fixed wall clock; production has no
        # clock override. All quotes are produced by the actual Market/Runner,
        # using an offline transport in the real-EOD schema (not real prices).
        exe=Path(os.environ["STRATIDE_PORTFOLIO_TEST_BIN"])
        class HTTP(f.HTTP):
            def __call__(self,api,params,fields):
                status,raw,extra=super().__call__(api,params,fields)
                data=json.loads(raw); names=data["data"]["fields"]
                if api=="daily" and params["trade_date"]>f.DAY:
                    for row in data["data"]["items"]:
                        row[names.index("pre_close")]="10.10";row[names.index("change")]="0";row[names.index("pct_chg")]="0"
                if api=="adj_factor" and params["trade_date"]>f.DAY:
                    for row in data["data"]["items"]:
                        if row[names.index("ts_code")]==f.B:row[names.index("adj_factor")]="2"
                return status,m.canonical(data),extra
        for approved in [False,True]:
            with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmp:
                root=Path(tmp);ledger=root/"account";at=["2026-11-04T08:00:00Z"]
                def bridge(path,action,value=None):
                    env=dict(os.environ,STRATIDE_PORTFOLIO_TEST_ARGS=json.dumps(["paper-portfolio",str(path),action]),
                             STRATIDE_PORTFOLIO_TEST_AT=str(p.milliseconds(at[0])))
                    result=subprocess.run([str(exe),"--exact","portfolio::tests::runner_child","--nocapture"],
                        input=m.canonical(value or {}),capture_output=True,env=env,timeout=20)
                    self.assertEqual(result.returncode,0,result.stdout.decode()+result.stderr.decode())
                    if action=="init":return {}
                    return next(json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith("{"))
                config=json.loads((ROOT/"docs/evidence/m0-pr03/sample-report/report.json").read_text(encoding="utf-8"))["config"]
                config.update(max_mark_age_ms=8*3600000,max_snapshot_age_ms=8*3600000)
                provenance=dict(mode="historical_replay",source_version="paper-eod-assumption-v1:offline-schema-test",
                    dataset_hash="a"*64,timezone="Asia/Shanghai",price_semantics="unadjusted_cny_fen")
                bridge(ledger,"init",dict(config=config,provenance=provenance,at=p.milliseconds(at[0]),day=20261104))
                symbols=[p.instrument(f.A),p.instrument(f.B)]
                fees=[dict(version="test-fees",source="offline-test",instrument=i,valid_from=20261104,valid_through=20261231,
                    commission_ppm=300,minimum_commission=1,transfer_ppm=10,sell_tax_ppm=500) for i in symbols]
                policy=dict(version="fixed-ticket-paper-v1",universe=symbols,target_value=201000,max_positions=2,max_daily_orders=2,
                    max_candidates=2,max_order_shares=100,capacity_shares=100,capacity_scope="Batch",max_symbol_value=400000,
                    max_daily_fees=100000,slippage_bps=100,min_amount_thousand_yuan=100,fees=fees,approve_fixed_baseline=True,automatic=True)
                if approved:policy["unverified_eod_assumption"]=dict(version="no-detected-action-mainboard-v1",max_exposure=config["strategy_limits"]["max_exposure"])
                bridge(ledger,"configure",policy)
                binding=root/"binding.json";binding.write_text(json.dumps(dict(ledger=str(ledger))),encoding="utf-8")
                market=m.Market(root/"market");market.initialize(f.DAY);market.control(True)
                http=HTTP();http.closed={"20261107","20261108"};http.missing_dates={"20261106":{f.A}}
                original=m.Download.__init__
                def init(download,*args,**kwargs):kwargs["sleep"]=lambda _:None;original(download,*args,**kwargs)
                def research(market,day,snapshot):
                    return dict(task_id="7",candidate_sha256="b"*64,registration_sha256="c"*64,model_version="offline-original-research-stub",
                        generated_at=p.milliseconds(at[0]),finished_at=p.milliseconds(at[0]),ready_sessions=84,
                        restriction="RESEARCH_ONLY",eligibility="ELIGIBILITY_DENIED",can_execute_forward_paper=False,selected=symbols)
                with patch.object(p,"binding_path",return_value=binding),patch.object(p,"bridge",side_effect=bridge),\
                        patch.object(p,"research",side_effect=research),patch.object(m.h,"now",side_effect=lambda:at[0]),\
                        patch.object(m.Download,"__init__",init):
                    def collect(day):
                        at[0]=m.h.day(day).isoformat()+"T08:10:00Z"
                        market.once(transport=http,clock=lambda:at[0]);at[0]=m.h.day(day).isoformat()+"T08:11:00Z"
                    collect(f.DAY);p.once(market)
                    collect("20261105");p.once(market)
                    view=bridge(ledger,"status");state=view["state"]
                    if not approved:
                        self.assertEqual(state["fills"],[])
                        continue
                    self.assertEqual(len(state["fills"]),1)
                    self.assertIn("CORPORATE_ACTIONS=UNVERIFIED",state["fills"][0]["historical_execution"])
                    first=state["portfolio"]["batches"][0]
                    self.assertTrue(all(q["corporate_actions_verified"] is False for q in first["confirmation"]["quotes"]))
                    self.assertTrue(any(o["status"]=="Expired" and o["proposal"]["instrument"]==p.instrument(f.B) for o in state["orders"]))
                    count=len(state["fills"]);p.once(market);self.assertEqual(len(bridge(ledger,"status")["state"]["fills"]),count)
                    collect("20261106");p.once(market,phase="confirm")
                    missing=bridge(ledger,"status")["state"];self.assertIsNotNone(missing["valuation_error"])
                    self.assertIsNone(missing["portfolio"]["pending"])
                    collect("20261109");p.once(market,phase="confirm")
                    recovered=bridge(ledger,"status")["state"]
                    self.assertIsNone(recovered["valuation_error"]);self.assertEqual(len(recovered["portfolio"]["recoveries"]),1)
                    for key in ("cash","positions","pending_orders"):
                        self.assertEqual(recovered["snapshot"][key],missing["snapshot"][key])
                    self.assertEqual(recovered["fills"],missing["fills"]);self.assertEqual(recovered["orders"],missing["orders"])
                    p.once(market);self.assertEqual(bridge(ledger,"status")["state"]["portfolio"]["batches"][-1]["decision"]["day"],20261109)

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

    def test_optional_paper_import_failure_keeps_watch_polling_and_stop_propagates(self):
        import builtins
        real_import=builtins.__import__;calls=[]
        def broken(name,*args,**kwargs):
            if name=="paper_portfolio":raise ImportError("offline test missing optional module")
            return real_import(name,*args,**kwargs)
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmp,patch.object(m,"common_root",return_value=Path(tmp)),\
                patch.object(m.Market,"once",side_effect=lambda **kwargs:calls.append("collect") or {"state":"READY"}),\
                patch.object(builtins,"__import__",side_effect=broken),patch.object(m.time,"sleep",side_effect=[None,KeyboardInterrupt]),\
                contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(KeyboardInterrupt):m.cli(["watch","--root",str(Path(tmp)/"market")])
            self.assertEqual(calls,["collect","collect"])
            for line in out.getvalue().splitlines():
                self.assertEqual(json.loads(line)["paper_confirmation"]["reason"],"PAPER_MODULE_UNAVAILABLE")

    def test_missing_snapshot_stays_blocked_and_handler_does_not_crash(self):
        # No snapshot is invented. The known code is the result, and the handler
        # must not raise NameError while recording it.
        with patch.object(p,"once",side_effect=m.Error("PAPER_MARKET_SNAPSHOT_MISSING")),\
                contextlib.redirect_stderr(io.StringIO()) as err:
            value=p.optional_step(object(),"freeze")
        self.assertEqual(value["state"],"BLOCKED")
        self.assertEqual(value["reason"],"PAPER_LOCAL_INPUT_OR_LEDGER_UNAVAILABLE")
        self.assertEqual(value["detail"]["type"],"WarehouseError")
        self.assertEqual(value["detail"]["message"],"PAPER_MARKET_SNAPSHOT_MISSING")
        self.assertNotIn("snapshot",value)
        self.assertNotIn("name 'sys' is not defined",err.getvalue())
        self.assertNotIn("Traceback",err.getvalue())
        with patch.object(p,"once",side_effect=RuntimeError("ledger helper failed")),\
                contextlib.redirect_stderr(io.StringIO()) as err:
            failed=p.optional_step(object(),"confirm")
        self.assertEqual(failed["detail"]["type"],"RuntimeError")
        self.assertIn("Traceback",err.getvalue())
        self.assertIn("ledger helper failed",err.getvalue())
        self.assertNotIn("name 'sys' is not defined",err.getvalue())

    def test_cli_snapshot_missing_reports_blocked_without_nameerror(self):
        with patch.object(p,"once",side_effect=m.Error("PAPER_MARKET_SNAPSHOT_MISSING")),\
                patch.object(p.m,"Market",return_value=object()),\
                patch.object(p.m,"default_root",return_value=Path(".")),\
                contextlib.redirect_stdout(io.StringIO()) as out,\
                contextlib.redirect_stderr(io.StringIO()) as err:
            code=p.main(["once"])
        self.assertEqual(code,1)
        body=json.loads(out.getvalue())
        self.assertEqual(body["state"],"BLOCKED")
        self.assertEqual(body["detail"]["message"],"PAPER_MARKET_SNAPSHOT_MISSING")
        self.assertIn("PAPER_MARKET_SNAPSHOT_MISSING",err.getvalue())
        self.assertNotIn("name 'sys' is not defined",err.getvalue())

    def test_watch_log_keeps_codes_and_drops_repeated_bulk(self):
        rejected=[dict(instrument=f"{i:06d}.SZ",reason="LIQUIDITY") for i in range(3000)]
        universe=[dict(market="Shenzhen",code=f"{i:06d}") for i in range(3000)]
        fees=[dict(instrument=item,commission_ppm=250) for item in universe]
        result=dict(state="ALREADY_FROZEN",
                    research=dict(state="BLOCKED",reason="NO_FROZEN_MARKET_SNAPSHOT",
                                  screen=dict(rejected=rejected,rejection_counts={"LIQUIDITY":3000},
                                              selected=[dict(instrument="000001.SZ")],source_day="20261108")),
                    paper_policy=dict(state="EXISTS",automatic=True,
                                      policy=dict(version="fixed-ticket-paper-v1",universe=universe,fees=fees,
                                                  max_positions=2)))
        line=json.dumps(m.watch_log_line(result),ensure_ascii=False)
        self.assertLess(len(line),4000)
        logged=json.loads(line)
        self.assertEqual(logged["state"],"ALREADY_FROZEN")
        self.assertEqual(logged["research"]["reason"],"NO_FROZEN_MARKET_SNAPSHOT")
        self.assertEqual(logged["research"]["screen"]["rejected_count"],3000)
        self.assertNotIn("rejected",logged["research"]["screen"])
        self.assertEqual(logged["research"]["screen"]["selected"],[dict(instrument="000001.SZ")])
        self.assertEqual(logged["paper_policy"]["policy"]["universe_count"],3000)
        self.assertEqual(logged["paper_policy"]["policy"]["fees_count"],3000)
        self.assertNotIn("universe",logged["paper_policy"]["policy"])
        self.assertNotIn("fees",logged["paper_policy"]["policy"])
        self.assertNotIn("000123.SZ",line)
        self.assertEqual(len(result["research"]["screen"]["rejected"]),3000)
        self.assertEqual(len(result["paper_policy"]["policy"]["universe"]),3000)

    def test_watch_missing_snapshot_prints_code_not_handler_crash_or_bulk(self):
        rejected=[dict(instrument=f"{i:06d}.SZ",reason="LIQUIDITY") for i in range(2000)]
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as tmp,\
                patch.object(m,"common_root",return_value=Path(tmp)),\
                patch.object(m.Market,"once",return_value=dict(state="ALREADY_FROZEN")),\
                patch.object(p,"once",side_effect=m.Error("PAPER_MARKET_SNAPSHOT_MISSING")),\
                patch.object(p,"ensure_policy",side_effect=m.Error("PAPER_MARKET_SNAPSHOT_REQUIRED")),\
                patch.object(mr,"once",return_value=dict(state="BLOCKED",reason="NO_FROZEN_MARKET_SNAPSHOT",
                    screen=dict(rejected=rejected,rejection_counts={"LIQUIDITY":2000},source_day="20261108"))),\
                patch.object(m.time,"sleep",side_effect=KeyboardInterrupt),\
                contextlib.redirect_stdout(io.StringIO()) as out,\
                contextlib.redirect_stderr(io.StringIO()) as err:
            binding=Path(tmp)/"state/paper-portfolio/binding.json"
            agent=Path(tmp)/"state/risk-portfolio/agent-binding.json"
            binding.parent.mkdir(parents=True)
            agent.parent.mkdir(parents=True)
            binding.write_text("{}",encoding="utf-8")
            agent.write_text("{}",encoding="utf-8")
            with self.assertRaises(KeyboardInterrupt):
                m.cli(["watch","--root",str(Path(tmp)/"market")])
        self.assertNotIn("name 'sys' is not defined",err.getvalue())
        self.assertNotIn("Traceback",err.getvalue())
        lines=out.getvalue().splitlines()
        self.assertEqual(len(lines),1)
        value=json.loads(lines[0])
        self.assertEqual(value["state"],"ALREADY_FROZEN")
        self.assertEqual(value["paper_policy"]["reason"],"PAPER_POLICY_ENSURE_FAILED")
        self.assertEqual(value["paper_policy"]["detail"]["message"],"PAPER_MARKET_SNAPSHOT_REQUIRED")
        self.assertEqual(value["paper_confirmation"]["detail"]["message"],"PAPER_MARKET_SNAPSHOT_MISSING")
        self.assertEqual(value["paper_decision"]["detail"]["message"],"PAPER_MARKET_SNAPSHOT_MISSING")
        self.assertEqual(value["research"]["screen"]["rejected_count"],2000)
        self.assertNotIn("rejected",value["research"]["screen"])
        self.assertNotIn("000123.SZ",lines[0])
        self.assertLess(len(lines[0]),4000)


if __name__=="__main__":unittest.main()
