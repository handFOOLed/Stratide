"""Local Dashboard bridge. Fixed operations, original tasks/budget/Registry only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("DESKTOP_SOURCE_INVALID")
    return json.loads(path.read_bytes())


def command(script, *args):
    p = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / script), *map(str, args)],
                       cwd=ROOT, capture_output=True, check=False)
    try:
        v = json.loads(p.stdout)
    except ValueError:
        raise ValueError("DESKTOP_COMMAND_OUTPUT_INVALID") from None
    if p.returncode:
        raise ValueError(v.get("error_code", v.get("reason", "DESKTOP_COMMAND_REJECTED")))
    return v


def snapshot(config):
    import portfolio_research as rp
    studies = []
    for name in config["timesfm_batches"]:
        try:
            # Status is read-only; old model/code rotation cannot rerun a study.
            v = command("timesfm-cpu.py", "status", "--name", name)
            r = v.get("result") or {}
            risk = r.get("research", {}).get("risk_portfolio", {})
            sys.path.insert(0,str(ROOT/"research/timesfm_cpu"))
            import cli as cpu
            plan=cpu.read_plan(name)
            received=max(o["available_at"] for series in plan["frozen"]["series"] for o in series["observations"])
            risk_rows=[dict(instrument=e["instrument"],as_of=e["as_of"],forecasts=e["volatility_forecast"],
                naive=e["baseline_comparison"]["naive"],ewma=e["baseline_comparison"]["ewma"],
                quality=e["quality_blockers"]) for e in risk.get("risk_experts",[])]
            studies.append(dict(id="timesfm:"+name, name=name, kind="TimesFM CPU", state=v.get("state"),
                mode=r.get("input_mode", "synthetic_test"), task_id=v.get("id"),
                result_sha256=rp.digest(r) if r else None,
                received_at=received,risk_rows=risk_rows,summary=risk, billing="LOCAL_NO_BILLING", reason=v.get("reason")))
        except (ValueError, OSError) as e:
            studies.append(dict(id="timesfm:"+name,name=name,kind="TimesFM CPU",state="BLOCKED",reason=str(e)))
    for name in config["fusion_batches"]:
        try:
            v = command("local-timesfm-fusion.py", "status", "--name", name)
            # The verified bridge already projects the immutable research receipt.
            result=v.get("result") or {}
            bundle=result.get("research",{}).get("risk_portfolio",{})
            portfolio=bundle.get("portfolio")
            studies.append(dict(id="fusion:"+name,name=name,kind="DeepSeek Fusion",state=v.get("state"),
                mode="synthetic_test",portfolio=portfolio,summary=v,billing="ESTIMATED_NOT_VERIFIED_BILL",reason=v.get("error_code")))
        except (ValueError, OSError) as e:
            studies.append(dict(id="fusion:"+name,name=name,kind="DeepSeek Fusion",state="BLOCKED",reason=str(e)))
    evaluations = []
    for operation in config["operations"]:
        if operation["kind"]=="recorded_fusion":
            try:
                value=rp.ReviewSource(operation["batch"]).report()
                studies.append(dict(id="recorded:"+operation["batch"],name=operation["batch"],kind="离线录制 Fusion",state=value["state"],
                    mode="synthetic_test",portfolio=value.get("portfolio"),summary=value,billing="NOT_BILLED"))
            except (ValueError,OSError) as e:
                studies.append(dict(id="recorded:"+operation["batch"],name=operation["batch"],kind="离线录制 Fusion",state="BLOCKED",reason=str(e)))
    for index, path in enumerate(config["evaluation_dirs"]):
        try:
            import risk_evaluation as re
            summary = re.verify(path)
            report=read(Path(path)/"report.json")
            split_rows=[]
            for name,split in report["splits"].items():
                metrics=[dict(model=model,horizon=h,**values) for model,horizons in split["metrics"].items() for h,values in horizons.items() if values is not None]
                split_rows.append(dict(name=name,samples=split["samples"],scored=split["scored"],status=split["status"],coverage=split["coverage"],metrics=metrics))
            # Report remains local: it is never passed into a cloud task summary.
            evaluations.append(dict(id=str(index),name=Path(path).name,state="verified_local_integrity",
                verdict=report["hypothesis_verdict"],split_rows=split_rows,summary=summary,report=report))
        except (ValueError, OSError, RuntimeError) as e:
            evaluations.append(dict(id=str(index),name=Path(path).name,state="BLOCKED",reason=str(e)))
    candidates=[]
    import candidates as registry
    for directory in config["registry_dirs"]:
        path=Path(directory)
        try:
            registry.no_links(path)
            store=registry.Registry.__new__(registry.Registry)
            store.root=path
            entries=sorted((path/"registrations").glob("*.json"))
            if len(entries)>50:raise ValueError("DESKTOP_REGISTRY_LIMIT")
            for entry in entries:
                record=store.registration(entry.stem)
                m=record["material"]
                task=m.get("saved_agent_task") or {}
                candidates.append(dict(registry=path.name,registration_sha256=entry.stem,
                    state="RESEARCH_ONLY" if m["template"] is None else "REGISTERED",
                    template=m["template"],mode=task.get("input",{}).get("mode"),task_id=task.get("id"),
                    registered_at=record["registered_at"],paper_allowed=False,live_allowed=False))
            entries=sorted((path/"candidates").iterdir()) if (path/"candidates").exists() else []
            if len(entries)>50:raise ValueError("DESKTOP_REGISTRY_LIMIT")
            for entry in entries:
                if not entry.is_dir():continue
                record=store.candidate(entry.name)
                candidates.append(dict(registry=path.name,candidate_sha256=entry.name,state="FROZEN_CANDIDATE",
                    registration_sha256=record["material"]["registration_sha256"],
                    data_status=record["material"]["data"]["status"],template=record["material"]["template"],
                    paper_allowed=False,live_allowed=False))
        except (ValueError,OSError,KeyError) as e:
            candidates.append(dict(registry=path.name,state="BLOCKED",reason=str(e)))
    evidence = []
    for index, path in enumerate(config["evidence_files"]):
        try:
            v = read(path)
            evidence.append(dict(id=str(index),name=Path(path).name,state="stored_evidence_not_qualification",
                sha256=__import__("hashlib").sha256(Path(path).read_bytes()).hexdigest(),report=v))
        except (ValueError, OSError) as e:
            evidence.append(dict(id=str(index),name=Path(path).name,state="BLOCKED",reason=str(e)))
    from evidence_audit import blockers
    import market_eod
    market = market_eod.Market(market_eod.default_root())
    if market.path.is_file():
        try:
            market_status = market.report()
            # Dashboard receives counts/state only; security names, prices and
            # raw provider responses stay in the local source/CLI.
            latest = market_status["latest"]
            market_status["latest"] = None if latest is None else {k: latest[k] for k in (
                "source_day", "state", "expected_market", "actual_quoted", "market_explained", "market_coverage_bps",
                "research_denominator", "eligible_symbols", "categories", "available_at", "source_states",
                "blockers", "snapshot_sha256", "catalog_state", "catalog_scopes", "market_denominator_verified")}
            if market_status["latest"] is not None:
                market_status["latest"]["eligible_count"] = len(market_status["latest"].pop("eligible_symbols"))
        except (market_eod.Error, OSError) as error:
            market_status = dict(state="BLOCKED", reason=str(error), latest=None, last_successful_date=None, gaps=[])
    else:
        market_status = dict(state="NOT_CONFIGURED", latest=None, last_successful_date=None, gaps=[])
    backup=dict(state="not_configured")
    if config.get("backup_manifest"):
        try:backup=command("local-backup.py","verify","--bundle",str(Path(config["backup_manifest"]).parent))
        except (ValueError,OSError) as e:backup=dict(state="BLOCKED",reason=str(e))
    return dict(schema_version=1,state="ready",studies=studies,evaluations=evaluations,candidates=candidates,evidence=evidence,admission=blockers(),backup=backup,market=market_status,
        historical_pit_status="NOT_VERIFIED",opening_observed="NOT_VERIFIED",trading_eligibility="BLOCKED",
        paper_allowed=False,live_allowed=False,real_market_cloud_egress=False,
        refresh="READ_ONLY_NO_INFERENCE",deployment="WINDOWS_LOCAL_WSL2_OPTIONAL",n100="DEFERRED_NOT_V1_GATE")


def run(config, operation):
    op = next((v for v in config["operations"] if v["id"] == operation), None)
    if op is None:
        raise ValueError("DESKTOP_OPERATION_NOT_FOUND")
    kind, name = op["kind"], op["batch"]
    if kind == "local_timesfm":
        # Explicit Owner approval enables only the existing local CPU gate.
        command("timesfm-cpu.py", "enable")
        result = command("timesfm-cpu.py", "once", "--name", name)
        if result.get("state") != "completed":
            raise ValueError(result.get("reason", "LOCAL_TASK_INCOMPLETE"))
    elif kind == "synthetic_fusion":
        # Do not enable or extend an original consumed cloud grant. The original
        # Rust gate checks synthetic provenance, unconsumed authorization, price
        # validity and shared CNY budget before it reads any key or sends bytes.
        import local_fusion as lf
        lf.check_model(name)
        result = command("local-timesfm-fusion.py", "once", "--name", name)
        if result.get("state") == "BLOCKED":
            raise ValueError(result.get("error_code", "FUSION_BLOCKED"))
    elif kind == "recorded_fusion":
        # Existing TST-only recorded adapter, no network or real billing grant.
        result = command("risk-portfolio.py", "--name", name, "once")
        if result.get("state")!="RESEARCH_ONLY":raise ValueError(result.get("reason","RECORDED_FUSION_INCOMPLETE"))
    elif kind == "risk_evaluation":
        matches = [p for p in config["evaluation_dirs"] if Path(p).name == name]
        if len(matches) != 1:
            raise ValueError("EVALUATION_SOURCE_NOT_CONFIGURED")
        result = command("risk-evaluate.py", "run", "--out", matches[0])
    else:
        raise ValueError("DESKTOP_OPERATION_INVALID")
    return dict(state="completed",operation=operation,source="ORIGINAL_RESEARCH_GATE",paper_allowed=False,live_allowed=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["snapshot", "run", "binding", "stop"])
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--operation")
    a = p.parse_args()
    try:
        config = read(a.config)
        if config["schema_version"] != 1 or Path(config["workspace"]).resolve() != ROOT:
            raise ValueError("DESKTOP_WORKSPACE_INVALID")
        if a.action=="binding":
            import portfolio_research as rp
            with rp.agent_db():result=rp.binding()
        elif a.action=="stop":result=command("timesfm-cpu.py","stop")
        else:result = snapshot(config) if a.action == "snapshot" else run(config, a.operation)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except Exception as e:
        # Boundary error response; private paths, traceback and provider replies
        # never become log output. A rejected command stays rejected.
        text=str(e)
        code=text if text and len(text)<=100 and all(c.isupper() or c.isdigit() or c=="_" for c in text) else "DESKTOP_SOURCE_OR_COMMAND_FAILED"
        print(json.dumps(dict(state="BLOCKED",error_code=code)))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
