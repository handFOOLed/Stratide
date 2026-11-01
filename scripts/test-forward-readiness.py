"""PR53 actual journal/PR33/receipt/Rust fake E2E. All created data is synthetic.

Clock/fault injection is confined to this test program. Production capture CLI
has no historical acquisition, force, synthetic-to-forward or clock option.
"""
import argparse
import copy
import datetime as dt
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "scripts"))
import forward_readiness as r
import forward_evidence as evidence
import multimodal as m

spec = importlib.util.spec_from_file_location("pr53_mm_fixtures", ROOT / "scripts/test-multimodal-research.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
RUN = "mm-test-fr-" + os.urandom(4).hex()
WORK = ROOT / "state/forward-readiness-tests" / RUN
RESULTS = []


def cli(name, command, *args, code=0):
    command = [sys.executable, "-I", "-B", str(ROOT / "scripts/forward-research-readiness.py"),
               "--name", name, command, *map(str, args)]
    p = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=90)
    if p.returncode != code:
        raise AssertionError((command, p.returncode, p.stdout[:1500], p.stderr[:1500]))
    return m.j.loads(p.stdout)


def setup(label, *, days=23, capture=True, skip=None, missing=None, late=None, falling=False, final=None, revise_first=False):
    name = RUN + "-" + label + "-" + os.urandom(2).hex()
    work = WORK / name
    work.mkdir(parents=True)
    journal = work / "forward.sqlite"
    selected = f.DAYS[-days:]
    events = f.f.base_events()[:1]
    events[0]["config"]["observation_id"] = name
    events[0]["started_at"] = f.f.stamp(selected[0]) - 1000
    document = b"Synthetic independent source contract: complete all price-affecting corporate actions for the stated instrument and inclusive range."
    (work / "contract.txt").write_bytes(document)
    contract = dict(schema_version=1, source_id="synthetic-independent-action-feed", kind="synthetic_test",
                    version="1", publisher_url=None, permission_basis="synthetic_test_no_provider_or_market_data",
                    completeness_scope=evidence.COMPLETE, completeness_quote=document.decode(),
                    document_sha256=m.j.sha(document), review_method="operator_manual_document_text_crosscheck",
                    document_path="contract.txt")
    contract_path = work / "contract.json"
    m.c.write(contract_path, contract)
    store = r.Store(name)
    first = True
    for i, day in enumerate(selected):
        if day == skip:
            continue
        f.f.append_day(events, day, close=format((1080-i*2 if falling else 1000+i*2) / 100, ".2f"))
        if i == 0 and revise_first:
            f.f.append_day(events, day, close="11.50")
        f.f.save_journal(journal, events)
        at = f.f.stamp(day) + 60000
        with patch.object(m.d, "now", return_value=at):
            result = m.d.Store(name).sync(journal)
        assert result["latest_attempt"]["state"] == "succeeded", result
        test_store = r.Store(name, clock=lambda at=at: at + 1000)
        if first:
            test_store.init(m.d.Store(name).root)
            test_store.configure_source(contract_path)
            first = False
        if not capture or day == missing:
            continue
        value = dict(schema_version=1, source_id=contract["source_id"], source_version="1", instrument="600000.SH",
                     as_of_day=day, covered_from=selected[i-1] if i else day, covered_through=day,
                     complete_scope=evidence.COMPLETE, publisher_generated_at=at-1000,
                     revision="synthetic-" + day, supersedes=None, events=[])
        if final and day == selected[-1]:
            final(value)
        path = work / (day + ".json")
        m.c.write(path, value)
        r.Store(name, clock=lambda at=at, day=day: at + 1000 + (86400000 if day == late else 0)).capture(path)
    return dict(name=name, store=store, work=work, journal=journal, events=events, contract=contract,
                contract_path=contract_path, days=selected)


def research(ctx, enabled=True):
    name = ctx["name"]
    f.call(name, "init", "--snapshot-store", name, "--readiness-store", name)
    if enabled:
        f.call(name, "enable")


