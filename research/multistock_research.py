"""Frozen, offline cross-sectional experiments. No account, order or promotion API."""
from __future__ import annotations

from collections import Counter, deque
import copy
from dataclasses import dataclass
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time

import multistock_data as data

D = Decimal
require, Error, sha, canonical = data.require, data.Error, data.sha, data.canonical
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "state" / "multistock-research"
STRATEGIES = ("momentum20_60", "reversal5", "inverse_vol20", "cash", "equal_weight", "sma20_60")
SOURCE_FILES = ("research/multistock_data.py", "research/multistock_research.py",
                "scripts/multistock-research.py", "research/historical_warehouse.py", "research/historical_sidecar.py")
SAFE = dict(**data.v1.SAFE, classification="EXPLORATORY", eligibility="ELIGIBILITY_DENIED")


def default_config(start=data.v1.START, end=data.v1.END):
    return dict(version="multistock-research-v1", start=start, end=end,
        momentum=[20,60], reversal=5, volatility=20, sma=[20,60], rebalance_sessions=5,
        max_positions=50, min_amount_thousand_cny="10000", turnover_cap="2",
        max_memory_mib=512, max_symbols=20000, max_sessions=1500,
        normalization="dimensionless_index_1_no_account_principal_no_shares",
        return_scale="adjusted_price_approximation_ex_post_not_taxed_total_return",
        execution="next_session_open_ex_post_uncertified_fractional_exposure",
        cash_rate="0", annual_sessions=252, label_horizon=1, purge_sessions=1, embargo_sessions=1,
        selection="precommitted_rules_no_fit_no_hyperparameter_or_winner_selection",
        universe="daily_observed_SSE_SZSE_A_code_families_consecutive_history_no_current_status_filter",
        cost_scenarios=[
            dict(name="gross",commission_bps="0",transfer_bps="0",slippage_bps="0",stamp_pre_bps="0",stamp_post_bps="0"),
            dict(name="base",commission_bps="3",transfer_bps="0.1",slippage_bps="10",stamp_pre_bps="10",stamp_post_bps="5"),
            dict(name="stress",commission_bps="5",transfer_bps="0.2",slippage_bps="30",stamp_pre_bps="10",stamp_post_bps="5")],
        stamp_switch="20230828",
        windows=[dict(name="development",role="development",start="20211101",end="20221230"),
            dict(name="validation",role="validation",start="20230103",end="20231229"),
            dict(name="wf2024",role="evaluation",train_end="20231229",start="20240101",end="20241231"),
            dict(name="wf2025",role="evaluation",train_end="20241231",start="20250101",end="20251231"),
            dict(name="wf2026",role="evaluation",train_end="20251231",start="20260101",end="20261030")])


def validate_config(config, ds):
    require(set(config) == set(default_config()), "CONFIG_FIELDS")
    require(config["start"] == ds.start and config["end"] == ds.end, "CONFIG_SOURCE_RANGE")
    fixed = default_config(ds.start, ds.end)
    for key in ("version","normalization","return_scale","execution","cash_rate","selection","universe",
                "annual_sessions","label_horizon","purge_sessions","embargo_sessions"):
        require(config[key] == fixed[key], "UNSUPPORTED_RESEARCH_CONVENTION")
    for key in ("reversal","volatility","rebalance_sessions","max_positions","max_symbols","max_sessions","max_memory_mib"):
        require(type(config[key]) is int and 1 <= config[key] <= 20000, "CONFIG_RESOURCE_OR_LOOKBACK")
    for key in ("momentum","sma"):
        require(len(config[key]) == 2 and all(type(x) is int and 1 <= x <= 252 for x in config[key])
                and config[key][0] < config[key][1], "CONFIG_LOOKBACK")
    require(config["volatility"] >= 2 and config["max_positions"] <= 500, "CONFIG_LOOKBACK_OR_POSITIONS")
    require(D(config["min_amount_thousand_cny"]).is_finite() and D(config["min_amount_thousand_cny"]) >= 0
            and D(config["turnover_cap"]).is_finite() and 0 <= D(config["turnover_cap"]) <= 2, "CONFIG_NUMERIC")
    require(config["windows"] and len({w["name"] for w in config["windows"]}) == len(config["windows"]), "CONFIG_WINDOWS")
    last = ""
    for w in config["windows"]:
        data.v1.day(w["start"]); data.v1.day(w["end"])
        require(ds.start <= w["start"] <= w["end"] <= ds.end and last < w["start"], "CONFIG_WINDOW_ORDER")
        require(w["role"] in ("development","validation","evaluation"), "CONFIG_WINDOW_ROLE")
        if w["role"] == "evaluation":
            require(ds.start <= w["train_end"] < w["start"], "CONFIG_TIME_LEAK")
        last = w["end"]
    require(len(config["cost_scenarios"]) >= 3 and len({s["name"] for s in config["cost_scenarios"]}) == len(config["cost_scenarios"]), "CONFIG_COST_SCENARIOS")
    for s in config["cost_scenarios"]:
        require(set(s) == set(fixed["cost_scenarios"][0]), "CONFIG_COST_FIELDS")
        for k,v in s.items():
            if k != "name":
                require(D(v).is_finite() and 0 <= D(v) <= 1000, "CONFIG_COST_RANGE")
    require(len(ds.days) <= config["max_sessions"], "SESSION_RESOURCE_LIMIT")


