"""Owner once entry; read commands neither infer nor recover/mutate Agent tasks."""
import argparse
import contextlib
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from model import Rejected, digest, loads, require, sha_file, verify_model
import runtime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stratide_paths as paths

ROOT = runtime.ROOT
EXE = paths.executable("timesfm-risk-agent")


def common_root():
    return paths.common_root()


def state_root():
    return common_root() / "state/timesfm-cpu"


def bridge(action, value=None):
    require(EXE.is_file(), "LOCAL_BRIDGE_NOT_BUILT")
    p = subprocess.run([str(EXE),action], input=json.dumps(value or {},allow_nan=False).encode(), cwd=ROOT,
                       capture_output=True, timeout=20, env=runtime.clean_env())
    v = loads(p.stdout)
    require(p.returncode == 0, v.get("error_code","LOCAL_BRIDGE_FAILED"))
    return v


def binding():
    path = common_root() / "state/risk-portfolio/agent-binding.json"
    require(path.is_file() and not path.is_symlink(), "CLOUD_AGENT_BINDING_REQUIRED")
    v = loads(path.read_bytes())
    # Rust revalidates the authoritative identity before every task mutation.
    require(Path(v["agent_dir"]).is_dir(), "ORIGINAL_AGENT_STORE_REQUIRED")
    return v


def frozen(descriptor, count=1):
    require(1 <= count <= 8, "RISK_INPUT_SIZE")
    now = dt.datetime.now(dt.timezone.utc)
    day = now.date()
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    end, days = day, []
    while len(days) < 84:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= dt.timedelta(days=1)
    days.reverse()
    while len(days) < 104:
        end += dt.timedelta(days=1)
        if end.weekday() < 5:
            days.append(end.isoformat())
    series = [dict(instrument=f"{600000+i:06}.SH",corporate_actions="SYNTHETIC_NONE_VERIFIED",observations=[
        dict(trade_day=d,available_at=d+"T00:00:00Z",close_fen=10000+3*n+int(30*math.sin(n+i)))
        for n,d in enumerate(days[:84])]) for i in range(count)]
    return dict(schema_version=1,scope="risk_portfolio_v1",policy="risk-portfolio-v1",input_mode="synthetic_test",
                snapshot_ref=digest(dict(series=series,calendar=days)),readiness_ref="SYNTHETIC_ENGINEERING_ONLY",
                as_of=now.isoformat().replace("+00:00","Z"),strategy_version="local-risk-v1",prompt_version="portfolio-json-v1",
                prompt_sha256=descriptor["prompt_sha256"],adapter_sha256=descriptor["adapter_sha256"],calendar=days,
                calendar_provenance="SYNTHETIC_EXCHANGE_SESSION_FIXTURE",series=series,
                opportunities=[dict(instrument=s["instrument"],status="UNKNOWN",evidence=[]) for s in series],
                account_facts="UNKNOWN_NO_ACCOUNT_ORDERS",risk_model=dict(id="local-timesfm-2.5-cpu",fingerprint=descriptor["code_sha256"]),
                fusion_model=dict(id="UNUSED_PR18",fingerprint="0"*64),batch_budget_micro=1,
                risk_recording_sha256="0"*64,fusion_recording_sha256="0"*64)


def batch_path(name):
    require(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}",name) is not None,"LOCAL_BATCH_NAME")
    path = state_root() / name
    require(not path.is_symlink(),"LOCAL_PATH_LINK")
    return path


def read_plan(name):
    path = batch_path(name) / "plan.json"
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2097152,"LOCAL_PLAN_MISSING_OR_SIZE")
    return loads(path.read_bytes())