def candidate_count(name):
    return len(list((m.c.Registry(name).root / "registrations").glob("*.json")))


def sql(path, statement, params=()):
    with sqlite3.connect(path) as db:
        db.execute(statement, params)


def queued(ctx):
    research(ctx)
    f.finish(f.launch(ctx["name"], "once", fixture=True, fault="after_queue"), 86)
    entry = m.Run(ctx["name"]).entries()[-1]
    intent = m.j.loads(m.meta()["mm_intent:" + ctx["name"] + ":" + entry["task_id"]])
    original = m.Run(ctx["name"]).task_for(intent)
    assert original["status"] == "queued" and not original["calls"]
    return entry["task_id"], original["id"]


class ReadinessTests(unittest.TestCase):
    def assert_blocked(self, ctx, blocker):
        result = ctx["store"].audit()
        self.assertEqual(result["forward_research_readiness"], "BLOCKED")
        self.assertIn(blocker, result["blockers"])
        research(ctx)
        f.call(ctx["name"], "once", code=2)
        self.assertEqual(f.counts(ctx["name"]), (0, 0))
        self.assertEqual(candidate_count(ctx["name"]), 0)
        return result

    def test_01_two_independent_journals_daily_coverage_original_fusion_and_inbox(self):
        for label, falling in (("positive-a", False), ("positive-b", True)):
            ctx = setup(label, falling=falling)
            name = ctx["name"]
            protected = f.fingerprint([ctx["journal"], m.d.Store(name).root])
            report = cli(name, "audit")
            self.assertEqual(report["forward_research_readiness"], "ALLOW_RESEARCH_ONLY")
            self.assertEqual(report["input_mode"], "synthetic_test")
            self.assertEqual(report["real_on_day_sessions"], 0)
            self.assertEqual(len(report["daily_evidence"]), 21)
            self.assertEqual({x["status"] for x in report["daily_evidence"]}, {"NO_ACTION_WITH_VERIFIED_COVERAGE"})
            self.assertEqual(cli(name, "audit")["receipt_sha256"], report["receipt_sha256"])
            receipt_before = f.fingerprint([ctx["store"].path])
            for command in ("status", "verify", "report"):
                self.assertEqual(cli(name, command)["receipt_sha256"], report["receipt_sha256"])
            self.assertEqual(receipt_before, f.fingerprint([ctx["store"].path]))
            research(ctx)
            complete = f.call(name, "once")
            self.assertEqual(complete["state"], "ARCHIVED")
            self.assertEqual(f.counts(name), (1, 1))
            self.assertEqual(candidate_count(name), 1)
            original = m.task(complete["agent_task_id"])
            ref = original["input"]["summary"]["research_readiness_receipt"]
            self.assertEqual(ref["receipt_sha256"], report["receipt_sha256"])
            self.assertEqual(original["calls"][0]["state"], "settled")
            self.assertTrue(f.call(name, "once")["reused"])
            inbox = f.call(name, "report", complete["task_id"])
            self.assertEqual(inbox["state"], "ARCHIVED")
            self.assertFalse(inbox["live_allowed"])
            self.assertFalse(inbox["can_execute_forward_paper"])
            after = f.fingerprint([ctx["journal"], m.d.Store(name).root])
            self.assertEqual(protected, after, {Path(k).name: (v, after.get(k)) for k, v in protected.items() if after.get(k) != v})
            RESULTS.append(dict(check=label, snapshot_sha256=report["input_snapshot_sha256"],
                receipt_sha256=report["receipt_sha256"], evidence_head_sha256=report["evidence_head_sha256"],
                task_id=complete["task_id"], agent_task_id=complete["agent_task_id"],
                daily_rows=21, tasks=1, fake_calls=1, registrations=1, real_forward_days_added=0,
                protected_original_bytes_and_mtime_unchanged=True))

    def test_02_insufficient_calendar_gap_missing_feed_and_fake_no_event(self):
        cases = [("short", dict(days=20), "INSUFFICIENT_FORWARD_HISTORY"),
                 ("gap", dict(skip=f.DAYS[-6]), "FORWARD_COVERAGE_GAP"),
                 ("no-feed", dict(capture=False), "ACTION_FEED_UNAVAILABLE"),
                 ("missing", dict(missing=f.DAYS[-4]), "COVERAGE_NOT_ATTESTED"),
                 ("empty-not-proof", dict(final=lambda x: x.update(complete_scope=None)), "COVERAGE_NOT_ATTESTED"),
                 ("future-publisher", dict(final=lambda x: x.update(publisher_generated_at=f.f.stamp(f.DAYS[-1])+86400000)),
                  "ACTION_FUTURE_PUBLICATION")]
        for label, options, reason in cases:
            with self.subTest(label=label):
                result = self.assert_blocked(setup(label, **options), reason)
                RESULTS.append(dict(check=label, blockers=result["blockers"], fake_calls=0, registrations=0))

    def test_03_ex_post_acquisition_never_rewrites_original_failure(self):
        ctx = setup("late", capture=False)
        name, store = ctx["name"], ctx["store"]
        blocked = store.audit()
        day = ctx["days"][-4]
        payload = dict(schema_version=1, source_id=ctx["contract"]["source_id"], source_version="1", instrument="600000.SH",
                       as_of_day=ctx["days"][-1], covered_from=ctx["days"][0], covered_through=ctx["days"][-1],
                       complete_scope=evidence.COMPLETE, publisher_generated_at=f.f.stamp(day),
                       revision="downloaded-today-not-observed-then", supersedes=None, events=[])
        path = ctx["work"] / "ex-post.json"
        m.c.write(path, payload)
        store.capture(path)
        updated = store.audit()
        self.assertNotEqual(blocked["receipt_sha256"], updated["receipt_sha256"])
        self.assertIn("COVERAGE_NOT_ATTESTED", updated["blockers"])
        self.assertEqual(cli(name, "verify", "--receipt", blocked["receipt_sha256"], code=2), blocked)
        # Actual late capture for a stale original source is retained as late.
        late_ctx = setup("late-last", late=f.DAYS[-1])
        with patch.object(late_ctx["store"], "clock", return_value=f.f.stamp(f.DAYS[-1])+86400000+100000):
            report = late_ctx["store"].audit()
        self.assertIn("PIT_NOT_PROVEN", report["blockers"])
        RESULTS.append(dict(check="ex_post_cannot_backfill", prior_receipt_retained=True,
                            new_receipt=updated["receipt_sha256"], blockers=updated["blockers"]))

    def test_04_real_event_units_dates_partial_facts_and_price_semantics(self):
        facts = dict.fromkeys(evidence.ca.FIELDS)
        facts.update(symbol="600000.SH", event_id="synthetic-dividend", event_type="CASH_DIVIDEND",
                     record_date="2026-07-15", ex_date="2026-07-16", scheduled_pay_date="2026-07-16",
                     cash_amount="0.42", cash_unit="CNY_PER_SHARE", currency="CNY", tax_basis="GROSS")
        partial = copy.deepcopy(facts)
        partial["cash_amount"] = None
        ctx = setup("event", final=lambda p: p.update(events=[partial]))
        self.assert_blocked(ctx, "EVENT_FACT_PARTIAL")
        for field, bad in (("currency", "USD"), ("cash_unit", "CNY"), ("cash_amount", "-0.42"),
                           ("scheduled_pay_date", "2026-07-10"), ("symbol", "000001.SZ")):
            altered = copy.deepcopy(facts)
            altered[field] = bad
            with self.subTest(field=field), self.assertRaises((m.j.Rejected, ValueError)):
                evidence.event_facts(altered, "600000.SH")
        RESULTS.append(dict(check="event_never_adjusts_or_books_money", event_blockers=["EVENT_FACT_PARTIAL", "PRICE_SEMANTICS_UNSAFE"],
                            unit_date_symbol_rejections=5, actual_account_cash_assertions=0))

    def test_05_sha_editing_json_mode_and_owner_disable_are_not_authority(self):
        ctx = setup("tamper")
        report = ctx["store"].audit()
        with ctx["store"].connect() as db:
            original, _ = ctx["store"].verify(report["receipt_sha256"])
        forged = copy.deepcopy(original)
        forged["result"]["forward_research_readiness"] = "ALLOW_RESEARCH_ONLY"
        forged["result"]["historical_pit_status"] = "VERIFIED"
        key = r.digest(forged)
        sql(ctx["store"].path, "INSERT INTO receipts VALUES(?,?)", (key, m.j.canonical(forged).decode()))
        with self.assertRaisesRegex(m.j.Rejected, "READINESS_REPLAY_MISMATCH"):
            ctx["store"].verify(key)
        raw = m.c.read(ctx["work"] / (ctx["days"][-1] + ".json"))
        raw["ready"] = True
        m.c.write(ctx["work"] / "forged-flag.json", raw)
        with self.assertRaisesRegex(m.j.Rejected, "ACTION_PAYLOAD_SCHEMA"):
            ctx["store"].capture(ctx["work"] / "forged-flag.json")
        contract = copy.deepcopy(ctx["contract"])
        contract["kind"] = "official_event_feed"
        contract["version"] = "2"
        m.c.write(ctx["work"] / "mode.json", contract)
        with self.assertRaisesRegex(m.j.Rejected, "ACTION_SOURCE_MODE_MISMATCH"):
            ctx["store"].configure_source(ctx["work"] / "mode.json")
        research(ctx, enabled=False)
        f.call(ctx["name"], "once", code=2)
        self.assertEqual(f.counts(ctx["name"]), (0, 0))
        with ctx["store"].connect() as db:
            blob = db.execute("SELECT sha,content FROM blobs LIMIT 1").fetchone()
        sql(ctx["store"].path, "UPDATE blobs SET content=? WHERE sha=?", (blob[1]+b"tampered", blob[0]))
        with self.assertRaisesRegex(m.j.Rejected, "READINESS_BLOB_SHA"):
            ctx["store"].verify()
        RESULTS.append(dict(check="forged_flag_hash_mode_owner", rejections=5, fake_calls=0, registrations=0))

    def test_06_queued_actual_rust_task_rechecks_receipt_and_original_journal(self):
        for mutation in ("receipt", "raw-journal", "owner"):
            with self.subTest(mutation=mutation):
                ctx = setup("queue-" + mutation)
                ctx["store"].audit()
                key, identity = queued(ctx)
                if mutation == "receipt":
                    value = dict(ctx["contract"], version="2")
                    m.c.write(ctx["work"] / "v2.json", value)
                    ctx["store"].configure_source(ctx["work"] / "v2.json")
                elif mutation == "raw-journal":
                    f.f.append_day(ctx["events"], ctx["days"][-1], close="11.50")
                    f.f.save_journal(ctx["journal"], ctx["events"])
                else:
                    f.call(ctx["name"], "disable")
                # Invoke Rust directly: bypass the Python runner's recheck.
                m.bridge("tick", ctx["name"], key)
                task = m.task(identity)
                self.assertEqual(task["status"], "cancelled")
                self.assertEqual(task["calls"], [])
                self.assertEqual(candidate_count(ctx["name"]), 0)
                RESULTS.append(dict(check="actual_rust_pre_reserve_" + mutation, task_status=task["status"],
                                    reason=task["reason"], calls=0, registrations=0))

    def test_07_source_revision_late_backfill_and_receipt_replay(self):
        ctx = setup("revised")
        old = ctx["store"].audit()
        f.f.append_day(ctx["events"], ctx["days"][-1], close="11.50")
        f.f.save_journal(ctx["journal"], ctx["events"])
        current = ctx["store"].audit()
        self.assertIn("SOURCE_CHANGED_SINCE_SYNC", current["blockers"])
        m.d.Store(ctx["name"]).sync()
        revised = ctx["store"].audit()
        self.assertIn("REVISED_OR_LATE_SOURCE_REJECTED", revised["blockers"])
        self.assertEqual(cli(ctx["name"], "verify", "--receipt", old["receipt_sha256"]), old)
        raw = m.c.read(ctx["work"] / (ctx["days"][-1] + ".json"))
        raw["supersedes"], raw["revision"] = raw["revision"], "correction-v2"
        missed = dict.fromkeys(evidence.ca.FIELDS)
        missed.update(symbol="600000.SH", event_id="synthetic-missed-action", event_type="CASH_DIVIDEND")
        raw["events"] = [missed]
        m.c.write(ctx["work"] / "correction.json", raw)
        ctx["store"].capture(ctx["work"] / "correction.json")
        corrected = ctx["store"].audit()
        self.assertIn("ACTION_SOURCE_REVISED", corrected["blockers"])
        self.assertIn("ACTION_SOURCE_CONFLICT", corrected["blockers"])
        self.assertEqual(cli(ctx["name"], "verify", "--receipt", old["receipt_sha256"]), old)
        RESULTS.append(dict(check="source_revision_and_action_correction", old_receipt_unchanged=True,
                            blockers=corrected["blockers"]))

    def test_08_freshness_asof_label_clock_and_malicious_paths(self):
        ctx = setup("quality")
        original = r.source(m.d.Store(ctx["name"]).root)
        at = m.s.clock_ms()
        with ctx["store"].connect() as db:
            captures, _ = ctx["store"].evidence(db, ctx["store"].control(db)[1])
        variants = [lambda v: v["versions"][-1].update(available_at=at+86400000),
                    lambda v: v["versions"][-1]["bar"].update(next_day_return=".5"),
                    lambda v: v["versions"][-1]["bar"].update(price_semantics="adjusted"),
                    lambda v: v.update(as_of_journal_event_at=at+86400000),
                    lambda v: v.update(data_mode="historical_replay")]
        for mutate in variants:
            src = copy.deepcopy(original)
            mutate(src["saved"]["content"])
            self.assertEqual(r.assess(src, captures, at)["forward_research_readiness"], "BLOCKED")
        self.assertIn("MISSED_OR_STALE", r.assess(original, captures, at+86400000)["blockers"])
        invalid_ref = r.assess(original, [], at, references=[dict(error_code="PR38_EVIDENCE_INVALID")])
        self.assertIn("PR38_EVIDENCE_INVALID", invalid_ref["blockers"])
        self.assertEqual(invalid_ref["source_evidence_status"], "UNKNOWN")
        ctx["store"].audit()
        with self.assertRaisesRegex(m.j.Rejected, "READINESS_CLOCK_REGRESSED"):
            r.Store(ctx["name"], clock=lambda: at-86400000).audit()
        with self.assertRaises(m.j.Rejected):
            r.Store("../outside")
        manifest = dict(ctx["contract"], document_path="../outside.txt", version="2")
        m.c.write(ctx["work"] / "path.json", manifest)
        with self.assertRaises(m.j.Rejected):
            ctx["store"].configure_source(ctx["work"] / "path.json")
        RESULTS.append(dict(check="freshness_asof_label_clock_paths", rejections=9))

    def test_09_publication_interruptions_recovery_duplicate_and_concurrent_runs(self):
        ctx = setup("recovery")
        for point in ("before_publish", "before_commit", "after_commit"):
            request = dict(name=ctx["name"], fault=point)
            path = ctx["work"] / (point + ".request.json")
            m.c.write(path, request)
            p = subprocess.run([sys.executable, "-B", str(Path(__file__).absolute()), "--fixture-request", str(path)],
                               cwd=ROOT, capture_output=True, timeout=90)
            self.assertEqual(p.returncode, 86, (p.stdout, p.stderr))
            recovered = cli(ctx["name"], "audit")
            self.assertEqual(recovered["forward_research_readiness"], "ALLOW_RESEARCH_ONLY")
            self.assertEqual(cli(ctx["name"], "verify")["receipt_sha256"], recovered["receipt_sha256"])
        command = [sys.executable, "-B", str(ROOT / "scripts/forward-research-readiness.py"), "--name", ctx["name"], "audit"]
        processes = [subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        codes, hashes = [], []
        for process in processes:
            out, err = process.communicate(timeout=90)
            codes.append(process.returncode)
            value = m.j.loads(out)
            if process.returncode == 0:
                hashes.append(value["receipt_sha256"])
            else:
                self.assertEqual(value["error_code"], "STORE_BUSY", (out, err))
        self.assertIn(0, codes)
        self.assertEqual(len(set(hashes)), 1)
        RESULTS.append(dict(check="process_exit86_three_publication_points_and_concurrent", exits=[86]*3,
                            recovery="PASS", concurrent_exit_codes=codes, duplicate_receipt_stable=True))

    def test_10_settled_kill_restart_never_recharges_and_other_task_cannot_attest(self):
        a, b = setup("cross-a"), setup("cross-b", falling=True)
        a["store"].audit()
        b["store"].audit()
        key, identity = queued(a)
        contract = dict(a["contract"], version="2")
        m.c.write(a["work"] / "v2.json", contract)
        a["store"].configure_source(a["work"] / "v2.json")
        research(b)
        f.finish(f.launch(b["name"], "once", fixture=True, fault="after_fusion"), 86)
        self.assertEqual(f.counts(b["name"]), (1, 1))
        self.assertEqual(m.task(identity)["status"], "queued")
        self.assertEqual(f.call(b["name"], "once")["state"], "ARCHIVED")
        self.assertEqual(f.counts(b["name"]), (1, 1))
        self.assertEqual(candidate_count(b["name"]), 1)
        m.bridge("tick", a["name"], key)
        self.assertEqual(m.task(identity)["status"], "cancelled")
        self.assertEqual(f.counts(a["name"]), (1, 0))
        self.assertEqual(candidate_count(a["name"]), 0)
        RESULTS.append(dict(check="exact_task_and_settled_restart", invalid_a_calls=0, valid_b_calls=1,
                            valid_b_registrations=1, duplicate_charges=0))

    def test_11_a_later_clean_21_session_window_recovers_without_rewriting_old_observations(self):
        for label, options in (("old-gap", dict(days=25, skip=f.DAYS[-24])),
                               ("old-revision", dict(days=25, revise_first=True))):
            ctx = setup(label, **options)
            before = f.fingerprint([ctx["journal"], m.d.Store(ctx["name"]).root])
            report = ctx["store"].audit()
            self.assertEqual(report["forward_research_readiness"], "ALLOW_RESEARCH_ONLY")
            research(ctx)
            self.assertEqual(f.call(ctx["name"], "once")["state"], "ARCHIVED")
            self.assertEqual(before, f.fingerprint([ctx["journal"], m.d.Store(ctx["name"]).root]))
            RESULTS.append(dict(check=label + "_new_clean_window", receipt_sha256=report["receipt_sha256"],
                                prior_versions_preserved=True, original_bytes_and_mtime_unchanged=True))

    def test_12_original_dispatch_gate_releases_reservation_after_owner_disable(self):
        ctx = setup("dispatch")
        ctx["store"].audit()
        key, identity = queued(ctx)
        # Deterministic fault in the original synthetic task's reserve COMMIT.
        # The first source check passes; dispatch MUST run its own second gate.
        # No production hook or budget arithmetic change is needed.
        trigger = "pr53_dispatch_fault_" + str(int(identity))
        with m.agent_db(write=True) as db:
            db.execute(f"CREATE TRIGGER {trigger} AFTER INSERT ON calls WHEN NEW.task_id={int(identity)} "
                       f"BEGIN UPDATE meta SET value='false' WHERE key='mm_enabled:{ctx['name']}'; END")
        try:
            m.bridge("tick", ctx["name"], key)
        finally:
            with m.agent_db(write=True) as db:
                db.execute(f"DROP TRIGGER {trigger}")
        task = m.task(identity)
        self.assertEqual(task["status"], "cancelled")
        self.assertEqual(task["reason"], "OWNER_DISABLED")
        self.assertEqual(len(task["calls"]), 1)
        self.assertEqual(task["calls"][0]["state"], "no_charge")
        self.assertEqual(candidate_count(ctx["name"]), 0)
        f.call(ctx["name"], "enable")
        self.assertEqual(f.call(ctx["name"], "once", code=2)["state"], "FUSION_FAILED")
        self.assertEqual(f.counts(ctx["name"]), (1, 1))
        RESULTS.append(dict(check="actual_dispatch_gate_after_reserve_commit", status="cancelled",
                            reason="OWNER_DISABLED", reserved_call_records=1, call_state="no_charge",
                            dispatched_calls=0, registrations=0, reenable_does_not_resend=True))

    def test_13_on_day_complete_evidence_and_identical_fact_refresh_create_new_receipts(self):
        ctx = setup("refresh", final=lambda p: p.update(complete_scope=None))
        old = ctx["store"].audit()
        self.assertEqual(old["forward_research_readiness"], "BLOCKED")
        path = ctx["work"] / (ctx["days"][-1] + ".json")
        payload = m.c.read(path)
        payload.update(complete_scope=evidence.COMPLETE, revision="complete-on-day-v2")
        fresh = ctx["work"] / "complete.json"
        m.c.write(fresh, payload)
        ctx["store"].capture(fresh)
        ready = ctx["store"].audit()
        self.assertEqual(ready["forward_research_readiness"], "ALLOW_RESEARCH_ONLY")
        self.assertNotEqual(old["receipt_sha256"], ready["receipt_sha256"])
        self.assertEqual(cli(ctx["name"], "verify", "--receipt", old["receipt_sha256"], code=2), old)
        key, identity = queued(ctx)
        payload.update(publisher_generated_at=payload["publisher_generated_at"]+1, revision="same-facts-refresh-v3")
        m.c.write(fresh, payload)
        ctx["store"].capture(fresh)
        newer = ctx["store"].audit()
        self.assertEqual(newer["forward_research_readiness"], "ALLOW_RESEARCH_ONLY")
        self.assertNotEqual(ready["receipt_sha256"], newer["receipt_sha256"])
        m.bridge("tick", ctx["name"], key)
        self.assertEqual(m.task(identity)["status"], "cancelled")
        self.assertEqual(m.task(identity)["calls"], [])
        RESULTS.append(dict(check="on_day_complete_then_unchanged_fact_refresh", old_failure_retained=True,
                            new_qualified_receipts=2, old_queued_calls=0, old_queued_status="cancelled"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--fixture-request", type=Path)
    parser.add_argument("--case")
    parser.add_argument("--real-snapshot", type=Path)
    parser.add_argument("--real-observer", type=Path)
    parser.add_argument("--real-corporate-action-bundle", type=Path)
    args = parser.parse_args()
    if args.real_snapshot:
        assert args.real_observer and args.real_corporate_action_bundle and args.evidence
        args.real_observer = args.real_observer.absolute()
        args.real_corporate_action_bundle = args.real_corporate_action_bundle.absolute()
        snapshot = r.snapshot_ref(args.real_snapshot)
        src = r.source(snapshot.path)
        assert src["saved"]["content"]["data_mode"] == "forward_observed_eod"
        assert Path(src["binding"]["source"]["path"]).resolve() == args.real_observer.resolve()
        protected_paths = [args.real_observer, snapshot.path.parent, args.real_corporate_action_bundle]
        before = f.fingerprint(protected_paths)
        name = "real-forward-audit-" + os.urandom(6).hex()
        cli(name, "init", "--snapshot-store", snapshot.path.parent,
            "--corporate-action-bundle", args.real_corporate_action_bundle)
        result = cli(name, "audit", code=2)
        assert result["forward_research_readiness"] == "BLOCKED"
        assert result["real_on_day_sessions"] == src["saved"]["content"]["on_day_valid_eod_days"]
        for command in ("status", "verify", "report"):
            assert cli(name, command, code=2) == result
        # Independent hashlib/raw reconstruction, outside the receipt code.
        import hashlib
        raw_count = 0
        with m.s.readonly(args.real_observer) as db:
            rows = db.execute("SELECT seq,payload,digest FROM events ORDER BY seq").fetchall()
        for _, payload, _ in rows:
            event = m.j.loads(payload)
            for raw in event.get("outcome", {}).get("raw", []):
                assert hashlib.sha256(bytes(raw["body"])).hexdigest() == raw["sha256"]
                raw_count += 1
        with r.Store(name).connect() as db:
            encoded = db.execute("SELECT content FROM receipts WHERE sha=?", (result["receipt_sha256"],)).fetchone()[0]
        assert hashlib.sha256(encoded.encode()).hexdigest() == result["receipt_sha256"]
        assert before == f.fingerprint(protected_paths)
        args.evidence.mkdir(parents=True, exist_ok=True)
        m.c.write(args.evidence / "real-audit.json", dict(result,
            verification=dict(raw_payload_sha256_checked_independently=raw_count,
                              receipt_sha256_checked_independently=True, real_forward_days_added=0,
                              paid_calls=0, public_market_requests=0, candidates=0, orders=0, fills=0),
            source_permission=dict(provider=src["saved"]["content"]["source"],
                raw_kinds=["daily", "trade_cal"], authority="EXISTING_OBSERVER_PERSISTED_LOCAL_STORAGE_GRANT",
                action_feed_authority="ACTION_FEED_UNAVAILABLE_NO_NEW_PROVIDER_REQUEST")))
        labels = {}
        for label, path in zip(("original_observer", "original_pr33_store", "original_pr38_bundle"), protected_paths):
            files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
            labels.update({label + ("/" + file.relative_to(path).as_posix() if path.is_dir() else ""):
                dict(sha256=before[str(file)][1], mtime_ns=before[str(file)][0], bytes=file.stat().st_size,
                     unchanged_sha_and_mtime=True) for file in files})
        m.c.write(args.evidence / "preservation.json", dict(files=labels, unchanged=True,
                    protected_file_count=len(before), source_hashes_only_no_prices_or_private_paths=True))
        print(m.j.canonical(dict(result="BLOCKED_AS_REQUIRED", receipt_sha256=result["receipt_sha256"],
              real_sessions=result["real_on_day_sessions"], blockers=result["blockers"], protected_files=len(before))).decode())
        return 0
    if args.fixture_request:
        request = m.c.read(args.fixture_request)
        assert request["name"].startswith("mm-test-fr-")
        def fault(point):
            if point == request["fault"]:
                os._exit(86)
        r.Store(request["name"], fault=fault).audit()
        return 0
    suite = (unittest.defaultTestLoader.loadTestsFromName(args.case, sys.modules[__name__]) if args.case else
             unittest.defaultTestLoader.loadTestsFromTestCase(ReadinessTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=True)
        m.c.write(args.evidence / "checks.json", dict(schema_version=1, tests=result.testsRun,
            failures=len(result.failures), errors=len(result.errors), results=RESULTS,
            real_forward_days_added=0, real_paid_calls=0, orders=0, fills=0,
            independent_acceptance="NOT_VERIFIED"))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
