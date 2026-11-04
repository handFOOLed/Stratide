"""Frozen, local-only forecast evaluation. No provider, financial writer or tuning."""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
import cli as cpu
import history as history
import model
import runtime
import multistock_data as data
import eod_journal as j

VERSION = "risk-evaluation-v1"
SAFE = dict(authority="RESEARCH_ONLY", eligibility="ELIGIBILITY_DENIED", paper_allowed=False,
            can_execute_forward_paper=False, live_allowed=False,
            cloud_egress="REAL_MARKET_DATA_EGRESS_DENIED", historical_pit_status="NOT_VERIFIED")
MODELS = ("timesfm", "naive", "ewma")
require = model.require


def read(path):
    return model.loads(Path(path).read_bytes())


def write(path, value):
    raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as f:
        os.chmod(path, 0o600)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def code_sha():
    files = ["research/risk_evaluation.py", "research/evidence_audit.py", "research/multistock_data.py",
             "scripts/verify-risk-evaluation.py"]
    return model.digest({n: model.sha_file(ROOT/n) for n in files})


def protocol(value):
    reference = read(ROOT/"config/risk-evaluation-v1.json")
    require(set(value) == set(reference), "EVALUATION_PROTOCOL_SCHEMA")
    # These are the metric/permission contract, not parameter search options.
    configurable = {"symbols", "splits", "context_closes", "model", "source_start", "source_end",
                    "minimum_complete_origins_per_split", "protocol_version"}
    require(all(value[k] == reference[k] for k in reference if k not in configurable), "EVALUATION_PROTOCOL_CONTRACT")
    require(84 <= value["context_closes"] <= 172 and type(value["context_closes"]) is int,
            "EVALUATION_CONTEXT_BOUNDS")
    require(1 <= len(value["symbols"]) <= 8 and len(set(value["symbols"])) == len(value["symbols"])
            and all(re.fullmatch(r"(?:60|00|30|68)[0-9]{4}\.(?:SH|SZ)", s) for s in value["symbols"]),
            "EVALUATION_SYMBOLS")
    require(value["model"] == reference["model"], "EVALUATION_MODEL_CONTRACT")
    require(1 <= value["minimum_complete_origins_per_split"] <= 1000, "EVALUATION_SAMPLE_MINIMUM")
    data.v1.historical_range(value["source_start"], value["source_end"])
    splits = value["splits"]
    require([s["name"] for s in splits] == ["development", "validation", "test"], "EVALUATION_SPLITS")
    previous = value["source_start"]
    for s in splits:
        require(set(s) == {"name", "from", "through"} and previous <= s["from"] <= s["through"] <= value["source_end"],
                "EVALUATION_SPLIT_ORDER")
        data.v1.day(s["from"]); data.v1.day(s["through"])
        previous = (data.v1.day(s["through"]) + dt.timedelta(days=1)).strftime("%Y%m%d")
    return value


def schedule(p, calendar):
    exchanges = {"SSE" if s.endswith(".SH") else "SZSE" for s in p["symbols"]}
    for day in data.v1.dates(p["source_start"], p["source_end"]):
        require(all((e, day) in calendar for e in exchanges), "EVALUATION_CALENDAR_GAP")
        require(len({calendar[e, day] for e in exchanges}) == 1, "HISTORY_CROSS_MARKET_CALENDAR")
    days = sorted(d for (e, d), opened in calendar.items() if e == sorted(exchanges)[0]
                  and opened == "1" and p["source_start"] <= d <= p["source_end"])
    out = []
    for split in p["splits"]:
        for month in sorted({d[:6] for d in days if split["from"] <= d <= split["through"]}):
            candidates = [d for d in days if d[:6] == month and d[6:] >= "15"
                          and split["from"] <= d <= split["through"]]
            if not candidates:
                continue
            origin = candidates[0]
            i = days.index(origin)
            context = days[max(0, i+1-p["context_closes"]):i+1]
            targets = days[i+1:i+21]
            reason = ("CONTEXT_UNAVAILABLE" if len(context) != p["context_closes"] else
                      "PURGED_SPLIT_BOUNDARY" if len(targets) != 20 or targets[-1] > split["through"] else None)
            out.append(dict(split=split["name"], origin=origin, context_days=context, target_days=targets, exclusion=reason))
    require(0 < len(out) <= 120, "EVALUATION_ORIGIN_LIMIT")
    return out


