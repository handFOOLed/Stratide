"""Versioned forward research receipts, separate from historical/trading authority.

Original observer, PR33 and PR38 are read-only. Only this new ignored store is
written. The original Agent remains the sole task queue and budget authority.
"""
import argparse
import contextlib
from dataclasses import dataclass
import datetime as dt
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import corporate_actions as ca
import data_snapshot as d
import eod_journal as j
import forward_evidence as f
import shadow as s

ROOT = Path(__file__).resolve().parents[1]
VERSION = "forward-research-readiness-v1"
SCHEMA = 1110
MAX_STORE = 64 * 1024 * 1024
SAFE = dict(restriction="RESEARCH_ONLY", eligibility="ELIGIBILITY_DENIED",
            historical_pit_status="NOT_VERIFIED", opening_source="BLOCKED",
            can_execute_forward_paper=False, live_allowed=False)


def digest(value):
    return j.sha(j.canonical(value))


@dataclass(frozen=True)
class SnapshotReference:
    path: Path

    def current(self, db):
        return d.Store.current(self, db)


def snapshot_ref(path):
    path = Path(path).absolute()
    if path.is_dir():
        path /= "snapshots.sqlite"
    j.no_links(path)
    j.require(path.name == "snapshots.sqlite" and path.is_file() and path.stat().st_size <= MAX_STORE,
              "READINESS_SNAPSHOT_PATH_OR_SIZE")
    return SnapshotReference(path.resolve(strict=True))


def source(path):
    ref = snapshot_ref(path)
    src = s.published(ref)
    if src["binding"]["source"]["kind"] == "authorized_observer":
        observer = Path(src["binding"]["source"]["path"])
        j.no_links(observer)
        j.require(observer.is_file() and observer.stat().st_size <= MAX_STORE, "OBSERVER_SIZE_OR_MISSING")
    actual, database_sha = d.read_source(src["binding"]["source"])
    j.require(digest(actual) == src["saved"]["snapshot_sha256"] and src["attempt"]
              and database_sha == src["attempt"].get("source_database_sha256"), "SOURCE_CHANGED_SINCE_SYNC")
    return src


def failure_code(error):
    return str(error) if isinstance(error, j.Rejected) else "READINESS_SOURCE_UNAVAILABLE"


def window_readiness(src, at):
    ready, window = s.readiness(src, at)
    # An old collection gap remains visible, but 21 later continuous sessions
    # can form a new window. Do not change PR48's original shadow contract.
    if len(window) == 21 and ready["gap"] and ready["gap"]["source_day"] < window[0]["bar"]["trade_day"]:
        ready["blockers"] = [reason for reason in ready["blockers"] if reason != "FORWARD_COVERAGE_GAP"]
    return ready, window


