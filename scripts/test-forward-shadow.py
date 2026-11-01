"""Real subprocess CLI E2E and failure evidence; synthetic clocks only here.

Reuses PR33's schema-1041 synthetic journal and real sync CLI. No market calls.
Retains all newly allocated fixtures, commands and frozen local input for review.
"""
import argparse
import copy
import datetime as dt
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import shadow as s

spec = importlib.util.spec_from_file_location("snapshot_fixtures", ROOT / "scripts/test-data-snapshot.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
RUN = "shadow-test-" + os.urandom(5).hex()
WORK = ROOT / "state/forward-shadow-tests" / RUN
COMMANDS, CHECKS = [], []
DAYS = [(dt.date(2026, 8, 1) + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(23)]


def at(day):
    return f.stamp(day) + 3600000


def fixture_cli(request):
    assert request["store"].startswith("shadow-test-")
    def fault(point):
        if point == request.get("fault"):
            os._exit(86)
        if point == request.get("pause"):
            Path(request["marker"]).write_text(point)
            while not Path(request["release"]).exists():
                time.sleep(0.02)
    def wait(_):
        raise KeyboardInterrupt  # one real foreground watch tick, then Ctrl+C
    ticks = iter(request.get("clock_ticks", []))
    def clock():
        return next(ticks, request["at"])
    with patch.object(s.d, "now", return_value=request["at"]), \
         patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
        if request.get("sync"):
            sys.argv = ["research-data.py", "--store", request["store"], *request["args"]]
            return s.d.main()
        return s.main(["--store", request["store"], *request["args"]], clock=clock, fault=fault, wait=wait)


def launch(name, *args, when=None, sync=False, fault=None, pause=None, cwd=ROOT, clock_ticks=None):
    WORK.mkdir(parents=True, exist_ok=True)
    request = WORK / ("request-" + os.urandom(5).hex() + ".json")
    marker, release = request.with_suffix(".marker"), request.with_suffix(".release")
    data = dict(store=name, args=list(map(str, args)), at=when or at(DAYS[20]), sync=sync,
                fault=fault, pause=pause, marker=str(marker), release=str(release), clock_ticks=clock_ticks or [])
    request.write_bytes(s.j.canonical(data))
    process = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).absolute()), "--fixture-cli", str(request)],
                               cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.shadow_request = data
    return process


def collect(process, expected=None):
    out, err = process.communicate(timeout=45)
    request = process.shadow_request
    value = json.loads(out) if out else None
    COMMANDS.append(dict(command=["research-data.py" if request["sync"] else "forward-shadow.py",
                                  "--store", request["store"], *request["args"]], clock=request["at"],
                         fault=request["fault"], exit_code=process.returncode, result=value))
    if expected is not None and process.returncode != expected:
        raise AssertionError(f"{request['args']}: expected {expected}, got {process.returncode}: {out[:2500]!r} {err[:1000]!r}")
    return process.returncode, value


def call(name, *args, code=0, **kwargs):
    return collect(launch(name, *args, **kwargs), code)[1]


def setup(label, count=21, enabled=True, edit=None):
    name = "shadow-test-" + label + "-" + os.urandom(5).hex()
    directory = WORK / name
    directory.mkdir(parents=True)
    path = directory / "forward.sqlite"
    events = f.base_events()[:1]
    events[0]["config"]["observation_id"] = name
    events[0]["started_at"] = f.stamp(DAYS[0]) - 1000
    for i in range(count):
        f.append_day(events, DAYS[i], close="11.00" if i == 20 else "9.00" if i == 21 else "10.00")
    if edit:
        edit(events)
    f.save_journal(path, events)
    when = at(DAYS[count - 1])
    call(name, "sync", "--observer", path, sync=True, when=when)
    call(name, "init", when=when)
    if enabled:
        call(name, "enable", when=when)
    return name, path, events


def manifest(paths):
    result = {}
    for base in paths:
        if base.is_file():
            result[str(base)] = s.j.sha(base.read_bytes())
        elif base.exists():
            for path in base.rglob("*"):
                if path.is_file():
                    result[str(path)] = s.j.sha(path.read_bytes())
    return result


