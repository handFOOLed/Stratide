"""Trusted, offline candidate CLI. No Agent tools, generated code or promotion.

The registry is expendable research state, never an authoritative money ledger.
Only the existing fixed historical template and evaluator can be invoked here.
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid

if __package__:
    from . import data_snapshot
else:
    import data_snapshot

ROOT = Path(__file__).resolve().parents[1]
VERSION = "m2-pr04-candidate-v1"
TEMPLATE_ID = "sma5-20-cross-fixed100-v1"
PARAMETERS = dict(fast_sessions=5, slow_sessions=20, quantity=100)
FLAGS = ("--initial-cash-fen", "--max-order-fen", "--account-cap-fen",
         "--strategy-cap-fen", "--daily-loss-fen", "--drawdown-fen")
CAPITAL = (10000000, 500000, 2000000, 2000000, 100000, 500000)
TEMPLATE = dict(template_id=TEMPLATE_ID, parameters=PARAMETERS,
                execution_model="next-open-adverse-tick-100-v1",
                fee_version="paper-cost-assumption-20260706-v1",
                capital=dict(zip(FLAGS, CAPITAL)),
                evaluation_protocol="m1-pr06-research-v1")
SYNTHETIC_ID = "first-buy-second-sell-third-risk-probe-v1"
SYNTHETIC_TEMPLATE = dict(template_id=SYNTHETIC_ID, parameters={},
                          fixture="samples/m0-pr03-synthetic.json", capital=dict(zip(FLAGS, CAPITAL)),
                          evaluation_protocol="synthetic-pipeline-v1")
TEMPLATES = {TEMPLATE_ID: TEMPLATE, SYNTHETIC_ID: SYNTHETIC_TEMPLATE}
RAW_NAMES = ("calendar.json", "daily.json", "limits.json", "suspensions.json", "extraction.json")
EXE = ROOT / "target/debug" / ("stratide-cli.exe" if os.name == "nt" else "stratide-cli")
EVALUATOR = ROOT / "scripts/research-evaluate.py"


class Rejected(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "AMBIGUOUS_JSON")
        result[key] = value
    return result


def read(path, limit=None):
    if limit is not None:
        require(path.stat().st_size <= limit, "INPUT_SIZE_LIMIT")
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object,
                      parse_constant=lambda _: require(False, "NONFINITE_JSON"))


def no_links(path):
    for part in (path, *path.parents):
        require(not part.is_symlink() and not part.is_junction(), "LINK_PATH_DENIED")


def write(path, value):
    """Commit a complete file on the same volume, under the registry writer lock."""
    no_links(path)
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temp.open("xb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def files(path):
    result = {}
    for directory, dirs, names in os.walk(path, followlinks=False):
        for name in (*dirs, *names):
            no_links(Path(directory) / name)
        for name in names:
            file = Path(directory) / name
            result[file.relative_to(path).as_posix()] = sha(file)
    return result


def protocol():
    paths = ["research/candidates.py", "scripts/research-candidate.py",
             "scripts/research-evaluate.py", "scripts/historical-data.py",
             "docs/M1_PR06_RESEARCH_PROTOCOL.md", "samples/m0-pr03-synthetic.json", "Cargo.lock", "Cargo.toml"]
    for base in ("apps/stratide-cli", "crates/contracts", "crates/risk", "crates/ledger"):
        paths.append(base + "/Cargo.toml")
        paths.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / base / "src").rglob("*.rs"))
    return dict(version=VERSION, files_sha256={name: sha(ROOT / name) for name in sorted(paths)})


def handoff(candidate_id=None, evaluation_id=None):
    # This contract is deliberately incapable of conveying execution authority.
    return dict(schema_version=1, contract="candidate-handoff-v1",
                candidate_sha256=candidate_id, evaluation_sha256=evaluation_id,
                eligibility="ELIGIBILITY_DENIED", qualification="NOT_ELIGIBLE",
                forward_paper_allowed=False, live_allowed=False,
                independent_acceptance="NOT_VERIFIED",
                reasons=["HISTORICAL_PIT_NOT_VERIFIED", "NO_TRUSTED_FORWARD_OPENING_EVIDENCE",
                         "FORWARD_PAPER_NOT_ENABLED", "NO_LIVE_AUTHORIZATION"])


def snapshot_provenance(task, store_name):
    summary = task["input"] if task else {}
    details = summary.get("summary", {})
    details = details if isinstance(details, dict) else {}
    claimed = (str(summary.get("version", "")).startswith(data_snapshot.AGENT_VERSION + ":")
               or summary.get("mode") == "forward_observed_eod"
               or data_snapshot.AGENT_SCOPE in summary.get("scopes", [])
               or str(details.get("snapshot_id", "")).startswith("eod-v1:"))
    require(store_name is None or claimed, "EOD_SNAPSHOT_TASK_REQUIRED")
    if not claimed:
        return None
    key = details.get("snapshot_sha256")
    require(isinstance(key, str) and re.fullmatch(r"[0-9a-f]{64}", key)
            and details.get("snapshot_id") == "eod-v1:" + key
            and summary.get("version") == data_snapshot.AGENT_VERSION + ":" + key
            and summary.get("mode") in ("synthetic_test", "forward_observed_eod")
            and details.get("data_mode") == summary["mode"]
            and details.get("last_valid_source_day") == summary.get("source_day", "").replace("-", "")
            and summary.get("scopes") == ["owner_task", data_snapshot.AGENT_SCOPE]
            and summary.get("eod_eligible") is False
            and all(details.get(k) is False for k in ("eod_eligible", "can_execute_forward_paper", "live_allowed"))
            and details.get("restriction") == "RESEARCH_ONLY", "EOD_SNAPSHOT_INPUT_CONTRACT")
    result = task["result"]
    require(result.get("provider_kind") == "fake" and result.get("synthetic_provider") is True
            and result.get("qualification") == "EXPLORATORY_NOT_INDEPENDENT", "EOD_SNAPSHOT_RESEARCH_ONLY")
    verified = "SOURCE_UNVERIFIED"
    if store_name is not None:
        try:
            expected = data_snapshot.Store(store_name).agent_input()
        except data_snapshot.Rejected as error:
            raise Rejected(str(error)) from None
        require(summary == expected, "EOD_SNAPSHOT_INPUT_MISMATCH")
        verified = "SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION"
    # The JSON/API export is not an Agent signer. Source-content validation does
    # not attest who wrote the task/result, nor confer evaluation authority.
    return dict(snapshot_sha256=key, snapshot_id=details["snapshot_id"],
                source_day=summary["source_day"], data_mode=summary["mode"],
                research_task_id=task["id"], input_summary_version=summary["version"],
                frozen_input_sha256=digest(summary), snapshot_verification=verified,
                task_origin="TASK_ORIGIN_NOT_ATTESTED", restriction="RESEARCH_ONLY",
                eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)


def owner_template(owner):
    """The same finite, exact Owner contract for registration and derivation."""
    allowed = {"schema_version", "template_id", "parameters", "hypothesis", "limitations"}
    template = TEMPLATES.get(owner.get("template_id")) if isinstance(owner, dict) and isinstance(owner.get("template_id"), str) else None
    supported = (isinstance(owner, dict) and set(owner) == allowed
                 and type(owner.get("schema_version")) is int and owner["schema_version"] == 1
                 and template is not None
                 and canonical(owner.get("parameters")) == canonical(template["parameters"])
                 and isinstance(owner.get("hypothesis"), str) and bool(owner["hypothesis"].strip())
                 and isinstance(owner.get("limitations"), list)
                 and bool(owner["limitations"]) and all(isinstance(v, str) for v in owner["limitations"]))
    return template if supported else None


class Registry:
    def __init__(self, name, create=False):
        require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name), "REGISTRY_NAME_INVALID")
        self.root = ROOT / "state/candidates" / name
        no_links(self.root)
        if create:
            require(subprocess.run(["git", "check-ignore", "--quiet", str(self.root / "candidate.json")],
                                   cwd=ROOT).returncode == 0, "REGISTRY_MUST_BE_GITIGNORED")
            self.root.mkdir(parents=True, exist_ok=True)
        require(self.root.is_dir(), "REGISTRY_NOT_FOUND")

    @contextlib.contextmanager
    def locked(self):
        no_links(self.root / ".lock")
        with (self.root / ".lock").open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise Rejected("REGISTRY_BUSY") from error
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def path(self, kind, identity):
        require(re.fullmatch(r"[0-9a-f]{64}", identity), "IDENTITY_INVALID")
        path = self.root / kind / identity
        no_links(path)
        return path

    def register(self, owner_input, agent_task, snapshot_store=None):
        require(owner_input is not None or agent_task is not None, "INPUT_REQUIRED")
        owner = read(owner_input, 32768) if owner_input else None
        task = read(agent_task, 262144) if agent_task else None
        if task is not None:
            # Accept the existing task-detail API envelope or its saved data object.
            if "api_version" in task:
                task = task["data"]
            require(isinstance(task, dict) and task.get("status") == "completed"
                    and isinstance(task.get("result"), dict), "SAVED_COMPLETED_TASK_REQUIRED")
            for key in ("id", "request", "input", "provider_id", "provider_hash", "calls"):
                require(key in task, "AGENT_PROVENANCE_MISSING")
            result, summary = task["result"], task["input"]
            require(isinstance(summary, dict) and isinstance(result.get("research"), dict),
                    "AGENT_PROVENANCE_MISSING")
            for key, original in (("source_day", "source_day"), ("input_mode", "mode"),
                                  ("input_summary_version", "version")):
                require(result.get(key) is not None and result[key] == summary.get(original),
                        "AGENT_INPUT_IDENTITY_MISMATCH")
            for key in ("model", "billing", "synthetic_provider"):
                require(key in result, "AGENT_PROVENANCE_MISSING")
        provenance = snapshot_provenance(task, snapshot_store)
        # No parsing of natural language, no guessed parameters, no provider tools.
        template = owner_template(owner)
        supported = template is not None
        material = dict(schema_version=1, owner_input=owner, saved_agent_task=task,
                        authority="owner_explicit_template" if supported else "research_only",
                        template=template if supported else None)
        if provenance is not None:
            material["snapshot_provenance"] = provenance
        identity = self.save_registration(material)
        result = dict(registration_sha256=identity,
                    state="REGISTERED" if supported else "RESEARCH_ONLY",
                    reason=None if supported else "UNSUPPORTED_CANDIDATE", handoff=handoff(),
                    next_step="freeze" if supported else "Owner must explicitly select the fixed template")
        if provenance is not None:
            result["snapshot_provenance"] = provenance
        return result

    def save_registration(self, material):
        identity = digest(material)
        path = self.path("registrations", identity).with_suffix(".json")
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            write(path, dict(registration_sha256=identity, registered_at=now(), material=material))
        self.registration(identity)
        return identity

    def derive(self, parent_identity, owner):
        """Explicit Owner association; keep the parent's historical provenance.

        Caller holds the original registry writer lock. No current snapshot read,
        task import, Agent invocation or hypothesis-to-strategy inference.
        """
        parent = self.registration(parent_identity)["material"]
        require(parent["authority"] == "research_only" and parent["template"] is None
                and parent["owner_input"] is None and parent.get("snapshot_provenance") is not None,
                "RESEARCH_PARENT_REQUIRED")
        template = owner_template(owner)
        require(template is not None, "OWNER_FIXED_TEMPLATE_REQUIRED")
        material = dict(parent, owner_input=owner, authority="owner_explicit_template", template=template,
                        parent_registration_sha256=parent_identity,
                        association="OWNER_EXPLICIT_ASSOCIATION_NOT_HYPOTHESIS_VALIDATION")
        return self.save_registration(material)

    def source(self, identity):
        material = self.registration(identity)["material"]
        task = material["saved_agent_task"]
        return dict(registration_sha256=identity, state="RESEARCH_ONLY",
                    snapshot_provenance=material.get("snapshot_provenance"),
                    task_origin="TASK_ORIGIN_NOT_ATTESTED" if task else None,
                    frozen_input=task["input"] if task else None,
                    frozen_research=task["result"]["research"] if task else None,
                    evaluation="NOT_EVALUATED", handoff=handoff(),
                    eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)

    def registration(self, identity):
        path = self.path("registrations", identity).with_suffix(".json")
        no_links(path)
        record = read(path)
        require(record["registration_sha256"] == identity and digest(record["material"]) == identity,
                "REGISTRATION_INTEGRITY_MISMATCH")
        return record

    def freeze(self, identity, source_dir, evidence_class, expected_input):
        registration = self.registration(identity)
        template = registration["material"]["template"]
        require(template in TEMPLATES.values(), "UNSUPPORTED_CANDIDATE")
        if template == SYNTHETIC_TEMPLATE:
            require(evidence_class == "synthetic_test" and source_dir is None, "SYNTHETIC_FIXTURE_SCOPE_REQUIRED")
        frozen_protocol = protocol()
        stage = self.root / (".freeze-" + uuid.uuid4().hex)
        frozen = stage / "frozen"
        frozen.mkdir(parents=True)
        data = dict(status="DATA_BLOCKED", evidence_class=evidence_class,
                    blockers=["LOCAL_SOURCE_REQUIRED"], input_sha256=None)
        if template == SYNTHETIC_TEMPLATE:
            dataset = frozen / "audit/input/dataset.json"
            dataset.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / SYNTHETIC_TEMPLATE["fixture"], dataset)
            source = read(dataset)
            actual = sha(dataset)
            if expected_input is not None and expected_input != actual:
                data["blockers"] = ["INPUT_SHA_MISMATCH"]
            else:
                data = dict(status="COMPLETE", evidence_class="synthetic_test", input_sha256=actual,
                            first_day=str(source["sessions"][0]["day"]), source_day=str(source["sessions"][-1]["day"]),
                            sessions=len(source["sessions"]), input_mode="synthetic_test",
                            source_type="repository_fixed_synthetic_fixture", historical_PIT="NOT_APPLICABLE",
                            target_coverage="NOT_MARKET_DATA", blockers=["SYNTHETIC_TEST_ONLY"])
        elif source_dir is not None:
            try:
                source = frozen / "source"
                source.mkdir()
                for name in RAW_NAMES:
                    no_links(source_dir / name)
                    require((source_dir / name).stat().st_size <= 4000000, "SOURCE_SIZE_LIMIT")
                    shutil.copyfile(source_dir / name, source / name)
                extraction = read(source / "extraction.json")
                require(evidence_class == "historical_replay" and extraction.get("response_kind") != "synthetic_test",
                        "SMA_REQUIRES_FROZEN_HISTORICAL_SOURCE")
                invoke([sys.executable, "-I", EVALUATOR, "audit", "--source-dir", source,
                        "--out", frozen / "audit"], "SOURCE_AUDIT_REJECTED")
                dataset = frozen / "audit/input/dataset.json"
                actual = sha(dataset)
                require(expected_input is None or expected_input == actual, "INPUT_SHA_MISMATCH")
                audit = read(frozen / "audit/audit.json")
                data = dict(status="COMPLETE", evidence_class=evidence_class, input_sha256=actual,
                            first_day=audit["selected_start"], source_day=audit["selected_end"],
                            sessions=audit["selected_sessions"], input_mode="historical_replay",
                            source_type=audit["source_type"], historical_PIT="NOT_VERIFIED",
                            target_coverage=audit["data_coverage"], blockers=audit["target_blockers"])
            except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                data["blockers"] = [str(error) if isinstance(error, Rejected) else "LOCAL_SOURCE_INVALID"]
        material = dict(schema_version=1, registration_sha256=identity,
                        input_summary=registration["material"], template=template,
                        template_config_sha256=digest(template), protocol=frozen_protocol, data=data,
                        frozen_files_sha256=files(frozen))
        require(protocol() == frozen_protocol, "EVALUATOR_PROTOCOL_CHANGED_REFREEZE_REQUIRED")
        candidate_id = digest(material)
        record = dict(candidate_sha256=candidate_id, frozen_at=now(), material=material)
        write(stage / "candidate.json", record)
        target = self.path("candidates", candidate_id)
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            self.candidate(candidate_id)
            require(stage.resolve().parent == self.root.resolve() and stage.name.startswith(".freeze-"),
                    "SCRATCH_PATH_INVALID")
            shutil.rmtree(stage)  # Only this operation's freshly created scratch directory.
        else:
            stage.rename(target)
        return self.status(candidate_id)

    def candidate(self, identity):
        path = self.path("candidates", identity)
        record = read(path / "candidate.json")
        material = record["material"]
        require(record["candidate_sha256"] == identity and digest(material) == identity,
                "CANDIDATE_INTEGRITY_MISMATCH")
        require(material["template"] in TEMPLATES.values()
                and material["template_config_sha256"] == digest(material["template"]),
                "TEMPLATE_MISMATCH")
        require(files(path / "frozen") == material["frozen_files_sha256"], "FROZEN_INPUT_INTEGRITY_MISMATCH")
        require(material["protocol"] == protocol(), "EVALUATOR_PROTOCOL_CHANGED_REFREEZE_REQUIRED")
        return record

    def status(self, identity):
        record = self.candidate(identity)
        path = self.path("candidates", identity)
        results = []
        for file in sorted((path / "evaluations").glob("*/result.json")):
            no_links(file)
            result = read(file)
            self.verify_result(path, result)
            results.append(dict(evaluation_sha256=result["evaluation_sha256"], state=result["state"],
                                engineering=result["engineering"], research_status=result["research_status"],
                                research_evidence=result["research_evidence"],
                                handoff=result["handoff"], report_ref=file.relative_to(self.root).as_posix()))
        unfinished = [p for p in (path / "evaluations").glob("*/attempt-*")
                      if not (p.parent / "result.json").exists()]
        return dict(candidate_sha256=identity, state=(results[-1]["state"] if results else
                    ("FROZEN" if record["material"]["data"]["status"] == "COMPLETE" else "DATA_BLOCKED")),
                    frozen_at=record["frozen_at"], data=record["material"]["data"],
                    evaluations=results, incomplete_attempts=len(unfinished), handoff=handoff(identity),
                    next_step="evaluate" if not results else "review immutable local evaluation; eligibility remains denied")

    def verify_result(self, candidate, result):
        material = result["receipt"]
        require(digest(material) == result["receipt_sha256"], "EVALUATION_RECEIPT_INTEGRITY_MISMATCH")
        require(result["candidate_sha256"] == candidate.name
                and digest(material["plan"]) == result["evaluation_sha256"], "EVALUATION_IDENTITY_MISMATCH")
        require(material["handoff"] == handoff(candidate.name, result["evaluation_sha256"]),
                "HANDOFF_INTEGRITY_MISMATCH")
        attempt = candidate / "evaluations" / result["evaluation_sha256"] / material["attempt"]
        require(re.fullmatch(r"attempt-[0-9]{4}", material["attempt"]), "ATTEMPT_ID_INVALID")
        require(files(attempt) == material["artifacts_sha256"], "EVALUATION_ARTIFACT_INTEGRITY_MISMATCH")
        for key in ("state", "engineering", "research_status", "research_evidence", "handoff", "summary",
                    "reasons", "data_coverage", "evidence_class"):
            require(result[key] == material[key], "EVALUATION_RECEIPT_INTEGRITY_MISMATCH")

    def evaluate(self, identity):
        record = self.candidate(identity)
        candidate = self.path("candidates", identity)
        data = record["material"]["data"]
        if data["status"] == "COMPLETE":
            require(EXE.is_file(), "TRUSTED_CLI_BUILD_REQUIRED")
            no_links(EXE)
        plan = dict(candidate_sha256=identity, protocol_sha256=digest(protocol()),
                    binary_sha256=sha(EXE) if data["status"] == "COMPLETE" else None)
        evaluation_id = digest(plan)
        destination = candidate / "evaluations" / evaluation_id
        no_links(destination)
        result_path = destination / "result.json"
        if result_path.exists():
            result = read(result_path)
            self.verify_result(candidate, result)
            return dict(result, reused=True, report_ref=result_path.relative_to(self.root).as_posix())
        destination.mkdir(parents=True, exist_ok=True)
        number = len(list(destination.glob("attempt-*"))) + 1
        require(number <= 9999, "ATTEMPT_LIMIT")
        attempt = destination / f"attempt-{number:04d}"
        attempt.mkdir()
        write(attempt / "plan.json", plan)  # Durable BEFORE any financial simulation.
        base = dict(state="DATA_BLOCKED", engineering="NOT_RUN", research_status="DATA_BLOCKED",
                    research_evidence="DATA_BLOCKED", data_coverage=dict(target="DATA_BLOCKED", selected_window="DATA_BLOCKED"),
                    reasons=data["blockers"], summary=None)
        if data["status"] == "COMPLETE":
            try:
                frozen = candidate / "frozen"
                dataset = frozen / "audit/input/dataset.json"
                flags = [str(v) for pair in zip(FLAGS, CAPITAL) for v in pair]
                invoke([EXE, "paper-replay", dataset, attempt / "ledger", attempt / "report",
                        "--sha256", data["input_sha256"], *flags], "PAPER_REPLAY_REJECTED")
                command = [sys.executable, "-I", EVALUATOR,
                           "evaluate-synthetic" if data["input_mode"] == "synthetic_test" else "evaluate",
                           "--exe", EXE, "--input", dataset, "--ledger", attempt / "ledger",
                           "--report", attempt / "report", "--out", attempt / "evaluation"]
                if data["input_mode"] != "synthetic_test":
                    command.extend(["--split", frozen / "audit/split.json", "--audit", frozen / "audit/audit.json",
                                    "--source-dir", frozen / "source"])
                invoke(command, "INDEPENDENT_EVALUATOR_REJECTED")
                # Recheck frozen bytes/rules/binary after the subprocess boundary.
                self.candidate(identity)
                require(plan["binary_sha256"] == sha(EXE), "EVALUATOR_BINARY_CHANGED")
                evaluated = read(attempt / "evaluation/evaluation.json")
                require(evaluated["input_sha256"] == data["input_sha256"]
                        and evaluated["strategy_version"] == record["material"]["template"]["template_id"],
                        "EVALUATED_IDENTITY_MISMATCH")
                base = dict(state="EVALUATED", engineering="ENGINEERING_PASS",
                            research_status=("RESEARCH_NOT_APPLICABLE" if data["evidence_class"] == "synthetic_test" else
                                             ("RESEARCH_INSUFFICIENT" if evaluated["research_evidence"] == "INSUFFICIENT_EVIDENCE"
                                              else "RESEARCH_DESCRIPTIVE_ONLY")),
                            research_evidence=("SYNTHETIC_TEST_ONLY" if data["evidence_class"] == "synthetic_test"
                                               else evaluated["research_evidence"]),
                            data_coverage=(dict(target="NOT_MARKET_DATA", selected_window="NOT_MARKET_DATA")
                                           if data["evidence_class"] == "synthetic_test" else evaluated["data_coverage"]),
                            reasons=evaluated["insufficient_reasons"],
                            summary=dict(windows=evaluated["windows"], ledger_head=evaluated["ledger_head"],
                                         reports_sha256=evaluated["reports_sha256"],
                                         fee_assumption=evaluated["fee_assumption"],
                                         limitations=evaluated["limitations"]))
            except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                # No success receipt is published on a failed or interrupted run.
                write(attempt / "failure.json", dict(state="FAILED", reason=str(error)
                      if isinstance(error, Rejected) else "EVALUATION_FAILED", handoff=handoff(identity)))
                raise Rejected("EVALUATION_FAILED_SEE_LOCAL_ATTEMPT") from error
        receipt = dict(plan=plan, attempt=attempt.name, **base,
                       evidence_class=data["evidence_class"], handoff=handoff(identity, evaluation_id),
                       artifacts_sha256=files(attempt))
        result = dict(candidate_sha256=identity, evaluation_sha256=evaluation_id,
                      receipt_sha256=digest(receipt), receipt=receipt, **base,
                      evidence_class=data["evidence_class"], handoff=receipt["handoff"])
        write(result_path, result)  # The only completed-evaluation publication point.
        return dict(result, reused=False, report_ref=result_path.relative_to(self.root).as_posix())


def invoke(args, code):
    completed = subprocess.run(list(map(str, args)), cwd=ROOT, capture_output=True, timeout=120)
    require(completed.returncode == 0, code)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    # Saved research text is a UTF-8 JSON interface, including on Windows pipes.
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="default", help="name under ignored state/candidates; no paths")
    commands = parser.add_subparsers(dest="action", required=True)
    register = commands.add_parser("register")
    register.add_argument("--owner-input", type=Path)
    register.add_argument("--agent-task", type=Path, help="saved task detail JSON; never invokes a Provider")
    register.add_argument("--snapshot-store", help="explicit local PR #33 store name; revalidates EOD task input")
    commands.add_parser("source", help="frozen registration research and snapshot provenance").add_argument("registration_sha256")
    freeze = commands.add_parser("freeze")
    freeze.add_argument("registration_sha256")
    freeze.add_argument("--source-dir", type=Path)
    freeze.add_argument("--evidence-class", choices=("historical_replay", "synthetic_test"), required=True)
    freeze.add_argument("--expected-input-sha256")
    for name in ("evaluate", "status"):
        commands.add_parser(name).add_argument("candidate_sha256")
    args = parser.parse_args()
    try:
        registry = Registry(args.registry, create=args.action == "register")
        with registry.locked():
            if args.action == "register":
                result = registry.register(args.owner_input, args.agent_task, args.snapshot_store)
            elif args.action == "source":
                result = registry.source(args.registration_sha256)
            elif args.action == "freeze":
                result = registry.freeze(args.registration_sha256, args.source_dir,
                                         args.evidence_class, args.expected_input_sha256)
            elif args.action == "evaluate":
                result = registry.evaluate(args.candidate_sha256)
            else:
                result = registry.status(args.candidate_sha256)
        # Full research/report content remains in the local registry.
        compact = {key: value for key, value in result.items() if key not in ("receipt", "summary")}
        print(json.dumps(compact, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        code = str(error) if isinstance(error, Rejected) else "LOCAL_INPUT_OR_STORAGE_INVALID"
        next_step = {"TRUSTED_CLI_BUILD_REQUIRED": "build stratide-cli in this worktree",
                     "EVALUATOR_PROTOCOL_CHANGED_REFREEZE_REQUIRED": "freeze a new version under current trusted rules",
                     "REGISTRY_BUSY": "wait for the active CLI operation to finish"}.get(
                         code, "inspect the local input or attempt; preserve old evidence and correct the stated blocker")
        print(json.dumps(dict(state="BLOCKED", error=code, next_step=next_step, handoff=handoff()), sort_keys=True))
        return 2
