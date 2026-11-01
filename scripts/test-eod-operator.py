"""Subprocess E2E; synthetic 1041 fixtures + loopback HTTP + original Rust Fake.

Clock/collector injection exists only in this test runner. The real collector
protocol is unchanged and separately exercised by stratide-forward regressions.
Every test allocates new ignored source/store/Agent/operator state.
"""
import argparse
import copy
import ctypes
import datetime as dt
from decimal import Decimal
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import eod_operator as o


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


af = module("auto_fixtures", ROOT / "scripts/test-eod-auto.py")
f = af.f
WORK = af.WORK
DAYS = [(dt.date(2026, 8, 1) + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(23)]
COMMANDS, CHECKS = [], []


def stamp(day, hour=18, minute=0):
    return int(dt.datetime.strptime(day, "%Y%m%d").replace(tzinfo=o.j.ZONE,
               hour=hour, minute=minute).timestamp() * 1000)


def append(path, event):
    # Real SQLite append/checkpoint transaction; never delete/rewrite an old row.
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        seq, previous = db.execute("SELECT seq,digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        digest = o.j.sha(json.dumps([1, "forward_observation", previous, seq + 1, payload],
                                    ensure_ascii=False, separators=(",", ":")).encode())
        db.execute("INSERT INTO events VALUES(?,?,?)", (seq + 1, payload, digest))
        db.execute("UPDATE checkpoint SET seq=?,digest=? WHERE id=1", (seq + 1, digest))