def assess(src, captures, at, source_error=None, references=None, evidence_head=None):
    """Deterministic, daily audit; absence is UNKNOWN, never a zero-event claim."""
    value = src["saved"]["content"]
    ready, window = window_readiness(src, at)
    reasons = list(ready["blockers"])
    mode = value["data_mode"]
    if mode not in ("synthetic_test", "forward_observed_eod"):
        reasons.append("HISTORICAL_REPLAY_EX_POST_ONLY")
    if len(window) < 21:
        reasons.append("INSUFFICIENT_FORWARD_HISTORY")
    if source_error:
        reasons.append(source_error)
    relevant = [v for v in value["versions"] if window and v["bar"]["trade_day"] >= window[0]["bar"]["trade_day"]]
    if any(v["revision_of"] is not None or v["late_backfill"] for v in relevant):
        reasons.append("REVISED_OR_LATE_SOURCE_REJECTED")
    days, previous = [], None
    for row in window:
        day = row["bar"]["trade_day"]
        daily = f.coverage_for(day, previous or day, captures, at)
        observed, received, available = [row[k] for k in ("observed_at", "received_at", "available_at")]
        if not (0 < observed <= received <= available <= value["as_of_journal_event_at"] <= at
                and all(j.day(t) == day for t in (observed, received, available))):
            daily["blockers"].append("WINDOW_TIME_INVALID")
        try:
            # The existing expert owns exact units/OHLC and label-leak rules.
            import multimodal_experts as e
            bar = row["bar"]
            expected = {"trade_day", "open_fen", "high_fen", "low_fen", "close_fen",
                        "volume_shares", "source_volume_unit", "price_semantics"}
            j.require(set(bar) == expected and bar["price_semantics"] == "unadjusted_cny_fen"
                      and bar["source_volume_unit"] == "hand_100_shares", "WINDOW_UNITS_OR_LABEL_LEAK")
            if len(window) == 21:
                e.closes(window)
        except j.Rejected as error:
            daily["blockers"].append(str(error))
        raw = [r for r in value["raw_sha256"] if r["sequence"] == row["sequence"]]
        daily.update(sequence=row["sequence"], bar_sha256=digest(row["bar"]), raw_sha256=raw,
                     **{k: row[k] for k in ("observed_at", "received_at", "available_at", "revision_of", "late_backfill")})
        reasons.extend(daily["blockers"])
        days.append(daily)
        previous = day
    if not captures:
        reasons.extend(("ACTION_FEED_UNAVAILABLE", "COVERAGE_NOT_ATTESTED"))
    for ref in references or []:
        if ref.get("error_code"):
            reasons.append(ref["error_code"])
        for event in ref.get("events", []):
            facts = event["facts"]
            ex_day = (facts.get("ex_date") or "").replace("-", "")
            if days and days[0]["source_day"] <= ex_day <= days[-1]["source_day"]:
                reasons.extend(("EVENT_FACT_PARTIAL", "PIT_NOT_PROVEN", "PRICE_SEMANTICS_UNSAFE"))
    blockers = sorted(set(reasons))
    return dict(contract=VERSION, input_mode=mode, instrument=value["instrument"],
                source_identity_sha256=digest(src["identity"]),
                observer_binding_sha256=digest(src["binding"]),
                input_snapshot_sha256=src["saved"]["snapshot_sha256"],
                journal_head=value["journal_head"], source_day=value["last_valid_source_day"],
                evidence_head_sha256=evidence_head,
                source_evidence_status=("ON_DAY_COVERAGE_VERIFIED_LOCALLY" if days and all(
                    r["status"] == "NO_ACTION_WITH_VERIFIED_COVERAGE" and not r["blockers"] for r in days)
                    else "FACTS_PARTIAL" if any(ref.get("events") for ref in references or []) else "UNKNOWN"),
                forward_research_readiness="BLOCKED" if blockers else "ALLOW_RESEARCH_ONLY",
                required_sessions=21, continuous_sessions=ready["continuous_on_day_count"],
                real_on_day_sessions=value["on_day_valid_eod_days"] if mode == "forward_observed_eod" else 0,
                daily_evidence=days, calendar_coverage=value["coverage"], gaps=value["gaps"],
                warnings=value["warnings"], blockers=blockers,
                corporate_action_references=references or [],
                assurance="LOCAL_OPERATOR_REVIEW_AND_ACQUISITION; HASHES_DO_NOT_AUTHENTICATE_PUBLISHER_OR_CLOCK",
                **SAFE)


