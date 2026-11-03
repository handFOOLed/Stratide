"""Owner CLI for the versioned local TimesFM -> original Agent Fusion task."""
import argparse
import contextlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import candidates as c
import portfolio_research as rp
import eod_journal as j
import data_snapshot as d

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "target/debug/local-fusion-agent"
POLICY = "local_timesfm_fusion_v1"


def bridge(action, arg=None):
    p = subprocess.run([str(EXE), action] + ([] if arg is None else [str(arg)]),
                       cwd=ROOT, capture_output=True, timeout=150)
    v = j.loads(p.stdout)
    j.require(p.returncode == 0, v.get("error_code", "FUSION_COMMAND_FAILED"))
    return v


def task(task_id):
    with rp.agent_db() as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        j.require(row and row["trigger_key"].startswith(POLICY + ":"), "ORIGINAL_FUSION_TASK_REQUIRED")
        v = {k: row[k] for k in ("provider_id", "provider_hash", "status", "reason", "created_at",
                                 "started_at", "finished_at", "cancel_requested_at")}
        v.update(id=str(row["id"]), request=j.loads(row["request"]), input=j.loads(row["input"]),
                 result=j.loads(row["result"]) if row["result"] else None)
        calls = []
        for row in db.execute("SELECT * FROM calls WHERE task_id=? ORDER BY id", (task_id,)):
            call = {k: row[k] for k in ("state", "price_version", "reason", "day", "month")}
            call.update({k: str(row[k]) if row[k] is not None else None for k in
                         ("id", "maximum_micro", "settled_micro", "usage_micro", "input_tokens", "output_tokens")})
            calls.append(call)
        v.update(calls=calls, retryable=False)
        return v


def check_model(name):
    # The original CPU CLI validates the installed files; this never runs inference.
    sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
    import cli as cpu
    import model
    try:
        manifest = model.verify_model(ROOT / "models/timesfm-2.5")
    except model.Rejected as error:
        raise j.Rejected(str(error)) from None
    source = cpu.task(name)
    j.require(source["state"] == "completed" and source["billing"] == "LOCAL_NO_BILLING",
              "FUSION_LOCAL_PARENT_INCOMPLETE")
    receipt = source["result"]["research"]["risk_portfolio"]["receipt"]
    j.require(receipt["manifest_sha256"] == model.digest(manifest) and not receipt["development_only"],
              "LOCAL_MODEL_CHANGED_NEW_TASK_REQUIRED")


class Run(rp.ReviewSource):
    def frozen(self):
        return bridge("status", self.name)["frozen"]

    def intent(self, phase):
        j.require(phase == "fusion", "LOCAL_FUSION_PHASE")
        view = bridge("status", self.name)
        if "task_id" not in view:
            return None
        value = task(view["task_id"])
        return dict(trigger_key=POLICY + ":" + str(view["context"]["parent_task_id"]) + ":" +
                    view["context"]["parent_result_sha256"], input=value["input"])

    def task_for(self, intent):
        with rp.agent_db() as db:
            row = db.execute("SELECT id FROM tasks WHERE trigger_key=?", (intent["trigger_key"],)).fetchone()
        return task(row[0]) if row else None

    def completed(self, value, intent):
        view = bridge("verify", self.name)
        j.require(value == task(value["id"]) and value["status"] == "completed"
                  and value["input"] == intent["input"] and value["result"] == view["result"]
                  and value["input"]["summary"] == view["context"]
                  and value["result"]["synthetic_provider"] is False
                  and len(value["calls"]) == 1 and value["calls"][0]["state"] in ("usage_received", "settled"),
                  "ORIGINAL_FUSION_TASK_NOT_COMPLETED")

    def once(self):
        with d.writer(rp.root() / ".once.lock"):
            check_model(self.name)
            value = bridge("once", self.name)
            if value["status"] != "completed":
                return dict(state="BLOCKED", task_id=value["id"], reason=value["reason"], calls=value["calls"],
                            failure_receipt=(value.get("result") or {}).get("cloud_failure"), **rp.SAFE)
            self.root.mkdir(parents=True, exist_ok=True)
            self.archive(task(value["id"]))
            return self.report()

    def archived(self, config, value):
        archive = rp.read(self.root / "archive.json")
        material = c.Registry(config["candidate_registry_name"]).registration(archive["registration_sha256"])["material"]
        j.require(material == dict(schema_version=1, owner_input=None, saved_agent_task=value, authority="research_only",
                                   template=None, snapshot_provenance=provenance(value, None))
                  and archive["task_detail_sha256"] == c.digest(value), "PORTFOLIO_ARCHIVE_CHANGED")
        return archive["registration_sha256"]

    def report(self):
        view = bridge("verify", self.name)
        value = task(view["task_id"])
        self.completed(value, self.intent("fusion"))
        registration = self.archived(self.config(), value)
        bundle = value["result"]["research"]["risk_portfolio"]
        return dict(state="RESEARCH_ONLY", task_id=value["id"], local_parent_task_id=view["context"]["parent_task_id"],
                    local_parent_result_sha256=view["context"]["parent_result_sha256"],
                    result_storage_sha256=view["result_storage_sha256"], verified=True,
                    input_mode="synthetic_test", portfolio=bundle["portfolio"], fusion_receipt=bundle["receipt"],
                    local_risk_receipt=view["local_risk"]["receipt"], registration_sha256=registration,
                    calls=value["calls"], paper_allowed=False, **rp.SAFE)


