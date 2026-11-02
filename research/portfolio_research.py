"""Cloud Risk + Portfolio V1. Original Rust tasks, budget and original Registry/Inbox.

Recordings are synthetic wire responses, never real cloud/model observations.
All batch names/worktrees share a fixed Agent database. Read commands never open
the writer bridge, recover tasks, bill, or start inference.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from zoneinfo import ZoneInfo

import candidates as c
import data_snapshot as d
import eod_journal as j
import shadow as s

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "target/debug" / ("risk-portfolio-agent.exe" if os.name == "nt" else "risk-portfolio-agent")
SCOPE, POLICY = "risk_portfolio_v1", "risk-portfolio-v1"
SAFE = dict(restriction="RESEARCH_ONLY", eligibility="ELIGIBILITY_DENIED",
            can_execute_forward_paper=False, live_allowed=False, orders=0, fills=0, nav=None)


def root():
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")}
    output = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT,
                            env=env, capture_output=True, check=True)
    return Path(os.fsdecode(output.stdout).strip()).resolve().parent / "state/risk-portfolio"


def digest(value):
    """serde_json Value's sorted compact representation (inputs contain no floats)."""
    return j.sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def read(path, limit=262144):
    c.no_links(path)
    return c.read(path, limit)


def bridge(*args):
    j.require(EXE.is_file(), "RISK_PORTFOLIO_AGENT_NOT_BUILT")
    p = subprocess.Popen([str(EXE), *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, _ = p.communicate(timeout=150)
    except (KeyboardInterrupt, subprocess.TimeoutExpired):
        if p.poll() is None:
            p.kill()
        p.communicate()
        raise j.Rejected("CLOUD_BRIDGE_INTERRUPTED_OUTCOME_REVIEW_REQUIRED") from None
    value = j.loads(out)
    j.require(p.returncode == 0, value.get("error_code", "CLOUD_BRIDGE_FAILED") if isinstance(value, dict) else "CLOUD_BRIDGE_FAILED")
    return value


@contextlib.contextmanager
def agent_db():
    with s.readonly(root() / ".agent/agent.sqlite") as db:
        j.require(db.execute("PRAGMA application_id").fetchone()[0] == 1397899569, "ORIGINAL_AGENT_SCHEMA_REQUIRED")
        yield db


def task(task_id):
    with agent_db() as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        j.require(row and row["trigger_key"].startswith(POLICY + ":"), "ORIGINAL_PORTFOLIO_TASK_REQUIRED")
        result = {k: row[k] for k in ("provider_id", "provider_hash", "status", "reason", "created_at", "started_at", "finished_at", "cancel_requested_at")}
        result.update(id=str(row["id"]), request=j.loads(row["request"]), input=j.loads(row["input"]),
                      result=j.loads(row["result"]) if row["result"] else None)
        calls = []
        for call in db.execute("SELECT * FROM calls WHERE task_id=? ORDER BY id", (task_id,)):
            v = {k: call[k] for k in ("state", "price_version", "reason", "day", "month")}
            v.update({k: str(call[k]) if call[k] is not None else None for k in
                      ("id", "maximum_micro", "settled_micro", "usage_micro", "input_tokens", "output_tokens")})
            calls.append(v)
        result["calls"] = calls
        result["retryable"] = result["status"] == "failed" and len(calls) < 2 and all(v["state"] == "no_charge" for v in calls)
        return result


def result_sha(task_id):
    with agent_db() as db:
        encoded = db.execute("SELECT result FROM tasks WHERE id=?", (task_id,)).fetchone()[0]
    j.require(encoded is not None, "RISK_PARENT_MISSING")
    return j.sha(encoded.encode())


def control(enabled):
    """Owner-local opt-in/stop can commit while the original Agent owns its lock."""
    path = root() / ".agent/agent.sqlite"
    for file in (path, *s.sidecars(path)):
        c.no_links(file)
    j.require(path.is_file(), "ORIGINAL_AGENT_STORE_REQUIRED")
    if enabled:
        config = read(root() / ".agent/settings.json")
        j.require(config["budget"]["currency"] == "TST" and all(m.get("cloud", {}).get("transport") == "recorded" for m in config["models"]),
                  "CLOUD_NOT_AUTHORIZED")
    with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        j.require(db.execute("PRAGMA application_id").fetchone()[0] == 1397899569
                  and db.execute("PRAGMA user_version").fetchone()[0] == 1, "ORIGINAL_AGENT_SCHEMA_REQUIRED")
        db.execute("INSERT INTO meta VALUES('risk_portfolio_enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   ("true" if enabled else "false",))
        db.commit()
    return dict(enabled=enabled, mode="SYNTHETIC_RECORDED_ONLY", **SAFE)


class Run:
    def __init__(self, name):
        j.require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name), "PORTFOLIO_NAME_INVALID")
        self.name, self.root = name, root() / name
        c.no_links(self.root)

    def frozen(self):
        return read(self.root / "frozen.json")

    def config(self):
        f = self.frozen()
        return dict(name=self.name, candidate_registry_name=self.name, binding_sha256=digest(f),
                    source_identity_sha256=f["snapshot_ref"])

    def task_for(self, intent):
        with agent_db() as db:
            row = db.execute("SELECT id FROM tasks WHERE trigger_key=?", (intent["trigger_key"],)).fetchone()
        return task(row[0]) if row else None

    def intent(self, phase):
        key = digest(self.frozen())
        with agent_db() as db:
            row = db.execute("SELECT input FROM tasks WHERE trigger_key=?", (f"{POLICY}:{self.name}:{key}:{phase}",)).fetchone()
        return dict(trigger_key=f"{POLICY}:{self.name}:{key}:{phase}", input=j.loads(row[0])) if row else None

    def once(self):
        with d.writer(root() / ".once.lock"):
            for phase in ("risk", "fusion"):
                bridge("queue", self.name, phase)
                value = bridge("tick", self.name, phase)
                if value["status"] != "completed":
                    failure = dict(state="BLOCKED", phase=phase, task_id=value["id"], reason=value["reason"],
                                   calls=value["calls"], failure_receipt=(value.get("result") or {}).get("cloud_failure"), **SAFE)
                    c.write(self.root / "failure.json", failure)
                    return failure
            self.archive(value)
            return self.report()

    def completed(self, value, intent):
        j.require(value and value == task(value["id"]) and value["status"] == "completed" and value["input"] == intent["input"]
                  and value["result"]["synthetic_provider"] is True and value["result"]["billing"] == "synthetic_test_settled"
                  and len(value["calls"]) == 1 and value["calls"][0]["state"] == "settled", "ORIGINAL_CLOUD_TASK_NOT_COMPLETED")
        output = value["result"]["research"]["risk_portfolio"]
        j.require(output["authority"] == "RESEARCH_ONLY" and output["eligibility"] == "ELIGIBILITY_DENIED"
                  and not output["can_execute_forward_paper"] and not output["live_allowed"]
                  and output["receipt"]["transport"] == "recorded" and output["receipt"]["billing"] == "NOT_BILLED"
                  and output["receipt"]["frozen_input_sha256"] == digest(self.frozen()), "CLOUD_RESULT_BINDING")

    def archive(self, value):
        self.completed(value, self.intent("fusion"))
        c.write(self.root / "task-export.json", value)
        registry = c.Registry(self.name, create=True)
        with registry.locked():
            registration = registry.register(None, self.root / "task-export.json")
        record = dict(registration_sha256=registration["registration_sha256"], task_detail_sha256=c.digest(value))
        path = self.root / "archive.json"
        if path.exists():
            j.require(read(path) == record, "PORTFOLIO_ARCHIVE_CHANGED")
        else:
            c.write(path, record)
        return record

    def archived(self, config, value):
        archive = read(self.root / "archive.json")
        material = c.Registry(config["candidate_registry_name"]).registration(archive["registration_sha256"])["material"]
        j.require(material == dict(schema_version=1, owner_input=None, saved_agent_task=value, authority="research_only",
                    template=None, snapshot_provenance=provenance(value, None))
                  and archive["task_detail_sha256"] == c.digest(value), "PORTFOLIO_ARCHIVE_CHANGED")
        return archive["registration_sha256"]

    def report(self):
        f = self.frozen()
        tasks = {}
        for phase in ("risk", "fusion"):
            intent = self.intent(phase)
            if intent is None:
                return dict(state="FROZEN_NOT_RUN", name=self.name, frozen_input_sha256=digest(f), **SAFE)
            v = self.task_for(intent)
            if v["status"] != "completed":
                return dict(state="BLOCKED", phase=phase, task_id=v["id"], reason=v["reason"], calls=v["calls"],
                            failure_receipt=(v.get("result") or {}).get("cloud_failure"), **SAFE)
            self.completed(v, intent)
            tasks[phase] = v
        archive = read(self.root / "archive.json")
        self.archived(self.config(), tasks["fusion"])
        risk, fusion = (tasks[k]["result"]["research"]["risk_portfolio"] for k in ("risk", "fusion"))
        j.require(tasks["fusion"]["input"]["summary"]["risk_result_sha256"] == result_sha(tasks["risk"]["id"]), "RISK_PARENT_CHANGED")
        return dict(schema_version=1, state="RESEARCH_ONLY", name=self.name, input_mode=f["input_mode"],
                    frozen_input_sha256=digest(f), snapshot_sha256=f["snapshot_ref"], strategy_version=f["strategy_version"],
                    prompt_version=f["prompt_version"], task_refs={k: v["id"] for k, v in tasks.items()},
                    call_refs={k: v["calls"] for k, v in tasks.items()}, risk_experts=risk["risk_experts"],
                    risk_receipt=risk["receipt"], fusion_receipt=fusion["receipt"], portfolio=fusion["portfolio"],
                    discovery=fusion["discovery"], registration_sha256=archive["registration_sha256"],
                    strategy_artifact_sha256=fusion["strategy_artifact_sha256"],
                    cloud="CLOUD_NOT_AUTHORIZED", billing="NOT_BILLED", real_cloud_calls=0,
                    cost_comparison=dict(currency="TST", unit="micro_test_currency", actual_cloud_bill="UNKNOWN_NOT_CALLED",
                        risk_simulated_settled_micro=tasks["risk"]["calls"][0]["settled_micro"],
                        fusion_simulated_settled_micro=tasks["fusion"]["calls"][0]["settled_micro"],
                        naive_ewma_model_fee_micro=0, note="synthetic metering only; no provider price claim"), **SAFE)


def provenance(value, store_name):
    j.require(store_name is None, "PORTFOLIO_HAS_OWN_VERSIONED_SOURCE_CONTRACT")
    original = task(value["id"])
    j.require(original == value and original["input"]["scopes"] == [SCOPE, "portfolio_fusion_v1"], "ORIGINAL_AGENT_TASK_MISMATCH")
    t = value["input"]["summary"]
    run = Run(t["batch"])
    f = run.frozen()
    run.completed(value, run.intent("fusion"))
    risk = task(t["risk_task_id"])
    run.completed(risk, run.intent("risk"))
    j.require(t["risk_result_sha256"] == result_sha(risk["id"]) and t["frozen_sha256"] == digest(f), "PORTFOLIO_SOURCE_CHANGED")
    for phase in ("risk", "fusion"):
        path = run.root / f"{phase}-recording.json"
        j.require(j.sha(path.read_bytes()) == f[f"{phase}_recording_sha256"], "OUTBOUND_RECEIPT_CHANGED_NEW_TASK_REQUIRED")
    return dict(snapshot_sha256=f["snapshot_ref"], source_day=value["input"]["source_day"], data_mode=f["input_mode"],
                research_task_id=value["id"], input_summary_version=value["input"]["version"], frozen_input_sha256=c.digest(value["input"]),
                expert_input_sha256=digest(f), risk_task_id=risk["id"], risk_result_sha256=t["risk_result_sha256"],
                snapshot_verification="ORIGINAL_AGENT_AND_FROZEN_SYNTHETIC_SOURCE_VERIFIED",
                task_origin="ORIGINAL_AGENT_SQLITE_VERIFIED_BY_RUNNER", restriction="RESEARCH_ONLY",
                eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)


class ReviewSource(Run):
    """Only the source seam changes; #46 owns Inbox/Owner association/evaluation."""
    def meta(self):
        saved = read(self.root / "archive.json")
        intent = self.intent("fusion")
        key = digest(self.frozen())
        return {"eod_auto_archive:" + key: j.canonical(saved).decode(), "eod_auto_intent:" + key: j.canonical(intent).decode()}

    def verify_binding(self, config, saved):
        j.require(config == self.config(), "PORTFOLIO_BINDING_CHANGED")

    def binding_owner(self, config):
        return self.name

    def settings(self):
        return read(root() / ".agent/settings.json")

    def validate_intent(self, key, intent):
        j.require(key == digest(self.frozen()) and intent == self.intent("fusion"), "PORTFOLIO_INTENT_CHANGED")


def synthetic_freeze(name, scenario, version):
    run = Run(name)
    j.require(not run.root.exists() and not (ROOT / "state/candidates" / name).exists(), "NEW_PORTFOLIO_BATCH_REQUIRED")
    models = {m["id"]: m for m in bridge("descriptor")}
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(j.ZONE).date()
    while today.weekday() >= 5:
        today -= dt.timedelta(days=1)
    days, day = [], today
    while len(days) < 84:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= dt.timedelta(days=1)
    days.reverse()
    day = today
    while len(days) < 104:
        day += dt.timedelta(days=1)
        if day.weekday() < 5:
            days.append(day.isoformat())
    stocks = ["600000.SH", "000001.SZ", "600519.SH"]
    series = [dict(instrument=stock, corporate_actions="SYNTHETIC_NONE_VERIFIED", observations=[
        dict(trade_day=day, available_at=day + "T00:00:00Z",
             close_fen=10000 + n * 3 + (int(450 * math.sin(n * 1.8 + i)) if scenario == "stress" else int(30 * math.sin(n + i))))
        for n, day in enumerate(days[:84])]) for i, stock in enumerate(stocks)]
    snapshot = digest(dict(series=series, calendar=days))
    pins = {phase + "_model": {k: models[model][k] for k in ("id", "fingerprint")}
            for phase, model in (("risk", "risk-timesfm"), ("fusion", "fusion-deepseek"))}
    identities = {k: models["risk-timesfm"][k] for k in ("adapter_sha256", "prompt_sha256")}
    strategy_hash = digest(dict(strategy_version=version, prompt_version="portfolio-json-v1", **identities, **pins))
    risk_recording = dict(jobComplete=True, jobReference=dict(projectId="stratide-offline", location="US", jobId="synthetic-timesfm-" + snapshot[:16]),
                          schema=dict(fields=[dict(name=n, type=t) for n, t in
                              (("instrument", "STRING"), ("forecast_timestamp", "TIMESTAMP"), ("forecast_value", "FLOAT"), ("ai_forecast_status", "STRING"))]),
                          totalBytesProcessed="1024", totalRows="60", rows=[])
    for stock in sorted(stocks):
        for n in range(20):
            timestamp = int((dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=64 + n)).timestamp())
            risk_recording["rows"].append(dict(f=[dict(v=stock), dict(v=str(timestamp)), dict(v="0.04" if scenario == "stress" else "0.004"), dict(v="")]))
    portfolio = dict(schema_version=1, proposal_id="synthetic-" + scenario + "-" + version, strategy_version=version,
                     strategy_hash=strategy_hash, strategy_definition="Test risk-sensitive diversified quality discovery against an all-cash control",
                     source_refs=[snapshot, strategy_hash], as_of=now.isoformat().replace("+00:00", "Z"), horizon=20,
                     candidate_instruments=stocks + ["300999.SZ"], positions=[] if scenario == "stress" else
                     [dict(instrument=stock, target_weight_bps=2000) for stock in stocks], cash_weight_bps=10000 if scenario == "stress" else 4000,
                     rationale="Use independently computed risk proxies; preserve cash when proxy volatility is high",
                     evidence_for=["Synthetic numerical risk evidence"], evidence_against=["Fundamentals and news are UNKNOWN"],
                     risk_assessment=["Tail probability and cross-instrument covariance are UNKNOWN_UNCALIBRATED"],
                     invalidation_conditions=["Independent forward comparison contradicts the hypothesis"],
                     next_experiment=["Freeze this version before independent cost-aware evidence evaluation"],
                     limitations=["Recorded synthetic response only; no real model capability, alpha or trade eligibility"],
                     estimated_turnover_bps=None, estimated_fees_micro=None, authority="RESEARCH_ONLY")
    fusion_recording = dict(id="synthetic-deepseek-" + snapshot[:16], model="deepseek-flash", choices=[dict(index=0, finish_reason="stop",
        message=dict(role="assistant", content=json.dumps(portfolio, ensure_ascii=False, separators=(",", ":"))))],
        usage=dict(prompt_tokens=1200, completion_tokens=600, total_tokens=1800))
    frozen = dict(schema_version=1, scope=SCOPE, policy=POLICY, input_mode="synthetic_test", snapshot_ref=snapshot,
                  readiness_ref="SYNTHETIC_ENGINEERING_ONLY", as_of=portfolio["as_of"], strategy_version=version, prompt_version="portfolio-json-v1",
                  calendar=days, calendar_provenance="SYNTHETIC_EXCHANGE_SESSION_FIXTURE", series=series, **identities,
                  opportunities=[dict(instrument=stock, status="UNKNOWN", evidence=[]) for stock in stocks], account_facts="UNKNOWN_NO_ACCOUNT_ORDERS",
                  risk_model={k: models["risk-timesfm"][k] for k in ("id", "fingerprint")},
                  fusion_model={k: models["fusion-deepseek"][k] for k in ("id", "fingerprint")}, batch_budget_micro=100000,
                  risk_recording_sha256=j.sha(c.canonical(risk_recording)), fusion_recording_sha256=j.sha(c.canonical(fusion_recording)))
    run.root.mkdir(parents=True)
    for file, value in (("risk-recording.json", risk_recording), ("fusion-recording.json", fusion_recording), ("frozen.json", frozen)):
        c.write(run.root / file, value)
    return dict(state="FROZEN_SYNTHETIC_NOT_RUN", name=name, frozen_input_sha256=digest(frozen), **SAFE)


