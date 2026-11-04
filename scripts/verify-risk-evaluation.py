"""Independent arithmetic/source audit. Standard library only; no production imports.

Run on the local sealed directory. No raw values, derived metrics or paths in stdout.
This is an independent algorithm, NOT independent human acceptance or PIT evidence.
"""
import argparse
from collections import Counter
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import statistics


def check(ok, code):
    if not ok: raise ValueError(code)


def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def digest(v): return hashlib.sha256(canonical(v)).hexdigest()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    def pairs(items):
        d={}
        for k,v in items:
            check(k not in d,"DUPLICATE_JSON")
            d[k]=v
        return d
    return json.loads(path.read_bytes(),object_pairs_hook=pairs,parse_constant=lambda _:check(False,"NONFINITE"))


def near(a,b):
    check(type(a) in (int,float) and math.isfinite(a) and math.isclose(a,float(b),rel_tol=2e-10,abs_tol=1e-13),"INDEPENDENT_ARITHMETIC_MISMATCH")


def targets(closes):
    with localcontext() as ctx:
        ctx.prec=45
        returns=[Decimal(b)/Decimal(a)-1 for a,b in zip(closes,closes[1:])]
        rms=[(sum(v*v for v in returns[n:n+20])/20).sqrt() for n in range(len(returns)-19)]
        ewma=returns[0]**2
        for v in returns[1:]: ewma=Decimal('.94')*ewma+Decimal('.06')*v*v
        return [float(x) for x in rms], float(ewma.sqrt())


def quality(plan):
    f,p=plan["frozen"],plan["history"]["payload"]
    check(digest(p) == plan["history"]["payload_sha256"] and digest(f) == p["frozen_sha256"],"INDEPENDENT_INPUT_SHA")
    check(p["historical_pit_status"] == "NOT_VERIFIED" and p["coverage"] == "PARTIAL"
          and p["cloud_egress"] == "REAL_MARKET_DATA_EGRESS_DENIED"
          and p["adjustment"] == "unadjusted_no_factor_application","INDEPENDENT_QUALITY_LABEL")
    check(len(f["series"]) == len(p["series"]) == 1,"INDEPENDENT_SERIES_COUNT")
    s,raw=f["series"][0],p["series"][0]
    check(s["instrument"] == raw["instrument"],"INDEPENDENT_IDENTITY")
    fs=raw["factors"]
    check([x["trade_date"] for x in fs] == [x["values"]["trade_date"] for x in raw["rows"]]
          and len({Decimal(x["adj_factor"]) for x in fs}) == 1,"INDEPENDENT_ACTION_OR_GAP")
    previous=None
    for obs,rr in zip(s["observations"],raw["rows"],strict=True):
        x=rr["values"]
        check(x["ts_code"] == s["instrument"] and obs["trade_day"].replace("-","") == x["trade_date"],"INDEPENDENT_ROW_IDENTITY")
        check(digest(x) == rr["row_sha256"],"INDEPENDENT_ROW_SHA")
        ref=x["ts_code"]+":"+x["trade_date"]
        source=p["sources"]["daily"][ref]
        check(source == rr["source_sha256"] and digest(p["sources"]["daily_manifests"][source]) == source,"INDEPENDENT_SOURCE_SHA")
        lo,hi,op,cl=(Decimal(x[k]) for k in ("low","high","open","close"))
        check(0 < lo <= min(op,cl) <= max(op,cl) <= hi and Decimal(x["vol"]) > 0 and Decimal(x["amount"]) > 0
              and (previous is None or (Decimal(x["pre_close"]) == previous and abs(cl/previous-1) <= Decimal('.35')))
              and not x.get("quality_flags"),"INDEPENDENT_PRICE_QUALITY")
        check(cl*100 == obs["close_fen"],"INDEPENDENT_FEN")
        previous=cl
    return [x["close_fen"] for x in s["observations"]]


