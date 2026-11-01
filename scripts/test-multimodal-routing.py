"""P1 regression: route the checked task, not the shared Agent queue head.

All journals, calls and costs are synthetic; the production CLI and original
Rust Agent/SQLite/Provider are exercised. Retain original m2-pr10 evidence.
"""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("multimodal_fixtures", ROOT / "scripts/test-multimodal-research.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
m = f.m
RESULTS = []


def queued(label):
    name, source, events = f.setup(label)
    f.finish(f.launch(name, "once", fixture=True, fault="after_queue"), 86)
    entry = m.Run(name).entries()[-1]
    key = entry["task_id"]
    intent = m.j.loads(m.meta()["mm_intent:" + name + ":" + key])
    original = m.Run(name).task_for(intent)
    assert original["status"] == "queued" and original["calls"] == []
    return name, key, source, events


def bridge(action, name, key):
    command = [str(m.EXE), action, name, key]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
    f.COMMANDS.append(dict(command=command, exit_code=result.returncode))
    assert result.returncode == 0, (result.stdout, result.stderr)
    return m.j.loads(result.stdout)


def facts(name):
    config = m.Run(name).config()
    current = m.s.published(m.d.Store(config["snapshot_store_name"]))
    with m.agent_db() as db:
        rows = db.execute("SELECT id,trigger_key,status,reason,input FROM tasks WHERE trigger_key LIKE ? ORDER BY id",
                          ("multimodal-v1:" + name + ":%",)).fetchall()
    registrations = [m.c.read(p)["material"]["saved_agent_task"]["id"] for p in
                     (m.c.Registry(name).root / "registrations").glob("*.json")]
    result = []
    for identity, trigger, state, reason, encoded in rows:
        saved = m.task(identity)
        source = m.j.loads(encoded)
        result.append(dict(id=identity, trigger_key=trigger, status=state, reason=reason,
            source_day=source["source_day"], input_snapshot_sha256=source["summary"]["input_snapshot_sha256"],
            current_snapshot_sha256=current["saved"]["snapshot_sha256"],
            current_source_day=current["saved"]["content"]["last_valid_source_day"],
            current_source_identity_sha256=m.e.digest(current["identity"]),
            frozen_input_sha256=m.e.digest(source), calls=saved["calls"],
            registrations=registrations.count(str(identity))))
    return result


def clock_bridge(name, key, at, *, global_tick=False):
    suffix = ".exe" if os.name == "nt" else ""
    choices = [p for p in (ROOT / "target/debug/deps").glob("multimodal_agent-*" + suffix)
               if p.is_file() and (os.name == "nt" or p.suffix == "")]
    assert choices, "cargo test -p stratide-research --bin multimodal-agent --no-run first"
    exe = max(choices,key=lambda p:p.stat().st_mtime_ns)
    result = subprocess.run([str(exe),"--exact","tests::routing_fixture","--nocapture"],
        input=m.j.canonical(dict(args=["tick",name,key],now_ms=at,global_tick=global_tick)),
        env=dict(os.environ,STRATIDE_MM_ROUTING_TEST="1"),capture_output=True,timeout=60)
    found = re.search(rb"MM_ROUTING_RESULT=(\{[^\n]+\})",result.stdout)
    assert result.returncode == 0 and found,(result.stdout,result.stderr)
    parsed = m.j.loads(found[1])
    f.COMMANDS.append(dict(command=["multimodal-agent libtest clock",name,key],at=at,
                         global_tick=global_tick,exit_code=parsed["exit_code"]))
    assert parsed["exit_code"] == 0,parsed
    return parsed["value"]


class RoutingTests(unittest.TestCase):
    def test_two_sources_tick_targets_b(self):
        a, akey, _, _ = queued("route-a")
        b, bkey, _, _ = queued("route-b")
        before = dict(a=facts(a), b=facts(b))
        actual_b = bridge("tick", b, bkey)
        self.assertEqual(actual_b["status"], "completed", "B tick executed a different queued task")
        self.assertEqual(facts(a), before["a"], "B tick changed A's original task/calls")
        bdone = f.call(b, "once")
        self.assertEqual(bdone["state"], "ARCHIVED")
        self.assertEqual(f.counts(b), (1, 1))
        self.assertEqual(f.call(a, "once")["state"], "ARCHIVED")
        self.assertEqual(f.counts(a), (1, 1))
        RESULTS.append(dict(check="two_sources_exact_task", before=before, after=dict(a=facts(a), b=facts(b))))

    def test_changed_source_terminates_a_then_new_experiment_b_runs(self):
        name, akey, source, events = queued("changed-source")
        original = facts(name)[0]
        # A same-day duplicate is a new Snapshot but not a price revision;
        # a separate explicit experiment B may use the new verified input.
        close = format(f.Decimal(events[-1]["outcome"]["bar"]["close_fen"])/100,".2f")
        f.f.append_day(events,f.DAYS[-1],close=close)
        f.f.save_journal(source,events)
        self.assertTrue(m.d.Store(name).sync()["can_research"])
        self.assertEqual(f.call(name,"once",code=2)["reason"],"SOURCE_CHANGED_REVIEW_REQUIRED")
        rejected = facts(name)[0]
        self.assertEqual(rejected["status"],"cancelled")
        self.assertEqual(rejected["calls"],[])
        self.assertEqual(rejected["registrations"],0)
        self.assertNotEqual(rejected["current_snapshot_sha256"],rejected["input_snapshot_sha256"])
        f.call(name,"experiment","--label","new-verified-snapshot")
        b = f.call(name,"once")
        self.assertEqual(b["state"],"ARCHIVED")
        self.assertNotEqual(b["task_id"],akey)
        self.assertNotEqual(b["input_snapshot_sha256"],original["input_snapshot_sha256"])
        self.assertEqual(facts(name)[0],rejected)
        self.assertEqual(facts(name)[1]["registrations"],1)
        self.assertEqual(f.counts(name),(2,1))
        RESULTS.append(dict(check="changed_source_new_experiment",before=original,after=facts(name)))

    def test_actual_task_gate_blocks_revision_expiry_and_disabled_global_claims(self):
        for scenario in ("revision","expiry","disabled"):
            a, akey, source, events = queued("gate-" + scenario)
            b, bkey, _, _ = queued("other-" + scenario)
            at = m.s.clock_ms()
            if scenario == "revision":
                f.f.append_day(events,f.DAYS[-1],close="11.50")
                f.f.save_journal(source,events)
                self.assertTrue(m.d.Store(a).sync()["can_research"])
                expected = "MULTIMODAL_SNAPSHOT_CHANGED"
            elif scenario == "expiry":
                at = int(dt.datetime.combine(f.TODAY+dt.timedelta(days=1),dt.time(16,0),m.j.ZONE).timestamp()*1000)
                expected = "MISSED_OR_STALE"
            else:
                f.call(a,"disable")
                expected = "OWNER_DISABLED"
            before = dict(a=facts(a),b=facts(b))
            self.assertEqual(bridge("tick",b,bkey)["status"],"completed")
            self.assertEqual(facts(a),before["a"])
            if scenario != "expiry":
                at = m.s.clock_ms()  # after the revision's actual sync commit
            # Also test the original global Agent tick, bypassing bridge-side
            # target/source checks. The ACTUAL A must still fail before reserve.
            a_result = clock_bridge(a,akey,at,global_tick=True)
            self.assertEqual(a_result["status"],"cancelled")
            self.assertEqual(a_result["reason"],expected)
            self.assertEqual(a_result["calls"],[])
            self.assertEqual(bridge("tick",a,akey)["status"],"cancelled")
            self.assertEqual(f.call(b,"once")["state"],"ARCHIVED")
            self.assertEqual(facts(a)[0]["registrations"],0)
            self.assertEqual(facts(b)[0]["registrations"],1)
            RESULTS.append(dict(check="actual_global_task_gate",scenario=scenario,before=before,
                                after=dict(a=facts(a),b=facts(b))))

    def test_cross_task_kill_restart_and_settled_recovery_do_not_reexecute(self):
        a,akey,_,_ = queued("kill-a")
        b,bkey,_,_ = queued("kill-b")
        original_a = facts(a)
        # B resumes its existing queued intent, settles, then dies before Inbox.
        f.finish(f.launch(b,"once",fixture=True,fault="after_fusion"),86)
        self.assertEqual(facts(a),original_a)
        self.assertEqual(f.counts(b),(1,1))
        self.assertEqual(facts(b)[0]["registrations"],0)
        recovered = f.call(b,"once")
        self.assertEqual(recovered["task_id"],bkey)
        self.assertEqual(recovered["state"],"ARCHIVED")
        self.assertTrue(f.call(b,"once")["reused"])
        self.assertEqual(f.counts(b),(1,1))
        self.assertEqual(facts(a),original_a)
        self.assertEqual(f.call(a,"once")["task_id"],akey)
        self.assertEqual(f.counts(a),(1,1))
        RESULTS.append(dict(check="cross_task_kill_settled_restart",after=dict(a=facts(a),b=facts(b)),
                            abrupt_exit_code=86,duplicate_calls=0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="append")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    suite = (unittest.TestSuite(RoutingTests(name) for name in args.test) if args.test else
             unittest.defaultTestLoader.loadTestsFromTestCase(RoutingTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=True)
        payload = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                       results=RESULTS, commands=f.COMMANDS, public_requests=0, true_paid_calls=0,
                       independent_acceptance="NOT_VERIFIED")
        paths = ((str(ROOT),"<checkout>"),(ROOT.as_posix(),"<checkout>"),
                 (str(m.s.common_root()),"<authority>"),(sys.executable,"python"))
        def portable(value):
            if isinstance(value,str):
                for original,replacement in paths:
                    value = value.replace(original,replacement)
                return value
            if isinstance(value,dict):
                return {key:portable(item) for key,item in value.items()}
            if isinstance(value,list):
                return [portable(item) for item in value]
            return value
        text = json.dumps(portable(payload), ensure_ascii=False, indent=2)
        (args.evidence / "routing.json").write_bytes((text + "\n").encode())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
