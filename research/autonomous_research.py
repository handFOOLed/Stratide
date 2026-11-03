"""Owner-authorized, zero-provider local research lifecycle. No financial authority."""
from __future__ import annotations

import argparse
import contextlib
from decimal import localcontext
import gzip
import json
import os
from pathlib import Path
import platform
import time
import uuid

import autonomous_dsl as dsl
import autonomous_runner as runner
import candidates
import multistock_research as m

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "state" / "autonomous-research"
SOURCE_FILES = tuple(dict.fromkeys((*m.SOURCE_FILES, "research/autonomous_dsl.py",
    "research/autonomous_runner.py", "research/autonomous_research.py", "research/candidates.py",
    "scripts/autonomous-research.py")))
require, Error, canonical, sha = m.require, m.Error, m.canonical, m.sha
DEFAULT_LIMITS = dict(candidates=4, rounds=2, workers=1, wall_seconds=1800,
                      memory_mib=512, disk_mib=256, checkpoint_sessions=100, max_attempts_per_round=3)


def read(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=dsl.unique,
                      parse_constant=lambda _: require(False, "NONFINITE_JSON"))


def put(path, value, immutable=True, raw=False):
    path = Path(path)
    m.data.v1.no_links(path)
    payload = value if raw else canonical(value)+b"\n"
    if immutable and path.exists():
        require(path.read_bytes() == payload, "PUBLISHED_HISTORY_IMMUTABLE")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+".tmp-"+uuid.uuid4().hex)
    with temp.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def output(path, existing=True):
    p = Path(path).absolute()
    m.data.v1.no_links(p)
    require(p != OUTPUT and p.is_relative_to(OUTPUT), "AUTONOMOUS_OUTPUT_BOUNDARY")
    require(not existing or (p/"plan.json").is_file(), "EXPERIMENT_NOT_INITIALIZED")
    return p


def plan(ds, config, seed=63, limits=None):
    limits = dict(DEFAULT_LIMITS, **(limits or {}))
    require(set(limits) == set(DEFAULT_LIMITS), "RESOURCE_FIELDS")
    for key,hi in dict(candidates=8, rounds=2, workers=1, wall_seconds=3600, memory_mib=512,
                       disk_mib=256, checkpoint_sessions=100, max_attempts_per_round=3).items():
        dsl.integer(limits[key], 1, hi)
    require(limits["candidates"] >= 4, "FOUR_DIVERSE_PROPOSALS_REQUIRED")
    require(type(seed) is int and 0 <= seed < 2**32, "SEED_BOUND")
    base = m.plan(ds, config)
    require(config["momentum"] == [20,60] and config["sma"] == [20,60] and config["max_positions"] <= 50,
            "FIXED_FEATURE_HISTORY_AND_CAP")
    require([s["name"] for s in config["cost_scenarios"]] == ["gross", "base", "stress"], "COST_SCENARIO_CONTRACT")
    roles = [w["role"] for w in config["windows"]]
    require(roles.count("development") == 1 and roles.count("validation") == 1 and "evaluation" in roles,
            "DEVELOPMENT_VALIDATION_EVALUATION_REQUIRED")
    require(roles == sorted(roles, key={"development":0, "validation":1, "evaluation":2}.get), "LEARNING_TIME_ORDER")
    base.pop("plan_sha")
    base.update(version="autonomous-research-plan-v1", seed=seed, limits=limits,
        code_sha={p:m.hash_file(ROOT/p) for p in SOURCE_FILES},
        ast_contract=dsl.VERSION, grammar_limits=dsl.LIMITS,
        authority="RESEARCH_ONLY", proposer="trusted_local_deterministic_v1", paid_limit_micro=0,
        optimization="development_only_no_winner_selection", exposure_label="EXPLORATORY_EX_POST / REUSED_EXPOSED_PERIOD",
        evaluation="PR62_Portfolio_same_source_cost_timing_capped_benchmarks_no_independent_blind_claim",
        validation_stop="stop_next_round_if_all_candidate_base_validation_metrics_have_zero_sessions",
        proposal_created_before_evaluation=True, evidence_allowed_for_next_round="DEVELOPMENT_ONLY",
        sealed_results=True, provider_integration="NONE_NO_AGENT_DISPATCH_OR_NEW_BUDGET_LEDGER")
    return dict(base, plan_sha=sha(canonical(base)))