def number(value, positive=False):
    require(value is not None and not isinstance(value,(float,bool)), "RESEARCH_NUMBER_NULL_OR_FLOAT")
    n = D(value)
    require(n.is_finite() and (not positive or n > 0), "RESEARCH_NUMBER_INVALID")
    return n


def price(row, field):
    if row is None or row["factor"] is None:
        return None
    if "_adjusted_"+field in row:
        return row["_adjusted_"+field]
    return number(row["daily"][field], True) * number(row["factor"], True)


class Features:
    """Only completed rows up to this session; no future anchor or outcome is stored."""
    def __init__(self, config):
        self.config = config
        self.lookback = max(*config["momentum"],config["reversal"],config["volatility"],*config["sma"])
        self.history, self.last_index, self.current = {}, {}, {}
        self.gaps = 0

    def update(self, day, index):
        self.current = {r["ts_code"]:r for r in day["rows"]}
        for code,row in self.current.items():
            values = self.history.setdefault(code,deque(maxlen=self.lookback+1))
            if code in self.last_index and self.last_index[code] != index-1:
                values.clear()
                self.gaps += 1
            self.last_index[code] = index
            p = price(row,"close")
            if p is None:
                values.clear()
            else:
                values.append(p)
        require(len(self.history) <= self.config["max_symbols"], "SYMBOL_RESOURCE_LIMIT")

    def eligible(self):
        out = {}
        for code,row in self.current.items():
            if any(q in row["quality"] for q in ("BSE_CALENDAR_NOT_VERIFIED","CALENDAR_NOT_CONFIRMED",
                    "NON_A_OR_IDENTITY_UNVERIFIED","SOURCE_EXCHANGE_CONFLICT","BASIC_CLOSE_CONFLICT")):
                continue
            if len(self.history[code]) != self.lookback+1 or row["suspension_events"] is None:
                continue
            if any(e["suspend_type"] == "S" for e in row["suspension_events"]):
                continue
            if number(row["daily"]["vol"]) <= 0 or number(row["daily"]["amount"]) < D(self.config["min_amount_thousand_cny"]):
                continue
            out[code] = list(self.history[code])
        return out


def weights(codes, raw=None):
    if not codes:
        return {}
    values = [raw[c] if raw else D(1) for c in codes]
    total = sum(values,D(0))
    out = {c:v/total for c,v in zip(codes,values)}
    out[codes[-1]] += D(1)-sum(out.values(),D(0))
    return {c:str(v) for c,v in out.items()}


def targets(features, config):
    eligible = features.eligible()
    momentum, reversal, invvol, sma = {}, {}, {}, []
    for code,p in eligible.items():
        momentum[code] = sum((p[-1]/p[-h-1]-1 for h in config["momentum"]),D(0))/2
        reversal[code] = -(p[-1]/p[-config["reversal"]-1]-1)
        n = config["volatility"]
        returns = [p[i]/p[i-1]-1 for i in range(len(p)-n,len(p))]
        avg = sum(returns,D(0))/n
        vol = (sum(((r-avg)**2 for r in returns),D(0))/(n-1)).sqrt()
        invvol[code] = 1/max(vol,D("0.000001"))
        fast,slow=config["sma"]
        if sum(p[-fast:],D(0))/fast > sum(p[-slow:],D(0))/slow:
            sma.append(code)
    n = config["max_positions"]
    return dict(momentum20_60=weights(sorted((c for c in eligible if momentum[c]>0),key=lambda c:(-momentum[c],c))[:n]),
        reversal5=weights(sorted(eligible,key=lambda c:(-reversal[c],c))[:n]),
        inverse_vol20=weights(sorted(eligible,key=lambda c:(-invvol[c],c))[:n],invvol),
        cash={},equal_weight=weights(sorted(eligible)),sma20_60=weights(sorted(sma)[:n]))


