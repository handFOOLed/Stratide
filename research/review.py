"""Offline review of actual EOD archives; no Agent, provider or trading entry.

The original Agent DB owns research facts. The original registry owns the lock,
derived registrations, frozen candidates and independent evaluator receipts.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import uuid

import candidates as c
import eod_auto as a

VERSION = "m2-pr08-review-v1"
MAX_ARCHIVES, MAX_VERSIONS, MAX_ATTEMPTS = 512, 128, 32
SAFE = dict(restriction="RESEARCH_ONLY", eligibility="ELIGIBILITY_DENIED",
            forward_paper_allowed=False, live_allowed=False,
            task_origin="TASK_ORIGIN_NOT_ATTESTED", independent_acceptance="NOT_VERIFIED")


def reason(error):
    return str(error) if isinstance(error, (c.Rejected, a.j.Rejected)) else "LOCAL_REVIEW_EVIDENCE_INVALID"


def read(path, limit):
    c.no_links(path)
    return c.read(path, limit)


class Review:
    def __init__(self, name, *, fault=lambda point: None, multimodal=False, portfolio=False, local_fusion=False):
        self.multimodal = multimodal or portfolio or local_fusion
        if local_fusion:
            from local_fusion import Run
            self.auto = Run(name)
        elif portfolio:
            from portfolio_research import ReviewSource
            self.auto = ReviewSource(name)
        elif multimodal:
            from multimodal import ReviewSource
            self.auto = ReviewSource(name)
        else:
            self.auto = a.Auto(name)
        self.config = self.auto.config()
        self.registry = c.Registry(self.config["candidate_registry_name"])
        self.root = self.registry.root / "reviews"
        c.no_links(self.root)
        self.fault = fault

    def archives(self):
        # Reuse #44's actual SQLite reader, origin checks and content address.
        # Never read task-export.json or use the current snapshot as old evidence.
        meta = self.auto.meta()
        self.auto.verify_binding(self.config, meta)
        self.auto.settings()
        c.require(self.auto.binding_owner(self.config) == self.auto.name, "EOD_AUTO_BINDING_OWNED")
        rows = sorted((k, v) for k, v in meta.items() if k.startswith("eod_auto_archive:"))
        c.require(len(rows) <= MAX_ARCHIVES, "ARCHIVE_LIST_LIMIT")
        return meta, rows

    def parent(self, identity, *, saved=None):
        self.registry.path("registrations", identity)  # validate SHA before lookup
        meta, rows = saved if saved is not None else self.archives()
        found = [(key, a.j.loads(value)) for key, value in rows
                 if a.j.loads(value).get("registration_sha256") == identity]
        c.require(len(found) == 1, "ARCHIVED_PARENT_NOT_FOUND")
        key, archive = found[0]
        source_key = key.removeprefix("eod_auto_archive:")
        intent = a.j.loads(meta["eod_auto_intent:" + source_key])
        day = intent["input"]["source_day"]
        if self.multimodal:
            self.auto.validate_intent(source_key, intent)
        else:
            c.require(intent["trigger_key"] == a.POLICY + ":" + self.config["binding_sha256"] + ":" + source_key
                      and day == source_key, "AUTO_BINDING_CHANGED")
        task = self.auto.task_for(intent)
        self.auto.completed(task, intent)
        c.require(len(c.canonical(task)) <= 262144, "INPUT_SIZE_LIMIT")
        c.require(c.digest(task) == archive["task_detail_sha256"]
                  and self.auto.archived(self.config, task) == identity, "AUTO_ARCHIVE_MISMATCH")
        provenance = self.registry.registration(identity)["material"]["snapshot_provenance"]
        return dict(parent_registration_sha256=identity, binding_sha256=self.config["binding_sha256"],
                    task_id=task["id"], task_detail_sha256=c.digest(task),
                    frozen_input_sha256=c.digest(task["input"]), source_day=day,
                    input_summary_version=task["input"]["version"],
                    model_sha256=c.digest({k: task["result"][k] for k in ("provider_id", "model")}),
                    provider_sha256=task["provider_hash"], snapshot_provenance=provenance,
                    current_source_verification="NOT_RECHECKED_OFFLINE_REVIEW")

    def plans(self, parent):
        paths = []
        if self.root.exists():
            for path in self.root.iterdir():
                c.require(len(paths) < MAX_ARCHIVES * MAX_VERSIONS, "REVIEW_LIST_LIMIT")
                if re.fullmatch(r"[0-9a-f]{64}", path.name):
                    c.no_links(path)
                    paths.append(path)
        records = []
        for path in sorted(paths):
            record = read(path / "plan.json", 524288)
            c.require(set(record) == {"review_sha256", "created_at", "material"}
                      and record["review_sha256"] == path.name
                      and c.digest(record["material"]) == path.name, "REVIEW_PLAN_INTEGRITY_MISMATCH")
            if record["material"]["parent"]["parent_registration_sha256"] == parent:
                records.append(record)
        c.require(len(records) <= MAX_VERSIONS, "REVIEW_VERSION_LIMIT")
        return sorted(records, key=lambda v: (v["created_at"], v["review_sha256"]))

    def verify_plan(self, record, parent):
        plan = record["material"]
        path = self.registry.path("reviews", record["review_sha256"])
        c.require(plan["version"] == VERSION and plan["parent"] == parent
                  and c.owner_template(plan["owner_input"]) is not None
                  and plan["owner_input_sha256"] == c.digest(plan["owner_input"]), "REVIEW_PLAN_INTEGRITY_MISMATCH")
        c.require(plan["protocol_sha256"] == c.digest(c.protocol()), "EVALUATOR_PROTOCOL_CHANGED_REFREEZE_REQUIRED")
        c.no_links(path / "source")
        c.require(c.files(path / "source") == plan["source"]["files_sha256"], "REVIEW_SOURCE_INTEGRITY_MISMATCH")
        return path, plan

    def result(self, record, parent):
        path, plan = self.verify_plan(record, parent)
        result = read(path / "result.json", 524288)
        c.require(set(result) == {"report_sha256", "report"} and c.digest(result["report"]) == result["report_sha256"],
                  "REVIEW_REPORT_INTEGRITY_MISMATCH")
        report = result["report"]
        child = self.registry.registration(report["registration_sha256"])["material"]
        expected = dict(self.registry.registration(parent["parent_registration_sha256"])["material"],
                        owner_input=plan["owner_input"], authority="owner_explicit_template",
                        template=c.owner_template(plan["owner_input"]),
                        parent_registration_sha256=parent["parent_registration_sha256"],
                        association="OWNER_EXPLICIT_ASSOCIATION_NOT_HYPOTHESIS_VALIDATION")
        c.require(child == expected, "REVIEW_ASSOCIATION_MISMATCH")
        candidate_id, evaluation_id = report["candidate_sha256"], report["evaluation_sha256"]
        self.registry.path("evaluations", evaluation_id)
        candidate = self.registry.candidate(candidate_id)
        c.require(candidate["material"]["registration_sha256"] == c.digest(child), "REVIEW_ASSOCIATION_MISMATCH")
        evaluation = self.registry.path("candidates", candidate_id) / "evaluations" / evaluation_id / "result.json"
        c.no_links(evaluation)
        receipt = read(evaluation, 1048576)
        self.registry.verify_result(self.registry.path("candidates", candidate_id), receipt)
        c.require(receipt["receipt"]["plan"]["protocol_sha256"] == plan["protocol_sha256"]
                  and receipt["receipt"]["plan"]["binary_sha256"] == (
                      plan["binary_sha256"] if candidate["material"]["data"]["status"] == "COMPLETE" else None),
                  "REVIEW_EVALUATOR_MISMATCH")
        expected_report = self.make_report(record, child, candidate, receipt)
        c.require(report == expected_report, "REVIEW_REPORT_INTEGRITY_MISMATCH")
        return dict(report, report_sha256=result["report_sha256"],
                    report_ref=(path / "result.json").relative_to(self.registry.root).as_posix())

    def make_report(self, record, child, candidate, receipt):
        plan = record["material"]
        return dict(schema_version=1, review_sha256=record["review_sha256"],
                    parent=plan["parent"], owner_input_sha256=plan["owner_input_sha256"],
                    template_id=child["template"]["template_id"], parameters=child["template"]["parameters"],
                    association="OWNER_EXPLICIT_ASSOCIATION_NOT_HYPOTHESIS_VALIDATION",
                    registration_sha256=c.digest(child), candidate_sha256=candidate["candidate_sha256"],
                    evaluation_sha256=receipt["evaluation_sha256"], receipt_sha256=receipt["receipt_sha256"],
                    protocol_sha256=plan["protocol_sha256"], binary_sha256=receipt["receipt"]["plan"]["binary_sha256"],
                    evaluation_report_ref=(self.registry.path("candidates", candidate["candidate_sha256"]) /
                        "evaluations" / receipt["evaluation_sha256"] / "result.json").relative_to(self.registry.root).as_posix(),
                    data=candidate["material"]["data"], frozen_files_sha256=candidate["material"]["frozen_files_sha256"],
                    source_input=plan["source"], state=receipt["state"], engineering=receipt["engineering"],
                    research_status=receipt["research_status"], research_evidence=receipt["research_evidence"],
                    reasons=receipt["reasons"], summary=receipt["summary"],
                    holdout="NOT_APPLICABLE_SYNTHETIC" if plan["evidence_class"] == "synthetic_test" else "EX_POST",
                    genuine_new_forward_days=0, agent_hypothesis_validation="NOT_ESTABLISHED",
                    handoff=c.handoff(candidate["candidate_sha256"], receipt["evaluation_sha256"]),
                    next_step="Owner review of the fixed template result; trading eligibility remains denied", **SAFE)

    def item(self, identity, *, saved=None):
        parent = self.parent(identity, saved=saved)
        versions = []
        for record in self.plans(identity):
            path, _ = self.verify_plan(record, parent)
            if (path / "result.json").exists():
                versions.append(self.result(record, parent))
            else:
                attempts = self.attempts(path)
                versions.append(dict(review_sha256=record["review_sha256"], state="REVIEW_REQUIRED",
                    reason=attempts[-1]["reason"] if attempts else "REVIEW_INTERRUPTED_OR_ACTIVE",
                    phase=attempts[-1]["phase"] if attempts else "PLANNED", attempts=len(attempts), **SAFE))
        return dict(parent=parent, state=versions[-1]["state"] if versions else "AWAITING_OWNER_TEMPLATE",
                    evaluation=versions[-1].get("research_evidence", "NOT_EVALUATED") if versions else "NOT_EVALUATED",
                    versions=versions, next_step="review --owner-input with an explicit fixed template" if not versions else
                    "report; resume the same review input if interrupted, or resolve the stated blocker", **SAFE)

    def inbox(self, identity=None):
        saved = self.archives()
        identities = [identity] if identity else [a.j.loads(value)["registration_sha256"] for _, value in saved[1]]
        items = []
        for key in identities:
            try:
                items.append(self.item(key, saved=saved))
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                items.append(dict(parent_registration_sha256=key, state="REVIEW_REQUIRED", reason=reason(error),
                                  evaluation="NOT_EVALUATED", next_step="inspect original archive and immutable evidence", **SAFE))
        return dict(schema_version=1, items=items, count=len(items), **SAFE)

    def attempts(self, path):
        names = sorted(path.glob("attempt-*.json"))
        c.require(len(names) <= MAX_ATTEMPTS, "REVIEW_ATTEMPT_LIMIT")
        for name in names:
            c.no_links(name)
        return [read(name, 8192) for name in names]

    def source_spec(self, template, evidence_class, source_dir):
        c.require(evidence_class in ("synthetic_test", "historical_replay"), "EVIDENCE_CLASS_INVALID")
        if template == c.SYNTHETIC_TEMPLATE:
            c.require(evidence_class == "synthetic_test" and source_dir is None, "SYNTHETIC_FIXTURE_SCOPE_REQUIRED")
            return dict(kind="repository_fixed_synthetic_fixture", files_sha256={},
                        fixture_sha256=c.sha(c.ROOT / template["fixture"])), None
        c.require(evidence_class == "historical_replay", "SMA_REQUIRES_FROZEN_HISTORICAL_SOURCE")
        hashes = {}
        if source_dir is not None:
            source_dir = source_dir.absolute()
            c.no_links(source_dir)
            for name in c.RAW_NAMES:
                file = source_dir / name
                c.no_links(file)
                if file.is_file():
                    c.require(file.stat().st_size <= 4000000, "SOURCE_SIZE_LIMIT")
                    hashes[name] = c.sha(file)
        available = len(hashes) == len(c.RAW_NAMES)
        return dict(kind="frozen_historical_source" if available else "LOCAL_SOURCE_UNAVAILABLE",
                    files_sha256=hashes if available else {},
                    partial_files_sha256={} if available else hashes), source_dir if available else None

    def run(self, identity, owner_path, evidence_class, source_dir=None):
        c.no_links(owner_path)
        owner = read(owner_path, 32768)
        template = c.owner_template(owner)
        c.require(template is not None, "OWNER_FIXED_TEMPLATE_REQUIRED")
        # One original registry lock covers plan publication, derivation, freeze,
        # evaluate and receipt association. Queries never acquire/create it.
        with self.registry.locked():
            parent = self.parent(identity)
            source, source_dir = self.source_spec(template, evidence_class, source_dir)
            c.no_links(c.EXE)
            plan = dict(version=VERSION, parent=parent, owner_input=owner, owner_input_sha256=c.digest(owner),
                        evidence_class=evidence_class, source=source, protocol_sha256=c.digest(c.protocol()),
                        binary_sha256=c.sha(c.EXE) if c.EXE.is_file() else None)
            key = c.digest(plan)
            path = self.registry.path("reviews", key)
            records = self.plans(identity)
            if not path.exists():
                c.require(len(records) < MAX_VERSIONS, "REVIEW_VERSION_LIMIT")
                self.root.mkdir(exist_ok=True)
                stage = self.root / (".review-" + uuid.uuid4().hex)
                stage.mkdir()
                if source_dir is not None:
                    (stage / "source").mkdir()
                    for name in c.RAW_NAMES:
                        shutil.copyfile(source_dir / name, stage / "source" / name)
                    c.require(c.files(stage / "source") == source["files_sha256"], "SOURCE_CHANGED_DURING_REVIEW")
                c.write(stage / "plan.json", dict(review_sha256=key, created_at=c.now(), material=plan))
                stage.rename(path)
            record = read(path / "plan.json", 524288)
            c.require(record["review_sha256"] == key and record["material"] == plan, "REVIEW_PLAN_INTEGRITY_MISMATCH")
            self.verify_plan(record, parent)
            if (path / "result.json").exists():
                return dict(self.result(record, parent), reused=True)
            previous = self.attempts(path)
            c.require(len(previous) < MAX_ATTEMPTS, "REVIEW_ATTEMPT_LIMIT")
            attempt = path / f"attempt-{len(previous) + 1:04d}.json"
            progress = dict(state="RUNNING", phase="BEFORE_REGISTRATION", reason="REVIEW_INTERRUPTED_OR_ACTIVE")
            c.write(attempt, progress)
            try:
                self.fault("before_registration")
                child = self.registry.derive(identity, owner)
                progress.update(phase="FREEZING", registration_sha256=child)
                c.write(attempt, progress)
                frozen = self.registry.freeze(child, path / "source" if source_dir is not None else None, evidence_class, None)
                candidate = frozen["candidate_sha256"]
                progress.update(phase="FROZEN", candidate_sha256=candidate)
                c.write(attempt, progress)
                self.fault("after_freeze")
                progress["phase"] = "EVALUATING"
                c.write(attempt, progress)
                self.fault("before_evaluate")
                evaluated = self.registry.evaluate(candidate)
                self.fault("after_evaluate")  # original receipt exists; association not yet published
                c.require(self.parent(identity) == parent, "AUTO_ARCHIVE_MISMATCH")
                report = self.make_report(record, self.registry.registration(child)["material"],
                                          self.registry.candidate(candidate), evaluated)
                c.write(path / "result.json", dict(report_sha256=c.digest(report), report=report))
                progress.update(state="COMPLETED", phase="REPORTED", reason=evaluated["state"],
                                evaluation_sha256=evaluated["evaluation_sha256"])
                c.write(attempt, progress)
                return dict(self.result(record, parent), reused=evaluated["reused"])
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                progress.update(state="FAILED", reason=reason(error))
                c.write(attempt, progress)
                raise


def main(argv=None, *, fault=lambda point: None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="只读研究 Inbox；Owner 显式固定模板 → 原冻结/独立评价/持久报告")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--auto", help="original EOD auto name; no review directory override")
    source.add_argument("--multimodal", help="original Time-Series + Fusion run name")
    source.add_argument("--risk-portfolio", help="versioned Cloud Risk + Portfolio research batch")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inbox")
    status = commands.add_parser("status")
    status.add_argument("parent_registration_sha256", nargs="?")
    report = commands.add_parser("report")
    report.add_argument("parent_registration_sha256")
    review = commands.add_parser("review")
    review.add_argument("parent_registration_sha256")
    review.add_argument("--owner-input", type=Path, required=True)
    review.add_argument("--evidence-class", choices=("synthetic_test", "historical_replay"), required=True)
    review.add_argument("--source-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        service = Review(args.risk_portfolio or args.multimodal or args.auto, fault=fault,
                         multimodal=args.multimodal is not None, portfolio=args.risk_portfolio is not None)
        if args.command == "review":
            value = service.run(args.parent_registration_sha256, args.owner_input, args.evidence_class, args.source_dir)
        else:
            value = service.inbox(getattr(args, "parent_registration_sha256", None))
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 2 if args.command != "review" and any(v["state"] == "REVIEW_REQUIRED" for v in value["items"]) else 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(json.dumps(dict(state="REVIEW_REQUIRED", reason=reason(error), evaluation="NOT_EVALUATED",
                             next_step="preserve old evidence; resolve the stated blocker and resume the same input", **SAFE), sort_keys=True))
        return 2
