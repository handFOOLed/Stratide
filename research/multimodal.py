"""Owner-local Time-Series + Fusion V1 orchestration.

The existing Rust Agent owns every task/call/reservation/settlement. This module
stores only frozen experiments and audit references, never a second work queue,
budget or financial ledger. Generated text is data, never a template selection.
"""
import argparse
import contextlib
import datetime as dt
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import candidates as c
import data_snapshot as d
import eod_journal as j
import multimodal_experts as e
import shadow as s

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "target/debug" / ("multimodal-agent.exe" if os.name == "nt" else "multimodal-agent")
MAX_RUNS = 256
MODEL_FIELDS = ("id", "label", "kind", "model", "endpoint", "api_key_env", "max_input_tokens",
                "max_output_tokens", "timeout_seconds", "price", "grant", "fake_scenario")
PRICE_FIELDS = ("version", "source", "currency", "input_micro_per_million", "output_micro_per_million",
                "bounded_text_billing_verified")
GRANT_FIELDS = ("receiver", "purpose", "scopes", "authorized_at", "revoked")


@lru_cache(maxsize=1)
def base_root():
    return s.common_root() / "state/multimodal"


def read(path, size=2 * 1024 * 1024):
    j.no_links(path)
    return c.read(path, size)


def bridge(action, name, key=None):
    j.require(EXE.is_file(), "MULTIMODAL_AGENT_NOT_BUILT")
    args = [str(EXE), action, name] + ([key] if key else [])
    process = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, _ = process.communicate(timeout=90)
    except (KeyboardInterrupt, subprocess.TimeoutExpired):
        # Join the original call before returning; a timeout is never safe retry.
        if process.poll() is None:
            process.kill()
        process.communicate()
        raise j.Rejected("FUSION_BRIDGE_INTERRUPTED_REVIEW_REQUIRED") from None
    value = j.loads(out)
    j.require(process.returncode == 0, value.get("error_code", "FUSION_BRIDGE_FAILED"))
    return value


@contextlib.contextmanager
def agent_db(write=False):
    path = base_root() / ".agent/agent.sqlite"
    for p in [path, *s.sidecars(path)]:
        j.no_links(p)
    if not write:
        # Existing #48 immutable reader also checks WAL, hot journals and source
        # changes. status/history/verify/report never open Agent::open/recovery.
        with s.readonly(path) as db:
            j.require(db.execute("PRAGMA application_id").fetchone()[0] == 1397899569
                      and db.execute("PRAGMA user_version").fetchone()[0] == 1, "MULTIMODAL_AGENT_SCHEMA")
            yield db
    else:
        j.require(path.is_file() and not Path(str(path) + "-journal").exists(), "MULTIMODAL_AGENT_MISSING_OR_RECOVERY_REQUIRED")
        db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        finally:
            db.close()


def meta():
    with agent_db() as db:
        return dict(db.execute("SELECT key,value FROM meta WHERE key LIKE 'mm_%' OR key='multimodal_agent_v1' OR key='paused'"))


def set_meta(key, value):
    with agent_db(write=True) as db:
        db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value WHERE value!=excluded.value",
                   (key, value if isinstance(value, str) else j.canonical(value).decode()))


def task(task_id):
    """Exact original Agent task projection; never import task JSON as truth."""
    with agent_db() as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        j.require(row is not None and row["trigger_key"].startswith("multimodal-v1:"), "MULTIMODAL_TASK_NOT_FOUND")
        value = {k: row[k] for k in ("provider_id", "provider_hash", "status", "reason", "created_at",
                                    "started_at", "finished_at", "cancel_requested_at")}
        value.update(id=str(row["id"]), request=j.loads(row["request"]), input=j.loads(row["input"]),
                     result=j.loads(row["result"]) if row["result"] else None)
        calls = []
        for call in db.execute("SELECT * FROM calls WHERE task_id=? ORDER BY id", (task_id,)):
            entry = {k: call[k] for k in ("state", "price_version", "reason", "day", "month")}
            entry.update({k: str(call[k]) if call[k] is not None else None for k in
                          ("id", "maximum_micro", "settled_micro", "usage_micro", "input_tokens", "output_tokens")})
            calls.append(entry)
        value["calls"] = calls
        value["retryable"] = value["status"] == "failed" and len(calls) < 2 and all(v["state"] == "no_charge" for v in calls)
    return value


