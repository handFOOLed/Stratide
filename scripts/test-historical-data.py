"""Synthetic adapter probes only; no market provenance claim, no network."""
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("historical_data", Path(__file__).with_name("historical-data.py"))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class AdapterTests(unittest.TestCase):
    def test_exact_fen_and_lots_conversion_rejects_fraction_overflow_and_nonfinite(self):
        self.assertEqual(adapter.exact(Decimal("9.85"), 100), 985)
        self.assertEqual(adapter.exact(Decimal("123.45"), 100), 12345)
        for value in ("9.851", "-1", "NaN", "Infinity", "92233720368547759"):
            with self.assertRaises(ValueError):
                adapter.exact(Decimal(value), 100)

    def test_http_and_mcp_formats_and_duplicate_source_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/"fixture.json"
            file.write_text(json.dumps(dict(code=0, data=dict(fields=["ts_code", "trade_date", "open"],
                                                             items=[["600000.SH", "20260717", 9.85]]))))
            result = adapter.rows(file)
            self.assertEqual(result[0]["open"], Decimal("9.85"))
            file.write_text('[{"ts_code":"600000.SH","trade_date":"20260717","open":9.85}]')
            self.assertEqual(adapter.rows(file), result)
            with self.assertRaises(ValueError):
                adapter.index(result*2, "trade_date", "20260717", "20260717")

    def test_missing_rows_are_blocked_and_not_zero_filled_or_called_suspension(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/"source"
            source.mkdir()
            (source/"extraction.json").write_text(json.dumps(dict(
                params=dict(ts_code="600000.SH", exchange="SSE", start_date="20260717", end_date="20260717"),
                extracted_at_utc="2026-10-29T00:00:00Z")))
            (source/"calendar.json").write_text('[{"exchange":"SSE","cal_date":"20260717","is_open":1,"pretrade_date":"20260716"}]')
            for name in ("daily", "limits", "suspensions"):
                (source/f"{name}.json").write_text("[]")
            out = Path(temp)/"output"
            with self.assertRaisesRegex(ValueError, "missing/extra daily"):
                adapter.prepare(source, out, "20260717", "20260717")
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
