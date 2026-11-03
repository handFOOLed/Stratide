"""PR16 source adapter. Original Rust task/cost authority; PR15 AST and evaluator."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess

import autonomous_dsl as dsl
import multistock_research as m

ROOT = Path(__file__).resolve().parents[1]
require, Error, canonical, sha = m.require, m.Error, m.canonical, m.sha
RUST_FILES = ("research/agent/src/structured.rs", "research/agent/src/service.rs", "research/agent/src/provider.rs",
              "research/agent/src/config.rs", "research/agent/src/lib.rs", "research/agent/src/risk_binding.rs",
              "research/agent/src/budget.rs", "research/agent/src/store.rs", "research/agent/src/bin/structured-research-agent.rs")
FILES = ("research/cloud_structured.py", "research/structured-grammar-v1.json", *RUST_FILES)
SCOPE = "cloud_structured_research_v1"


def binary():
    path = ROOT/"target/debug/structured-research-agent.exe"
    if not path.exists():
        path = path.with_suffix("")
    require(path.is_file(), "BUILD_STRUCTURED_RESEARCH_AGENT_FIRST")
    return path


def rust(command, root, *args):
    run = subprocess.run([str(binary()), command, str(root), *map(str,args)], cwd=ROOT,
                         capture_output=True, timeout=120, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    try:
        value = json.loads(run.stdout)
    except (ValueError, UnicodeError):
        raise Error("ORIGINAL_AGENT_BRIDGE_FAILED") from None
    require(run.returncode == 0, value.get("reason", "ORIGINAL_AGENT_BRIDGE_FAILED"))
    return value


def configuration(root, agent_dir, mode, model_id="structured-recorded", configure_recorded=False):
    require(mode == "recorded_cloud", "AUTHORIZED_CLOUD_BLOCKED_OWNER_PROVIDER_DATA_PERMISSION_REQUIRED")
    require(agent_dir is not None, "EXISTING_OWNER_AGENT_REQUIRED")
    root = Path(root).absolute()
    rust("bind", root, Path(agent_dir).absolute())
    if configure_recorded:
        rust("configure-recorded", root)
    model = rust("descriptor", root, model_id)
    require(model["currency"] == "TST" and model["transport"] == "recorded", "RECORDING_IS_NOT_CLOUD_AUTHORIZATION")
    return dict(mode=mode, model=model, authority_id=model["authority_id"], parser_sha=m.hash_file(ROOT/"research/cloud_structured.py"),
                binary_sha=m.hash_file(binary()), summary_mode="synthetic_test", real_provider_enabled=False)


def expected_source(frozen, n):
    c=frozen["cloud"]
    return dict(kind="rust_agent_structured_v1",task_ref=f"cloud-structured-v1:{frozen['plan_sha']}:{n}",
        plan_sha=frozen["plan_sha"],round=n,producer_sha=c["model"]["adapter_sha"],model_sha=c["model"]["fingerprint"],
        prompt_sha=c["model"]["prompt_sha"],parser_sha=c["parser_sha"])


def grammar():
    value=json.loads((ROOT/"research/structured-grammar-v1.json").read_bytes())
    require(value["version"]==dsl.VERSION and value["features"]==dsl.UNITS and value["limits"]==dsl.LIMITS,"GRAMMAR_VALIDATOR_VERSION_MISMATCH")
    return value


def output_contract():
    return dict(contract="cloud-structured-response-v1",proposal_contract="structured-research-proposal-v1",authority="RESEARCH_ONLY",
        candidate_fields=["contract","source","hypothesis","ast","authority","constraints","counterexample"],
        refusal="null_or_short_reason",text_limit=1000)


def request(frozen,n,feedback=None):
    config=frozen["config"]
    dev=next(w for w in config["windows"] if w["role"]=="development")
    # This issue sends no real research/data summary. Counts are explicitly synthetic;
    # development feedback is the existing PR15 projection, never the result object.
    stats=dict(mode="synthetic_test",role="development",start=dev["start"],end=dev["end"],
               observed_sessions=0,universe_count=0,missing_count=0,prior_failure_count=0,feedback=None)
    if feedback is not None:
        require(feedback["role"]=="development" and feedback["evidence_allowed_for_next_round"]=="DEVELOPMENT_ONLY",
                "NON_DEVELOPMENT_FEEDBACK_DENIED")
        stats["feedback"]={k:feedback[k] for k in ("role","reduce_exposure","evaluated","failed_or_negative")}
        stats["prior_failure_count"]=feedback["failed_or_negative"]
    return dict(response_source=expected_source(frozen,n),
        research_boundary=dict(source_sha=frozen["source_sha"],dataset_versions=frozen["source_refs"]["version_bounds"],
            windows=config["windows"],cost_scenarios=config["cost_scenarios"],max_positions=config["max_positions"],
            candidate_limit=frozen["limits"]["candidates"],training_knowledge="UNKNOWN_POSSIBLY_TRAINED_ON_EXPOSED_HISTORY",
            historical_pit_status="NOT_VERIFIED",target="next_session_open_ex_post_fractional_exposure"),
        development_summary=stats,grammar=grammar(),output_contract=output_contract())


def prepare_request(root,frozen,n,feedback=None):
    import autonomous_research as a
    value=request(frozen,n,feedback)
    a.put(root/f"cloud/round-{n:02}/request.json",value)
    return value


def freeze_boundary(root,frozen):
    import autonomous_research as a
    # No per-day source receipts, paths, account facts or dataset rows are copied.
    projection={k:frozen[k] for k in ("plan_sha","proposer","source_sha","limits","cloud")}
    projection["source_refs"]=dict(version_bounds=frozen["source_refs"]["version_bounds"])
    projection["config"]={k:frozen["config"][k] for k in ("windows","cost_scenarios","max_positions")}
    a.put(root/"cloud/boundary.json",projection)


def parse_response(raw,source,cap,limit,seen=(),refused=False):
    require(type(raw) is bytes and len(raw)<=49152,"CLOUD_RESPONSE_SIZE")
    require(not refused,"PROVIDER_REFUSED_OR_TRUNCATED")
    value=json.loads(raw,object_pairs_hook=dsl.unique,parse_constant=lambda _:require(False,"NONFINITE_JSON"))
    dsl.fields(value,"contract source candidates refusal")
    require(value["contract"]=="cloud-structured-response-v1" and value["source"]==source,"CLOUD_RESPONSE_SOURCE_MISMATCH")
    require(type(value["candidates"]) is list and len(value["candidates"])<=limit,"CANDIDATE_RESOURCE_LIMIT")
    require(value["refusal"] is None or (type(value["refusal"]) is str and 1<=len(value["refusal"])<=1000),"CLOUD_REFUSAL_SCHEMA")
    require(not value["refusal"] or not value["candidates"],"CLOUD_REFUSAL_WITH_CANDIDATES")
    accepted,rejected,known={},[],set(seen)
    for candidate in value["candidates"]:
        encoded=canonical(candidate)
        try:
            p=dsl.parse_proposal(encoded,source,cap,cloud=True)
            require(p["ast_sha"] not in known,"DUPLICATE_CANDIDATE")
            known.add(p["ast_sha"])
            accepted[f"candidate_{len(accepted)+1:02}"]=p
        except (Error,ValueError,TypeError,KeyError) as exc:
            rejected.append(dict(proposal_sha=sha(encoded),state="REJECTED",reason=str(exc) if isinstance(exc,Error) else "INVALID_PROPOSAL"))
    if value["refusal"]:
        rejected.append(dict(proposal_sha=sha(raw),state="REJECTED",reason="MODEL_EXPLICIT_REFUSAL"))
    return accepted,rejected


def read_task(root,n):
    """Read-only: no Agent open/recovery, config changes, or source database reads."""
    import autonomous_research as a
    context=root/f"cloud/round-{n:02}/context.json"
    if not context.exists(): return None
    ctx=a.read(context)
    bound=a.read(root/"agent-binding.json")
    path=Path(bound["agent_dir"])/"agent.sqlite"
    m.data.v1.no_links(path)
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as db:
        db.row_factory=sqlite3.Row
        trigger=f"cloud-structured-v1:{ctx['plan_sha']}:{n}"
        row=db.execute("SELECT * FROM tasks WHERE trigger_key=?",(trigger,)).fetchone()
        if row is None: return None
        require(json.loads(row["input"])["summary"]==ctx,"STRUCTURED_PERSISTED_INPUT_MISMATCH")
        calls=[dict(r) for r in db.execute("SELECT id,state,maximum_micro,settled_micro,usage_micro,input_tokens,output_tokens,price_version,reason,day,month FROM calls WHERE task_id=? ORDER BY id",(row["id"],))]
        result=json.loads(row["result"]) if row["result"] else None
        return dict(id=row["id"],status=row["status"],reason=row["reason"],provider_hash=row["provider_hash"],
                    input_sha=sha(row["input"].encode()),result_sha=sha(row["result"].encode()) if row["result"] else None,
                    result=result,calls=calls)


def freeze_transport(root,frozen,n,feedback=None,recording=None):
    import autonomous_research as a
    folder=root/f"cloud/round-{n:02}"
    prepare_request(root,frozen,n,feedback)
    if not (folder/"context.json").exists():
        require(recording is not None,"RECORDED_RESPONSE_REQUIRED_NO_DEFAULT_MODEL_CALL")
        path=Path(recording)
        m.data.v1.no_links(path)
        require(path.is_file() and path.stat().st_size<=65536,"RECORDING_SIZE")
        wire=path.read_bytes()
        a.put(folder/"recording.json",wire,raw=True)
        a.put(folder/"context.json",dict(experiment=str(root),round=n,plan_sha=frozen["plan_sha"],
            request_sha=m.hash_file(folder/"request.json"),recording_sha=sha(wire),model_id=frozen["cloud"]["model"]["id"],
            boundary_sha=m.hash_file(root/"cloud/boundary.json"),
            model_sha=frozen["cloud"]["model"]["fingerprint"],authority_id=frozen["cloud"]["authority_id"]))
    elif recording is not None:
        require(m.hash_file(Path(recording))==a.read(folder/"context.json")["recording_sha"],"RECORDING_CHANGED_NEW_EXPERIMENT_REQUIRED")
    require(m.hash_file(binary())==frozen["cloud"]["binary_sha"],"AGENT_BINARY_CHANGED_NEW_EXPERIMENT_REQUIRED")
    return folder


def obtain(root,frozen,n,feedback,seen,recording=None):
    import autonomous_research as a
    folder=freeze_transport(root,frozen,n,feedback,recording)
    try:
        rust("once",root,n)
        task=read_task(root,n)
    except Error as exc:
        a.put(folder/"blocked.json",dict(state="BLOCKED",reason=str(exc)),immutable=False)
        task=read_task(root,n)
        if task is None:
            return None,dict(state="BLOCKED",reason=str(exc))
    if task["status"]!="completed":
        state="OUTCOME_UNKNOWN" if task["status"]=="outcome_uncertain" else "BLOCKED"
        return None,dict(state=state,reason=task["reason"],task_id=task["id"],calls=task["calls"])
    receipt=task["result"]["research"].get("structured_research")
    require(receipt and receipt["request_sha"]==a.read(folder/"context.json")["request_sha"]
        and receipt["provider_sha"]==frozen["cloud"]["model"]["fingerprint"]
        and receipt["response_sha"]==sha(receipt["content"].encode()),"STRUCTURED_RESULT_PROVENANCE")
    try:
        proposals,rejected=parse_response(receipt["content"].encode(),expected_source(frozen,n),frozen["config"]["max_positions"],
                                          frozen["limits"]["candidates"],seen,receipt["refused"])
    except (Error,ValueError,TypeError,KeyError) as exc:
        proposals={}
        rejected=[dict(proposal_sha=receipt["response_sha"],state="REJECTED",reason=str(exc) if isinstance(exc,Error) else "INVALID_CLOUD_JSON")]
    audit=dict(task_id=task["id"],task_input_sha=task["input_sha"],task_result_sha=task["result_sha"],
        request_sha=receipt["request_sha"],wire_sha=receipt["wire_sha"],response_sha=receipt["response_sha"],
        model_sha=receipt["provider_sha"],prompt_sha=receipt["prompt_sha"],adapter_sha=receipt["adapter_sha"],
        calls=task["calls"],accepted=len(proposals),rejected=len(rejected),
        outcome="ALL_REJECTED" if not proposals else "PARTIAL" if len(proposals)<frozen["limits"]["candidates"] else "ACCEPTED",
        real_provider_calls=0,paid_calls=0,currency="TST")
    a.put(folder/"receipt.json",audit)
    return (proposals,rejected),audit


def verify_round(root,frozen,n,record):
    import autonomous_research as a
    folder=root/f"cloud/round-{n:02}"
    ctx=a.read(folder/"context.json")
    require(m.hash_file(folder/"request.json")==ctx["request_sha"] and m.hash_file(folder/"recording.json")==ctx["recording_sha"],"CLOUD_FROZEN_INPUT_CHANGED")
    require(a.read(folder/"request.json")==request(frozen,n,record["feedback"]),"CLOUD_REQUEST_CHANGED")
    audit=a.read(folder/"receipt.json")
    require(record["cloud_receipt"]==audit,"CLOUD_RECEIPT_CHANGED")
    task=read_task(root,n)
    require(task and task["status"]=="completed" and task["id"]==audit["task_id"]
        and task["input_sha"]==audit["task_input_sha"] and task["result_sha"]==audit["task_result_sha"]
        and task["calls"]==audit["calls"],"ORIGINAL_AGENT_RESULT_CHANGED")
    receipt=task["result"]["research"]["structured_research"]
    require(receipt["response_sha"]==audit["response_sha"] and receipt["wire_sha"]==ctx["recording_sha"],"CLOUD_OUTPUT_SHA_MISMATCH")
    proposals,rejected={},[]
    try:
        previous={p["ast_sha"] for i in range(1,n) for p in a.read(root/f"round-{i:02}/proposals.json")["proposals"].values()}
        proposals,rejected=parse_response(receipt["content"].encode(),expected_source(frozen,n),frozen["config"]["max_positions"],
                                          frozen["limits"]["candidates"],previous,receipt["refused"])
    except (Error,ValueError,TypeError,KeyError) as exc:
        rejected=[dict(proposal_sha=receipt["response_sha"],state="REJECTED",reason=str(exc) if isinstance(exc,Error) else "INVALID_CLOUD_JSON")]
    require(proposals==record["proposals"] and rejected==record["rejected"],"CLOUD_AST_ADMISSION_CHANGED")


def verify_pending(root,frozen):
    import autonomous_research as a
    pending=[]
    for n in (1,2):
        folder=root/f"cloud/round-{n:02}"
        if not folder.exists():continue
        feedback=None if n==1 else a.read(root/f"round-{n-1:02}/feedback.json")
        require(a.read(folder/"request.json")==request(frozen,n,feedback),"CLOUD_REQUEST_CHANGED")
        if not (folder/"context.json").exists():
            pending.append(dict(round=n,state="WAITING_FOR_EXPLICIT_RECORDING"));continue
        ctx=a.read(folder/"context.json")
        require(ctx["experiment"]==str(root) and ctx["plan_sha"]==frozen["plan_sha"] and ctx["round"]==n
            and ctx["request_sha"]==m.hash_file(folder/"request.json")
            and ctx["recording_sha"]==m.hash_file(folder/"recording.json")
            and ctx["boundary_sha"]==m.hash_file(root/"cloud/boundary.json")
            and ctx["model_sha"]==frozen["cloud"]["model"]["fingerprint"]
            and ctx["authority_id"]==frozen["cloud"]["authority_id"],"CLOUD_FROZEN_INPUT_CHANGED")
        task=read_task(root,n)
        if not (root/f"round-{n:02}/proposals.json").exists():
            pending.append(dict(round=n,state="NOT_DISPATCHED" if task is None else task["status"],
                task_id=None if task is None else task["id"],calls=[] if task is None else task["calls"]))
    return dict(scope="ORIGINAL_AGENT_READONLY_PENDING_AND_BLOCKED_RECEIPTS",pending=pending)


def report(root):
    import autonomous_research as a
    rounds=[]
    for n in (1,2):
        folder=root/f"cloud/round-{n:02}"
        if not folder.exists(): continue
        task=read_task(root,n)
        rounds.append(dict(round=n,task=None if task is None else {k:v for k,v in task.items() if k!="result"},
            receipt=a.read(folder/"receipt.json") if (folder/"receipt.json").exists() else None,
            blocked=a.read(folder/"blocked.json") if (folder/"blocked.json").exists() else None))
    return dict(mode="recorded_cloud",real_provider_calls=0,paid_calls=0,external_data_sends=0,rounds=rounds)
