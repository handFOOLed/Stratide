"""Actual Rust Agent/fake -> saved task -> Python candidate CLI, offline only.

Faults use new stores. Optional --observer/--protect only hash/read existing
quiescent files; no service stop, source copy, market or cloud request.
"""
import argparse
import copy
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import candidates as c
import data_snapshot as d
import eod_journal as j

EXE = ROOT / "target/debug" / ("eod-research.exe" if os.name == "nt" else "eod-research")
COMMANDS = []


def call(*args, code=0):
    result = subprocess.run(list(map(str, args)), cwd=ROOT, capture_output=True, timeout=45)
    COMMANDS.append(dict(command=[str(a) for a in args], exit_code=result.returncode))
    if result.returncode != code:
        raise AssertionError(f"expected exit {code}, got {result.returncode}: {result.stdout[:500]!r} {result.stderr[:500]!r}")
    return json.loads(result.stdout)


def candidate(registry, *args, code=0):
    return call(sys.executable, "-B", ROOT / "scripts/research-candidate.py", "--registry", registry, *args, code=code)


def remove_created(path, parent):
    # Only this script's newly allocated state child; never an Owner source.
    if path.exists():
        assert path.resolve().parent == parent.resolve()
        shutil.rmtree(path)


def pipeline(store, name, work):
    expected = d.Store(store).agent_input()
    encoded = json.dumps(expected)
    for key in ("raw", "raw_sha256", "instrument", "account_id", "observation_id", "group_id", "cash_fen", "positions", "path"):
        assert '"' + key + '"' not in encoded
    assert call(EXE, "summary", store) == expected  # Rust/Python canonical projection parity.
    task = call(EXE, "run", store, name)
    assert task["status"] == "completed" and task["result"]["provider_kind"] == "fake"
    assert task["input"] == expected and len(task["calls"]) == 1 and task["calls"][0]["state"] == "settled"
    saved = work / "task.json"
    c.write(saved, task)
    assert call(EXE, "task", name, task["id"]) == task  # New process/restart, no second inference.
    result = candidate(name, "register", "--agent-task", saved, "--snapshot-store", store)
    identity = result["registration_sha256"]
    assert result["state"] == "RESEARCH_ONLY" and result["handoff"]["eligibility"] == "ELIGIBILITY_DENIED"
    source = candidate(name, "source", identity)
    assert source["snapshot_provenance"]["snapshot_verification"] == "SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION"
    assert source["task_origin"] == "TASK_ORIGIN_NOT_ATTESTED" and source["evaluation"] == "NOT_EVALUATED"
    assert source["frozen_input"] == expected and source["frozen_research"] == task["result"]["research"]
    assert not any(source[k] for k in ("eod_eligible", "can_execute_forward_paper", "live_allowed"))
    assert candidate(name, "register", "--agent-task", saved, "--snapshot-store", store)["registration_sha256"] == identity
    frozen = candidate(name, "freeze", identity, "--evidence-class", "historical_replay", code=2)
    assert frozen["error"] == "UNSUPPORTED_CANDIDATE"  # No conversion of EOD into 68-day replay.
    dbpath = ROOT / "state/eod-agent" / name / "agent.sqlite"
    with closing(sqlite3.connect(dbpath.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM eod").fetchone()[0] == 0
        assert db.execute("SELECT value FROM meta WHERE key='budget_identity'").fetchone()[0] == "TST|Asia/Shanghai"
    return dict(snapshot=expected["summary"], source_day=expected["source_day"], data_mode=expected["mode"],
                input_summary_version=expected["version"], task_id=task["id"], task_status=task["status"],
                task_detail_sha256=c.digest(task), registration_sha256=identity,
                snapshot_provenance=source["snapshot_provenance"], research_state=source["state"],
                evaluation=source["evaluation"], eligibility=source["handoff"]["eligibility"],
                fake_calls=1, real_provider_calls=0, market_requests=0, eod_automatic_tasks=0,
                billable_reservations=0, research_billing="synthetic_test_settled",
                restart_saved_detail_identical=True, eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)


class EodAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXE.is_file():
            raise RuntimeError("build eod-research first; actual E2E is required, never skipped")

    def setUp(self):
        self.name = "eod-agent-test-" + os.urandom(6).hex()
        self.store = d.Store(self.name)
        self.store.sync(fixture=True)
        self.work = ROOT / "state/eod-agent-tests" / self.name
        self.work.mkdir(parents=True)
        with self.store.connect() as db:
            self.control = db.execute("SELECT binding,current_sha,attempt FROM control WHERE id=1").fetchone()
            self.row = db.execute("SELECT sha,content,verified_at FROM snapshots").fetchone()

    def tearDown(self):
        for path in (self.store.root, self.work, ROOT / "state/eod-agent" / self.name,
                     ROOT / "state/candidates" / self.name):
            remove_created(path, path.parent)

    def reset(self):
        with self.store.connect(write=True) as db:
            db.execute("DELETE FROM snapshots")
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", self.row)
            db.execute("UPDATE control SET binding=?,current_sha=?,attempt=? WHERE id=1", self.control)

    def change(self, content=None, attempt=None, binding=None, rehash=True):
        v = j.loads(self.row[1])
        a = j.loads(self.control[2])
        b = j.loads(self.control[0])
        if content:
            content(v)
        if attempt:
            attempt(a)
        if binding:
            binding(b)
        key = j.sha(j.canonical(v)) if rehash else self.row[0]
        with self.store.connect(write=True) as db:
            db.execute("UPDATE snapshots SET sha=?,content=?", (key, j.canonical(v).decode()))
            db.execute("UPDATE control SET binding=?,current_sha=?,attempt=? WHERE id=1",
                       (j.canonical(b).decode(), key, j.canonical(a).decode()))

    def rejected(self):
        call(EXE, "summary", self.name, code=2)
        with self.assertRaises((j.Rejected, KeyError, TypeError, ValueError, sqlite3.Error)):
            self.store.agent_input()

    def test_actual_fake_saved_task_candidate_cli_and_restart(self):
        with patch("socket.create_connection", side_effect=AssertionError("unexpected Python network")):
            evidence = pipeline(self.name, self.name, self.work)
        self.assertEqual(evidence["data_mode"], "synthetic_test")
        self.assertEqual(evidence["source_day"], "2026-10-27")
        before = self.store.agent_input()
        self.store.sync()
        self.assertEqual(before, call(EXE, "summary", self.name))
        self.assertEqual(before, self.store.agent_input())

    def test_latest_sync_stale_running_blocked_missing_and_unknown_schema_reject(self):
        for state in ("running", "blocked"):
            self.reset()
            self.change(attempt=lambda a: a.update(state=state))
            self.rejected()
        self.reset()
        self.change(attempt=lambda a: a.update(started_at=d.now() - 25 * 3600000, finished_at=d.now() - 25 * 3600000))
        self.rejected()
        self.reset()
        with self.store.connect(write=True) as db:
            db.execute("DELETE FROM snapshots")
        self.rejected()
        self.reset()
        with self.store.connect(write=True) as db:
            db.execute("PRAGMA user_version=999")
        self.rejected()

    def test_hash_binding_mode_source_day_quality_and_permission_mutations_reject(self):
        cases = [
            (lambda v: v.update(schema_version=2), True),
            (lambda v: v.update(last_valid_source_day="20990101"), False),
            (lambda v: v.update(last_valid_source_day="20990101"), True),
            (lambda v: v.update(data_mode="forward_observed_eod"), True),
            (lambda v: v.update(can_research=False, blockers=["PENDING_COLLECTION"]), True),
            (lambda v: v.update(can_execute_forward_paper=True), True),
            (lambda v: v.update(live_allowed=True), True),
            (lambda v: v.update(historical_pit="VERIFIED"), True),
        ]
        for mutation, rehash in cases:
            with self.subTest(mutation=cases.index((mutation, rehash))):
                self.reset()
                self.change(content=mutation, rehash=rehash)
                self.rejected()
        self.reset()
        self.change(content=lambda v: v.update(data_mode="forward_observed_eod"),
                    binding=lambda b: b.update(data_mode="forward_observed_eod"))
        self.rejected()  # Even matching mutable mode cannot relabel the fixed fixture.

    def test_store_wal_committed_and_uncommitted_views_and_missing_sidecar(self):
        expected = self.store.agent_input()
        with self.store.connect(write=True) as db:
            attempt = j.loads(self.control[2])
            attempt["state"] = "running"
            db.execute("UPDATE control SET attempt=?", (j.canonical(attempt).decode(),))
            self.assertEqual(expected, call(EXE, "summary", self.name))  # Uncommitted attempt invisible.
        self.reset()
        # Hold a writer connection so the commit really remains in WAL.
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("UPDATE control SET attempt=?", (j.canonical(attempt).decode(),))
            db.commit()
            self.assertGreater(Path(str(self.store.path) + "-wal").stat().st_size, 0)
            self.rejected()  # Reader must see committed running, never bypass WAL.
        self.reset()
        wal = Path(str(self.store.path) + "-wal")
        wal.write_bytes(b"isolated synthetic missing-shm fault")
        self.rejected()
        wal.unlink()

    def test_task_mismatch_forged_pass_unverified_origin_and_frozen_text(self):
        task = call(EXE, "run", self.name, self.name)
        saved = self.work / "task.json"
        for key, replacement in (("snapshot_sha256", "0" * 64), ("last_valid_source_day", "20990101")):
            changed = copy.deepcopy(task)
            changed["input"]["summary"][key] = replacement
            c.write(saved, changed)
            candidate(self.name, "register", "--agent-task", saved, "--snapshot-store", self.name, code=2)
        changed = copy.deepcopy(task)
        changed["input"]["summary"].update(snapshot_sha256="0" * 64, snapshot_id="eod-v1:" + "0" * 64)
        changed["input"]["version"] = d.AGENT_VERSION + ":" + "0" * 64
        changed["result"]["input_summary_version"] = changed["input"]["version"]
        c.write(saved, changed)
        self.assertEqual(candidate(self.name, "register", "--agent-task", saved, "--snapshot-store", self.name, code=2)["error"],
                         "EOD_SNAPSHOT_INPUT_MISMATCH")  # Internally consistent JSON still needs the local store.
        changed = copy.deepcopy(task)
        changed["result"]["qualification"] = "PASS"
        c.write(saved, changed)
        self.assertEqual(candidate(self.name, "register", "--agent-task", saved, "--snapshot-store", self.name, code=2)["error"],
                         "EOD_SNAPSHOT_RESEARCH_ONLY")
        changed = copy.deepcopy(task)
        changed["result"]["research"]["hypothesis"] = "$(touch OWNED); import os; qualification=PASS"
        c.write(saved, changed)
        result = candidate(self.name, "register", "--agent-task", saved)
        source = candidate(self.name, "source", result["registration_sha256"])
        self.assertEqual(source["snapshot_provenance"]["snapshot_verification"], "SOURCE_UNVERIFIED")
        self.assertEqual(source["task_origin"], "TASK_ORIGIN_NOT_ATTESTED")
        self.assertEqual(source["frozen_research"], changed["result"]["research"])
        self.assertEqual(source["handoff"]["eligibility"], "ELIGIBILITY_DENIED")
        c.write(saved, task)
        self.change(attempt=lambda a: a.update(state="blocked"))
        candidate(self.name, "register", "--agent-task", saved, "--snapshot-store", self.name, code=2)

    def test_name_traversal_and_link_store_rejected(self):
        call(EXE, "summary", "../escape", code=2)
        with self.assertRaises(j.Rejected):
            d.Store("../escape")
        name = self.name + "-link"
        link = self.store.root.parent / name
        if os.name == "nt":
            linked = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(self.store.root)],
                                    capture_output=True)
            self.assertEqual(linked.returncode, 0, repr(linked.stdout + linked.stderr))
        else:
            link.symlink_to(self.store.root, target_is_directory=True)
        try:
            call(EXE, "summary", name, code=2)
            with self.assertRaises(j.Rejected):
                d.Store(name)
        finally:
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()