def settings():
    raw = read(base_root() / ".agent/settings.json", 131072)
    j.require(isinstance(raw, dict) and isinstance(raw.get("models"), list) and raw["models"]
              and isinstance(raw.get("budget"), dict) and raw["budget"].get("currency") == "TST"
              and all(m.get("kind") == "fake" and m.get("endpoint") is None and m.get("api_key_env") is None
                      and isinstance(m.get("price"), dict) and m["price"].get("source") == "synthetic_test"
                      and m["price"].get("currency") == "TST" and m.get("fake_scenario") != "safe_transient"
                      for m in raw["models"]), "MULTIMODAL_LOCAL_FAKE_ONLY")
    return raw


def model_descriptor(model_id):
    models = [m for m in settings()["models"] if m.get("id") == model_id]
    j.require(len(models) == 1, "FUSION_MODEL_NOT_CONFIGURED")
    model = models[0]
    # Match the owning Rust Model's serde field order, including Price/Grant;
    # config whitespace/key order cannot invent a fresh model/budget identity.
    j.require(set(model) == set(MODEL_FIELDS), "MODEL_CONFIG_INVALID")
    normalized = {k: model[k] for k in MODEL_FIELDS}
    for name, fields in (("price", PRICE_FIELDS), ("grant", GRANT_FIELDS)):
        if normalized[name] is not None:
            j.require(set(normalized[name]) == set(fields), "MODEL_CONFIG_INVALID")
            normalized[name] = {k: normalized[name][k] for k in fields}
    fingerprint = j.sha(json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode())
    return dict(provider_id=model_id, provider_hash=fingerprint, model=model["model"])


def validate_fusion(value):
    fields = {"hypothesis", "evidence_for", "evidence_against", "risks", "falsification", "next_experiment", "limitations"}
    j.require(isinstance(value, dict) and set(value) == fields and len(j.canonical(value)) <= 12000, "FUSION_SCHEMA")
    j.require(isinstance(value["hypothesis"], str) and 0 < len(value["hypothesis"].encode()) <= 2048, "FUSION_OUTPUT_INVALID")
    texts = [value["hypothesis"]]
    for key in fields - {"hypothesis"}:
        j.require(isinstance(value[key], list) and 1 <= len(value[key]) <= 6
                  and all(isinstance(v, str) and 0 < len(v.encode()) <= 1024 for v in value[key]), "FUSION_OUTPUT_INVALID")
        texts.extend(value[key])
    for text in texts:
        lower = text.lower()
        j.require(text.strip() and not lower.startswith("/") and not any(t in lower for t in
                  ("http:", "https:", "file:", ":\\", "\\\\", "$(", "`", "<script", "<img", "powershell",
                   "cmd.exe", "python ", "bash ", "sh -", "#!/", "/etc/", "/tmp/", "../"))
                  and not any(t in lower for t in ("rm ", "curl ", "wget ", "invoke-expression"))
                  and not any(word.startswith("/") for word in text.split())
                  and not any(ord(v) < 32 for v in text), "FUSION_COMMAND_OR_URL_REJECTED")