def targets_from_history(days, config):
    f=Features(config)
    for i,d in enumerate(days):
        f.update(d,i)
    return targets(f,config)


def execution_block(row, side):
    if row is None:
        return "DAILY_MISSING"
    if row["factor"] is None:
        return "FACTOR_NULL"
    for flag in ("SOURCE_EXCHANGE_CONFLICT","BSE_CALENDAR_NOT_VERIFIED","CALENDAR_NOT_CONFIRMED","NON_A_OR_IDENTITY_UNVERIFIED"):
        if flag in row["quality"]:
            return flag
    if row["suspension_events"] is None:
        return "SUSPENSION_SOURCE_UNKNOWN"
    if any(e["suspend_type"] == "S" for e in row["suspension_events"]):
        return "SUSPENSION_EVENT"
    limit = row["limit"]
    if not limit or limit.get("up_limit") is None or limit.get("down_limit") is None:
        return "LIMIT_UNKNOWN"
    if limit.get("asset_type") not in (None,"STK"):
        return "ASSET_TYPE_UNVERIFIED"
    # Whole-session volume is not known at the assumed open. Liquidity filtering
    # belongs to completed t features; do not use t+1 volume to choose executions.
    p = number(row["daily"]["open"],True)
    if side=="buy" and p >= number(limit["up_limit"],True):
        return "UP_LIMIT_REFERENCE"
    if side=="sell" and p <= number(limit["down_limit"],True):
        return "DOWN_LIMIT_REFERENCE"
    return None


def cost_rate(scenario, side, date, switch="20230828"):
    bps = sum((D(scenario[k]) for k in ("commission_bps","transfer_bps","slippage_bps")),D(0))
    if side=="sell":
        bps += D(scenario["stamp_pre_bps" if date < switch else "stamp_post_bps"])
    return bps/10000


@dataclass(slots=True)
class Holding:
    units: D
    mark: D
    mark_date: str
    bought_index: int


class Portfolio:
    """Dimensionless fractional price exposures, never shares, cash CNY or broker fills."""
    def __init__(self, scenario, config):
        self.scenario, self.config = scenario, config
        self.cash, self.previous = D(1), D(1)
        self.holdings = {}
        self.series = []

    def value(self):
        return self.cash+sum((h.units*h.mark for h in self.holdings.values()),D(0))

    def mark(self, rows, field, date):
        for code,h in self.holdings.items():
            p=price(rows.get(code),field)
            if p is not None:
                h.mark,h.mark_date=p,date

    def step(self, day, index, target, rows=None):
        date=day["trade_date"]
        if rows is None:
            rows={r["ts_code"]:r for r in day["rows"]}
        self.mark(rows,"open",date)
        opening=self.value()
        turnover,cost,changes = D(0),D(0),0
        rejected=Counter()
        if target is not None:
            require(sum((D(v) for v in target.values()),D(0)) <= 1, "TARGET_LEVERAGE")
            remaining = opening*D(self.config["turnover_cap"])
            for side in ("sell","buy"):
                codes=sorted(self.holdings) if side=="sell" else sorted(target)
                for code in codes:
                    h=self.holdings.get(code)
                    current=h.units*h.mark if h else D(0)
                    wanted=opening*D(target.get(code,"0"))
                    delta=(current-wanted) if side=="sell" else (wanted-current)
                    if delta <= D("1e-28"):
                        continue
                    block=execution_block(rows.get(code),side)
                    if not block and side=="sell" and h.bought_index>=index:
                        block="T_PLUS_1_ASSUMPTION"
                    if remaining <= D("1e-28"):
                        block="TURNOVER_CAP"
                    if block:
                        rejected[block]+=1
                        continue
                    rate=cost_rate(self.scenario,side,date,self.config["stamp_switch"])
                    notional=min(delta,remaining)
                    if side=="buy":
                        notional=min(notional,self.cash/(1+rate))
                    if notional <= D("1e-28"):
                        rejected["CASH_CAP"]+=1
                        continue
                    p=price(rows[code],"open")
                    fee=notional*rate
                    if side=="sell":
                        h.units-=notional/p
                        self.cash+=notional-fee
                        if h.units <= D("1e-28"):
                            del self.holdings[code]
                    else:
                        self.cash-=notional+fee
                        if h:
                            h.units+=notional/p
                            h.bought_index=index
                        else:
                            self.holdings[code]=Holding(notional/p,p,date,index)
                    remaining-=notional
                    turnover+=notional/opening
                    cost+=fee
                    changes+=1
            require(self.cash >= D("-1e-28"), "NEGATIVE_NORMALIZED_CASH")
        self.mark(rows,"close",date)
        value=self.value()
        stale=[h for h in self.holdings.values() if h.mark_date != date]
        stale_value=sum((h.units*h.mark for h in stale),D(0))
        record=dict(trade_date=date,index=str(value),daily_return=str(value/self.previous-1),
            turnover=str(turnover),modeled_cost=str(cost),assumed_exposure_changes=changes,
            rejected=dict(rejected),stale_marks=len(stale),stale_weight=str(stale_value/value),
            terminal_zero_stale_index=str(value-stale_value),holdings=len(self.holdings))
        self.previous=value
        self.series.append(record)
        return record