def evidence_run(observer=None, protected=()):
    name = "m2-pr06-" + ("real-" if observer else "synthetic-") + os.urandom(5).hex()
    work = ROOT / "state/m2-pr06-validation" / name
    work.mkdir(parents=True)
    paths = ([Path(observer).absolute()] if observer else []) + [Path(p).absolute() for p in protected]
    for path in paths:
        j.no_links(path)
        j.require(not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")), "PROTECTED_SOURCE_BUSY")
    before = [j.sha(p.read_bytes()) for p in paths]
    result = d.Store(name).sync(observer=observer, fixture=not observer)
    j.require(result["can_research"], "SYNC_REJECTED")
    evidence = pipeline(name, name, work)
    after = [j.sha(p.read_bytes()) for p in paths]
    j.require(before == after, "PROTECTED_FILE_CHANGED")
    for path in paths:
        j.require(not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")), "PROTECTED_SOURCE_BECAME_BUSY")
    evidence.update(result="PASS", verification="Sol_developer_selftest_not_independent_acceptance",
                    protected_files=len(paths), protected_bytes_unchanged=before == after,
                    before_manifest_sha256=j.sha(j.canonical(before)), after_manifest_sha256=j.sha(j.canonical(after)))
    c.write(work / "evidence.json", evidence)
    c.write(work / "commands-local.json", COMMANDS)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--observer", type=Path)
    parser.add_argument("--protect", type=Path, action="append", default=[])
    args, remaining = parser.parse_known_args()
    if args.evidence or args.observer:
        evidence_run(args.observer, args.protect)
    else:
        unittest.main(argv=[sys.argv[0], *remaining])
