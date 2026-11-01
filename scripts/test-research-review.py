"""Actual #44 synthetic archive → production review CLI → original evaluator.

Only this test driver injects process-exit points. No production clock, executable,
provider or failure override exists. New ignored fixtures are retained for review.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import eod_auto as a
import review as r

spec = importlib.util.spec_from_file_location("auto_fixtures", a.ROOT / "scripts/test-eod-auto.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
ROOT = a.ROOT
WORK = ROOT / "state/review-tests" / ("run-" + os.urandom(5).hex())
COMMANDS, CHECKS = [], []
SYNTHETIC = ROOT / "research/synthetic-candidate.example.json"
HISTORICAL = ROOT / "research/fixed-candidate.example.json"
HISTORICAL_SOURCE = None


def setup(label):
    name, observer = f.setup("review-" + label)
    archived = f.call(name, "once")
    return name, archived["registration_sha256"], observer


def launch(name, *args, fault=None):
    if fault:
        request = WORK / (os.urandom(5).hex() + ".json")
        a.c.write(request, dict(args=["--auto", name, *map(str, args)], fault=fault))
        command = [sys.executable, "-B", __file__, "--fixture-cli", str(request)]
    else:
        command = [sys.executable, "-B", str(ROOT / "scripts/research-review.py"), "--auto", name, *map(str, args)]
    return subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def collect(process, args, expected=(0,)):
    out, err = process.communicate(timeout=120)
    if process.returncode not in expected:
        raise AssertionError(f"{args}: {process.returncode}: {out[:2400]!r} {err[:2400]!r}")
    value = json.loads(out) if out else None
    COMMANDS.append(dict(command=list(map(str, args)), exit_code=process.returncode, result=value))
    return process.returncode, value


def call(name, *args, code=0, fault=None):
    return collect(launch(name, *args, fault=fault), args, (code,))[1]


def review_args(parent, owner=SYNTHETIC, evidence="synthetic_test", source=None):
    return ["review", parent, "--owner-input", owner, "--evidence-class", evidence,
            *(["--source-dir", source] if source is not None else [])]


def counts(name):
    registry = a.c.Registry(name)
    values = f.counts(name)
    values.update(review_links=len(list((registry.root / "reviews").glob("*/result.json"))),
                  review_plans=len(list((registry.root / "reviews").glob("*/plan.json"))),
                  review_attempts=len(list((registry.root / "reviews").glob("*/attempt-*.json"))),
                  candidates=len(list((registry.root / "candidates").glob("*/candidate.json"))),
                  evaluation_attempts=len(list((registry.root / "candidates").glob("*/evaluations/*/attempt-*"))),
                  evaluation_receipts=len(list((registry.root / "candidates").glob("*/evaluations/*/result.json"))))
    return values


def preserve(name, parent, observer):
    auto = a.Auto(name)
    files = [auto.dbpath, observer, a.d.Store(name).path,
             a.c.Registry(name).path("registrations", parent).with_suffix(".json")]
    return {str(p): a.c.sha(p) for p in files}


class ReviewTests(unittest.TestCase):
    def test_full_cli_two_directories_and_readonly_inbox_report(self):
        summaries = []
        for label in ("full-a", "full-b"):
            name, parent, observer = setup(label)
            original = preserve(name, parent, observer)
            before = counts(name)
            self.assertEqual(before["registrations"], 1)
            registry = a.c.Registry(name)
            old = a.c.files(registry.root)
            pending = call(name, "inbox")["items"][0]
            self.assertEqual(pending["state"], "AWAITING_OWNER_TEMPLATE")
            self.assertEqual(pending["evaluation"], "NOT_EVALUATED")
            self.assertEqual(call(name, "status", parent)["items"][0], pending)
            self.assertEqual(call(name, "report", parent)["items"][0], pending)
            self.assertEqual(old, a.c.files(registry.root))
            self.assertEqual(before, counts(name))
            evaluated = call(name, *review_args(parent))
            self.assertEqual(evaluated["state"], "EVALUATED")
            self.assertEqual(evaluated["engineering"], "ENGINEERING_PASS")
            self.assertEqual(evaluated["research_evidence"], "SYNTHETIC_TEST_ONLY")
            self.assertEqual(evaluated["agent_hypothesis_validation"], "NOT_ESTABLISHED")
            self.assertFalse(evaluated["forward_paper_allowed"])
            self.assertFalse(evaluated["live_allowed"])
            self.assertEqual(evaluated["handoff"], a.c.handoff(evaluated["candidate_sha256"], evaluated["evaluation_sha256"]))
            child = registry.registration(evaluated["registration_sha256"])["material"]
            self.assertEqual(child["parent_registration_sha256"], parent)
            self.assertEqual(child["owner_input"], a.c.read(SYNTHETIC))
            completed = counts(name)
            self.assertEqual(completed, dict(intents=1, tasks=1, calls=1, registrations=2, review_links=1,
                review_plans=1, review_attempts=1, candidates=1, evaluation_attempts=1, evaluation_receipts=1))
            self.assertTrue(call(name, *review_args(parent))["reused"])
            old = a.c.files(registry.root)
            for args in (("inbox",), ("status",), ("status", parent), ("report", parent)):
                saved = call(name, *args)
                self.assertEqual(saved["items"][0]["state"], "EVALUATED")
                output = json.dumps(saved)
                for forbidden in (str(ROOT), "close_fen", "owner-token", "600000.SH"):
                    self.assertNotIn(forbidden, output)
            self.assertEqual(old, a.c.files(registry.root))
            self.assertEqual(completed, counts(name))
            self.assertEqual(original, preserve(name, parent, observer))
            summaries.append(evaluated["summary"])
            CHECKS.append(dict(check=label, before=before, after=completed, old_sha_unchanged=True,
                               state=evaluated["state"], summary=evaluated["summary"]))
        self.assertEqual(summaries[0], summaries[1])

    def test_four_process_exit_points_resume_and_reuse_original_receipt(self):
        for point in ("before_registration", "after_freeze", "before_evaluate", "after_evaluate"):
            name, parent, observer = setup("kill")
            original = preserve(name, parent, observer)
            args = review_args(parent)
            call(name, *args, fault=point, code=87)
            interrupted = counts(name)
            pending = call(name, "report", parent, code=2)["items"][0]
            self.assertEqual(pending["state"], "REVIEW_REQUIRED")
            self.assertEqual(interrupted, counts(name))
            result = call(name, *args)
            self.assertEqual(result["state"], "EVALUATED")
            final = counts(name)
            self.assertEqual(final["tasks"], 1)
            self.assertEqual(final["calls"], 1)
            self.assertEqual(final["registrations"], 2)
            self.assertEqual(final["review_attempts"], 2)
            self.assertEqual(final["evaluation_attempts"], 1)
            self.assertEqual(final["evaluation_receipts"], 1)
            if point == "after_evaluate":
                self.assertTrue(result["reused"])
            self.assertTrue(call(name, *args)["reused"])
            self.assertEqual(final, counts(name))
            self.assertEqual(original, preserve(name, parent, observer))
            CHECKS.append(dict(check="kill_" + point, exit_code=87, interrupted=interrupted, recovered=final,
                               evaluation_reused=result["reused"], original_sha_unchanged=True))

    def test_two_concurrent_clis_and_renamed_auto_cannot_repeat_research(self):
        name, parent, _ = setup("concurrent")
        args = review_args(parent)
        processes = [launch(name, *args), launch(name, *args)]
        results = [collect(p, args, (0, 2)) for p in processes]
        self.assertIn(0, [code for code, _ in results])
        for code, value in results:
            if code == 2:
                self.assertEqual(value["reason"], "REGISTRY_BUSY")
        call(name, *args)
        final = counts(name)
        self.assertEqual(final["evaluation_attempts"], 1)
        peer = "auto-test-review-peer-" + os.urandom(4).hex()
        f.call(peer, "init", "--snapshot-store", name)
        self.assertEqual(call(peer, "review", parent, "--owner-input", SYNTHETIC,
                              "--evidence-class", "synthetic_test", code=2)["reason"], "EOD_AUTO_BINDING_OWNED")
        self.assertEqual(final, counts(name))
        CHECKS.append(dict(check="concurrent_and_cross_name", exits=[v[0] for v in results], counts=final))

    def test_stale_changed_missing_eod_snapshot_offline_review_never_relabels_current(self):
        name, parent, observer = setup("stale")
        events = f.f.base_events()
        events[-1]["outcome"]["available_at"] += 1
        f.f.save_journal(observer, events)
        # Original current snapshot is deliberately absent. Registered material
        # still exists, and production review uses its historical content address.
        store = a.d.Store(name).path
        store.rename(store.with_suffix(".saved"))
        report = call(name, *review_args(parent))
        provenance = report["parent"]["snapshot_provenance"]
        self.assertEqual(provenance["snapshot_verification"], "SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION")
        self.assertEqual(report["parent"]["current_source_verification"], "NOT_RECHECKED_OFFLINE_REVIEW")
        self.assertEqual(report["task_origin"], "TASK_ORIGIN_NOT_ATTESTED")
        self.assertEqual(report["genuine_new_forward_days"], 0)
        CHECKS.append(dict(check="stale_changed_missing_eod", state=report["state"], provenance=provenance,
                           current_source_verification=report["parent"]["current_source_verification"]))

    def test_moved_review_directory_still_reuses_original_candidate_and_evaluation(self):
        name, parent, _ = setup("moved")
        first = call(name, *review_args(parent))
        registry = a.c.Registry(name)
        (registry.root / "reviews").rename(registry.root / "reviews.saved")
        recovered = call(name, *review_args(parent))
        self.assertTrue(recovered["reused"])
        for key in ("registration_sha256", "candidate_sha256", "evaluation_sha256", "receipt_sha256"):
            self.assertEqual(first[key], recovered[key])
        final = counts(name)
        self.assertEqual(final["candidates"], 1)
        self.assertEqual(final["evaluation_attempts"], 1)
        self.assertEqual(final["registrations"], 2)
        self.assertTrue((registry.root / "reviews.saved" / first["review_sha256"] / "result.json").is_file())
        CHECKS.append(dict(check="moved_review_directory", original_receipt_reused=True, counts=final))

    def test_missing_or_inadequate_history_is_stable_data_blocked_and_new_template_version(self):
        name, parent, _ = setup("blocked")
        missing = WORK / "missing-history"
        args = review_args(parent, HISTORICAL, "historical_replay", missing)
        report = call(name, *args)
        self.assertEqual(report["state"], "DATA_BLOCKED")
        self.assertEqual(report["holdout"], "EX_POST")
        self.assertEqual(report["engineering"], "NOT_RUN")
        before = counts(name)
        self.assertTrue(call(name, *args)["reused"])
        self.assertEqual(before, counts(name))
        bad = WORK / "synthetic-raw-history"
        bad.mkdir()
        for file in a.c.RAW_NAMES:
            a.c.write(bad / file, {"response_kind": "synthetic_test"} if file == "extraction.json" else [])
        report2 = call(name, *review_args(parent, HISTORICAL, "historical_replay", bad))
        self.assertEqual(report2["state"], "DATA_BLOCKED")
        self.assertNotEqual(report["review_sha256"], report2["review_sha256"])
        self.assertEqual(call(name, *review_args(parent))["state"], "EVALUATED")
        self.assertEqual(len(call(name, "report", parent)["items"][0]["versions"]), 3)
        CHECKS.append(dict(check="history_missing_inadequate_versions", states=[report["state"], report2["state"], "EVALUATED"],
                           reasons=[report["reasons"], report2["reasons"]], counts=counts(name)))

    def test_local_historical_source_content_reuse_missing_and_new_version(self):
        name, parent, _ = setup("history")
        if HISTORICAL_SOURCE is None:
            blocked = call(name, *review_args(parent, HISTORICAL, "historical_replay"))
            self.assertEqual(blocked["state"], "DATA_BLOCKED")
            CHECKS.append(dict(check="local_history", state="DATA_BLOCKED", real_history="NOT_PROVIDED"))
            return
        original = {file: a.c.sha(HISTORICAL_SOURCE / file) for file in a.c.RAW_NAMES}
        result = call(name, *review_args(parent, HISTORICAL, "historical_replay", HISTORICAL_SOURCE))
        self.assertEqual(result["state"], "EVALUATED")
        self.assertEqual(result["research_evidence"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["data"]["sessions"], 68)
        self.assertEqual(result["data"]["historical_PIT"], "NOT_VERIFIED")
        self.assertEqual(result["holdout"], "EX_POST")
        equivalent = WORK / "same-history-another-directory"
        equivalent.mkdir()
        for file in a.c.RAW_NAMES:
            shutil.copyfile(HISTORICAL_SOURCE / file, equivalent / file)
        before = counts(name)
        duplicate = call(name, *review_args(parent, HISTORICAL, "historical_replay", equivalent))
        self.assertTrue(duplicate["reused"])
        self.assertEqual(result["review_sha256"], duplicate["review_sha256"])
        self.assertEqual(before, counts(name))
        # Actual source loss creates a new honest blocker, preserving old report.
        (equivalent / "daily.json").rename(equivalent / "daily.saved")
        blocked = call(name, *review_args(parent, HISTORICAL, "historical_replay", equivalent))
        self.assertEqual(blocked["state"], "DATA_BLOCKED")
        self.assertEqual(original, {file: a.c.sha(HISTORICAL_SOURCE / file) for file in a.c.RAW_NAMES})
        self.assertEqual(len(call(name, "report", parent)["items"][0]["versions"]), 2)
        CHECKS.append(dict(check="local_history", state=result["state"], research_evidence=result["research_evidence"],
                           sessions=68, holdout=result["holdout"], identical_directory_reused=True,
                           missing_source_state=blocked["state"], original_source_sha_unchanged=True, counts=counts(name)))

    def test_original_registration_task_call_intent_and_source_sha_tampering_fail_closed(self):
        mutations = ("registration", "task", "call", "intent", "archive", "source_sha", "qualification")
        for mutation in mutations:
            name, parent, _ = setup("tamper")
            auto = a.Auto(name)
            registry = a.c.Registry(name)
            if mutation in ("registration", "qualification"):
                path = registry.path("registrations", parent).with_suffix(".json")
                record = a.c.read(path)
                record["material"]["live_allowed" if mutation == "qualification" else "authority"] = True
                a.c.write(path, record)
            else:
                with auto.db(write=True) as db:
                    if mutation == "task":
                        db.execute("UPDATE tasks SET status='failed' WHERE id=1")
                    elif mutation == "call":
                        db.execute("UPDATE calls SET state='reserved' WHERE task_id=1")
                    elif mutation == "intent":
                        db.execute("UPDATE meta SET value='{}' WHERE key LIKE 'eod_auto_intent:%'")
                    elif mutation == "archive":
                        record = a.j.loads(db.execute("SELECT value FROM meta WHERE key LIKE 'eod_auto_archive:%'").fetchone()[0])
                        record["task_detail_sha256"] = "0" * 64
                        db.execute("UPDATE meta SET value=? WHERE key LIKE 'eod_auto_archive:%'", (json.dumps(record),))
                    else:
                        value = a.j.loads(db.execute("SELECT input FROM tasks WHERE id=1").fetchone()[0])
                        value["summary"]["snapshot_sha256"] = "0" * 64
                        db.execute("UPDATE tasks SET input=? WHERE id=1", (json.dumps(value),))
            before = counts(name)
            blocked = call(name, *review_args(parent), code=2)
            self.assertEqual(blocked["state"], "REVIEW_REQUIRED")
            self.assertEqual(call(name, "inbox", code=2)["items"][0]["state"], "REVIEW_REQUIRED")
            self.assertEqual(before, counts(name))
            CHECKS.append(dict(check="parent_tamper_" + mutation, reason=blocked["reason"], no_new_work=True))

    def test_forged_completed_export_and_fake_directory_do_not_create_inbox_entries(self):
        name, parent, _ = setup("forged")
        auto = a.Auto(name)
        a.c.write(auto.root / "task-export.json", dict(status="completed", live_allowed=True))
        registry = a.c.Registry(name)
        a.c.write(registry.root / "registrations" / ("f" * 64 + ".json"), dict(status="completed"))
        self.assertEqual(call(name, "inbox")["count"], 1)
        self.assertEqual(call(name, *review_args("f" * 64), code=2)["reason"], "ARCHIVED_PARENT_NOT_FOUND")
        self.assertEqual(call(name, *review_args(parent))["state"], "EVALUATED")
        CHECKS.append(dict(check="forged_completed_export_ignored", archive_count=1, task_count=1, fake_call_count=1))

    def test_owner_parameter_injection_and_junction_never_run(self):
        name, parent, _ = setup("owner")
        original = counts(name)
        for mutation in (dict(template_id="powershell"), dict(parameters={"quantity": 999999}),
                         dict(exe="cmd.exe"), dict(endpoint="https://invalid.example"),
                         dict(live_allowed=True), dict(initial_cash_fen=999999999999)):
            owner = WORK / (os.urandom(4).hex() + ".json")
            a.c.write(owner, dict(a.c.read(SYNTHETIC), **mutation))
            self.assertEqual(call(name, *review_args(parent, owner), code=2)["reason"], "OWNER_FIXED_TEMPLATE_REQUIRED")
        target = WORK / "link-target"
        target.mkdir()
        link = WORK / "source-link"
        if os.name == "nt":
            p = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr.decode(errors="replace"))
        else:
            link.symlink_to(target, target_is_directory=True)
        self.assertEqual(call(name, *review_args(parent, HISTORICAL, "historical_replay", link), code=2)["reason"], "LINK_PATH_DENIED")
        self.assertEqual(original, counts(name))
        CHECKS.append(dict(check="owner_parameter_and_link_injection", rejected=7, counts_unchanged=True))

    def test_evaluated_report_receipt_qualification_and_frozen_input_tampering(self):
        for mutation in ("report", "receipt", "qualification", "frozen"):
            name, parent, _ = setup("result")
            evaluated = call(name, *review_args(parent))
            registry = a.c.Registry(name)
            if mutation == "report":
                path = registry.root / evaluated["report_ref"]
                value = a.c.read(path)
                value["report"]["state"] = "PASS"
                a.c.write(path, value)
            elif mutation == "frozen":
                path = registry.path("candidates", evaluated["candidate_sha256"]) / "frozen/audit/input/dataset.json"
                value = a.c.read(path)
                value["sessions"][0]["day"] += 1
                a.c.write(path, value)
            else:
                path = registry.root / evaluated["evaluation_report_ref"]
                value = a.c.read(path)
                if mutation == "receipt":
                    value["receipt"]["engineering"] = "PASS"
                else:
                    value["handoff"]["live_allowed"] = True
                a.c.write(path, value)
            before = counts(name)
            self.assertEqual(call(name, "report", parent, code=2)["items"][0]["state"], "REVIEW_REQUIRED")
            blocked = call(name, *review_args(parent), code=2)
            self.assertEqual(before, counts(name))
            CHECKS.append(dict(check="evaluated_tamper_" + mutation, reason=blocked["reason"], no_rerun=True))

    def test_no_agent_provider_or_replay_on_readonly_queries(self):
        name, parent, _ = setup("readonly")
        # Directly deny all process creation and registry writes in this process.
        with patch.object(a, "bridge", side_effect=AssertionError("Agent invoked")), \
             patch.object(a.c, "invoke", side_effect=AssertionError("replay invoked")), \
             patch.object(a.c, "write", side_effect=AssertionError("query wrote state")), \
             patch("socket.create_connection", side_effect=AssertionError("network")):
            service = r.Review(name)
            self.assertEqual(service.inbox()["items"][0]["state"], "AWAITING_OWNER_TEMPLATE")
            self.assertEqual(service.inbox(parent)["count"], 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-cli", type=Path)
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--historical-source", type=Path, help="existing private frozen raw source; never fetched or modified")
    args, rest = parser.parse_known_args()
    if args.fixture_cli:
        request = a.c.read(args.fixture_cli)
        def fault(point):
            if request["fault"] == point:
                os._exit(87)
        raise SystemExit(r.main(request["args"], fault=fault))
    HISTORICAL_SOURCE = args.historical_source.absolute() if args.historical_source else None
    WORK.mkdir(parents=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = dict(result="PASS" if result.wasSuccessful() else "FAIL", tests_run=result.testsRun,
                    failures=len(result.failures), errors=len(result.errors), checks=CHECKS,
                    verification="developer_selftest_not_independent_acceptance", data_mode="synthetic_test",
                    real_provider_calls=0, market_requests=0, genuine_new_forward_days=0)
    a.c.write(WORK / "evidence.json", evidence)
    a.c.write(WORK / "commands-local.json", COMMANDS)
    print(json.dumps(dict(result=evidence["result"], tests_run=result.testsRun, evidence_ref=WORK.relative_to(ROOT).as_posix())))
    raise SystemExit(0 if result.wasSuccessful() else 1)