class Source:
    """Only selected symbols, accepted versions, and three APIs; no raw/full-row scan."""
    def __init__(self, dataset):
        self.ds, self.cache = dataset, {}

    def queries(self, days, symbol):
        daily, factors, suspensions = [], [], []
        parts = {api: [] for api in ("adj_factor", "suspend_d")}
        for day in days:
            for api in ("daily", "adj_factor", "suspend_d"):
                p = self.ds.partitions[api].get(day)
                require(p is not None, "HISTORY_SIDECAR_COVERAGE_GAP" if api != "daily" else "HISTORY_PARTITION_MISSING")
                key = (api, day, symbol)
                if key not in self.cache:
                    self.cache[key] = self.ds._rows(api, day, [symbol])
                rows = self.cache[key]
                if api == "daily":
                    for x in rows:
                        values = {k: v for k, v in x.items() if k != "_row_sha"}
                        require(data.sha(data.canonical(values)) == x["_row_sha"], "EVALUATION_ROW_SHA")
                        daily.append(dict(values=values, version_id=p["id"], partition_status=p["status"],
                                          source_sha=p["source_sha"], availability=p["manifest"]))
                else:
                    parts[api].append(dict(trade_date=day, version_id=p["id"], quality=p["status"],
                                           reason=p["reason"], row_count=p["row_count"], source_sha=p["source_sha"],
                                           sources=p["manifest"]["attempts"]))
                    for x in rows:
                        value = {k: v for k, v in x.items() if k != "_row_sha"}
                        require(data.sha(data.canonical(value)) == x["_row_sha"], "EVALUATION_ROW_SHA")
                        (factors if api == "adj_factor" else suspensions).append(dict(data=value))
        return dict(rows=daily), dict(rows=factors, partitions=parts["adj_factor"]), dict(rows=suspensions, partitions=parts["suspend_d"])

    def prefix(self, descriptor, symbol, days):
        daily, factors, suspensions = self.queries(days, symbol)
        return history.assemble(descriptor, [symbol], history.iso(days[-1])+"T08:00:00Z", days,
            self.ds.catalog, daily, factors, suspensions,
            dict(daily=self.ds.version_bounds[0], sidecar=self.ds.version_bounds[1]),
            dict(calendar_sha256=model.digest({e+":"+d:v for (e,d),v in self.ds.calendar.items() if d in days}),
                 sidecar_metadata_sha256=self.ds.refs["metadata_source_sha"],
                 contract_v1_sha256=model.digest(data.v1.CONTRACT), contract_v2_sha256=model.digest(data.sidecar.CONTRACT)))


def new_directory(path):
    path = Path(path).absolute()
    j.no_links(path)
    require(subprocess.run(["git", "check-ignore", "--quiet", str(path/"report.json")], cwd=ROOT).returncode == 0,
            "EVALUATION_OUTPUT_MUST_BE_IGNORED")
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    return path


