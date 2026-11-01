"""P0 scenario CLI/financial/time/recovery counterexamples; offline Sol self-test."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import historical_dividend as d

FLAGS = [str(x) for pair in zip(d.v.FLAGS, d.CAPITAL) for x in pair]


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.bundle, cls.assumptions = d.fixture(cls.out/"fixture")
        p = subprocess.run([sys.executable, str(ROOT/"scripts/historical-dividend.py"), "run",
            "--source-dir", str(cls.source), "--evidence-bundle", str(cls.bundle), "--assumptions", str(cls.assumptions),
            "--exe", str(cls.exe), "--out", str(cls.out/"chain")], capture_output=True)
        if p.returncode:
            raise AssertionError(p.stdout.decode("utf-8", errors="replace")+p.stderr.decode("utf-8", errors="replace"))
        cls.input = cls.out/"chain/frozen/dataset.json"
        cls.dataset = d.read(cls.input)
        cls.report = d.read(cls.out/"chain/a/report/report.json")
        cls.rows = d.v.journal(cls.out/"chain/a/ledger/ledger.sqlite")

    def cli(self, *args, code=0):
        p = subprocess.run([str(self.exe), *map(str, args)], capture_output=True)
        self.assertEqual(p.returncode, code, p.stdout+p.stderr)
        return p

    def variant(self, name, change):
        a = d.read(self.assumptions)
        change(a)
        path = self.out/(name+"-assumptions.json")
        d.write(path, a)
        return path

    def mutate_source(self, name, file, change):
        root = self.out/name
        shutil.copytree(self.source, root)
        value = d.read(root/(file+".json"))
        change(value)
        d.write(root/(file+".json"), value)
        a = self.variant(name, lambda a: a["source_sha256"].update({file: d.sha(root/(file+".json"))}))
        return root, a

    def test_complete_cli_and_separate_statuses_and_actual_receipt(self):
        summary = d.read(self.out/"chain/public-summary.json")
        self.assertEqual(summary["scenario_engineering_status"], "ENGINEERING_RUNNABLE")
        self.assertEqual(summary["real_historical_eligibility"], "DENIED")
        self.assertEqual(summary["real_pit_days_added"], 0)
        self.assertTrue(summary["two_fresh_runs_identical"])
        e = self.dataset["cash_dividends"][0]
        self.assertGreater(e["source_available_at"], e["payment_at"])
        self.assertEqual(e["fact_status"], "EX_POST_MODEL_ONLY")
        self.assertTrue(all(s["opening"] is None for s in self.dataset["sessions"]))
        self.assertEqual(self.report["strategy_version"], "sma5-20-cross-fixed100-v1")
        # 20-session warmup begins on July 6, so SMA has no record-date shares.
        self.assertEqual(self.report["cash_dividend"]["gross_income_fen"], 0)
        self.assertEqual(len(self.report["daily"]), 40)

    def test_hand_derived_price_move_is_not_cancelled_by_dividend_and_payment_no_profit(self):
        # Fixed artificial comparator: buy100 at10.01, commission5.00+transfer0.02.
        r = d.read(self.out/"chain/a/evaluation/buy-hold-report/report.json")
        rows = {x["day"]: x for x in r["daily"]}
        cash = 10_000_000-100*1001-502
        self.assertEqual(rows[20260715]["nav_fen"], cash+100*1000)
        self.assertEqual(rows[20260716]["cash_fen"], cash)
        self.assertEqual(rows[20260716]["nav_fen"], cash+100*950+4200-840)
        self.assertEqual(rows[20260716]["nav_fen"]-rows[20260715]["nav_fen"], -1640)
        self.assertEqual(rows[20260716]["cash_dividend"]["receivable_fen"], 4200)
        self.assertEqual(rows[20260716]["cash_dividend"]["liability_fen"], 840)
        self.assertEqual(rows[20260720]["nav_fen"], rows[20260717]["nav_fen"])
        self.assertEqual(rows[20260720]["cash_fen"], cash+3360)
        self.assertEqual(r["ending_nav_fen"], cash+100*1020+3360)
        self.assertTrue(all(row["external_flow_total_fen"] == 0 for row in rows.values()))
        d.write(self.out/"hand-counterproof.json", dict(status="PASS", ex_price_move_plus_net_dividend_fen=-1640,
            cash_fen_before_payment=cash, receivable_fen=4200, liability_fen=840, payment_income_increment_fen=0,
            kind="Sol hand-derived arithmetic, not independent reviewer acceptance"))

    def test_preparer_rejects_calendar_missing_daily_extra_break_negative_and_integer_overflow(self):
        cases = [
            ("calendar-gap", "calendar", lambda a: a.pop(2)),
            ("missing-day", "daily", lambda a: a.pop(4)),
            ("other-break", "daily", lambda a: a[12].update(pre_close="8.00")),
            ("negative", "daily", lambda a: a[2].update(open="-1")),
            ("overflow", "daily", lambda a: a[2].update(open=str(2**63))),
            ("band", "limits", lambda a: a[2].update(down_limit="11")),
            ("duplicate", "daily", lambda a: a.append(copy.deepcopy(a[0]))),
            ("scope", "extraction", lambda a: a["params"].update(ts_code="000001.SZ")),
        ]
        for name, file, change in cases:
            with self.subTest(name=name):
                source, a = self.mutate_source(name, file, change)
                with self.assertRaises((ValueError, d.ca.Rejected)):
                    d.freeze(source, self.bundle, a, self.out/(name+"-blocked"))
                self.assertFalse((self.out/(name+"-blocked/dataset.json")).exists())

    def test_bad_sha_evidence_tamper_and_original_prepare_discontinuity_remain_rejected(self):
        a = self.variant("bad-sha", lambda a: a["source_sha256"].update(daily="0"*64))
        with self.assertRaisesRegex(ValueError, "SHA_MISMATCH"):
            d.build(self.source, self.bundle, a)
        bundle = self.out/"tampered-bundle"
        shutil.copytree(self.bundle, bundle)
        manifest = d.read(bundle/"manifest.json")
        manifest["events"][0]["facts"]["cash_amount"] = "0.43"
        d.write(bundle/"manifest.json", manifest)
        with self.assertRaises((ValueError, d.ca.Rejected)):
            d.build(self.source, bundle, self.assumptions)
        with self.assertRaisesRegex(ValueError, "corporate-action/adjustment discontinuity"):
            d.h.prepare(self.source, self.out/"old-prepare-must-refuse", "20260706", "20260828")
        self.assertFalse((self.out/"old-prepare-must-refuse/dataset.json").exists())

    def test_unknown_model_tax_dates_payment_and_unlabeled_assumptions_rejected(self):
        mutations = {
            "tax-negative": lambda a: a["models"]["withholding_ppm"].update(value=-1),
            "tax-over": lambda a: a["models"]["withholding_ppm"].update(value=1_000_001),
            "shares": lambda a: a["models"]["share_change_ratio"].update(value="0.1"),
            "unlabeled": lambda a: a["models"]["payment_at"].update(modeled_only=False),
            "missing-model": lambda a: a["models"].pop("payment_at"),
            "late-record": lambda a: a["models"]["record_at"].update(value="2026-07-16T11:00:00Z"),
            "intraday-pay": lambda a: a["models"]["payment_at"].update(value="2026-07-20T05:00:00Z"),
            "unknown-date": lambda a: a["models"]["payment_at"].update(value="2026-07-19T01:30:00Z"),
            "early-fees": lambda a: a.update(selected_start="20240101"),
        }
        for name, change in mutations.items():
            with self.subTest(name=name):
                a = self.variant(name, change)
                with self.assertRaises((ValueError, d.ca.Rejected)):
                    d.build(self.source, self.bundle, a)

    def test_cli_rejects_gate_unit_amount_mode_version_and_old_paths_before_new_ledger(self):
        mutations = {
            "pit": lambda a: a["cash_dividends"][0].update(historical_pit="VERIFIED"),
            "admit": lambda a: a["scenario"].update(real_historical_eligibility="ALLOWED"),
            "real": lambda a: a["cash_dividends"][0].update(real_account_eligible=True),
            "unknown-tax": lambda a: a["cash_dividends"][0]["tax"].update(identity="unknown"),
            "amount": lambda a: a["cash_dividends"][0].update(cash_amount_fen=-42),
            "huge": lambda a: a["cash_dividends"][0].update(cash_amount_fen=2**63),
            "unit": lambda a: a["cash_dividends"][0].update(cash_unit="per_ten_shares"),
            "version": lambda a: a["cash_dividends"][0].update(version=""),
            "duplicate": lambda a: a["cash_dividends"].append(copy.deepcopy(a["cash_dividends"][0])),
            "forward": lambda a: a["historical"].update(availability="verified_forward"),
        }
        for name, change in mutations.items():
            value = copy.deepcopy(self.dataset)
            change(value)
            path = self.out/("bad-"+name+".json")
            d.write(path, value)
            ledger = self.out/("bad-"+name)/"ledger"
            self.cli("paper-historical-dividend-replay", path, ledger, self.out/("bad-"+name)/"report",
                "--sha256", d.sha(path), *FLAGS, code=2)
            self.assertFalse(ledger.exists(), name)
        for command in ("paper-replay", "paper-dividend-replay"):
            self.cli(command, self.input, self.out/(command+"-ledger"), self.out/(command+"-report"),
                "--sha256", d.sha(self.input), *FLAGS, code=2)
        self.cli("paper-benchmark", self.input, self.out/"old-benchmark-must-refuse", "--sha256", d.sha(self.input),
            "--start-index", 0, "--end-index", len(self.dataset["sessions"]), *FLAGS, code=2)
        self.assertFalse((self.out/"old-benchmark-must-refuse").exists())
        self.cli("paper-historical-dividend-replay", ROOT/"samples/cash-dividend-v1.json",
            self.out/"wrong-legacy-ledger", self.out/"wrong-legacy-report", "--sha256",
            d.sha(ROOT/"samples/cash-dividend-v1.json"), *FLAGS, code=2)

    def test_retry_and_restored_each_phase_prefix_resume_no_duplicate_or_changed_payload(self):
        before = d.sha(self.out/"chain/a/ledger/ledger.sqlite")
        self.cli("paper-historical-dividend-replay", self.input, self.out/"chain/a/ledger", self.out/"chain/a/report",
            "--sha256", d.sha(self.input), *FLAGS)
        self.assertEqual(before, d.sha(self.out/"chain/a/ledger/ledger.sqlite"))
        phase_indices = [i for i, r in enumerate(self.rows) if '"CashDividendV1"' in r[2]]
        for seq in phase_indices:
            for committed in (False, True):
                prefix = seq if committed else seq-1
                root = self.out/f"resume-{seq}-{committed}"
                root.mkdir()
                ledger = root/"ledger"
                ledger.mkdir()
                with sqlite3.connect((self.out/"chain/a/ledger/ledger.sqlite").resolve().as_uri()+"?mode=ro", uri=True) as src:
                    with sqlite3.connect(ledger/"ledger.sqlite") as dst:
                        src.backup(dst)
                        dst.execute("delete from events where seq>?", (prefix,))
                        dst.execute("update checkpoint set seq=?,digest=? where id=1", (prefix, self.rows[prefix][3]))
                self.cli("paper-historical-dividend-replay", self.input, ledger, root/"report", "--sha256", d.sha(self.input), *FLAGS)
                self.assertEqual(d.v.journal(ledger/"ledger.sqlite"), self.rows)
                for name in d.v.NAMES:
                    self.assertEqual((root/"report"/name).read_bytes(), (self.out/"chain/a/report"/name).read_bytes())
        value = copy.deepcopy(self.dataset)
        value["cash_dividends"][0]["version"] += "-changed"
        path = self.out/"changed-version.json"
        d.write(path, value)
        self.cli("paper-historical-dividend-replay", path, self.out/"chain/a/ledger", self.out/"changed-report",
            "--sha256", d.sha(path), *FLAGS, code=2)
        self.assertEqual(before, d.sha(self.out/"chain/a/ledger/ledger.sqlite"))

    def test_tax_sensitivity_and_same_open_ex_payment_are_distinct_models(self):
        endings = {}
        for rate in (0, 200_000, 1_000_000):
            def change(a):
                a["version"] = f"tax-{rate}-payment0716-v1"
                a["models"]["withholding_ppm"].update(value=rate, version=f"tax-{rate}-v1")
                a["models"]["payment_at"].update(value="2026-07-16T01:30:00Z", version="payment0716-v1")
            a = self.variant(f"tax{rate}", change)
            dataset, _ = d.build(self.source, self.bundle, a)
            path = self.out/f"tax{rate}.json"
            d.write(path, dataset)
            base = self.out/f"tax{rate}"
            self.cli("paper-historical-dividend-benchmark", path, base/"ledger", base/"report", "--sha256", d.sha(path), *FLAGS)
            endings[rate] = d.verify_files(dataset, base/"ledger", base/"report")["ending_nav_fen"]
            report = d.read(base/"report/report.json")
            ex, pay = [e for e in report["events"] if e["command"].get("CashDividendV1", {}).get("phase") in ("ex", "payment")]
            self.assertEqual(ex["nav_fen"], pay["nav_fen"])
            self.assertEqual(pay["cash_dividend"]["receivable_fen"], 0)
        self.assertEqual(endings[0]-endings[200_000], 840)
        self.assertEqual(endings[0]-endings[1_000_000], 4200)

    def test_independent_arithmetic_time_signal_fee_and_reservation_tamper_rejected(self):
        report = d.read(self.out/"chain/a/evaluation/buy-hold-report/report.json")
        rows = d.v.journal(self.out/"chain/a/evaluation/buy-hold-ledger/ledger.sqlite")
        for field in ("cash_fen", "nav_fen", "liability_fen", "receivable_fen", "peak"):
            value = copy.deepcopy(report)
            audit = next(e for e in value["events"] if e["cash_dividend"]["receivable_fen"])
            if field in ("cash_fen", "nav_fen"):
                audit[field] += 1
            elif field == "peak":
                audit["risk"]["cash_flow_adjusted_peak"] += 1
            else:
                audit["cash_dividend"][field] += 1
            with self.assertRaises(ValueError):
                d.v.verify(self.dataset, rows, value, True)
        value = copy.deepcopy(report)
        value["daily"][0]["reserved_cash_fen"] -= 1
        value["daily"][0]["available_cash_fen"] += 1
        with self.assertRaises(ValueError):
            d.v.verify(self.dataset, rows, value, True)
        value = copy.deepcopy(self.report)
        next(e for e in value["events"] if "Submit" in e["command"])["command"]["Submit"]["proposal"]["quantity"] = 200
        with self.assertRaises(ValueError):
            d.audit_timeline(self.dataset, value)

    def test_future_mutation_does_not_change_prior_sma_and_cannot_supply_forward_opening(self):
        self.assertTrue(self.report["fills"])
        target = self.report["fills"][0]["day"]
        value = copy.deepcopy(self.dataset)
        s = next(s for s in value["sessions"] if s["day"] == target)
        s["open_fen"] += 1
        s["high_fen"] += 1
        s["low_fen"] -= 1
        s["close_fen"] += 1
        path = self.out/"future-mutation-artificial.json"
        d.write(path, value)
        self.cli("paper-historical-dividend-replay", path, self.out/"future/ledger", self.out/"future/report", "--sha256", d.sha(path), *FLAGS)
        other = d.read(self.out/"future/report/report.json")
        proposals = lambda r: [o["proposal"] for o in r["orders"] if o["accepted_on"] < target]
        self.assertEqual(proposals(other), proposals(self.report))
        self.assertEqual(other["fills"][0]["price"], self.report["fills"][0]["price"]+1)

    def test_missing_real_source_machine_blocker_exit2_and_no_empty_success_report(self):
        p = subprocess.run([sys.executable, str(ROOT/"scripts/historical-dividend.py"), "prepare",
            "--source-dir", str(self.out/"missing-source"), "--evidence-bundle", str(self.bundle),
            "--assumptions", str(self.assumptions), "--out", str(self.out/"missing-source-result")], capture_output=True)
        self.assertEqual(p.returncode, 2)
        result = json.loads(p.stdout)
        self.assertEqual(result["scenario_engineering_status"], "DATA_BLOCKED")
        self.assertIn("SOURCE_MISSING", result["blockers"])
        self.assertTrue((self.out/"missing-source-result/blocker.json").is_file())
        self.assertFalse((self.out/"missing-source-result/dataset.json").exists())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    d.isolated(args.out)
    args.out.mkdir(parents=True, exist_ok=False)
    ScenarioTests.out = args.out.resolve()
    ScenarioTests.exe = args.exe.resolve()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ScenarioTests))
    d.write(args.out/"self-test.json", dict(kind="Sol self-test; not independent reviewer acceptance", tests=result.testsRun,
        success=result.wasSuccessful(), failures=len(result.failures), errors=len(result.errors),
        protocol=d.PROTOCOL, real_pit_days_added=0, real_historical_eligibility="DENIED"))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
