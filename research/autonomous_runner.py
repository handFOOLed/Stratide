"""Bounded multi-candidate streaming using PR62's Portfolio and source contracts."""
from __future__ import annotations

from collections import Counter, deque
from decimal import Decimal as D, localcontext
import gzip
import json
from pathlib import Path
import time

import autonomous_dsl as dsl
import multistock_research as m

require, canonical, sha = m.require, m.canonical, m.sha
BENCHMARKS = ("cash", "matched_equal_weight", "simple_positive_return")


def dump_book(book):
    return dict(cash=str(book.cash), previous=str(book.previous),
                holdings={c:dict(units=str(h.units), mark=str(h.mark), mark_date=h.mark_date,
                                bought_index=h.bought_index) for c,h in book.holdings.items()})


def load_book(book, state):
    book.cash, book.previous = D(state["cash"]), D(state["previous"])
    book.holdings = {c:m.Holding(D(h["units"]), D(h["mark"]), h["mark_date"], h["bought_index"])
                     for c,h in state["holdings"].items()}


def dump_features(f):
    return dict(history={c:[str(v) for v in q] for c,q in f.history.items()},
                amounts={c:list(q) for c,q in f.amounts.items()}, last_index=f.last_index, gaps=f.gaps,
                current={c:{k:v for k,v in row.items() if not k.startswith("_adjusted_")}
                         for c,row in f.current.items()})


def load_features(f, state):
    f.history = {c:deque(map(D,q), maxlen=f.lookback+1) for c,q in state["history"].items()}
    f.amounts = {c:deque(q, maxlen=f.lookback+1) for c,q in state["amounts"].items()}
    f.last_index, f.gaps, f.current = state["last_index"], state["gaps"], state["current"]


def benchmark_targets(eligible, config):
    cap = config["max_positions"]
    positive = [c for c,p in eligible.items() if p[-1] > p[-21]]
    return dict(cash={}, matched_equal_weight=m.weights(sorted(eligible)[:cap]),
                simple_positive_return=m.weights(sorted(positive)[:cap]))


def select(features, proposals, config, index, force=False):
    eligible = features.eligible()
    targets, diagnostics = {}, {}
    for name,p in proposals.items():
        ast = p["ast"]
        if force or (index >= features.lookback and (index-features.lookback)%ast["rebalance_sessions"] == 0):
            targets[name], diagnostics[name] = features.targets(ast, eligible)
    if force or (index >= features.lookback and (index-features.lookback)%config["rebalance_sessions"] == 0):
        targets.update(benchmark_targets(eligible, config))
    return targets, diagnostics, eligible


