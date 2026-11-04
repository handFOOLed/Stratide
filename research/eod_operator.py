"""Owner-authorized foreground EOD wiring; original subsystem records are authority.

V1 deliberately retains the collector's 16:00 single-attempt protocol. At 15:15
it reports EARLY_SOURCE_UNVERIFIED instead of spending an unsafe early slot.
No provider, strategy, financial ledger or model implementation lives here.
"""
import argparse
import contextlib
import datetime as dt
import getpass
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

import data_snapshot as d
import eod_journal as j
import shadow as s

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import eod_auto as a

POLICY = "eod-operator-v1"
SCHEMA = 1090
SAFE = dict(opening_source="BLOCKED", historical_pit="NOT_VERIFIED",
            forward_paper_allowed=False, live_allowed=False,
            orders=0, fills=0, nav=None, authority="NO_ORDERS/NO_FILLS/NO_NAV")
CREDENTIAL_SOURCES = ("windows-credential-manager", "process-env")


def credential(target, value=None):
    """One fixed, repository-scoped Windows Generic Credential. No arbitrary reads.

    Persistence LOCAL_MACHINE means this Windows user on this machine, including
    later logons; it is not a machine-wide credential or a plaintext state file.
    """
    j.require(os.name == "nt", "WINDOWS_CREDENTIAL_MANAGER_UNAVAILABLE")
    import ctypes as ct
    from ctypes import wintypes as w

    class Credential(ct.Structure):
        _fields_ = [("Flags", w.DWORD), ("Type", w.DWORD), ("TargetName", w.LPWSTR),
                    ("Comment", w.LPWSTR), ("LastWritten", w.FILETIME),
                    ("CredentialBlobSize", w.DWORD), ("CredentialBlob", ct.POINTER(ct.c_ubyte)),
                    ("Persist", w.DWORD), ("AttributeCount", w.DWORD), ("Attributes", ct.c_void_p),
                    ("TargetAlias", w.LPWSTR), ("UserName", w.LPWSTR)]

    dll = ct.WinDLL("Advapi32.dll", use_last_error=True)
    dll.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ct.POINTER(ct.POINTER(Credential))]
    dll.CredReadW.restype = w.BOOL
    dll.CredWriteW.argtypes = [ct.POINTER(Credential), w.DWORD]
    dll.CredWriteW.restype = w.BOOL
    dll.CredFree.argtypes = [ct.c_void_p]
    dll.CredFree.restype = None
    if value is not None:
        encoded = value.encode("utf-16-le")
        j.require(0 < len(encoded) <= 2560, "CREDENTIAL_FORMAT_INVALID")
        blob = (ct.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        entry = Credential(Type=1, TargetName=target, CredentialBlobSize=len(encoded),
                           CredentialBlob=blob, Persist=2, UserName="Stratide Tushare EOD")
        j.require(dll.CredWriteW(ct.byref(entry), 0), "CREDENTIAL_STORE_UNAVAILABLE")
        return None
    entry = ct.POINTER(Credential)()
    j.require(dll.CredReadW(target, 1, 0, ct.byref(entry)), "CREDENTIAL_UNAVAILABLE")
    try:
        return ct.string_at(entry.contents.CredentialBlob,
                            entry.contents.CredentialBlobSize).decode("utf-16-le")
    finally:
        dll.CredFree(entry)


def spawn(stage, store, observer, reports, auto_name, token):
    """Submit one original trusted CLI to the OS; never wait inside the fence."""
    env = dict(os.environ)
    env.pop("STRATIDE_TUSHARE_TOKEN", None)
    if stage == "collector":
        exe = ROOT / "target/debug" / ("stratide-cli.exe" if os.name == "nt" else "stratide-cli")
        j.no_links(exe)
        j.require(exe.is_file(), "FORWARD_CLI_NOT_BUILT")
        # Only the original collector receives the token, never argv/output.
        env["STRATIDE_TUSHARE_TOKEN"] = token
        command = [str(exe), "forward-eod-step", str(observer.parent), str(reports)]
    else:
        script, args = {
            "snapshot": ("research-data.py", ["--store", store, "sync"]),
            "shadow": ("forward-shadow.py", ["--store", store, "once"]),
            "fake": ("eod-auto-research.py", ["--name", auto_name, "once"]),
        }[stage]
        path = ROOT / "scripts" / script
        j.no_links(path)
        command = [sys.executable, "-I", "-B", str(path), *args]
    return subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class ReadonlyAuto(a.Auto):
    @contextlib.contextmanager
    def db(self, write=False):
        j.require(not write, "READ_ONLY")
        self.check_paths()
        with s.readonly(self.dbpath) as db:
            j.require(db.execute("PRAGMA application_id").fetchone()[0] == 1397899569
                      and db.execute("PRAGMA user_version").fetchone()[0] == 1, "AUTO_STORE_INVALID")
            yield db


class Operator:
    def __init__(self, store, *, clock=s.clock_ms, spawn=spawn,
                 fault=lambda point: None):
        self.store = d.Store(store)
        self.src = s.published(self.store)
        j.require(self.src["binding"]["source"]["kind"] == "authorized_observer", "OBSERVER_REQUIRED")
        self.identity = dict(policy=POLICY, source=self.src["identity"])
        self.key = j.sha(j.canonical(self.identity))
        self.root = s.common_root() / "state/eod-operator" / self.key
        self.path = self.root / "operator.sqlite"
        self.clock, self.spawn, self.fault = clock, spawn, fault
        self.check_paths()

    def check_paths(self):
        for path in (self.root, self.path, self.root / "writer.lock", self.root / "collector-reports",
                     *s.sidecars(self.path)):
            j.no_links(path)

    @contextlib.contextmanager
    def write(self, create=False):
        self.check_paths()
        j.require(create or self.path.is_file(), "OPERATOR_NOT_INITIALIZED")
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        finally:
            db.close()

    def append(self, db, kind, data):
        row = db.execute("SELECT seq,payload,digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        at = self.clock()
        j.require(not row or at >= j.loads(row[1])["at"], "OPERATOR_CLOCK_REGRESSED")
        seq, previous = (row[0] + 1, row[2]) if row else (0, "")
        payload = dict(kind=kind, at=at, data=data)
        digest = j.sha(j.canonical([SCHEMA, self.key, previous, seq, payload]))
        db.execute("INSERT INTO events VALUES(?,?,?)", (seq, j.canonical(payload).decode(), digest))

    def journal(self, db):
        j.require(db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA, "OPERATOR_SCHEMA")
        entries, previous, enabled = [], "", False
        for seq, payload, digest in db.execute("SELECT * FROM events ORDER BY seq"):
            value = j.loads(payload)
            j.require(seq == len(entries) and digest == j.sha(j.canonical(
                [SCHEMA, self.key, previous, seq, value])), "OPERATOR_CHAIN")
            j.require(not entries or value["at"] >= entries[-1]["at"], "OPERATOR_CLOCK_REGRESSED")
            if seq == 0:
                j.require(value["kind"] == "initialized" and value["data"]["identity"] == self.identity,
                          "OPERATOR_BINDING_CHANGED")
            elif value["kind"] in ("enabled", "disabled"):
                enabled = value["kind"] == "enabled"
            else:
                j.require(value["kind"] in ("stage_started", "receipt"), "OPERATOR_EVENT")
            entries.append(value)
            previous = digest
        j.require(entries, "OPERATOR_EMPTY")
        return dict(entries=entries, head=previous, enabled=enabled, config=entries[0]["data"])

    def saved(self):
        with s.readonly(self.path) as db:
            return self.journal(db)

    def bound(self, config):
        # Aliases share the canonical journal, but cannot redirect its writers.
        j.require(config["snapshot_path"] == str(self.store.path.resolve())
                  and config["workspace"] == str(ROOT), "OPERATOR_BINDING_OWNED")
        path = Path(config["observer"])
        for target in (path, path.parent / "forward.lock"):
            j.no_links(target)
        j.require(str(path) == self.src["binding"]["source"]["path"], "OBSERVER_BINDING_CHANGED")
        return path

    def init(self, observer, shadow_store, auto_name, credential_source):
        j.require(shadow_store in (None, self.store.root.name), "SHADOW_STORE_MUST_MATCH")
        self.src = s.source(self.store)
        source = Path(observer).absolute()
        if source.is_dir():
            source /= "forward.sqlite"
        j.no_links(source)
        j.require(str(source.resolve(strict=True)) == self.src["binding"]["source"]["path"], "OBSERVER_BINDING_CHANGED")
        shadow = s.Shadow(self.store.root.name, clock=self.clock)
        with s.readonly(shadow.path) as db:
            shadow.journal(db)  # must already exist; Operator never enables either child
        if auto_name:
            auto = ReadonlyAuto(auto_name)
            config = auto.config()
            j.require(config["snapshot_store_name"] == self.store.root.name
                      and config["source_identity_sha256"] == a.c.digest(self.src["binding"]), "AUTO_BINDING_CHANGED")
            auto.settings()
            auto.meta()
        config = dict(identity=self.identity, workspace=str(ROOT), snapshot_path=str(self.store.path.resolve()),
                      snapshot_store=self.store.root.name, observer=str(source.resolve()),
                      auto_name=auto_name, credential_source=credential_source)
        self.root.parent.mkdir(parents=True, exist_ok=True)
        j.require(subprocess.run(["git", "check-ignore", "--quiet", str(self.path)], cwd=s.common_root()).returncode == 0,
                  "OPERATOR_MUST_BE_GITIGNORED")
        self.root.mkdir(exist_ok=True)
        with d.writer(self.root / "writer.lock"):
            j.require(not self.path.exists(), "OPERATOR_ALREADY_INITIALIZED")
            with self.write(create=True) as db:
                db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,payload TEXT NOT NULL,digest TEXT NOT NULL)")
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER immutable_{action} BEFORE {action} ON events "
                               "BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END")
                db.execute(f"PRAGMA user_version={SCHEMA}")
                self.append(db, "initialized", config)
        return dict(state="INITIALIZED_OFF", binding_sha256=self.key, **SAFE)

    def control(self, enabled):
        with self.write() as db:
            state = self.journal(db)
            if enabled:
                self.bound(state["config"])
            self.append(db, "enabled" if enabled else "disabled", {})
        return dict(state="ENABLED" if enabled else "DISABLED", **SAFE)

    def credential_target(self):
        root = j.sha(str(s.common_root()).casefold().encode())
        return "Stratide/" + root + "/tushare-daily-trade-cal-v1"

    def token(self, config):
        value = (os.environ.get("STRATIDE_TUSHARE_TOKEN") if config["credential_source"] == "process-env"
                 else credential(self.credential_target()))
        j.require(isinstance(value, str) and value.strip() and len(value) <= 1024,
                  "CREDENTIAL_UNAVAILABLE")
        return value.strip()

    def configure_credential(self):
        config = self.saved()["config"]
        self.bound(config)
        j.require(config["credential_source"] == "windows-credential-manager", "CREDENTIAL_SOURCE_MISMATCH")
        j.require(sys.stdin.isatty(), "INTERACTIVE_TERMINAL_REQUIRED")
        value = getpass.getpass("既有 Tushare Token（不回显，仅保存到当前 Windows 用户凭据管理器）: ")
        j.require(value.strip() and len(value) <= 1024, "CREDENTIAL_FORMAT_INVALID")
        credential(self.credential_target(), value.strip())
        return dict(state="CREDENTIAL_CONFIGURED", **SAFE)

    def observer(self, config):
        path = self.bound(config)
        content, database_sha = j.read_observer(path)
        j.require(all(content[k] == v for k, v in self.identity["source"].items()), "OBSERVER_BINDING_CHANGED")
        # Read the same immutable prefix to inspect the original automatic slot.
        with s.readonly(path) as db:
            rows = db.execute("SELECT payload FROM events ORDER BY seq").fetchall()
        j.require(database_sha == j.sha(path.read_bytes()), "SOURCE_CHANGED_DURING_READ")
        return content, database_sha, [j.loads(r[0]) for r in rows]

    def slot(self, content, events, day):
        starts = {e["run_id"]: e for e in events if e["event"] == "collection_started"
                  and e["trade_day"] == day and j.day(e["observed_at"]) == day
                  and dt.datetime.fromtimestamp(e["observed_at"] / 1000, j.ZONE).hour >= 16}
        if not starts:
            return None
        run = next(reversed(starts))
        out = next((e["outcome"] for e in reversed(events) if e["event"] == "collection_finished"
                    and e["run_id"] == run), None)
        if not out:
            return "OUTCOME_UNKNOWN"
        if "CALENDAR_CONFLICT" in content["blockers"]:
            return "CALENDAR_CONFLICT"
        status = out["status"]
        if status == "valid_eod" and not out["late_backfill"]:
            return "EOD_SOURCE_VERIFIED"
        if status == "market_closed":
            return "MARKET_CLOSED"
        if status == "missing_daily_not_proof_of_suspension":
            return "DATA_NOT_READY"
        if status in ("network_timeout_or_tls_error", "response_read_or_size_error", "response_reflected_secret_discarded"):
            return "OUTCOME_UNKNOWN"
        if status == "rate_limited":
            return "RATE_LIMITED"
        if "permission_denied" in status:
            return "PERMISSION_DENIED"
        return "SOURCE_BLOCKED"

    def shadow_evidence(self, day):
        shadow = s.Shadow(self.store.root.name, clock=self.clock)
        with s.readonly(shadow.path) as db:
            state = shadow.journal(db)
        record = next((o for o in state["observations"] if o["material"]["source_day"] == day), None)
        ref = None
        if record:
            ref = dict(event_id=record["event_id"], evidence_sha256=record["evidence_sha256"],
                       input_snapshot_sha256=record["material"]["input_snapshot_sha256"],
                       decision_at=record["material"]["decision_at"],
                       result=record["material"]["calculation"]["result"])
        return state["enabled"], ref

    def auto_evidence(self, config, day):
        if not config["auto_name"]:
            return None, None
        auto = ReadonlyAuto(config["auto_name"])
        ac = auto.config()
        auto.settings()
        j.require(ac["snapshot_store_name"] == self.store.root.name
                  and ac["source_identity_sha256"] == a.c.digest(self.src["binding"]), "AUTO_BINDING_CHANGED")
        meta = auto.meta()
        j.require(meta.get("eod_auto_binding") == ac["binding_sha256"], "AUTO_BINDING_CHANGED")
        enabled = meta.get("eod_auto_enabled") == "true" and meta.get("paused") != "true"
        key = day[:4] + "-" + day[4:6] + "-" + day[6:]
        intent, archived = meta.get("eod_auto_intent:" + key), meta.get("eod_auto_archive:" + key)
        if not intent or not archived:
            return enabled, None
        intent, archived = j.loads(intent), j.loads(archived)
        task = auto.task_for(intent)
        auto.completed(task, intent)
        j.require(auto.archived(ac, task) == archived["registration_sha256"]
                  and a.c.digest(task) == archived["task_detail_sha256"], "AUTO_ARCHIVE_MISMATCH")
        return enabled, dict(task_id=task["id"], task_detail_sha256=a.c.digest(task),
                             registration_sha256=archived["registration_sha256"], fake_calls=len(task["calls"]),
                             started_at=task["started_at"], finished_at=task["finished_at"],
                             snapshot_sha256=task["input"]["summary"]["snapshot_sha256"])

    def require_enabled(self):
        j.require(self.saved()["enabled"], "OWNER_DISABLED")

    def start(self, stage, day):
        with self.write() as db:
            j.require(self.journal(db)["enabled"], "OWNER_DISABLED")
            self.append(db, "stage_started", dict(stage=stage, source_day=day))

    def dispatch(self, stage, day, config, token=None):
        self.start(stage, day)  # durable intent, not permission to execute later
        # control(False) takes this same BEGIN IMMEDIATE transaction. The last
        # enabled check AND actual Popen stay together: no check/unlock/spawn gap.
        # Popen returning is the irreversible OS dispatch boundary; its child is
        # already in flight. All work/waiting happens after releasing this fence.
        with self.write() as db:
            j.require(self.journal(db)["enabled"], "OWNER_DISABLED")
            process = self.spawn(stage, self.store.root.name, Path(config["observer"]),
                                 self.root / "collector-reports", config["auto_name"], token)
        try:
            process.communicate(timeout=120)
        except KeyboardInterrupt:
            process.wait(timeout=120)
            raise
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise j.Rejected("OUTCOME_UNKNOWN") from None
        return process.returncode  # original subsystem records remain authority

    def receipt(self, state, day, refs, reason=None):
        value = dict(state=state, source_day=day, data_mode=self.identity["source"]["data_mode"], refs=refs, reason=reason)
        with self.write() as db:
            saved = self.journal(db)
            old = next((e["data"] for e in reversed(saved["entries"]) if e["kind"] == "receipt"), None)
            if value != old:
                self.append(db, "receipt", value)
        return dict(**value, **SAFE)

    def once(self):
        self.check_paths()
        j.require(self.path.is_file(), "OPERATOR_NOT_INITIALIZED")
        with d.writer(self.root / "writer.lock"):
            # Recover our own interrupted DELETE transaction only under writer
            # authority. Queries deliberately refuse hot journals without writes.
            with self.write() as db:
                config = self.journal(db)["config"]
            refs, day = {}, j.day(self.clock())
            try:
                self.require_enabled()
                content, dbsha, events = self.observer(config)
                j.require(content["as_of_journal_event_at"] <= self.clock(), "FUTURE_SOURCE_VERSION")
                refs["observer"] = dict(journal_head=content["journal_head"], database_sha256=dbsha)
                local = dt.datetime.fromtimestamp(self.clock() / 1000, j.ZONE)
                minute = local.hour * 60 + local.minute
                if minute < 915:
                    return self.receipt("WAITING_FOR_CLOSE_WINDOW", day, refs)
                if minute < 960:
                    return self.receipt("WAITING_FOR_PUBLICATION", day, refs, "EARLY_SOURCE_UNVERIFIED")
                j.require(not content["pending_runs"], "OUTCOME_UNKNOWN")
                j.require(not content["blockers"] or set(content["blockers"]) <= {"NO_VALID_EOD", "CALENDAR_UNKNOWN"},
                          "SOURCE_QUALITY_BLOCKED")
                slot = self.slot(content, events, day)
                if slot is None:
                    # A valid early observation does not license an implicit revision.
                    if any(v["bar"]["trade_day"] == day and not v["late_backfill"] for v in content["versions"]):
                        return self.receipt("DATA_BLOCKED", day, refs, "EARLY_SOURCE_UNVERIFIED")
                    if minute > 1035:
                        return self.receipt("DATA_NOT_READY", day, refs, "MISSED_COLLECTION_WINDOW")
                    token = self.token(config)  # missing token must not consume the original slot
                    self.dispatch("collector", day, config, token)
                    self.fault("after_collect")
                    content, dbsha, events = self.observer(config)
                    refs["observer"] = dict(journal_head=content["journal_head"], database_sha256=dbsha)
                    slot = self.slot(content, events, day)
                if slot != "EOD_SOURCE_VERIFIED":
                    return self.receipt(slot or "DATA_BLOCKED", day, refs, "ORIGINAL_SLOT_NO_AUTOMATIC_RETRY")
                j.require(j.day(self.clock()) == day, "MISSED_OR_STALE")
                self.require_enabled()
                published = s.published(self.store)
                attempt = published["attempt"]
                if (published["saved"]["content"] != content or not attempt or attempt["state"] != "succeeded"
                        or attempt.get("source_database_sha256") != dbsha
                        or self.clock() - attempt["started_at"] > d.MAX_SYNC_AGE_MS):
                    self.dispatch("snapshot", day, config)
                    j.require(s.published(self.store)["attempt"]["state"] == "succeeded", "SNAPSHOT_SYNC_BLOCKED")
                    self.fault("after_sync")
                self.src = s.source(self.store)
                ready, _ = s.readiness(self.src, self.clock())
                j.require(not [r for r in ready["blockers"] if r != "INSUFFICIENT_FORWARD_WARMUP"],
                          next(iter(ready["blockers"]), "SOURCE_BLOCKED"))
                refs["snapshot"] = dict(snapshot_sha256=self.src["saved"]["snapshot_sha256"],
                                        journal_head=content["journal_head"], verified_at=self.src["saved"]["verified_at"],
                                        started_at=self.src["attempt"]["started_at"], finished_at=self.src["attempt"]["finished_at"])
                self.require_enabled()
                enabled, ref = self.shadow_evidence(day)
                if ref is None:
                    j.require(enabled, "SHADOW_OWNER_DISABLED")
                    self.dispatch("shadow", day, config)
                    self.fault("after_shadow")
                    _, ref = self.shadow_evidence(day)
                    j.require(ref is not None, "SHADOW_NOT_COMMITTED")
                refs["shadow"] = ref
                self.require_enabled()
                enabled, ref = self.auto_evidence(config, day)
                if config["auto_name"]:
                    if ref is None:
                        j.require(enabled, "AUTO_OWNER_DISABLED_OR_PAUSED")
                        self.dispatch("fake", day, config)
                        self.fault("after_fake")
                        _, ref = self.auto_evidence(config, day)
                        j.require(ref is not None, "AUTO_NOT_ARCHIVED")
                    refs["fake"] = ref
                self.require_enabled()
                # Recheck authoritative inputs and each committed ref before COMPLETE.
                self.verify_refs(config, day, refs, complete=True)
                return self.receipt("COMPLETE", day, refs)
            except (j.Rejected, a.c.Rejected) as error:
                reason = str(error)
                reason = reason if re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", reason) else "SUBSYSTEM_BLOCKED"
                state = ("DISABLED" if reason == "OWNER_DISABLED" else "CREDENTIAL_UNAVAILABLE" if reason == "CREDENTIAL_UNAVAILABLE"
                         else "OUTCOME_UNKNOWN" if reason == "OUTCOME_UNKNOWN" else "PARTIAL" if "snapshot" in refs else "DATA_BLOCKED")
                return self.receipt(state, day, refs, reason)

    def verify_refs(self, config, day, refs, complete=False):
        content, _, _ = self.observer(config)
        if "observer" in refs:
            j.require(refs["observer"]["journal_head"] in content["journal_chain"], "OPERATOR_ORIGINAL_PREFIX_CHANGED")
        if "snapshot" in refs:
            with s.readonly(self.store.path) as db:
                row = db.execute("SELECT content FROM snapshots WHERE sha=?", (refs["snapshot"]["snapshot_sha256"],)).fetchone()
            j.require(row and j.sha(j.canonical(j.loads(row[0]))) == refs["snapshot"]["snapshot_sha256"], "SNAPSHOT_HASH_MISMATCH")
            old = j.loads(row[0])
            j.require(content["journal_chain"][:len(old["journal_chain"])] == old["journal_chain"]
                      and old["journal_head"] == refs["snapshot"]["journal_head"], "OPERATOR_ORIGINAL_PREFIX_CHANGED")
        if "shadow" in refs:
            _, ref = self.shadow_evidence(day)
            j.require(ref == refs["shadow"], "OPERATOR_SHADOW_REF_MISMATCH")
        if "fake" in refs:
            _, ref = self.auto_evidence(config, day)
            j.require(ref == refs["fake"], "OPERATOR_AUTO_REF_MISMATCH")
        if complete:
            j.require(set(refs) == ({"observer", "snapshot", "shadow", "fake"} if config["auto_name"]
                                    else {"observer", "snapshot", "shadow"}), "OPERATOR_INCOMPLETE_REFS")
            j.require(refs["snapshot"]["snapshot_sha256"] == refs["shadow"]["input_snapshot_sha256"]
                      and (not config["auto_name"] or refs["fake"]["snapshot_sha256"] == refs["snapshot"]["snapshot_sha256"]),
                      "OPERATOR_CROSS_SOURCE_REFS")

    def query(self, action):
        state = self.saved()
        config = state["config"]
        receipts = [dict(at=e["at"], **e["data"]) for e in state["entries"] if e["kind"] == "receipt"]
        verified, reason = True, None
        try:
            self.observer(config)
            for entry in receipts:
                self.verify_refs(config, entry["source_day"], entry["refs"], entry["state"] == "COMPLETE")
        except (j.Rejected, a.c.Rejected, OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            verified, reason = False, "AUTHORITATIVE_EVIDENCE_BLOCKED"
        result = dict(state="VERIFIED" if verified else "DATA_BLOCKED", enabled=state["enabled"],
                      data_mode=self.identity["source"]["data_mode"],
                      binding_sha256=self.key, journal_head=state["head"], event_count=len(state["entries"]),
                      credential_source=config["credential_source"], credential_available="NOT_CHECKED_READ_ONLY",
                      collection_window="16:00-17:15 Asia/Shanghai", early_source="EARLY_SOURCE_UNVERIFIED",
                      auto_configured=bool(config["auto_name"]), last=receipts[-1] if receipts else None,
                      latest_stage=next((dict(at=e["at"], **e["data"]) for e in reversed(state["entries"])
                                         if e["kind"] == "stage_started"), None),
                      authoritative_evidence_verified=verified, reason=reason, **SAFE)
        if action in ("history", "verify", "report"):
            result["receipts"] = receipts
            result["stages"] = [dict(at=e["at"], **e["data"]) for e in state["entries"] if e["kind"] == "stage_started"]
            result["verification"] = "LOCAL_SUBSYSTEM_SHA_AND_COMMIT_REFS_NOT_INDEPENDENT_ACCEPTANCE"
        return result


def main(argv=None, *, clock=s.clock_ms, spawn=spawn,
         fault=lambda point: None, wait=time.sleep):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "market":
        import market_eod
        return market_eod.cli(arguments[1:])
    parser = argparse.ArgumentParser(description="EOD Operator：一次启用，前台每日自动；NO_ORDERS/NO_FILLS/NO_NAV")
    parser.add_argument("--snapshot-store", required=True, help="已有 PR33 store 名称")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--observer", required=True)
    init.add_argument("--shadow-store")
    init.add_argument("--auto-name")
    init.add_argument("--credential-source", choices=CREDENTIAL_SOURCES,
                      default="windows-credential-manager" if os.name == "nt" else "process-env")
    for command in ("enable", "disable", "credential", "once", "status", "history", "verify", "report"):
        commands.add_parser(command)
    watch = commands.add_parser("watch")
    watch.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        service = Operator(args.snapshot_store, clock=clock, spawn=spawn, fault=fault)
        if args.command == "init":
            result = service.init(args.observer, args.shadow_store, args.auto_name, args.credential_source)
        elif args.command in ("enable", "disable"):
            result = service.control(args.command == "enable")
        elif args.command == "credential":
            result = service.configure_credential()
        elif args.command == "watch":
            j.require(60 <= args.interval_seconds <= 3600, "WATCH_INTERVAL_INVALID")
            while True:
                try:
                    result = service.once()
                except (j.Rejected, a.c.Rejected, OSError, sqlite3.Error, ValueError, KeyError, TypeError):
                    result = dict(state="DATA_BLOCKED", reason="OPERATOR_STORE_OR_SOURCE_UNAVAILABLE", **SAFE)
                print(j.canonical(result).decode(), flush=True)
                wait(args.interval_seconds)
        elif args.command == "once":
            result = service.once()
        else:
            result = service.query(args.command)
        print(j.canonical(result).decode(), flush=True)
        return 3 if result["state"] in ("DATA_BLOCKED", "PARTIAL", "OUTCOME_UNKNOWN", "CREDENTIAL_UNAVAILABLE",
                                           "DATA_NOT_READY", "SOURCE_BLOCKED", "RATE_LIMITED", "PERMISSION_DENIED", "CALENDAR_CONFLICT") else 0
    except KeyboardInterrupt:
        return 130
    except (j.Rejected, a.c.Rejected, OSError, sqlite3.Error, ValueError, KeyError, TypeError, OverflowError) as error:
        reason = str(error) if isinstance(error, (j.Rejected, a.c.Rejected)) else "OPERATOR_STORE_OR_SOURCE_INVALID"
        reason = reason if re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", reason) else "SUBSYSTEM_BLOCKED"
        print(j.canonical(dict(state="DATA_BLOCKED", reason=reason, **SAFE)).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
