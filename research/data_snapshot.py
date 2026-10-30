"""Offline EOD snapshot publication and research-only consumption. No Provider imports.

Only this module's new state/data-sync/<name> store is writable. Publishing the
snapshot and its pointer is one SQLite FULL transaction; a failed refresh keeps
the old pointer. The source is a read-only schema-1041 observer or fixed fixture.
"""
import argparse
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

if __package__:
    from .eod_journal import (AVAILABILITY, Rejected, canonical, day, loads, no_links, read_observer,
                             require, sha, verify_rows)
else:
    from eod_journal import (AVAILABILITY, Rejected, canonical, day, loads, no_links, read_observer,
                            require, sha, verify_rows)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "samples/m2-pr05-eod-synthetic.json"
STORE_VERSION = 1050
AGENT_SCOPE = "forward_eod_research_summary_v1"
AGENT_VERSION = "eod-agent-input-v1"
MAX_SYNC_AGE_MS = 24 * 60 * 60 * 1000


def now():
    return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)


def read_source(spec):
    if spec["kind"] == "repository_synthetic_fixture":
        content = verify_rows(loads(FIXTURE.read_bytes())["rows"])
        require(content["data_mode"] == "synthetic_test", "FIXTURE_MODE_MISMATCH")
        return content, None
    require(spec["kind"] == "authorized_observer", "SOURCE_KIND")
    return read_observer(spec["path"])


