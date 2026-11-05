"""Forward EOD shadow evidence. Offline, fixed rule, no execution dependencies.

The PR33 reader owns source validation. This module owns on-day selection,
immutable decisions and Owner opt-in. All Git worktrees share one canonical
source/rule journal in the primary checkout's ignored state directory.
"""
import argparse
import contextlib
import datetime as dt
from decimal import Decimal
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

if __package__:
    from . import data_snapshot as d, eod_journal as j
else:
    import data_snapshot as d
    import eod_journal as j

import stratide_paths as paths

ROOT = Path(__file__).resolve().parents[1]
RULE = dict(version="sma5-20-shadow-v1", indicator_version="sma5-20-cross-fixed100-v1",
            fast=5, slow=20, relation="fast_sum*4>slow_sum", warmup=21,
            instrument="600000.SH", price_semantics="unadjusted_cny_fen")
RULE_SHA = j.sha(j.canonical(RULE))
SAFE = dict(opening_source="BLOCKED", historical_pit="NOT_VERIFIED",
            forward_paper_allowed=False, live_allowed=False, orders=0, fills=0, nav=None,
            limitations=["CORPORATE_ACTION_PIT_NOT_VERIFIED"], authority="NO_ORDERS")
SCHEMA = 1070


def clock_ms():
    return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)


def common_root():
    return paths.common_root()