class HttpFixture:
    def __init__(self, scenario="valid"):
        self.scenario, self.calls = scenario, []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                api, day = request["api_name"], request["day"]
                fixture.calls.append(dict(api=api, day=day))
                scenario = fixture.scenario
                if scenario == "unknown":
                    self.connection.shutdown(2)
                    self.connection.close()
                    return
                code = 429 if scenario == "rate" else 403 if scenario == "permission" else 200
                if api == "trade_cal":
                    start, end = o.j.date(request["from"]), o.j.date(day)
                    fields = ["exchange", "cal_date", "is_open"]
                    rows = [["SSE", (start + dt.timedelta(days=i)).strftime("%Y%m%d"),
                             0 if scenario == "closed" and i == (end - start).days else 1]
                            for i in range((end - start).days + 1)]
                    if scenario == "calendar_unknown":
                        rows = []
                else:
                    fields = ["ts_code", "trade_date", "open", "high", "low", "close", "vol"]
                    close = "11.00" if day == DAYS[20] else "9.00" if day == DAYS[21] else "10.00"
                    rows = [["600000.SH", "19990101" if scenario == "wrong_day" else day,
                             "10.00", "12.00", "9.00", close, "100"]]
                    if scenario == "empty":
                        rows = []
                body = json.dumps(dict(code=0, data=dict(fields=fields, items=rows)), separators=(",", ":")).encode()
                self.send_response_only(code)
                self.send_header("Date", dt.datetime.fromtimestamp(request["at"] / 1000,
                                  dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def fixture_cli(request, stage=None):
    name, now = request["name"], request["at"]
    assert name.startswith("auto-test-") and Path(request["observer"]).is_relative_to(WORK.parent)

    def collector(path, reports, token):
        assert token == "synthetic-token-never-public" and request["port"]
        content, _ = o.j.read_observer(path)
        assert content["data_mode"] == "synthetic_test"
        key = o.j.day(now)
        last = content["coverage"][-1]["source_day"]
        run = "operator-synthetic-" + str(content["event_count"])
        append(path, dict(event="collection_started", run_id=run, observed_at=now,
                         trade_day=key, calendar_from=last, calendar_through=key))
        if request.get("fault") == "collector_started":
            os._exit(86)
        outcome = dict(status="collecting", raw=[], calendar=[], bar=None, provider_published_at=None,
                       available_at=None, duplicate_of=None, revision_of=None, late_backfill=False)

        def fetch(api):
            conn = http.client.HTTPConnection("127.0.0.1", request["port"], timeout=5)
            try:
                conn.request("POST", "/", json.dumps(dict(api_name=api, day=key, **{"from": last}, at=now)))
                response = conn.getresponse()
                body = response.read()
                raw = dict(api=api, http_status=response.status, server_date=response.getheader("Date"),
                           body=list(body), sha256=o.j.sha(body), received_at=now)
                outcome["raw"].append(raw)
                if response.status != 200:
                    raise o.j.Rejected("rate_limited" if response.status == 429 else "permission_denied")
                return o.j.response(raw)
            finally:
                conn.close()

        try:
            cal = fetch("trade_cal")
            if not cal:
                raise o.j.Rejected("calendar_incomplete")
            outcome["calendar"] = [dict(day=r["cal_date"], is_open=bool(r["is_open"])) for r in cal]
            if not outcome["calendar"][-1]["is_open"]:
                outcome["status"] = "market_closed"
            else:
                rows = fetch("daily")
                fault("collector_inflight")
                if not rows:
                    raise o.j.Rejected("missing_daily_not_proof_of_suspension")
                row = rows[0]
                if row["trade_date"] != key:
                    raise o.j.Rejected("daily_identity_mismatch")
                outcome.update(status="valid_eod", available_at=now,
                    bar=dict(trade_day=key, **{field + "_fen": o.j.exact(row[field]) for field in ("open", "high", "low", "close")},
                             volume_shares=o.j.exact(row["vol"]), source_volume_unit="hand_100_shares", price_semantics="unadjusted_cny_fen"))
        except o.j.Rejected as error:
            outcome["status"] = str(error)
        except (OSError, http.client.HTTPException):
            outcome["status"] = "network_timeout_or_tls_error"
        append(path, dict(event="collection_finished", run_id=run, finished_at=now, outcome=outcome))
        return 0  # deliberately uninformative: Operator must read the original DB

    def invoke(action, auto_name):
        env = dict(os.environ, STRATIDE_AUTO_FIXTURE_TEST="1")
        process = subprocess.run([str(af.test_exe()), "--exact", "tests::fixture_cli", "--nocapture"],
            input=json.dumps(dict(args=[action, auto_name], now_ms=now, fixture_source=request["observer"])).encode(),
            capture_output=True, env=env, timeout=45)
        found = re.search(rb"EOD_AUTO_FIXTURE_RESULT=(\{[^\n]+\})", process.stdout)
        assert process.returncode == 0 and found, (process.stdout, process.stderr)
        result = json.loads(found[1])
        o.j.require(result["exit_code"] == 0, result["value"].get("error_code", "BRIDGE_TEST_ERROR"))
        return result["value"]

    def spawn(stage, store, observer, reports, auto_name, token):
        assert store == name and (stage != "collector" or token == "synthetic-token-never-public")
        if stage == "collector" and request.get("pause_dispatch"):
            Path(request["marker"] + ".dispatch").write_text("last_enabled_check_completed_before_Popen")
            while not Path(request["release"] + ".dispatch").exists():
                time.sleep(0.02)
        path = Path(request["marker"]).with_suffix(".stage.json")
        path.write_bytes(o.j.canonical(dict(request=request, stage=stage)))
        return subprocess.Popen([sys.executable, "-X", "utf8", "-B", str(Path(__file__).absolute()),
                                 "--fixture-stage", str(path)], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def fault(point):
        if point == "after_fake" and request.get("fault") == "operator_receipt":
            service = o.Operator(name, clock=lambda: now)
            with service.write() as db:
                db.execute("PRAGMA cache_size=1")
                service.append(db, "receipt", dict(state="UNCOMMITTED_TEST", source_day=o.j.day(now),
                                                  refs={}, reason="synthetic" * 2000))
                os._exit(86)  # real hot DELETE journal, before receipt commit
        if point == request.get("fault"):
            os._exit(86)
        if point == request.get("pause"):
            Path(request["marker"]).write_text(point)
            while not Path(request["release"]).exists():
                time.sleep(0.02)

    def wait(_):
        raise KeyboardInterrupt

    env = dict(os.environ)
    env.pop("STRATIDE_TUSHARE_TOKEN", None)
    if not request.get("missing_token"):
        env["STRATIDE_TUSHARE_TOKEN"] = "synthetic-token-never-public"
    original_once = o.Operator.once
    original_start = o.Operator.start
    original_control = o.Operator.control
    def checked_control(service, enabled):
        if not enabled and request.get("mark_control"):
            Path(request["marker"]).write_text("disable_entered")
        return original_control(service, enabled)

    def checked_start(service, stage, day):
        original_start(service, stage, day)
        fault("before_" + stage + "_dispatch")

    def checked_once(service):
        try:
            return original_once(service)
        except Exception:
            traceback.print_exc()  # isolated synthetic runner only
            raise
    with patch.dict(os.environ, env, clear=True), patch.object(o.d, "now", return_value=now), \
         patch.object(o.Operator, "once", checked_once), patch.object(o.Operator, "start", checked_start), \
         patch.object(o.Operator, "control", checked_control):
        if stage == "collector":
            return collector(Path(request["observer"]), None, env["STRATIDE_TUSHARE_TOKEN"])
        if stage == "snapshot":
            return 0 if o.d.Store(name).sync()["can_research"] else 2
        if stage == "shadow":
            o.s.Shadow(name, clock=lambda: now).once()
            return 0
        if stage == "fake":
            o.a.Auto(name, clock=lambda: now, invoke=invoke).once()
            return 0
        return o.main(["--snapshot-store", name, *request["args"]], clock=lambda: now,
                      spawn=spawn, fault=fault, wait=wait)


def launch(name, *args, at=None, port=0, cwd=ROOT, **options):
    directory = WORK / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("request-" + os.urandom(5).hex() + ".json")
    request = dict(name=name, observer=str(directory / "forward.sqlite"), at=at or stamp(DAYS[1]),
                   args=list(map(str, args)), port=port, marker=str(path.with_suffix(".marker")),
                   release=str(path.with_suffix(".release")), **options)
    path.write_bytes(o.j.canonical(request))
    process = subprocess.Popen([sys.executable, "-X", "utf8", "-B", str(Path(__file__).absolute()), "--fixture-cli", str(path)],
                               cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.request = request
    return process


def finish(process, code=0, timeout=90):
    out, err = process.communicate(timeout=timeout)
    if process.returncode != code:
        raise AssertionError(f"{process.request['args']}: expected {code}, got {process.returncode}: {out[:2200]!r} {err[:2200]!r}")
    values = [json.loads(line) for line in out.splitlines()]
    value = values[-1] if values else None
    COMMANDS.append(dict(command=["eod-operator.py", "--snapshot-store", process.request["name"], *process.request["args"]],
                         at=process.request["at"], fault=process.request.get("fault"), exit_code=code, result=value))
    return value


def call(name, *args, code=0, **options):
    return finish(launch(name, *args, **options), code)


def setup(label, *, auto=False, enabled=True, shadow_enabled=True):
    name = "auto-test-operator-" + label + "-" + os.urandom(4).hex()
    path = WORK / name / "forward.sqlite"
    path.parent.mkdir(parents=True)
    events = f.base_events()[:1]
    events[0]["config"]["observation_id"] = name
    events[0]["started_at"] = f.stamp(DAYS[0]) - 1000
    f.append_day(events, DAYS[0])
    f.save_journal(path, events)
    initial = stamp(DAYS[0], 17, 1)
    with patch.object(o.d, "now", return_value=initial):
        assert o.d.Store(name).sync(observer=path)["can_research"]
    shadow = o.s.Shadow(name, clock=lambda: initial)
    shadow.init()
    if shadow_enabled:
        shadow.control(True)
    if auto:
        af.call(name, "init", "--snapshot-store", name, now=initial)
        af.call(name, "enable", now=initial)
    call(name, "init", "--observer", path, "--credential-source", "process-env",
         *(["--auto-name", name] if auto else []), at=initial)
    if enabled:
        call(name, "enable", at=initial)
    return name, path


def fingerprint(paths):
    result = {}
    for root in paths:
        for path in ([root] if root.is_file() else root.rglob("*") if root.exists() else []):
            if path.is_file():
                result[str(path)] = (path.stat().st_mtime_ns, o.j.sha(path.read_bytes()))
    return result


def authorities(name, observer):
    paths = dict(observer=observer, snapshot=o.d.Store(name).path, shadow=o.s.Shadow(name).path,
                 agent=o.a.Auto(name).dbpath)
    hashes = {label: {suffix or "main": o.j.sha(path.read_bytes()) if path.exists() else None
                       for suffix in ("", "-wal", "-shm", "-journal")
                       for path in [Path(str(base) + suffix)]} for label, base in paths.items()}
    counts = {}
    for label, path in paths.items():
        tables = dict(observer=("events",), snapshot=("snapshots",), shadow=("inputs",), agent=("tasks", "calls"))[label]
        with o.s.readonly(path) as db:
            counts.update({label + "_" + table: db.execute("SELECT count(*) FROM " + table).fetchone()[0]
                           for table in tables})
    counts["registrations"] = len(list((ROOT / "state/candidates" / name / "registrations").glob("*.json")))
    return dict(sha256=hashes, counts=counts)


class OperatorTests(unittest.TestCase):
    def test_two_22_day_chains_original_shadow_and_rust_fake(self):
        outcomes = []
        for label in ("full-a", "full-b"):
            name, path = setup(label, auto=True)
            results = []
            with HttpFixture() as http:
                for i in range(22):
                    value = call(name, "once", at=stamp(DAYS[i], 17, 5), port=http.port)
                    self.assertEqual(value["state"], "COMPLETE")
                    self.assertEqual(value["refs"]["fake"]["fake_calls"], 1)
                    results.append(value["refs"]["shadow"]["result"])
                    again = call(name, "once", at=stamp(DAYS[i], 17, 5), port=http.port)
                    self.assertEqual(value, again)
                self.assertEqual(len(http.calls), 42)
                self.assertTrue(all(r["api"] in ("trade_cal", "daily") for r in http.calls))
            self.assertEqual(results[-2:], ["UP_CROSS", "DOWN_CROSS"])
            self.assertEqual(af.counts(name), dict(intents=22, tasks=22, calls=22, registrations=22))
            shadow = o.s.Shadow(name)
            with o.s.readonly(shadow.path) as db:
                state = shadow.journal(db)
            for record in state["observations"]:
                material = record["material"]
                closes = [Decimal(v["bar"]["close_fen"]) for v in material["window"]]
                if len(closes) == 21:
                    before = sum(closes[:20][-5:]) / 5 > sum(closes[:20]) / 20
                    after = sum(closes[-5:]) / 5 > sum(closes[-20:]) / 20
                    expected = "NO_CROSS" if before == after else "UP_CROSS" if after else "DOWN_CROSS"
                    self.assertEqual(material["calculation"]["result"], expected)
            protected = [path, o.d.Store(name).root, shadow.root, o.Operator(name).root,
                         o.a.Auto(name).root, ROOT / "state/candidates" / name]
            before = fingerprint(protected)
            for action in ("status", "history", "verify", "report"):
                result = call(name, action, at=stamp(DAYS[21]))
                self.assertTrue(result["authoritative_evidence_verified"])
                text = json.dumps(result)
                self.assertNotIn("synthetic-token-never-public", text)
                self.assertNotIn(str(ROOT), text)
                self.assertNotIn("close_fen", text)
                self.assertEqual((result["orders"], result["fills"], result["nav"]), (0, 0, None))
            self.assertEqual(before, fingerprint(protected))
            outcomes.append(results)
        self.assertEqual(*outcomes)
        CHECKS.append(dict(check="two_22_day_original_subsystems", outcomes=outcomes[0],
                           tasks=44, settled_fake_calls=44, registrations=44, loopback_requests=84,
                           independent_decimal=True, readonly_bytes_and_mtimes_unchanged=True))

    def test_persisted_enable_foreground_watch_window_disable_and_cutoff(self):
        name, _ = setup("window", enabled=False)
        with HttpFixture() as http:
            self.assertEqual(call(name, "once", at=stamp(DAYS[1], 15, 12), port=http.port)["state"], "DISABLED")
            call(name, "enable", at=stamp(DAYS[1], 15, 13))
            self.assertEqual(call(name, "once", at=stamp(DAYS[1], 15, 14), port=http.port)["state"], "WAITING_FOR_CLOSE_WINDOW")
            for minute in (15, 25, 55):
                value = call(name, "watch", "--interval-seconds", 60, at=stamp(DAYS[1], 15, minute), port=http.port, code=130)
                self.assertEqual(value["reason"], "EARLY_SOURCE_UNVERIFIED")
            self.assertEqual(http.calls, [])
            self.assertEqual(call(name, "watch", "--interval-seconds", 60, at=stamp(DAYS[1], 16), port=http.port, code=130)["state"], "COMPLETE")
            self.assertEqual(call(name, "once", at=stamp(DAYS[1], 16, 10), port=http.port)["state"], "COMPLETE")
            self.assertEqual(len(http.calls), 2)
            call(name, "disable", at=stamp(DAYS[1], 16, 11))
            self.assertEqual(call(name, "watch", "--interval-seconds", 60, at=stamp(DAYS[2]), port=http.port, code=130)["state"], "DISABLED")
            self.assertEqual(len(http.calls), 2)
            call(name, "enable", at=stamp(DAYS[2]))
            self.assertEqual(call(name, "once", at=stamp(DAYS[2]), port=http.port, code=3)["reason"], "MISSED_COLLECTION_WINDOW")
            self.assertEqual(len(http.calls), 2)

    def test_failure_responses_are_not_success_or_automatic_retries(self):
        for scenario, expected in (("empty", "DATA_NOT_READY"), ("unknown", "OUTCOME_UNKNOWN"),
                ("wrong_day", "SOURCE_BLOCKED"), ("closed", "MARKET_CLOSED"),
                ("calendar_unknown", "SOURCE_BLOCKED"), ("rate", "RATE_LIMITED"), ("permission", "PERMISSION_DENIED")):
            with self.subTest(scenario=scenario):
                name, path = setup(scenario)
                store_before = o.j.sha(o.d.Store(name).path.read_bytes())
                with HttpFixture(scenario) as http:
                    code = 0 if expected == "MARKET_CLOSED" else 3
                    value = call(name, "once", at=stamp(DAYS[1], 16), port=http.port, code=code)
                    self.assertEqual(value["state"], expected)
                    count = len(http.calls)
                    http.scenario = "valid"
                    again = call(name, "once", at=stamp(DAYS[1], 16, 10), port=http.port, code=code)
                    self.assertEqual(again["state"], expected)
                    self.assertEqual(len(http.calls), count)
                self.assertEqual(store_before, o.j.sha(o.d.Store(name).path.read_bytes()))
                self.assertNotIn("shadow", value["refs"])
                content, _ = o.j.read_observer(path)
                self.assertEqual(content["valid_eod_days"], 1)

    def test_missing_credential_does_not_spend_slot(self):
        name, path = setup("credential")
        before = o.j.sha(path.read_bytes())
        with HttpFixture() as http:
            for minute in (0, 10):
                result = call(name, "once", at=stamp(DAYS[1], 16, minute), port=http.port, missing_token=True, code=3)
                self.assertEqual(result["state"], "CREDENTIAL_UNAVAILABLE")
            self.assertEqual(http.calls, [])
            self.assertEqual(before, o.j.sha(path.read_bytes()))
            self.assertEqual(call(name, "once", at=stamp(DAYS[1], 16, 20), port=http.port)["state"], "COMPLETE")

    def test_four_process_kills_recover_authoritative_commits(self):
        for point in ("after_collect", "after_sync", "after_shadow", "after_fake"):
            with self.subTest(point=point):
                name, _ = setup(point, auto=True)
                with HttpFixture() as http:
                    call(name, "once", at=stamp(DAYS[1], 16), port=http.port, fault=point, code=86)
                    value = call(name, "once", at=stamp(DAYS[1], 16, 10), port=http.port)
                    self.assertEqual(value["state"], "COMPLETE")
                    self.assertEqual(len(http.calls), 2)
                    self.assertEqual(af.counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))
                    self.assertTrue(call(name, "verify", at=stamp(DAYS[1], 16, 10))["authoritative_evidence_verified"])
        CHECKS.append(dict(check="four_actual_process_kills", points=["after_collect", "after_sync", "after_shadow", "after_fake"],
                           exits=86, collector_attempts_each=1, fake_settlements_each=1))

    def test_kill_after_original_started_is_unknown_no_request(self):
        name, _ = setup("started")
        with HttpFixture() as http:
            killed = call(name, "once", at=stamp(DAYS[1], 16), port=http.port, fault="collector_started", code=3)
            self.assertEqual(killed["state"], "OUTCOME_UNKNOWN")  # collector child exits 86; parent retains its intent
            value = call(name, "once", at=stamp(DAYS[1], 16, 10), port=http.port, code=3)
            self.assertEqual(value["state"], "OUTCOME_UNKNOWN")
            self.assertEqual(http.calls, [])

    def test_own_hot_receipt_recovers_only_in_writer_without_rerunning_children(self):
        name, _ = setup("hot-receipt", auto=True)
        with HttpFixture() as http:
            call(name, "once", at=stamp(DAYS[1], 16), port=http.port, fault="operator_receipt", code=86)
            service = o.Operator(name)
            before = fingerprint([service.root])
            call(name, "report", at=stamp(DAYS[1], 16, 10), code=2)
            self.assertEqual(before, fingerprint([service.root]))
            result = call(name, "once", at=stamp(DAYS[1], 16, 10), port=http.port)
            self.assertEqual(result["state"], "COMPLETE")
            self.assertEqual(len(http.calls), 2)
            self.assertEqual(af.counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))
            self.assertTrue(call(name, "verify", at=stamp(DAYS[1], 16, 10))["authoritative_evidence_verified"])

    def wait_marker(self, process, suffix=""):
        deadline = time.monotonic() + 30
        while not Path(process.request["marker"] + suffix).exists():
            self.assertIsNone(process.poll())
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)

    def test_double_writer_and_disable_during_stage(self):
        name, _ = setup("concurrent", auto=True)
        with HttpFixture() as http:
            process = launch(name, "once", at=stamp(DAYS[1], 16), port=http.port, pause="after_sync")
            self.wait_marker(process)
            self.assertEqual(call(name, "once", at=stamp(DAYS[1], 16), port=http.port, code=2)["reason"], "STORE_BUSY")
            call(name, "disable", at=stamp(DAYS[1], 16))
            Path(process.request["release"]).write_text("release")
            self.assertEqual(finish(process)["state"], "DISABLED")
            self.assertEqual(len(http.calls), 2)
            self.assertEqual(af.counts(name), dict(intents=0, tasks=0, calls=0, registrations=0))
            with o.s.readonly(o.s.Shadow(name).path) as db:
                self.assertEqual(len(o.s.Shadow(name).journal(db)["observations"]), 0)

    def test_disable_return_before_dispatch_fences_all_four_stages(self):
        for stage in ("collector", "snapshot", "shadow", "fake"):
            with self.subTest(stage=stage):
                name, observer = setup("stop-" + stage, auto=True)
                with HttpFixture() as http:
                    process = launch(name, "once", at=stamp(DAYS[1], 16), port=http.port,
                                     pause="before_" + stage + "_dispatch")
                    self.wait_marker(process)
                    before = authorities(name, observer)
                    requests = len(http.calls)
                    disable = launch(name, "disable", at=stamp(DAYS[1], 16))
                    try:
                        self.assertEqual(finish(disable, timeout=10)["state"], "DISABLED")
                    finally:
                        Path(process.request["release"]).write_text("release")
                    result = finish(process)
                    after = authorities(name, observer)
                    CHECKS.append(dict(check="disable_before_dispatch", stage=stage, disable_exit=disable.returncode,
                                       once_exit=process.returncode, before=before, after=after,
                                       http_before=requests, http_after=len(http.calls)))
                    self.assertEqual(result["state"], "DISABLED")
                    self.assertEqual(before, after)
                    self.assertEqual(requests, len(http.calls))

    def test_disable_during_collector_keeps_raw_without_starting_downstream(self):
        name, observer = setup("stop-inflight", auto=True)
        before = authorities(name, observer)
        with HttpFixture() as http:
            process = launch(name, "once", at=stamp(DAYS[1], 16), port=http.port, pause="collector_inflight")
            self.wait_marker(process)
            self.assertEqual(len(http.calls), 2)
            disable = launch(name, "disable", at=stamp(DAYS[1], 16))
            try:
                self.assertEqual(finish(disable, timeout=10)["state"], "DISABLED")
            finally:
                Path(process.request["release"]).write_text("release")
            self.assertEqual(finish(process)["state"], "DISABLED")
            after = authorities(name, observer)
            CHECKS.append(dict(check="disable_inflight_collector", disable_exit=disable.returncode,
                               once_exit=process.returncode, before=before, after=after, http_calls=len(http.calls)))
            self.assertEqual(len(http.calls), 2)
        content, _ = o.j.read_observer(observer)
        self.assertEqual(content["last_valid_source_day"], DAYS[1])
        self.assertEqual(content["valid_eod_days"], 2)
        self.assertEqual(content["raw_sha256"][-2:][0]["api"], "trade_cal")
        self.assertEqual(after["counts"]["observer_events"], before["counts"]["observer_events"] + 2)
        for label in ("snapshot", "shadow", "agent"):
            self.assertEqual(before["sha256"][label], after["sha256"][label])
        self.assertEqual(after["counts"]["agent_calls"], 0)

    def test_last_enabled_check_through_actual_popen_is_one_transaction(self):
        name, observer = setup("stop-popen", auto=True)
        before = authorities(name, observer)
        with HttpFixture() as http:
            process = launch(name, "once", at=stamp(DAYS[1], 16), port=http.port,
                             pause_dispatch=True, pause="collector_inflight")
            disable, disabled = None, None
            try:
                self.wait_marker(process, ".dispatch")  # inside spawn, immediately before actual Popen
                disable = launch(name, "disable", at=stamp(DAYS[1], 16), mark_control=True)
                self.wait_marker(disable)
                with sqlite3.connect(o.Operator(name).path, timeout=0) as probe:
                    with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                        probe.execute("BEGIN IMMEDIATE")
                self.assertIsNone(disable.poll())
                Path(process.request["release"] + ".dispatch").write_text("allow_Popen")
                self.wait_marker(process)  # actual HTTP issued; collector deliberately still in flight
                disabled = finish(disable, timeout=10)
                self.assertEqual(disabled["state"], "DISABLED")
                self.assertIsNone(process.poll())  # disable did not wait for stage completion
            finally:
                Path(process.request["release"] + ".dispatch").write_text("release")
                Path(process.request["release"]).write_text("release")
                result = finish(process)
                if disable is not None and disabled is None:
                    disable.communicate(timeout=10)
            self.assertEqual(result["state"], "DISABLED")
            after = authorities(name, observer)
            self.assertEqual(len(http.calls), 2)
            for label in ("snapshot", "shadow", "agent"):
                self.assertEqual(before["sha256"][label], after["sha256"][label])
            CHECKS.append(dict(check="actual_Popen_held_transaction_against_disable", dispatch_transaction_locked=True,
                               disable_returned_before_collector_finished=True, disable_exit=disable.returncode,
                               once_exit=process.returncode, before=before, after=after, http_calls=len(http.calls)))

    def test_child_disabled_and_cross_source_refs(self):
        name, _ = setup("shadow-off", shadow_enabled=False)
        with HttpFixture() as http:
            result = call(name, "once", at=stamp(DAYS[1], 16), port=http.port, code=3)
            self.assertEqual(result["reason"], "SHADOW_OWNER_DISABLED")
        name, _ = setup("auto-off", auto=True)
        af.call(name, "disable", now=stamp(DAYS[1], 16))
        with HttpFixture() as http:
            result = call(name, "once", at=stamp(DAYS[1], 16), port=http.port, code=3)
            self.assertEqual(result["reason"], "AUTO_OWNER_DISABLED_OR_PAUSED")
            self.assertIn("shadow", result["refs"])
            self.assertEqual(af.counts(name)["calls"], 0)
        service = o.Operator(name)
        with self.assertRaises(o.j.Rejected):
            service.verify_refs(service.saved()["config"], DAYS[1], {}, complete=True)

    def test_canonical_alias_copy_cwd_and_links(self):
        name, path = setup("canonical")
        alias = name + "-alias"
        with patch.object(o.d, "now", return_value=stamp(DAYS[0])):
            o.d.Store(alias).sync(observer=path)
        first, second = o.Operator(name), o.Operator(alias)
        self.assertEqual(first.path, second.path)
        result = call(alias, "init", "--observer", path, at=stamp(DAYS[0]), code=2)
        self.assertEqual(result["reason"], "OPERATOR_ALREADY_INITIALIZED")
        self.assertEqual(call(alias, "enable", at=stamp(DAYS[0]), code=2)["reason"], "OPERATOR_BINDING_OWNED")
        copied = path.with_name("copied.sqlite")
        copied.write_bytes(path.read_bytes())
        copied_name = name + "-copy"
        with patch.object(o.d, "now", return_value=stamp(DAYS[0])):
            o.d.Store(copied_name).sync(observer=copied)
        self.assertEqual(first.path, o.Operator(copied_name).path)
        self.assertEqual(call(copied_name, "init", "--observer", copied, at=stamp(DAYS[0]), code=2)["reason"], "OPERATOR_ALREADY_INITIALIZED")
        self.assertEqual(call(name, "status", at=stamp(DAYS[0]), cwd=WORK)["binding_sha256"], first.key)
        link = o.d.Store(name + "-link").root
        if os.name == "nt":
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(o.d.Store(name).root)], capture_output=True)
            self.assertEqual(result.returncode, 0)
        else:
            link.symlink_to(o.d.Store(name).root, target_is_directory=True)
        try:
            self.assertEqual(call(name + "-link", "status", code=2)["reason"], "LINK_PATH_DENIED")
        finally:
            link.rmdir() if os.name == "nt" else link.unlink()

    def test_early_future_late_backfill_and_bad_raw(self):
        name, path = setup("future")
        with sqlite3.connect(path) as db:
            events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY seq")]
        f.append_day(events, DAYS[1])
        for event in events[-2:]:
            append(path, event)
        result = call(name, "once", at=stamp(DAYS[1], 16), code=3)
        self.assertEqual(result["reason"], "FUTURE_SOURCE_VERSION")
        name, path = setup("bad-raw")
        with sqlite3.connect(path) as db:
            event = json.loads(db.execute("SELECT payload FROM events WHERE seq=2").fetchone()[0])
            event["outcome"]["raw"][0]["body"][0] ^= 1
            # Rechain the synthetic fixture; original raw SHA validation must still reject.
            events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY seq")]
        events[2] = event
        f.save_journal(path, events)
        value = call(name, "once", at=stamp(DAYS[1], 16), code=3)
        self.assertEqual(value["reason"], "RAW_SHA_MISMATCH")
        self.assertFalse(call(name, "report", code=3)["authoritative_evidence_verified"])
        name, path = setup("late")
        with sqlite3.connect(path) as db:
            events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY seq")]
        f.append_day(events, DAYS[1], received_day=DAYS[2])
        for event in events[-2:]:
            append(path, event)
        with HttpFixture() as http:
            result = call(name, "once", at=stamp(DAYS[2], 17, 5), port=http.port, code=3)
            self.assertNotEqual(result["state"], "COMPLETE")
            self.assertNotIn("shadow", result["refs"])

    def test_readonly_absent_and_no_invocation_or_token_lookup(self):
        name, _ = setup("readonly")
        service = o.Operator(name)
        paths = [service.root, o.d.Store(name).root, o.s.Shadow(name).root]
        before = fingerprint(paths)
        with patch.object(o, "spawn", side_effect=AssertionError("dispatch")), \
             patch.object(o, "credential", side_effect=AssertionError("credential")), \
             patch.object(o.d.Store, "sync", side_effect=AssertionError("sync")), \
             patch.object(o.s.Shadow, "once", side_effect=AssertionError("shadow")), \
             patch.object(o.a.Auto, "once", side_effect=AssertionError("auto")):
            for command in ("status", "history", "verify", "report"):
                self.assertTrue(service.query(command)["authoritative_evidence_verified"])
        self.assertEqual(before, fingerprint(paths))
        # An initialized PR33 source with no Operator never creates Operator state on query.
        alias = name + "-new"
        path = WORK / alias / "forward.sqlite"
        path.parent.mkdir(parents=True)
        events = f.base_events()
        events[0]["config"]["observation_id"] = alias
        f.save_journal(path, events)
        o.d.Store(alias).sync(observer=path)
        absent = o.Operator(alias)
        self.assertFalse(absent.root.exists())
        call(alias, "status", code=2)
        self.assertFalse(absent.root.exists())
        process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/eod-operator.py"),
                                  "--snapshot-store", name, "once", "--clock", "0"], capture_output=True)
        self.assertEqual(process.returncode, 2)

    def test_early_observation_never_becomes_post_16_data(self):
        name, path = setup("early", auto=True)
        with sqlite3.connect(path) as db:
            events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY seq")]
        f.append_day(events, DAYS[1])
        started, finished = events[-2:]
        early = stamp(DAYS[1], 15, 15)
        started["observed_at"] = early
        finished["finished_at"] = finished["outcome"]["available_at"] = early
        for raw in finished["outcome"]["raw"]:
            raw["received_at"] = early
            raw["server_date"] = dt.datetime.fromtimestamp(early / 1000, dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        for event in (started, finished):
            append(path, event)
        with patch.object(o.d, "now", return_value=stamp(DAYS[1], 15, 16)):
            self.assertTrue(o.d.Store(name).sync()["can_research"])
        before = o.j.sha(path.read_bytes())
        with HttpFixture() as http:
            self.assertEqual(call(name, "once", at=stamp(DAYS[1], 15, 16), port=http.port)["state"], "WAITING_FOR_PUBLICATION")
            value = call(name, "once", at=stamp(DAYS[1], 16), port=http.port, code=3)
            self.assertEqual(value["reason"], "EARLY_SOURCE_UNVERIFIED")
            self.assertEqual(http.calls, [])
        self.assertEqual(before, o.j.sha(path.read_bytes()))
        self.assertEqual(af.counts(name)["calls"], 0)

    def test_source_revision_does_not_research_again_or_mix_success_refs(self):
        name, path = setup("revision", auto=True)
        with HttpFixture() as http:
            first = call(name, "once", at=stamp(DAYS[1], 17, 5), port=http.port)
            with sqlite3.connect(path) as db:
                events = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY seq")]
            f.append_day(events, DAYS[1], close="10.50")
            pair = events[-2:]
            delta = stamp(DAYS[1], 17, 6) - pair[0]["observed_at"]
            pair[0]["observed_at"] += delta
            pair[1]["finished_at"] += delta
            pair[1]["outcome"]["available_at"] += delta
            for raw in pair[1]["outcome"]["raw"]:
                raw["received_at"] += delta
                raw["server_date"] = dt.datetime.fromtimestamp(raw["received_at"] / 1000, dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
            for event in pair:
                append(path, event)
            changed = call(name, "once", at=stamp(DAYS[1], 17, 10), port=http.port, code=3)
            self.assertEqual(changed["state"], "PARTIAL")
            self.assertEqual(changed["reason"], "OPERATOR_CROSS_SOURCE_REFS")
            self.assertEqual(changed["refs"]["shadow"], first["refs"]["shadow"])
            self.assertEqual(changed["refs"]["fake"], first["refs"]["fake"])
            self.assertEqual(len(http.calls), 2)
            self.assertEqual(af.counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))

    @unittest.skipUnless(os.name == "nt", "Windows credential API")
    def test_native_windows_credential_roundtrip_synthetic_only(self):
        target = "Stratide/test/eod-operator-" + os.urandom(10).hex()
        value = "synthetic_test_NOT_A_REAL_TOKEN"
        try:
            o.credential(target, value)
            self.assertEqual(o.credential(target), value)
        finally:
            dll = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
            dll.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
            self.assertTrue(dll.CredDeleteW(target, 1, 0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-cli", type=Path)
    parser.add_argument("--fixture-stage", type=Path)
    parser.add_argument("--test", action="append")
    args = parser.parse_args()
    if args.fixture_cli:
        raise SystemExit(fixture_cli(o.j.loads(args.fixture_cli.read_bytes())))
    if args.fixture_stage:
        request = o.j.loads(args.fixture_stage.read_bytes())
        raise SystemExit(fixture_cli(request["request"], request["stage"]))
    WORK.mkdir(parents=True)
    af.test_exe()
    suite = (unittest.TestSuite(OperatorTests(name) for name in args.test) if args.test else
             unittest.defaultTestLoader.loadTestsFromTestCase(OperatorTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = dict(result="PASS" if result.wasSuccessful() else "FAIL", tests_run=result.testsRun,
                    failures=len(result.failures), errors=len(result.errors), checks=CHECKS,
                    verification="developer_selftest_not_independent_acceptance", data_mode="synthetic_test",
                    clock="test_only_dependency_injection_and_original_Rust_cfg_test",
                    collector="loopback_HTTP_schema1041_protocol_fixture_original_collector_unchanged",
                    collection_policy="16h_fallback_EARLY_SOURCE_UNVERIFIED_no_early_retry",
                    implementation_sha256={p: o.j.sha((ROOT / p).read_bytes()) for p in
                        ("research/eod_operator.py", "scripts/eod-operator.py", "scripts/test-eod-operator.py")},
                    public_market_requests=0, real_llm_calls=0, genuine_new_forward_days=0,
                    **o.SAFE)
    (WORK / "operator-evidence.json").write_bytes(o.j.canonical(evidence))
    (WORK / "operator-commands-local.json").write_bytes(o.j.canonical(COMMANDS))
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print("Local evidence: " + str(WORK))
    raise SystemExit(0 if result.wasSuccessful() else 1)