def metrics(series, annual_sessions=252):
    if not series:
        return dict(sessions=0,total_return=None,annualized_return=None,volatility=None,sharpe=None,
                    status="NO_EVALUATION_SESSIONS")
    values=[number(r["daily_return"])+1 for r in series]
    index,peak,drawdown=D(1),D(1),D(0)
    for v in values:
        index*=v
        peak=max(peak,index)
        drawdown=min(drawdown,index/peak-1)
    returns=[float(v-1) for v in values]
    stdev=statistics.stdev(returns) if len(returns)>1 else 0
    rejected=Counter()
    for r in series:rejected.update(r["rejected"])
    stale_sessions=sum(r["stale_marks"]>0 for r in series)
    return dict(sessions=len(series),start=series[0]["trade_date"],end=series[-1]["trade_date"],
        total_return=str(index-1),annualized_return=str(index**(D(annual_sessions)/len(series))-1),
        volatility=stdev*math.sqrt(annual_sessions),
        sharpe=statistics.mean(returns)/stdev*math.sqrt(annual_sessions) if stdev else None,
        max_drawdown=str(drawdown),turnover=str(sum((D(r["turnover"]) for r in series),D(0))),
        modeled_cost_index_units=str(sum((D(r["modeled_cost"]) for r in series),D(0))),
        assumed_exposure_changes=sum(r["assumed_exposure_changes"] for r in series),
        rejected_changes=sum(rejected.values()),rejection_reasons=dict(rejected),
        stale_mark_sessions=stale_sessions,max_stale_weight=str(max(D(r["stale_weight"]) for r in series)),
        terminal_zero_stale_index=series[-1]["terminal_zero_stale_index"],
        status="PARTIAL_STALE_MARK_ASSUMPTIONS" if stale_sessions else "EXPLORATORY_UNCERTIFIED_EXECUTION")


def peak_rss_bytes():
    if os.name=="nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[("cb",wintypes.DWORD),("faults",wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
                ("peak_working","working","peak_paged","paged","peak_nonpaged","nonpaged","pagefile","peak_pagefile")]
        counters=Counters()
        counters.cb=ctypes.sizeof(counters)
        ok=ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(-1),ctypes.byref(counters),counters.cb)
        require(ok, "MEMORY_MEASUREMENT_FAILED")
        return counters.peak_working
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=="darwin" else 1024)


def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        while block:=f.read(1024*1024):h.update(block)
    return h.hexdigest()


def plan(ds, config):
    validate_config(config,ds)
    body=dict(version="multistock-frozen-plan-v1",**SAFE, config=config,
        source_refs=ds.refs, source_sha=ds.source_sha, query_sha=ds.query_sha, source_origin=ds.origin,
        code_sha={p:hash_file(ROOT/p) for p in SOURCE_FILES},
        arithmetic="Decimal_precision_50_portfolio_and_source; float_statistics_only",
        evaluation="fixed_rules_development_validation_late_expanding_walk_forward_no_selection_no_blind_alpha")
    return dict(body,plan_sha=sha(canonical(body)))