def event(root, kind, **details):
    # One writer owns this journal. Failure records are append-only and never replaced on recovery.
    folder = root/"events"
    folder.mkdir(exist_ok=True)
    sequence = len(list(folder.glob("*.json")))+1
    value = dict(sequence=sequence, at=m.data.v1.now(), kind=kind, **details)
    put(folder/f"{sequence:04d}.json", value)
    return sequence


def initialize(ds, config, out, seed=63, limits=None, authorized=False):
    require(authorized, "EXPLICIT_LOCAL_START_AUTHORIZATION_REQUIRED")
    root = output(out, existing=False)
    with ds:
        frozen = plan(ds, config, seed, limits)
        locators = dict(v1=str(ds.roots[0]), v2=str(ds.roots[1]))
    root.mkdir(parents=True, exist_ok=True)
    with m.data.v1.writer_lock(root):
        if (root/"plan.json").exists():
            require(read(root/"plan.json") == frozen, "EXPERIMENT_PLAN_CONFLICT_USE_NEW_VERSION")
        else:
            put(root/"plan.json", frozen)
        put(root/"locators.json", locators)
        for relative in SOURCE_FILES:
            put(root/"frozen-source"/relative, (ROOT/relative).read_bytes(), raw=True)
        put(root/"authorization.json", dict(plan_sha=frozen["plan_sha"], authority="OWNER_LOCAL_START",
            scope="LOCAL_DETERMINISTIC_RESEARCH_ONLY", paid_limit_micro=0, providers=[], trading=False))
        if not (root/"control"/"state.json").exists():
            put(root/"control"/"state.json", dict(paused=False, cancelled=False))
        if not (root/"status.json").exists():
            put(root/"status.json", dict(**m.SAFE, state="PLANNED", phase="FROZEN_PLAN", completed_rounds=0,
                cumulative_trials=0, current_round=None, plan_sha=frozen["plan_sha"]))
            event(root, "OWNER_AUTHORIZED_PLAN", plan_sha=frozen["plan_sha"])
    return status(root)


def check_plan(root, current_code=False):
    frozen = read(root/"plan.json")
    body = dict(frozen)
    digest = body.pop("plan_sha")
    require(sha(canonical(body)) == digest, "PLAN_SHA_MISMATCH")
    require(frozen["authority"] == "RESEARCH_ONLY" and frozen["paid_limit_micro"] == 0 and
            all(frozen[k] == m.SAFE[k] for k in m.SAFE), "PLAN_AUTHORITY_INVALID")
    require(set(frozen["code_sha"]) == set(SOURCE_FILES), "FROZEN_CODE_FILES")
    for relative,digest in frozen["code_sha"].items():
        require(m.hash_file(root/"frozen-source"/relative) == digest, "FROZEN_CODE_SHA")
        if current_code:
            require(m.hash_file(ROOT/relative) == digest, "CODE_CHANGED_CREATE_NEW_EXPERIMENT")
    return frozen


def status(out):
    root = output(out)
    s = read(root/"status.json")
    control = read(root/"control"/"state.json")
    return dict(s, control=control, effective_state="CANCELLED" if control["cancelled"] else
                "PAUSED" if control["paused"] else s["state"])


