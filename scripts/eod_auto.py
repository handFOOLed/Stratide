"""Owner-local EOD automation; original Agent SQLite and candidate registry.

Only main() chooses the real clock/bridge. Tests inject these dependencies in a
separate test process; the production CLI accepts neither a clock nor task JSON.
"""
import argparse
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import candidates as c
import data_snapshot as d
import eod_journal as j

POLICY = "eod-auto-v1"
EXE = ROOT / "target/debug" / ("eod-auto-agent.exe" if os.name == "nt" else "eod-auto-agent")
SAFE = dict(mode="LOCAL_FAKE_ONLY", restriction="RESEARCH_ONLY", evaluation="NOT_EVALUATED",
            eligibility="ELIGIBILITY_DENIED", can_execute_forward_paper=False, live_allowed=False)
SKIPS = {"OWNER_DISABLED", "OWNER_PAUSED", "BEFORE_EOD_WINDOW", "MISSED_OR_STALE", "NO_VALID_CURRENT_EOD"}


def clock_ms():
    return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)


def bridge(action, name):
    j.require(EXE.is_file(), "EOD_AUTO_AGENT_NOT_BUILT")
    # Argument arrays only, no shell and no caller-selectable executable.
    process = subprocess.Popen([str(EXE), action, name], cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    try:
        out, _ = process.communicate(timeout=90)
    except KeyboardInterrupt:
        process.wait(timeout=90)  # submitted fake finishes; do not abandon an active child
        raise
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise j.Rejected("AGENT_BRIDGE_TIMEOUT_REVIEW_REQUIRED") from None
    try:
        value = j.loads(out)
    except (ValueError, TypeError):
        raise j.Rejected("AGENT_BRIDGE_PROTOCOL") from None
    j.require(process.returncode == 0, value.get("error_code", "AGENT_BRIDGE_FAILED"))
    return value


class Auto:
    def __init__(self, name, *, clock=clock_ms, invoke=bridge, fault=lambda point: None):
        j.require(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name), "AUTO_NAME_INVALID")
        self.name, self.clock, self.invoke, self.fault = name, clock, invoke, fault
        self.root = ROOT / "state/eod-auto" / name
        self.agent = self.root / "agent"
        self.dbpath = self.agent / "agent.sqlite"
        self.check_paths()

    def check_paths(self):
        for path in [self.root, self.root / "config.json", self.root / "once.lock", self.root / "status.json",
                     self.root / "task-export.json", self.agent / "settings.json", self.agent / "owner-token",
                     self.agent / "agent.lock", *[Path(str(self.dbpath) + s) for s in ("", "-wal", "-shm", "-journal")]]:
            j.no_links(path)

    def config(self):
        value = c.read(self.root / "config.json", 8192)
        j.require(set(value) == {"schema_version", "policy", "mode", "snapshot_store_name", "agent_dir",
                                "candidate_registry_name", "source_identity_sha256", "binding_sha256"}
                  and value["schema_version"] == 1 and value["policy"] == POLICY
                  and value["mode"] == "local_fake" and value["agent_dir"] == "agent"
                  and value["candidate_registry_name"] == self.name, "AUTO_CONFIG_INVALID")
        for key in ("binding_sha256", "source_identity_sha256"):
            j.require(re.fullmatch(r"[0-9a-f]{64}", value[key]), "AUTO_CONFIG_INVALID")
        j.require(value["binding_sha256"] == c.digest({k: value[k] for k in
                  ("policy", "snapshot_store_name", "source_identity_sha256")}), "AUTO_BINDING_CHANGED")
        d.Store(value["snapshot_store_name"])
        c.Registry(value["candidate_registry_name"])
        return value

    @contextlib.contextmanager
    def db(self, write=False):
        self.check_paths()
        j.require(self.dbpath.is_file(), "AUTO_INIT_INCOMPLETE")
        j.require(not Path(str(self.dbpath) + "-journal").exists(), "AUTO_STORE_JOURNAL")
        conn = sqlite3.connect(self.dbpath.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=1)
        try:
            conn.execute("PRAGMA synchronous=FULL" if write else "PRAGMA query_only=ON")
            if not write:
                conn.execute("BEGIN")
            j.require(conn.execute("PRAGMA application_id").fetchone()[0] == 1397899569
                      and conn.execute("PRAGMA user_version").fetchone()[0] == 1
                      and conn.execute("PRAGMA quick_check").fetchall() == [("ok",)], "AUTO_STORE_INVALID")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        finally:
            conn.close()

    def meta(self):
        with self.db() as db:
            return dict(db.execute("SELECT key,value FROM meta"))

    def verify_binding(self, config, meta):
        j.require(meta.get("eod_auto_binding") == config["binding_sha256"], "AUTO_BINDING_CHANGED")
        token = (self.agent / "owner-token").read_text(encoding="utf-8").strip()
        j.require(re.fullmatch(r"[A-Za-z0-9]{32,128}", token), "OWNER_TOKEN_INVALID")

    def settings(self):
        raw = c.read(self.agent / "settings.json", 131072)
        j.require(isinstance(raw, dict) and isinstance(raw.get("models"), list) and raw["models"]
                  and isinstance(raw.get("budget"), dict) and raw["budget"].get("currency") == "TST"
                  and all(m.get("kind") == "fake" and m.get("endpoint") is None
                          and m.get("api_key_env") is None and isinstance(m.get("price"), dict)
                          and m["price"].get("currency") == "TST" and m["price"].get("source") == "synthetic_test"
                          for m in raw["models"]), "EOD_AUTO_LOCAL_FAKE_ONLY")
        return raw

    def init(self, store):
        source = d.Store(store)
        with source.connect() as db:
            binding, snapshot, _ = source.current(db)
        j.require(binding and snapshot, "NO_PUBLISHED_SNAPSHOT")
        registry = ROOT / "state/candidates" / self.name
        j.no_links(registry)
        j.require(not self.root.exists() and not registry.exists(), "NEW_AUTO_DIRECTORY_REQUIRED")
        j.require(subprocess.run(["git", "check-ignore", "--quiet", str(self.root / "config.json")],
                                cwd=ROOT).returncode == 0, "AUTO_DIRECTORY_MUST_BE_GITIGNORED")
        config = dict(schema_version=1, policy=POLICY, mode="local_fake", snapshot_store_name=store,
                      agent_dir="agent", candidate_registry_name=self.name, source_identity_sha256=c.digest(binding))
        config["binding_sha256"] = c.digest({k: config[k] for k in
                                            ("policy", "snapshot_store_name", "source_identity_sha256")})
        self.root.mkdir(parents=True, exist_ok=False)
        registry.mkdir(parents=True, exist_ok=False)
        c.write(self.root / "config.json", config)
        self.invoke("init", self.name)
        return self.status()

    def control(self, action, task_id=None):
        config, meta = self.config(), self.meta()
        self.verify_binding(config, meta)
        # Owner-local filesystem authority, like the existing invoice CLI. This
        # writes the original Agent pause bit without waiting on a running fake.
        with self.db(write=True) as db:
            if action == "cancel":
                j.require(task_id is not None, "TASK_ID_REQUIRED")
                changed = db.execute("UPDATE tasks SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END,"
                                     "reason='OWNER_CANCEL_REQUESTED',cancel_requested_at=?,"
                                     "finished_at=CASE WHEN status='queued' THEN ? ELSE finished_at END "
                                     "WHERE id=? AND trigger_key LIKE ? AND status IN ('queued','running')",
                                     (self.iso(), self.iso(), task_id, POLICY + ":" + config["binding_sha256"] + ":%"))
                j.require(changed.rowcount == 1, "TASK_NOT_CANCELLABLE")
            else:
                key = "paused" if action in ("pause", "resume") else "eod_auto_enabled"
                value = "true" if action in ("pause", "enable") else "false"
                db.execute("UPDATE meta SET value=? WHERE key=?", (value, key))
        return self.status()

    def iso(self):
        return dt.datetime.fromtimestamp(self.clock() / 1000, dt.timezone.utc).isoformat()

    def task(self, task_id):
        config = self.config()
        with self.db() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            j.require(row is not None and row["trigger_key"].startswith(POLICY + ":" + config["binding_sha256"] + ":"),
                      "AUTO_TASK_NOT_FOUND")
            task = {k: row[k] for k in ("provider_id", "provider_hash", "status", "reason", "created_at",
                                       "started_at", "finished_at", "cancel_requested_at")}
            task.update(id=str(row["id"]), request=j.loads(row["request"]), input=j.loads(row["input"]),
                        result=j.loads(row["result"]) if row["result"] else None)
            task["calls"] = []
            for call in db.execute("SELECT * FROM calls WHERE task_id=? ORDER BY id", (task_id,)):
                detail = {k: call[k] for k in ("state", "price_version", "reason", "day", "month")}
                detail.update({k: str(call[k]) if call[k] is not None else None for k in
                               ("id", "maximum_micro", "settled_micro", "usage_micro", "input_tokens", "output_tokens")})
                task["calls"].append(detail)
            task["retryable"] = task["status"] == "failed" and len(task["calls"]) < 2 and all(
                v["state"] == "no_charge" for v in task["calls"])
        return task

    def task_for(self, intent):
        with self.db() as db:
            row = db.execute("SELECT id FROM tasks WHERE trigger_key=?", (intent["trigger_key"],)).fetchone()
        return self.task(row[0]) if row else None

    def source(self, config):
        market = dt.timezone(dt.timedelta(hours=8))
        now = dt.datetime.fromtimestamp(self.clock() / 1000, market)
        j.require(now.hour >= 16, "BEFORE_EOD_WINDOW")
        store = d.Store(config["snapshot_store_name"])
        wal = Path(str(store.path) + "-wal")
        j.no_links(wal)
        if wal.exists() and wal.stat().st_size:
            # SQLite may ignore a malformed WAL header and expose the previous
            # main file. Detect that concrete corruption before opening SQLite.
            j.require(Path(str(store.path) + "-shm").is_file(), "SNAPSHOT_WAL_INCOMPLETE")
            with wal.open("rb") as stream:
                header = stream.read(32)
            j.require(len(header) == 32, "SNAPSHOT_WAL_INVALID")
            magic, version, page_size = struct.unpack(">III", header[:12])
            j.require(magic in (0x377f0682, 0x377f0683) and version == 3007000
                      and 512 <= page_size <= 65536 and page_size & (page_size - 1) == 0,
                      "SNAPSHOT_WAL_INVALID")
        expected = store.agent_input()  # original bounded reader, latest WAL/sync/permission checks
        with store.connect() as db:
            binding, saved, attempt = store.current(db)
        j.require(c.digest(binding) == config["source_identity_sha256"], "AUTO_SOURCE_IDENTITY_CHANGED")
        # Do not claim a successful sync still matches an observer changed since
        # that sync. Original verifier opens only read-only, saved local inputs.
        content, database_sha = d.read_source(binding["source"])
        j.require(j.sha(j.canonical(content)) == saved["snapshot_sha256"]
                  and database_sha == attempt["source_database_sha256"], "SOURCE_CHANGED_SINCE_SYNC")
        j.require(expected["summary"]["snapshot_sha256"] == saved["snapshot_sha256"], "SOURCE_CHANGED_SINCE_SYNC")
        j.require(expected["source_day"] == now.strftime("%Y-%m-%d"), "MISSED_OR_STALE")
        last = content["bars"][-1]
        j.require(last["late_backfill"] is False and all(
            dt.datetime.fromtimestamp(last[k] / 1000, market).date() == now.date()
            and dt.datetime.fromtimestamp(last[k] / 1000, market).hour >= 16
            for k in ("observed_at", "received_at", "available_at")), "MISSED_OR_STALE")
        j.require(any(r["source_day"] == now.strftime("%Y%m%d") and r["state"] == "valid_eod"
                      for r in content["coverage"]), "NO_VALID_CURRENT_EOD")
        return expected

    def completed(self, task, intent):
        j.require(task and task["status"] == "completed" and task["input"] == intent["input"],
                  "SAVED_COMPLETED_TASK_REQUIRED")
        r, calls = task["result"], task["calls"]
        j.require(isinstance(r, dict) and r.get("provider_kind") == "fake" and r.get("synthetic_provider") is True
                  and r.get("qualification") == "EXPLORATORY_NOT_INDEPENDENT"
                  and r.get("billing") == "synthetic_test_settled" and r.get("provider_id") == task["provider_id"]
                  and len(calls) == 1 and calls[0]["state"] == "settled"
                  and int(calls[0]["settled_micro"]) > 0, "AUTO_TASK_ORIGIN_INVALID")

    def archived(self, config, task):
        # Content addressing lets recovery find an already committed registration
        # without refreshing its historical verification or creating another one.
        provenance = c.snapshot_provenance(task, None)
        provenance["snapshot_verification"] = "SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION"
        material = dict(schema_version=1, owner_input=None, saved_agent_task=task, authority="research_only",
                        template=None, snapshot_provenance=provenance)
        identity = c.digest(material)
        registry = c.Registry(config["candidate_registry_name"])
        path = registry.path("registrations", identity).with_suffix(".json")
        if path.exists():
            j.require(registry.registration(identity)["material"] == material, "AUTO_ARCHIVE_MISMATCH")
            return identity
        return None

    def archive(self, config, intent, task):
        self.completed(task, intent)
        identity = self.archived(config, task)
        if identity is None:
            try:
                expected = self.source(config)
                j.require(expected == intent["input"], "SOURCE_CHANGED_REVIEW_REQUIRED")
            except (j.Rejected, c.Rejected) as error:
                raise j.Rejected("SOURCE_CHANGED_REVIEW_REQUIRED") from error
            c.write(self.root / "task-export.json", task)  # freshly exported from the actual Agent DB
            registry = c.Registry(config["candidate_registry_name"])
            with registry.locked():
                result = registry.register(None, self.root / "task-export.json", config["snapshot_store_name"])
            identity = result["registration_sha256"]
        self.fault("after_registration")
        record = j.canonical(dict(registration_sha256=identity, task_detail_sha256=c.digest(task))).decode()
        with self.db(write=True) as db:
            db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       ("eod_auto_archive:" + task["input"]["source_day"], record))
        self.fault("after_archive")
        return dict(state="COMPLETED", reason="CANDIDATE_ARCHIVED", task_id=task["id"],
                    registration_sha256=identity, source_day=task["input"]["source_day"],
                    input_version=task["input"]["version"], fake_calls=len(task["calls"]), **SAFE)

    def once(self, sync=False):
        self.check_paths()
        config = self.config()
        with d.writer(self.root / "once.lock"):
            meta = self.meta()
            self.verify_binding(config, meta)
            self.settings()  # fake-only check before sync or any Agent recovery/write
            self.invoke("check", self.name)
            j.require(meta.get("eod_auto_enabled") == "true", "OWNER_DISABLED")
            j.require(meta.get("paused") != "true", "OWNER_PAUSED")
            if sync:
                refreshed = d.Store(config["snapshot_store_name"]).sync()
                j.require(refreshed["can_research"], (refreshed["latest_attempt"] or {}).get("error_code") or "SYNC_BLOCKED")
            intents = [j.loads(v) for k, v in sorted(meta.items()) if k.startswith("eod_auto_intent:")]
            market_day = dt.datetime.fromtimestamp(self.clock() / 1000, dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d")
            for intent in intents:
                day = intent["input"]["source_day"]
                j.require(intent["trigger_key"] == POLICY + ":" + config["binding_sha256"] + ":" + day,
                          "AUTO_BINDING_CHANGED")
                if "eod_auto_archive:" + day in meta:
                    continue
                task = self.task_for(intent)
                if day < market_day:
                    # A missed old intention is evidence, not a catch-up job or
                    # a permanent block on future genuinely observed source days.
                    if task and task["status"] == "completed":
                        self.completed(task, intent)
                        if self.archived(config, task):
                            return self.archive(config, intent, task)
                    with self.db(write=True) as db:
                        db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)",
                                   ("eod_auto_review:" + day, "MISSED_OR_STALE" if not task or task["status"] == "queued"
                                    else "SOURCE_CHANGED_REVIEW_REQUIRED"))
                        if task and task["status"] == "queued":
                            db.execute("UPDATE tasks SET status='cancelled',reason='AUTO_MISSED_OR_STALE',finished_at=? "
                                       "WHERE id=? AND status='queued'", (self.iso(), task["id"]))
                    continue
                if task and task["status"] == "completed":
                    return self.archive(config, intent, task)
                j.require(not task or task["status"] == "queued", "AUTO_TASK_REVIEW_REQUIRED")
                try:
                    expected = self.source(config)
                    j.require(expected == intent["input"], "SOURCE_CHANGED_REVIEW_REQUIRED")
                except (j.Rejected, c.Rejected) as error:
                    raise j.Rejected("SOURCE_CHANGED_REVIEW_REQUIRED") from error
                return self.finish(config)
            expected = self.source(config)
            archive = meta.get("eod_auto_archive:" + expected["source_day"])
            if archive:
                record = j.loads(archive)
                intent = j.loads(meta["eod_auto_intent:" + expected["source_day"]])
                task = self.task_for(intent)
                self.completed(task, intent)
                j.require(self.archived(config, task) == record["registration_sha256"]
                          and c.digest(task) == record["task_detail_sha256"], "AUTO_ARCHIVE_MISMATCH")
                return dict(state="SKIPPED", reason="ALREADY_ARCHIVED_INPUT_FROZEN", task_id=task["id"],
                            registration_sha256=record["registration_sha256"], source_day=expected["source_day"], **SAFE)
            self.invoke("intent", self.name)
            self.fault("after_intent")
            return self.finish(config)

    def finish(self, config):
        self.invoke("queue", self.name)
        self.fault("after_task")
        self.invoke("tick", self.name)
        self.fault("after_research")
        # Re-read durable truth, never accept caller-provided result.json.
        meta = self.meta()
        current = self.source(config)
        intent = j.loads(meta["eod_auto_intent:" + current["source_day"]])
        task = self.task_for(intent)
        j.require(task and task["status"] == "completed", "AUTO_TASK_REVIEW_REQUIRED")
        return self.archive(config, intent, task)

    def remember(self, result):
        c.write(self.root / "status.json", dict(at=self.iso(), **result))

    def status(self):
        config, meta = self.config(), self.meta()
        self.verify_binding(config, meta)
        latest = c.read(self.root / "status.json", 8192) if (self.root / "status.json").exists() else None
        result = dict(schema_version=1, policy=POLICY, snapshot_store_name=config["snapshot_store_name"],
                      candidate_registry_name=config["candidate_registry_name"], agent_dir="agent",
                      binding_sha256=config["binding_sha256"], enabled=meta.get("eod_auto_enabled") == "true",
                      paused=meta.get("paused") == "true", last=latest, source=None, tasks=[], **SAFE)
        try:
            self.settings()
            result["settings_state"] = "LOCAL_FAKE_ONLY"
        except j.Rejected as error:
            result["settings_state"] = str(error)
        try:
            saved, attempt = d.Store(config["snapshot_store_name"]).read_snapshot()
            v = saved["content"]
            result["source"] = {k: v.get(k) for k in ("data_mode", "last_valid_source_day", "as_of_journal_event_at")}
            result["source"].update(snapshot_sha256=saved["snapshot_sha256"], observed_at=v["bars"][-1]["observed_at"],
                                     received_at=v["bars"][-1]["received_at"], available_at=v["bars"][-1]["available_at"],
                                     latest_sync={k: attempt.get(k) for k in
                                                  ("state", "started_at", "finished_at", "error_code")})
        except (j.Rejected, OSError, sqlite3.Error, KeyError, TypeError, ValueError):
            result["source_error"] = "SNAPSHOT_UNAVAILABLE_OR_INVALID"
        for key, value in sorted(meta.items()):
            if key.startswith("eod_auto_intent:"):
                intent = j.loads(value)
                task = self.task_for(intent)
                archive = meta.get("eod_auto_archive:" + intent["input"]["source_day"])
                result["tasks"].append(dict(source_day=intent["input"]["source_day"],
                    input_version=intent["input"]["version"], task_id=task["id"] if task else None,
                    task_status=task["status"] if task else "INTENT_RECORDED", attempts=len(task["calls"]) if task else 0,
                    task_reason=task["reason"] if task else None,
                    registration_sha256=j.loads(archive)["registration_sha256"] if archive else None,
                    review_reason=meta.get("eod_auto_review:" + intent["input"]["source_day"]),
                    archive_state="ARCHIVED" if archive else "PENDING"))
        result["needs_manual_review"] = result["settings_state"] != "LOCAL_FAKE_ONLY" or bool(
            latest and latest.get("state") == "BLOCKED") or any(
            t["task_status"] in ("cancelled", "failed", "outcome_uncertain") or t["review_reason"] for t in result["tasks"])
        return result

    def candidate(self, identity):
        config, meta = self.config(), self.meta()
        records = [j.loads(v)["registration_sha256"] for k, v in meta.items() if k.startswith("eod_auto_archive:")]
        j.require(identity in records, "AUTO_CANDIDATE_NOT_FOUND")
        return c.Registry(config["candidate_registry_name"]).source(identity)