def source_reasons(raw):
    """Independent rejection oracle over captured source rows, including failed samples."""
    reasons=set();days=raw["days"];symbol=raw["symbol"];cat=raw["catalog"]
    if not cat or not cat.get("list_date") or cat["list_date"]>days[0] or (cat.get("delist_date") and cat["delist_date"]<=days[-1]):
        reasons.add("HISTORY_LISTING_INTERVAL")
    if cat and cat.get("exchange") != ("SSE" if symbol.endswith(".SH") else "SZSE"):
        reasons.add("HISTORY_IDENTITY_MISMATCH")
    rows=raw["daily"]["rows"]
    dates=[x["values"]["trade_date"] for x in rows if x["values"]["ts_code"]==symbol]
    if len(set(dates))!=len(dates):reasons.add("HISTORY_DUPLICATE_DAY")
    if dates!=days:reasons.add("HISTORY_MISSING_OR_SUSPENDED_DAY")
    fs=[x["data"] for x in raw["factors"]["rows"] if x["data"]["ts_code"]==symbol]
    if [x["trade_date"] for x in fs]!=days:reasons.add("HISTORY_FACTOR_COVERAGE_GAP")
    factor_values=[Decimal(x["adj_factor"]) for x in fs]
    if any(x<=0 for x in factor_values):reasons.add("HISTORY_FACTOR_INVALID")
    if len(set(factor_values))!=1:reasons.add("HISTORY_RAW_ACTION_DISCONTINUITY")
    if any(x["data"]["ts_code"]==symbol and x["data"]["suspend_type"]=="S" for x in raw["suspensions"]["rows"]):
        reasons.add("HISTORY_SUSPENSION_REPORTED")
    previous=None
    for row in rows:
        x=row["values"]
        if x.get("quality_flags"):reasons.add("HISTORY_SOURCE_ROW_QUALITY")
        op,hi,lo,cl=(Decimal(x[k]) for k in ("open","high","low","close"))
        if not (0 < lo <= min(op,cl) <= max(op,cl) <= hi):reasons.add("HISTORY_PRICE_INVALID")
        if Decimal(x["vol"])<=0 or Decimal(x["amount"])<=0:reasons.add("HISTORY_VOLUME_INVALID")
        if previous is not None:
            if Decimal(x["pre_close"])!=previous:reasons.add("HISTORY_PRE_CLOSE_ACTION_OR_REVISION")
            if previous>0 and abs(cl/previous-1)>Decimal('.35'):reasons.add("HISTORY_PRICE_JUMP")
        if cl*100 != (cl*100).to_integral_value():reasons.add("HISTORY_PRICE_PRECISION")
        check(digest(row["availability"])==row["source_sha"],"INDEPENDENT_SOURCE_MANIFEST")
        previous=cl
    return reasons


def verify_capacity(report, p):
    """Independent month arithmetic; legacy sealed reports remain byte-identical."""
    capacities = {}
    for split in p["splits"]:
        start_year,start_month=int(split["from"][:4]),int(split["from"][4:6])
        end_year,end_month=int(split["through"][:4]),int(split["through"][4:6])
        maximum=(end_year-start_year)*12+end_month-start_month+1
        if int(split["through"][6:]) < 15: maximum-=1
        required=p["minimum_complete_origins_per_split"]
        capacities[split["name"]]=dict(status="STRUCTURALLY_UNREACHABLE" if maximum<required else "POTENTIALLY_REACHABLE",
            maximum_monthly_origins=maximum,required_complete_origins=required)
        if report["schema_version"] == 2:
            rows=[r for r in report["samples"] if r["split"]==split["name"] and r["state"]=="SCORED"]
            count=len({r["origin"] for r in rows})
            agg=report["splits"][split["name"]]
            check(agg["protocol_capacity"]==capacities[split["name"]]
                  and agg["distinct_origins"]==count
                  and agg["sample_evidence_status"]==("MINIMUM_ORIGINS_MET" if count>=required else "INSUFFICIENT_EVIDENCE")
                  and agg["status"]==("STRUCTURALLY_UNREACHABLE" if maximum<required else
                      "EX_POST_RESEARCH_ONLY" if count>=required else "INSUFFICIENT_EVIDENCE"),"INDEPENDENT_PROTOCOL_CAPACITY")
    if report["schema_version"] == 2:
        verdict="STRUCTURALLY_UNREACHABLE" if any(v["status"]=="STRUCTURALLY_UNREACHABLE" for v in capacities.values()) else "INSUFFICIENT_EVIDENCE"
        check(report["protocol_capacity"]==capacities and report["hypothesis_verdict"]==verdict,"INDEPENDENT_PROTOCOL_CAPACITY")
    return capacities