def sidecars(path):
    return [Path(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal")]


@contextlib.contextmanager
def readonly(path):
    """Never create WAL/SHM/locks, or perform hot-journal recovery on a query.

    A busy source is retried by the next once/watch tick, after its writer closes.
    PR33 leaves an empty WAL and SHM after a read. An empty WAL needs no overlay;
    immutable=1 reads its checkpointed main file without touching those sidecars.
    """
    for p in [path, *sidecars(path)]:
        j.no_links(p)
    j.require(path.is_file(), "STORE_NOT_INITIALIZED")
    wal, shm, rollback = sidecars(path)
    j.require(not rollback.exists() and (not wal.exists() or
              (wal.stat().st_size == 0 and shm.is_file())), "STORE_BUSY_OR_RECOVERY_REQUIRED")
    def fingerprint():
        return [j.sha(p.read_bytes()) if p.exists() else None for p in [path, wal, shm, rollback]]
    before = fingerprint()
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        j.require(db.execute("PRAGMA quick_check").fetchall() == [("ok",)], "STORE_INTEGRITY")
        yield db
        j.require(before == fingerprint(), "SOURCE_CHANGED_DURING_READ")
    finally:
        db.close()


def published(store):
    """Read the existing binding even when source faults prevent new observation."""
    with readonly(store.path) as db:
        j.require(db.execute("PRAGMA user_version").fetchone()[0] == d.STORE_VERSION, "STORE_SCHEMA")
        binding, saved, attempt = store.current(db)
    j.require(binding and saved, "NO_PUBLISHED_SNAPSHOT")
    content = saved["content"]
    j.require(content["instrument"] == RULE["instrument"], "SHADOW_INSTRUMENT")
    j.require(content["data_mode"] in ("synthetic_test", "forward_observed_eod"), "SHADOW_SOURCE_MODE")
    j.require(content["endpoint_version"] == j.VERSION and content["available_at_semantics"] == j.AVAILABILITY
              and content["historical_pit"] == "NOT_VERIFIED" and not content["can_execute_forward_paper"]
              and not content["live_allowed"], "SHADOW_SOURCE_CONTRACT")
    identity = {key: content[key] for key in
                ("source", "instrument", "endpoint_version", "journal_genesis", "data_mode")}
    return dict(identity=identity, binding_sha256=j.sha(j.canonical(identity)), binding=binding,
                observer_binding_sha256=j.sha(j.canonical(binding)),
                saved=saved, attempt=attempt)


def source(store):
    """PR33's published snapshot + latest sync + freshly verified original journal."""
    src = published(store)
    content, database_sha = d.read_source(src["binding"]["source"])
    j.require(j.sha(j.canonical(content)) == src["saved"]["snapshot_sha256"] and src["attempt"]
              and database_sha == src["attempt"].get("source_database_sha256"), "SOURCE_CHANGED_SINCE_SYNC")
    return src


def sequence(content, at):
    """Original on-day versions only; never join windows across a known/unknown gap.

    Freeze the first valid on-day version. A later-day revision remains diagnostic
    and cannot become yesterday's close; a same-day revision is not a new day.
    """
    selected = {}
    for version in content["versions"]:
        key = version["bar"]["trade_day"]
        times = [version[k] for k in ("observed_at", "received_at", "available_at")]
        if (version["late_backfill"] is False and all(type(t) is int and t <= at
                and j.day(t) == key and dt.datetime.fromtimestamp(t / 1000, j.ZONE).hour >= 16 for t in times)):
            selected.setdefault(key, version)
    coverage = content["coverage"]
    days, gap = [], None
    for row in coverage:
        key, state = row["source_day"], row["state"]
        if key > j.day(at):
            continue
        if state == "market_closed":
            continue
        if state != "valid_eod" or key not in selected:
            days, gap = [], dict(source_day=key, state=state if state != "valid_eod" else "NO_ON_DAY_VERSION")
        else:
            days.append(selected[key])
    # Coverage must reach the selected source day; no weekday calendar inference.
    last = content["last_valid_source_day"]
    if not days or days[-1]["bar"]["trade_day"] != last:
        days = []
    return days, gap


def readiness(src, at):
    value, attempt = src["saved"]["content"], src["attempt"]
    reasons = []
    if dt.datetime.fromtimestamp(at / 1000, j.ZONE).hour < 16:
        reasons.append("BEFORE_EOD_WINDOW")
    if value["last_valid_source_day"] != j.day(at):
        reasons.append("MISSED_OR_STALE")
    if (not attempt or attempt["state"] != "succeeded" or attempt["error_code"] is not None
            or attempt["blockers"] or attempt.get("journal_head") != value["journal_head"]):
        reasons.append("SNAPSHOT_SYNC_NOT_SUCCEEDED")
        if attempt:
            reasons.extend(attempt["blockers"])
            if attempt["error_code"]:
                reasons.append(attempt["error_code"])
    if attempt and (attempt.get("finished_at") is None or not (0 < attempt["started_at"] <= attempt["finished_at"] <= at)
                    or at - attempt["started_at"] > d.MAX_SYNC_AGE_MS):
        reasons.append("SNAPSHOT_SYNC_STALE_OR_CLOCK")
    if value["as_of_journal_event_at"] > at or any(v["available_at"] > at or v["received_at"] > at
                                                  or v["observed_at"] > at for v in value["versions"]):
        reasons.append("FUTURE_SOURCE_VERSION")
    reasons.extend(value["blockers"])
    days, gap = sequence(value, at)
    if gap:
        reasons.append("CALENDAR_UNKNOWN" if gap["state"] == "calendar_unknown" else "FORWARD_COVERAGE_GAP")
    if not days or days[-1]["bar"]["trade_day"] != j.day(at):
        reasons.append("NO_VALID_CURRENT_ON_DAY_EOD")
    if len(days) < RULE["warmup"]:
        reasons.append("INSUFFICIENT_FORWARD_WARMUP")
    return dict(source_day=value["last_valid_source_day"], valid_on_day_count=value["on_day_valid_eod_days"],
                continuous_on_day_count=len(days), required_on_day_count=21,
                blockers=list(dict.fromkeys(reasons)), gap=gap, coverage=value["coverage"], gaps=value["gaps"],
                warnings=value["warnings"], latest_sync=attempt, as_of=value["as_of_journal_event_at"],
                journal_head=value["journal_head"], available_at_semantics=j.AVAILABILITY), days[-21:]


def calculate(days):
    closes = [v["bar"]["close_fen"] for v in days]
    j.require(all(type(c) is int and c > 0 for c in closes), "INVALID_CLOSE_UNIT")
    if len(closes) < 21:
        return dict(result="INSUFFICIENT_FORWARD_WARMUP", arithmetic=None)
    previous_fast, previous_slow = sum(closes[-6:-1]), sum(closes[-21:-1])
    current_fast, current_slow = sum(closes[-5:]), sum(closes[-20:])
    before, after = previous_fast * 4 > previous_slow, current_fast * 4 > current_slow
    result = "NO_CROSS" if before == after else "UP_CROSS" if after else "DOWN_CROSS"
    return dict(result=result, arithmetic=dict(previous_fast_sum_fen=previous_fast,
                previous_slow_sum_fen=previous_slow, current_fast_sum_fen=current_fast,
                current_slow_sum_fen=current_slow, previous_above=before, current_above=after))


def audit_input(material):
    """Revalidate saved evidence and independently check arithmetic using Decimal."""
    content, at = material["snapshot_content"], material["decision_at"]
    j.require(j.sha(j.canonical(content)) == material["input_snapshot_sha256"], "SHADOW_INPUT_SHA")
    # Saved content includes every original version and journal chain commitment.
    j.require(content["journal_head"] == material["journal_head"] and material["rule"] == RULE
              and material["rule_sha256"] == RULE_SHA, "SHADOW_INPUT_CONTRACT")
    identity = {key: content[key] for key in
                ("source", "instrument", "endpoint_version", "journal_genesis", "data_mode")}
    j.require(material["binding_sha256"] == j.sha(j.canonical(identity)), "SHADOW_BINDING")
    src = dict(saved=dict(content=content), attempt=material["latest_sync"])
    ready, days = readiness(src, at)
    j.require(ready == material["readiness"] and days == material["window"], "SHADOW_WINDOW")
    evidence = []
    for v in days:
        evidence.append(dict(source_day=v["bar"]["trade_day"], sequence=v["sequence"],
            close_source_sha256=j.sha(j.canonical(v["bar"])),
            raw_sha256=[r for r in content["raw_sha256"] if r["sequence"] == v["sequence"]],
            **{k: v[k] for k in ("observed_at", "received_at", "available_at", "revision_of")}))
    j.require(evidence == material["window_evidence"] and material["source_day"] == ready["source_day"]
              and material["as_of"] == content["as_of_journal_event_at"], "SHADOW_INPUT_EVIDENCE")
    j.require(not [r for r in ready["blockers"] if r != "INSUFFICIENT_FORWARD_WARMUP"], "SHADOW_TIME_OR_COVERAGE")
    expected = dict(result="INSUFFICIENT_FORWARD_WARMUP", arithmetic=None)
    if len(days) == 21:
        closes = [Decimal(v["bar"]["close_fen"]) for v in days]
        previous = sum(closes[-6:-1]) / 5 > sum(closes[-21:-1]) / 20
        current = sum(closes[-5:]) / 5 > sum(closes[-20:]) / 20
        expected = dict(result="NO_CROSS" if previous == current else "UP_CROSS" if current else "DOWN_CROSS",
                        arithmetic=dict(previous_fast_sum_fen=int(sum(closes[-6:-1])),
                            previous_slow_sum_fen=int(sum(closes[-21:-1])), current_fast_sum_fen=int(sum(closes[-5:])),
                            current_slow_sum_fen=int(sum(closes[-20:])), previous_above=previous, current_above=current))
    j.require(expected == material["calculation"], "SHADOW_ARITHMETIC")
    j.require(j.sha(j.canonical(expected)) == material["calculation_commitment_sha256"], "SHADOW_ARITHMETIC_SHA")
    expected_mode = ("SYNTHETIC_TEST_SHADOW" if content["data_mode"] == "synthetic_test" else
                     "SHADOW_FORWARD_OBSERVED" if len(days) == 21 else "FORWARD_WARMUP_ONLY")
    j.require(material["mode"] == expected_mode and material["permissions"] == SAFE, "SHADOW_AUTHORITY")


def public_input(material):
    """No raw price or SMA value in default CLI output; local SQLite holds inputs."""
    return {key: material[key] for key in ("mode", "source_day", "binding_sha256", "observer_binding_sha256",
            "rule", "rule_sha256", "input_snapshot_sha256", "journal_head", "decision_at", "as_of",
            "readiness", "window_evidence", "calculation_commitment_sha256", "permissions")} | dict(
                result=material["calculation"]["result"], arithmetic_check="DECIMAL_RECOMPUTED",
                local_input_commitment_sha256=j.sha(j.canonical(material)))


class Shadow:
    def __init__(self, store, *, clock=clock_ms, fault=lambda point: None):
        self.store, self.clock, self.fault = d.Store(store), clock, fault
        self.src = published(self.store)
        self.key = j.sha(j.canonical(dict(binding=self.src["identity"], rule_sha256=RULE_SHA)))
        self.root = common_root() / "state/forward-shadow" / self.key
        self.path = self.root / "shadow.sqlite"
        for path in [self.root, self.path, self.root / "writer.lock", *sidecars(self.path)]:
            j.no_links(path)

    @contextlib.contextmanager
    def write(self):
        # Opening a hot rollback journal is allowed only in the writer path.
        db = sqlite3.connect(self.path, timeout=0)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        finally:
            db.close()

    def append(self, db, kind, at, data, event_key=None):
        row = db.execute("SELECT seq,digest,payload FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        seq, previous = (row[0] + 1, row[1]) if row else (0, "")
        j.require(row is None or at >= j.loads(row[2])["at"], "SHADOW_CLOCK_REGRESSED")
        payload = dict(kind=kind, at=at, data=data)
        encoded = j.canonical(payload).decode()
        digest = j.sha(j.canonical([SCHEMA, self.key, previous, seq, event_key, payload]))
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (seq, event_key, encoded, digest, previous))

    def journal(self, db):
        j.require(db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA, "SHADOW_SCHEMA")
        entries, pending, enabled, previous, observations = [], {}, False, "", []
        for seq, event_key, payload, digest, prev in db.execute("SELECT * FROM events ORDER BY seq"):
            value = j.loads(payload)
            j.require(seq == len(entries) and prev == previous and digest == j.sha(j.canonical(
                [SCHEMA, self.key, previous, seq, event_key, value])), "SHADOW_CHAIN")
            j.require(not entries or value["at"] >= entries[-1]["at"], "SHADOW_CLOCK_REGRESSED")
            kind, data = value["kind"], value["data"]
            if seq == 0:
                j.require(kind == "initialized" and data == dict(identity=self.src["identity"], rule=RULE), "SHADOW_BINDING")
            elif kind in ("enabled", "disabled"):
                enabled = kind == "enabled"
            elif kind == "run_started":
                pending[seq] = value
            elif kind in ("interrupted", "blocked", "observation", "duplicate"):
                j.require(data["run"] in pending, "SHADOW_RUN_ORDER")
                del pending[data["run"]]
                if kind == "observation":
                    material = j.loads(db.execute("SELECT content FROM inputs WHERE sha=?", (data["input_sha256"],)).fetchone()[0])
                    j.require(j.sha(j.canonical(material)) == data["input_sha256"], "SHADOW_INPUT_SHA")
                    audit_input(material)
                    j.require(event_key == self.event_key(material["source_day"]) and enabled
                              and value["at"] == material["decision_at"], "SHADOW_EVENT_IDENTITY")
                    observations.append(dict(event_id=event_key, evidence_sha256=data["input_sha256"], material=material))
            else:
                j.require(False, "SHADOW_EVENT_KIND")
            entries.append(value)
            previous = digest
        j.require(entries, "SHADOW_EMPTY")
        return dict(entries=entries, pending=pending, enabled=enabled, head=previous, observations=observations)

    def event_key(self, day):
        return j.sha(j.canonical([self.key, day]))

    def init(self):
        self.src = source(self.store)
        j.require(not self.root.exists(), "SHADOW_ALREADY_INITIALIZED")
        j.require(paths.ignored(self.path), "SHADOW_MUST_BE_GITIGNORED")
        self.root.mkdir(parents=True, exist_ok=False)
        with d.writer(self.root / "writer.lock"), self.write() as db:
            db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,event_key TEXT UNIQUE,payload TEXT NOT NULL,digest TEXT NOT NULL,previous TEXT NOT NULL)")
            db.execute("CREATE TABLE inputs(sha TEXT PRIMARY KEY,content TEXT NOT NULL)")
            for table in ("events", "inputs"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END")
            db.execute(f"PRAGMA user_version={SCHEMA}")
            self.append(db, "initialized", self.clock(), dict(identity=self.src["identity"], rule=RULE))
        return dict(state="INITIALIZED_OFF", binding_sha256=self.src["binding_sha256"], **SAFE)

    def recover(self, db, at):
        state = self.journal(db)
        j.require(at >= state["entries"][-1]["at"], "SHADOW_CLOCK_REGRESSED")
        for run in state["pending"]:
            self.append(db, "interrupted", at, dict(run=run, reason="PROCESS_INTERRUPTED_NOT_COMMITTED"))
        return state

    def control(self, enabled):
        j.require(self.path.is_file(), "STORE_NOT_INITIALIZED")
        with d.writer(self.root / "writer.lock"), self.write() as db:
            at = self.clock()
            self.recover(db, at)
            self.append(db, "enabled" if enabled else "disabled", at, {})
        return dict(state="ENABLED" if enabled else "DISABLED", **SAFE)

    def once(self):
        j.require(self.path.is_file(), "STORE_NOT_INITIALIZED")
        with d.writer(self.root / "writer.lock"):
            with self.write() as db:
                at = self.clock()
                state = self.recover(db, at)
                if not state["enabled"]:
                    return dict(state="SKIPPED", reason="OWNER_DISABLED", **SAFE)
                run = db.execute("SELECT count(*) FROM events").fetchone()[0]
                self.append(db, "run_started", at, {})
            self.fault("before_intent")
            try:
                self.src = source(self.store)
                at = self.clock()
                ready, days = readiness(self.src, at)
                j.require(not [r for r in ready["blockers"] if r != "INSUFFICIENT_FORWARD_WARMUP"],
                          next(iter(ready["blockers"]), "SOURCE_BLOCKED"))
                # Current-day revision/refresh never supersedes an already frozen day.
                with readonly(self.path) as db:
                    state = self.journal(db)
                existing = next((o for o in state["observations"] if
                                 o["material"]["source_day"] == ready["source_day"]), None)
                if existing:
                    with self.write() as db:
                        self.append(db, "duplicate", at, dict(run=run, source_day=ready["source_day"],
                                    latest_snapshot_sha256=self.src["saved"]["snapshot_sha256"], blockers=ready["blockers"],
                                    reason="ALREADY_FROZEN_NO_RECOMPUTE"))
                    return dict(state="ALREADY_FROZEN", reason="ALREADY_FROZEN_NO_RECOMPUTE",
                                observation=public_input(existing["material"]), source_diagnostics=ready, **SAFE)
                content, saved = self.src["saved"]["content"], self.src["saved"]
                calculation = calculate(days)
                mode = ("SYNTHETIC_TEST_SHADOW" if content["data_mode"] == "synthetic_test" else
                        "SHADOW_FORWARD_OBSERVED" if len(days) == 21 else "FORWARD_WARMUP_ONLY")
                evidence = []
                for v in days:
                    refs = [r for r in content["raw_sha256"] if r["sequence"] == v["sequence"]]
                    evidence.append(dict(source_day=v["bar"]["trade_day"], sequence=v["sequence"],
                        close_source_sha256=j.sha(j.canonical(v["bar"])), raw_sha256=refs,
                        **{k: v[k] for k in ("observed_at", "received_at", "available_at", "revision_of")}))
                material = dict(mode=mode, source_day=ready["source_day"], binding_sha256=self.src["binding_sha256"],
                    observer_binding_sha256=self.src["observer_binding_sha256"], rule=RULE, rule_sha256=RULE_SHA,
                    input_snapshot_sha256=saved["snapshot_sha256"], journal_head=content["journal_head"],
                    decision_at=at, as_of=content["as_of_journal_event_at"], snapshot_content=content,
                    latest_sync=self.src["attempt"], window=days, window_evidence=evidence, readiness=ready,
                    calculation=calculation, calculation_commitment_sha256=j.sha(j.canonical(calculation)), permissions=SAFE)
                audit_input(material)
                # Capture actual time inside the persistence transaction; never
                # turn a computation crossing midnight into yesterday's decision.
                with self.write() as db:
                    committed_at = self.clock()
                    j.require(j.day(committed_at) == ready["source_day"] and committed_at >= at, "MISSED_OR_STALE")
                    material["decision_at"] = committed_at
                    audit_input(material)
                    key = j.sha(j.canonical(material))
                    db.execute("INSERT OR IGNORE INTO inputs VALUES(?,?)", (key, j.canonical(material).decode()))
                    self.append(db, "observation", committed_at, dict(run=run, input_sha256=key), self.event_key(ready["source_day"]))
                    self.fault("before_persist")
                self.fault("after_persist")
                return dict(state="COMMITTED", observation=public_input(material), **SAFE)
            except j.Rejected as error:
                with self.write() as db:
                    self.append(db, "blocked", self.clock(), dict(run=run, reason=str(error)))
                return dict(state="BLOCKED", reason=str(error), **SAFE)

    def query(self, action):
        with readonly(self.path) as db:
            state = self.journal(db)
        ready, _ = readiness(self.src, self.clock())
        source_verified = True
        try:
            current = source(self.store)
            j.require(current["identity"] == self.src["identity"], "SHADOW_BINDING")
            # Every frozen snapshot must be an original journal prefix, and its
            # normalized versions must still match the verified original rows.
            for observation in state["observations"]:
                old = observation["material"]["snapshot_content"]
                new = current["saved"]["content"]
                j.require(new["journal_chain"][:len(old["journal_chain"])] == old["journal_chain"]
                          and new["versions"][:len(old["versions"])] == old["versions"]
                          and new["raw_sha256"][:len(old["raw_sha256"])] == old["raw_sha256"], "SHADOW_ORIGINAL_PREFIX_CHANGED")
        except j.Rejected as error:
            ready["blockers"].insert(0, str(error))
            source_verified = False
        observations = [dict(event_id=o["event_id"], evidence_sha256=o["evidence_sha256"],
                             **public_input(o["material"])) for o in state["observations"]]
        result = dict(state="VERIFIED", enabled=state["enabled"], binding_sha256=self.src["binding_sha256"],
                      rule=RULE, rule_sha256=RULE_SHA, journal_head=state["head"], event_count=len(state["entries"]),
                      observation_count=len(observations), signal_count=sum(o["result"] in
                        ("UP_CROSS", "DOWN_CROSS", "NO_CROSS") for o in observations),
                      source_diagnostics=ready, interrupted_or_pending_runs=list(state["pending"]),
                      current_input_snapshot_sha256=self.src["saved"]["snapshot_sha256"], **SAFE)
        if action in ("history", "verify", "report"):
            result["observations"] = observations
            result["diagnostics"] = [e for e in state["entries"] if e["kind"] in ("blocked", "interrupted", "duplicate")]
        if action in ("verify", "report"):
            result["verification"] = "LOCAL_SHA_CHAIN_TIME_WINDOW_AND_DECIMAL_CHECKED_NOT_EXTERNAL_PIT_CERTIFICATION"
        result["source_verified"] = source_verified
        if not source_verified:
            result["state"] = "FROZEN_EVIDENCE_VERIFIED_SOURCE_BLOCKED"
        return result


def main(argv=None, *, clock=clock_ms, fault=lambda point: None, wait=time.sleep):
    parser = argparse.ArgumentParser(description="离线 Forward EOD Shadow；NO_ORDERS / NO_FILLS / NO_NAV")
    parser.add_argument("--store", required=True, help="已有 PR33 store 的受限名称")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "enable", "disable", "once", "status", "history", "verify", "report"):
        commands.add_parser(command)
    watch = commands.add_parser("watch")
    watch.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        service = Shadow(args.store, clock=clock, fault=fault)
        if args.command == "watch":
            j.require(60 <= args.interval_seconds <= 3600, "WATCH_INTERVAL_INVALID")
            while True:
                try:
                    result = service.once()
                except j.Rejected as error:
                    result = dict(state="BLOCKED", reason=str(error), **SAFE)
                print(j.canonical(result).decode(), flush=True)
                wait(args.interval_seconds)
        elif args.command == "init":
            result = service.init()
        elif args.command in ("enable", "disable"):
            result = service.control(args.command == "enable")
        elif args.command == "once":
            result = service.once()
        else:
            result = service.query(args.command)
        print(j.canonical(result).decode())
        return 3 if result["state"] in ("BLOCKED", "SKIPPED") else 0
    except KeyboardInterrupt:
        return 130
    except (j.Rejected, OSError, sqlite3.Error, ValueError, KeyError, TypeError, OverflowError) as error:
        code = str(error) if isinstance(error, j.Rejected) else "SHADOW_STORE_OR_SOURCE_INVALID"
        print(j.canonical(dict(state="BLOCKED", reason=code, **SAFE)).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
