"""Real pinned weights only. Never uses a test double or writes an Agent task."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research/timesfm_cpu"))
import benchmark
import cli
import model
import runtime


def run():
    manifest=model.verify_model(runtime.ROOT/"models/timesfm-2.5")
    desc=cli.bridge("descriptor")
    diagnostic=sys.platform!="linux"
    results=[]
    with runtime.lock(cli.state_root()/"worker.lock"):
        for count in (1,4,8):
            plan=dict(batch=f"real-cpu-{count}",frozen=cli.frozen(desc,count),manifest_sha256=model.digest(manifest),
                      code_sha256=desc["code_sha256"],max_context=256,batch_size=1,threads=2)
            projected=cli.bridge("project",plan)
            request=json.loads(projected["worker_request_json"])
            response=benchmark.run_request(request,diagnostic,projected["worker_request_json"].encode())
            bundle=cli.bridge("decode-development" if diagnostic else "decode",dict(plan=plan,response=response))
            denied=False
            if diagnostic:
                try:
                    cli.bridge("decode",dict(plan=plan,response=response))
                except model.Rejected as e:
                    denied=str(e)=="LOCAL_ISOLATION_REQUIRED"
                model.require(denied,"DEVELOPMENT_MUST_NOT_COMPLETE_PRODUCTION")
            model.require(len(bundle["risk_experts"])==count and bundle["paper_allowed"] is False
                          and bundle["live_allowed"] is False,"RISK_RESULT_CONTRACT")
            results.append(dict(series=count,input_mode="synthetic_test",backend="REAL_TIMESFM_2_5_CPU",
                                production_task_created=False,production_decode_denied=denied,
                                request_sha256=response["request_sha256"],result_sha256=model.digest(bundle),
                                metrics=response["metrics"],risk_result=bundle))
    return dict(label="DEVELOPMENT_CPU_DIAGNOSTIC" if diagnostic else "LINUX_CPU_ENGINEERING_TEST",
                N100_ACCEPTANCE="NOT_VERIFIED",runs=results)


if __name__=="__main__":
    try:
        print(json.dumps(run(),allow_nan=False))
    except model.Rejected as e:
        print(json.dumps(dict(state="NOT_RUN_MODEL_UNAVAILABLE" if str(e)=="MODEL_NOT_PROVISIONED" else "FAILED",error_code=str(e))))
        raise SystemExit(2)