def provenance(value, store_name):
    j.require(store_name is None, "PORTFOLIO_HAS_OWN_VERSIONED_SOURCE_CONTRACT")
    original = task(value["id"])
    j.require(value == original and value["input"]["scopes"] == [POLICY, "portfolio_fusion_v1"],
              "ORIGINAL_AGENT_TASK_MISMATCH")
    ctx = value["input"]["summary"]
    run = Run(ctx["batch"])
    run.completed(value, run.intent("fusion"))
    f = run.frozen()
    return dict(snapshot_sha256=f["snapshot_ref"], source_day=value["input"]["source_day"], data_mode=f["input_mode"],
                research_task_id=value["id"], input_summary_version=value["input"]["version"],
                frozen_input_sha256=c.digest(value["input"]), expert_input_sha256=ctx["parent_plan_sha256"],
                risk_task_id=str(ctx["parent_task_id"]), risk_result_sha256=ctx["parent_result_sha256"],
                snapshot_verification="ORIGINAL_LOCAL_CPU_PARENT_AND_REAL_FUSION_SYNTHETIC_SOURCE_VERIFIED",
                task_origin="ORIGINAL_AGENT_SQLITE_VERIFIED_BY_RUNNER", restriction="RESEARCH_ONLY",
                eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init-cny", "configure", "preflight", "enable", "once", "disable",
                                          "status", "report", "verify", "inbox", "budget", "capture-model"])
    parser.add_argument("action", nargs="?", choices=["status"])
    parser.add_argument("--name", default="pr19-synthetic-smoke")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "configure":
            j.require(args.config is not None, "FUSION_LOCAL_CONFIG_REQUIRED")
            out = bridge("configure", args.config)
        elif args.command in ("preflight", "enable"):
            check_model(args.name)
            out = bridge(args.command, args.name)
        elif args.command == "once":
            out = Run(args.name).once()
        elif args.command == "inbox":
            from review import Review
            out = Review(args.name, local_fusion=True).inbox()
        elif args.command in ("report", "verify"):
            out = Run(args.name).report()
        else:
            out = bridge(args.command, args.name) if args.command in ("status", "capture-model") else bridge(args.command)
        print(json.dumps(out, ensure_ascii=False, allow_nan=False))
        return 2 if out.get("state") == "BLOCKED" else 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, j.Rejected, c.Rejected):
        error = sys.exception()
        code = str(error) if isinstance(error, (j.Rejected, c.Rejected)) else "LOCAL_FUSION_COMMAND_FAILED"
        print(json.dumps(dict(state="BLOCKED", error_code=code, paper_allowed=False, **rp.SAFE)))
        return 2
