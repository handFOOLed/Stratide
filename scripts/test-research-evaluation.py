"""Focused unit checks plus optional actual Windows CLI research workflow.

Actual runs require the already-frozen local audit/source; no network requests.
All writes are exclusive new ignored directories, including negative probes.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

spec = importlib.util.spec_from_file_location("research", Path(__file__).with_name("research-evaluate.py"))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class MetricsTests(unittest.TestCase):
    def report(self):
        # Artificial accounting-only values, never market evidence.
        return dict(initial_nav_fen=10000, fills=[], orders=[], daily=[
            dict(day=20261001, nav_fen=9900, cash_fen=8900, held_shares=100, pending_orders=1),
            dict(day=20261002, nav_fen=9800, cash_fen=8900, held_shares=100, pending_orders=0),
            dict(day=20261003, nav_fen=9700, cash_fen=9700, held_shares=0, pending_orders=0)])

    def test_boundary_uses_previous_nav_carries_position_and_pending(self):
        report = self.report()
        frozen = copy.deepcopy(report)
        w = r.window_metrics(report, 1, 3)
        self.assertEqual(w["initial_nav_fen"], 9900)
        self.assertEqual(w["carried_shares"], 100)
        self.assertEqual(w["carried_pending_orders"], 1)
        self.assertEqual(w["net_pnl_fen"], -200)
        self.assertEqual(report, frozen)
        r.window_metrics(report, 2, 3)  # Boundary is only a read-only projection.
        self.assertEqual(report, frozen)

    def test_missing_boundary_or_intermediate_nav_never_zero_filled(self):
        report = self.report()
        report["daily"][0]["nav_fen"] = None
        w = r.window_metrics(report, 1, 3)
        self.assertIsNone(w["net_return"])
        self.assertIsNone(w["max_drawdown"])
        report = self.report()
        report["daily"][1]["nav_fen"] = None
        w = r.window_metrics(report, 0, 3)
        self.assertIsNone(w["net_pnl_fen"])
        self.assertEqual(w["missing_nav_days"], 1)
        self.assertIsNone(w["max_drawdown"])

    def test_negative_returns_no_trades_short_window_and_null_inference(self):
        w = r.window_metrics(self.report(), 0, 3)
        self.assertEqual(w["net_return"], "-0.030000000000")
        self.assertEqual(w["fills"], 0)
        self.assertEqual(w["completed_round_trips"], 0)
        for key in ("sharpe", "annualized_return", "win_rate", "significance"):
            self.assertIsNone(w[key]["value"])
            self.assertTrue(w[key]["reason"])

    def test_posthoc_stress_only_charges_window_fills_and_labels_bound(self):
        report = self.report()
        report["fills"] = [dict(day=20261001, side="Buy", quantity=100, fees=dict(commission=50)),
                           dict(day=20261003, side="Sell", quantity=100, fees=dict(commission=50))]
        w = r.window_metrics(report, 1, 3)
        self.assertEqual(w["model_fee_fen"], 50)
        self.assertEqual(w["completed_round_trips"], 0)  # Carried buy not an independent in-window round.
        self.assertEqual(w["posthoc_cost_bounds"][0]["extra_fee_fen"], 500)
        self.assertEqual(w["posthoc_cost_bounds"][0]["kind"], "posthoc_cost_bound")
        self.assertEqual(w["posthoc_cost_bounds"][1]["hypothetical_net_pnl_fen"], -1200)

    def test_cash_and_drawdown_do_not_truncate_negative_sub_basis_point(self):
        self.assertEqual(r.ratio(-1, 10000000), "-0.000000100000")
        self.assertEqual(r.drawdown(10000, [10100, 9999]), "0.010000000000")


def actual(a):
    out = r.new_output(a.out)
    dataset = a.audit_dir / "input/dataset.json"
    split = a.audit_dir / "split.json"
    quality = a.audit_dir / "audit.json"
    exe = a.exe.resolve()
    flags = [str(v) for pair in zip(r.FLAGS, r.CAPITAL) for v in pair]
    protected = [dataset, split, quality, *(a.source_dir / f"{key}.json" for key in r.adapter.APIS),
                 a.source_dir / "extraction.json"]
    # Optional original PR12 sources/reports are hashed only to demonstrate that
    # this workflow did not overwrite them. No bytes are copied to GitHub.
    for directory in a.preserve_dir:
        protected.extend(p for p in directory.rglob("*") if p.is_file())
    before = {str(p.resolve()): r.sha(p) for p in protected}
    evaluations = []
    for name in ("a", "b"):
        run = out / name
        r.cli(exe, "paper-replay", dataset, run / "ledger", run / "report", "--sha256", r.sha(dataset), *flags)
        # A separate actual process exercises the documented script entrypoint.
        command = [sys.executable, str(Path(__file__).with_name("research-evaluate.py")), "evaluate",
                   "--exe", str(exe), "--input", str(dataset), "--split", str(split), "--audit", str(quality),
                   "--source-dir", str(a.source_dir), "--ledger", str(run / "ledger"),
                   "--report", str(run / "report"), "--out", str(run / "evaluation")]
        result = subprocess.run(command, capture_output=True, timeout=120)
        r.require(result.returncode == 0, result.stderr.decode("utf-8", errors="replace"))
        evaluations.append(r.read(run / "evaluation/evaluation.json"))
    for name in (*r.NAMES,):
        r.require((out / "a/report" / name).read_bytes() == (out / "b/report" / name).read_bytes(), "six reports differ")
    for name in ("evaluation.json", "evaluation.csv"):
        r.require((out / "a/evaluation" / name).read_bytes() == (out / "b/evaluation" / name).read_bytes(), "evaluation differs")
    for name in ("full", "development", "holdout"):
        relative = f"benchmark-{name}/benchmark.json"
        r.require((out / "a/evaluation" / relative).read_bytes() == (out / "b/evaluation" / relative).read_bytes(), "benchmark differs")
    report = r.read(out / "a/report/report.json")
    source = r.read(dataset)
    # Re-use the authoritative preparation gate: the long window must really
    # reject its corporate-action discontinuity, not just print a status label.
    try:
        r.adapter.prepare(a.source_dir, out / "unsupported-long-input", "20240101", "20261028")
        raise AssertionError("corporate-action discontinuity bypassed")
    except ValueError as error:
        r.require("corporate-action/adjustment discontinuity" in str(error), str(error))
    # A missing actual open-day row cannot become a zero-valued bar/suspension.
    missing_source = out / "missing-source-probe"
    shutil.copytree(a.source_dir, missing_source)
    daily = r.read(missing_source / "daily.json")
    removed_day = str(source["sessions"][2]["day"])
    r.write(missing_source / "daily.json", [row for row in daily if row["trade_date"] != removed_day])
    try:
        r.adapter.prepare(missing_source, out / "missing-input", str(source["sessions"][0]["day"]), "20261028")
        raise AssertionError("missing daily was filled or ignored")
    except ValueError as error:
        r.require("missing/extra daily" in str(error), str(error))
    # Independent comparator has one entry attempt, including failure and the
    # no-next-day case. It must not search forward for a more favorable entry.
    for name, stop, suspend in (("benchmark-pending", 1, False), ("benchmark-suspended", len(source["sessions"]), True)):
        probe = copy.deepcopy(source)
        probe["source_version"] += "/synthetic_benchmark_failure_probe_not_market_evidence"
        if suspend:
            probe["sessions"][0]["rules"]["tradable"] = False
        path = out / (name+".json")
        r.write(path, probe)
        r.cli(exe, "paper-benchmark", path, out / name, "--sha256", r.sha(path),
              "--start-index", 0, "--end-index", stop, *flags)
        b = r.read(out / name / "benchmark.json")
        r.require(b["status"] == "NOT_EVALUATED" and not b["fills"] and len(b["orders"]) == 1,
                  "benchmark failure chose a later entry")
        r.require(b["daily"][-1]["pending_orders"] == (0 if suspend else 1), "benchmark pending state hidden")
    # Freeze all newly generated authoritative evidence before read-only projections.
    active = [out / "a/ledger/ledger.sqlite", *(out / "a/report" / n for n in r.NAMES)]
    active_before = {str(p): r.sha(p) for p in active}
    if report["fills"]:
        first_fill_index = next(i for i, s in enumerate(source["sessions"]) if s["day"] == report["fills"][0]["day"])
        w = r.window_metrics(report, first_fill_index+1, len(source["sessions"]))
        r.require(w["carried_shares"] == 100 and w["initial_nav_fen"] == report["daily"][first_fill_index]["nav_fen"], "boundary reset")
    # Honest no-trade/last-day pending prefixes; explicitly synthetic probes made
    # from an original dataset, never additional historical/forward observations.
    first_order = report["orders"][0]["accepted_on"] if report["orders"] else None
    if first_order:
        idx = next(i for i, s in enumerate(source["sessions"]) if s["day"] == first_order)
        for name, length, pending in (("no-trade", 20, 0), ("last-day-pending", idx+1, 1)):
            probe = copy.deepcopy(source)
            probe["sessions"] = probe["sessions"][:length]
            probe["source_version"] += "/synthetic_prefix_probe_not_market_evidence"
            path = out / (name+".json")
            r.write(path, probe)
            r.cli(exe, "paper-replay", path, out / name / "ledger", out / name / "report", "--sha256", r.sha(path), *flags)
            p = r.read(out / name / "report/report.json")
            r.require(not p["fills"] and p["ending_pending_orders"] == pending, "no-trade/pending misreported")
            w = r.window_metrics(p, 0, len(p["daily"]))
            r.require(w["ending_pending_orders"] == pending and w["win_rate"]["value"] is None, "false statistics")
    # Boundary changes cannot change previously generated proposals/ledger;
    # an altered frozen split is rejected before any evaluation can proceed.
    changed_split = copy.deepcopy(r.read(split))
    changed_split["development_count"] -= 1
    bad_split = out / "changed-split.json"
    r.write(bad_split, changed_split)
    args = argparse.Namespace(input=dataset, split=bad_split, audit=quality, source_dir=a.source_dir,
                              exe=exe, ledger=out / "a/ledger", report=out / "a/report")
    failure = out / "bad-split-evaluation"
    failure.mkdir()
    try:
        r.evaluate(args, failure)
        raise AssertionError("changed split accepted")
    except ValueError as error:
        r.require("split/protocol changed" in str(error), str(error))
    # Tampered reports cannot pass on the strength of self-reported hashes.
    tampered = out / "tampered-report"
    shutil.copytree(out / "a/report", tampered)
    fake = r.read(tampered / "report.json")
    fake["ending_nav_fen"] += 1
    r.write(tampered / "report.json", fake)
    failure = out / "tampered-evaluation"
    failure.mkdir()
    try:
        r.verify_reports(exe, dataset, out / "a/ledger", tampered, failure)
        raise AssertionError("tampered report accepted")
    except ValueError as error:
        r.require("report differs" in str(error), str(error))
    # Actual T+1 mutation, including next open and all other daily price fields.
    if report["fills"]:
        target = report["fills"][0]["day"]
        mutated = copy.deepcopy(source)
        s = next(s for s in mutated["sessions"] if s["day"] == target)
        s["open_fen"] += 1
        s["high_fen"] = max(s["high_fen"], s["open_fen"]) + 1
        s["low_fen"] -= 1
        s["close_fen"] += 1
        s["volume_shares"] += 100
        mutated["source_version"] += "/synthetic_future_mutation_not_market_evidence"
        path = out / "future-mutation.json"
        r.write(path, mutated)
        r.cli(exe, "paper-replay", path, out / "future/ledger", out / "future/report", "--sha256", r.sha(path), *flags)
        other = r.read(out / "future/report/report.json")
        original_proposals = [o["proposal"] for o in report["orders"] if o["accepted_on"] < target]
        r.require(original_proposals == [o["proposal"] for o in other["orders"] if o["accepted_on"] < target], "future changed prior proposal")
        r.require(report["fills"][0]["price"] != other["fills"][0]["price"], "probe did not change future price")
    # Benchmark starts by its own calendar rule, not the strategy first buy.
    full = evaluations[0]["windows"]["full"]
    b = r.read(out / "a/evaluation/benchmark-full/benchmark.json")
    r.require(b["orders"][0]["accepted_on"] == source["sessions"][0]["day"], "benchmark follows strategy entry")
    if b["fills"] and report["fills"]:
        r.require(b["fills"][0]["day"] != report["fills"][0]["day"], "real fixture did not exercise independent benchmark entry")
    r.require(before == {str(p.resolve()): r.sha(p) for p in protected}, "protected evidence changed")
    r.require(active_before == {str(p): r.sha(p) for p in active}, "evaluation mutated strategy ledger/reports")
    summary = dict(kind="Sol self-test; not independent acceptance", two_ledgers_six_reports_identical=True,
                   evaluations_and_benchmarks_identical=True, original_evidence_files_unchanged=len(protected),
                   future_mutation_preserves_T_proposals=True, split_is_read_only_and_change_rejected=True,
                   tampered_report_rejected=True, no_trade_and_last_pending_honest=True,
                   missing_data_and_corporate_actions_blocked=True, failed_benchmark_never_retries=True,
                   independent_benchmark_entry=True, accounting="PASS", input_sha256=r.sha(dataset),
                   ledger_head=report["ledger_head"], windows=full,
                   research_evidence=evaluations[0]["research_evidence"])
    r.write(out / "self-test.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "windows"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--preserve-dir", type=Path, action="append", default=[])
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MetricsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    if args.exe:
        r.require(args.audit_dir and args.source_dir and args.out, "actual CLI run requires audit/source/out")
        actual(args)
