"""One synthetic PR17 loopback + original CNY test Store + PR15/PR62 evidence."""
import argparse
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("test_pr17",ROOT/"scripts/test-deepseek-structured.py")
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
a,cloud=t.a,t.cloud


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--tag",required=True)
    tag=parser.parse_args().tag
    a.require(1<=len(tag)<=48 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in tag),"SYNTHETIC_TAG_INVALID")
    source=ROOT/"state/deepseek-evidence"/tag
    a.require(not source.exists(),"SYNTHETIC_EVIDENCE_ALREADY_EXISTS")
    source.mkdir(parents=True)
    t.Suite.sources=source;t.Suite.base=a.OUTPUT/("pr17-"+tag);t.Suite.counter=0
    t.Suite.dates,_=t.pr16.prior.make_fixture(source)
    suite=t.Suite();root,owner,_=suite.experiment()
    before=cloud.rust("preflight",root)
    suite.enable(root)
    transport=t.loopback(root,suite.wire(root))
    suite.once(root)
    plan=a.read(root/"plan.json");proposals=a.read(root/"round-01/proposals.json")
    verified=a.verify(root)
    cloud.rust("disable-deepseek",root)
    suite.once(root)
    task=cloud.read_task(root,1)
    with closing(sqlite3.connect((owner/"agent.sqlite").as_uri()+"?mode=ro",uri=True)) as db:
        count=db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    value=dict(contract="m2-pr17-synthetic-evidence-v1",fixture="synthetic_90_sessions_original_CNY_test_Store_not_real_money",
        base_sha="e24f30f69b12fa303221ccd4fc6b8ea9084dc989",source_sha=plan["source_sha"],plan_sha=plan["plan_sha"],
        model=plan["cloud"]["model"],parser_sha=plan["cloud"]["parser_sha"],binary_sha=plan["cloud"]["binary_sha"],
        request_sha=a.m.hash_file(root/"cloud/round-01/request.json"),task_id=task["id"],task_input_sha=task["input_sha"],task_result_sha=task["result_sha"],
        ast_sha=[p["ast_sha"] for p in proposals["proposals"].values()],accepted=len(proposals["proposals"]),rejected=len(proposals["rejected"]),
        result_sha=a.m.hash_file(root/"round-01/results.json"),archive_sha=a.m.hash_file(root/"round-01/archive.json"),
        receipt=proposals["cloud_receipt"],verified=verified["verified"],preflight_enabled=before["enabled"],after_once_enabled=cloud.rust("preflight",root)["enabled"],
        call_count_after_duplicate_once=count,transport=transport,**a.m.SAFE,
        real_provider_status="REAL_PROVIDER_NOT_RUN_OWNER_AUTHORIZATION_MISSING",actual_paid_calls=0,actual_paid_micro=0,
        actual_key_content_reads=0,new_tushare_calls=0,tushare_token_reads=0,old_full_data_verifications=0)
    # The model descriptor contains only synthetic grant/budget fixtures, never a credential locator.
    a.put(source/"summary.json",value)
    print(json.dumps(value,ensure_ascii=False,sort_keys=True))


if __name__=="__main__":main()