def output_path(path):
    p=Path(path).absolute()
    data.v1.no_links(p)
    require(p != OUTPUT_ROOT and p.is_relative_to(OUTPUT_ROOT), "OUTPUT_MUST_BE_IN_IGNORED_RESEARCH_ROOT")
    require(not p.exists(), "OUTPUT_ALREADY_EXISTS")
    return p


def write_json(path, value):
    Path(path).write_bytes(canonical(value)+b"\n")


def run(dataset, config, out, progress=None):
    out=output_path(out)
    started,wall,cpu=data.v1.now(),time.perf_counter(),time.process_time()
    with localcontext() as ctx:
        ctx.prec=50
        with dataset as ds:
            frozen=plan(ds,config)
            before=data.file_receipts(ds.roots)
            out.mkdir(parents=True)
            write_json(out/"plan.json",frozen)
            for relative in SOURCE_FILES:
                target=out/"frozen-source"/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/relative).read_bytes())
            features=Features(config)
            books={f"{name}/{s['name']}":Portfolio(s,config) for name in STRATEGIES for s in config["cost_scenarios"]}
            folds={w["name"]:dict(window=w,books={},dates=[d for d in ds.days if w["start"]<=d<=w["end"]])
                   for w in config["windows"] if w["role"]=="evaluation"}
            for f in folds.values():
                f["evaluation_dates"]=f["dates"][config["embargo_sessions"]:]
                f["books"]={k:Portfolio(b.scenario,config) for k,b in books.items()}
            counts,quality,exchanges,side_counts,unmatched=Counter(),Counter(),Counter(),Counter(),Counter()
            seen,set_eligible=set(),set()
            daily_coverage=[]
            stream=hashlib.sha256()
            pending=None
            pending_date=None
            try:
                with (out/"daily.jsonl").open("wb") as daily_file,(out/"signals.jsonl").open("wb") as signal_file:
                    for i,date in enumerate(ds.days):
                        day=ds.read_day(date)
                        rows=day["rows"]
                        for r in rows:
                            r["_adjusted_open"]=price(r,"open")
                            r["_adjusted_close"]=price(r,"close")
                        by_code={r["ts_code"]:r for r in rows}
                        counts["daily_rows"]+=len(rows)
                        counts["processed_sessions"]+=1
                        seen.update(r["ts_code"] for r in rows)
                        for r in rows:
                            quality.update(r["quality"])
                            exchanges[r["exchange"]]+=1
                        side_counts.update(day["sidecar_rows"])
                        unmatched.update(day["sidecar_without_daily"])
                        stream.update(canonical(dict(date=date,rows=[(r["ts_code"],r["daily"]["_row_sha"],
                            r["factor_source"]["_row_sha"] if r["factor_source"] else None,
                            r["daily_basic"]["_row_sha"] if r["daily_basic"] else None,
                            r["limit"]["_row_sha"] if r["limit"] else None) for r in rows])))
                        full={k:b.step(day,i,pending[k.split('/')[0]] if pending is not None else None,by_code) for k,b in books.items()}
                        wf={}
                        wf_signal_dates={}
                        for name,f in folds.items():
                            if date not in f["evaluation_dates"]:
                                continue
                            # Reset exposure at every fold. Left-side price history is reusable, outcomes are not fitted.
                            activate=not next(iter(f["books"].values())).series
                            use=targets(features,config) if activate else pending
                            wf[name]={k:b.step(day,i,use[k.split('/')[0]] if use is not None else None,by_code) for k,b in f["books"].items()}
                            wf_signal_dates[name]=ds.days[i-1] if activate else pending_date
                        daily_file.write(canonical(dict(trade_date=date,full=full,walk_forward=wf,
                            signal_date=pending_date if pending is not None else None,walk_forward_signal_dates=wf_signal_dates))+b"\n")
                        features.update(day,i)
                        eligible=features.eligible()
                        set_eligible.update(eligible)
                        daily_coverage.append(dict(trade_date=date,observed=len(rows),eligible=len(eligible)))
                        pending=None
                        pending_date=None
                        if i>=features.lookback and (i-features.lookback)%config["rebalance_sessions"]==0:
                            pending=targets(features,config)
                            pending_date=date
                            signal_file.write(canonical(dict(signal_date=date,earliest_execution=ds.days[i+1] if i+1<len(ds.days) else None,
                                eligible=len(eligible),targets={k:dict(count=len(v),sha=sha(canonical(v))) for k,v in pending.items()}))+b"\n")
                        rss=peak_rss_bytes()
                        require(rss <= config["max_memory_mib"]*1024**2, "MEMORY_RESOURCE_LIMIT")
                        if progress and (i+1==len(ds.days) or (i+1)%100==0):
                            progress(dict(processed_sessions=i+1,date=date,daily_rows=counts["daily_rows"],
                                          elapsed_seconds=round(time.perf_counter()-wall,3),peak_rss_bytes=rss))
                full_results={k:metrics(b.series) for k,b in books.items()}
                windows={w["name"]:{k:metrics([r for r in b.series if w["start"]<=r["trade_date"]<=w["end"]])
                         for k,b in books.items()} for w in config["windows"]}
                fold_results={name:dict(window=f["window"],embargo_dates=f["dates"][:config["embargo_sessions"]],
                    training="EXPANDING_LEFT_HISTORY_FIXED_RULES_NO_FIT",purged_training_signal_sessions=config["purge_sessions"],
                    results={k:metrics(b.series) for k,b in f["books"].items()}) for name,f in folds.items()}
                relative={}
                for k,result in full_results.items():
                    scenario=k.split('/')[1]
                    relative[k]={name:str(D(result["total_return"])-D(full_results[f"{name}/{scenario}"]["total_return"]))
                                 for name in ("cash","equal_weight","sma20_60")}
                obtained=[a["obtained_at"] for ps in ds.partitions.values() for p in ps.values()
                          for a in p["manifest"]["attempts"] if a.get("obtained_at")]
                result=dict(**SAFE,state="COMPLETED_COVERAGE_PARTIAL",source_origin=ds.origin,plan_sha=frozen["plan_sha"],
                    source_sha=ds.source_sha,query_sha=ds.query_sha,read_stream_sha=stream.hexdigest(),
                    range=[ds.start,ds.end],version_bounds=ds.refs["version_bounds"],
                    source_obtained_at=dict(first=min(obtained) if obtained else None,last=max(obtained) if obtained else None),
                    coverage=dict(counts,observed_securities=len(seen),eligible_securities=len(set_eligible),
                        by_exchange=dict(exchanges),sidecar_rows=dict(side_counts),sidecar_without_daily=dict(unmatched),
                        partition_quality=ds.inspect()["apis"],
                        quality=dict(quality),observed_series_gaps=features.gaps,daily=daily_coverage,
                        observed_current_catalog_delisted=sum(ds.catalog.get(c,{}).get("list_status")=="D" for c in seen),
                        bse_calendar="NOT_VERIFIED",historical_universe="NOT_VERIFIED"),
                    full_period=full_results,windows=windows,walk_forward=fold_results,relative_total_return=relative,
                    assumptions=assumptions(config),read_only_source_unchanged=before==data.file_receipts(ds.roots))
                require(result["read_only_source_unchanged"], "SOURCE_FILES_CHANGED")
                write_json(out/"results.json",result)
                execution=dict(started_at=started,ended_at=data.v1.now(),wall_seconds=time.perf_counter()-wall,
                    cpu_seconds=time.process_time()-cpu,peak_rss_bytes=peak_rss_bytes(),
                    python=platform.python_version(),sqlite=data.v1.sqlite3.sqlite_version,platform=platform.system(),
                    threads=1,workers=1,source_file_receipts_before=before,
                    source_file_receipts_after=data.file_receipts(ds.roots),
                    validation="incremental_new_logic_only_no_old_raw_or_full_database_hash",http_api_calls=0,token_reads=0,
                    cloud_model_calls=0,paid_calls=0,processed_sessions=len(ds.days),daily_rows=counts["daily_rows"])
                write_json(out/"execution.json",execution)
                files=["plan.json","results.json","daily.jsonl","signals.jsonl"]+["frozen-source/"+p for p in SOURCE_FILES]
                hashes={p:hash_file(out/p) for p in files}
                run_receipt=dict(**SAFE,output_sha=sha(canonical(hashes)),files=hashes,execution_sha=hash_file(out/"execution.json"))
                write_json(out/"run.json",run_receipt)
                return dict(results=result,execution=execution,output_sha=run_receipt["output_sha"])
            except BaseException as e:
                write_json(out/"interrupted.json",dict(**SAFE,state="PARTIAL_INTERRUPTED",reason=str(e) if isinstance(e,Error) else type(e).__name__,
                    processed=dict(counts),last_completed_date=daily_coverage[-1]["trade_date"] if daily_coverage else None,
                    frozen_plan_sha=frozen["plan_sha"],recovery="new_output_directory_same_frozen_version_bounds_no_refetch"))
                raise