class Run:
    def __init__(self, name, *, clock=s.clock_ms, invoke=bridge, fault=lambda point: None):
        j.require(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name), "MULTIMODAL_NAME_INVALID")
        self.name, self.clock, self.invoke, self.fault = name, clock, invoke, fault
        self.root = base_root() / name
        for path in (self.root, self.root / "config.json", self.root / "active-plan.json", self.root / "experiments"):
            j.no_links(path)

    def config(self):
        value = read(self.root / "config.json", 8192)
        fields = {"schema_version", "policy", "name", "snapshot_store_name", "agent_dir", "candidate_registry_name",
                  "source_identity_sha256", "checkout_root", "binding_sha256"}
        if isinstance(value, dict) and "readiness_store_name" in value:
            import forward_readiness as r
            r.Store(value["readiness_store_name"])
            fields.add("readiness_store_name")
        j.require(isinstance(value, dict) and set(value) == fields and value["schema_version"] == 1
                  and value["policy"] == e.POLICY and value["name"] == self.name and value["agent_dir"] == ".agent"
                  and value["candidate_registry_name"] == self.name and value["checkout_root"] == str(ROOT)
                  and value["binding_sha256"] == e.digest({k: v for k, v in value.items() if k != "binding_sha256"}),
                  "MULTIMODAL_CONFIG")
        d.Store(value["snapshot_store_name"])
        c.Registry(value["candidate_registry_name"])
        return value

    def verify_binding(self, config, saved):
        j.require(saved.get("multimodal_agent_v1") == e.POLICY
                  and saved.get("mm_binding:" + self.name) == config["binding_sha256"], "MULTIMODAL_BINDING_CHANGED")

    def init(self, store, readiness_name=None):
        src = s.source(d.Store(store))
        if readiness_name is not None:
            import forward_readiness as r
            with r.Store(readiness_name).connect() as db:
                readiness_config = r.Store(readiness_name).control(db)[0]
            j.require(readiness_config["snapshot_path"] == str(d.Store(store).path.resolve())
                      and readiness_config["source_identity_sha256"] == e.digest(src["identity"]), "READINESS_TASK_BINDING")
        j.require(not self.root.exists() and not (ROOT / "state/candidates" / self.name).exists(), "NEW_MULTIMODAL_DIRECTORY_REQUIRED")
        base_root().mkdir(parents=True, exist_ok=True)
        with d.writer(base_root() / ".init.lock"):
            j.require(subprocess.run(["git", "check-ignore", "--quiet", str(self.root / "config.json")], cwd=s.common_root()).returncode == 0,
                      "MULTIMODAL_STATE_MUST_BE_GITIGNORED")
            self.root.mkdir()
            c.Registry(self.name, create=True)
            config = dict(schema_version=1, policy=e.POLICY, name=self.name, snapshot_store_name=store,
                          agent_dir=".agent", candidate_registry_name=self.name,
                          source_identity_sha256=e.digest(src["identity"]), checkout_root=str(ROOT))
            if readiness_name is not None:
                config["readiness_store_name"] = readiness_name
            config["binding_sha256"] = e.digest(config)
            c.write(self.root / "config.json", config)
            self.invoke("init", self.name)
            set_meta("mm_binding:" + self.name, config["binding_sha256"])
            self.save_plan("local-test-shrinkage", "fake", "initial-v1", False)
        return self.status()

    def plan(self):
        record = read(self.root / "active-plan.json", 8192)
        plan = record["plan"]
        j.require(set(record) == {"plan", "plan_sha256"} and e.digest(plan) == record["plan_sha256"]
                  and set(plan) == {"schema_version", "label", "baseline", "time_series", "fusion", "target", "horizon_sessions", "policy"}
                  and plan["schema_version"] == 1 and plan["baseline"] == e.BASELINE and plan["policy"] == e.POLICY
                  and plan["target"] == e.TARGET and plan["horizon_sessions"] == 1
                  and plan["time_series"] in e.ADAPTERS.values(), "MULTIMODAL_PLAN_INVALID")
        return plan

    def save_plan(self, adapter, fusion, label, without_fusion):
        j.require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", label), "EXPERIMENT_LABEL_INVALID")
        plan = dict(schema_version=1, label=label, baseline=e.BASELINE, time_series=e.ADAPTERS[adapter],
                    fusion=None if without_fusion else model_descriptor(fusion), target=e.TARGET, horizon_sessions=1, policy=e.POLICY)
        c.write(self.root / "active-plan.json", dict(plan=plan, plan_sha256=e.digest(plan)))
        return dict(state="EXPLICIT_NEW_EXPERIMENT", plan=plan, plan_sha256=e.digest(plan), **e.SAFE)

    def experiment(self, adapter, fusion, label, without_fusion=False):
        self.config()
        with d.writer(base_root() / ".once.lock"):
            return self.save_plan(adapter, fusion, label, without_fusion)

    def control(self, enabled):
        config = self.config()
        with agent_db(write=True) as db:
            binding = db.execute("SELECT value FROM meta WHERE key=?", ("mm_binding:" + self.name,)).fetchone()
            j.require(binding and binding[0] == config["binding_sha256"], "MULTIMODAL_BINDING_CHANGED")
            if enabled:
                key = "mm_source_owner:" + config["source_identity_sha256"]
                owner = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
                j.require(owner is None or owner[0] == self.name, "MULTIMODAL_SOURCE_OWNED")
                db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", (key, self.name))
            db.execute("UPDATE meta SET value=? WHERE key=?", ("true" if enabled else "false", "mm_enabled:" + self.name))
        return self.status()

    def path(self, key):
        j.require(isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key), "EXPERIMENT_KEY_INVALID")
        path = self.root / "experiments" / key
        j.no_links(path)
        return path

    def entries(self, saved=None):
        saved = saved if saved is not None else meta()
        prefix = "mm_run:" + self.name + ":"
        rows = [j.loads(value) for key, value in saved.items() if key.startswith(prefix)]
        j.require(len(rows) <= MAX_RUNS, "MULTIMODAL_RUN_LIMIT")
        return sorted(rows, key=lambda row: (row["created_at"], row["task_id"]))

    def progress(self, key, state, **extra):
        record_key = "mm_run:" + self.name + ":" + key
        prior = meta().get(record_key)
        value = j.loads(prior) if prior else dict(task_id=key, created_at=self.clock())
        value.update(state=state, **extra)
        set_meta(record_key, value)
        set_meta("mm_latest:" + self.name, value)
        return value

    def task_for(self, intent):
        with agent_db() as db:
            row = db.execute("SELECT id FROM tasks WHERE trigger_key=?", (intent["trigger_key"],)).fetchone()
        return task(row[0]) if row else None

    def completed(self, value, intent):
        j.require(value and value["status"] == "completed" and value["input"] == intent["input"]
                  and len(value["calls"]) == 1 and value["calls"][0]["state"] == "settled"
                  and value["result"]["provider_kind"] == "fake" and value["result"]["synthetic_provider"] is True
                  and value["result"]["billing"] == "synthetic_test_settled", "FUSION_NOT_COMPLETED")
        validate_fusion(value["result"]["research"]["fusion"])

    def archived(self, config, value):
        key = value["input"]["summary"]["task_id"]
        receipt = meta().get("mm_archive:" + self.name + ":" + key)
        j.require(receipt, "MULTIMODAL_ARCHIVE_MISSING")
        archive = j.loads(receipt)
        material = c.Registry(config["candidate_registry_name"]).registration(archive["registration_sha256"])["material"]
        j.require(material["saved_agent_task"] == value and material["owner_input"] is None
                  and material["authority"] == "research_only" and material["template"] is None
                  and material["snapshot_provenance"] == provenance(value, None)
                  and c.digest(value) == archive["task_detail_sha256"], "MULTIMODAL_ARCHIVE_MISMATCH")
        return archive["registration_sha256"]

    def freeze(self, config, plan, at):
        src = s.source(d.Store(config["snapshot_store_name"]))
        j.require(e.digest(src["identity"]) == config["source_identity_sha256"], "MULTIMODAL_SOURCE_IDENTITY_CHANGED")
        receipt = self.readiness_reference(config, src, at)
        ready, window = e.source_window(src, at, receipt)
        value = src["saved"]["content"]
        spec = dict(source_identity_sha256=e.digest(src["identity"]), input_snapshot_sha256=src["saved"]["snapshot_sha256"],
                    source_day=value["last_valid_source_day"], target=e.TARGET, horizon_sessions=1, plan=plan, policy=e.POLICY)
        if receipt is not None:
            spec["research_readiness_receipt"] = receipt
        key = e.experiment_key(spec)
        day_key = "mm_day_plan:" + spec["source_identity_sha256"] + ":" + spec["source_day"] + ":" + e.digest(plan)
        saved = meta()
        j.require(saved.get(day_key, key) == key, "SOURCE_CHANGED_REVIEW_REQUIRED")
        path = self.path(key)
        if path.exists():
            frozen = read(path / "input.json")
        else:
            j.require(len(self.entries(saved)) < MAX_RUNS, "MULTIMODAL_RUN_LIMIT")
            frozen = dict(schema_version=1, policy=e.POLICY, task_id=key, spec=spec, plan=plan,
                          input_mode=value["data_mode"], instrument=value["instrument"], source_day=value["last_valid_source_day"],
                          input_snapshot_sha256=src["saved"]["snapshot_sha256"], source_identity_sha256=e.digest(src["identity"]),
                          decision_at=at, as_of=value["as_of_journal_event_at"], snapshot_content=value,
                          latest_sync=src["attempt"], readiness=ready, window=window, window_sha256=e.digest(window), authority=e.SAFE)
            path.mkdir(parents=True)
            c.write(path / "input.json", frozen)
        e.validate_frozen(frozen)
        set_meta(day_key, key)
        set_meta("mm_task_owner:" + key, self.name)
        if "mm_run:" + self.name + ":" + key not in saved:
            self.progress(key, "FROZEN", source_day=frozen["source_day"], input_snapshot_sha256=frozen["input_snapshot_sha256"],
                          frozen_input_sha256=e.digest(frozen), plan_sha256=e.digest(plan))
        return frozen

    def readiness_reference(self, config, src, at):
        if "readiness_store_name" not in config:
            return None
        import forward_readiness as r
        return r.reference(config["readiness_store_name"], src, at)

    def once(self):
        config = self.config()
        with d.writer(base_root() / ".once.lock"):
            saved = meta()
            self.verify_binding(config, saved)
            j.require(saved.get("mm_enabled:" + self.name) == "true", "OWNER_DISABLED")
            j.require(saved.get("paused") != "true", "OWNER_PAUSED")
            at = self.clock()
            j.require(at >= int(saved.get("mm_clock:" + self.name, "0")), "MULTIMODAL_CLOCK_REGRESSED")
            set_meta("mm_clock:" + self.name, str(at))
            plan = self.plan()
            key = None
            try:
                pending = [r for r in self.entries(saved) if r["state"] in ("FROZEN", "EXPERTS_READY", "FUSION_QUEUED", "FUSION_COMPLETED")]
                if pending:
                    j.require(len(pending) == 1, "MULTIMODAL_PENDING_REVIEW_REQUIRED")
                    frozen = read(self.path(pending[0]["task_id"]) / "input.json")
                    e.validate_frozen(frozen)
                    j.require(frozen["plan"] == plan, "PENDING_EXPERIMENT_MUST_FINISH_FIRST")
                else:
                    frozen = self.freeze(config, plan, at)
                key, path = frozen["task_id"], self.path(frozen["task_id"])
                # A completed registration wins over resyncs/restarts. No calls.
                if saved.get("mm_archive:" + self.name + ":" + key):
                    return dict(self.verify(key), reused=True)
                previous = next((r for r in self.entries(saved) if r["task_id"] == key), {})
                if previous.get("state") in ("FAILED", "FUSION_FAILED"):
                    return dict(previous, **e.SAFE)
                self.fault("after_freeze")
                for kind, filename in (("baseline", "baseline.json"), ("time_series", "time-series.json")):
                    file = path / filename
                    value = read(file, 8192) if file.exists() else e.result(frozen, kind, self.clock(),
                              adapter=e.TimeSeriesAdapter(plan["time_series"]["model_id"]) if kind == "time_series" else None)
                    e.validate_expert(value, frozen, kind)
                    if not file.exists():
                        c.write(file, value)
                base, temporal = read(path / "baseline.json", 8192), read(path / "time-series.json", 8192)
                self.progress(key, "EXPERTS_READY", baseline_sha256=e.digest(base), time_series_sha256=e.digest(temporal))
                self.fault("after_experts")
                if plan["fusion"] is None:
                    self.progress(key, "COMPARISON_COMPLETED", fusion="DISABLED_CONTROL_NO_AGENT_CALL")
                    return self.report(key)
                summary = e.fusion_input(frozen, base, temporal)
                intent = dict(trigger_key="multimodal-v1:" + self.name + ":" + key, input=summary)
                intent_key = "mm_intent:" + self.name + ":" + key
                prior_intent = meta().get(intent_key)
                j.require(prior_intent is None or j.loads(prior_intent) == intent, "MULTIMODAL_INPUT_CHANGED")
                if not prior_intent:
                    c.write(path / "fusion-input.json", summary)
                    set_meta(intent_key, intent)
                original = self.task_for(intent)
                if not original:
                    j.require(model_descriptor(plan["fusion"]["provider_id"]) == plan["fusion"], "PINNED_MODEL_CONFIGURATION_CHANGED")
                    original = self.invoke("queue", self.name, key)
                self.progress(key, "FUSION_QUEUED", agent_task_id=original["id"])
                self.fault("after_queue")
                if original["status"] == "queued":
                    # Recheck authoritative original journal before NEW calls.
                    try:
                        current = s.source(d.Store(config["snapshot_store_name"]))
                        receipt = self.readiness_reference(config, current, self.clock())
                        e.source_window(current, self.clock(), receipt)
                        j.require(receipt == frozen["readiness"].get("research_readiness_receipt"), "READINESS_EVIDENCE_CHANGED")
                        j.require(current["saved"]["snapshot_sha256"] == frozen["input_snapshot_sha256"], "SOURCE_CHANGED_REVIEW_REQUIRED")
                    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                        # Finish this original queued intent too; a Python audit
                        # failure must not leave executable work in Agent SQLite.
                        self.invoke("reject", self.name, key)
                        raise
                    self.invoke("tick", self.name, key)
                    original = self.task_for(intent)
                if original["status"] != "completed":
                    self.progress(key, "FUSION_FAILED", agent_task_id=original["id"], reason=original["reason"],
                                  agent_status=original["status"], calls=original["calls"])
                    return dict(state="FUSION_FAILED", task_id=key, reason=original["reason"], **e.SAFE)
                self.completed(original, intent)
                self.progress(key, "FUSION_COMPLETED", agent_task_id=original["id"])
                self.fault("after_fusion")
                # Export is only an argument to the original registration API;
                # provenance() independently compares it to original SQLite.
                c.write(path / "task-export.json", original)
                registry = c.Registry(config["candidate_registry_name"])
                with registry.locked():
                    registration = registry.register(None, path / "task-export.json", config["snapshot_store_name"])
                archive = dict(registration_sha256=registration["registration_sha256"], task_detail_sha256=c.digest(original))
                set_meta("mm_archive:" + self.name + ":" + key, archive)
                self.progress(key, "ARCHIVED", **archive)
                return self.verify(key)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                reason = str(error) if isinstance(error, (j.Rejected, c.Rejected)) else "MULTIMODAL_LOCAL_FAILURE"
                if key:
                    self.progress(key, "FAILED", reason=reason)
                    c.write(self.path(key) / "failure.json", dict(state="FAILED", reason=reason, task_id=key, **e.SAFE))
                else:
                    set_meta("mm_latest:" + self.name, dict(state="BLOCKED", reason=reason, at=at, **e.SAFE))
                raise j.Rejected(reason) from None

    def verify(self, key):
        config, saved = self.config(), meta()
        self.verify_binding(config, saved)
        path = self.path(key)
        frozen = read(path / "input.json")
        e.validate_frozen(frozen)
        progress = next(r for r in self.entries(saved) if r["task_id"] == key)
        j.require(e.digest(frozen) == progress["frozen_input_sha256"], "FROZEN_INPUT_SHA")
        if progress["state"] in ("FAILED", "FUSION_FAILED"):
            checked = {}
            for kind, filename in (("baseline", "baseline.json"), ("time_series", "time-series.json")):
                if (path / filename).exists():
                    value = read(path / filename, 8192)
                    e.validate_expert(value, frozen, kind)
                    checked[kind + "_sha256"] = e.digest(value)
            original_refs = {}
            if progress.get("agent_task_id"):
                original = task(progress["agent_task_id"])
                j.require(original["input"]["summary"]["task_id"] == key
                          and original["input"] == read(path / "fusion-input.json", 32768), "FUSION_INPUT_MISMATCH")
                original_refs = dict(agent_status=original["status"], calls=original["calls"], task_detail_sha256=c.digest(original))
            return dict(progress | original_refs, checked_artifacts=checked, verification="FAILURE_PRESERVED_NOT_SUCCESS", **e.SAFE)
        base, temporal = read(path / "baseline.json", 8192), read(path / "time-series.json", 8192)
        e.validate_expert(base, frozen, "baseline")
        e.validate_expert(temporal, frozen, "time_series")
        result = dict(state="COMPARISON_COMPLETED", task_id=key, source_day=frozen["source_day"], input_mode=frozen["input_mode"],
                      input_snapshot_sha256=frozen["input_snapshot_sha256"], frozen_input_sha256=e.digest(frozen),
                      baseline_sha256=e.digest(base), time_series_sha256=e.digest(temporal),
                      arithmetic="INDEPENDENT_DECIMAL_RECOMPUTED", **e.SAFE)
        if frozen["plan"]["fusion"] is not None:
            intent = j.loads(saved["mm_intent:" + self.name + ":" + key])
            j.require(intent["input"] == e.fusion_input(frozen, base, temporal), "FUSION_INPUT_MISMATCH")
            value = self.task_for(intent)
            self.completed(value, intent)
            registration = self.archived(config, value)
            result.update(state="ARCHIVED", agent_task_id=value["id"], task_detail_sha256=c.digest(value),
                          fusion_sha256=e.digest(value["result"]["research"]["fusion"]), registration_sha256=registration,
                          calls=value["calls"])
        return result

    def report(self, key):
        result = self.verify(key)
        if result["state"] in ("FAILED", "FUSION_FAILED"):
            return dict(result, evaluation="NOT_EVALUATED", cloud_cost="UNKNOWN_NOT_BILLED",
                        independent_acceptance="NOT_VERIFIED")
        path = self.path(key)
        frozen = read(path / "input.json")
        base, temporal = read(path / "baseline.json"), read(path / "time-series.json")
        result.update(baseline=base, time_series=temporal,
                      comparison=(e.walk_forward(frozen["snapshot_content"], frozen["plan"]["time_series"])
                                  if frozen["input_mode"] == "synthetic_test" else
                                  dict(status="NOT_EVALUATED_FORWARD_RESEARCH_ONLY", authority=e.SAFE)),
                      external_timeseries="EXTERNAL_TIMESERIES_NOT_CONFIGURED", holdout="EXPLORATORY_EX_POST",
                      actual_tradable_at="UNKNOWN_OPENING_SOURCE_BLOCKED", text_event_expert="NOT_IMPLEMENTED",
                      evaluation="NOT_EVALUATED", independent_acceptance="NOT_VERIFIED",
                      cloud_cost="UNKNOWN_NOT_BILLED", public_requests=0)
        if frozen["plan"]["fusion"] is not None:
            value = task(result["agent_task_id"])
            result["fusion"] = value["result"]["research"]["fusion"]
            result["fusion_cost"] = dict(billing="SYNTHETIC_TST_SETTLED_NOT_CLOUD_MONEY", calls=value["calls"],
                started_at=value["started_at"], finished_at=value["finished_at"],
                elapsed_ms=int((dt.datetime.fromisoformat(value["finished_at"]) - dt.datetime.fromisoformat(value["started_at"])).total_seconds() * 1000),
                currency="TST",
                price_version=value["calls"][0]["price_version"], token_source="ORIGINAL_RUST_FAKE_PROVIDER_BYTE_BOUND")
        else:
            result["fusion"] = None
            result["fusion_cost"] = dict(billing="DISABLED_NO_AGENT_CALL", input_tokens=None, output_tokens=None)
        result["report_sha256"] = e.digest(result)
        return result

    def status(self):
        config, saved = self.config(), meta()
        self.verify_binding(config, saved)
        latest = j.loads(saved["mm_latest:" + self.name]) if "mm_latest:" + self.name in saved else None
        return dict(schema_version=1, name=self.name, enabled=saved.get("mm_enabled:" + self.name) == "true",
                    source_identity_sha256=config["source_identity_sha256"], plan=self.plan(), latest=latest,
                    runs=len(self.entries(saved)), mode="LOCAL_FAKE_ONLY", external_timeseries="EXTERNAL_TIMESERIES_NOT_CONFIGURED",
                    **e.SAFE)

    def history(self):
        return dict(schema_version=1, runs=self.entries(), **e.SAFE)