def control(out, action):
    root = output(out)
    with m.data.v1.writer_lock(root/"control"):
        previous = read(root/"control"/"state.json")
        require(action != "resume" or not previous["cancelled"], "CANCELLED_EXPERIMENT_IS_TERMINAL")
        current = dict(previous)
        current["cancelled" if action == "cancel" else "paused"] = action != "resume"
        put(root/"control"/f"command-{uuid.uuid4().hex}.json",
            dict(action=action, at=m.data.v1.now(), previous=previous, current=current))
        put(root/"control"/"state.json", current, immutable=False)
    return status(root)


def history(out):
    root = output(out)
    return dict(**m.SAFE, status=status(root), events=[read(p) for p in sorted((root/"events").glob("*.json"))])


def brief_result(result):
    return dict(**{k:result[k] for k in ("state", "round_sha", "source_sha", "proposed", "rejected",
                "exposure_label", "evidence_allowed_for_next_round", "sealed_results")},
        coverage={k:v for k,v in result["coverage"].items() if k not in ("seen", "eligible")},
        observed_securities=len(result["coverage"]["seen"]), eligible_securities=len(result["coverage"]["eligible"]),
        full_period=result["full_period"], windows=result["windows"], walk_forward=result["walk_forward"],
        benchmark_comparison=result["benchmark_comparison"], assumptions=result["assumptions"])


def report(out, full=False):
    root = output(out)
    s = status(root)
    reports = []
    for n in range(1, 3):
        folder = root/f"round-{n:02d}"
        if not (folder/"archive.json").exists():
            continue
        receipt = read(folder/"archive.json")
        result = read(folder/"results.json")
        require(m.hash_file(folder/"results.json") == receipt["files"]["results.json"], "RESULT_HASH_MISMATCH")
        reports.append(dict(round=n, result=result if full else brief_result(result), output_sha=receipt["output_sha"]))
    # Compatible narrow consumer surface; the old fixed-template registry is not modified.
    return dict(**m.SAFE, contract="autonomous-research-inbox-v1", authority="RESEARCH_ONLY", status=s,
                rounds=reports, handoff=candidates.handoff(), independent_acceptance="NOT_VERIFIED",
                selection_warning="CUMULATIVE_TRIALS_MULTIPLE_COMPARISONS_REUSED_EXPOSED_DATA_NOT_ALPHA")


def freeze_round(root, frozen, n):
    folder = root/f"round-{n:02d}"
    if (folder/"proposals.json").exists():
        record = read(folder/"proposals.json")
        validate_round(record, frozen, n)
        return record
    feedback = None if n == 1 else read(root/f"round-{n-1:02d}"/"feedback.json")
    seen = set()
    for i in range(1, n):
        previous = read(root/f"round-{i:02d}"/"proposals.json")
        seen.update(p["ast_sha"] for p in previous["proposals"].values())
    source = dict(kind="trusted_local_deterministic_v1", task_ref=f"local:{frozen['plan_sha']}:{n}",
                  producer_sha=frozen["code_sha"]["research/autonomous_dsl.py"], seed=frozen["seed"], round=n)
    generated = dsl.propose(frozen["seed"], n, frozen["config"]["max_positions"], feedback, seen)
    require(len(generated) <= frozen["limits"]["candidates"], "CANDIDATE_RESOURCE_LIMIT")
    proposals, rejected = {}, []
    for g in generated:
        raw = canonical(dict(contract="structured-research-proposal-v1", source=source,
                             authority="RESEARCH_ONLY", hypothesis=g["hypothesis"], ast=g["ast"]))
        try:
            p = dsl.parse_proposal(raw, source, frozen["config"]["max_positions"])
            require(p["ast_sha"] not in seen, "DUPLICATE_CANDIDATE")
            seen.add(p["ast_sha"])
            proposals[f"candidate_{len(proposals)+1:02d}"] = p
        except (Error, ValueError, TypeError, KeyError) as e:
            rejected.append(dict(proposal_sha=sha(raw), state="REJECTED", reason=str(e) if isinstance(e, Error) else "INVALID_PROPOSAL"))
    body = dict(**m.SAFE, version="autonomous-round-v1", plan_sha=frozen["plan_sha"], round=n,
                source_sha=frozen["source_sha"], source_origin=frozen["source_origin"],
                version_bounds=frozen["source_refs"]["version_bounds"], config=frozen["config"], proposals=proposals, rejected=rejected,
                feedback=feedback, feedback_sha=sha(canonical(feedback)), source=source,
                proposal_created_before_evaluation=True, evidence_allowed_for_next_round="DEVELOPMENT_ONLY",
                exposure_label=frozen["exposure_label"], sealed_results=True)
    record = dict(body, round_sha=sha(canonical(body)))
    put(folder/"proposals.json", record)
    event(root, "PROPOSALS_FROZEN", round=n, round_sha=record["round_sha"], count=len(proposals), rejected=len(rejected))
    return record


