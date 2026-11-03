"""Issue #63 directed synthetic evidence; no market/network/provider calls."""
import copy
from decimal import Decimal as D, localcontext
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"research"))
import autonomous_research as a
import autonomous_dsl as dsl
import autonomous_runner as runner

spec = importlib.util.spec_from_file_location("prior_tests", ROOT/"scripts"/"test-multistock-research.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


class Suite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT/"state"/"autonomous-tests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=parent)
        cls.sources = Path(cls.temp.name)
        cls.dates, cls.codes = prior.make_fixture(cls.sources)
        cls.base = a.OUTPUT/cls.sources.name
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setup_experiment(self, limits=None):
        Suite.counter += 1
        root = self.base/str(Suite.counter)
        dates = self.dates
        config = a.m.default_config(dates[0], dates[-1])
        config["max_positions"] = 2
        config["windows"] = [dict(name="development", role="development", start=dates[0], end=dates[69]),
            dict(name="validation", role="validation", start=dates[70], end=dates[79]),
            dict(name="exposed", role="evaluation", start=dates[80], end=dates[-1], train_end=dates[79])]
        ds = a.m.data.Dataset(self.sources/"v1", self.sources/"v2", dates[0], dates[-1], 90, 360)
        a.initialize(ds, config, root, limits=limits, authorized=True)
        return root

    def test_generator_structure_seed_units_and_rejections(self):
        first = dsl.propose(63, 1, 2)
        self.assertEqual(first, dsl.propose(63, 1, 2))
        self.assertEqual(len({p["ast_sha"] for p in first}), 4)
        self.assertEqual(len({p["ast"]["score"]["op"]+p["ast"]["filter"]["op"] for p in first}), 4)
        self.assertTrue(all(dsl.validate(p["ast"], 2) for p in first))
        for field,value in (("python", "import os"), ("url", "https://example.invalid"), ("path", "../../secrets")):
            bad = copy.deepcopy(first[0]["ast"])
            bad[field] = value
            with self.assertRaises(a.Error):
                dsl.validate(bad, 2)
        for field,value in (("lag", 0), ("window", 61), ("unit", "CNY"), ("missing", "fill_zero")):
            bad = copy.deepcopy(first[0]["ast"])
            bad["score"][field] = value
            with self.assertRaises(a.Error):
                dsl.validate(bad, 2)
        bad = copy.deepcopy(first[0]["ast"])
        for _ in range(10):
            bad["score"] = dict(op="negate", arg=bad["score"])
        with self.assertRaisesRegex(a.Error, "COMPLEXITY"):
            dsl.validate(bad, 2)

    def test_text_agent_and_forged_sources_are_rejected(self):
        source = dict(kind="trusted_local_deterministic_v1", task_ref="local:test")
        with self.assertRaises(a.Error):
            dsl.parse_proposal(a.canonical(dict(hypothesis="Buy the best stock")), source, 2)
        p = dict(contract="structured-research-proposal-v1", source=dict(kind="rust_agent", task_ref="forged"),
                 authority="RESEARCH_ONLY", hypothesis="test", ast=dsl.propose(63,1,2)[0]["ast"])
        with self.assertRaisesRegex(a.Error, "SOURCE_MISMATCH"):
            dsl.parse_proposal(a.canonical(p), source, 2)
        p["source"], p["authority"] = source, "ALLOW_PAPER"
        with self.assertRaisesRegex(a.Error, "AUTHORITY"):
            dsl.parse_proposal(a.canonical(p), source, 2)
        with self.assertRaisesRegex(a.Error, "DUPLICATE"):
            dsl.parse_proposal(b'{"contract":1,"contract":2}', source, 2)

    def test_two_round_e2e_negative_results_dedup_and_immutable(self):
        root = self.setup_experiment()
        before = a.m.data.file_receipts([self.sources/"v1", self.sources/"v2"])
        with mock.patch.object(a.m.data.v1, "credential", side_effect=AssertionError("TOKEN_READ")), \
             mock.patch.object(a.m.data.v1.TushareHTTP, "__call__", side_effect=AssertionError("HTTP")):
            first = a.once(root)
            self.assertEqual(first["status"]["completed_rounds"], 1)
            second = a.once(root)
        self.assertEqual(second["status"]["state"], "COMPLETED")
        self.assertEqual(len(second["rounds"]), 2)
        self.assertEqual(before, a.m.data.file_receipts([self.sources/"v1", self.sources/"v2"]))
        hashes = {p["ast_sha"] for p in a.read(root/"round-01"/"proposals.json")["proposals"].values()}
        next_hashes = {p["ast_sha"] for p in a.read(root/"round-02"/"proposals.json")["proposals"].values()}
        self.assertFalse(hashes & next_hashes)
        self.assertTrue(a.verify(root)["verified"])
        saved = (root/"round-01"/"results.json").read_bytes()
        a.once(root)
        self.assertEqual(saved, (root/"round-01"/"results.json").read_bytes())
        with self.assertRaisesRegex(a.Error, "IMMUTABLE"):
            a.put(root/"round-01"/"results.json", {})
        for rr in second["rounds"]:
            for key,value in rr["result"]["full_period"].items():
                self.assertLessEqual(value["assumed_exposure_changes"], 200)
            self.assertEqual(rr["result"]["full_period"]["cash/base"]["total_return"], "0")
        self.assertFalse(second["paper_allowed"])

    def test_feedback_cannot_see_validation_or_exposed_outcomes(self):
        windows = [dict(name="dev", role="development"), dict(name="held", role="validation")]
        value = dict(total_return="-0.1", max_drawdown="-0.3")
        base = dict(windows=dict(dev={"candidate_01/base":value}, held={"candidate_01/base":value}))
        modified = copy.deepcopy(base)
        modified["windows"]["held"] = {"secret_winner":{"total_return":"9999999"}}
        feedback = dsl.development_feedback("round", base, windows)
        self.assertEqual(feedback, dsl.development_feedback("round", modified, windows))
        self.assertEqual(dsl.propose(63,2,2,feedback), dsl.propose(63,2,2,dsl.development_feedback("round",modified,windows)))
        self.assertTrue(feedback["reduce_exposure"])
        self.assertNotIn("9999999", json.dumps(feedback))
        other_provenance = dict(feedback, round_sha="changed_exposed_source_hash")
        self.assertEqual(dsl.propose(63,2,2,feedback), dsl.propose(63,2,2,other_provenance))
        with self.assertRaisesRegex(a.Error,"SCHEMA_FIELDS"):
            dsl.propose(63,2,2,dict(feedback, hidden_holdout_winner="secret"))

    def test_timing_cost_direction_and_benchmark_cap(self):
        root = self.setup_experiment()
        a.once(root)
        folder = root/"round-01"
        receipts = a.chunk_receipts(folder)
        any_change = False
        for record in runner.iter_daily(folder, [r["chunk"] for r in receipts]):
            for key,value in record["full"].items():
                self.assertLessEqual(value["holdings"], 2)
                self.assertGreaterEqual(D(value["modeled_cost"]), 0)
                if value["assumed_exposure_changes"]:
                    any_change = True
                    self.assertLess(record["signal_date"], record["trade_date"])
        self.assertTrue(any_change)
        result = a.read(folder/"results.json")
        for name in ("candidate_01", "matched_equal_weight", "simple_positive_return"):
            self.assertGreaterEqual(D(result["full_period"][name+"/gross"]["total_return"]),
                                    D(result["full_period"][name+"/stress"]["total_return"]))

    def test_independent_decimal_cash_units_fees_and_normalized_index(self):
        # A separately written tiny ledger, with literal buy/sell/slippage/fee arithmetic.
        # It does not call cost_rate, weights, price or metrics to compute the expected path.
        with localcontext() as ctx:
            ctx.prec = 50
            scenario = dict(name="base", commission_bps="3", transfer_bps="1", slippage_bps="6", stamp_pre_bps="10", stamp_post_bps="5")
            cfg = dict(a.m.default_config(), hard_position_cap=1, min_hold_sessions=1)
            books = [a.m.Portfolio(scenario, cfg) for _ in range(4)]
            cash, units, mark, prev = D(1), D(0), D(0), D(1)
            for i,(op,cl,target) in enumerate((("10","11","1"), ("12","9",None), ("8","8","0"))):
                fee = D(0)
                if i == 0:
                    notional = cash/D("1.001")
                    units = notional/D(op)
                    fee = notional*D("0.001")
                    cash -= notional+fee
                elif i == 2:
                    notional = units*D(op)
                    fee = notional*D("0.002")
                    cash += notional-fee
                    units = D(0)
                mark = D(cl)
                expected = cash+units*mark
                row = dict(ts_code="600000.SH", trade_date=f"2021110{i+1}", daily=dict(open=op, close=cl, vol="1000",amount="20000"),
                    factor="1", quality=[], limit=dict(up_limit="100",down_limit="1"), suspension_events=[])
                day = dict(trade_date=row["trade_date"], rows=[row])
                for book in books:
                    record = book.step(day, i, None if target is None else {"600000.SH":target})
                    self.assertLess(abs(book.cash-cash), D("1e-45"))
                    self.assertLess(abs(book.value()-expected), D("1e-45"))
                    self.assertLess(abs(D(record["daily_return"])-(expected/prev-1)), D("1e-45"))
                    self.assertLess(abs(D(record["modeled_cost"])-fee), D("1e-45"))
                    self.assertEqual(sum((h.units for h in book.holdings.values()),D(0)), units)
                prev = expected
            self.assertLess(expected, D(1))  # A losing experiment is correct evidence.

    def test_recovery_evaluate_publish_archive_and_no_duplicate_reads(self):
        for stage in ("evaluate", "publish", "archive"):
            root = self.setup_experiment(dict(checkpoint_sessions=30))
            def fault(name, count):
                if name == stage and (stage != "evaluate" or count == 65):
                    raise RuntimeError("injected_local_interruption")
            with self.assertRaises(RuntimeError):
                a.once(root, fault=fault)
            folder = root/"round-01"
            saved = [(p, p.read_bytes()) for p in (folder/"chunks").glob("*/commit.json")]
            original = a.m.data.Dataset.read_day
            dates = []
            def read_day(ds, date, symbols=()):
                dates.append(date)
                return original(ds,date,symbols)
            with mock.patch.object(a.m.data.Dataset,"read_day",read_day):
                a.once(root)
            self.assertEqual(len(dates), 30 if stage == "evaluate" else 0)
            for p,content in saved:
                self.assertEqual(p.read_bytes(), content)
            self.assertTrue(a.verify(root)["verified"])
            self.assertTrue(any(e["kind"] == "STAGE_FAILED" for e in a.history(root)["events"]))

    def test_freeze_pause_cancel_resources_concurrency(self):
        root = self.setup_experiment()
        with self.assertRaises(RuntimeError):
            a.once(root, fault=lambda stage,n: (_ for _ in ()).throw(RuntimeError("kill")) if stage == "freeze" else None)
        original = (root/"round-01"/"proposals.json").read_bytes()
        a.control(root, "pause")
        with mock.patch.object(a.m.data.Dataset,"__enter__",side_effect=AssertionError("source read")):
            self.assertEqual(a.once(root)["status"]["effective_state"], "PAUSED")
        a.control(root, "resume")
        with a.m.data.v1.writer_lock(root):
            with self.assertRaisesRegex(a.Error,"BUSY"):
                a.once(root)
        a.once(root)
        self.assertEqual(original, (root/"round-01"/"proposals.json").read_bytes())
        a.control(root,"cancel")
        with self.assertRaisesRegex(a.Error,"TERMINAL"):
            a.control(root,"resume")
        limited = self.setup_experiment(dict(memory_mib=1))
        self.assertEqual(a.once(limited)["status"]["state"], "PARTIAL_RESOURCE_LIMIT")

    def test_readonly_commands_no_source_http_dispatch_or_mutations(self):
        root = self.setup_experiment()
        a.once(root)
        before = {p.relative_to(root).as_posix():(p.stat().st_size,p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
        with mock.patch.object(a.m.data.Dataset,"__enter__",side_effect=AssertionError("old source scan")), \
             mock.patch.object(a.m.data.v1,"credential",side_effect=AssertionError("token")):
            a.status(root)
            a.history(root)
            a.report(root)
            a.verify(root)
        after = {p.relative_to(root).as_posix():(p.stat().st_size,p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before,after)
        command = [sys.executable,"-I","-B",str(ROOT/"scripts/autonomous-research.py"),"status","--out",str(root)]
        self.assertEqual(subprocess.run(command,capture_output=True).returncode, 0)

    def test_corrupt_sources_outputs_candidate_explosion_and_empty_candidates(self):
        root = self.setup_experiment()
        a.once(root)
        results = root/"round-01"/"results.json"
        saved = results.read_bytes()
        results.write_bytes(saved.replace(b'"COMPLETED"',b'"ALLOW_PAPER"'))
        with self.assertRaises(a.Error):
            a.verify(root)
        results.write_bytes(saved)
        bad = self.setup_experiment()
        with mock.patch.object(dsl,"propose",return_value=dsl.propose(63,1,2)*3):
            with self.assertRaisesRegex(a.Error,"CANDIDATE_RESOURCE_LIMIT"):
                a.once(bad)
        empty = self.setup_experiment()
        with mock.patch.object(dsl,"propose",return_value=[]):
            result = a.once(empty)
        self.assertEqual(result["status"]["state"], "COMPLETED")
        self.assertEqual(result["rounds"][0]["result"]["proposed"], 0)
        changed = self.setup_experiment()
        loc = a.read(changed/"locators.json")
        loc["v1"] = str(self.sources/"missing-v1")
        a.put(changed/"locators.json",loc,immutable=False)
        with self.assertRaises(a.Error):
            a.once(changed)
        self.assertEqual(a.status(changed)["state"],"BLOCKED")

    def test_archive_status_gap_failure_audit_and_seed_reproduction(self):
        root = self.setup_experiment()
        def fault(stage,n):
            if stage == "archived":
                raise RuntimeError("kill_after_archive")
        with self.assertRaises(RuntimeError):
            a.once(root,fault=fault)
        with mock.patch.object(a.m.data.Dataset,"__enter__",side_effect=AssertionError("completed research repeated")):
            result = a.once(root)
        self.assertEqual(result["status"]["completed_rounds"],1)
        frozen = a.read(root/"round-01"/"proposals.json")
        same = self.setup_experiment()
        a.once(same)
        self.assertEqual(frozen,a.read(same/"round-01"/"proposals.json"))
        self.assertEqual((root/"round-01/results.json").read_bytes(),(same/"round-01/results.json").read_bytes())
        retry = self.setup_experiment()
        with self.assertRaises(RuntimeError):
            a.once(retry,fault=lambda stage,n: (_ for _ in ()).throw(RuntimeError("fail")) if stage=="publish" else None)
        a.once(retry)
        audit = retry/"round-01"/"attempts"/"01-failed.json"
        audit.write_bytes(b'{}')
        with self.assertRaisesRegex(a.Error,"FAILURE_AUDIT_HASH_MISMATCH"):
            a.verify(retry)

    def test_optional_valuation_nulls_and_feature_time_prefix(self):
        config = a.m.default_config()
        ast = dsl.propose(63,1,2)[0]["ast"]
        ast["score"] = dsl.feature("pe",1)
        self.assertTrue(dsl.validate(ast,2))
        with a.m.data.Dataset(self.sources/"v1",self.sources/"v2",self.dates[0],self.dates[-1],90,360) as ds:
            f = dsl.Features(config)
            for i,date in enumerate(self.dates[:69]):
                f.update(ds.read_day(date),i)
            eligible = f.eligible()
            self.assertTrue(eligible)
            targets, diagnostics = f.targets(ast,eligible)
            self.assertEqual(targets,{})
            self.assertEqual(diagnostics["missing_features"],len(eligible))
            first = f.targets(dsl.propose(63,1,2)[0]["ast"],eligible)
            tomorrow = ds.read_day(self.dates[69])
            tomorrow["rows"][0]["daily"]["close"] = "999999"
            self.assertEqual(first,f.targets(dsl.propose(63,1,2)[0]["ast"],eligible))

    def test_post_seal_failure_audit_tamper_delete_extra_and_recovery(self):
        root = self.setup_experiment()
        def fault(stage, n):
            if stage == "archived":
                raise RuntimeError("post_seal_failure")
        with self.assertRaises(RuntimeError):
            a.once(root, fault=fault)
        folder = root/"round-01"
        sealed = (folder/"archive.json").read_bytes()
        # Reach the exact old bug, then the replacement verifiable post-seal journal.
        tail = folder/"post-seal.json"
        if not tail.exists():
            tail = folder/"attempts"/"01-failed.json"
        saved = tail.read_bytes()
        for mode in ("tamper", "delete"):
            with self.subTest(mode=mode):
                try:
                    if mode == "tamper":
                        tail.write_bytes(saved.replace(b'RuntimeError', b'HiddenError'))
                    else:
                        tail.unlink()
                    with self.assertRaises((a.Error, OSError)):
                        a.verify(root)
                finally:
                    tail.write_bytes(saved)
        extra = folder/"attempts"/"99-failed.json"
        try:
            extra.write_bytes(b'{}')
            with self.assertRaisesRegex(a.Error, "AUDIT_FILE_SET"):
                a.verify(root)
        finally:
            extra.unlink()
        missing = folder/"attempts"/"01.json"
        content = missing.read_bytes()
        try:
            missing.unlink()
            with self.assertRaises((a.Error, OSError)):
                a.verify(root)
        finally:
            missing.write_bytes(content)
        with mock.patch.object(a.m.data.Dataset, "__enter__", side_effect=AssertionError("completed research repeated")):
            restored = a.once(root)
            self.assertTrue(a.verify(root)["verified"])
        self.assertEqual(restored["status"]["completed_rounds"], 1)
        self.assertEqual(sealed, (folder/"archive.json").read_bytes())
        journal = a.read(folder/"post-seal.json")
        self.assertEqual([r["kind"] for r in journal["records"]], ["STAGE_FAILED", "ARCHIVE_STATUS_RECOVERY"])
        # Deleting or rewriting a past entry after recovery must also be detected.
        saved = (folder/"post-seal.json").read_bytes()
        journal["records"].pop(0)
        try:
            a.put(folder/"post-seal.json", journal, immutable=False)
            with self.assertRaises(a.Error):
                a.verify(root)
        finally:
            (folder/"post-seal.json").write_bytes(saved)

    def test_seed3_without_contraction_has_bounded_novel_second_round(self):
        feedback = dsl.development_feedback("round", dict(windows=dict(dev={
            "candidate_01/base":dict(total_return="0.1", max_drawdown="-0.1")})),
            [dict(name="dev", role="development")])
        self.assertFalse(feedback["reduce_exposure"])
        first = dsl.propose(3, 1, 2)
        seen = {p["ast_sha"] for p in first}
        with mock.patch.object(dsl, "validate", wraps=dsl.validate) as validate:
            second = dsl.propose(3, 2, 2, feedback, seen)
        self.assertEqual(len(second), 4)
        self.assertFalse(seen & {p["ast_sha"] for p in second})
        self.assertEqual(second, dsl.propose(3, 2, 2, feedback, seen))
        self.assertLessEqual(validate.call_count, 16)
        self.assertTrue(all(dsl.validate(p["ast"], 2) for p in second))


if __name__ == "__main__":
    unittest.main(verbosity=2)
