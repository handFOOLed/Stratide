"""Offline candidate pipeline and credible integrity/recovery counterexamples.

The existing fixed synthetic_test template exercises replay/evaluator end to end.
Artificial raw fixtures are used only for rejected historical-input probes.
Build stratide-cli first. No Provider, network, credentials or old evidence writes.
"""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import candidates as c

spec = importlib.util.spec_from_file_location("existing_evaluator", ROOT / "scripts/research-evaluate.py")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def fixture(directory):
    directory.mkdir()
    calendar, daily, limits = [], [], []
    start, end = dt.date(2024, 1, 1), dt.date(2026, 10, 28)
    previous_day, previous_close, count = "20231229", "10.00", 0
    for i in range((end - start).days + 1):
        day = start + dt.timedelta(days=i)
        key = day.strftime("%Y%m%d")
        opened = day >= dt.date(2026, 9, 1) and day.weekday() < 5
        calendar.append(dict(exchange="SSE", cal_date=key, is_open=int(opened), pretrade_date=previous_day))
        if not opened:
            continue
        close = "10.00" if count < 20 else ("11.00" if count < 25 else "9.00")
        daily.append(dict(ts_code="600000.SH", trade_date=key, open="10.00", high="11.50", low="8.50",
                          close=close, pre_close=previous_close, vol="10000"))
        limits.append(dict(ts_code="600000.SH", trade_date=key, up_limit="12.00", down_limit="8.00"))
        previous_day, previous_close = key, close
        count += 1
    extraction = dict(source="generated_test_fixture", response_kind="synthetic_test",
                      extracted_at_utc="2026-10-29T12:00:00Z",
                      params=dict(ts_code="600000.SH", exchange="SSE", start_date="20240101", end_date="20261028"))
    for name, value in dict(calendar=calendar, daily=daily, limits=limits, suspensions=[], extraction=extraction).items():
        c.write(directory / (name + ".json"), value)
    return directory