def freeze(config, roots, out):
    p = protocol(read(config))
    out = Path(out)
    require(all(out.absolute() != Path(x).absolute() and Path(x).absolute() not in out.absolute().parents for x in roots),
            "EVALUATION_OUTPUT_SOURCE_COLLISION")
    with data.Dataset(*roots, start=p["source_start"], end=p["source_end"]) as ds:
        desc = cpu.bridge("descriptor")
        manifest = model.verify_model(ROOT/"models/timesfm-2.5")
        frozen = dict(schema_version=1, version=VERSION, protocol=p, protocol_sha256=model.digest(p),
            created_at=dt.datetime.now(dt.timezone.utc).isoformat(), source_origin=ds.origin,
            roots=[str(x) for x in ds.roots], source_sha256=ds.source_sha, source_refs=ds.refs,
            source_file_receipts=data.file_receipts(ds.roots), descriptor=desc,
            calendar={e+":"+d:v for (e,d),v in ds.calendar.items()},
            model_manifest_sha256=model.digest(manifest), implementation_sha256=code_sha(),
            origins=schedule(p, ds.calendar), source_policy="accepted_local_versions_no_raw_full_recheck", **SAFE)
        path = new_directory(out)
        write(path/"frozen.json", frozen)
        write(path/"freeze.json", dict(pin=model.digest(frozen), protocol_sha256=frozen["protocol_sha256"], state="FROZEN_NOT_RUN"))
    return summary(path)


def load_frozen(out, fresh=False):
    out = Path(out).absolute()
    j.no_links(out)
    f, pin = read(out/"frozen.json"), read(out/"freeze.json")["pin"]
    require(model.digest(f) == pin and f["protocol_sha256"] == model.digest(f["protocol"]), "EVALUATION_FROZEN_SHA")
    if fresh:
        require(f["implementation_sha256"] == code_sha() and f["descriptor"] == cpu.bridge("descriptor")
                and f["model_manifest_sha256"] == model.digest(model.verify_model(ROOT/"models/timesfm-2.5")),
                "EVALUATION_PIN_CHANGED_NEW_FREEZE_REQUIRED")
    return f, pin


def realized(closes):
    returns = [b/a-1 for a,b in zip(closes, closes[1:])]
    return [math.sqrt(statistics.mean(x*x for x in returns[i:i+20])) for i in range(len(returns)-19)]


def sample_scores(predictions, actual, horizons=(5,20)):
    scores = {}
    for name, values in predictions.items():
        require(len(values) == len(actual) == 20 and all(math.isfinite(v) and 0 <= v <= .35 for v in values+actual),
                "EVALUATION_PREDICTION_UNITS")
        scores[name] = {}
        for h in horizons:
            errors = [a-b for a,b in zip(values[:h], actual[:h])]
            scores[name][str(h)] = dict(mae=statistics.mean(abs(x) for x in errors),
                mse=statistics.mean(x*x for x in errors), rmse=math.sqrt(statistics.mean(x*x for x in errors)),
                smape=statistics.mean(0 if abs(a)+abs(b) == 0 else 2*abs(a-b)/(abs(a)+abs(b))
                                      for a,b in zip(values[:h], actual[:h])),
                horizon_mean_absolute_error=abs(statistics.mean(values[:h])-statistics.mean(actual[:h])))
    return scores