@contextlib.contextmanager
def writer(path):
    # OS lifetime lock releases on process death; an abandoned running attempt is
    # a diagnostic, never a successful snapshot or an automatic retry.
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Rejected("STORE_BUSY") from None
        try:
            yield
        finally:
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class Store:
    def __init__(self, name):
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name) is not None, "STORE_NAME")
        self.root = ROOT / "state/data-sync" / name
        no_links(self.root)
        self.path = self.root / "snapshots.sqlite"
        no_links(self.path)
        no_links(self.root / "writer.lock")

    @contextlib.contextmanager
    def connect(self, write=False):
        no_links(self.path)
        if write:
            db = sqlite3.connect(self.path, timeout=0)
        else:
            require(self.path.is_file(), "STORE_NOT_INITIALIZED")
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=0)
            db.execute("PRAGMA query_only=ON")
        try:
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if write and db.execute("PRAGMA user_version").fetchone()[0] == 0:
                require(not db.execute("SELECT name FROM sqlite_master").fetchall(), "STORE_SCHEMA")
                db.execute("CREATE TABLE control(id INTEGER PRIMARY KEY CHECK(id=1), binding TEXT, current_sha TEXT, attempt TEXT)")
                db.execute("CREATE TABLE snapshots(sha TEXT PRIMARY KEY, content TEXT NOT NULL, verified_at INTEGER NOT NULL)")
                db.execute("INSERT INTO control VALUES(1,NULL,NULL,NULL)")
                db.execute(f"PRAGMA user_version={STORE_VERSION}")
            require(db.execute("PRAGMA user_version").fetchone()[0] == STORE_VERSION, "STORE_SCHEMA")
            require(db.execute("PRAGMA quick_check").fetchall() == [("ok",)], "STORE_INTEGRITY")
            yield db
            if write:
                db.commit()
        finally:
            db.close()

    def current(self, db):
        row = db.execute("SELECT binding,current_sha,attempt FROM control WHERE id=1").fetchone()
        require(row is not None, "STORE_CONTROL")
        binding, key, attempt = (loads(row[0]) if row[0] else None), row[1], (loads(row[2]) if row[2] else None)
        snapshot = None
        if key:
            saved = db.execute("SELECT content,verified_at FROM snapshots WHERE sha=?", (key,)).fetchone()
            require(saved is not None, "SNAPSHOT_MISSING")
            content = loads(saved[0])
            require(sha(canonical(content)) == key, "SNAPSHOT_HASH_MISMATCH")
            require(content["schema_version"] == 1 and content["can_execute_forward_paper"] is False
                    and content["live_allowed"] is False and content["opening_source"] == "BLOCKED", "SNAPSHOT_CONTRACT")
            require(binding and content["data_mode"] == binding["data_mode"]
                    and content["journal_genesis"] == binding["journal_genesis"], "SNAPSHOT_SOURCE_BINDING")
            snapshot = dict(snapshot_id="eod-v1:" + key, snapshot_sha256=key, verified_at=saved[1], content=content)
        return binding, snapshot, attempt

    def _publish(self, db, binding, content, at):
        key = sha(canonical(content))
        db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (key, canonical(content).decode(), at))
        db.execute("UPDATE control SET binding=?,current_sha=? WHERE id=1", (canonical(binding).decode(), key))

    def sync(self, observer=None, fixture=False):
        require(not (observer and fixture), "CHOOSE_ONE_SOURCE")
        spec = None
        if observer:
            source = Path(observer).absolute()
            if source.is_dir():
                source = source / "forward.sqlite"
            no_links(source)
            source = source.resolve()
            require(not source.is_relative_to(self.root.resolve()), "SOURCE_STORE_OVERLAP")
            spec = dict(kind="authorized_observer", path=str(source))
        elif fixture:
            spec = dict(kind="repository_synthetic_fixture")
        self.root.mkdir(parents=True, exist_ok=True)
        with writer(self.root / "writer.lock"):
            with self.connect(write=True) as db:
                binding, old, previous = self.current(db)
                spec = spec or (binding["source"] if binding else None)
                require(spec is not None, "SOURCE_REQUIRED")
                started = now()
                attempt = dict(state="running", started_at=started, finished_at=None,
                               error_code=None, blockers=[], source_changed=None, new_append=None)
                db.execute("UPDATE control SET attempt=? WHERE id=1", (canonical(attempt).decode(),))
            try:
                require(binding is None or spec == binding["source"], "SOURCE_BINDING_CHANGED")
                content, database_sha = read_source(spec)
                attempted_head = content["journal_head"]
                attempt["journal_head"] = attempted_head
                attempt["source_database_sha256"] = database_sha
                attempt["source_changed"] = old is None or attempted_head != old["content"]["journal_head"]
                require(content["as_of_journal_event_at"] <= started
                        and (previous is None or started >= previous["started_at"]), "CLOCK_BEFORE_SOURCE_OR_PREVIOUS_SYNC")
                identity = dict(source=spec, data_mode=content["data_mode"], journal_genesis=content["journal_genesis"])
                require(binding is None or identity == binding, "SOURCE_GENESIS_OR_MODE_CHANGED")
                if old:
                    prefix = old["content"]["journal_chain"]
                    require(content["journal_chain"][:len(prefix)] == prefix, "SOURCE_REWRITE_OR_ROLLBACK")
                attempt["new_append"] = bool(old and attempt["source_changed"])
                if content["blockers"]:
                    attempt["blockers"] = content["blockers"]
                    raise Rejected("SOURCE_QUALITY_BLOCKED")
                with self.connect(write=True) as db:
                    finished = now()
                    require(finished >= started, "SYNC_CLOCK_REGRESSED")
                    self._publish(db, identity, content, finished)
                    attempt.update(state="succeeded", finished_at=finished)
                    db.execute("UPDATE control SET attempt=? WHERE id=1", (canonical(attempt).decode(),))
            except (Rejected, OSError, sqlite3.Error, ValueError, KeyError, TypeError, OverflowError) as error:
                code = (str(error) if isinstance(error, Rejected) else "SOURCE_DATABASE_ERROR" if isinstance(error, sqlite3.Error)
                        else "SOURCE_IO_ERROR" if isinstance(error, OSError) else "SOURCE_FORMAT_ERROR")
                attempt.update(state="blocked", finished_at=now(), error_code=code)
                with self.connect(write=True) as db:
                    db.execute("UPDATE control SET attempt=? WHERE id=1", (canonical(attempt).decode(),))
        return self.status()

    def read_snapshot(self):
        """Stable local adapter: returns validated content, including local-only bars."""
        with self.connect() as db:
            _, snapshot, attempt = self.current(db)
        require(snapshot is not None, "NO_PUBLISHED_SNAPSHOT")
        return snapshot, attempt

    def status(self):
        with self.connect() as db:
            _, saved, attempt = self.current(db)
        result = dict(schema_version=1, latest_attempt=attempt, snapshot=None,
                      can_research=False, can_execute_forward_paper=False, live_allowed=False,
                      opening_source="BLOCKED", source_checked_only_at_latest_sync=True)
        if saved:
            content = saved["content"]
            summary = {k: content[k] for k in ("data_mode", "last_valid_source_day", "journal_head", "event_count",
                                               "as_of_journal_event_at", "valid_eod_days", "on_day_valid_eod_days",
                                               "coverage", "gaps", "warnings", "blockers", "can_research",
                                               "can_execute_forward_paper", "live_allowed", "raw_sha256",
                                               "available_at_semantics", "historical_pit", "opening_source")}
            latest = content["bars"][-1]
            summary.update({k: latest[k] for k in ("observed_at", "received_at", "available_at", "provider_published_at")})
            summary.update(snapshot_id=saved["snapshot_id"], snapshot_sha256=saved["snapshot_sha256"],
                           verified_at=saved["verified_at"])
            result["snapshot"] = summary
            result["can_research"] = content["can_research"] and attempt["state"] == "succeeded"
            result["wall_clock_day"] = day(now())
            result["source_day_differs_from_wall_clock"] = day(now()) != content["last_valid_source_day"]
            result["calendar_after_snapshot"] = "UNKNOWN_NOT_FETCHED"
        return result

    def consume(self):
        """Offline research summary only; does not enqueue an Agent task or qualify EOD."""
        status = self.status()
        saved = status["snapshot"]
        require(saved is not None, "NO_PUBLISHED_SNAPSHOT")
        source_day = saved["last_valid_source_day"]
        return dict(version="eod-research-input-v1", source_day=f"{source_day[:4]}-{source_day[4:6]}-{source_day[6:]}",
                    data_mode=saved["data_mode"], snapshot_sha256=saved["snapshot_sha256"],
                    verified_at=saved["verified_at"], can_research=status["can_research"],
                    eod_eligible=False, can_execute_forward_paper=False, live_allowed=False,
                    quality=dict(coverage=saved["coverage"], gaps=saved["gaps"], warnings=saved["warnings"],
                                 blockers=saved["blockers"], historical_pit=saved["historical_pit"],
                                 latest_sync=status["latest_attempt"], source_day_differs_from_wall_clock=status["source_day_differs_from_wall_clock"]),
                    qualification="RESEARCH_INPUT_ONLY_NOT_PIT_OR_EXECUTION_EVIDENCE")

    def agent_input(self):
        """Same bounded projection as Rust eod_snapshot; no Agent/observer writes.

        Fresh sync permission is checked now, but wall/sync time is deliberately
        excluded from the frozen content identity. A later resync cannot change
        a source day or a saved Agent input with the same snapshot SHA.
        """
        for suffix in ("", "-wal", "-shm", "-journal"):
            path = Path(str(self.path) + suffix)
            no_links(path)
            if path.exists():
                require(path.is_file() and path.stat().st_size <= 64 * 1024 * 1024, "SNAPSHOT_STORE_SIZE")
                require(suffix != "-journal", "SNAPSHOT_STORE_JOURNAL")
        require(not Path(str(self.path) + "-wal").exists()
                or Path(str(self.path) + "-shm").is_file(), "SNAPSHOT_WAL_INCOMPLETE")
        with self.connect() as db:
            require(db.execute("PRAGMA journal_mode").fetchone()[0] == "wal", "SNAPSHOT_STORE_SCHEMA")
            size = db.execute("SELECT length(CAST(content AS BLOB)) FROM snapshots WHERE sha="
                              "(SELECT current_sha FROM control WHERE id=1)").fetchone()
            require(size and 0 < size[0] <= 8 * 1024 * 1024, "SNAPSHOT_CONTENT_SIZE")
            binding, saved, attempt = self.current(db)
            require(saved is not None, "NO_PUBLISHED_SNAPSHOT")
            payload = db.execute("SELECT content FROM snapshots WHERE sha=?", (saved["snapshot_sha256"],)).fetchone()[0]
            require(payload == canonical(saved["content"]).decode(), "SNAPSHOT_HASH_MISMATCH")
        v, key = saved["content"], saved["snapshot_sha256"]
        require(v["can_research"] is True and v["blockers"] == [] and v["pending_runs"] == 0
                and v["available_at_semantics"] == AVAILABILITY
                and v["historical_pit"] == "NOT_VERIFIED", "SNAPSHOT_CONTRACT")
        mode = v["data_mode"]
        require(mode in ("synthetic_test", "forward_observed_eod")
                and binding["source"]["kind"] in ("authorized_observer", "repository_synthetic_fixture")
                and (binding["source"]["kind"] != "repository_synthetic_fixture" or mode == "synthetic_test"),
                "SNAPSHOT_SOURCE_BINDING")
        chain = v["journal_chain"]
        require(chain and chain[0] == v["journal_genesis"] and chain[-1] == v["journal_head"]
                and v["event_count"] == len(chain), "SNAPSHOT_SOURCE_BINDING")
        require(attempt and attempt["state"] == "succeeded" and attempt["error_code"] is None
                and attempt["blockers"] == [] and attempt["journal_head"] == v["journal_head"],
                "SNAPSHOT_SYNC_NOT_SUCCEEDED")
        started, finished = attempt["started_at"], attempt["finished_at"]
        require(type(started) is int and type(finished) is int
                and 0 < started <= finished <= now() and now() - started <= MAX_SYNC_AGE_MS,
                "SNAPSHOT_SYNC_STALE_OR_CLOCK")
        bars = v["bars"]
        require(bars and v["valid_eod_days"] == len(bars)
                and all(a["bar"]["trade_day"] < b["bar"]["trade_day"] for a, b in zip(bars, bars[1:]))
                and bars[-1]["bar"]["trade_day"] == v["last_valid_source_day"], "SNAPSHOT_SOURCE_DAY")
        raw_day, last = v["last_valid_source_day"], bars[-1]
        source_day = dt.datetime.strptime(raw_day, "%Y%m%d").strftime("%Y-%m-%d")
        require(source_day.replace("-", "") == raw_day, "SNAPSHOT_SOURCE_DAY")
        observed, received, available, asof = (last["observed_at"], last["received_at"],
                                              last["available_at"], v["as_of_journal_event_at"])
        require(all(type(t) is int for t in (observed, received, available, asof))
                and 0 < observed <= received <= available <= asof <= started
                and raw_day <= day(available) and last["provider_published_at"] is None, "SNAPSHOT_TIME_INVALID")
        require(type(v["on_day_valid_eod_days"]) is int
                and 0 <= v["on_day_valid_eod_days"] <= len(bars), "SNAPSHOT_QUALITY_INVALID")
        require(all(w in {"INTERRUPTED_COLLECTION", "LATE_BACKFILL", "REVISED_EOD", "COLLECTION_ERROR",
                          "MISSING_ON_DAY_EOD"} for w in v["warnings"]), "SNAPSHOT_QUALITY_INVALID")
        for row in [*v["coverage"], *v["gaps"]]:
            parsed = dt.datetime.strptime(row["source_day"], "%Y%m%d").strftime("%Y%m%d")
            require(parsed == row["source_day"] and row["state"] in
                    ("valid_eod", "market_closed", "missing_valid_eod", "calendar_unknown"), "SNAPSHOT_QUALITY_INVALID")
        safe_rows = lambda rows: [{k: r[k] for k in ("source_day", "state")} for r in rows[-16:]]
        summary = dict(snapshot_id=saved["snapshot_id"], snapshot_sha256=key, data_mode=mode,
                       last_valid_source_day=raw_day, as_of_journal_event_at=asof,
                       observed_at=observed, received_at=received, available_at=available, provider_published_at=None,
                       available_at_semantics=AVAILABILITY,
                       valid_eod_days=v["valid_eod_days"], on_day_valid_eod_days=v["on_day_valid_eod_days"],
                       quality=dict(coverage=safe_rows(v["coverage"]), coverage_count=len(v["coverage"]),
                                    gaps=safe_rows(v["gaps"]), gap_count=len(v["gaps"]), warnings=v["warnings"], blockers=[],
                                    historical_pit="NOT_VERIFIED", opening_source="BLOCKED",
                                    source_checked_only_at_latest_sync=True, calendar_after_snapshot="UNKNOWN_NOT_FETCHED",
                                    sync_policy="latest_succeeded_within_24h"),
                       restriction="RESEARCH_ONLY", eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)
        require(len(canonical(summary)) <= 8192, "SNAPSHOT_SUMMARY_SIZE")
        return dict(version=f"{AGENT_VERSION}:{key}", source_day=source_day, mode=mode,
                    scopes=["owner_task", AGENT_SCOPE], summary=summary, eod_eligible=False)