class ShadowTests(unittest.TestCase):
    def test_full_22_day_two_directory_cli_decimal_and_watch(self):
        normalized = []
        for label in ("full-a", "full-b"):
            name, path, events = setup(label, count=1, enabled=False)
            self.assertEqual(call(name, "once", when=at(DAYS[0]), code=3)["reason"], "OWNER_DISABLED")
            call(name, "enable", when=at(DAYS[0]))
            outcomes = []
            for i in range(22):
                if i:
                    f.append_day(events, DAYS[i], close="11.00" if i == 20 else "9.00" if i == 21 else "10.00")
                    f.save_journal(path, events)
                    call(name, "sync", sync=True, when=at(DAYS[i]))
                value = call(name, "once", when=at(DAYS[i]))
                outcomes.append((value["observation"]["result"], value["observation"]["readiness"]["continuous_on_day_count"]))
            self.assertEqual(outcomes[:20], [("INSUFFICIENT_FORWARD_WARMUP", i) for i in range(1, 21)])
            self.assertEqual(outcomes[-2:], [("UP_CROSS", 21), ("DOWN_CROSS", 22)])
            service = s.Shadow(name)
            with s.readonly(service.path) as db:
                journal = service.journal(db)
            for record in journal["observations"]:
                material = record["material"]
                closes = [Decimal(v["bar"]["close_fen"]) for v in material["window"]]
                self.assertEqual(s.j.day(material["decision_at"]), material["source_day"])
                self.assertGreater(material["decision_at"], material["as_of"])
                if len(closes) == 21:
                    before = sum(closes[:20][-5:]) / 5 > sum(closes[:20]) / 20
                    after = sum(closes[-5:]) / 5 > sum(closes[-20:]) / 20
                    self.assertEqual(material["calculation"]["result"], "NO_CROSS" if before == after else "UP_CROSS" if after else "DOWN_CROSS")
            protected = [service.root, path, s.d.Store(name).root]
            before = manifest(protected)
            for action in ("status", "history", "verify", "report"):
                result = call(name, action, when=at(DAYS[21]))
                self.assertEqual(result["observation_count"], 22)
                self.assertEqual(result["signal_count"], 2)
                self.assertTrue(result["source_verified"])
                self.assertEqual(result["orders"], 0)
                self.assertEqual(result["fills"], 0)
                self.assertIsNone(result["nav"])
            self.assertEqual(before, manifest(protected))
            watch = call(name, "watch", "--interval-seconds", 60, when=at(DAYS[21]), code=130)
            self.assertEqual(watch["state"], "ALREADY_FROZEN")
            self.assertEqual(call(name, "status", when=at(DAYS[21]))["observation_count"], 22)
            normalized.append(outcomes)
        self.assertEqual(*normalized)
        CHECKS.append(dict(check="22_day_two_directory_e2e", normalized_outcomes=normalized[0],
                           readonly_bytes_unchanged=True, independent_decimal=True, real_forward_days_added=0))

    def test_time_missed_stale_before_16_future_and_no_warmup(self):
        early_name, _, _ = setup("early", count=20)
        name, _, _ = setup("time")
        early = at(DAYS[20]) - 3 * 3600000
        value = call(early_name, "once", when=early, code=3)
        self.assertEqual(value["reason"], "BEFORE_EOD_WINDOW")
        service = s.Shadow(name, clock=lambda: early)
        ready, _ = s.readiness(service.src, early)
        self.assertIn("BEFORE_EOD_WINDOW", ready["blockers"])
        self.assertIn("FUTURE_SOURCE_VERSION", ready["blockers"])
        regressed = call(name, "once", clock_ticks=[at(DAYS[20]), at(DAYS[20]),
            at(DAYS[20]) - 1, at(DAYS[20]) - 1], code=2)
        self.assertEqual(regressed["reason"], "SHADOW_CLOCK_REGRESSED")
        self.assertEqual(call(name, "status")["signal_count"], 0)
        # A normal next writer recovers the pending attempt instead of inheriting
        # a timestamp regression in the committed append-only chain.
        self.assertEqual(call(name, "once")["state"], "COMMITTED")
        missed_name, _, _ = setup("missed")
        for offset in (24 * 3600000, 25 * 3600000):
            blocked = call(missed_name, "once", when=at(DAYS[20]) + offset, code=3)
            self.assertEqual(blocked["reason"], "MISSED_OR_STALE")
        status = call(missed_name, "status", when=at(DAYS[22]))
        self.assertEqual(status["signal_count"], 0)
        self.assertIn("SNAPSHOT_SYNC_STALE_OR_CLOCK", status["source_diagnostics"]["blockers"])
        small, _, _ = setup("small", count=2)
        warmup = call(small, "once", when=at(DAYS[1]))
        self.assertEqual(warmup["observation"]["result"], "INSUFFICIENT_FORWARD_WARMUP")
        self.assertEqual(warmup["observation"]["mode"], "SYNTHETIC_TEST_SHADOW")
        CHECKS.append(dict(check="time_gates", reasons=status["source_diagnostics"]["blockers"],
                           warmup_result=warmup["observation"]["result"]))

    def test_revision_future_append_and_unsynced_source_preserve_frozen(self):
        name, path, events = setup("revision")
        first = call(name, "once")["observation"]
        f.append_day(events, DAYS[20], close="9.00")
        f.save_journal(path, events)
        self.assertEqual(call(name, "once", code=3)["reason"], "SOURCE_CHANGED_SINCE_SYNC")
        call(name, "sync", sync=True)
        repeated = call(name, "once")
        self.assertEqual(repeated["observation"], first)
        f.append_day(events, DAYS[21], close="9.00")
        f.save_journal(path, events)
        call(name, "sync", sync=True, when=at(DAYS[21]))
        # Future T+1 source is not usable as T's decision; query does not rewrite T.
        self.assertEqual(call(name, "once", code=3)["reason"], "MISSED_OR_STALE")
        report = call(name, "report", when=at(DAYS[21]))
        self.assertEqual(report["observations"][0]["local_input_commitment_sha256"], first["local_input_commitment_sha256"])
        self.assertEqual(report["signal_count"], 1)
        CHECKS.append(dict(check="revision_and_future_freeze", frozen_commitment=first["local_input_commitment_sha256"],
                           current_source_changed=True, signal_count=report["signal_count"]))

    def test_known_gap_late_backfill_unknown_conflict_units_sha_mode(self):
        def remove_day(events):
            del events[1 + 2 * 10:1 + 2 * 11]
        name, _, _ = setup("gap", edit=remove_day)
        # The raw calendar still declares this day open. No weekday assumptions.
        self.assertEqual(call(name, "once", code=3)["reason"], "FORWARD_COVERAGE_GAP")
        CHECKS.append(dict(check="known_open_gap", reason="FORWARD_COVERAGE_GAP", signals=0))
        def backfill_gap(events):
            fixed = events[:1]
            for i in range(21):
                if i != 10:
                    f.append_day(fixed, DAYS[i])
                if i == 11:
                    f.append_day(fixed, DAYS[10], received_day=DAYS[11])
            events[:] = fixed
        late_gap, _, _ = setup("backfill-gap", edit=backfill_gap)
        self.assertEqual(call(late_gap, "once", code=3)["reason"], "FORWARD_COVERAGE_GAP")
        self.assertLess(call(late_gap, "status")["source_diagnostics"]["continuous_on_day_count"], 21)
        # Use a separate binding for each invalid source to preserve PR33 append-only guarantees.
        late_name, late_path, late = setup("late", count=1)
        f.append_day(late, DAYS[1], received_day=DAYS[2])
        f.save_journal(late_path, late)
        call(late_name, "sync", sync=True, when=at(DAYS[2]))
        self.assertEqual(call(late_name, "once", when=at(DAYS[2]), code=3)["reason"], "MISSED_OR_STALE")
        for label in ("unknown", "conflict", "units", "sha", "mode", "instrument"):
            n, p, ev = setup(label, count=2)
            if label == "unknown":
                ev.append(dict(event="collection_started", run_id="unknown", observed_at=f.stamp(DAYS[2]),
                    trade_day=DAYS[2], calendar_from=DAYS[2], calendar_through=DAYS[2]))
                ev.append(dict(event="interrupted", run_id="unknown", detected_at=f.stamp(DAYS[2]) + 10))
            elif label == "conflict":
                f.append_day(ev, DAYS[2], calendar_override={DAYS[0]: 0})
            elif label == "units":
                ev[-1]["outcome"]["bar"]["price_semantics"] = "adjusted_yuan"
            elif label == "sha":
                ev[-1]["outcome"]["raw"][-1]["body"][0] ^= 1
            elif label == "mode":
                ev[0]["host"] = "not_synthetic"
            else:
                ev[0]["config"]["instrument"] = "600001.SH"
            f.save_journal(p, ev)
            call(n, "sync", sync=True, when=at(DAYS[2]), code=2)
            value = call(n, "once", when=at(DAYS[2]), code=3)
            expected = {"units": "RAW_BAR_MISMATCH", "sha": "RAW_SHA_MISMATCH", "instrument": "RAW_BAR_IDENTITY"}
            self.assertEqual(value["reason"], expected.get(label, "SOURCE_CHANGED_SINCE_SYNC"))
            CHECKS.append(dict(check=label, reason=value["reason"]))

    def test_concurrent_alias_watch_disable_restart_and_cwd(self):
        name, path, _ = setup("parallel")
        alias = "shadow-test-alias-" + os.urandom(5).hex()
        copied_source = WORK / (alias + ".sqlite")
        copied_source.write_bytes(path.read_bytes())
        call(alias, "sync", "--observer", copied_source, sync=True)
        self.assertEqual(call(alias, "init", code=2)["reason"], "SHADOW_ALREADY_INITIALIZED")
        self.assertEqual(s.Shadow(name).path, s.Shadow(alias).path)
        processes = [launch(name, "once"), launch(alias, "watch", "--interval-seconds", 60)]
        results = [collect(p) for p in processes]
        self.assertIn(results[0][0], (0, 2))
        self.assertEqual(results[1][0], 130)
        count = call(name, "status")["signal_count"]
        if not count:
            call(name, "once")
        self.assertEqual(call(alias, "status")["signal_count"], 1)
        call(alias, "disable")
        self.assertEqual(call(name, "once", code=3)["reason"], "OWNER_DISABLED")
        call(name, "enable")
        self.assertEqual(call(alias, "once", cwd=WORK)["state"], "ALREADY_FROZEN")
        self.assertEqual(call(name, "status")["signal_count"], 1)
        CHECKS.append(dict(check="concurrency_alias_restart_cwd", copied_source_same_identity=True,
                           process_exits=[v[0] for v in results], signal_count=1))

    def test_snapshot_sha_and_historical_modes_cannot_enter_shadow(self):
        for label in ("hash", "historical_replay", "EXPLORATORY_EX_POST"):
            name, path, _ = setup("snapshot-" + label.lower().replace("_", "-"))
            service, store = s.Shadow(name), s.d.Store(name)
            before = manifest([path, service.root])
            with store.connect(write=True) as db:
                binding, saved, attempt = store.current(db)
                value = saved["content"]
                value["data_mode"] = label
                encoded = s.j.canonical(value).decode()
                if label == "hash":
                    db.execute("UPDATE snapshots SET content=? WHERE sha=?", (encoded, saved["snapshot_sha256"]))
                else:
                    # Even rehashing an ex-post snapshot and relabeling its outer
                    # binding does not make it a supported forward source.
                    key = s.j.sha(s.j.canonical(value))
                    binding["data_mode"] = label
                    db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, encoded, saved["verified_at"]))
                    db.execute("UPDATE control SET current_sha=?,binding=?", (key, s.j.canonical(binding).decode()))
            value = call(name, "once", code=2)
            self.assertEqual(value["reason"], "SNAPSHOT_HASH_MISMATCH" if label == "hash" else "SHADOW_SOURCE_MODE")
            self.assertEqual(before, manifest([path, service.root]))
            CHECKS.append(dict(check="snapshot_tamper", mode=label, reason=value["reason"], committed_signals=0))

    def test_three_actual_process_interruptions_and_rollback_recovery(self):
        for point in ("before_intent", "before_persist", "after_persist"):
            name, _, _ = setup("kill-" + point.replace("_", "-"))
            call(name, "once", fault=point, code=86)
            service = s.Shadow(name)
            before = manifest([service.root])
            if point == "before_persist":
                self.assertEqual(call(name, "verify", code=2)["reason"], "STORE_BUSY_OR_RECOVERY_REQUIRED")
            else:
                state = call(name, "status")
                self.assertEqual(state["signal_count"], 1 if point == "after_persist" else 0)
                self.assertEqual(before, manifest([service.root]))
            resumed = call(name, "once")
            self.assertEqual(resumed["state"], "ALREADY_FROZEN" if point == "after_persist" else "COMMITTED")
            report = call(name, "report")
            self.assertEqual(report["signal_count"], 1)
            self.assertFalse(report["interrupted_or_pending_runs"])
            if point != "after_persist":
                self.assertTrue(any(e["kind"] == "interrupted" for e in report["diagnostics"]))
            CHECKS.append(dict(check="actual_process_interrupt", point=point, exit_code=86, committed_signals=1))

    def test_os_lock_and_disable_fences_next_day(self):
        name, path, events = setup("lock")
        process = launch(name, "once", pause="before_intent")
        marker, release = Path(process.shadow_request["marker"]), Path(process.shadow_request["release"])
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        try:
            self.assertTrue(marker.exists())
            self.assertEqual(call(name, "once", code=2)["reason"], "STORE_BUSY")
            self.assertEqual(call(name, "disable", code=2)["reason"], "STORE_BUSY")
        finally:
            release.touch()
            collect(process, 0)
        call(name, "disable")
        f.append_day(events, DAYS[21], close="9.00")
        f.save_journal(path, events)
        call(name, "sync", sync=True, when=at(DAYS[21]))
        self.assertEqual(call(name, "once", when=at(DAYS[21]), code=3)["reason"], "OWNER_DISABLED")
        self.assertEqual(call(name, "status", when=at(DAYS[21]))["signal_count"], 1)
        CHECKS.append(dict(check="writer_lock_disable", signal_count=1, next_day_disabled=True))

    def test_queries_absent_store_and_no_strategy_sync_network_or_writes(self):
        name, path, _ = setup("readonly")
        call(name, "once")
        service = s.Shadow(name)
        before = manifest([service.root, s.d.Store(name).root, path])
        with patch.object(s, "calculate", side_effect=AssertionError("query runs strategy")), \
             patch.object(s.d.Store, "sync", side_effect=AssertionError("query syncs")), \
             patch.object(s.d, "writer", side_effect=AssertionError("query locks")), \
             patch("socket.create_connection", side_effect=AssertionError("query network")):
            for command in ("status", "history", "verify", "report"):
                self.assertTrue(service.query(command)["source_verified"])
        self.assertEqual(before, manifest([service.root, s.d.Store(name).root, path]))
        missing = "shadow-test-missing-" + os.urandom(5).hex()
        call(missing, "status", code=2)
        self.assertFalse(s.d.Store(missing).root.exists())
        # A source with no shadow init is also queried without creating state.
        new = "shadow-test-uninitialized-" + os.urandom(5).hex()
        call(new, "sync", "--observer", path, sync=True)
        # Existing source identity intentionally resolves to the same canonical journal.
        self.assertEqual(s.Shadow(new).path, service.path)
        fresh = "shadow-test-no-init-" + os.urandom(5).hex()
        events = f.base_events()
        events[0]["config"]["observation_id"] = fresh
        fresh_path = WORK / (fresh + ".sqlite")
        f.save_journal(fresh_path, events)
        call(fresh, "sync", "--observer", fresh_path, sync=True, when=at("20261027"))
        no_init = s.Shadow(fresh)
        self.assertFalse(no_init.root.exists())
        snapshot_before = manifest([s.d.Store(fresh).root, fresh_path])
        for action in ("status", "history", "verify", "report"):
            self.assertEqual(call(fresh, action, when=at("20261027"), code=2)["reason"], "STORE_NOT_INITIALIZED")
        self.assertFalse(no_init.root.exists())
        self.assertEqual(snapshot_before, manifest([s.d.Store(fresh).root, fresh_path]))
        CHECKS.append(dict(check="strict_readonly", byte_manifest_equal=True, absent_store_not_created=True))