def assumptions(config):
    return dict(return_scale=config["return_scale"],normalization=config["normalization"],cash_rate="0",
        risk_free_rate="0",annual_sessions=config["annual_sessions"],signal="t_completed_close_to_t_plus_1_open_or_later",
        adjustment="raw_price_times_same_date_factor_no_future_anchor; ex_post_revisions_not_PIT",
        turnover="sum_buy_and_sell_notional_divided_by_pre_rebalance_index",execution_certification="NOT_VERIFIED",
        lot_100="NOT_MODELED_FRACTIONAL_DIMENSIONLESS_EXPOSURES_NO_AUTHORIZED_PRINCIPAL",
        t_plus_1="no_same_session_sale_of_new_exposure; weekly_changes; not_broker_settlement_certification",
        suspension="explicit_S_blocks; zero_events_remains_UNKNOWN_UNCERTIFIED",
        liquidity="prior_completed_session_amount_filter; volume_and_open_reference_only_no_depth_or_capacity_proof",
        costs="proportional_assumptions_including_sell_stamp_schedule; no_minimum_commission_or_empirical_impact_calibration",
        missing_marks="last_observed_adjusted_mark_carry_explicit_PARTIAL; terminal_zero_stale_sensitivity_not_actual_recovery",
        benchmark="cash; all_eligible_equal_weight_weekly; code_sorted_capped_SMA; same_sources_and_execution_cost_rules",
        selection="three_precommitted_rules_no_winner_selection; late_period_not_used_for_parameter_choice; not_independent_blind_test",
        license="local_personal_research_no_raw_redistribution_or_cloud_sharing_grant")