class Store:
    def __init__(self, name, *, clock=s.clock_ms, fault=lambda point: None):
        ca.identifier(name)
        self.name, self.clock, self.fault = name, clock, fault
        self.root = ROOT / "state/forward-readiness" / name
        self.path = self.root / "readiness.sqlite"
        for path in (self.path, self.root / "writer.lock"):
            j.no_links(path)

    @contextlib.contextmanager
    def connect(self, write=False):
        j.no_links(self.path)
        if not write:
            j.require(self.path.is_file() and self.path.stat().st_size <= MAX_STORE, "READINESS_STORE_MISSING_OR_SIZE")
            with s.readonly(self.path) as db:
                j.require(db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA, "READINESS_SCHEMA")
                yield db
            return
        j.require(self.path.is_file() and self.path.stat().st_size <= MAX_STORE, "READINESS_STORE_MISSING_OR_SIZE")
        db = sqlite3.connect(self.path, timeout=0)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            j.require(db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA, "READINESS_SCHEMA")
            j.require(db.execute("PRAGMA quick_check").fetchall() == [("ok",)], "READINESS_INTEGRITY")
            yield db
            self.fault("before_commit")
            db.commit()
            self.fault("after_commit")
        finally:
            db.close()

    def init(self, snapshot, bundle=None):
        ref = snapshot_ref(snapshot)
        src = s.published(ref)
        config = dict(schema_version=1, contract=VERSION, name=self.name, snapshot_path=str(ref.path),
                      source_identity_sha256=digest(src["identity"]), observer_binding_sha256=digest(src["binding"]),
                      corporate_action_bundle=str(Path(bundle).absolute()) if bundle else None)
        if bundle:
            ca.status(Path(bundle))
        config["config_sha256"] = digest(config)
        j.require(not self.root.exists(), "NEW_READINESS_DIRECTORY_REQUIRED")
        j.require(not ref.path.is_relative_to(self.root), "READINESS_SOURCE_OVERLAP")
        self.root.parent.mkdir(parents=True, exist_ok=True)
        j.require(subprocess.run(["git", "check-ignore", "--quiet", "--", str(self.path)], cwd=ROOT).returncode == 0,
                  "READINESS_STATE_MUST_BE_GITIGNORED")
        # Atomic directory publication; interrupted staging never looks initialized.
        stage = self.root.with_name("." + self.name + ".init-" + os.urandom(6).hex())
        stage.mkdir()
        with contextlib.closing(sqlite3.connect(stage / "readiness.sqlite")) as db:
            db.executescript("PRAGMA synchronous=FULL; CREATE TABLE control(config TEXT NOT NULL,head TEXT,latest TEXT,clock INTEGER NOT NULL);"
                             "CREATE TABLE blobs(sha TEXT PRIMARY KEY,content BLOB NOT NULL);"
                             "CREATE TABLE evidence(seq INTEGER PRIMARY KEY,sha TEXT UNIQUE,payload TEXT NOT NULL);"
                             "CREATE TABLE receipts(sha TEXT PRIMARY KEY,content TEXT NOT NULL);")
            db.execute(f"PRAGMA user_version={SCHEMA}")
            db.execute("INSERT INTO control VALUES(?,NULL,NULL,?)", (j.canonical(config).decode(), self.clock()))
            db.commit()
        os.rename(stage, self.root)
        return dict(state="INITIALIZED", name=self.name, forward_research_readiness="BLOCKED", **SAFE)

    def control(self, db):
        row = db.execute("SELECT config,head,latest,clock FROM control").fetchone()
        j.require(row is not None, "READINESS_CONTROL")
        config = j.loads(row[0])
        f.keys(config, ("schema_version", "contract", "name", "snapshot_path", "source_identity_sha256",
                        "observer_binding_sha256", "corporate_action_bundle", "config_sha256"), "READINESS_CONFIG")
        j.require(config["config_sha256"] == digest({k: v for k, v in config.items() if k != "config_sha256"})
                  and config["schema_version"] == 1 and config["contract"] == VERSION
                  and config["name"] == self.name, "READINESS_CONFIG_SHA")
        return config, row[1], row[2], row[3]

    def blob(self, db, key):
        ca.digest(key)
        row = db.execute("SELECT content FROM blobs WHERE sha=?", (key,)).fetchone()
        j.require(row and 0 < len(row[0]) <= ca.MAX_FILE and j.sha(row[0]) == key, "READINESS_BLOB_SHA")
        return row[0]

    def put_blob(self, db, raw):
        j.require(0 < len(raw) <= ca.MAX_FILE, "READINESS_BLOB_SIZE")
        key = j.sha(raw)
        db.execute("INSERT OR IGNORE INTO blobs VALUES(?,?)", (key, raw))
        j.require(self.blob(db, key) == raw, "READINESS_BLOB_SHA")
        return key

    def evidence(self, db, head):
        config, current, _, _ = self.control(db)
        rows = db.execute("SELECT seq,sha,payload FROM evidence ORDER BY seq").fetchall()
        j.require(len(rows) <= f.MAX_RECORDS, "READINESS_EVIDENCE_LIMIT")
        previous, high, contract, captures, found = None, 0, None, [], head is None
        for expected_seq, (seq, key, raw) in enumerate(rows, 1):
            record = j.loads(raw)
            j.require(seq == expected_seq and record["sequence"] == seq and record["previous"] == previous
                      and digest(record) == key and record["acquired_at"] >= high, "READINESS_EVIDENCE_CHAIN")
            previous, high = key, record["acquired_at"]
            if found:
                continue
            f.keys(record, ("sequence", "previous", "acquired_at", "kind", "content"), "READINESS_EVIDENCE_SCHEMA")
            content = record["content"]
            if record["kind"] == "source_contract":
                f.keys(content, ("contract", "document_sha256"), "READINESS_CONTRACT_SCHEMA")
                contract = f.SourceContract.parse(content["contract"], self.blob(db, content["document_sha256"]),
                                                 config_mode(config))
            else:
                j.require(record["kind"] == "coverage" and contract, "READINESS_EVIDENCE_KIND")
                f.keys(content, ("raw_sha256", "contract_sha256", "input_snapshot_sha256", "source_day"),
                       "READINESS_CAPTURE_SCHEMA")
                j.require(content["contract_sha256"] == digest(contract.__dict__), "READINESS_CONTRACT_CHANGED")
                payload = f.Coverage.parse(j.loads(self.blob(db, content["raw_sha256"])), contract, "600000.SH")
                j.require(payload.as_of_day == content["source_day"], "READINESS_CAPTURE_DAY")
                self.capture_snapshot(config, content, record["acquired_at"])
                captures.append(dict(sha256=key, acquired_at=record["acquired_at"], payload=payload.__dict__, **content))
            if key == head:
                found = True
        j.require(found and previous == current, "READINESS_EVIDENCE_HEAD")
        return captures, contract

    def capture_snapshot(self, config, content, acquired):
        ref = snapshot_ref(config["snapshot_path"])
        with s.readonly(ref.path) as original:
            row = original.execute("SELECT content,verified_at FROM snapshots WHERE sha=?",
                                   (content["input_snapshot_sha256"],)).fetchone()
        j.require(row and j.sha(row[0].encode()) == content["input_snapshot_sha256"], "CAPTURE_ORIGINAL_SNAPSHOT_SHA")
        snapshot = j.loads(row[0])
        identity = {k: snapshot[k] for k in ("source", "instrument", "endpoint_version", "journal_genesis", "data_mode")}
        j.require(digest(identity) == config["source_identity_sha256"]
                  and snapshot["last_valid_source_day"] == content["source_day"]
                  and 0 < snapshot["as_of_journal_event_at"] <= row[1] <= acquired,
                  "CAPTURE_SNAPSHOT_CAUSAL_ORDER")

    def append(self, db, kind, content, at):
        _, head, _, high = self.control(db)
        j.require(at >= high, "READINESS_CLOCK_REGRESSED")
        count = db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        j.require(count < f.MAX_RECORDS, "READINESS_EVIDENCE_LIMIT")
        record = dict(sequence=count + 1, previous=head, acquired_at=at, kind=kind, content=content)
        key = digest(record)
        db.execute("INSERT INTO evidence VALUES(?,?,?)", (count + 1, key, j.canonical(record).decode()))
        db.execute("UPDATE control SET head=?,clock=?", (key, at))
        return key

    def configure_source(self, manifest):
        with d.writer(self.root / "writer.lock"), self.connect(write=True) as db:
            config, head, _, _ = self.control(db)
            captures, old = self.evidence(db, head)
            value, document = f.load_contract(manifest, config_mode(config))
            if old and old.__dict__ == value:
                return dict(state="REUSED_SOURCE_CONTRACT", contract_sha256=digest(value))
            if old:
                j.require(old.source_id == value["source_id"], "ACTION_SOURCE_IDENTITY_CHANGED")
                j.require(old.version != value["version"], "ACTION_CONTRACT_VERSION_CONFLICT")
            key = self.put_blob(db, document)
            evidence = self.append(db, "source_contract", dict(contract=value, document_sha256=key), self.clock())
        return dict(state="SOURCE_CONTRACT_RECORDED", evidence_sha256=evidence, contract_sha256=digest(value), **SAFE)

    def capture(self, payload):
        raw = ca.read_file(Path(payload))
        with d.writer(self.root / "writer.lock"), self.connect(write=True) as db:
            config, head, _, high = self.control(db)
            at = self.clock()
            j.require(at >= high, "READINESS_CLOCK_REGRESSED")
            captures, contract = self.evidence(db, head)
            j.require(contract, "ACTION_FEED_UNAVAILABLE")
            src = source(config["snapshot_path"])
            self.binding(config, src)
            value = f.Coverage.parse(j.loads(raw), contract, src["saved"]["content"]["instrument"])
            j.require(value.as_of_day == src["saved"]["content"]["last_valid_source_day"], "ACTION_SNAPSHOT_DAY_MISMATCH")
            j.require(src["saved"]["verified_at"] <= at and src["saved"]["content"]["as_of_journal_event_at"] <= at,
                      "CAPTURE_SNAPSHOT_CAUSAL_ORDER")
            duplicate = next((r for r in captures if r["raw_sha256"] == j.sha(raw)
                              and r["contract_sha256"] == digest(contract.__dict__)), None)
            if duplicate:
                return dict(state="REUSED_COVERAGE", evidence_sha256=duplicate["sha256"], acquired_at=duplicate["acquired_at"], **SAFE)
            if value.supersedes:
                j.require(any(r["payload"]["revision"] == value.supersedes
                              and r["payload"]["as_of_day"] == value.as_of_day for r in captures), "ACTION_REVISION_ANCESTOR_MISSING")
            key = self.put_blob(db, raw)
            evidence = self.append(db, "coverage", dict(raw_sha256=key, contract_sha256=digest(contract.__dict__),
                                   input_snapshot_sha256=src["saved"]["snapshot_sha256"], source_day=value.as_of_day), at)
        return dict(state="COVERAGE_RECORDED", evidence_sha256=evidence, acquired_at=at, **SAFE)

    def binding(self, config, src):
        j.require(digest(src["identity"]) == config["source_identity_sha256"]
                  and digest(src["binding"]) == config["observer_binding_sha256"], "READINESS_SOURCE_IDENTITY_CHANGED")

    def references(self, config):
        if not config["corporate_action_bundle"]:
            return []
        try:
            value = ca.status(Path(config["corporate_action_bundle"]))
            return [{k: value[k] for k in ("bundle_sha256", "event_fact_status", "historical_pit_status",
                                           "obtained_at", "documents", "events")}]
        except (OSError, ValueError, KeyError, TypeError):
            return [dict(error_code="PR38_EVIDENCE_INVALID")]

    def audit(self):
        with d.writer(self.root / "writer.lock"), self.connect(write=True) as db:
            config, head, latest, high = self.control(db)
            at = self.clock()
            j.require(at >= high, "READINESS_CLOCK_REGRESSED")
            captures, _ = self.evidence(db, head)
            src = s.published(snapshot_ref(config["snapshot_path"]))
            source_error = None
            try:
                self.binding(config, src)
                source(config["snapshot_path"])
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                source_error = failure_code(error)
            result = assess(src, captures, at, source_error, self.references(config), head)
            basis = digest(dict(result=result, latest_sync=src["attempt"]))
            if latest:
                old = self.receipt(db, latest)
                if old["basis_sha256"] == basis:
                    db.execute("UPDATE control SET clock=?", (at,))
                    return public(old, latest)
            receipt = dict(schema_version=1, name=self.name, config_sha256=config["config_sha256"],
                           decision_at=at, evidence_head_sha256=head, basis_sha256=basis,
                           source_error=source_error, result=result, snapshot_content=src["saved"]["content"],
                           snapshot_binding=src["binding"],
                           latest_sync=src["attempt"])
            key = digest(receipt)
            db.execute("INSERT OR IGNORE INTO receipts VALUES(?,?)", (key, j.canonical(receipt).decode()))
            self.fault("before_publish")
            db.execute("UPDATE control SET latest=?,clock=?", (key, at))
        return public(receipt, key)

    def receipt(self, db, key):
        ca.digest(key)
        row = db.execute("SELECT content FROM receipts WHERE sha=?", (key,)).fetchone()
        j.require(row and 0 < len(row[0].encode()) <= 4 * 1024 * 1024, "READINESS_RECEIPT_MISSING_OR_SIZE")
        value = j.loads(row[0])
        j.require(digest(value) == key, "READINESS_RECEIPT_SHA")
        f.keys(value, ("schema_version", "name", "config_sha256", "decision_at", "evidence_head_sha256",
                       "basis_sha256", "source_error", "result", "snapshot_content", "snapshot_binding", "latest_sync"),
               "READINESS_RECEIPT_SCHEMA")
        return value

    def verify(self, key=None, *, current=False, at=None):
        at = self.clock() if at is None else at
        with self.connect() as db:
            config, head, latest, high = self.control(db)
            key = key or latest
            j.require(key, "READINESS_AUDIT_REQUIRED")
            receipt = self.receipt(db, key)
            captures, _ = self.evidence(db, receipt["evidence_head_sha256"])
            value = receipt["snapshot_content"]
            identity = {k: value[k] for k in ("source", "instrument", "endpoint_version", "journal_genesis", "data_mode")}
            src = dict(saved=dict(content=value, snapshot_sha256=digest(value)), identity=identity,
                       binding=receipt["snapshot_binding"], attempt=receipt["latest_sync"])
            self.binding(config, src)
            result = assess(src, captures, receipt["decision_at"], receipt["source_error"],
                            receipt["result"]["corporate_action_references"], receipt["evidence_head_sha256"])
            j.require(receipt["schema_version"] == 1 and receipt["name"] == self.name
                      and receipt["config_sha256"] == config["config_sha256"] and result == receipt["result"]
                      and digest(dict(result=result, latest_sync=receipt["latest_sync"])) == receipt["basis_sha256"],
                      "READINESS_REPLAY_MISMATCH")
            if current:
                j.require(at >= high and at >= receipt["decision_at"], "READINESS_CLOCK_REGRESSED")
                j.require(head == receipt["evidence_head_sha256"] and latest == key, "READINESS_EVIDENCE_CHANGED")
                now_src = source(config["snapshot_path"])
                self.binding(config, now_src)
                j.require(now_src["saved"]["snapshot_sha256"] == result["input_snapshot_sha256"], "READINESS_SNAPSHOT_CHANGED")
                current_result = assess(now_src, captures, at, None, self.references(config), head)
                j.require(not current_result["blockers"] and current_result == result, "READINESS_CURRENTLY_BLOCKED")
            return receipt, key