def preservation(root, baseline):
    """Hash existing state/reports/code without reading credential files."""
    found = subprocess.run(["rg", "--files", "--hidden", "--no-ignore", "-g", "!**/target/**",
        "-g", "!**/node_modules/**", "-g", "!**/.git/**", "-g", "!issue47-worktree/**"],
        cwd=root, capture_output=True, check=True).stdout.decode().splitlines()
    values = {}
    for item in found:
        path = root / item
        parts = Path(item).parts
        if ("state" in parts or "audit-output" in parts or "evidence" in parts
                or path.suffix in (".sqlite", ".db", ".csv") or item == ".gitignore"):
            if "forward-shadow" in parts:
                continue  # this module's new canonical state
            if any(word in path.name.lower() for word in ("token", "secret", "settings", ".env")):
                continue
            values[item] = s.j.sha(path.read_bytes())
    if baseline.exists():
        previous = json.loads(baseline.read_bytes())
        changed = [p for p, digest in previous.items() if values.get(p) != digest]
        assert not changed, "protected original files changed: " + repr(changed[:5])
        return dict(protected_files=len(previous), before_manifest_sha256=s.j.sha(s.j.canonical(previous)),
                    after_manifest_sha256=s.j.sha(s.j.canonical({p: values[p] for p in previous})), original_bytes_unchanged=True)
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_bytes(s.j.canonical(values))
    return dict(protected_files=len(values), captured=True)


