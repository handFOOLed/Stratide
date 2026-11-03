"""Developer evidence only: explicit isolated TST Owner, loopback and optional one local history pass."""
from contextlib import closing
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import autonomous_research as a
import cloud_structured as cloud

spec=importlib.util.spec_from_file_location("fixture",ROOT/"scripts/test-cloud-structured.py")
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag",required=True)
    parser.add_argument("--real-locators",type=Path)
    args=parser.parse_args()
    a.require(args.tag.replace("-","").isalnum() and len(args.tag)<=50,"EVIDENCE_TAG")
    local=ROOT/"state/cloud-structured-evidence"/args.tag
    a.require(not local.exists(),"EVIDENCE_TAG_ALREADY_EXISTS")
    local.mkdir(parents=True)
    evidence=ROOT/"docs/evidence/m2-pr16"
    evidence.mkdir(parents=True,exist_ok=True)
    commands=[]
    replacements={str(ROOT):"<WORKTREE>",sys.executable:"python"}
    def redact(text):
        for private,label in sorted(replacements.items(),key=lambda p:-len(p[0])):text=text.replace(private,label)
        return text
    def save(name,value):
        (evidence/name).write_bytes(a.canonical(value)+b"\n")
    def command(label,argv):
        started=time.perf_counter()
        run=subprocess.run([str(x) for x in argv],cwd=ROOT,capture_output=True)
        (local/f"{label}.stdout").write_bytes(run.stdout)
        (local/f"{label}.stderr").write_bytes(run.stderr)
        commands.append(dict(label=label,argv=[redact(str(x)) for x in argv],exit=run.returncode,seconds=round(time.perf_counter()-started,3)))
        save("commands.json",commands)
        a.require(run.returncode==0,"EVIDENCE_COMMAND_FAILED_"+label)
        return json.loads(run.stdout.decode().splitlines()[-1])
    owner=local/"owner"
    fixture.init_owner(owner)
    commands.append(dict(label="explicit-original-synthetic-owner",argv=["target/debug/stratided","--agent-init-fake","<DISPOSABLE_TST_OWNER>"],exit=0))
    def run_research(label,v1,v2,start,end,versions,config,loopback=False):
        out=a.OUTPUT/f"{args.tag}-{label}"
        a.require(not out.exists(),"NEW_EXPERIMENT_REQUIRED")
        cfg=local/f"{label}-config.json";cfg.write_bytes(a.canonical(dict(research_config=config,limits=dict(rounds=1))))
        base=[sys.executable,"-I","-B","scripts/autonomous-research.py"]
        command(label+"-init",base+["init","--source","recorded_cloud","--agent-dir",owner,"--configure-recorded",
            "--v1-root",v1,"--v2-root",v2,"--v1-version",versions[0],"--v2-version",versions[1],
            "--start",start,"--end",end,"--config",cfg,"--out",out,"--authorize-local"])
        frozen=a.read(out/"plan.json");source=cloud.expected_source(frozen,1)
        recording=local/f"{label}-wire.json";recording.write_bytes(fixture.wire(source,frozen["config"]["max_positions"]))
        transport=fixture.loopback_task(out,recording) if loopback else dict(loopback_http_calls=0,external_http_calls=0)
        print(json.dumps(dict(stage=label+"-evaluating",plan_sha=frozen["plan_sha"],transport=transport)),flush=True)
        result=command(label+"-once",base+["once","--out",out,"--recording",recording])
        verify=command(label+"-verify",base+["verify","--out",out])
        command(label+"-status",base+["status","--out",out]);command(label+"-history",base+["history","--out",out])
        command(label+"-report",base+["report","--out",out])
        before={p.relative_to(out).as_posix():a.m.hash_file(p) for p in out.rglob("*") if p.is_file()}
        command(label+"-repeat-once",base+["once","--out",out])
        a.require(before=={p.relative_to(out).as_posix():a.m.hash_file(p) for p in out.rglob("*") if p.is_file()},"REPEAT_MUTATED_RESULT")
        run=a.read(out/"round-01/attempts/01-end.json")
        record=a.read(out/"round-01/proposals.json")
        audit=a.read(out/"cloud/round-01/receipt.json")
        summary=dict(**a.m.SAFE,mode="recorded_cloud",model_capability="NOT_VERIFIED_SYNTHETIC_RECORDING",status=result["status"],
            plan_sha=frozen["plan_sha"],source_sha=frozen["source_sha"],code_sha=frozen["code_sha"],model=frozen["cloud"]["model"],
            ast_sha=[p["ast_sha"] for p in record["proposals"].values()],cloud_receipt=audit,transport=transport,
            result=result["rounds"][0],verification=verify,repeat_unchanged=True,
            resources={k:run[k] for k in ("wall_seconds","cpu_seconds","peak_rss_bytes","workers","threads","python")},
            old_source_receipts_unchanged=run["source_file_receipts_before"]==run["source_file_receipts_after"],
            real_model_calls=0,paid_calls=0,new_market_requests=0,token_reads=0)
        save(label+"-summary.json",summary)
        print(json.dumps(dict(stage=label+"-complete",candidates=len(record["proposals"]),output_sha=result["rounds"][0]["output_sha"],
            sessions=result["rounds"][0]["result"]["coverage"]["processed_sessions"],seconds=run["wall_seconds"])),flush=True)
    dates,_=fixture.prior.make_fixture(local/"synthetic")
    config=dict(max_positions=2,windows=[dict(name="development",role="development",start=dates[0],end=dates[69]),
        dict(name="validation",role="validation",start=dates[70],end=dates[79]),
        dict(name="exposed",role="evaluation",start=dates[80],end=dates[-1],train_end=dates[79])])
    run_research("synthetic",local/"synthetic/v1",local/"synthetic/v2",dates[0],dates[-1],[90,360],config,True)
    if args.real_locators:
        # Only the existing private locator and the small prior archive receipts are read.
        locations=a.read(args.real_locators)
        replacements.update({locations["v1"]:"<V1_ROOT>",locations["v2"]:"<V2_ROOT>"})
        old={p.name+str(p.parent.name):a.m.hash_file(p) for p in args.real_locators.parent.glob("round-*/archive.json")}
        if all((Path(p)/"warehouse.sqlite").is_file() for p in locations.values()):
            run_research("real",locations["v1"],locations["v2"],"20211101","20261030",[1212,4848],{})
            a.require(old=={p.name+str(p.parent.name):a.m.hash_file(p) for p in args.real_locators.parent.glob("round-*/archive.json")},"OLD_ARCHIVE_CHANGED")
            save("old-archive-receipts.json",dict(before=old,after=old,scope="PR15_SMALL_ARCHIVE_RECEIPTS_ONLY_NO_OLD_DATA_HASH_SCAN"))
        else:save("real-summary.json",dict(**a.m.SAFE,state="BLOCKED",reason="EXISTING_LOCAL_HISTORY_UNREADABLE"))
    with closing(sqlite3.connect(owner/"agent.sqlite")) as db:
        totals=db.execute("SELECT COUNT(*),SUM(settled_micro),SUM(CASE WHEN state NOT IN ('settled','no_charge') THEN maximum_micro ELSE 0 END) FROM calls").fetchone()
    save("run-totals.json",dict(original_owner="EXPLICIT_DISPOSABLE_TST_USING_ORIGINAL_INIT",calls=totals[0],settled_micro=totals[1],
        unknown_reserved_micro=totals[2],currency="TST",actual_paid_calls=0,external_data_sends=0,new_market_requests=0))
    return 0


if __name__=="__main__":raise SystemExit(main())