def validate_round(r, frozen, n):
    body = dict(r)
    digest = body.pop("round_sha")
    require(sha(canonical(body)) == digest and r["plan_sha"] == frozen["plan_sha"] and
            r["config"] == frozen["config"] and r["source_sha"] == frozen["source_sha"] and r["round"] == n,
            "ROUND_SHA_MISMATCH")
    expected = dict(kind="trusted_local_deterministic_v1", task_ref=f"local:{frozen['plan_sha']}:{n}",
                    producer_sha=frozen["code_sha"]["research/autonomous_dsl.py"], seed=frozen["seed"], round=n)
    require(r["source"] == expected and len(r["proposals"])+len(r["rejected"]) <= frozen["limits"]["candidates"],
            "ROUND_SOURCE_OR_CANDIDATE_LIMIT")
    require(r["proposal_created_before_evaluation"] and r["sealed_results"] and
            r["evidence_allowed_for_next_round"] == "DEVELOPMENT_ONLY", "PREREGISTRATION_REQUIRED")
    for p in r["proposals"].values():
        require(dsl.validate(p["ast"], frozen["config"]["max_positions"]) == p["ast_sha"], "AST_SHA_MISMATCH")
        dsl.parse_proposal(canonical({k:v for k,v in p.items() if k != "ast_sha"}), expected, frozen["config"]["max_positions"])


def finished(result, frozen, n):
    validation = next(w["name"] for w in frozen["config"]["windows"] if w["role"] == "validation")
    no_validation = all(v["sessions"] == 0 for k,v in result["windows"][validation].items() if k.startswith("candidate_"))
    return n == frozen["limits"]["rounds"] or not result["proposed"] or no_validation


def chunk_receipts(folder):
    return [read(p) for p in sorted((folder/"chunks").glob("*/commit.json"))]


def verify_chunks(folder, receipts):
    end = 0
    for i,r in enumerate(receipts):
        require(r["chunk"] == f"chunks/{i:04d}" and r["start"] == end and r["end"] > end, "CHUNK_SEQUENCE")
        require(set(r["files"]) == {"daily.jsonl.gz", "signals.jsonl.gz", "checkpoint.json.gz"}, "CHUNK_FILES")
        for name,digest in r["files"].items():
            m.data.v1.no_links(folder/r["chunk"]/name)
            require(m.hash_file(folder/r["chunk"]/name) == digest, "CHUNK_HASH_MISMATCH")
        end = r["end"]
    return end