def config_mode(config):
    # Re-read the immutable PR33 source identity, never accept a caller mode flag.
    src = s.published(snapshot_ref(config["snapshot_path"]))
    j.require(digest(src["identity"]) == config["source_identity_sha256"], "READINESS_SOURCE_IDENTITY_CHANGED")
    return src["saved"]["content"]["data_mode"]


def public(receipt, key):
    return dict(receipt["result"], receipt_sha256=key, decision_at=receipt["decision_at"],
                name=receipt["name"], receipt_verification="REPLAYABLE_LOCAL_EVIDENCE_NOT_EXTERNAL_CERTIFICATION",
                next_required_evidence=([] if not receipt["result"]["blockers"] else [
                    "21 consecutive on-day original EOD sessions and a fresh PR33 snapshot",
                    "operator-reviewed authorized complete action-feed contract and actual on-day capture for each return interval"]))


def reference(name, src, at):
    receipt, key = Store(name).verify(current=True, at=at)
    result = receipt["result"]
    j.require(result["forward_research_readiness"] == "ALLOW_RESEARCH_ONLY"
              and result["input_snapshot_sha256"] == src["saved"]["snapshot_sha256"]
              and result["source_identity_sha256"] == digest(src["identity"]), "READINESS_TASK_BINDING")
    return dict(contract=VERSION, store_name=name, receipt_sha256=key,
                evidence_head_sha256=receipt["evidence_head_sha256"])