def provenance(value, store_name):
    """New scope only: verify original task, frozen experts and retained PR33 SHA.
    A task-export file alone cannot supply a successful multimodal provenance.
    """
    summary = value["input"]
    j.require(summary["scopes"] == ["owner_task", e.SCOPE] and value == task(value["id"]), "ORIGINAL_AGENT_TASK_MISMATCH")
    key = summary["summary"]["task_id"]
    owner = meta().get("mm_task_owner:" + key)
    j.require(owner, "MULTIMODAL_TASK_OWNER_MISSING")
    service = Run(owner)
    config, path = service.config(), service.path(key)
    j.require(store_name is None or store_name == config["snapshot_store_name"], "MULTIMODAL_SNAPSHOT_BINDING")
    frozen = read(path / "input.json")
    expected = e.fusion_input(frozen, read(path / "baseline.json"), read(path / "time-series.json"))
    j.require(summary == expected and value["provider_hash"] == frozen["plan"]["fusion"]["provider_hash"], "MULTIMODAL_INPUT_MISMATCH")
    service.completed(value, dict(input=expected))
    store = d.Store(config["snapshot_store_name"])
    with s.readonly(store.path) as db:
        saved = db.execute("SELECT content FROM snapshots WHERE sha=?", (frozen["input_snapshot_sha256"],)).fetchone()
    j.require(saved and j.loads(saved[0]) == frozen["snapshot_content"] and j.sha(saved[0].encode()) == frozen["input_snapshot_sha256"],
              "MULTIMODAL_ORIGINAL_SNAPSHOT_MISMATCH")
    result = dict(snapshot_sha256=frozen["input_snapshot_sha256"], snapshot_id="eod-v1:" + frozen["input_snapshot_sha256"],
                source_day=summary["source_day"], data_mode=summary["mode"], research_task_id=value["id"],
                input_summary_version=summary["version"], frozen_input_sha256=c.digest(summary),
                expert_input_sha256=e.digest(frozen), baseline_sha256=e.digest(read(path / "baseline.json")),
                time_series_sha256=e.digest(read(path / "time-series.json")),
                snapshot_verification="RETAINED_PR33_AND_ORIGINAL_AGENT_VERIFIED", task_origin="ORIGINAL_AGENT_SQLITE_VERIFIED_BY_RUNNER",
                restriction="RESEARCH_ONLY", eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)
    if "research_readiness_receipt" in frozen["readiness"]:
        result["research_readiness_receipt"] = frozen["readiness"]["research_readiness_receipt"]
    return result