def main():
    parser = argparse.ArgumentParser(description="离线核验既有 EOD，只发布研究快照；不采集、不调用模型。")
    parser.add_argument("--store", required=True, help="新 state/data-sync/ 下的本地名称")
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync")
    source = sync.add_mutually_exclusive_group()
    source.add_argument("--observer", type=Path, help="既有 observer 目录或 forward.sqlite，只读")
    source.add_argument("--fixture", action="store_true", help="固定 synthetic_test 输入")
    sub.add_parser("status")
    sub.add_parser("snapshot", help="只读已发布快照的脱敏元数据；完整内容由本地 adapter 读取")
    sub.add_parser("consume", help="只读研究摘要，不启动 Agent/Provider")
    args = parser.parse_args()
    try:
        store = Store(args.store)
        value = (store.sync(args.observer, args.fixture) if args.command == "sync" else
                 store.consume() if args.command == "consume" else store.status())
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 2 if args.command == "sync" and value["latest_attempt"]["state"] != "succeeded" else 0
    except (Rejected, OSError, sqlite3.Error, ValueError, KeyError, TypeError, OverflowError) as error:
        code = str(error) if isinstance(error, Rejected) else "LOCAL_STORE_OR_INPUT_ERROR"
        print(json.dumps(dict(error_code=code, can_execute_forward_paper=False, live_allowed=False)))
        return 2


if __name__ == "__main__":
    sys.exit(main())