def verify(out):
    out=Path(out).absolute()
    data.v1.no_links(out)
    require(out.is_relative_to(OUTPUT_ROOT), "OUTPUT_MUST_BE_IN_IGNORED_RESEARCH_ROOT")
    receipt=json.loads((out/"run.json").read_bytes())
    expected={"plan.json","results.json","daily.jsonl","signals.jsonl"}|{"frozen-source/"+p for p in SOURCE_FILES}
    require(set(receipt["files"])==expected, "OUTPUT_MANIFEST_FILES")
    for relative,digest in receipt["files"].items():
        data.v1.no_links(out/relative)
        require(hash_file(out/relative)==digest, "OUTPUT_HASH_MISMATCH")
    require(sha(canonical(receipt["files"]))==receipt["output_sha"], "OUTPUT_MANIFEST_SHA")
    require(hash_file(out/"execution.json")==receipt["execution_sha"], "EXECUTION_HASH_MISMATCH")
    frozen=json.loads((out/"plan.json").read_bytes())
    plan_sha=frozen.pop("plan_sha")
    require(sha(canonical(frozen))==plan_sha, "PLAN_SHA_MISMATCH")
    results=json.loads((out/"results.json").read_bytes())
    require(results["plan_sha"]==plan_sha and not results["paper_allowed"] and not results["live_allowed"], "RESULT_PLAN_OR_ELIGIBILITY")
    for relative,digest in frozen["code_sha"].items():
        require(hash_file(out/"frozen-source"/relative)==digest, "FROZEN_CODE_SHA")
    return dict(**SAFE,verified=True,scope="NEW_RESEARCH_ARTIFACTS_ONLY_NOT_OLD_SOURCE_REVERIFY",
                plan_sha=plan_sha,output_sha=receipt["output_sha"])


def brief(result):
    return dict(**{k:result[k] for k in ("state","source_origin","plan_sha","source_sha","query_sha","range","version_bounds",
                "data_mode","historical_pit_status","forward_research_readiness","paper_allowed","live_allowed")},
        coverage={k:v for k,v in result["coverage"].items() if k!="daily"},
        full_period={k:{f:r[f] for f in ("total_return","annualized_return","max_drawdown","sharpe","turnover",
                     "rejected_changes","stale_mark_sessions")} for k,r in result["full_period"].items()})
