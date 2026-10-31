"""Fixed synthetic counterexamples; none certifies real-market or historical PIT."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import corporate_actions as ca


def fixture(root):
    facts = dict(symbol="600000.SH", event_id="synthetic-2026-event", event_type="CASH_DIVIDEND",
                 announcement_date="2026-07-09", record_date="2026-07-15", ex_date="2026-07-16",
                 scheduled_pay_date="2026-07-16", cash_amount="0.42", cash_unit="CNY_PER_SHARE",
                 currency="CNY", tax_basis="GROSS", tax_terms="按身份及持有期适用税款",
                 net_cash_amount="0.42", stock_dividend_ratio="0", capitalization_ratio="0",
                 rights_ratio="0", stock_listing_date="2026-07-16", sellable_date="2026-07-16",
                 actual_account_cash_received_at="2026-07-16T10:00:00Z")
    text = ("synthetic_test 600000 synthetic-2026-event 现金红利 每股人民币0.42元（含税）\n"
            "公告2026-07-09 登记2026-07-15 除息及发放2026-07-16\n"
            "按身份及持有期适用税款；每股净额0.42；送股0 转增0 配股0\n"
            "上市及可卖2026-07-16 实际到账2026-07-16T10:00:00Z")
    raw = text.encode()
    (root / "synthetic.txt").write_bytes(raw)
    document = dict(id="implementation", role="implementation", version="synthetic-v1", supersedes=None,
                    document_id="synthetic-2026-event", path="synthetic.txt", sha256=ca.sha(raw),
                    text_path="synthetic.txt", text_sha256=ca.sha(raw), public_url=None,
                    obtained_at="2026-10-01T00:00:00Z", disclosed_on="2026-07-09",
                    published_at=None,
                    disclosure_basis="document_signed_date", review_method="operator_manual_document_text_crosscheck")
    return dict(schema_version=1, evidence_kind="synthetic_test", symbol="600000.SH", breakpoint="2026-07-16",
                decision_at="2026-07-16T01:30:00Z", documents=[document],
                events=[dict(source_id="implementation", facts=facts,
                             references={k: dict(page=1, quote=text) for k in facts})], historical_source=None)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "state").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "state")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = fixture(self.root)
        self.path = self.root / "source-manifest.json"
        self.out = self.root / "bundle"

    def save(self):
        self.path.write_bytes(ca.canonical(self.manifest))

    def audit(self):
        self.save()
        return ca.audit(self.path, self.out)

    def evaluate(self):
        return ca.evaluate(self.manifest, self.root)[0]

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/corporate-action-evidence.py"), *map(str, args)],
                                capture_output=True, cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return result.returncode, json.loads(result.stdout)

    def test_complete_synthetic_is_only_source_pass_and_status_recomputes(self):
        result = self.audit()
        self.assertEqual(result["status"], "FOUND_VERIFIABLE_EVENT")
        self.assertEqual(result["event_fact_status"], "SYNTHETIC_PASS")
        self.assertEqual(result["historical_pit_status"], "NOT_VERIFIED")
        self.assertEqual(result["accounting_support_status"], "NOT_IMPLEMENTED")
        self.assertFalse(result["historical_replay_eligible"])
        self.assertEqual(result, ca.status(self.out))
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertEqual(self.cli("status", "--bundle", self.out), (0, result))

    def test_missing_announcement_publishes_real_blocked_bundle_and_cli_exit_2(self):
        self.manifest.update(documents=[], events=[])
        result = self.audit()
        self.assertEqual(result["status"], "DATA_BLOCKED")
        self.assertIn("SOURCE_MISSING", result["blockers"])
        self.assertTrue(result["next_required_evidence"])
        self.assertEqual(self.cli("status", "--bundle", self.out), (2, result))

    def test_missing_date_or_unit_remains_null_and_partial(self):
        for field in ("ex_date", "cash_unit"):
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest["events"][0]["facts"][field] = None
                del manifest["events"][0]["references"][field]
                result = ca.evaluate(manifest, self.root)[0]
                self.assertEqual(result["status"], "PARTIAL")
                self.assertEqual(result["events"][0]["facts"][field], None)
                self.assertIn("FACT_MISSING:" + field, result["blockers"])
        self.manifest = manifest
        self.save()
        code, result = self.cli("audit", "--source-manifest", self.path, "--out", self.out)
        self.assertEqual((code, result["status"]), (1, "PARTIAL"))

    def test_conflicting_versions_retained_even_with_supersedes(self):
        second = copy.deepcopy(self.manifest["documents"][0])
        second.update(id="corrected", role="correction", supersedes="implementation", version="synthetic-v2",
                      path="corrected.txt", text_path="corrected.txt")
        raw = (self.root / "synthetic.txt").read_bytes().replace(b"0.42", b"0.43")
        (self.root / "corrected.txt").write_bytes(raw)
        second.update(sha256=ca.sha(raw), text_sha256=ca.sha(raw))
        event = copy.deepcopy(self.manifest["events"][0])
        event["source_id"] = "corrected"
        for field in ("cash_amount", "net_cash_amount"):
            event["facts"][field] = "0.43"
        for ref in event["references"].values():
            ref["quote"] = ref["quote"].replace("0.42", "0.43")
        self.manifest["documents"].append(second)
        self.manifest["events"].append(event)
        result = self.audit()
        self.assertEqual(result["event_fact_status"], "SOURCE_CONFLICT")
        self.assertEqual(len(result["documents"]), 2)
        self.assertIn("cash_amount", result["conflicting_fields"])
        self.assertFalse(result["historical_replay_eligible"])

    def test_exact_duplicate_is_idempotent_and_does_not_add_event(self):
        first = self.evaluate()
        self.manifest["documents"] *= 2
        self.manifest["events"] *= 2
        self.assertEqual(first, self.evaluate())
        result = self.audit()
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(len(result["events"]), 1)

    def test_wrong_source_sha_and_unsupported_quote_fail_without_publication(self):
        self.manifest["documents"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ca.Rejected, "SOURCE_SHA_MISMATCH"):
            self.audit()
        self.assertFalse(self.out.exists())
        self.manifest = fixture(self.root)
        self.manifest["events"][0]["facts"]["cash_amount"] = "42"
        with self.assertRaisesRegex(ca.Rejected, "FACT_QUOTE_VALUE_MISMATCH"):
            self.audit()
        self.manifest["events"][0]["facts"]["cash_amount"] = "0.42"
        self.manifest["events"][0]["references"]["cash_amount"]["quote"] = "不存在的原文0.42"
        with self.assertRaisesRegex(ca.Rejected, "QUOTE_NOT_IN_SOURCE"):
            self.audit()

    def test_disclosure_after_decision_cannot_be_pit_pass(self):
        self.manifest["documents"][0]["disclosed_on"] = "2026-07-17"
        result = self.audit()
        self.assertIn("DISCLOSED_AFTER_DECISION:implementation", result["blockers"])
        self.assertIn("ACQUIRED_AFTER_DECISION:implementation", result["blockers"])
        self.assertEqual(result["historical_pit_status"], "NOT_VERIFIED")
        self.assertFalse(result["historical_replay_eligible"])
        self.manifest["documents"][0].update(disclosed_on="2026-07-16", published_at="2026-07-16T01:31:00Z")
        result = self.evaluate()
        self.assertIn("DISCLOSED_AFTER_DECISION:implementation", result["blockers"])
        self.assertFalse(result["historical_replay_eligible"])

    def test_event_days_use_shanghai_timezone_and_exact_times_remain_utc_comparable(self):
        self.manifest["decision_at"] = "2026-07-16T00:30:00+08:00"
        self.manifest["documents"][0].update(disclosed_on="2026-07-16", obtained_at="2026-07-15T16:40:00Z")
        result = self.evaluate()
        self.assertEqual(result["decision_at"], "2026-07-15T16:30:00Z")
        self.assertIn("ACQUIRED_AFTER_DECISION:implementation", result["blockers"])
        self.assertNotIn("DISCLOSED_AFTER_DECISION:implementation", result["blockers"])
        self.assertFalse(result["historical_replay_eligible"])

    def test_business_sha_ignores_verification_and_acquisition_clock(self):
        first = self.audit()
        self.manifest["documents"][0]["obtained_at"] = "2026-10-02T00:00:00Z"
        self.out = self.root / "second-bundle"
        second = self.audit()
        self.assertEqual(first["bundle_sha256"], second["bundle_sha256"])
        self.assertNotEqual(first["obtained_at"], second["obtained_at"])
        # Same output is a byte-preserving reread, including the old verification time.
        saved = (self.out / "bundle.json").read_bytes()
        self.assertEqual(second, self.audit())
        self.assertEqual(saved, (self.out / "bundle.json").read_bytes())

    def test_half_write_and_failed_publish_retry_do_not_overwrite_old_evidence(self):
        original = ca.write_frozen
        calls = 0

        def interrupted(path, raw):
            nonlocal calls
            calls += 1
            if calls == 2:
                path.write_bytes(raw[:5])
                raise OSError("synthetic interrupted write")
            original(path, raw)

        with patch.object(ca, "write_frozen", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.audit()
        self.assertFalse(self.out.exists())
        abandoned = list(self.root.glob(".bundle.tmp-*"))
        self.assertEqual(len(abandoned), 1)
        with self.assertRaises(OSError):
            ca.status(abandoned[0])
        result = self.audit()
        saved = (self.out / "bundle.json").read_bytes()
        self.manifest["documents"][0]["version"] = "synthetic-v2"
        with self.assertRaisesRegex(ca.Rejected, "IMMUTABLE_BUNDLE_USE_NEW_OUTPUT"):
            self.audit()
        self.assertEqual(saved, (self.out / "bundle.json").read_bytes())
        self.assertEqual(result, ca.status(self.out))
        self.out = self.root / "failed-rename"
        with patch.object(ca.os, "rename", side_effect=OSError("synthetic publication fault")):
            with self.assertRaises(OSError):
                self.audit()
        self.assertFalse(self.out.exists())
        self.assertEqual(self.audit()["status"], "FOUND_VERIFIABLE_EVENT")

    def test_status_detects_original_or_summary_tampering(self):
        self.audit()
        text = next((self.out / "documents").glob("*.txt"))
        original = text.read_bytes()
        text.write_bytes(original + b"tampered")
        code, result = self.cli("status", "--bundle", self.out)
        self.assertEqual((code, result["error_code"]), (2, "SOURCE_SHA_MISMATCH"))
        text.write_bytes(original)
        file = self.out / "bundle.json"
        saved = json.loads(file.read_bytes())
        saved["content"]["historical_replay_eligible"] = True
        file.write_bytes(ca.canonical(saved))
        code, result = self.cli("status", "--bundle", self.out)
        self.assertEqual((code, result["error_code"]), (2, "BUNDLE_VERIFICATION_SHA_MISMATCH"))

    def test_strict_schema_types_units_dates_and_public_url(self):
        for change, code in ((lambda m: m.update(extra=True), "MANIFEST_SCHEMA"),
                (lambda m: m["events"][0]["facts"].update(cash_amount="NaN"), "FACT_DECIMAL_INVALID"),
                (lambda m: m["events"][0]["facts"].update(cash_unit="UNKNOWN"), "FACT_ENUM_INVALID"),
                (lambda m: m["events"][0]["facts"].update(ex_date="2026-02-30"), "DATE_INVALID"),
                (lambda m: m["documents"][0].update(public_url="https://example.org/private?token=secret"), "PUBLIC_URL_INVALID"),
                (lambda m: m["documents"][0].update(path="../outside.pdf"), "SOURCE_PATH_INVALID")):
            with self.subTest(code=code):
                manifest = copy.deepcopy(self.manifest)
                change(manifest)
                with self.assertRaisesRegex(ca.Rejected, code):
                    ca.evaluate(manifest, self.root)
        self.save()
        self.path.write_bytes(b'{"schema_version":1,"schema_version":1}')
        code, result = self.cli("audit", "--source-manifest", self.path, "--out", self.out)
        self.assertEqual((code, result["error_code"]), (2, "AMBIGUOUS_JSON"))
        # No exception's OS message or absolute input path may appear in stdout.
        code, result = self.cli("audit", "--source-manifest", self.root / "private-missing.json", "--out", self.out)
        self.assertEqual((code, result["error_code"]), (2, "SOURCE_IO_OR_FORMAT_ERROR"))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_size_and_output_boundary(self):
        file = self.root / "oversize.txt"
        with file.open("wb") as stream:
            stream.truncate(ca.MAX_FILE + 1)
        with self.assertRaisesRegex(ca.Rejected, "SOURCE_SIZE_OR_TYPE"):
            ca.read_file(file)
        self.save()
        with self.assertRaisesRegex(ca.Rejected, "OUTPUT_MUST_BE_NEW_STATE_DIRECTORY"):
            ca.audit(self.path, ROOT / "state/../../outside-evidence")

    def test_history_comparison_uses_sourced_amount_without_relaxing_replay(self):
        source = self.root / "historical"
        source.mkdir()
        rows = {
            "daily": [dict(ts_code="600000.SH", trade_date="20260715", close="10", pre_close="10"),
                      dict(ts_code="600000.SH", trade_date="20260716", close="9.58", pre_close="9.58")],
            "calendar": [dict(exchange="SSE", cal_date="20260715", is_open=1),
                         dict(exchange="SSE", cal_date="20260716", is_open=1)],
            "limits": [], "suspensions": [],
            "extraction": dict(params=dict(ts_code="600000.SH", exchange="SSE", start_date="20240101",
                                           end_date="20261028"), extracted_at_utc="2026-10-29T05:16:51.993Z"),
        }
        hashes = {}
        for name, value in rows.items():
            raw = ca.canonical(value)
            (source / (name + ".json")).write_bytes(raw)
            hashes[name] = ca.sha(raw)
        self.manifest["historical_source"] = dict(directory="historical", sha256=hashes)
        first = self.audit()
        self.assertEqual(first["consistency"]["event_ex_date_vs_breakpoint"], "DATE_MATCH")
        self.assertTrue(first["consistency"]["sourced_cash_vs_price_delta_match"])
        self.assertTrue(first["consistency"]["event_within_existing_fee_model"])
        self.assertFalse(first["historical_replay_eligible"])
        for name, expected in hashes.items():
            self.assertEqual(ca.sha((source / (name + ".json")).read_bytes()), expected)
        self.assertNotIn("observed_close_minus_pre_close_fen", json.dumps(first))
        # A missing event amount is never filled from the observed 42-fen delta.
        self.manifest["events"][0]["facts"]["cash_amount"] = None
        del self.manifest["events"][0]["references"]["cash_amount"]
        result = self.evaluate()
        self.assertIsNone(result["events"][0]["facts"]["cash_amount"])
        self.assertIsNone(result["consistency"]["sourced_cash_vs_price_delta_match"])
        # A different date is not forced to match. Keep the actual source claim.
        self.manifest = fixture(self.root)
        raw = (self.root / "synthetic.txt").read_bytes().replace(b"2026-07-16", b"2026-07-17")
        (self.root / "synthetic.txt").write_bytes(raw)
        self.manifest["documents"][0].update(sha256=ca.sha(raw), text_sha256=ca.sha(raw))
        for field in ("ex_date", "scheduled_pay_date", "stock_listing_date", "sellable_date"):
            self.manifest["events"][0]["facts"][field] = "2026-07-17"
        self.manifest["events"][0]["facts"]["actual_account_cash_received_at"] = "2026-07-17T10:00:00Z"
        for ref in self.manifest["events"][0]["references"].values():
            ref["quote"] = raw.decode()
        self.manifest["historical_source"] = dict(directory="historical", sha256=hashes)
        result = self.evaluate()
        self.assertEqual(result["consistency"]["event_ex_date_vs_breakpoint"], "DATE_MISMATCH")
        self.assertIn("EVENT_BREAKPOINT_DATE_MISMATCH", result["blockers"])

    def test_actual_directory_junction_or_symlink_is_rejected(self):
        target = self.root / "target"
        target.mkdir()
        link = self.root / "linked"
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(target, target_is_directory=True)
        try:
            with self.assertRaisesRegex(ca.Rejected, "LINK_PATH_DENIED"):
                ca.read_file(link / "anything.txt")
            self.save()
            with self.assertRaisesRegex(ca.Rejected, "LINK_PATH_DENIED"):
                ca.audit(self.path, link / "bundle")
        finally:
            if os.name == "nt":
                link.rmdir()  # Remove only the known junction, never recurse into target.
            else:
                link.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