def aggregate(records, p):
    out = {}
    for split in p["splits"]:
        rows = [r for r in records if r["split"] == split["name"]]
        good = [r for r in rows if r["state"] == "SCORED"]
        origins = len({r["origin"] for r in good})
        eligible = [r for r in rows if r["state"] != "PURGED"]
        result = dict(samples=len(rows), scored=len(good), distinct_origins=origins,
                      coverage=len(good)/len(eligible) if eligible else 0,
                      prediction_failures=sum(r["state"] == "PREDICTION_FAILED" for r in rows),
                      failure_rate=sum(r["state"] == "PREDICTION_FAILED" for r in rows)/len(eligible) if eligible else 0,
                      exclusions=dict(Counter(r["reason"] for r in rows if r["state"] != "SCORED")),
                      performance={"samples_with_worker_metrics":sum("resources" in r for r in rows),
                        "supervisor_wall_seconds_total":sum(r.get("supervisor_wall_seconds",0) for r in rows),
                        "worker_cpu_seconds_total":sum(r.get("resources",{}).get("cpu_seconds",0) for r in rows),
                        "peak_worker_rss_bytes":max((r.get("resources",{}).get("peak_rss_bytes",0) for r in rows),default=0),
                        "peak_cgroup_memory_bytes":max((r.get("resources",{}).get("cgroup_memory_peak_bytes",0) for r in rows),default=0)},
                      status="EX_POST_RESEARCH_ONLY" if origins >= p["minimum_complete_origins_per_split"] else "INSUFFICIENT_EVIDENCE",
                      metrics={}, paired={})
        for name in MODELS:
            result["metrics"][name] = {}
            for h in ("5", "20"):
                xs = [r["scores"][name][h] for r in good]
                result["metrics"][name][h] = ({k:statistics.mean(x[k] for x in xs) for k in ("mae","smape","horizon_mean_absolute_error")} |                     dict(rmse=math.sqrt(statistics.mean(x["mse"] for x in xs)), points=len(xs)*int(h)) if xs else None)
        for other in ("naive", "ewma"):
            result["paired"][other] = {}
            for h in ("5","20"):
                pairs = [dict(sample_id=r["sample_id"], difference=r["scores"]["timesfm"][h]["mae"]-r["scores"][other][h]["mae"]) for r in good]
                xs = [x["difference"] for x in pairs]
                result["paired"][other][h] = dict(samples=pairs, mean=statistics.mean(xs) if xs else None,
                    minimum=min(xs) if xs else None, maximum=max(xs) if xs else None,
                    timesfm_lower_error_fraction=sum(x<0 for x in xs)/len(xs) if xs else None,
                    interpretation="DESCRIPTIVE_OVERLAPPING_CORRELATED_NOT_INDEPENDENT_CI")
        out[split["name"]] = result
    return out


def reason(error):
    if isinstance(error, sqlite3.Error): return "EVIDENCE_STORAGE_UNAVAILABLE"
    return str(error) if isinstance(error, (model.Rejected, data.Error, j.Rejected)) and re.fullmatch("[A-Z0-9_]{1,100}", str(error)) else "EVALUATION_SAMPLE_FAILED"


