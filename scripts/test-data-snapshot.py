"""Windows/offline snapshot E2E and focused provenance/recovery counterexamples.

All fault cases use isolated synthetic schema-1041 journals, never the observer.
Optional real run accepts explicit existing files and publishes only counts/hashes.
"""
import argparse
import copy
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import data_snapshot as data
import eod_journal as journal


def stamp(day):
    return int(dt.datetime.strptime(day + "170000", "%Y%m%d%H%M%S").replace(tzinfo=journal.ZONE).timestamp() * 1000)


def raw(api, rows, at):
    fields = list(rows[0])
    body = json.dumps(dict(code=0, data=dict(fields=fields, items=[list(r.values()) for r in rows])),
                      separators=(",", ":")).encode()
    return dict(api=api, http_status=200, sha256=journal.sha(body), received_at=at,
                server_date=dt.datetime.fromtimestamp(at / 1000, dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
                body=list(body))


def append_day(events, key, *, received_day=None, close="10.00", calendar_override=None):
    received_day = received_day or key
    at = stamp(received_day) + len(events) * 1000
    run = "synthetic-" + str(len(events))
    previous = [e["outcome"]["bar"] for e in events if e["event"] == "collection_finished" and e["outcome"]["bar"]]
    old = next((b for b in reversed(previous) if b["trade_day"] == key), None)
    from_day = min(key, journal.day(events[0]["started_at"]))
    first, last = journal.date(from_day), journal.date(received_day)
    cal = [dict(exchange="SSE", cal_date=(first + dt.timedelta(days=i)).strftime("%Y%m%d"),
                is_open=1) for i in range((last - first).days + 1)]
    if calendar_override:
        for row in cal:
            if row["cal_date"] in calendar_override:
                row["is_open"] = calendar_override[row["cal_date"]]
    daily = dict(ts_code="600000.SH", trade_date=key, open="10.00", high="12.00", low="9.00", close=close, vol="100")
    bar = dict(trade_day=key, open_fen=1000, high_fen=1200, low_fen=900, close_fen=journal.exact(close),
               volume_shares=10000, source_volume_unit="hand_100_shares", price_semantics="unadjusted_cny_fen")
    old_seq = next((i for i in range(len(events) - 1, 0, -1)
                    if events[i]["event"] == "collection_finished" and events[i]["outcome"]["bar"]
                    and events[i]["outcome"]["bar"]["trade_day"] == key), None)
    events.append(dict(event="collection_started", run_id=run, observed_at=at, trade_day=key,
                       calendar_from=from_day, calendar_through=received_day))
    events.append(dict(event="collection_finished", run_id=run, finished_at=at + 30,
                       outcome=dict(status="valid_eod", raw=[raw("trade_cal", cal, at + 10), raw("daily", [daily], at + 20)],
                                    calendar=[dict(day=r["cal_date"], is_open=bool(r["is_open"])) for r in cal],
                                    bar=bar, provider_published_at=None, available_at=at + 30,
                                    duplicate_of=old_seq if old == bar else None,
                                    revision_of=old_seq if old is not None and old != bar else None,
                                    late_backfill=key < received_day)))


def base_events():
    events = [dict(event="initialized", config=dict(observation_id="synthetic_test_m2_pr05", instrument="600000.SH",
                   strategy_version="synthetic_test", source="tushare_pro", license_note="synthetic_test_no_market_evidence",
                   local_automation_and_raw_storage_authorized=True),
                   started_at=stamp("20261026") - 1000, version=journal.VERSION, host="synthetic_test")]
    append_day(events, "20261026")
    append_day(events, "20261027")
    return events


def chained(events):
    rows, previous = [], ""
    for n, event in enumerate(events):
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        digest = journal.sha(json.dumps([1, "forward_observation", previous, n, payload],
                                        ensure_ascii=False, separators=(",", ":")).encode())
        rows.append((n, payload, digest))
        previous = digest
    return rows


def save_journal(path, events):
    rows = chained(events)
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA user_version=1041")
        db.execute("CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,payload TEXT,digest TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY,seq INTEGER,digest TEXT)")
        db.execute("DELETE FROM events")
        db.execute("DELETE FROM checkpoint")
        db.executemany("INSERT INTO events VALUES(?,?,?)", rows)
        db.execute("INSERT INTO checkpoint VALUES(1,?,?)", rows[-1][::2])
        db.commit()


def cli(name, command, *args):
    result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/research-data.py"),
                             "--store", name, command, *map(str, args)], capture_output=True, timeout=30)
    return result.returncode, json.loads(result.stdout)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.name = "test-" + os.urandom(6).hex()
        self.store = data.Store(self.name)
        self.work = ROOT / "state/data-sync-tests" / self.name
        self.work.mkdir(parents=True)
        self.source = self.work / "forward.sqlite"
        self.events = base_events()
        save_journal(self.source, self.events)

    def tearDown(self):
        # Only this test's two newly allocated names; no original evidence.
        for path, parent in ((self.work, ROOT / "state/data-sync-tests"), (self.store.root, ROOT / "state/data-sync")):
            self.assertEqual(path.resolve().parent, parent.resolve())
            if path.exists():
                shutil.rmtree(path)

    def sync(self):
        return self.store.sync(self.source)

    def test_fixed_fixture_cli_retry_restart_and_readonly_consumer(self):
        code, first = cli(self.name, "sync", "--fixture")
        self.assertEqual(code, 0)
        self.assertEqual(first["snapshot"]["valid_eod_days"], 2)
        self.assertEqual(first["snapshot"]["data_mode"], "synthetic_test")
        for command in ("sync", "snapshot", "status"):
            code, repeated = cli(self.name, command)
            self.assertEqual(code, 0)
            self.assertEqual(repeated["snapshot"], first["snapshot"])
        code, consumed = cli(self.name, "consume")
        self.assertEqual(code, 0)
        self.assertEqual(consumed["source_day"], "2026-10-27")
        self.assertFalse(consumed["eod_eligible"])
        self.assertFalse(consumed["can_execute_forward_paper"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 1)

    def test_new_day_duplicate_revision_and_late_backfill_keep_real_times(self):
        first = self.sync()
        append_day(self.events, "20261028")
        save_journal(self.source, self.events)
        fresh = self.sync()
        self.assertTrue(fresh["latest_attempt"]["new_append"])
        self.assertNotEqual(first["snapshot"]["snapshot_sha256"], fresh["snapshot"]["snapshot_sha256"])
        self.assertEqual(fresh["snapshot"]["last_valid_source_day"], "20261028")
        append_day(self.events, "20261028")
        save_journal(self.source, self.events)
        self.assertEqual(self.sync()["snapshot"]["on_day_valid_eod_days"], 3)
        append_day(self.events, "20261027", received_day="20261029", close="11.00")
        save_journal(self.source, self.events)
        revised = self.sync()
        self.assertEqual(revised["snapshot"]["last_valid_source_day"], "20261028")
        self.assertIn("REVISED_EOD", revised["snapshot"]["warnings"])
        self.assertIn("LATE_BACKFILL", revised["snapshot"]["warnings"])
        self.assertEqual(revised["snapshot"]["gaps"], [dict(source_day="20261029", state="missing_valid_eod")])
        saved, _ = self.store.read_snapshot()
        bar = next(r for r in saved["content"]["bars"] if r["bar"]["trade_day"] == "20261027")
        self.assertGreater(bar["available_at"], stamp("20261029"))

    def test_backfill_never_repairs_missed_forward_day(self):
        events = base_events()[:1]
        append_day(events, "20261026", received_day="20261027")
        save_journal(self.source, events)
        result = self.sync()
        self.assertTrue(result["can_research"])
        self.assertEqual(result["snapshot"]["on_day_valid_eod_days"], 0)
        self.assertEqual(len(result["snapshot"]["gaps"]), 2)

    def test_conflict_unknown_calendar_clock_fault_and_pending_retain_snapshot(self):
        first = self.sync()["snapshot"]
        cases = {}
        conflict = copy.deepcopy(self.events)
        append_day(conflict, "20261028", calendar_override={"20261026": 0})
        cases["CALENDAR_CONFLICT"] = conflict
        pending = copy.deepcopy(self.events)
        pending.append(dict(event="collection_started", run_id="unfinished", observed_at=stamp("20261028"),
                            trade_day="20261028", calendar_from="20261028", calendar_through="20261028"))
        cases["PENDING_COLLECTION"] = pending
        unknown = copy.deepcopy(pending)
        unknown.append(dict(event="interrupted", run_id="unfinished", detected_at=stamp("20261028") + 10))
        cases["CALENDAR_UNKNOWN"] = unknown
        clock = copy.deepcopy(self.events)
        clock.append(dict(event="clock_fault", detected_at=stamp("20261026"), previous_high_water=stamp("20261027"), reason="wall_clock_regressed"))
        cases["SOURCE_CLOCK_FAULT"] = clock
        for blocker, events in cases.items():
            with self.subTest(blocker=blocker):
                save_journal(self.source, events)
                result = self.sync()
                self.assertEqual(result["snapshot"], first)
                self.assertIn(blocker, result["latest_attempt"]["blockers"])
                self.assertFalse(result["can_research"])

    def test_corruption_raw_hash_and_database_fail_closed(self):
        first = self.sync()["snapshot"]
        missing_calendar = copy.deepcopy(self.events)
        append_day(missing_calendar, "20261027")
        missing_calendar[-1]["outcome"]["calendar"] = []
        save_journal(self.source, missing_calendar)
        self.assertEqual(self.sync()["latest_attempt"]["error_code"], "EOD_TIME_OR_CALENDAR")
        bad = copy.deepcopy(self.events)
        bad[-1]["outcome"]["raw"][-1]["body"][0] ^= 1
        save_journal(self.source, bad)
        self.assertEqual(self.sync()["latest_attempt"]["error_code"], "RAW_SHA_MISMATCH")
        self.source.write_bytes(b"synthetic corrupted SQLite")
        result = self.sync()
        self.assertEqual(result["latest_attempt"]["error_code"], "SOURCE_DATABASE_ERROR")
        self.assertEqual(result["snapshot"], first)

    def test_rollback_rewrite_and_source_switch_rejected(self):
        self.sync()
        save_journal(self.source, self.events[:3])
        self.assertEqual(self.sync()["latest_attempt"]["error_code"], "SOURCE_REWRITE_OR_ROLLBACK")
        other = self.work / "other.sqlite"
        save_journal(other, self.events)
        self.assertEqual(self.store.sync(other)["latest_attempt"]["error_code"], "SOURCE_BINDING_CHANGED")

    def test_consumer_hash_and_synthetic_relabel_rejected_even_with_new_hash(self):
        self.sync()
        with self.store.connect(write=True) as db:
            key, payload, at = db.execute("SELECT sha,content,verified_at FROM snapshots").fetchone()
            content = journal.loads(payload)
            content["last_valid_source_day"] = "20990101"
            db.execute("UPDATE snapshots SET content=? WHERE sha=?", (journal.canonical(content).decode(), key))
        with self.assertRaisesRegex(journal.Rejected, "SNAPSHOT_HASH_MISMATCH"):
            self.store.consume()
        content["last_valid_source_day"] = "20261027"
        content["schema_version"] = 2
        new_key = journal.sha(journal.canonical(content))
        with self.store.connect(write=True) as db:
            db.execute("UPDATE snapshots SET content=?,sha=?", (journal.canonical(content).decode(), new_key))
            db.execute("UPDATE control SET current_sha=?", (new_key,))
        with self.assertRaisesRegex(journal.Rejected, "SNAPSHOT_CONTRACT"):
            self.store.consume()
        content["schema_version"] = 1
        content["data_mode"] = "forward_observed_eod"
        new_key = journal.sha(journal.canonical(content))
        with self.store.connect(write=True) as db:
            db.execute("UPDATE snapshots SET content=?,sha=?", (journal.canonical(content).decode(), new_key))
            db.execute("UPDATE control SET current_sha=?", (new_key,))
        with self.assertRaisesRegex(journal.Rejected, "SNAPSHOT_SOURCE_BINDING"):
            self.store.consume()

    def test_original_bytes_and_directory_preserved_and_wal_not_copied(self):
        before = {p.name: journal.sha(p.read_bytes()) for p in self.work.iterdir()}
        self.sync()
        self.store.consume()
        self.assertEqual(before, {p.name: journal.sha(p.read_bytes()) for p in self.work.iterdir()})
        wal = Path(str(self.source) + "-wal")
        wal.write_bytes(b"synthetic test marker")
        result = self.sync()
        self.assertEqual(result["latest_attempt"]["error_code"], "SOURCE_BUSY_OR_WAL_UNSUPPORTED")
        self.assertEqual(wal.read_bytes(), b"synthetic test marker")

    def test_offline_calls_have_no_network_process_or_trading_authority(self):
        with patch("socket.create_connection", side_effect=AssertionError("unexpected network")), \
             patch("subprocess.Popen", side_effect=AssertionError("unexpected child")):
            self.sync()
            result = self.store.consume()
        self.assertTrue(result["can_research"])
        self.assertFalse(result["live_allowed"])
        self.assertNotIn("budget", result)

    def test_concurrent_source_append_and_local_clock_regression_keep_previous_asof(self):
        old = self.sync()["snapshot"]
        original = journal.verify_rows

        def appending(rows):
            content = original(rows)
            append_day(self.events, "20261028")
            save_journal(self.source, self.events)
            return content

        with patch.object(journal, "verify_rows", side_effect=appending):
            changed = self.sync()
        self.assertEqual(changed["latest_attempt"]["error_code"], "SOURCE_CHANGED_DURING_READ")
        self.assertEqual(changed["snapshot"], old)
        at = data.now()
        with patch.object(data, "now", side_effect=[at, at - 1, at - 1, at, at]):
            regressed = self.sync()
        self.assertEqual(regressed["latest_attempt"]["error_code"], "SYNC_CLOCK_REGRESSED")
        self.assertEqual(regressed["snapshot"], old)

    def test_process_kill_unpublished_transaction_and_concurrent_writer(self):
        old = self.sync()["snapshot"]
        append_day(self.events, "20261028")
        save_journal(self.source, self.events)
        marker = self.work / "before-publish"
        runner = self.work / "pause.py"
        runner.write_text("import sys,time\nfrom pathlib import Path\nsys.path.insert(0," + repr(str(ROOT / "research")) + ")\n"
                          "import data_snapshot as d\n"
                          "original=d.Store._publish\n"
                          "def pause(self,db,binding,content,at):\n"
                          " original(self,db,binding,content,at)\n"
                          " Path(" + repr(str(marker)) + ").write_text('staged_uncommitted')\n"
                          " time.sleep(30)\n"
                          "d.Store._publish=pause\n"
                          "d.Store(" + repr(self.name) + ").sync(" + repr(str(self.source)) + ")\n", encoding="utf-8")
        child = subprocess.Popen([sys.executable, "-I", "-B", str(runner)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "test child never reached uncommitted publication")
            code, busy = cli(self.name, "sync")
            self.assertEqual(code, 2)
            self.assertEqual(busy["error_code"], "STORE_BUSY")
            self.assertEqual(self.store.status()["snapshot"], old)
            child.kill()
            child.communicate(timeout=10)
            state = self.store.status()
            self.assertEqual(state["snapshot"], old)
            self.assertEqual(state["latest_attempt"]["state"], "running")
            self.assertFalse(state["can_research"])
            recovered = self.store.sync()
            self.assertEqual(recovered["snapshot"]["last_valid_source_day"], "20261028")
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)


def real_offline(observer, protected):
    paths = [Path(observer).resolve(), *(Path(p).resolve() for p in protected)]
    for p in paths:
        journal.no_links(p)
        journal.require(not any(Path(str(p) + s).exists() for s in ("-wal", "-shm", "-journal")), "PROTECTION_BASELINE_BUSY")
    before = [journal.sha(p.read_bytes()) for p in paths]
    name = "real-eod-selftest-" + os.urandom(6).hex()
    code, first = cli(name, "sync", "--observer", paths[0])
    journal.require(code == 0, "REAL_SYNC_FAILED")
    code, repeated = cli(name, "sync")
    journal.require(code == 0 and repeated["snapshot"] == first["snapshot"], "REAL_REPEAT_MISMATCH")
    code, consumer = cli(name, "consume")
    journal.require(code == 0 and consumer["data_mode"] == "forward_observed_eod", "REAL_CONSUMER_FAILED")
    after = [journal.sha(p.read_bytes()) for p in paths]
    for p in paths:
        journal.require(not any(Path(str(p) + s).exists() for s in ("-wal", "-shm", "-journal")), "PROTECTION_FINISH_BUSY")
    journal.require(before == after, "PROTECTED_FILES_CHANGED_OR_CONCURRENTLY_WRITTEN")
    return dict(result="PASS", store=name, snapshot=first["snapshot"], consumer=consumer,
                protected_files=len(paths), before_manifest_sha256=journal.sha(journal.canonical(before)),
                after_manifest_sha256=journal.sha(journal.canonical(after)), original_bytes_unchanged=True,
                network_calls=0, provider_calls=0, new_forward_events=0,
                verification="developer_selftest_not_independent_acceptance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--observer", type=Path)
    parser.add_argument("--protect", type=Path, action="append", default=[])
    args, remaining = parser.parse_known_args()
    if args.observer:
        print(json.dumps(real_offline(args.observer, args.protect), ensure_ascii=False, indent=2))
    else:
        unittest.main(argv=[sys.argv[0], *remaining])