def task(name, detailed=False):
    plan = read_plan(name)
    # Read-only SQLite, no writer bridge or automatic recovery.
    b = binding()
    path = Path(b["agent_dir"]) / "agent.sqlite"
    require(not path.is_symlink(),"LOCAL_PATH_LINK")
    with contextlib.closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as db:
        db.row_factory = sqlite3.Row
        require(db.execute("PRAGMA application_id").fetchone()[0] == 1397899569,"ORIGINAL_AGENT_SCHEMA_REQUIRED")
        meta = dict(db.execute("SELECT key,value FROM meta WHERE key IN ('risk_portfolio_authority_id','risk_portfolio_settings_path')"))
        require(meta.get("risk_portfolio_authority_id") == b["authority_id"] and meta.get("risk_portfolio_settings_path") == b["settings_path"],"CLOUD_AGENT_AUTHORITY_CHANGED")
        row = db.execute("SELECT * FROM tasks WHERE trigger_key=?",("timesfm-cpu-v1:"+name,)).fetchone()
        if not row:
            return dict(state="FROZEN_NOT_RUN",billing="LOCAL_NO_BILLING")
        require(row["provider_id"] == "local-timesfm-2.5-cpu" and loads(row["input"])["summary"]["plan"] == plan,"LOCAL_TASK_CHANGED")
        require(db.execute("SELECT count(*) FROM calls WHERE task_id=?",(row["id"],)).fetchone()[0] == 0,"LOCAL_BILLING_INVALID")
        if detailed:
            return dict(id=str(row["id"]),status=row["status"],request=loads(row["request"]),
                        input=loads(row["input"]),provider_id=row["provider_id"],provider_hash=row["provider_hash"],
                        result=loads(row["result"]) if row["result"] else None,calls=[])
        return dict(id=str(row["id"]),state=row["status"],reason=row["reason"],provider_hash=row["provider_hash"],
                    result=loads(row["result"]) if row["result"] else None,billing="LOCAL_NO_BILLING",paper_allowed=False,live_allowed=False)


def once(name, runner=runtime.run):
    plan = read_plan(name)
    require(plan["manifest_sha256"] == digest(verify_model(ROOT / "models/timesfm-2.5")),"LOCAL_MODEL_CHANGED_NEW_TASK_REQUIRED")
    projection = bridge("project",plan)
    runtime.command(plan["threads"])  # Reject unsupported hosts before creating a task.
    with runtime.lock(state_root()/"worker.lock"), runtime.lock(Path(binding()["agent_dir"])/"agent.lock"):
        prior = bridge("begin",plan)
        if prior["status"] != "local_running":
            return task(name)
        receipt = dict(id=int(prior["id"]),plan=plan)
        try:
            response = runner(projection["worker_request_json"].encode())
            require(read_plan(name) == plan and digest(verify_model(ROOT/"models/timesfm-2.5")) == plan["manifest_sha256"],"LOCAL_INPUT_CHANGED")
            bridge("complete",dict(receipt,response=response))
        except BaseException as e:
            code = str(e) if isinstance(e,Rejected) and re.fullmatch("[A-Z_]{1,80}",str(e)) else "WORKER_FAILED"
            bridge("fail",dict(receipt,failure=code))
            if isinstance(e,KeyboardInterrupt):
                raise
        return task(name)