def main(argv=None, *, clock=clock_ms, invoke=bridge, fault=lambda point: None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Owner 本机显式启用的 LOCAL_FAKE_ONLY EOD 自动研究")
    parser.add_argument("--name", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--snapshot-store", required=True)
    for name in ("enable", "disable", "pause", "resume", "status"):
        commands.add_parser(name)
    for name in ("once", "watch"):
        p = commands.add_parser(name)
        p.add_argument("--sync", action="store_true", help="沿用已绑定来源执行本地只读 sync")
        if name == "watch":
            p.add_argument("--interval-seconds", type=int, default=300)
            p.add_argument("--cycles", type=int, help="可选的前台循环次数；默认持续运行")
    for name in ("task", "cancel"):
        commands.add_parser(name).add_argument("task_id", type=int)
    commands.add_parser("candidate").add_argument("registration_sha256")
    args = parser.parse_args(argv)
    auto = None
    try:
        auto = Auto(args.name, clock=clock, invoke=invoke, fault=fault)
        if args.command == "init":
            value = auto.init(args.snapshot_store)
        elif args.command in ("enable", "disable", "pause", "resume", "cancel"):
            value = auto.control(args.command, getattr(args, "task_id", None))
        elif args.command == "status":
            value = auto.status()
        elif args.command == "task":
            value = dict(task=auto.task(args.task_id), **SAFE)
        elif args.command == "candidate":
            value = auto.candidate(args.registration_sha256)
        else:
            if args.command == "watch":
                j.require(60 <= args.interval_seconds <= 3600 and (args.cycles is None or args.cycles > 0),
                          "WATCH_INTERVAL_OR_CYCLES_INVALID")
            count = 0
            while True:
                try:
                    value = auto.once(args.sync)
                    code = 0
                except (j.Rejected, c.Rejected) as error:
                    reason = str(error)
                    value = dict(state="SKIPPED" if reason in SKIPS else "BLOCKED", reason=reason, **SAFE)
                    code = 3 if reason in SKIPS else 2
                # A competing once cannot overwrite the active writer's status.
                if value.get("reason") not in ("STORE_BUSY", "AGENT_ALREADY_RUNNING", "REGISTRY_BUSY"):
                    auto.remember(value)
                print(json.dumps(value, ensure_ascii=False), flush=True)
                count += 1
                if args.command == "once" or args.cycles is not None and count >= args.cycles:
                    return code
                time.sleep(args.interval_seconds)
        print(json.dumps(value, ensure_ascii=False), flush=True)
        return 0
    except KeyboardInterrupt:
        print(json.dumps(dict(state="STOPPED", reason="STOPPED_BY_OWNER", **SAFE)), flush=True)
        return 0
    except (j.Rejected, c.Rejected, OSError, sqlite3.Error, ValueError, KeyError, TypeError, OverflowError) as error:
        reason = str(error) if isinstance(error, (j.Rejected, c.Rejected)) else "AUTO_STATE_IO_OR_FORMAT_ERROR"
        print(json.dumps(dict(state="BLOCKED", reason=reason, **SAFE)), flush=True)
        return 2