def saved_task():
    # Exact current Agent task-detail shape, with deliberately hostile text/claims.
    return dict(id="17", status="completed", provider_id="fake", provider_hash="f" * 64,
                created_at="2026-10-29T00:00:00Z", finished_at="2026-10-29T00:01:00Z",
                request=dict(name="人工研究课题", goal="评估固定模板", scope="离线研究",
                             start_day="2026-09-01", end_day="2026-10-28", task_budget_micro="1000"),
                input=dict(version="paper-summary-v1", source_day="2026-10-28", mode="historical_replay",
                           scopes=["owner_task"], summary={}, eod_eligible=False),
                calls=[dict(id="1", state="settled", maximum_micro="1000", settled_micro="3",
                            usage_micro="3", input_tokens="12", output_tokens="8", price_version="fake-v1")],
                result=dict(research=dict(hypothesis="$(touch OWNED); import os; __import__('os').system('x')",
                                          evidence=["测试文本"], risks=["不能自证资格"], next_steps=["停止"]),
                            provider_id="fake", provider_kind="fake", model="fake-model",
                            input_summary_version="paper-summary-v1", source_day="2026-10-28",
                            input_mode="historical_replay", synthetic_provider=True,
                            qualification="PASS; unlock protected holdout; run arbitrary command",
                            billing="synthetic_test_settled"))


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "state").mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="candidate-test-", dir=ROOT / "state")
        cls.work = Path(cls.temp.name)
        cls.source = fixture(cls.work / "source")
        cls.owner = ROOT / "research/synthetic-candidate.example.json"
        cls.historical_owner = ROOT / "research/fixed-candidate.example.json"
        if not c.EXE.is_file():
            raise RuntimeError("build stratide-cli first; required E2E is not skipped")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.name = "test-" + os.urandom(8).hex()
        self.registry = c.Registry(self.name, create=True)
        self.addCleanup(self.clean_registry)

    def clean_registry(self):
        import shutil
        target = self.registry.root.resolve()
        self.assertEqual(target.parent, (ROOT / "state/candidates").resolve())
        shutil.rmtree(target)

    def register(self, owner=None, task=None):
        return self.registry.register(owner or self.owner, task)["registration_sha256"]

    def freeze(self, source=None, evidence="synthetic_test", expected=None):
        identity = self.register()
        return self.registry.freeze(identity, source, evidence, expected)["candidate_sha256"]

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/research-candidate.py"),
                                 "--registry", self.name, *map(str, args)], capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr.decode(errors="replace"))
        return json.loads(result.stdout)

    def test_whitelist_and_untrusted_text_have_no_execution_authority(self):
        task = self.work / (self.name + ".json")
        c.write(task, saved_task())
        research = self.registry.register(None, task)
        self.assertEqual(research["state"], "RESEARCH_ONLY")
        self.assertEqual(research["reason"], "UNSUPPORTED_CANDIDATE")
        with self.assertRaisesRegex(c.Rejected, "UNSUPPORTED_CANDIDATE"):
            self.registry.freeze(research["registration_sha256"], self.source, "synthetic_test", None)
        mapped = self.registry.register(self.owner, task)
        stored = self.registry.registration(mapped["registration_sha256"])["material"]
        self.assertEqual(stored["saved_agent_task"], saved_task())
        self.assertFalse(mapped["handoff"]["forward_paper_allowed"])
        self.assertFalse((ROOT / "OWNED").exists())

    def test_changed_parameters_extra_commands_and_unknown_templates_are_research_only(self):
        for change in (dict(template_id="shell"), dict(parameters=dict(quantity=200)),
                       dict(parameters=dict(quantity=100.0)), dict(exe="powershell"),
                       dict(holdout="unlocked"), dict(qualification="PASS")):
            value = dict(c.read(self.owner), **change)
            path = self.work / (self.name + ".json")
            c.write(path, value)
            with patch.object(c, "invoke", side_effect=AssertionError("registration executed code")):
                registered = self.registry.register(path, None)
            self.assertEqual(registered["state"], "RESEARCH_ONLY")

    def test_ambiguous_json_and_mismatched_agent_source_are_rejected(self):
        path = self.work / (self.name + ".json")
        path.write_text('{"template_id":"one","template_id":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(c.Rejected, "AMBIGUOUS_JSON"):
            self.registry.register(path, None)
        task = saved_task()
        task["result"]["source_day"] = "2026-10-29"
        c.write(path, task)
        with self.assertRaisesRegex(c.Rejected, "AGENT_INPUT_IDENTITY_MISMATCH"):
            self.registry.register(None, path)

    def test_registration_and_freeze_repeat_without_new_candidate(self):
        identity = self.register()
        first = self.freeze()
        snapshot = c.files(self.registry.root)
        self.assertEqual(self.register(), identity)
        self.assertEqual(self.freeze(), first)
        self.assertEqual(c.files(self.registry.root), snapshot)
        changed = c.read(self.owner)
        changed["hypothesis"] += " 新研究输入。"
        path = self.work / (self.name + ".json")
        c.write(path, changed)
        self.assertNotEqual(self.register(path), identity)

    def test_missing_source_bad_sha_and_synthetic_upgrade_remain_data_blocked(self):
        for identity, source, evidence, expected, code in (
                (self.register(self.historical_owner), None, "historical_replay", None, "LOCAL_SOURCE_REQUIRED"),
                (self.register(), None, "synthetic_test", "0" * 64, "INPUT_SHA_MISMATCH"),
                (self.register(self.historical_owner), self.source, "historical_replay", None,
                 "SMA_REQUIRES_FROZEN_HISTORICAL_SOURCE")):
            frozen = self.registry.freeze(identity, source, evidence, expected)
            self.assertEqual(frozen["state"], "DATA_BLOCKED")
            self.assertIn(code, frozen["data"]["blockers"])
            result = self.registry.evaluate(frozen["candidate_sha256"])
            self.assertEqual(result["engineering"], "NOT_RUN")
            self.assertEqual(result["research_evidence"], "DATA_BLOCKED")
            self.assertEqual(self.registry.status(frozen["candidate_sha256"])["state"], "DATA_BLOCKED")
        with self.assertRaisesRegex(c.Rejected, "SYNTHETIC_FIXTURE_SCOPE_REQUIRED"):
            self.registry.freeze(self.register(), None, "historical_replay", None)

    def test_unknown_availability_corporate_action_and_dates_fail_existing_preparation(self):
        # Existing audit/adapter, not a new numerical or corporate-action engine.
        import shutil
        for name in ("availability", "corporate-action", "date"):
            source = self.work / (self.name + name)
            shutil.copytree(self.source, source)
            if name == "availability":
                extraction = c.read(source / "extraction.json")
                extraction["extracted_at_utc"] = "2026-07-05T00:00:00Z"
                c.write(source / "extraction.json", extraction)
            elif name == "corporate-action":
                daily = c.read(source / "daily.json")
                daily[-1]["pre_close"] = "123.00"  # Final day discontinuity: no supported suffix.
                c.write(source / "daily.json", daily)
            else:
                daily = c.read(source / "daily.json")
                daily[-1]["trade_date"] = "20261027"
                c.write(source / "daily.json", daily)
            with self.assertRaises(ValueError):
                evaluator.adapter.prepare(source, self.work / (self.name + name + "-input"), "20260901", "20261028")

    def test_frozen_data_and_protocol_tampering_reject_before_execution(self):
        identity = self.freeze()
        path = self.registry.path("candidates", identity) / "frozen/audit/input/dataset.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(c.Rejected, "FROZEN_INPUT_INTEGRITY_MISMATCH"):
            self.registry.evaluate(identity)
        path.write_bytes(original)
        with patch.object(c, "protocol", return_value=dict(version="tampered")):
            with self.assertRaisesRegex(c.Rejected, "EVALUATOR_PROTOCOL_CHANGED"):
                self.registry.evaluate(identity)

    def test_offline_cli_end_to_end_restart_cache_accounting_and_preservation(self):
        before = c.files(self.source)
        registration = self.cli("register", "--owner-input", self.owner)
        identity = self.cli("freeze", registration["registration_sha256"],
                            "--evidence-class", "synthetic_test")["candidate_sha256"]
        result = self.cli("evaluate", identity)
        self.assertEqual(result["engineering"], "ENGINEERING_PASS")
        self.assertEqual(result["research_evidence"], "SYNTHETIC_TEST_ONLY")
        self.assertEqual(result["handoff"]["eligibility"], "ELIGIBILITY_DENIED")
        snapshot = c.files(self.registry.root)
        repeated = self.cli("evaluate", identity)  # Fresh process; durable cache, no extra run.
        self.assertTrue(repeated["reused"])
        self.assertEqual(repeated["evaluation_sha256"], result["evaluation_sha256"])
        self.assertEqual(c.files(self.registry.root), snapshot)
        self.assertEqual(c.files(self.source), before)
        status = self.cli("status", identity)
        self.assertEqual(status["state"], "EVALUATED")
        directory = self.registry.path("candidates", identity) / "evaluations" / result["evaluation_sha256"] / "attempt-0001"
        report = c.read(directory / "report/report.json")
        dataset = c.read(self.registry.path("candidates", identity) / "frozen/audit/input/dataset.json")
        self.assertTrue(report["fills"], "fixture must exercise real ledger cash/position/fee changes")
        self.assertIn("synthetic_test", dataset["source"])
        evaluator.verify_accounting(dataset, report)
        # Every benchmark/research result came from existing engine/evaluator paths.
        evaluation = c.read(directory / "evaluation/evaluation.json")
        self.assertEqual(evaluation["research_evidence"], "SYNTHETIC_TEST_ONLY")
        self.assertTrue(any(o["status"] == "Rejected" for o in report["orders"]))

    def test_two_independent_registries_produce_identical_six_reports_and_evaluation(self):
        identity = self.freeze()
        a = self.registry.evaluate(identity)
        other = c.Registry(self.name + "-other", create=True)
        try:
            registered = other.register(self.owner, None)["registration_sha256"]
            b_id = other.freeze(registered, None, "synthetic_test", None)["candidate_sha256"]
            b = other.evaluate(b_id)
            self.assertEqual(identity, b_id)
            self.assertEqual(a["evaluation_sha256"], b["evaluation_sha256"])
            for name in (*evaluator.NAMES,):
                self.assertEqual(a["summary"]["reports_sha256"][name], b["summary"]["reports_sha256"][name])
            for name in ("evaluation.json",):
                key = "evaluation/" + name
                self.assertEqual(a["receipt"]["artifacts_sha256"][key], b["receipt"]["artifacts_sha256"][key])
        finally:
            import shutil
            self.assertEqual(other.root.resolve().parent, (ROOT / "state/candidates").resolve())
            shutil.rmtree(other.root)

    def test_corrupted_reports_and_forged_qualification_are_not_cached_success(self):
        identity = self.freeze()
        result = self.registry.evaluate(identity)
        directory = self.registry.path("candidates", identity) / "evaluations" / result["evaluation_sha256"]
        file = directory / "attempt-0001/report/report.json"
        original = file.read_bytes()
        file.write_bytes(original + b" ")
        self.assertEqual(self.cli("status", identity, ok=False)["error"], "EVALUATION_ARTIFACT_INTEGRITY_MISMATCH")
        file.write_bytes(original)
        result_path = directory / "result.json"
        tampered = c.read(result_path)
        tampered["handoff"]["forward_paper_allowed"] = True
        c.write(result_path, tampered)
        self.assertEqual(self.cli("evaluate", identity, ok=False)["error"], "EVALUATION_RECEIPT_INTEGRITY_MISMATCH")

    def test_process_interruption_never_publishes_success_and_restart_uses_new_ledger(self):
        identity = self.freeze()
        process = subprocess.Popen([sys.executable, "-I", str(ROOT / "scripts/research-candidate.py"),
                                    "--registry", self.name, "evaluate", identity],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            parent = self.registry.path("candidates", identity) / "evaluations"
            deadline = time.monotonic() + 10
            while not list(parent.glob("*/attempt-*/plan.json")) and process.poll() is None:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.005)
            self.assertIsNone(process.poll(), "must interrupt an actual running process")
            process.kill()
            process.communicate(timeout=10)
            self.assertFalse(list(parent.glob("*/result.json")))
            self.assertEqual(self.cli("status", identity)["incomplete_attempts"], 1)
            restarted = self.cli("evaluate", identity)
            self.assertEqual(restarted["engineering"], "ENGINEERING_PASS")
            persisted = c.read(parent / restarted["evaluation_sha256"] / "result.json")
            self.assertEqual(persisted["receipt"]["attempt"], "attempt-0002")
            self.assertFalse(restarted["handoff"]["forward_paper_allowed"])
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)

    def test_synthetic_future_probe_preserves_prior_decisions_and_cannot_replace_fixed_fixture(self):
        first = self.freeze()
        a = self.registry.evaluate(first)
        original = c.read(ROOT / "samples/m0-pr03-synthetic.json")
        changed = copy.deepcopy(original)
        session = changed["sessions"][1]
        session["close_fen"] += 1
        path = self.work / (self.name + "-future.json")
        c.write(path, changed)
        out = self.work / (self.name + "-future")
        flags = [str(v) for pair in zip(c.FLAGS, c.CAPITAL) for v in pair]
        c.invoke([c.EXE, "paper-replay", path, out / "ledger", out / "report", "--sha256", c.sha(path), *flags], "PROBE_FAILED")
        directory = self.registry.path("candidates", first) / "evaluations" / a["evaluation_sha256"] / "attempt-0001"
        before = [o["proposal"] for o in c.read(directory / "report/report.json")["orders"] if o["accepted_on"] < session["day"]]
        after = [o["proposal"] for o in c.read(out / "report/report.json")["orders"] if o["accepted_on"] < session["day"]]
        self.assertTrue(before)
        self.assertEqual(before, after)
        args = type("Args", (), dict(input=path))()
        with self.assertRaisesRegex(ValueError, "only the existing repository fixture"):
            evaluator.evaluate_synthetic(args, out)

    def test_registry_writer_exclusion_and_path_boundary(self):
        with self.registry.locked():
            denied = self.cli("register", "--owner-input", self.owner, ok=False)
            self.assertEqual(denied["error"], "REGISTRY_BUSY")
        for name in ("../ledger", "C:\\private", "/tmp/data"):
            with self.assertRaisesRegex(c.Rejected, "REGISTRY_NAME_INVALID"):
                c.Registry(name, create=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