def iter_daily(root, chunks):
    for chunk in chunks:
        with gzip.open(root/chunk/"daily.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                yield json.loads(line)


def step(book, day, index, target, rows):
    before = {c:(h.units, h.mark) for c,h in book.holdings.items()}
    record = book.step(day, index, target, rows)
    record.update(normalized_cash=str(book.cash),
                  position_value=str(sum((h.units*h.mark for h in book.holdings.values()), D(0))))
    if D(record["daily_return"]) < D("-0.05") or D(record["stale_weight"]) > D("0.1"):
        contributions = []
        for code in before.keys() | book.holdings.keys():
            old_units, old_mark = before.get(code, (D(0), D(0)))
            h = book.holdings.get(code)
            opening = m.price(rows.get(code), "open")
            opening = old_mark if opening is None else opening
            closing = h.mark if h else opening
            pnl = old_units*(opening-old_mark)+(h.units if h else D(0))*(closing-opening)
            contributions.append(dict(ts_code=code, price_contribution=str(pnl),
                end_exposure=str(h.units*h.mark) if h else "0", mark_date=h.mark_date if h else day["trade_date"],
                source_row_sha=rows[code]["daily"]["_row_sha"] if code in rows else None))
        record["worst_price_contributions"] = sorted(contributions, key=lambda v:(D(v["price_contribution"]),v["ts_code"]))[:3]
    return record


def audit_daily(record, previous, cap):
    for group, books in [("full",record["full"]), *record["walk_forward"].items()]:
        for name,r in books.items():
            key = (group, name)
            value = D(r["index"])
            require(abs(D(r["normalized_cash"])+D(r["position_value"])-value) < D("1e-40"), "INDEX_CONSERVATION")
            require(D(r["normalized_cash"]) >= D("-1e-28") and D(r["position_value"]) >= 0 and
                    0 <= D(r["modeled_cost"]) and 0 <= D(r["turnover"]) <= D("2.000000000000000000000000001"), "CASH_COST_TURNOVER_DIRECTION")
            require(0 <= r["holdings"] <= cap, "HOLDINGS_CAP")
            require(abs(D(r["daily_return"])-(value/previous.get(key,D(1))-1)) < D("1e-40"), "JOURNAL_RETURN_RECURRENCE")
            if r["assumed_exposure_changes"]:
                signal = record["signal_date"] if group == "full" else record["walk_forward_signal_dates"][group]
                require(signal and signal < record["trade_date"], "FUTURE_SIGNAL_LEAK")
            previous[key] = value


def summarize(root, chunks, frozen, counts):
    full, folds = {}, {}
    previous = {}
    for record in iter_daily(root, chunks):
        audit_daily(record, previous, frozen["config"]["max_positions"])
        for key,value in record["full"].items():
            full.setdefault(key, []).append(value)
        for name,books in record["walk_forward"].items():
            for key,value in books.items():
                folds.setdefault(name, {}).setdefault(key, []).append(value)
    config = frozen["config"]
    windows = {w["name"]:{k:m.metrics([r for r in series if w["start"] <= r["trade_date"] <= w["end"]])
                           for k,series in full.items()} for w in config["windows"]}
    results = {k:m.metrics(series) for k,series in full.items()}
    failures = {}
    for key,r in results.items():
        if not key.startswith("candidate_"):
            continue
        series = full[key]
        failures[key] = dict(negative_return=r["total_return"] is not None and D(r["total_return"]) < 0,
            worst_days=sorted(series, key=lambda v:D(v["daily_return"]))[:3],
            reason=("NEGATIVE_OR_STALE_IS_RESEARCH_EVIDENCE_NOT_ENGINEERING_FAILURE"),
            stale_warning=r.get("stale_mark_sessions", 0), rejection_reasons=r.get("rejection_reasons", {}))
    return dict(**m.SAFE, state="COMPLETED", round_sha=frozen["round_sha"],
                source_sha=frozen["source_sha"], source_origin=frozen["source_origin"], version_bounds=frozen["version_bounds"],
                range=[config["start"],config["end"]], full_period=results, windows=windows,
                walk_forward={name:{key:m.metrics(series) for key,series in books.items()} for name,books in folds.items()},
                coverage=counts, failure_attribution=failures,
                benchmark_comparison={k:{b:str(D(v["total_return"])-D(results[f"{b}/{k.split('/')[1]}"]["total_return"]))
                    for b in BENCHMARKS} for k,v in results.items() if k.startswith("candidate_")},
                assumptions=dict(m.assumptions(config), benchmark="same_eligibility_same_position_cap_same_costs_same_min_holding",
                                 exposure_label="REUSED_EXPOSED_PERIOD", historical_pit_status="NOT_VERIFIED"),
                proposed=len(frozen["proposals"]), rejected=frozen["rejected"],
                evidence_allowed_for_next_round="DEVELOPMENT_ONLY", sealed_results=True,
                exposure_label="EXPLORATORY_EX_POST / REUSED_EXPOSED_PERIOD")


def evaluate(ds, config, frozen, root, checkpoint, commit, controls, limits, progress=None, fault=None):
    """A committed chunk is the recovery unit. Incomplete chunks have no effects outside research."""
    wall = time.perf_counter()
    features = dsl.Features(config)
    proposals = frozen["proposals"]
    names = tuple(proposals) + BENCHMARKS
    books = {f"{name}/{s['name']}":m.Portfolio(s, dict(config, hard_position_cap=config["max_positions"],
                min_hold_sessions=proposals[name]["ast"]["min_hold_sessions"] if name in proposals else 5))
             for name in names for s in config["cost_scenarios"]}
    folds = {w["name"]:dict(window=w, dates=[d for d in ds.days if w["start"] <= d <= w["end"]][1:],
                started=False, books={k:m.Portfolio(b.scenario, b.config) for k,b in books.items()})
             for w in config["windows"] if w["role"] == "evaluation"}
    counts = dict(processed_sessions=0, daily_rows=0, sidecar_rows={}, seen=[], eligible=[],
                  feature_rejections={}, empty_signals={}, read_stream_sha=sha(b""))
    pending, pending_date = {}, None
    if checkpoint:
        load_features(features, checkpoint["features"])
        counts, pending, pending_date = checkpoint["counts"], checkpoint["pending"], checkpoint["pending_date"]
        for k,b in books.items():
            load_book(b, checkpoint["books"][k])
        for name,f in folds.items():
            f["started"] = checkpoint["folds"][name]["started"]
            for k,b in f["books"].items():
                load_book(b, checkpoint["folds"][name]["books"][k])
    seen, eligible_seen = set(counts["seen"]), set(counts["eligible"])
    side = Counter(counts["sidecar_rows"])
    missing, empty = Counter(counts["feature_rejections"]), Counter(counts["empty_signals"])
    records, signals = [], []

    def save():
        nonlocal records, signals
        if not records:
            return
        counts.update(seen=sorted(seen), eligible=sorted(eligible_seen), sidecar_rows=dict(side),
                      feature_rejections=dict(missing), empty_signals=dict(empty))
        state = dict(features=dump_features(features), counts=counts, pending=pending, pending_date=pending_date,
                     books={k:dump_book(b) for k,b in books.items()},
                     folds={name:dict(started=f["started"], books={k:dump_book(b) for k,b in f["books"].items()})
                            for name,f in folds.items()})
        commit(records, signals, state)
        records, signals = [], []

    for i in range(counts["processed_sessions"], len(ds.days)):
        control = controls()
        reason = "CANCELLED" if control["cancelled"] else "PAUSED" if control["paused"] else None
        if not reason and (time.perf_counter()-wall >= limits["wall_seconds"] or
                           m.peak_rss_bytes() > limits["memory_mib"]*1024**2):
            reason = "PARTIAL_RESOURCE_LIMIT"
        if reason:
            save()
            return reason
        date = ds.days[i]
        day = ds.read_day(date)
        rows = {r["ts_code"]:r for r in day["rows"]}
        for row in rows.values():
            row["_adjusted_open"], row["_adjusted_close"] = m.price(row, "open"), m.price(row, "close")
        # Execution always precedes this session's feature update.
        full = {k:step(b, day, i, pending.get(k.split('/')[0]), rows) for k,b in books.items()}
        wf, wf_dates = {}, {}
        for name,f in folds.items():
            if date not in f["dates"]:
                continue
            use = pending
            if not f["started"]:
                use,_,_ = select(features, proposals, config, i-1, force=True)
            wf_dates[name] = ds.days[i-1] if not f["started"] else pending_date
            wf[name] = {k:step(b, day, i, use.get(k.split('/')[0]), rows) for k,b in f["books"].items()}
            f["started"] = True
        records.append(dict(trade_date=date, signal_date=pending_date, full=full, walk_forward=wf,
                            walk_forward_signal_dates=wf_dates))
        # Series live in immutable chunk journals. Retain only the current day's record in each book.
        for b in books.values():
            b.series.clear()
        for f in folds.values():
            for b in f["books"].values():
                b.series.clear()
        features.update(day, i)
        pending, diagnostics, eligible = select(features, proposals, config, i)
        pending_date = date if pending else None
        if pending:
            signals.append(dict(signal_date=date, earliest_execution=ds.days[i+1] if i+1 < len(ds.days) else None,
                targets={k:dict(weights=v, sha=sha(canonical(v))) for k,v in pending.items()}, diagnostics=diagnostics,
                source_rows_sha=sha(canonical([(c,r["daily"]["_row_sha"]) for c,r in rows.items()]))))
        for name,diag in diagnostics.items():
            missing[name] += diag["missing_features"]
            empty[name] += diag["selected"] == 0
        seen.update(rows)
        eligible_seen.update(eligible)
        side.update(day["sidecar_rows"])
        counts["daily_rows"] += len(rows)
        counts["processed_sessions"] = i+1
        counts["read_stream_sha"] = sha(canonical([counts["read_stream_sha"], date,
            [(c,r["daily"]["_row_sha"], r["versions"], r["factor_source"]["_row_sha"] if r["factor_source"] else None,
              r["daily_basic"]["_row_sha"] if r["daily_basic"] else None,
              r["limit"]["_row_sha"] if r["limit"] else None) for c,r in rows.items()]]))
        if fault:
            fault("evaluate", i+1)
        if len(records) >= limits["checkpoint_sessions"] or i+1 == len(ds.days):
            save()
            if progress:
                progress(dict(processed_sessions=i+1, date=date, daily_rows=counts["daily_rows"],
                              elapsed_seconds=round(time.perf_counter()-wall, 3), peak_rss_bytes=m.peak_rss_bytes()))
    return "EVALUATED"