def status():
    config = read(root() / ".agent/settings.json")
    with agent_db() as db:
        enabled = db.execute("SELECT value FROM meta WHERE key='risk_portfolio_enabled'").fetchone()
        counts = dict(tasks=db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], calls=db.execute("SELECT COUNT(*) FROM calls").fetchone()[0])
        held = db.execute("SELECT COALESCE(SUM(maximum_micro),0) FROM calls WHERE state NOT IN ('settled','no_charge')").fetchone()[0]
        today = dt.datetime.now(ZoneInfo(config["budget"]["timezone"]))
        daily, monthly = db.execute("SELECT COALESCE(SUM(CASE WHEN day=? THEN settled_micro ELSE 0 END),0), COALESCE(SUM(CASE WHEN month=? THEN settled_micro ELSE 0 END),0) FROM calls WHERE state='settled'",
                                    (today.strftime("%Y-%m-%d"), today.strftime("%Y-%m"))).fetchone()
    return dict(enabled=bool(enabled and enabled[0] == "true"), budget=config["budget"], held_maximum_micro=held,
                daily_settled_micro=daily, monthly_settled_micro=monthly,
                daily_remaining_micro=max(0, config["budget"]["daily_limit_micro"]-daily-held),
                monthly_remaining_micro=max(0, config["budget"]["monthly_limit_micro"]-monthly-held),
                models=[{k: m[k] for k in ("id", "model", "kind", "endpoint", "cloud", "grant")} for m in config["models"]],
                cloud="CLOUD_NOT_AUTHORIZED", billing="NOT_BILLED", **counts, **SAFE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "enable", "disable", "models", "status", "history", "once", "verify", "report", "inbox"):
        commands.add_parser(command)
    freeze = commands.add_parser("synthetic-freeze")
    freeze.add_argument("--scenario", choices=("calm", "stress"), required=True)
    freeze.add_argument("--strategy-version", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            value = bridge(args.command)
        elif args.command in ("enable", "disable"):
            value = control(args.command == "enable")
        elif args.command in ("models", "status"):
            value = status()
        elif args.command == "history":
            with agent_db() as db:
                value = dict(tasks=[dict(id=str(i), status=state, trigger_key=trigger) for i, state, trigger in
                                   db.execute("SELECT id,status,trigger_key FROM tasks ORDER BY id LIMIT 1000")], **SAFE)
        elif args.command == "synthetic-freeze":
            value = synthetic_freeze(args.name, args.scenario, args.strategy_version)
        elif args.command == "inbox":
            import review
            value = review.Review(args.name, portfolio=True).inbox()
        else:
            run = Run(args.name)
            value = run.once() if args.command == "once" else run.report()
        print(j.canonical(value).decode())
        return 2 if value.get("state") == "BLOCKED" else 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        code = str(error) if isinstance(error, (j.Rejected, c.Rejected)) else "PORTFOLIO_LOCAL_FAILURE"
        print(j.canonical(dict(state="BLOCKED", reason=code, cloud="CLOUD_NOT_AUTHORIZED", billing="NOT_BILLED", **SAFE)).decode())
        return 2