def verify(out):
    out=Path(out).absolute()
    check(not any(p.is_symlink() for p in (out,*out.parents)),"INDEPENDENT_OUTPUT_LINK")
    seal,f,freeze,report=(load(out/n) for n in ("seal.json","frozen.json","freeze.json","report.json"))
    pin=digest(f)
    check(pin == freeze["pin"] == seal["pin"] == report["pin"],"INDEPENDENT_PIN")
    check(digest(f["protocol"]) == f["protocol_sha256"] == report["protocol_sha256"],"INDEPENDENT_PROTOCOL_PIN")
    check(set(seal["files"]) == {str(x.relative_to(out)) for x in out.rglob("*.json") if x.name != "seal.json"},"INDEPENDENT_FILES")
    for name,expected in seal["files"].items():
        path=out/name
        check(".." not in Path(name).parts and path.is_relative_to(out) and not path.is_symlink() and sha(path)==expected,"INDEPENDENT_REPORT_HASH")
    p=f["protocol"]
    check(report["schema_version"] in (1,2),"INDEPENDENT_REPORT_SCHEMA")
    capacities=verify_capacity(report,p)
    check(p["target"] == report["target"] == "rolling20_rms_daily_return_ratio" and p["horizons"] == [5,20]
          and p["holdout_was_previously_exposed"] is True,"INDEPENDENT_TARGET")
    # Independently derive month origins and purge windows from the frozen exchange calendar.
    exchanges={"SSE" if x.endswith(".SH") else "SZSE" for x in p["symbols"]}
    days=sorted(k.split(":")[1] for k,v in f["calendar"].items() if k.split(":")[0]==sorted(exchanges)[0]
                and v=="1" and p["source_start"] <= k.split(":")[1] <= p["source_end"])
    derived=[]
    for split in p["splits"]:
        for month in sorted({d[:6] for d in days if split["from"] <= d <= split["through"]}):
            choices=[d for d in days if d[:6]==month and d[6:] >= "15" and split["from"] <= d <= split["through"]]
            if not choices:continue
            origin=choices[0];i=days.index(origin)
            context=days[max(0,i+1-p["context_closes"]):i+1];future=days[i+1:i+21]
            exclusion="CONTEXT_UNAVAILABLE" if len(context)!=p["context_closes"] else "PURGED_SPLIT_BOUNDARY" if len(future)!=20 or future[-1]>split["through"] else None
            derived.append(dict(split=split["name"],origin=origin,context_days=context,target_days=future,exclusion=exclusion))
    check(derived==f["origins"],"INDEPENDENT_CALENDAR_SCHEDULE")
    records=report["samples"]
    splits={s["name"]:s for s in p["splits"]}
    expected={(o["split"],o["origin"],s) for o in f["origins"] for s in p["symbols"]}
    check(len(records)==len(expected) and {(x["split"],x["origin"],x["instrument"]) for x in records} == expected,"INDEPENDENT_SAMPLE_COMPLETENESS")
    scored=0;quality_checked=0;quality_unverified=0
    for row in records:
        origin=next(o for o in f["origins"] if o["split"]==row["split"] and o["origin"]==row["origin"])
        check(row["context_days"] == origin["context_days"] and row["target_days"] == origin["target_days"],"INDEPENDENT_SPLIT_DATES")
        split=splits[row["split"]]
        check(split["from"] <= row["origin"] <= split["through"],"INDEPENDENT_SPLIT_ORIGIN")
        path=out/"samples"/row["sample_id"]
        if (path/"prefix-source.json").exists():
            rejected=source_reasons(load(path/"prefix-source.json"));quality_checked+=1
            if row["state"]=="INPUT_BLOCKED":check(row["reason"] in rejected,"INDEPENDENT_INPUT_REJECTION")
            else:check(not rejected,"INDEPENDENT_INPUT_QUALITY")
        elif row["state"]=="INPUT_BLOCKED":
            # Partition absence can be proven directly from frozen accepted-version metadata.
            missing=any(d not in f["source_refs"]["partitions"][api] for d in row["context_days"] for api in ("daily","adj_factor","suspend_d"))
            check(missing,"INDEPENDENT_INPUT_REJECTION_EVIDENCE_MISSING");quality_checked+=1
        if (path/"outcome-source.json").exists():
            rejected=source_reasons(load(path/"outcome-source.json"));quality_checked+=1
            if row["state"]=="TARGET_BLOCKED":check(row["reason"] in rejected,"INDEPENDENT_TARGET_REJECTION")
            else:check(not rejected,"INDEPENDENT_TARGET_QUALITY")
        elif row["state"]=="TARGET_BLOCKED":
            missing=any(d not in f["source_refs"]["partitions"][api] for d in row["context_days"]+row["target_days"] for api in ("daily","adj_factor","suspend_d"))
            check(missing,"INDEPENDENT_TARGET_REJECTION_EVIDENCE_MISSING");quality_checked+=1
        if row["state"] != "SCORED": continue
        scored+=1
        check(len(row["context_days"]) == p["context_closes"] and len(row["target_days"]) == 20
              and row["context_days"][-1] == row["origin"] < row["target_days"][0]
              and row["target_days"][-1] <= split["through"] and row["target_sent_to_worker"] is False,"INDEPENDENT_NO_LOOKAHEAD")
        path=out/"samples"/row["sample_id"]
        check(load(path/"sample.json") == row,"INDEPENDENT_SAMPLE_REPORT")
        plan,proj,response,outcome=(load(path/n) for n in ("plan.json","projection.json","worker-response.json","outcome-input.json"))
        closes=quality(plan)
        full=quality(dict(frozen=outcome["frozen"],history=outcome["history"]))
        check(full[:len(closes)] == closes,"INDEPENDENT_PREFIX_CHANGED")
        rms,ewma=targets(closes)
        actual=targets(full)[0][-20:]
        request=json.loads(proj["worker_request_json"])
        check(request["input_mode"] == "historical_research_only" and len(request["series"]) == 1,"INDEPENDENT_WORKER_MODE")
        check(len(request["series"][0]["values"]) == len(closes)-20,"INDEPENDENT_WORKER_PREFIX_LENGTH")
        for a,b in zip(request["series"][0]["values"],rms,strict=True):near(a,b)
        check(hashlib.sha256(proj["worker_request_json"].encode()).hexdigest()==response["request_sha256"]==row["request_sha256"],"INDEPENDENT_WORKER_SHA")
        check(response["model_revision"]==p["model"]["revision"] and response["weight_sha256"]==p["model"]["weight_sha256"]
              and response["isolation"]["mechanism"]=="systemd-cgroup-v2+bubblewrap","INDEPENDENT_MODEL_ISOLATION")
        check(digest(response["forecasts"])==row["prediction_sha256"],"INDEPENDENT_PREDICTION_SHA")
        for a,b in zip(row["actual"],actual,strict=True):near(a,b)
        for name,values in row["predictions"].items():
            expected_values=response["forecasts"][0]["values"] if name=="timesfm" else [rms[-1] if name=="naive" else ewma]*20
            for a,b in zip(values,expected_values,strict=True):near(a,b)
            for h in (5,20):
                errors=[a-b for a,b in zip(values[:h],actual[:h])]
                xs=row["scores"][name][str(h)]
                for key,v in dict(mae=sum(abs(x) for x in errors)/h,mse=sum(x*x for x in errors)/h,
                    rmse=math.sqrt(sum(x*x for x in errors)/h),smape=sum(0 if a==b==0 else 2*abs(a-b)/(abs(a)+abs(b)) for a,b in zip(values[:h],actual[:h]))/h,
                    horizon_mean_absolute_error=abs(sum(values[:h])-sum(actual[:h]))/h).items():near(xs[key],v)
    check(report["counts"] == dict(Counter(x["state"] for x in records)),"INDEPENDENT_COUNTS")
    for split in p["splits"]:
        all_rows=[r for r in records if r["split"]==split["name"]]
        good=[r for r in all_rows if r["state"]=="SCORED"]
        agg=report["splits"][split["name"]]
        check(agg["scored"]==len(good) and agg["samples"]==len(all_rows),"INDEPENDENT_COVERAGE")
        near(agg["coverage"],len(good)/max(1,sum(r["state"]!="PURGED" for r in all_rows)))
        for name in ("timesfm","naive","ewma"):
            for h in ("5","20"):
                summary=agg["metrics"][name][h]
                if not good:
                    check(summary is None,"INDEPENDENT_EMPTY_METRICS");continue
                for key in ("mae","smape","horizon_mean_absolute_error"):
                    near(summary[key],sum(r["scores"][name][h][key] for r in good)/len(good))
                near(summary["rmse"],math.sqrt(sum(r["scores"][name][h]["mse"] for r in good)/len(good)))
        for baseline in ("naive","ewma"):
            for h in ("5","20"):
                paired=agg["paired"][baseline][h]
                check([x["sample_id"] for x in paired["samples"]]==[r["sample_id"] for r in good],"INDEPENDENT_PAIRED_SAMPLES")
                for x,r in zip(paired["samples"],good,strict=True):near(x["difference"],r["scores"]["timesfm"][h]["mae"]-r["scores"][baseline][h]["mae"])
                if good:near(paired["mean"],statistics.mean(x["difference"] for x in paired["samples"]))
    check(report["paper_allowed"] is False and report["live_allowed"] is False and report["can_execute_forward_paper"] is False
          and report["cloud_egress"]=="REAL_MARKET_DATA_EGRESS_DENIED" and report["calls"]==report["billable_calls"]==report["budget_writes"]==0,
          "INDEPENDENT_AUTHORITY")
    return dict(verified=True,verification="INDEPENDENT_STANDARD_LIBRARY_RECOMPUTATION_NOT_INDEPENDENT_ACCEPTANCE",
                pin=pin,samples=len(records),scored=scored,quality_decisions_recomputed=quality_checked,
                protocol_capacity=capacities,stored_report_schema_version=report["schema_version"],
                capacity_assessment="READ_ONLY_PROTOCOL_DIAGNOSIS_NOT_REQUALIFICATION",metrics_uploaded=False,real_data_egress=False)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("out",type=Path);args=parser.parse_args()
    try: print(json.dumps(verify(args.out)));raise SystemExit(0)
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError,AssertionError):
        print(json.dumps(dict(verified=False,error_code="INDEPENDENT_EVALUATION_REJECTED")));raise SystemExit(2)
