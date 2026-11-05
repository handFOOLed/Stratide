"""Issue #82 focused production-path tests; synthetic HTTP only, no credentials."""
import datetime as dt
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import market_eod as m

DAY = "20261104"
A, B, S, N, D, U, BJ = "600000.SH", "000001.SZ", "000002.SZ", "600001.SH", "000003.SZ", "600002.SH", "920001.BJ"


def catalog():
    result = []
    for code in (A, B, S, N, D, U, BJ):
        result.append(dict(ts_code=code, symbol=code[:6], name="合成证券" + code,
            exchange={"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}[code[-2:]], market="主板",
            list_status="D" if code == D else "L", list_date=DAY if code == N else "20261105" if code == U else "20000101",
            delist_date="20261103" if code == D else None))
    return result


def bar(code, date):
    return dict(ts_code=code, trade_date=date, open="10.01", high="10.50", low="9.50", close="10.10",
                pre_close="10.00", change="0.10", pct_chg="1", vol="100", amount="101.0")


class HTTP:
    def __init__(self):
        self.calls = []
        self.catalog = catalog()
        self.catalog_omissions = set()
        self.resumed = set()
        self.failures = {}
        self.missing = set()
        self.missing_dates = {}
        self.bad = set()
        self.duplicates = False
        self.closed = set()
        self.cap = False

    def __call__(self, api, params, fields):
        self.calls.append((api, dict(params)))
        failure = (api, params.get("suspend_type")) if (api, params.get("suspend_type")) in self.failures else api
        if failure in self.failures:
            value = self.failures.pop(failure)
            if isinstance(value, Exception):
                raise value
            return value
        if api == "stock_basic":
            rows = [r for r in self.catalog if r["exchange"] == params["exchange"] and r["list_status"] == params["list_status"]
                    and (params["exchange"], params["list_status"]) not in self.catalog_omissions]
        elif api == "trade_cal":
            rows = [dict(exchange=params["exchange"], cal_date=d, is_open=int(d not in self.closed),
                         pretrade_date=(m.h.day(d)-dt.timedelta(days=1)).strftime("%Y%m%d"))
                    for d in m.h.dates(params["start_date"], params["end_date"])]
        else:
            date = params["trade_date"]
            active = [r["ts_code"] for r in self.catalog if r["list_date"] <= date and
                      (r["delist_date"] is None or date < r["delist_date"]) and r["ts_code"] != S]
            active = [c for c in active if c not in self.missing and c not in self.missing_dates.get(date, set())]
            if api == "daily":
                rows = [bar(c, date) for c in active]
                for row in rows:
                    if row["ts_code"] in self.bad:
                        row["low"] = "20"
                if params.get("ts_code"):
                    rows = [r for r in rows if r["ts_code"] in params["ts_code"].split(",")]
                elif self.cap:
                    rows = rows[:6000]
            elif api == "adj_factor":
                rows = [dict(ts_code=c, trade_date=date, adj_factor="1") for c in active]
            elif api == "daily_basic":
                rows = [dict(ts_code=c, trade_date=date, close="10.10", turnover_rate="1", total_mv="100") for c in active]
            elif api == "suspend_d":
                rows = [dict(ts_code=S, trade_date=date, suspend_type="S", suspend_timing=None)] if S in {r["ts_code"] for r in self.catalog} else []
                rows += [dict(ts_code=c, trade_date=date, suspend_type="R", suspend_timing=None) for c in sorted(self.resumed)]
                if params.get("suspend_type"):
                    rows = [r for r in rows if r["suspend_type"] == params["suspend_type"]]
                if params.get("ts_code"):
                    rows = [r for r in rows if r["ts_code"] in params["ts_code"].split(",")]
        if self.duplicates and rows:
            rows = list(reversed(rows)) + [rows[0]]
        names = fields.split(",")
        raw = m.canonical(dict(code=0, data=dict(fields=names, items=[[r.get(f) for f in names] for r in rows])))
        return 200, raw, ""


class MarketTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "state/test-market-eod"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.market = m.Market(Path(self.temp.name))
        self.http = HTTP()
        self.at = "2026-11-04T08:10:00+00:00"
        self.market.initialize(DAY, data_mode="synthetic_test")
        self.market.control(True)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(m.h, "now", lambda: self.at).start()
        # Exercise the actual journal/transport path without real wall-clock waits.
        original = m.Download.__init__
        def init(download, *args, **kwargs):
            kwargs["sleep"] = lambda seconds: None
            original(download, *args, **kwargs)
        mock.patch.object(m.Download, "__init__", init).start()

    def once(self, **kwargs):
        return self.market.once(transport=self.http, clock=lambda: self.at, **kwargs)

    def research_agent(self, enabled):
        """Only a synthetic Agent schema, never the repository Owner binding."""
        import market_research as research
        common = self.market.root / "test-common"
        binding_dir = common / "state/risk-portfolio"
        agent = common / "agent"
        binding_dir.mkdir(parents=True)
        agent.mkdir()
        settings = agent / "settings.json"
        settings.write_text("{}", encoding="utf-8")
        config = dict(automatic_timesfm=enabled, automatic_deepseek=enabled, candidate_count=8,
                      daily_call_limit=1, trading_day_call_limit=1,
                      model_version="DeepSeek-V4.1-Flash-1017_ALIAS_MUTABLE")
        bound = dict(schema_version=1, agent_dir=str(agent), settings_path=str(settings), authority_id="a"*64)
        (binding_dir / "agent-binding.json").write_text(json.dumps(bound), encoding="utf-8")
        with contextlib.closing(sqlite3.connect(agent / "agent.sqlite")) as db, db:
            db.executescript("PRAGMA application_id=1397899569; PRAGMA user_version=1; "
                             "CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);")
            db.executemany("INSERT INTO meta VALUES(?,?)", [
                ("risk_portfolio_authority_id", bound["authority_id"]),
                ("risk_portfolio_settings_path", str(settings)), (research.CONFIG, json.dumps(config))])
        mock.patch.object(m, "common_root", return_value=common).start()
        mock.patch.object(research.rp, "root", return_value=binding_dir).start()
        paid = mock.patch.object(research, "bridge", side_effect=AssertionError("unexpected cloud bridge")).start()
        return research, agent, config, paid

    def collect_via_cli(self, action):
        """Exercise cli + real collector/journal, with synthetic HTTP and no waits."""
        original = m.Market.once
        def collect(market, **kwargs):
            return original(market, transport=self.http, clock=lambda: self.at)
        def next_poll(seconds):
            self.assertEqual(seconds, 30)
            if self.at.startswith("2026-11-04"):
                self.at = "2026-11-05T08:10:00+00:00"
            else:
                raise KeyboardInterrupt
        output = io.StringIO()
        with mock.patch.object(m.Market, "once", collect), mock.patch.object(m.time, "sleep", next_poll), \
                contextlib.redirect_stdout(output):
            if action == "watch":
                with self.assertRaises(KeyboardInterrupt):
                    m.cli([action, "--root", str(self.market.root)])
            else:
                self.assertEqual(m.cli([action, "--root", str(self.market.root)]), 0)
        results = [json.loads(line) for line in output.getvalue().splitlines()]
        expected = [DAY, "20261105"] if action == "watch" else [DAY]
        self.assertEqual(len(results), len(expected))
        self.assertTrue(all(v["state"] == "READY" for v in results), results)
        with self.market.read() as db:
            for day in expected:
                self.assertEqual(self.market.load_snapshot(db, day)["state"], "READY")
        self.assertEqual([p["trade_date"] for a,p in self.http.calls if a == "daily"], expected)
        return results

    def test_watch_disabled_but_unreadable_agent_does_not_stop_collection(self):
        research, agent, config, paid = self.research_agent(False)
        # Last persisted config is OFF; unreadable SQLite fails before that can be read.
        (agent / "agent.sqlite").write_bytes(b"unreadable synthetic Agent database")
        results = self.collect_via_cli("watch")
        for result in results:
            self.assertEqual(result["research"]["state"], "BLOCKED")
            self.assertEqual(result["research"]["reason"], "RESEARCH_UNAVAILABLE")
        paid.assert_not_called()

    def test_watch_enabled_agent_write_failure_does_not_stop_collection(self):
        research, agent, config, paid = self.research_agent(True)
        marker = "PRIVATE_AGENT_PATH_AND_KEY_NOT_FOR_OUTPUT"
        with mock.patch.object(research, "save", side_effect=sqlite3.OperationalError(marker)) as save:
            results = self.collect_via_cli("watch")
        self.assertEqual(save.call_count, 2)
        self.assertTrue(all(v["research"]["reason"] == "RESEARCH_UNAVAILABLE" for v in results))
        self.assertNotIn(marker, json.dumps(results))
        paid.assert_not_called()

    def test_watch_worker_failure_does_not_stop_collection(self):
        research, agent, config, paid = self.research_agent(True)
        for day in (DAY, "20261105"):
            run = dict(state="SCREENED", source_day=day, batch="market-"+day, config=config,
                       plan_sha256="b"*64, events=["EOD_RECEIVED", "SCREENED"],
                       screen=dict(selected=[dict(instrument=A)], rules_sha256=research.rp.digest(research.RULES),
                                   implementation_sha256=m.sha(Path(research.__file__).read_bytes())))
            research.save(day, run)
        sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
        import cli as cpu
        with mock.patch.object(cpu, "bridge", return_value={}), \
                mock.patch.object(cpu, "once", side_effect=RuntimeError("private worker details")) as worker:
            results = self.collect_via_cli("watch")
        self.assertEqual(worker.call_count, 2)
        self.assertTrue(all(v["research"]["state"] == "BLOCKED" for v in results))
        self.assertNotIn("private worker details", json.dumps(results))
        paid.assert_not_called()

    def test_once_research_failure_keeps_successful_eod_result(self):
        research, agent, config, paid = self.research_agent(True)
        with mock.patch.object(research, "save", side_effect=sqlite3.OperationalError("private details")):
            result = self.collect_via_cli("once")[0]
        self.assertEqual(result["research"]["state"], "BLOCKED")
        self.assertEqual(result["research"]["reason"], "RESEARCH_UNAVAILABLE")
        self.assertNotIn("cloud_egress", result["research"])
        paid.assert_not_called()

    def test_watch_explicit_stop_from_research_still_propagates(self):
        research, agent, config, paid = self.research_agent(True)
        for signal in (KeyboardInterrupt, SystemExit):
            with self.subTest(signal=signal.__name__), \
                    mock.patch.object(m.Market, "once", return_value=dict(state="ALREADY_FROZEN")), \
                    mock.patch.object(research, "once", side_effect=signal):
                with self.assertRaises(signal):
                    m.cli(["watch", "--root", str(self.market.root)])
        paid.assert_not_called()

    def test_coverage_denominators_native_reuse_and_readonly_gate(self):
        self.http.duplicates = True
        self.assertEqual(self.once()["state"], "READY")
        snapshot = self.market.report()["latest"]
        self.assertEqual((snapshot["catalog_total"], snapshot["expected_market"], snapshot["actual_quoted"]), (7, 5, 4))
        self.assertEqual((snapshot["research_denominator"], snapshot["eligible_symbols"]), (2, sorted([A, B])))
        self.assertEqual(snapshot["market_coverage_bps"], 10000)
        self.assertEqual(sum(snapshot["categories"].values()), 7)
        self.assertEqual(snapshot["categories"], dict(DELISTED=1, NEW_LISTING=1, NOT_LISTED=1, QUOTED=2, SUSPENDED=1, UNSUPPORTED=1))
        self.assertEqual(len([a for a,p in self.http.calls if a == "daily"]), 1)
        calls = len(self.http.calls)
        self.assertEqual(self.once()["state"], "ALREADY_FROZEN")
        report = self.market.report()
        self.assertEqual(len(self.http.calls), calls)
        source = self.market.research_source(DAY, [A], self.at)
        self.assertEqual(source["sources"]["daily"][0]["ts_code"], A)
        self.assertFalse(source["paper_allowed"])
        with self.assertRaisesRegex(m.Error, "SOURCE_NOT_AVAILABLE"):
            self.market.research_source(DAY, [A], "2026-11-04T07:59:00Z")
        with self.assertRaisesRegex(m.Error, "SECURITY_NOT_ELIGIBLE"):
            self.market.research_source(DAY, [BJ], self.at)
        with self.market.read() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM day_rows").fetchone()[0], 4)
            self.assertGreater(sum(r[0] for r in db.execute("SELECT duplicates FROM attempts")), 0)
        self.assertEqual(report["last_successful_date"], DAY)

    def test_partial_late_arrival_retry_preserves_old_snapshot(self):
        self.http.missing.add(B)
        self.assertEqual(self.once()["state"], "BLOCKED")
        old = self.market.report()["latest"]
        self.assertEqual(old["missing_symbols"], [B])
        self.assertEqual(old["eligible_symbols"], [])
        count = len(self.http.calls)
        self.assertEqual(self.once()["state"], "WAITING_RETRY")
        self.assertEqual(len(self.http.calls), count)
        self.http.missing.clear()
        self.at = "2026-11-04T08:16:00+00:00"
        self.assertEqual(self.once()["state"], "READY")
        with self.market.read() as db:
            frozen = db.execute("SELECT content,sha FROM market_snapshots ORDER BY id LIMIT 1").fetchone()
            self.assertEqual(frozen[1], old["snapshot_sha256"])
            self.assertEqual(m.sha(frozen[0].encode()), old["snapshot_sha256"])

    def test_missing_exchange_catalog_cannot_claim_full_market_ready(self):
        for exchange, omissions, absent_quotes in (
            ("BSE", {("BSE", s) for s in m.h.STATUSES}, {BJ}),
            ("SSE", {("SSE", "L")}, {A, N, U}),
        ):
            with self.subTest(exchange=exchange):
                self.market = m.Market(self.market.root / exchange)
                self.market.initialize(DAY, data_mode="synthetic_test")
                self.market.control(True)
                self.http = HTTP()
                self.http.catalog_omissions = omissions
                self.http.missing = absent_quotes
                self.assertEqual(self.once()["state"], "BLOCKED")
                report = self.market.report()
                snapshot = report["latest"]
                self.assertEqual(snapshot["market_coverage_bps"], 10000)
                self.assertEqual(snapshot["catalog_state"], "NOT_VERIFIED")
                self.assertEqual(snapshot["catalog_scopes"][exchange]["listed_rows"], 0)
                self.assertFalse(snapshot["market_denominator_verified"])
                self.assertEqual(snapshot["eligible_symbols"], [])
                self.assertIsNone(report["last_successful_date"])
                with self.assertRaisesRegex(m.Error, "MARKET_DAY_NOT_QUALIFIED"):
                    self.market.research_source(DAY, [B], self.at)

    def test_catalog_shrink_preserves_missing_prior_securities_and_blocks(self):
        self.assertEqual(self.once()["state"], "READY")
        previous = self.market.report()["latest"]["snapshot_sha256"]
        self.http.catalog = [r for r in self.http.catalog if r["ts_code"] not in (N, U)]
        self.at = "2026-11-05T08:10:00+00:00"
        self.assertEqual(self.once()["state"], "BLOCKED")
        snapshot = self.market.report()["latest"]
        self.assertEqual(snapshot["catalog_missing_symbols"], sorted([N, U]))
        self.assertEqual(snapshot["catalog_scopes"]["SSE"]["listed_rows"], 1)
        self.assertEqual(snapshot["expected_market"], 6)
        self.assertEqual(snapshot["categories"]["CATALOG_MISSING"], 2)
        self.assertEqual(snapshot["eligible_symbols"], [])
        with self.market.read() as db:
            self.assertEqual(self.market.load_snapshot(db, DAY)["snapshot_sha256"], previous)

    def test_new_listing_and_explicit_delisting_keep_catalog_verified(self):
        self.assertEqual(self.once()["state"], "READY")
        new_code = "600003.SH"
        self.http.catalog = [dict(r, list_status="D", delist_date="20261105") if r["ts_code"] == A else r
                             for r in self.http.catalog]
        self.http.catalog.append(dict(self.http.catalog[0], ts_code=new_code, symbol=new_code[:6],
                                      list_status="L", list_date="20261105", delist_date=None))
        self.at = "2026-11-05T08:10:00+00:00"
        self.assertEqual(self.once()["state"], "READY")
        snapshot = self.market.report()["latest"]
        self.assertEqual(snapshot["catalog_state"], "VERIFIED")
        self.assertTrue(snapshot["market_denominator_verified"])
        self.assertEqual(snapshot["catalog_missing_symbols"], [])
        self.assertEqual(snapshot["categories"]["DELISTED"], 2)
        self.assertEqual(snapshot["categories"]["NEW_LISTING"], 2)
        self.assertEqual(snapshot["categories"]["UNSUPPORTED"], 1)
        self.assertEqual(snapshot["catalog_scopes"]["BSE"]["listed_rows"], 1)

    def test_suspension_requires_explicit_s_and_r_and_keeps_resume_separate(self):
        self.http.resumed = {B}
        self.assertEqual(self.once()["state"], "READY")
        queries = [p for a, p in self.http.calls if a == "suspend_d"]
        self.assertEqual({p["suspend_type"] for p in queries}, {"S", "R"})
        snapshot = self.market.report()["latest"]
        self.assertEqual(snapshot["suspend_query_types"], ["R", "S"])
        source = self.market.research_source(DAY, [B], self.at)
        self.assertEqual([r["suspend_type"] for r in source["sources"]["suspend_d"]], ["R"])
        self.at = "2026-11-05T08:10:00+00:00"
        self.http.failures[("suspend_d", "R")] = (200, m.canonical(dict(code=2002, msg="无接口权限")), "")
        self.assertEqual(self.once()["state"], "BLOCKED")
        snapshot = self.market.report()["latest"]
        self.assertEqual(snapshot["source_states"]["suspend_d"], "PERMISSION_DENIED")
        self.assertEqual(snapshot["eligible_symbols"], [])

    def test_anomalies_are_counted_and_not_admitted_to_native_daily(self):
        self.http.bad.add(A)
        self.assertEqual(self.once()["state"], "BLOCKED")
        snapshot = self.market.report()["latest"]
        self.assertIn(A, snapshot["anomalous_symbols"])
        self.assertEqual(snapshot["categories"]["ANOMALOUS"], 1)
        with self.market.read() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM daily_rows WHERE ts_code=?", (A,)).fetchone()[0], 0)

    def test_calendar_holiday_and_window_do_not_fetch_daily(self):
        self.at = "2026-11-04T07:59:00+00:00"
        self.assertEqual(self.once()["state"], "WAITING_FOR_COLLECTION_WINDOW")
        self.assertEqual(self.http.calls, [])
        self.at = "2026-11-04T08:10:00+00:00"
        self.http.closed.add(DAY)
        self.assertEqual(self.once()["state"], "MARKET_CLOSED")
        self.assertEqual({a for a,p in self.http.calls}, {"trade_cal"})
        self.at = "2026-11-04T10:01:00+00:00"
        self.assertEqual(self.once()["state"], "DEADLINE_REACHED")

    def test_network_429_restart_and_bound_on_retries(self):
        self.http.failures["daily"] = TimeoutError()
        self.assertEqual(self.once()["state"], "NETWORK_OUTCOME_UNKNOWN")
        saved = len(self.http.calls)
        self.market = m.Market(self.market.root)
        self.assertEqual(self.once()["state"], "WAITING_RETRY")
        self.assertEqual(len(self.http.calls), saved)
        self.at = "2026-11-04T08:16:00+00:00"
        self.http.failures["daily"] = (429, b"rate limited", "600")
        self.assertEqual(self.once()["state"], "RATE_LIMITED")
        self.at = "2026-11-04T08:22:00+00:00"
        self.assertEqual(self.once()["state"], "WAITING_RETRY")
        self.at = "2026-11-04T08:27:00+00:00"
        self.http.failures["daily"] = TimeoutError()
        self.assertEqual(self.once()["state"], "NETWORK_OUTCOME_UNKNOWN")
        self.at = "2026-11-04T08:33:00+00:00"
        self.assertEqual(self.once()["state"], "ATTEMPT_LIMIT_REACHED")
        self.assertEqual(len([a for a,p in self.http.calls if a == "daily"]), 3)

    def test_process_death_resumes_committed_sources_without_repeating_requests(self):
        def die(point):
            if point == "before_snapshot":
                raise SystemExit("simulated process death")
        with self.assertRaises(SystemExit):
            self.once(fault=die)
        before = len(self.http.calls)
        self.market = m.Market(self.market.root)
        self.assertEqual(self.once()["state"], "READY")
        self.assertEqual(len(self.http.calls), before)

    def test_required_and_optional_permission_states_are_honest(self):
        denied = (200, m.canonical(dict(code=2002, msg="无接口权限")), "")
        self.http.failures["daily_basic"] = denied
        self.assertEqual(self.once()["state"], "READY")
        report = self.market.report()
        self.assertEqual(report["interface_permissions"]["daily_basic"], "PERMISSION_DENIED")
        self.assertEqual(report["latest"]["source_states"]["daily_basic"], "PERMISSION_DENIED")
        self.market.research_source(DAY, [A], self.at)

    def test_required_permission_blocks_eligibility(self):
        self.http.failures["suspend_d"] = (200, m.canonical(dict(code=2002, msg="无接口权限")), "")
        self.assertEqual(self.once()["state"], "BLOCKED")
        snapshot = self.market.report()["latest"]
        self.assertEqual(snapshot["eligible_symbols"], [])
        self.assertEqual(snapshot["source_states"]["suspend_d"], "PERMISSION_DENIED")

    def test_incremental_sessions_holiday_and_late_backfill_are_separate(self):
        self.market = m.Market(self.market.root / "incremental")
        self.market.initialize("20261102", data_mode="synthetic_test")
        self.market.control(True)
        self.http.closed.add("20261103")
        self.http.missing_dates["20261102"] = {B}
        self.assertEqual(self.once()["state"], "BLOCKED")
        with self.market.read() as db:
            self.assertTrue(self.market.load_snapshot(db, "20261102")["late_backfill"])
            self.assertIsNone(self.market.load_snapshot(db, "20261103"))
            self.assertFalse(self.market.load_snapshot(db, DAY)["late_backfill"])
        self.http.missing_dates.clear()
        self.at = "2026-11-04T08:16:00+00:00"
        prior = len(self.http.calls)
        self.assertEqual(self.once()["state"], "READY")
        self.assertEqual([p["trade_date"] for a,p in self.http.calls[prior:] if a == "daily"], ["20261102"])
        self.at = "2026-11-05T08:10:00+00:00"
        prior = len(self.http.calls)
        self.assertEqual(self.once()["state"], "READY")
        self.assertEqual([p["trade_date"] for a,p in self.http.calls[prior:] if a == "daily"], ["20261105"])
        self.assertEqual(self.market.report()["last_successful_date"], "20261105")

    def test_actual_process_kill_leaves_unknown_request_and_resumes_with_cooldown(self):
        marker = self.market.root / "request-started"
        process = subprocess.Popen([sys.executable, "-B", __file__, "--crash-worker", str(self.market.root)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline:
                self.assertIsNone(process.poll())
                time.sleep(.02)
            self.assertTrue(marker.exists())
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stderr.close()
        self.assertEqual(self.once()["state"], "WAITING_RETRY")
        self.assertEqual(self.http.calls, [])
        self.at = "2026-11-04T08:16:00+00:00"
        self.assertEqual(self.once()["state"], "READY")
        self.assertEqual({a for a,p in self.http.calls}, {"daily", "adj_factor", "suspend_d", "daily_basic"})

    def test_six_thousand_boundary_is_partitioned_not_silently_complete(self):
        self.http.catalog = [dict(ts_code=f"{600000+i}.SH", symbol=str(600000+i), name="合成",
            exchange="SSE", market="主板", list_status="L" if i < 4000 else "P",
            list_date="20000101", delist_date=None) for i in range(5999)] + [r for r in catalog() if r["ts_code"] in (B, BJ)]
        self.http.cap = True
        self.assertEqual(self.once()["state"], "READY")
        snapshot = self.market.report()["latest"]
        self.assertEqual((snapshot["expected_market"], snapshot["actual_quoted"]), (6001, 6001))
        self.assertEqual(snapshot["source_states"]["daily"], "PARTITIONED_CURRENT_CATALOG")
        requests = [p for a,p in self.http.calls if a == "daily"]
        self.assertEqual(len(requests), 32)
        self.assertTrue(all(len(p["ts_code"].split(",")) > 1 for p in requests[1:-1]))

    def test_raw_sha_and_single_writer_fence(self):
        self.assertEqual(self.once()["state"], "READY")
        with m.h.writer_lock(self.market.root):
            with self.assertRaisesRegex(m.Error, "WRITER_BUSY"):
                self.once()
        with self.market.read() as db:
            request = db.execute("SELECT id FROM attempts WHERE api='daily'").fetchone()[0]
        self.market.raw_path(request).write_bytes(__import__("gzip").compress(b"{}"))
        with self.assertRaisesRegex(m.Error, "RAW_SHA_MISMATCH"):
            self.market.research_source(DAY, [A], self.at)

    def test_dashboard_refresh_is_readonly_counts_only_without_credentials(self):
        self.once()
        spec = importlib.util.spec_from_file_location("dashboard_bridge", ROOT / "scripts/dashboard-workspace.py")
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        config = dict(timesfm_batches=[], fusion_batches=[], operations=[], evaluation_dirs=[], registry_dirs=[], evidence_files=[])
        before = {p: (m.sha(p.read_bytes()), p.stat().st_mtime_ns) for p in self.market.root.rglob("*") if p.is_file()}
        with mock.patch.object(m, "default_root", lambda: self.market.root), mock.patch.object(m.h, "credential", side_effect=AssertionError("read-only credential read")):
            for _ in range(2):
                result = bridge.snapshot(config)["market"]
                self.assertEqual(result["latest"]["eligible_count"], 2)
                self.assertNotIn("eligible_symbols", result["latest"])
                self.assertNotIn("securities", result["latest"])
        after = {p: (m.sha(p.read_bytes()), p.stat().st_mtime_ns) for p in self.market.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_existing_timesfm_source_gate_uses_qualified_snapshot_without_inference(self):
        self.once()
        sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
        import history
        self.assertEqual(history.market_day(self.market.root, DAY, [A], self.at)["source_day"], DAY)
        with self.assertRaisesRegex(history.Blocked, "SECURITY_NOT_ELIGIBLE"):
            history.market_day(self.market.root, DAY, [BJ], self.at)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--crash-worker":
        market = m.Market(Path(sys.argv[2]))
        m.h.now = lambda: "2026-11-04T08:10:00+00:00"
        inherited_init = m.Download.__init__
        def init(download, *args, **kwargs):
            kwargs["sleep"] = lambda seconds: None
            inherited_init(download, *args, **kwargs)
        m.Download.__init__ = init
        original = HTTP()
        def blocked_transport(api, params, fields):
            if api == "daily":
                (market.root / "request-started").write_text("synthetic", encoding="utf-8")
                time.sleep(30)
            return original(api, params, fields)
        market.once(transport=blocked_transport, clock=m.h.now)
    else:
        unittest.main()