def evaluate_sample(out, f, pin, source, origin, symbol, runner):
    sample_id = origin["split"]+"-"+origin["origin"]+"-"+symbol
    row = dict(sample_id=sample_id, split=origin["split"], origin=origin["origin"], instrument=symbol,
               context_days=origin["context_days"], target_days=origin["target_days"], state="PURGED", reason=origin["exclusion"])
    path = out/"samples"/sample_id
    path.mkdir(parents=True)
    if origin["exclusion"]:
        write(path/"sample.json", row)
        return row
    try:
        queried = source.queries(origin["context_days"], symbol)
        write(path/"prefix-source.json", dict(days=origin["context_days"], symbol=symbol,
            catalog=source.ds.catalog.get(symbol), daily=queried[0], factors=queried[1], suspensions=queried[2]))
        prefix, evidence = source.prefix(f["descriptor"], symbol, origin["context_days"])
        plan = dict(batch="oos-"+pin[:16]+"-"+origin["origin"]+"-"+symbol[:6], frozen=prefix, history=evidence,
            manifest_sha256=f["model_manifest_sha256"], code_sha256=f["descriptor"]["code_sha256"],
            max_context=256, batch_size=1, threads=2)
        write(path/"plan.json", plan)
        base_started = time.perf_counter()
        projection = cpu.bridge("project", plan)
        row["baseline_and_validation_wall_seconds"] = time.perf_counter()-base_started
        write(path/"projection.json", projection)
    except (model.Rejected, data.Error, ValueError, KeyError, TypeError) as error:
        row.update(state="INPUT_BLOCKED", reason=reason(error))
        write(path/"sample.json", row)
        return row
    try:
        # Prediction only sees the strict prefix; target prices/quality read later.
        started = time.perf_counter()
        response = runner(projection["worker_request_json"].encode())
        row["supervisor_wall_seconds"] = time.perf_counter()-started
        write(path/"worker-response.json", response)
        bundle = cpu.bridge("decode", dict(plan=plan, response=response))
        write(path/"risk-result.json", bundle)
        row["resources"] = response["metrics"]
        row["request_sha256"] = response["request_sha256"]
        row["prediction_sha256"] = model.digest(response["forecasts"])
    except (model.Rejected, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        row.update(state="PREDICTION_FAILED", reason=reason(error))
        write(path/"sample.json", row)
        return row
    try:
        outcome_days = origin["context_days"]+origin["target_days"]
        queried = source.queries(outcome_days, symbol)
        write(path/"outcome-source.json", dict(days=outcome_days, symbol=symbol,
            catalog=source.ds.catalog.get(symbol), daily=queried[0], factors=queried[1], suspensions=queried[2]))
        full, quality = source.prefix(f["descriptor"], symbol, outcome_days)
        write(path/"outcome-input.json", dict(frozen=full, history=quality))
        closes = [x["close_fen"] for x in full["series"][0]["observations"]]
        actual = realized(closes)[-20:]
        base = projection["baselines"][0]
        predictions = dict(timesfm=response["forecasts"][0]["values"], naive=[base["naive"]]*20, ewma=[base["ewma"]]*20)
        row.update(state="SCORED", reason=None, actual=actual, predictions=predictions,
                   scores=sample_scores(predictions, actual), target_sent_to_worker=False,
                   quality=dict(status="PARTIAL", historical_pit_status="NOT_VERIFIED", blockers=quality["payload"]["blockers"]))
    except (model.Rejected, data.Error, ValueError, KeyError, TypeError) as error:
        row.update(state="TARGET_BLOCKED", reason=reason(error))
    write(path/"sample.json", row)
    return row


def run(out, runner=runtime.run):
    out = Path(out).absolute()
    f, pin = load_frozen(out, fresh=True)
    if (out/"seal.json").exists():
        return verify(out)
    require(not (out/"started.json").exists(), "EVALUATION_INTERRUPTED_NEW_FREEZE_REQUIRED")
    with runtime.lock(out/"run.lock"), runtime.lock(cpu.state_root()/"worker.lock"):
        require(not (out/"started.json").exists(), "EVALUATION_ALREADY_STARTED")
        write(out/"started.json", dict(pin=pin, at=dt.datetime.now(dt.timezone.utc).isoformat()))
        p = f["protocol"]
        before = data.file_receipts(f["roots"])
        records = []
        with data.Dataset(*f["roots"], start=p["source_start"], end=p["source_end"],
                          v1_version=f["source_refs"]["version_bounds"]["v1"], v2_version=f["source_refs"]["version_bounds"]["v2"]) as ds:
            require(ds.source_sha == f["source_sha256"] and schedule(p, ds.calendar) == f["origins"], "EVALUATION_SOURCE_CHANGED")
            source = Source(ds)
            for origin in f["origins"]:
                for symbol in p["symbols"]:
                    records.append(evaluate_sample(out, f, pin, source, origin, symbol, runner))
                    print(json.dumps(dict(progress=len(records), state=records[-1]["state"])), file=sys.stderr, flush=True)
        require(before == data.file_receipts(f["roots"]), "EVALUATION_SOURCE_MUTATED")
        require(f["implementation_sha256"] == code_sha(), "EVALUATION_CODE_CHANGED_DURING_RUN")
        from evidence_audit import blockers
        report = dict(schema_version=1, version=VERSION, pin=pin, protocol_sha256=f["protocol_sha256"],
            classification="EX_POST_RESEARCH_ONLY" if f["source_origin"] == "REAL_LOCAL_HISTORY" else "SYNTHETIC_TEST_ONLY",
            REAL_OOS="EX_POST_EVALUATED_PIT_NOT_VERIFIED" if f["source_origin"] == "REAL_LOCAL_HISTORY" and any(r["state"] == "SCORED" for r in records) else "NOT_VERIFIED",
            hypothesis_verdict="INSUFFICIENT_EVIDENCE", holdout_was_previously_exposed=True,
            target=p["target"], unit="daily_return_ratio", sample_weight=p["sample_weight"],
            horizons=p["horizons"], uncertainty=p["uncertainty"], splits=aggregate(records,p),
            counts=dict(Counter(r["state"] for r in records)), samples=records,
            fusion_comparability=p["fusion_comparability"], source_bytes_unchanged=True,
            calls=0, billable_calls=0, budget_writes=0, new_market_requests=0,
            admission=blockers(), engineering="COMPLETED_WITH_EXPLICIT_EVIDENCE_LIMITATIONS", N100_ACCEPTANCE="NOT_VERIFIED", **SAFE)
        write(out/"report.json",report)
        write(out/"seal.json",dict(pin=pin, files={str(x.relative_to(out)):model.sha_file(x)
            for x in sorted(out.rglob("*.json")) if x.name != "seal.json"}, authority="LOCAL_INTEGRITY_NOT_EXTERNAL_CERTIFICATION"))
    return verify(out)


def summary(out):
    f, pin = load_frozen(out)
    report = read(Path(out)/"report.json") if (Path(out)/"seal.json").exists() else {}
    return dict(state="SEALED" if report else "INTERRUPTED" if (Path(out)/"started.json").exists() else "FROZEN_NOT_RUN",
                pin=pin, protocol_sha256=f["protocol_sha256"], origins=len(f["origins"]),
                samples=sum(report.get("counts",{}).values()), counts=report.get("counts",{}),
                REAL_OOS=report.get("REAL_OOS","NOT_RUN"), hypothesis_verdict="INSUFFICIENT_EVIDENCE",
                metrics_visibility="LOCAL_REPORT_ONLY_NO_MARKET_DERIVATIVES_IN_STDOUT", **SAFE)


def verify(out):
    out=Path(out).absolute()
    f, pin = load_frozen(out)
    seal = read(out/"seal.json")
    require(seal["pin"] == pin and seal["files"], "EVALUATION_SEAL_PIN")
    files={str(p.relative_to(out)) for p in out.rglob("*.json") if p.name != "seal.json"}
    require(files == set(seal["files"]), "EVALUATION_SEAL_FILES")
    for name, digest in seal["files"].items():
        path=out/name
        require(path.is_relative_to(out) and ".." not in Path(name).parts and path.is_file() and not path.is_symlink(), "EVALUATION_SEAL_PATH")
        require(model.sha_file(path) == digest,"EVALUATION_REPORT_SHA")
    require(read(out/"report.json")["pin"] == pin, "EVALUATION_REPORT_PIN")
    return dict(summary(out), verified=True, verification="LOCAL_SEAL_ONLY_USE_INDEPENDENT_RECOMPUTATION")


def main():
    parser=argparse.ArgumentParser(description="Local-only frozen risk forecast evaluation; stdout is redacted.")
    parser.add_argument("command", choices=["freeze","run","report","verify","audit"])
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--protocol",type=Path,default=ROOT/"config/risk-evaluation-v1.json")
    parser.add_argument("--v1-root",type=Path)
    parser.add_argument("--v2-root",type=Path)
    parser.add_argument("--observer",type=Path)
    parser.add_argument("--through")
    parser.add_argument("--operator-root",type=Path)
    args=parser.parse_args()
    try:
        if args.command == "freeze":
            require(args.v1_root and args.v2_root,"EVALUATION_EXPLICIT_SOURCES_REQUIRED")
            result=freeze(args.protocol,[args.v1_root,args.v2_root],args.out)
        elif args.command == "run": result=run(args.out)
        elif args.command in ("report","verify"): result=verify(args.out)
        else:
            from evidence_audit import audit
            result=audit(args.observer,args.through,args.out,args.operator_root,args.v1_root,args.v2_root)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except (model.Rejected,j.Rejected,data.Error,data.sidecar.Error,sqlite3.Error,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print(json.dumps(dict(state="BLOCKED",error_code=reason(error),REAL_OOS="NOT_VERIFIED",**SAFE)))
        return 2