def once(out, progress=None, fault=None):
    root = output(out)
    with m.data.v1.writer_lock(root):
        frozen = check_plan(root, current_code=True)
        auth = read(root/"authorization.json")
        require(auth["plan_sha"] == frozen["plan_sha"] and auth["scope"] == "LOCAL_DETERMINISTIC_RESEARCH_ONLY"
                and auth["paid_limit_micro"] == 0 and not auth["providers"] and not auth["trading"], "LOCAL_AUTHORIZATION_INVALID")
        s = status(root)
        if s["control"]["cancelled"] or s["control"]["paused"] or s["state"] == "COMPLETED":
            return report(root)
        n = s["completed_rounds"]+1
        if n > frozen["limits"]["rounds"]:
            return report(root)
        wall, cpu = time.perf_counter(), time.process_time()
        folder = root/f"round-{n:02d}"
        if (folder/"archive.json").exists():
            # Crash after the immutable archive and before the convenience status update.
            verify(root)
            result = read(folder/"results.json")
            complete = finished(result, frozen, n)
            put(root/"status.json", dict({k:v for k,v in s.items() if k not in ("control","effective_state")},
                state="COMPLETED" if complete else "PLANNED", phase="ARCHIVED", completed_rounds=n), immutable=False)
            event(root, "ARCHIVE_STATUS_RECOVERED", round=n)
            return report(root)
        if n > 1:
            verify(root)
        r = freeze_round(root, frozen, n)
        if fault:
            fault("freeze", n)
        attempts = len(list((folder/"attempts").glob("[0-9][0-9].json")))
        require(attempts < frozen["limits"]["max_attempts_per_round"], "RETRY_LIMIT_KEEP_FAILURE_EVIDENCE")
        attempt = attempts+1
        put(folder/"attempts"/f"{attempt:02d}.json", dict(state="RUNNING", at=m.data.v1.now(), round_sha=r["round_sha"]))
        event(root, "EVALUATION_STARTED", round=n, attempt=attempt, round_sha=r["round_sha"])
        def set_status(state, phase, completed=None):
            put(root/"status.json", dict(**m.SAFE, state=state, phase=phase,
                completed_rounds=n-1 if completed is None else completed,
                current_round=n, plan_sha=frozen["plan_sha"],
                cumulative_trials=sum(len(read(root/f"round-{j:02d}"/"proposals.json")["proposals"])+
                    len(read(root/f"round-{j:02d}"/"proposals.json")["rejected"]) for j in range(1,n+1))), immutable=False)
        set_status("RUNNING", "EVALUATE")
        try:
            receipts = chunk_receipts(folder)
            done = verify_chunks(folder, receipts)
            checkpoint = json.loads(gzip.decompress((folder/receipts[-1]["chunk"]/"checkpoint.json.gz").read_bytes())) if receipts else None
            require(not checkpoint or checkpoint["counts"]["processed_sessions"] == done, "CHECKPOINT_SEQUENCE")
            location = read(root/"locators.json")
            ds = m.data.Dataset(location["v1"], location["v2"], frozen["config"]["start"], frozen["config"]["end"],
                                frozen["source_refs"]["version_bounds"]["v1"], frozen["source_refs"]["version_bounds"]["v2"])
            total_bytes = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
            def commit(records, signals, state):
                nonlocal total_bytes, checkpoint
                index = len(receipts)
                chunk = f"chunks/{index:04d}"
                # Uncommitted files from a killed local stage are replaceable; sealed chunks never are.
                payloads = {"daily.jsonl.gz":b"".join(canonical(v)+b"\n" for v in records),
                            "signals.jsonl.gz":b"".join(canonical(v)+b"\n" for v in signals),
                            "checkpoint.json.gz":canonical(state)}
                compressed = {name:gzip.compress(v, mtime=0) for name,v in payloads.items()}
                require(total_bytes+sum(map(len,compressed.values())) <= frozen["limits"]["disk_mib"]*1024**2,
                        "DISK_RESOURCE_LIMIT")
                for name,payload in compressed.items():
                    put(folder/chunk/name, payload, immutable=False, raw=True)
                rec = dict(chunk=chunk, start=receipts[-1]["end"] if receipts else 0,
                           end=state["counts"]["processed_sessions"],
                           files={name:sha(v) for name,v in compressed.items()})
                put(folder/chunk/"commit.json", rec)
                receipts.append(rec)
                checkpoint = state
                total_bytes += sum(map(len,compressed.values()))
            with localcontext() as ctx:
                ctx.prec = 50
                with ds:
                    require(ds.source_sha == frozen["source_sha"] and ds.query_sha == frozen["query_sha"], "FROZEN_SOURCE_CHANGED")
                    before = m.data.file_receipts(ds.roots)
                    state = runner.evaluate(ds, frozen["config"], r, folder, checkpoint, commit,
                        lambda:read(root/"control"/"state.json"), frozen["limits"], progress, fault)
                    after = m.data.file_receipts(ds.roots)
                    require(before == after, "READONLY_SOURCE_CHANGED")
                put(folder/"attempts"/f"{attempt:02d}-end.json", dict(state=state, wall_seconds=time.perf_counter()-wall,
                    cpu_seconds=time.process_time()-cpu, peak_rss_bytes=m.peak_rss_bytes(), workers=1, threads=1,
                    http_api_calls=0, token_reads=0, cloud_model_calls=0, paid_calls=0,
                    source_file_receipts_before=before, source_file_receipts_after=after,
                    python=platform.python_version(), validation="incremental_no_old_raw_or_database_hash"))
                if state != "EVALUATED":
                    event(root, state, round=n, processed_sessions=receipts[-1]["end"] if receipts else 0)
                    set_status(state, "EVALUATE")
                    return report(root)
                set_status("RUNNING", "PUBLISH")
                if fault:
                    fault("publish", n)
                result = runner.summarize(folder, [v["chunk"] for v in receipts], r, checkpoint["counts"])
                put(folder/"results.json", result)
                feedback = dsl.development_feedback(r["round_sha"], result, frozen["config"]["windows"])
                put(folder/"feedback.json", feedback)
                if fault:
                    fault("archive", n)
                files = {p:m.hash_file(folder/p) for p in ("proposals.json", "results.json", "feedback.json")}
                files.update({v["chunk"]+"/commit.json":m.hash_file(folder/v["chunk"]/"commit.json") for v in receipts})
                audit_files = {p.relative_to(folder).as_posix():m.hash_file(p) for p in sorted((folder/"attempts").glob("*.json"))}
                put(folder/"archive.json", dict(**m.SAFE, round_sha=r["round_sha"], files=files,
                    output_sha=sha(canonical(files)), audit_files=audit_files, audit_sha=sha(canonical(audit_files)), sealed_results=True))
                if fault:
                    fault("archived", n)
                event(root, "ROUND_ARCHIVED", round=n, round_sha=r["round_sha"], output_sha=sha(canonical(files)))
                complete = finished(result, frozen, n)
                set_status("COMPLETED" if complete else "PLANNED", "ARCHIVED", completed=n)
            return report(root)
        except BaseException as exc:
            reason = str(exc) if isinstance(exc, Error) else type(exc).__name__
            put(folder/"attempts"/f"{attempt:02d}-failed.json", dict(state="FAILED", reason=reason, at=m.data.v1.now()))
            event(root, "STAGE_FAILED", round=n, attempt=attempt, reason=reason,
                  committed_sessions=receipts[-1]["end"] if "receipts" in locals() and receipts else 0)
            set_status("PARTIAL_RESOURCE_LIMIT" if reason == "DISK_RESOURCE_LIMIT" else "BLOCKED", "RECOVER_LOCAL_STAGE")
            raise