def verify(name):
    out = task(name)
    require(out["state"] == "completed","LOCAL_TASK_INCOMPLETE")
    plan = read_plan(name)
    require(digest(verify_model(ROOT/"models/timesfm-2.5")) == plan["manifest_sha256"],"LOCAL_MODEL_CHANGED_NEW_TASK_REQUIRED")
    bundle = out["result"]["research"]["risk_portfolio"]
    require(bundle["receipt"]["code_sha256"] == plan["code_sha256"]
            and bundle["receipt"]["manifest_sha256"] == plan["manifest_sha256"]
            and bundle["authority"] == "RESEARCH_ONLY" and bundle["eligibility"] == "ELIGIBILITY_DENIED"
            and bundle["paper_allowed"] is False and bundle["live_allowed"] is False,"LOCAL_RESULT_CHANGED")
    require(bridge("decode",dict(plan=plan,response=out["result"]["worker_response"])) == bundle,"LOCAL_RESULT_CHANGED")
    if plan.get("history"):
        bridge("verify-result",out["result"])
        require(str(out["result"]["task_id"]) == out["id"],"LOCAL_TASK_CHANGED")
    out["verified"] = True
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command",choices=["descriptor","enable","disable","synthetic-freeze","once","status","report","verify","preflight","stop","bench","historical-preflight","historical-freeze"])
    parser.add_argument("--name",default="local-risk")
    parser.add_argument("--series",type=int,default=1)
    parser.add_argument("--max-context",type=int,choices=[256,512],default=256)
    parser.add_argument("--batch-size",type=int,choices=[1,2,3,4],default=1)
    parser.add_argument("--development-cpu-diagnostic",action="store_true")
    parser.add_argument("--v1-root",type=Path)
    parser.add_argument("--v2-root",type=Path)
    parser.add_argument("--symbols")
    parser.add_argument("--as-of")
    parser.add_argument("--context",type=int,default=84)
    args = parser.parse_args()
    try:
        if args.command in ("historical-preflight", "historical-freeze"):
            from history import read
            require(args.v1_root is not None and args.v2_root is not None and args.symbols and args.as_of,
                    "HISTORY_EXPLICIT_SOURCE_SYMBOLS_AS_OF_REQUIRED")
            descriptor = bridge("descriptor")
            f, history = read(descriptor,args.v1_root,args.v2_root,args.symbols.split(","),args.as_of,args.context)
            manifest = verify_model(ROOT/"models/timesfm-2.5")
            plan = dict(batch=args.name,frozen=f,history=history,manifest_sha256=digest(manifest),
                        code_sha256=descriptor["code_sha256"],max_context=args.max_context,
                        batch_size=args.batch_size,threads=2)
            bridge("project",plan)
            if args.command == "historical-preflight":
                with runtime.lock(state_root()/"worker.lock"):
                    isolation = runtime.run(b"probe")
                out = dict(state="PARTIAL",quality=history["payload"]["quality"],
                           input_sha256=history["payload_sha256"],isolation=isolation,billing="LOCAL_NO_BILLING",
                           cloud_egress="REAL_MARKET_DATA_EGRESS_DENIED")
            else:
                # Exclusive private publication; incomplete writes cannot launch a task.
                path = batch_path(args.name)
                path.mkdir(parents=True,exist_ok=False)
                raw = (json.dumps(plan,separators=(",",":"),allow_nan=False)+"\n").encode()
                require(len(raw) <= 2097152,"LOCAL_PLAN_MISSING_OR_SIZE")
                with (path/"plan.json").open("xb") as file:
                    os.chmod(path/"plan.json",0o600)
                    file.write(raw)
                    file.flush()
                    os.fsync(file.fileno())
                out = dict(state="FROZEN_NOT_RUN",input_sha256=history["payload_sha256"],
                           quality=history["payload"]["quality"],billing="LOCAL_NO_BILLING",
                           historical_pit_status="NOT_VERIFIED",cloud_egress="REAL_MARKET_DATA_EGRESS_DENIED")
        elif args.command == "descriptor":
            out = bridge("descriptor")
        elif args.command in ("enable","disable"):
            out = bridge(args.command)
        elif args.command == "synthetic-freeze":
            descriptor = bridge("descriptor")
            plan = dict(batch=args.name,frozen=frozen(descriptor,args.series),manifest_sha256=digest(verify_model(ROOT/"models/timesfm-2.5")),
                        code_sha256=descriptor["code_sha256"],max_context=args.max_context,batch_size=args.batch_size,threads=2)
            bridge("project",plan)
            path = batch_path(args.name)
            path.mkdir(parents=True,exist_ok=False)
            (path/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
            out = dict(state="FROZEN_NOT_RUN",billing="LOCAL_NO_BILLING")
        elif args.command == "once":
            out = once(args.name)
            if out["state"] == "completed" and read_plan(args.name).get("history"):
                from history import archive
                out["archive"] = archive(args.name)
        elif args.command in ("status","report","verify"):
            out = task(args.name)
            if args.command == "verify" and out["state"] == "completed":
                out = verify(args.name)
            if args.command in ("report","verify") and out["state"] == "completed" and read_plan(args.name).get("history"):
                from history import archived
                out["archive"] = archived(args.name)
        elif args.command == "preflight":
            manifest = verify_model(ROOT/"models/timesfm-2.5")
            with runtime.lock(state_root()/"worker.lock"):
                out = dict(model_manifest_sha256=digest(manifest),**runtime.run(b"probe"))
        elif args.command == "stop":
            if (common_root()/"state/risk-portfolio/agent-binding.json").is_file():
                bridge("disable")
            out = runtime.stop()
        else:
            from benchmark import benchmark
            with runtime.lock(state_root()/"worker.lock"):
                out = benchmark(args.development_cpu_diagnostic)
        print(json.dumps(out,ensure_ascii=False,allow_nan=False))
        return 2 if out.get("state") in ("failed","cancelled") else 0
    except (Rejected,OSError,ValueError,KeyError,TypeError,sqlite3.Error,subprocess.SubprocessError) as e:
        print(json.dumps(dict(coverage=getattr(e,"coverage",None),
                              error_code=str(e) if isinstance(e,Rejected) else "LOCAL_COMMAND_FAILED",
                              billing="LOCAL_NO_BILLING",paper_allowed=False,live_allowed=False)))
        return 2
