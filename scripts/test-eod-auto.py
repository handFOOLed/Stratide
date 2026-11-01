"""Process-level synthetic CLI E2E, interruption/restart and safety counterexamples.

The fixture CLI is confined to this test file plus Rust's cfg(test) executable.
Production eod-auto-research.py/eod-auto-agent have no clock/fault override.
All artifacts remain in newly allocated, ignored state children for inspection.
"""
import argparse
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import eod_auto as a

ROOT = a.ROOT
spec = importlib.util.spec_from_file_location("snapshot_fixtures", ROOT / "scripts/test-data-snapshot.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
NOW = f.stamp("20261027") + 3600000
RUN = "auto-test-" + os.urandom(5).hex()
WORK = ROOT / "state/eod-auto-tests" / RUN
COMMANDS, RESULTS = [], []


def test_exe():
    suffix = ".exe" if os.name == "nt" else ""
    choices = sorted((ROOT / "target/debug/deps").glob("eod_auto_agent-*" + suffix), key=lambda p: p.stat().st_mtime)
    choices = [p for p in choices if p.is_file() and (os.name == "nt" or p.suffix == "")]
    if not choices:
        raise AssertionError("cargo test -p stratide-research --bin eod-auto-agent --no-run first")
    return choices[-1]


def fixture_cli(request):
    name, clock = request["name"], request["now_ms"]
    assert name.startswith("auto-test-")
    def invoke(action, auto_name):
        env = dict(os.environ, STRATIDE_AUTO_FIXTURE_TEST="1")
        p = subprocess.run([str(test_exe()), "--exact", "tests::fixture_cli", "--nocapture"],
                           input=json.dumps(dict(args=[action, auto_name], now_ms=clock,
                                                fixture_source=request["fixture_source"])).encode(),
                           capture_output=True, timeout=45, env=env)
        output = p.stdout.decode("utf-8")
        found = re.search(r"EOD_AUTO_FIXTURE_RESULT=(\{[^\n]+\})", output)
        if p.returncode or not found:
            raise AssertionError("fixture Rust bridge failed: " + output + p.stderr.decode("utf-8", errors="replace"))
        result = json.loads(found[1])
        a.j.require(result["exit_code"] == 0, result["value"].get("error_code", "BRIDGE_TEST_ERROR"))
        return result["value"]
    def fault(point):
        if request.get("fault") == point:
            os._exit(86)  # actual process interruption, no cleanup or state rewrite
    with patch.object(a.d, "now", return_value=clock), patch("socket.create_connection", side_effect=AssertionError("network")):
        if request.get("data_sync"):
            sys.argv = ["research-data.py", "--store", name, *request["args"]]
            return a.d.main()
        return a.main(["--name", name, *request["args"]], clock=lambda: clock, invoke=invoke, fault=fault)


def launch(name, *args, now=NOW, fault=None, data_sync=False):
    work = WORK / name
    work.mkdir(parents=True, exist_ok=True)
    request = work / ("request-" + os.urandom(5).hex() + ".json")
    store = name
    config_path = ROOT / "state/eod-auto" / name / "config.json"
    if args and args[0] == "init" and "--snapshot-store" in args:
        store = args[args.index("--snapshot-store") + 1]
    elif config_path.exists():
        store = a.c.read(config_path)["snapshot_store_name"]
    a.c.write(request, dict(name=name, now_ms=now, args=list(map(str, args)), fault=fault,
                           data_sync=data_sync, fixture_source=str(WORK / store / "forward.sqlite")))
    return subprocess.Popen([sys.executable, "-B", str(Path(__file__).absolute()), "--fixture-cli", str(request)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def call(name, *args, now=NOW, fault=None, data_sync=False, code=0):
    process = launch(name, *args, now=now, fault=fault, data_sync=data_sync)
    out, err = process.communicate(timeout=60)
    if process.returncode != code:
        raise AssertionError(f"{args}: expected {code}, got {process.returncode}: {out[:1800]!r} {err[:1800]!r}")
    try:
        values = [json.loads(out)] if out else []
    except json.JSONDecodeError:
        values = [json.loads(line) for line in out.splitlines()]
    COMMANDS.append(dict(name=name, command=["fixture-cli", *map(str, args)],
                         source_clock_ms=now, fault=fault, exit_code=process.returncode,
                         result=values[-1] if values else None))
    return values[-1] if values else None


def counts(name):
    auto = a.Auto(name)
    with auto.db() as db:
        tasks = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        calls = db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        intents = db.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'eod_auto_intent:%'").fetchone()[0]
    registrations = len(list((ROOT / "state/candidates" / name / "registrations").glob("*.json")))
    return dict(intents=intents, tasks=tasks, calls=calls, registrations=registrations)


def setup(label="run", events=None, enabled=True):
    name = "auto-test-" + label + "-" + os.urandom(5).hex()
    source = WORK / name / "forward.sqlite"
    source.parent.mkdir(parents=True)
    f.save_journal(source, events or f.base_events())
    call(name, "sync", "--observer", source, data_sync=True)
    call(name, "init", "--snapshot-store", name)
    if enabled:
        call(name, "enable")
    return name, source


def sql(name, statements):
    with a.Auto(name).db(write=True) as db:
        for query, params in statements:
            db.execute(query, params)


def collect(process, name, *args):
    out, err = process.communicate(timeout=60)
    if process.returncode not in (0, 2):
        raise AssertionError(f"{args}: exit={process.returncode}: {out[:500]!r} {err[:500]!r}")
    value = json.loads(out)
    COMMANDS.append(dict(name=name, command=["fixture-cli", *map(str, args)],
                         source_clock_ms=NOW, exit_code=process.returncode, result=value))
    return process.returncode, value


def total_counts(names):
    values = [counts(name) for name in names]
    return {key: sum(v[key] for v in values) for key in values[0]}


class AutoTests(unittest.TestCase):
    def test_distinct_instances_same_binding_concurrent_enable_and_restart(self):
        first, _ = setup("binding-a", enabled=False)
        second = "auto-test-binding-b-" + os.urandom(5).hex()
        call(second, "init", "--snapshot-store", first)
        names = (first, second)
        self.assertEqual(a.Auto(first).config()["binding_sha256"], a.Auto(second).config()["binding_sha256"])
        processes = [launch(name, "enable") for name in names]
        enabled = [collect(p, name, "enable") for p, name in zip(processes, names)]
        processes = [launch(name, "once") for name in names]
        runs = [collect(p, name, "once") for p, name in zip(processes, names)]
        aggregate = total_counts(names)
        RESULTS.append(dict(check="distinct_instances_same_binding", enable_exits=[v[0] for v in enabled],
                            once_exits=[v[0] for v in runs], global_counts=aggregate))
        self.assertEqual(aggregate, dict(intents=1, tasks=1, calls=1, registrations=1))
        self.assertEqual(sorted(v[0] for v in enabled), [0, 2])
        owner = names[next(i for i, value in enumerate(runs) if value[0] == 0)]
        blocked = next(name for name in names if name != owner)
        self.assertEqual(call(blocked, "enable", code=2)["reason"], "EOD_AUTO_BINDING_OWNED")
        self.assertEqual(call(owner, "once")["reason"], "ALREADY_ARCHIVED_INPUT_FROZEN")
        self.assertEqual(call(blocked, "once", code=2)["reason"], "EOD_AUTO_BINDING_OWNED")
        raw = subprocess.run([str(a.EXE), "intent", blocked], capture_output=True)
        self.assertEqual(raw.returncode, 2)
        self.assertEqual(json.loads(raw.stdout)["error_code"], "EOD_AUTO_BINDING_OWNED")
        call(owner, "disable")
        self.assertEqual(call(blocked, "enable", code=2)["reason"], "EOD_AUTO_BINDING_OWNED")
        call(owner, "enable")
        call(owner, "once")
        self.assertEqual(total_counts(names), aggregate)
        independent, _ = setup("binding-independent")
        call(independent, "once")
        self.assertNotEqual(a.Auto(independent).config()["binding_sha256"], a.Auto(owner).config()["binding_sha256"])
        self.assertEqual(counts(independent), aggregate)
        RESULTS.append(dict(check="binding_owner_persists_after_disable_and_restart", global_counts=total_counts(names),
                            different_source_counts=counts(independent)))

    def test_legacy_enabled_instances_claim_once_and_preserve_original_work(self):
        first, _ = setup("legacy-enabled-a", enabled=False)
        second = "auto-test-legacy-enabled-b-" + os.urandom(5).hex()
        call(second, "init", "--snapshot-store", first)
        # Pre-fix enable had no shared claim. Seed only those original flags;
        # every research task/call/result below still comes from the actual CLI.
        for name in (first, second):
            sql(name, [("UPDATE meta SET value='true' WHERE key='eod_auto_enabled'", ())])
        processes = [launch(name, "once") for name in (first, second)]
        runs = [collect(p, name, "once") for p, name in zip(processes, (first, second))]
        self.assertEqual(sorted(v[0] for v in runs), [0, 2])
        self.assertEqual(total_counts((first, second)), dict(intents=1, tasks=1, calls=1, registrations=1))
        RESULTS.append(dict(check="legacy_enabled_without_claim", once_exits=[r[0] for r in runs],
                            global_counts=total_counts((first, second))))

        prior, _ = setup("legacy-prior-a")
        call(prior, "once", fault="after_task", code=86)
        auto = a.Auto(prior)
        claim = auto.binding_paths(auto.config())[1]
        self.assertEqual(claim.parent, ROOT / "state/eod-auto/.bindings")
        claim.unlink()  # newly created synthetic fixture: emulate pre-fix metadata, never delete an Agent DB
        newcomer = "auto-test-legacy-prior-b-" + os.urandom(5).hex()
        call(newcomer, "init", "--snapshot-store", prior)
        before = a.j.sha(auto.dbpath.read_bytes())
        self.assertEqual(call(newcomer, "enable", code=2)["reason"], "EOD_AUTO_BINDING_OWNED")
        self.assertEqual(before, a.j.sha(auto.dbpath.read_bytes()))
        self.assertEqual(a.Auto(newcomer).binding_owner(auto.config()), prior)
        call(prior, "once")
        self.assertEqual(total_counts((prior, newcomer)), dict(intents=1, tasks=1, calls=1, registrations=1))
        RESULTS.append(dict(check="legacy_original_intent_retains_ownership", original_db_sha_unchanged_during_claim=True,
                            global_counts=total_counts((prior, newcomer))))

    def test_legacy_conflicting_intents_block_without_rewriting_evidence(self):
        first, _ = setup("legacy-conflict-a", enabled=False)
        second = "auto-test-legacy-conflict-b-" + os.urandom(5).hex()
        call(second, "init", "--snapshot-store", first)
        config = a.Auto(first).config()
        with patch.object(a.d, "now", return_value=NOW):
            expected = a.d.Store(first).agent_input()
        intent = dict(input=expected, trigger_key=a.POLICY + ":" + config["binding_sha256"] + ":" + expected["source_day"])
        # Negative upgrade fixture contains only pre-task intent records. Never
        # fabricate a completed task, Provider call or research result.
        for name in (first, second):
            sql(name, [("UPDATE meta SET value='true' WHERE key='eod_auto_enabled'", ()),
                       ("INSERT INTO meta VALUES(?,?)", ("eod_auto_intent:" + expected["source_day"], json.dumps(intent)))])
        before = {name: a.j.sha(a.Auto(name).dbpath.read_bytes()) for name in (first, second)}
        for name in (first, second):
            self.assertEqual(call(name, "enable", code=2)["reason"], "EOD_AUTO_BINDING_REVIEW_REQUIRED")
            self.assertEqual(call(name, "once", code=2)["reason"], "EOD_AUTO_BINDING_REVIEW_REQUIRED")
            self.assertEqual(before[name], a.j.sha(a.Auto(name).dbpath.read_bytes()))
        self.assertEqual(total_counts((first, second)), dict(intents=2, tasks=0, calls=0, registrations=0))
        self.assertFalse(a.Auto(first).binding_paths(config)[1].exists())
        RESULTS.append(dict(check="legacy_conflicting_intents", reason="EOD_AUTO_BINDING_REVIEW_REQUIRED",
                            original_db_sha_unchanged=True, new_tasks=0, new_calls=0, new_registrations=0))

    def test_full_cli_two_isolated_runs_repeat_revision_and_readonly_queries(self):
        evidence = []
        for _ in range(2):
            name, source = setup("full", enabled=False)
            self.assertEqual(call(name, "once", code=3)["reason"], "OWNER_DISABLED")
            self.assertEqual(counts(name), dict(intents=0, tasks=0, calls=0, registrations=0))
            call(name, "enable")
            result = call(name, "watch", "--cycles", 1, "--sync")
            self.assertEqual(result["state"], "COMPLETED")
            saved = call(name, "task", result["task_id"])["task"]
            candidate = call(name, "candidate", result["registration_sha256"])
            self.assertEqual(candidate["frozen_input"], saved["input"])
            self.assertEqual(candidate["frozen_research"], saved["result"]["research"])
            self.assertEqual(candidate["snapshot_provenance"]["snapshot_verification"], "SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION")
            self.assertEqual(candidate["task_origin"], "TASK_ORIGIN_NOT_ATTESTED")
            before = a.j.sha(a.Auto(name).dbpath.read_bytes())
            for action in (("status",), ("task", saved["id"]), ("candidate", result["registration_sha256"])):
                value = call(name, *action)
                text = json.dumps(value)
                for forbidden in (str(ROOT), "600000.SH", "raw_sha256", "close_fen", "owner-token"):
                    self.assertNotIn(forbidden, text)
            self.assertEqual(before, a.j.sha(a.Auto(name).dbpath.read_bytes()))
            for args in (("once",), ("once", "--sync")):
                self.assertEqual(call(name, *args)["reason"], "ALREADY_ARCHIVED_INPUT_FROZEN")
            events = f.base_events()
            f.append_day(events, "20261027", close="11.00")
            f.save_journal(source, events)
            call(name, "sync", data_sync=True)
            self.assertEqual(call(name, "once")["reason"], "ALREADY_ARCHIVED_INPUT_FROZEN")
            self.assertEqual(call(name, "task", saved["id"])["task"], saved)
            self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))
            evidence.append(dict(source_day=saved["input"]["source_day"], data_mode=saved["input"]["mode"],
                                 frozen_input=saved["input"], research=saved["result"]["research"], counts=counts(name),
                                 state=candidate["state"], evaluation=candidate["evaluation"], handoff=candidate["handoff"]))
        self.assertEqual(evidence[0], evidence[1])
        RESULTS.append(dict(check="two_isolated_full_cli", logical_evidence_equal=True,
                            ignored_fields=["directory/source identity", "task/candidate SHA", "process timestamps"],
                            counts=evidence[0]["counts"], source_day=evidence[0]["source_day"], data_mode="synthetic_test"))

    def test_five_process_interruption_nodes_resume_without_duplicates(self):
        for point in ("after_intent", "after_task", "after_research", "after_registration", "after_archive"):
            with self.subTest(point=point):
                name, _ = setup("crash")
                call(name, "once", fault=point, code=86)
                partial = counts(name)
                result = call(name, "once")
                self.assertIn(result["reason"], ("CANDIDATE_ARCHIVED", "ALREADY_ARCHIVED_INPUT_FROZEN"))
                self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))
                call(name, "once")
                self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))
                RESULTS.append(dict(check="process_interruption", point=point, before_restart=partial, after_restart=counts(name)))

    def test_parallel_once_and_watch_only_one_daily_task(self):
        name, _ = setup("concurrent")
        path = a.Auto(name).agent / "settings.json"
        settings = a.c.read(path)
        settings["models"][0]["fake_scenario"] = "slow"
        a.c.write(path, settings)
        first = launch(name, "watch", "--cycles", 1)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            with a.Auto(name).db() as db:
                dispatched = db.execute("SELECT COUNT(*) FROM calls WHERE state='dispatched'").fetchone()[0]
            if dispatched:
                break
            time.sleep(0.02)
        self.assertEqual(dispatched, 1)
        busy = call(name, "once", code=2)
        self.assertEqual(busy["reason"], "STORE_BUSY")
        # Controls remain immediate while an already dispatched fake finishes.
        self.assertFalse(call(name, "disable")["enabled"])
        out, err = first.communicate(timeout=20)
        self.assertEqual(first.returncode, 0, out + err)
        self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))
        self.assertEqual(call(name, "once", code=3)["reason"], "OWNER_DISABLED")
        RESULTS.append(dict(check="concurrent_once_watch_and_disable", competing_reason=busy["reason"], counts=counts(name)))

    def test_pause_resume_cancel_and_disabled_restart(self):
        name, _ = setup("control")
        self.assertTrue(call(name, "pause")["paused"])
        self.assertEqual(call(name, "once", code=3)["reason"], "OWNER_PAUSED")
        self.assertEqual(counts(name)["tasks"], 0)
        call(name, "resume")
        call(name, "once", fault="after_task", code=86)
        call(name, "cancel", 1)
        self.assertEqual(call(name, "once", code=2)["reason"], "AUTO_TASK_REVIEW_REQUIRED")
        self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=0, registrations=0))
        call(name, "disable")
        self.assertEqual(call(name, "once", code=3)["reason"], "OWNER_DISABLED")
        self.assertTrue(call(name, "status")["needs_manual_review"])

    def test_time_counterexamples_and_production_has_no_clock_override(self):
        name, _ = setup("time")
        for now, reason in ((f.stamp("20261027") - 7200000, "BEFORE_EOD_WINDOW"),
                            (f.stamp("20261028"), "MISSED_OR_STALE"),
                            (NOW + 25 * 3600000, "SNAPSHOT_SYNC_STALE_OR_CLOCK")):
            # A fresh read cannot move original source day forward.
            code = 2 if reason == "SNAPSHOT_SYNC_STALE_OR_CLOCK" else 3
            self.assertEqual(call(name, "once", now=now, code=code)["reason"], reason)
            self.assertEqual(counts(name)["tasks"], 0)
        p = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/eod-auto-research.py"),
                            "--name", name, "once", "--now", str(NOW)], capture_output=True)
        self.assertEqual(p.returncode, 2)
        # The actual clock really skips the old synthetic source.
        p = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/eod-auto-research.py"),
                            "--name", name, "once"], capture_output=True)
        self.assertIn(p.returncode, (2, 3))
        self.assertEqual(counts(name)["tasks"], 0)
        events = f.base_events()[:3]
        f.append_day(events, "20261026", received_day="20261027")
        late, _ = setup("late", events=events)
        self.assertEqual(call(late, "once", code=3)["reason"], "MISSED_OR_STALE")

    def test_source_changed_before_and_after_sync_no_task_replacement(self):
        name, source = setup("source")
        events = f.base_events()
        f.append_day(events, "20261027", close="11.00")
        f.save_journal(source, events)
        self.assertEqual(call(name, "once", code=2)["reason"], "SOURCE_CHANGED_SINCE_SYNC")
        self.assertEqual(counts(name)["tasks"], 0)
        call(name, "once", "--sync", fault="after_research", code=86)
        f.append_day(events, "20261027", close="10.50")
        f.save_journal(source, events)
        call(name, "sync", data_sync=True)
        self.assertEqual(call(name, "once", code=2)["reason"], "SOURCE_CHANGED_REVIEW_REQUIRED")
        self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=0))

    def test_archived_but_not_recorded_recovers_after_source_revision(self):
        name, source = setup("archive")
        call(name, "once", fault="after_registration", code=86)
        events = f.base_events()
        f.append_day(events, "20261027", close="11.00")
        f.save_journal(source, events)
        call(name, "sync", data_sync=True)
        self.assertEqual(call(name, "once")["state"], "COMPLETED")
        self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))

    def test_new_observed_day_continues_and_missed_intent_never_backfills(self):
        for missed in (False, True):
            name, source = setup("next-day")
            if missed:
                call(name, "once", fault="after_task", code=86)
            else:
                call(name, "once")
            events = f.base_events()
            f.append_day(events, "20261028")
            f.save_journal(source, events)
            next_clock = f.stamp("20261028") + 3600000
            result = call(name, "once", "--sync", now=next_clock)
            self.assertEqual(result["source_day"], "2026-10-28")
            self.assertEqual(counts(name), dict(intents=2, tasks=2, calls=1 if missed else 2,
                                               registrations=1 if missed else 2))
            old = call(name, "task", 1, now=next_clock)["task"]
            if missed:
                self.assertEqual(old["status"], "cancelled")
                self.assertEqual(old["reason"], "AUTO_MISSED_OR_STALE")
            self.assertEqual(call(name, "once", now=next_clock)["reason"], "ALREADY_ARCHIVED_INPUT_FROZEN")
            RESULTS.append(dict(check="next_observed_source_day", old_day_missed=missed, counts=counts(name)))

    def test_cloud_settings_real_currency_and_bad_grant_never_reserve_or_call(self):
        for change, expected in ((lambda v: v["models"][0].update(kind="chat_completions_v1", endpoint="https://never-resolve.invalid/v1/chat/completions",
                                      api_key_env="STRATIDE_RESEARCH_KEY_NEVER_READ", fake_scenario=None), "EOD_AUTO_LOCAL_FAKE_ONLY"),
                                 (lambda v: v["budget"].update(currency="CNY"), "EOD_AUTO_LOCAL_FAKE_ONLY"),
                                 (lambda v: v.update(default_model="not-present"), "MODEL_SELECTION_INVALID"),
                                 (lambda v: v["models"][0]["grant"].update(revoked=True), "AUTHORIZATION_REQUIRED")):
            name, _ = setup("permission")
            auto = a.Auto(name)
            settings = a.c.read(auto.agent / "settings.json")
            change(settings)
            a.c.write(auto.agent / "settings.json", settings)
            before = a.j.sha(auto.dbpath.read_bytes())
            self.assertEqual(call(name, "once", code=2)["reason"], expected)
            self.assertEqual(counts(name), dict(intents=0, tasks=0, calls=0, registrations=0))
            self.assertEqual(before, a.j.sha(auto.dbpath.read_bytes()))
            if expected == "EOD_AUTO_LOCAL_FAKE_ONLY":
                p = subprocess.run([str(a.EXE), "check", name], capture_output=True)
                self.assertEqual(p.returncode, 2)
                self.assertEqual(json.loads(p.stdout)["error_code"], expected)

    def test_snapshot_corruption_wal_identity_permissions_and_quality(self):
        mutations = [("hash", lambda v, b, t: v.update(last_valid_source_day="20990101"), False),
                     ("permission", lambda v, b, t: v.update(live_allowed=True), True),
                     ("identity", lambda v, b, t: b.update(journal_genesis="0" * 64), True),
                     ("running", lambda v, b, t: t.update(state="running"), True),
                     ("unknown_calendar", lambda v, b, t: v.update(can_research=False, blockers=["CALENDAR_UNKNOWN"]), True),
                     ("missing_day", lambda v, b, t: v.update(last_valid_source_day=None, bars=[]), True)]
        for label, mutate, rehash in mutations:
            name, _ = setup("bad-" + label)
            store = a.d.Store(name)
            with store.connect(write=True) as db:
                binding, saved, attempt = store.current(db)
                content = saved["content"]
                mutate(content, binding, attempt)
                sha = a.c.digest(content) if rehash else saved["snapshot_sha256"]
                db.execute("UPDATE snapshots SET sha=?,content=? WHERE sha=?",
                           (sha, a.j.canonical(content).decode(), saved["snapshot_sha256"]))
                db.execute("UPDATE control SET binding=?,current_sha=?,attempt=? WHERE id=1",
                           (a.j.canonical(binding).decode(), sha, a.j.canonical(attempt).decode()))
            call(name, "once", code=2)
            self.assertEqual(counts(name)["tasks"], 0)
        name, _ = setup("wal")
        wal = Path(str(a.d.Store(name).path) + "-wal")
        shm = Path(str(a.d.Store(name).path) + "-shm")
        if shm.exists():
            shm.unlink()  # only this test's quiescent new store
        wal.write_bytes(b"synthetic damaged WAL")
        self.assertEqual(call(name, "once", code=2)["reason"], "SNAPSHOT_WAL_INCOMPLETE")
        self.assertEqual(counts(name)["tasks"], 0)
        shm.write_bytes(bytes(32768))
        self.assertEqual(call(name, "once", code=2)["reason"], "SNAPSHOT_WAL_INVALID")
        self.assertEqual(counts(name)["tasks"], 0)

    def test_partial_or_forged_export_and_budget_failure_not_archived(self):
        name, _ = setup("partial")
        call(name, "once", fault="after_task", code=86)
        task = call(name, "task", 1)["task"]
        self.assertEqual(task["status"], "queued")
        forged = copy.deepcopy(task)
        forged.update(status="completed", result=dict(qualification="PASS"))
        a.c.write(a.Auto(name).root / "task-export.json", forged)
        call(name, "once")  # discards forged file, runs the actual queued task once
        self.assertNotEqual(call(name, "task", 1)["task"], forged)
        self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))
        name, _ = setup("budget")
        path = a.Auto(name).agent / "settings.json"
        settings = a.c.read(path)
        settings["budget"]["daily_limit_micro"] = 1
        a.c.write(path, settings)
        call(name, "once", code=2)
        self.assertEqual(call(name, "task", 1)["task"]["reason"], "DAILY_BUDGET_EXHAUSTED")
        self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=0, registrations=0))

    def test_uncommitted_trigger_is_not_a_success_and_rollback_allows_one_intent(self):
        name, _ = setup("transaction")
        auto = a.Auto(name)
        with auto.db(write=True) as db:
            db.execute("INSERT INTO meta VALUES('eod_auto_intent:2026-10-27','uncommitted-invalid')")
            # Read-only status sees only committed state, never the unfinished intent.
            self.assertEqual(call(name, "status")["tasks"], [])
            db.rollback()
        call(name, "once")
        self.assertEqual(counts(name), dict(intents=1, tasks=1, calls=1, registrations=1))

    def test_init_existing_directory_binding_and_junction_are_rejected(self):
        name, _ = setup("init")
        before = a.j.sha(a.Auto(name).dbpath.read_bytes())
        self.assertEqual(call(name, "init", "--snapshot-store", name, code=2)["reason"], "NEW_AUTO_DIRECTORY_REQUIRED")
        self.assertEqual(before, a.j.sha(a.Auto(name).dbpath.read_bytes()))
        path = a.Auto(name).root / "config.json"
        config = a.c.read(path)
        config["snapshot_store_name"] = "a-different-source"
        a.c.write(path, config)
        self.assertEqual(call(name, "once", code=2)["reason"], "AUTO_BINDING_CHANGED")
        other, _ = setup("junction")
        link_name = other + "-link"
        link = ROOT / "state/data-sync" / link_name
        if os.name == "nt":
            p = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(a.d.Store(other).root)], capture_output=True)
            self.assertEqual(p.returncode, 0)
        else:
            link.symlink_to(a.d.Store(other).root, target_is_directory=True)
        try:
            call("auto-test-link-" + os.urandom(4).hex(), "init", "--snapshot-store", link_name, code=2)
        finally:
            link.rmdir() if os.name == "nt" else link.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-cli", type=Path)
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--test", action="append", help="只执行指定 AutoTests 方法")
    args, remaining = parser.parse_known_args()
    if args.fixture_cli:
        raise SystemExit(fixture_cli(a.c.read(args.fixture_cli)))
    WORK.mkdir(parents=True)
    test_exe()
    suite = (unittest.TestSuite(AutoTests(name) for name in args.test) if args.test else
             unittest.defaultTestLoader.loadTestsFromTestCase(AutoTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = dict(result="PASS" if result.wasSuccessful() else "FAIL", tests_run=result.testsRun,
                    failures=len(result.failures), errors=len(result.errors), verification="Sol_developer_selftest_not_independent_acceptance",
                    data_mode="synthetic_test", fixture_source_day="2026-10-27", source_clock_ms=NOW,
                    clock="cfg(test)_Rust_and_test_only_Python_dependency_injection",
                    production_clock_override=False, real_provider_calls=0, market_requests=0,
                    genuine_new_forward_days=0, checks=RESULTS, **a.SAFE)
    a.c.write(WORK / "evidence.json", evidence)
    a.c.write(WORK / "commands-local.json", COMMANDS)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