def verify(out):
    root = output(out)
    frozen = check_plan(root)
    checked, trials = [], 0
    for n in range(1, frozen["limits"]["rounds"]+1):
        folder = root/f"round-{n:02d}"
        if not (folder/"proposals.json").exists():
            continue
        r = read(folder/"proposals.json")
        validate_round(r, frozen, n)
        trials += len(r["proposals"])+len(r["rejected"])
        receipts = chunk_receipts(folder)
        verify_chunks(folder, receipts)
        if not (folder/"archive.json").exists():
            checked.append(dict(round=n, state="PARTIAL", committed_sessions=receipts[-1]["end"] if receipts else 0))
            continue
        receipt = read(folder/"archive.json")
        expected = {"proposals.json", "results.json", "feedback.json"}|{v["chunk"]+"/commit.json" for v in receipts}
        require(set(receipt["files"]) == expected and sha(canonical(receipt["files"])) == receipt["output_sha"], "ARCHIVE_MANIFEST")
        for relative,digest in receipt["files"].items():
            require(m.hash_file(folder/relative) == digest, "ARCHIVE_HASH_MISMATCH")
        require(sha(canonical(receipt["audit_files"])) == receipt["audit_sha"], "AUDIT_SHA_MISMATCH")
        for relative,digest in receipt["audit_files"].items():
            require(Path(relative).parent == Path("attempts") and not Path(relative).is_absolute(), "AUDIT_PATH")
            require(m.hash_file(folder/relative) == digest, "FAILURE_AUDIT_HASH_MISMATCH")
        with localcontext() as ctx:
            ctx.prec = 50
            result = read(folder/"results.json")
            rebuilt = runner.summarize(folder, [v["chunk"] for v in receipts], r, result["coverage"])
            require(canonical(rebuilt) == canonical(result), "ECONOMIC_JOURNAL_MISMATCH")
            require(dsl.development_feedback(r["round_sha"], result, frozen["config"]["windows"]) == read(folder/"feedback.json"),
                    "DEVELOPMENT_FEEDBACK_MISMATCH")
        if n > 1:
            require(r["feedback"] == read(root/f"round-{n-1:02d}"/"feedback.json"), "FEEDBACK_PROVENANCE")
        checked.append(dict(round=n, state="SEALED", output_sha=receipt["output_sha"]))
    return dict(**m.SAFE, verified=True, plan_sha=frozen["plan_sha"], rounds=checked, cumulative_trials=trials,
                scope="NEW_ARTIFACT_HASHES_AND_JOURNAL_METRICS_NOT_OLD_SOURCE_REVERIFY_NOT_INDEPENDENT_ACCEPTANCE")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "init", "once", "status", "history", "report", "verify", "pause", "resume", "cancel"))
    parser.add_argument("--v1-root", type=Path)
    parser.add_argument("--v2-root", type=Path)
    parser.add_argument("--v1-version", type=int)
    parser.add_argument("--v2-version", type=int)
    parser.add_argument("--start", default=m.data.v1.START)
    parser.add_argument("--end", default=m.data.v1.END)
    parser.add_argument("--seed", type=int, default=63)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--authorize-local", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    with localcontext() as ctx:
        ctx.prec = 50
        if args.command in ("plan", "init"):
            require(args.v1_root and args.v2_root and args.v1_version and args.v2_version, "EXPLICIT_SOURCE_ROOTS_AND_VERSION_BOUNDS_REQUIRED")
            ds = m.data.Dataset(args.v1_root, args.v2_root, args.start, args.end, args.v1_version, args.v2_version)
            config = m.default_config(args.start, args.end)
            options = read(args.config) if args.config else {}
            require(set(options) <= {"research_config", "limits"}, "LOCAL_CONFIG_FIELDS")
            config.update(options.get("research_config", {}))
            if args.command == "plan":
                with ds:
                    p = plan(ds, config, args.seed, options.get("limits"))
                return p if args.full else dict(**m.SAFE, plan_sha=p["plan_sha"], source_sha=p["source_sha"], limits=p["limits"], seed=p["seed"])
            require(args.out is not None, "OUTPUT_REQUIRED")
            return initialize(ds, config, args.out, args.seed, options.get("limits"), args.authorize_local)
        require(args.out is not None, "OUTPUT_REQUIRED")
        if args.command in ("pause", "resume", "cancel"):
            return control(args.out, args.command)
        if args.command == "once":
            return once(args.out, lambda v:print(json.dumps(dict(progress=v)), flush=True))
        if args.command == "report":
            return report(args.out, args.full)
        return {"status":status, "history":history, "verify":verify}[args.command](args.out)