class ReviewSource(Run):
    """Small source seam for the existing #46 Inbox and Owner evaluator flow."""
    def meta(self):
        saved = meta()
        for original, mapped in (("mm_archive:", "eod_auto_archive:"), ("mm_intent:", "eod_auto_intent:")):
            prefix = original + self.name + ":"
            saved.update({mapped + key[len(prefix):]: value for key, value in list(saved.items()) if key.startswith(prefix)})
        return saved

    def settings(self):
        return settings()

    def binding_owner(self, config):
        return meta().get("mm_source_owner:" + config["source_identity_sha256"])

    def validate_intent(self, key, intent):
        j.require(intent["trigger_key"] == "multimodal-v1:" + self.name + ":" + key
                  and intent["input"]["summary"]["task_id"] == key, "MULTIMODAL_BINDING_CHANGED")


def main(argv=None, *, clock=s.clock_ms, invoke=bridge, fault=lambda point: None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="本地 Time-Series + Fusion 研究；默认 OFF、原 Agent fake 与预算、无交易权限")
    parser.add_argument("--name", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--snapshot-store", required=True)
    init.add_argument("--readiness-store", help="Explicit, separately audited forward readiness store")
    for name in ("enable", "disable", "once", "status", "history"):
        commands.add_parser(name)
    for name in ("verify", "report"):
        commands.add_parser(name).add_argument("task_id", nargs="?")
    experiment = commands.add_parser("experiment", help="显式新实验，保留旧版本和原预算账户")
    experiment.add_argument("--time-series-model", choices=tuple(e.ADAPTERS), default="local-test-shrinkage")
    experiment.add_argument("--fusion-model", default="fake")
    experiment.add_argument("--label", required=True)
    experiment.add_argument("--without-fusion", action="store_true")
    args = parser.parse_args(argv)
    try:
        service = Run(args.name, clock=clock, invoke=invoke, fault=fault)
        if args.command == "init":
            value = service.init(args.snapshot_store, args.readiness_store)
        elif args.command in ("enable", "disable"):
            value = service.control(args.command == "enable")
        elif args.command == "once":
            value = service.once()
        elif args.command == "experiment":
            value = service.experiment(args.time_series_model, args.fusion_model, args.label, args.without_fusion)
        elif args.command in ("verify", "report"):
            rows = service.entries()
            key = args.task_id or (rows[-1]["task_id"] if rows else None)
            j.require(key is not None, "NO_EXPERIMENT")
            value = service.verify(key) if args.command == "verify" else service.report(key)
        else:
            value = service.status() if args.command == "status" else service.history()
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 2 if value.get("state") in ("FAILED", "FUSION_FAILED", "BLOCKED") else 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, StopIteration) as error:
        code = str(error) if isinstance(error, (j.Rejected, c.Rejected)) else "MULTIMODAL_LOCAL_FAILURE"
        print(json.dumps(dict(state="BLOCKED", reason=code, **e.SAFE), sort_keys=True))
        return 2
