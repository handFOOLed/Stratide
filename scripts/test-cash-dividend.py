"""Actual Windows CLI E2E + independent accounting negative probes (no network).

Requires an exclusive new ignored output root. Leaves runnable evidence, including
two fresh ledgers/reports/evaluations, instead of replacing any existing account.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name+".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


v = module("cash-dividend-evaluate")
counterproof = module("cash-dividend-counterproof")
CAPITAL = ("1000000", "500000", "800000", "500000", "100000", "200000")
CONFIG = [item for pair in zip(v.FLAGS, CAPITAL) for item in pair]


class CashDividendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = v.read(cls.input)
        cls.output = cls.out
        for name in ("a", "b"):
            base = cls.output/name
            v.cli(cls.exe, "paper-dividend-replay", cls.input, base/"ledger", base/"report",
                  "--sha256", v.sha(cls.input), *CONFIG)
            p = subprocess.run([sys.executable, str(ROOT/"scripts/research-evaluate.py"),
                "evaluate-cash-dividend", "--input", str(cls.input), "--source", str(cls.source),
                "--ledger", str(base/"ledger"), "--report", str(base/"report"), "--exe", str(cls.exe),
                "--out", str(base/"evaluation")], capture_output=True)
            if p.returncode:
                raise AssertionError(p.stderr.decode("utf-8", errors="replace"))
        cls.report = v.read(cls.output/"a/report/report.json")
        cls.rows = v.journal(cls.output/"a/ledger/ledger.sqlite")

    def reject(self, command, *args):
        p = subprocess.run([str(self.exe), command, *map(str, args)], capture_output=True)
        self.assertEqual(p.returncode, 2, p.stdout+p.stderr)
        return p.stderr.decode("utf-8", errors="replace")

    def test_two_actual_ledgers_seven_reports_and_evaluations_identical(self):
        self.assertEqual(self.rows, v.journal(self.output/"b/ledger/ledger.sqlite"))
        self.assertEqual(v.sha(self.output/"a/ledger/ledger.sqlite"), v.sha(self.output/"b/ledger/ledger.sqlite"))
        for name in v.NAMES:
            self.assertEqual((self.output/"a/report"/name).read_bytes(), (self.output/"b/report"/name).read_bytes())
        self.assertEqual(v.read(self.output/"a/evaluation/evaluation.json"), v.read(self.output/"b/evaluation/evaluation.json"))
        for kind in ("benchmark", "cash"):
            self.assertEqual(v.journal(self.output/f"a/evaluation/{kind}-ledger/ledger.sqlite"),
                             v.journal(self.output/f"b/evaluation/{kind}-ledger/ledger.sqlite"))
            for name in v.NAMES:
                self.assertEqual((self.output/f"a/evaluation/{kind}-report"/name).read_bytes(),
                                 (self.output/f"b/evaluation/{kind}-report"/name).read_bytes())

    def test_restart_identical_retry_zero_new_events_and_read_only_report(self):
        before = v.sha(self.output/"a/ledger/ledger.sqlite")
        v.cli(self.exe, "paper-dividend-replay", self.input, self.output/"a/ledger", self.output/"a/report",
              "--sha256", v.sha(self.input), *CONFIG)
        self.assertEqual(v.sha(self.output/"a/ledger/ledger.sqlite"), before)
        v.cli(self.exe, "paper-dividend-report", self.input, self.output/"a/ledger", self.output/"restart-report",
              "--sha256", v.sha(self.input))
        self.assertEqual(v.journal(self.output/"a/ledger/ledger.sqlite"), self.rows)
        for name in v.NAMES:
            self.assertEqual((self.output/"a/report"/name).read_bytes(), (self.output/"restart-report"/name).read_bytes())

    def test_separate_rational_counterproof_and_both_accounting_benchmarks(self):
        result = counterproof.check(self.report)
        self.assertEqual(result["status"], "PASS")
        v.write(self.output/"counterproof.json", result)
        evaluation = v.read(self.output/"a/evaluation/evaluation.json")
        self.assertEqual(evaluation["buy_hold_benchmark"]["gross_income_fen"], 4200)
        self.assertEqual(evaluation["buy_hold_benchmark"]["tax_expense_fen"], 840)
        self.assertEqual(evaluation["buy_hold_benchmark"]["ending_nav_fen"], 999129)
        self.assertEqual(evaluation["cash_benchmark"]["ending_nav_fen"], 1000000)
        self.assertEqual(evaluation["cash_benchmark"]["gross_income_fen"], 0)
        self.assertEqual(evaluation["research_evidence"], "INSUFFICIENT_EVIDENCE")

    def test_independent_verifier_rejects_cash_nav_tax_receivable_income_and_peak_tamper(self):
        for field in ("cash_fen", "nav_fen", "receivable_fen", "liability_fen", "gross_income_fen", "tax_expense_fen", "peak"):
            r = copy.deepcopy(self.report)
            audit = next(e for e in r["events"] if e["cash_dividend"]["receivable_fen"])
            if field == "peak":
                audit["risk"]["cash_flow_adjusted_peak"] += 1
            elif field in ("cash_fen", "nav_fen"):
                audit[field] += 1
            else:
                audit["cash_dividend"][field] += 1
            with self.assertRaises(ValueError, msg=field):
                v.verify(self.dataset, self.rows, r)
        r = copy.deepcopy(self.report)
        r["fills"][0]["fees"]["commission"] += 1
        with self.assertRaises(ValueError):
            v.verify(self.dataset, self.rows, r)

    def test_cli_real_partial_unknown_tax_unit_date_version_and_mixed_events_rejected_before_creation(self):
        probes = {
            "partial": lambda e: e.update(fact_status="FACTS_PARTIAL"),
            "real": lambda e: e.update(real_account_eligible=True),
            "unknown-tax": lambda e: e["tax"].update(identity="unknown"),
            "missing-tax": lambda e: e.pop("tax"),
            "late": lambda e: e.update(source_available_at=e["record_at"]+1),
            "date": lambda e: e.update(ex_day=20260717),
            "announcement": lambda e: e.update(announcement_at=e["payment_at"]),
            "bonus": lambda e: e.update(schema="STOCK_DIVIDEND"),
            "mixed": lambda e: e.update(stock_dividend_ratio="0.1"),
            "version": lambda e: e.update(version=""),
            "source": lambda e: e.update(source_sha256="unknown"),
            "fraction": lambda e: e.update(cash_unit="per_ten_shares", cash_amount_fen=421),
            "negative": lambda e: e.update(cash_amount_fen=-42),
        }
        for name, change in probes.items():
            d = copy.deepcopy(self.dataset)
            change(d["cash_dividends"][0])
            path = self.output/("invalid-"+name+".json")
            v.write(path, d)
            account = self.output/("invalid-"+name)/"ledger"
            self.reject("paper-dividend-replay", path, account, self.output/("invalid-"+name)/"report",
                        "--sha256", v.sha(path), *CONFIG)
            self.assertFalse(account.exists(), name)
        d = copy.deepcopy(self.dataset)
        d["cash_dividends"].append(copy.deepcopy(d["cash_dividends"][0]))
        d["cash_dividends"][1]["cash_amount_fen"] = 43
        path = self.output/"conflicting-events.json"
        v.write(path, d)
        self.reject("paper-dividend-replay", path, self.output/"conflict/ledger", self.output/"conflict/report", "--sha256", v.sha(path), *CONFIG)

    def test_v4_unknown_event_or_modified_payload_and_new_input_cannot_mutate_committed_ledger(self):
        before = v.sha(self.output/"a/ledger/ledger.sqlite")
        d = copy.deepcopy(self.dataset)
        d["cash_dividends"][0]["cash_amount_fen"] += 1
        path = self.output/"modified-frozen-input.json"
        v.write(path, d)
        self.reject("paper-dividend-replay", path, self.output/"a/ledger", self.output/"conflict/report", "--sha256", v.sha(path), *CONFIG)
        cmd = copy.deepcopy(next(e["command"] for e in self.report["events"] if "CashDividendV1" in e["command"]))
        cmd["CashDividendV1"]["event_id"] = "unknown"
        path = self.output/"unknown-command.json"
        v.write(path, cmd)
        self.reject("paper-apply", self.output/"a/ledger", "unknown", path)
        self.assertEqual(v.sha(self.output/"a/ledger/ledger.sqlite"), before)

    def test_real_pr38_snapshot_read_only_comparison_is_blocked(self):
        evidence = ROOT/"docs/evidence/m1-pr07b/real-summary.json"
        before = v.sha(evidence)
        p = subprocess.run([sys.executable, str(ROOT/"scripts/research-evaluate.py"), "audit-cash-dividend-source",
                            "--evidence", str(evidence), "--out", str(self.output/"real-source-audit")], capture_output=True)
        self.assertEqual(p.returncode, 2)
        audit = v.read(self.output/"real-source-audit/source-audit.json")
        self.assertEqual(audit["facts"]["cash_amount"], "0.42")
        self.assertEqual(audit["facts"]["record_date"], "2026-07-15")
        self.assertEqual(audit["facts"]["ex_date"], "2026-07-16")
        self.assertEqual(audit["event_fact_status"], "FACTS_PARTIAL")
        self.assertEqual(audit["real_supported_history_days_added"], 0)
        self.assertFalse(audit["real_event_activation"])
        self.assertEqual(v.sha(evidence), before)

    def test_source_sha_and_report_csv_must_agree(self):
        d = copy.deepcopy(self.dataset)
        d["cash_dividends"][0]["source_sha256"] = "a"*64
        with self.assertRaises(ValueError):
            v.source_check(d, self.source)
        altered = self.output/"tampered-csv"
        shutil.copytree(self.output/"a/report", altered)
        (altered/"daily.csv").write_bytes((altered/"daily.csv").read_bytes().replace(b"999129", b"999130"))
        with self.assertRaises(ValueError):
            v.verify_files(self.dataset, self.output/"a/ledger", altered)

    def test_v3_golden_reports_hashes_and_existing_account_are_byte_compatible(self):
        old = ROOT/"samples/m0-pr03-synthetic.json"
        base = self.output/"v3"
        v.cli(self.exe, "paper-replay", old, base/"ledger", base/"report", "--sha256", v.sha(old), *CONFIG)
        for name in v.NAMES[:6]:
            self.assertEqual((base/"report"/name).read_bytes(), (ROOT/"docs/evidence/m0-pr03/sample-report"/name).read_bytes(), name)
        before = v.sha(base/"ledger/ledger.sqlite")
        self.reject("paper-dividend-replay", self.input, base/"ledger", base/"bad-report", "--sha256", v.sha(self.input), *CONFIG)
        with sqlite3.connect((base/"ledger/ledger.sqlite").resolve().as_uri()+"?mode=ro", uri=True) as db:
            self.assertEqual(db.execute("pragma user_version").fetchone()[0], 3)
        self.assertEqual(v.sha(base/"ledger/ledger.sqlite"), before)
        v.cli(self.exe, "paper-report", old, base/"ledger", base/"restart-report", "--sha256", v.sha(old))
        self.reject("paper-replay", self.input, self.output/"a/ledger", base/"wrong-mode", "--sha256", v.sha(self.input), *CONFIG)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    args.out = args.out.resolve()
    v.require(subprocess.run(["git", "check-ignore", "--quiet", str(args.out/"self-test.json")], cwd=ROOT).returncode == 0,
              "output must be ignored")
    args.out.mkdir(parents=True, exist_ok=False)
    CashDividendTests.out = args.out
    CashDividendTests.exe = args.exe.resolve()
    CashDividendTests.input = ROOT/"samples/cash-dividend-v1.json"
    CashDividendTests.source = ROOT/"samples/cash-dividend-source-v1.json"
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CashDividendTests))
    v.write(args.out/"self-test.json", dict(kind="Sol self-test, not independent acceptance", tests=result.testsRun,
            success=result.wasSuccessful(), errors=len(result.errors), failures=len(result.failures),
            input_sha256=v.sha(CashDividendTests.input), ledger_head=CashDividendTests.report["ledger_head"] if hasattr(CashDividendTests, "report") else None))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