def real_boundary(observer, old_snapshot):
    protected = [observer, *s.sidecars(observer)]
    if old_snapshot:
        protected.extend([old_snapshot, *s.sidecars(old_snapshot)])
    before = manifest(protected)
    content, database_sha = s.j.read_observer(observer)
    assert content["data_mode"] == "forward_observed_eod"
    old_count = None
    if old_snapshot:
        with s.readonly(old_snapshot) as db:
            _, old, _ = s.d.Store("unused").current(db)
        old_count = old["content"]["on_day_valid_eod_days"]
        assert old_count == 2
    name = "shadow-test-real-" + os.urandom(5).hex()
    records = []
    def cli(script, *args, expected=0):
        process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts" / script),
                                  "--store", name, *map(str, args)], capture_output=True, timeout=30)
        assert process.returncode == expected, (process.stdout[:1000], process.stderr[:1000])
        value = json.loads(process.stdout)
        records.append(dict(command=[script, "--store", name, *map(str, args)], exit_code=process.returncode, result=value))
        return value
    cli("research-data.py", "sync", "--observer", observer)
    service = s.Shadow(name)
    if not service.path.exists():
        cli("forward-shadow.py", "init")
    cli("forward-shadow.py", "enable")
    once = cli("forward-shadow.py", "once", expected=3)
    assert once["reason"] == "MISSED_OR_STALE"
    for action in ("status", "history", "verify", "report"):
        value = cli("forward-shadow.py", action)
        assert value["signal_count"] == 0 and value["observation_count"] == 0
        assert value["source_diagnostics"]["valid_on_day_count"] == 2
        assert "INSUFFICIENT_FORWARD_WARMUP" in value["source_diagnostics"]["blockers"]
    cli("forward-shadow.py", "disable")
    assert before == manifest(protected)
    evidence = dict(result="PASS", original_on_day_days=content["on_day_valid_eod_days"],
        old_pr33_snapshot_on_day_days=old_count, source_days=[v["bar"]["trade_day"] for v in content["bars"]],
        source_database_sha256=database_sha, original_journal_head=content["journal_head"],
        actual_decision_clock_ms=s.clock_ms(), once_reason=once["reason"],
        warmup_reason="INSUFFICIENT_FORWARD_WARMUP", committed_observations=0, committed_signals=0,
        new_real_forward_days=0, original_bytes_unchanged=True, protected_files=len(before), **s.SAFE)
    target = ROOT / "state/issue47-evidence"
    target.mkdir(parents=True, exist_ok=True)
    (target / "real-boundary.json").write_bytes(s.j.canonical(evidence))
    (target / "real-commands-local.json").write_bytes(s.j.canonical(records))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-cli", type=Path)
    parser.add_argument("--preserve-root", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--real-observer", type=Path)
    parser.add_argument("--old-snapshot", type=Path)
    args, rest = parser.parse_known_args()
    if args.fixture_cli:
        raise SystemExit(fixture_cli(json.loads(args.fixture_cli.read_bytes())))
    if args.preserve_root:
        print(json.dumps(preservation(args.preserve_root.resolve(), args.baseline.resolve())))
        raise SystemExit(0)
    if args.real_observer:
        print(json.dumps(real_boundary(args.real_observer.resolve(), args.old_snapshot.resolve() if args.old_snapshot else None)))
        raise SystemExit(0)
    WORK.mkdir(parents=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ShadowTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = dict(result="PASS" if result.wasSuccessful() else "FAIL", tests_run=result.testsRun,
                    failures=len(result.failures), errors=len(result.errors), checks=CHECKS,
                    verification="developer_selftest_not_independent_acceptance", data_mode="synthetic_test",
                    market_calls=0, provider_calls=0, new_real_forward_days=0)
    (WORK / "evidence.json").write_bytes(s.j.canonical(evidence))
    (WORK / "commands-local.json").write_bytes(s.j.canonical(COMMANDS))
    print(json.dumps(dict(result=evidence["result"], tests_run=result.testsRun, evidence_ref=WORK.relative_to(ROOT).as_posix())))
    raise SystemExit(0 if result.wasSuccessful() else 1)