def authorize(ref, src, at, *, current=True):
    f.keys(ref, ("contract", "store_name", "receipt_sha256", "evidence_head_sha256"), "READINESS_REFERENCE_SCHEMA")
    j.require(ref["contract"] == VERSION, "READINESS_REFERENCE_VERSION")
    receipt, key = Store(ref["store_name"]).verify(ref["receipt_sha256"], current=current, at=at)
    result = receipt["result"]
    content = src["saved"]["content"]
    j.require(result["forward_research_readiness"] == "ALLOW_RESEARCH_ONLY"
              and receipt["evidence_head_sha256"] == ref["evidence_head_sha256"]
              and digest(content) == result["input_snapshot_sha256"]
              and content == receipt["snapshot_content"] and src["attempt"] == receipt["latest_sync"]
              and receipt["decision_at"] <= at and j.day(at) == result["source_day"], "READINESS_TASK_BINDING")
    return ref


def gate(value):
    f.keys(value, ("reference", "now_ms", "input_snapshot_sha256", "source_identity_sha256", "source_day", "input_mode"),
           "READINESS_GATE_SCHEMA")
    ref = value["reference"]
    receipt, _ = Store(ref["store_name"]).verify(ref["receipt_sha256"], current=True, at=f.stamp(value["now_ms"]))
    result = receipt["result"]
    j.require(ref["contract"] == VERSION and ref["evidence_head_sha256"] == receipt["evidence_head_sha256"]
              and all(result[k] == value[k] for k in
                      ("input_snapshot_sha256", "source_identity_sha256", "source_day", "input_mode")), "READINESS_TASK_BINDING")
    return dict(verified=True, **ref)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--snapshot-store", required=True, type=Path)
    init.add_argument("--corporate-action-bundle", type=Path)
    configure = commands.add_parser("source")
    configure.add_argument("--contract", required=True, type=Path)
    capture = commands.add_parser("capture")
    capture.add_argument("--payload", required=True, type=Path)
    commands.add_parser("audit")
    for command in ("status", "report", "verify"):
        sub = commands.add_parser(command)
        sub.add_argument("--receipt")
    commands.add_parser("gate", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == "gate":
            raw = sys.stdin.buffer.read(8193)
            j.require(len(raw) <= 8192, "READINESS_GATE_SIZE")
            result = gate(j.loads(raw))
        else:
            store = Store(args.name)
            if args.command == "init":
                result = store.init(args.snapshot_store, args.corporate_action_bundle)
            elif args.command == "source":
                result = store.configure_source(args.contract)
            elif args.command == "capture":
                result = store.capture(args.payload)
            elif args.command == "audit":
                result = store.audit()
            else:
                receipt, key = store.verify(args.receipt)
                result = public(receipt, key)
        print(j.canonical(result).decode())
        return 2 if args.command != "init" and result.get("forward_research_readiness") == "BLOCKED" else 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(j.canonical(dict(forward_research_readiness="BLOCKED", error_code=failure_code(error), **SAFE)).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
