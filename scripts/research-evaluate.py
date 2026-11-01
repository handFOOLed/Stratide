"""Issue #13: offline quality gate and read-only evaluation of verified paper outputs.

audit freezes the objective supported suffix and 70/30 split BEFORE replay.
evaluate backs up SQLite read-only, re-exports via the existing CLI, compares all
six reports, and uses the existing engine for independent fixed-entry benchmarks.
Only new gitignored output directories; no network, third-party dependencies,
strategy optimization, financial kernel edits or original evidence writes.
"""
import argparse
import contextlib
import csv
import datetime as dt
from decimal import Decimal, localcontext
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "m1-pr06-research-v1"
PROTOCOL_FILE = ROOT / "docs/M1_PR06_RESEARCH_PROTOCOL.md"
NAMES = ("report.json", "events.json", "daily.csv", "orders.csv", "fills.csv", "positions.csv")
FLAGS = ("--initial-cash-fen", "--max-order-fen", "--account-cap-fen",
         "--strategy-cap-fen", "--daily-loss-fen", "--drawdown-fen")
CAPITAL = (10000000, 500000, 2000000, 2000000, 100000, 500000)
spec = importlib.util.spec_from_file_location("historical_data", Path(__file__).with_name("historical-data.py"))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def new_output(path):
    path = path.resolve()
    require(subprocess.run(["git", "check-ignore", "--quiet", str(path / "evaluation.json")],
                           cwd=ROOT).returncode == 0, "output must be gitignored")
    path.mkdir(parents=True, exist_ok=False)
    return path


def split_for(dataset):
    days = [s["day"] for s in dataset["sessions"]]
    k = len(days) * 70 // 100
    return dict(protocol_version=PROTOCOL, protocol_sha256=sha(PROTOCOL_FILE),
                days=days, count=len(days), development_count=k,
                development_end=days[k-1] if k else None,
                holdout_start=days[k] if 0 < k < len(days) else None,
                holdout_was_previously_exposed=True,
                holdout_kind="retrospective_historical_not_prospective_OOS")


def audit(source, out):
    """No strategy returns are read or computed here."""
    extraction = read(source / "extraction.json")
    require(extraction["params"] == dict(ts_code="600000.SH", exchange="SSE",
                                        start_date="20240101", end_date="20261028"),
            "audit requires the frozen target query, not a performance-selected range")
    start, end = "20240101", "20261028"
    cal = adapter.index(adapter.rows(source / "calendar.json"), "cal_date", start, end, True)
    daily = adapter.index(adapter.rows(source / "daily.json"), "trade_date", start, end)
    limits = adapter.index(adapter.rows(source / "limits.json"), "trade_date", start, end)
    suspension_rows = adapter.rows(source / "suspensions.json")
    expected = {(adapter.day(start)+dt.timedelta(days=i)).strftime("%Y%m%d")
                for i in range((adapter.day(end)-adapter.day(start)).days+1)}
    opened = sorted(d for d, r in cal.items() if str(r["is_open"]) == "1")
    missing = sorted(set(opened)-set(daily))
    missing_limits = sorted(set(opened)-set(limits))
    unknown = sorted(d for d, r in cal.items() if str(r["is_open"]) not in ("0", "1"))
    discontinuities, invalid = [], []
    previous = None
    for date in opened:
        if date not in daily:
            previous = None
            continue
        row = daily[date]
        try:
            values = {k: adapter.exact(row[k], 100) for k in ("open", "high", "low", "close", "pre_close", "vol")}
            require(0 < values["low"] <= min(values["open"], values["close"]) <=
                    max(values["open"], values["close"]) <= values["high"], "invalid OHLC")
            if date in limits:
                lower = adapter.exact(limits[date]["down_limit"], 100)
                upper = adapter.exact(limits[date]["up_limit"], 100)
                require(0 < lower < upper and all(lower <= values[k] <= upper for k in ("open", "high", "low", "close")),
                        "invalid price band")
            if previous is not None and values["pre_close"] != previous:
                discontinuities.append(date)
            previous = values["close"]
        except (ValueError, KeyError, TypeError):
            invalid.append(date)
            previous = None
    reasons = ["historical rule/fee coverage before 20260706 is unsupported"]
    if discontinuities:
        reasons.append("corporate-action/adjustment discontinuities; no corporate action accounting")
    result = dict(protocol_version=PROTOCOL, protocol_sha256=sha(PROTOCOL_FILE),
                  target_start=start, target_end=end, source_type=extraction["response_kind"],
                  extraction=extraction, api_fields=adapter.FIELDS,
                  raw_sha256={k: sha(source / f"{k}.json") for k in adapter.APIS},
                  units="CNY yuan*100 -> exact integer fen; vol lots*100 -> exact integer shares",
                  numeric_parser="Decimal; no binary float conversion or zero filling",
                  source_rows=len(daily), exchange_open_days=len(opened), calendar_rows=len(cal),
                  missing_calendar_days=sorted(expected-set(cal)), unknown_calendar_days=unknown,
                  missing_daily_days=missing, extra_daily_days=sorted(set(daily)-set(opened)),
                  missing_limit_days=missing_limits, invalid_numeric_or_ohlc_days=invalid,
                  suspension_events=len(suspension_rows), discontinuity_days=discontinuities,
                  data_coverage="DATA_BLOCKED", target_blockers=reasons,
                  historical_PIT="NOT_VERIFIED", revision_history="unavailable",
                  selected_window="BLOCKED", selected_start=None, selected_end=None)
    # Retain the audit even when no supported suffix exists.
    write(out / "audit.json", result)
    predecessors_valid = all(str(cal[date]["pretrade_date"]) == opened[i-1]
                             for i, date in enumerate(opened) if i)
    require(set(cal) == expected and not unknown and not missing and not missing_limits and predecessors_valid
            and not invalid and set(daily) == set(opened), "incomplete target source; audit retained, no selection/replay")
    require(end in daily, "fixed end day missing; no endpoint selection")
    lower = max("20260706", max(discontinuities, default="00000000"))
    selected = [d for d in opened if d >= "20260706" and
                (d > lower if lower in discontinuities else d >= lower)]
    require(selected and selected[-1] == end, "no supported contiguous suffix")
    selected_start = selected[0]
    # Existing adapter is the authority. No exception catch to bypass a BLOCKED prepare.
    with contextlib.redirect_stdout(io.StringIO()):
        adapter.prepare(source, out / "input", selected_start, end)
    dataset = read(out / "input/dataset.json")
    split = split_for(dataset)
    split["input_sha256"] = sha(out / "input/dataset.json")
    write(out / "split.json", split)
    result.update(selected_window="COMPLETE", selected_start=selected_start, selected_end=end,
                  selected_sessions=len(dataset["sessions"]), selected_missing_days=0,
                  input_sha256=split["input_sha256"])
    write(out / "audit.json", result)
    return result


def cli(exe, *args):
    result = subprocess.run([str(exe.resolve()), *map(str, args)], capture_output=True, timeout=120)
    require(result.returncode == 0, "existing CLI rejected input/ledger/benchmark: " +
            result.stderr.decode("utf-8", errors="replace")[:2000])


def verify_reports(exe, dataset_path, ledger, report, out):
    """Backup from a read-only SQLite transaction; original lock/db never written.

    Existing Rust open/history replays every command and verifies the v3 chain.
    Original six reports must equal its fresh export, not a self-declared JSON SHA.
    """
    copied = out / "verified-ledger"
    copied.mkdir()
    with sqlite3.connect(ledger.joinpath("ledger.sqlite").resolve().as_uri()+"?mode=ro", uri=True) as original:
        with sqlite3.connect(copied / "ledger.sqlite") as backup:
            original.backup(backup)
    cli(exe, "paper-report", dataset_path, copied, out / "verified-report", "--sha256", sha(dataset_path))
    for name in NAMES:
        require((report / name).read_bytes() == (out / "verified-report" / name).read_bytes(),
                "report differs from authoritative ledger re-export: " + name)
    return read(out / "verified-report/report.json")


def verify_accounting(dataset, report):
    """Independent identities, no simulated execution or alternate money ledger."""
    require("cash_dividends" not in dataset and report.get("ledger_schema", 3) == 3,
            "CASH_DIVIDEND_V1 requires evaluate-cash-dividend protocol")
    require([r["day"] for r in report["daily"]] == [s["day"] for s in dataset["sessions"]], "daily coverage mismatch")
    require(report["external_flow_total_fen"] == 0, "external flows not supported by this protocol")
    cash, held, fees = report["initial_nav_fen"], 0, 0
    ids = set()
    for s, row in zip(dataset["sessions"], report["daily"]):
        for f in (f for f in report["fills"] if f["day"] == s["day"]):
            require(f["event_id"] not in ids, "duplicate fill")
            ids.add(f["event_id"])
            require(f["side"] in ("Buy", "Sell") and f["quantity"] > 0, "invalid fill")
            charge = sum(f["fees"].values())
            signed = f["quantity"] if f["side"] == "Buy" else -f["quantity"]
            cash -= signed*f["price"] + charge
            held += signed
            fees += charge
        require(cash >= 0 and held >= 0 and row["cash_fen"] == cash and row["held_shares"] == held,
                "cash/position conservation failed")
        require(row["cumulative_fee_fen"] == fees and row["external_flow_total_fen"] == 0, "fee/flow mismatch")
        if row["nav_fen"] is not None:
            require(s["status_verified"] and not row["valuation_error"], "untrusted valuation labelled valid")
            require(row["nav_fen"] == cash+held*s["close_fen"], "NAV identity failed")
            require(row["realized_pnl_fen"] is not None and row["unrealized_pnl_fen"] is not None and
                    row["nav_fen"]-report["initial_nav_fen"] == row["realized_pnl_fen"]+row["unrealized_pnl_fen"],
                    "P&L identity failed")
        else:
            require(bool(row["valuation_error"]), "missing NAV must have a reason")
    require(fees == report["total_fee_fen"] and cash == report["ending_cash_fen"] and
            held == report["ending_held_shares"] and len(ids) == len(report["fills"]), "ending totals mismatch")


def ratio(numerator, denominator):
    if denominator is None or denominator <= 0 or numerator is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 32
        return format((Decimal(numerator)/Decimal(denominator)).quantize(Decimal("0.000000000001")), "f")


def drawdown(initial, values):
    if initial is None or initial <= 0 or any(v is None for v in values):
        return None
    peak, worst = initial, Decimal(0)
    for nav in values:
        peak = max(peak, nav)
        worst = max(worst, Decimal(peak-nav)/Decimal(peak))
    return format(worst.quantize(Decimal("0.000000000001")), "f")


def window_metrics(report, start, end):
    rows = report["daily"][start:end]
    first, last = rows[0], rows[-1]
    previous = report["daily"][start-1] if start else None
    initial = previous["nav_fen"] if previous else report["initial_nav_fen"]
    fills = [f for f in report["fills"] if first["day"] <= f["day"] <= last["day"]]
    orders = [o for o in report["orders"] if first["day"] <= o["accepted_on"] <= last["day"]]
    complete = initial is not None and all(r["nav_fen"] is not None for r in rows)
    missing = sum(r["nav_fen"] is None for r in rows)
    # Count only rounds with both legs inside the window; carried shares are not
    # re-created at the split. Fixed engine currently has 100-share full fills.
    lots, rounds = [], 0
    for fill in fills:
        if fill["side"] == "Buy":
            lots.append(fill["quantity"])
        else:
            remaining = fill["quantity"]
            while lots and remaining:
                take = min(lots[0], remaining)
                lots[0] -= take
                remaining -= take
                if not lots[0]:
                    lots.pop(0)
                    rounds += 1
    end_nav = last["nav_fen"]
    net = end_nav-initial if complete else None
    fee = sum(sum(f["fees"].values()) for f in fills)
    stress = []
    for extra in (500, 1000):
        drag = len(fills)*extra
        stress.append(dict(kind="posthoc_cost_bound", extra_fen_per_fill=extra,
                           extra_fee_fen=drag, hypothetical_net_pnl_fen=net-drag if net is not None else None,
                           hypothetical_return=ratio(net-drag, initial) if net is not None else None,
                           note="fixed realized fills only; no re-matching/risk/reservation/position changes"))
    unavailable = dict(value=None, reason="descriptive protocol; historical/short/dependent sample, no inferential claim")
    return dict(first_day=first["day"], last_day=last["day"], start_index=start, end_index=end,
                days=len(rows), valid_nav_days=len(rows)-missing, missing_nav_days=missing,
                initial_nav_fen=initial, ending_nav_fen=end_nav, initial_cash_fen=previous["cash_fen"] if previous else initial,
                ending_cash_fen=last["cash_fen"], carried_shares=previous["held_shares"] if previous else 0,
                carried_pending_orders=previous["pending_orders"] if previous else 0,
                ending_shares=last["held_shares"], ending_pending_orders=last["pending_orders"],
                proposals=len(orders), fills=len(fills), risk_rejections=sum(o["status"] == "Rejected" for o in orders),
                accepted_proposals=sum(o["status"] != "Rejected" for o in orders),
                completed_round_trips=rounds, model_fee_fen=fee, net_pnl_fen=net,
                net_return=ratio(net, initial), excess_vs_cash_return=ratio(net, initial),
                model_fee_return_drag=ratio(fee, initial),
                max_drawdown=drawdown(initial, [r["nav_fen"] for r in rows]),
                holding_close_observations=sum(r["held_shares"] > 0 for r in rows),
                flat_close_fraction=ratio(sum(r["held_shares"] == 0 for r in rows), len(rows)),
                fills_per_session=ratio(len(fills), len(rows)),
                valuation_reason=None if complete else "missing trusted daily or boundary NAV; no zero fill or skipped gap",
                cash_benchmark=dict(initial_nav_fen=initial, ending_nav_fen=initial,
                                    net_return="0.000000000000" if initial is not None else None),
                posthoc_cost_bounds=stress, sharpe=unavailable, annualized_return=unavailable,
                win_rate=unavailable, significance=unavailable)


def benchmark(exe, dataset, input_sha, window, out):
    principal = window["initial_nav_fen"]
    if principal is None or not 0 < principal <= CAPITAL[0]:
        return dict(status="NOT_EVALUATED", reason="boundary NAV missing/invalid or exceeds authorized research principal")
    args = [str(v) for pair in zip(FLAGS, (principal, *CAPITAL[1:])) for v in pair]
    cli(exe, "paper-benchmark", dataset, out, "--sha256", input_sha,
        "--start-index", window["start_index"], "--end-index", window["end_index"], *args)
    b = read(out / "benchmark.json")
    require(b["input_sha256"] == input_sha and b["initial_nav_fen"] == principal, "benchmark identity mismatch")
    # Direct identity against the original input closes, independent of SMA entry.
    sessions = read(dataset)["sessions"][window["start_index"]:window["end_index"]]
    for s, row in zip(sessions, b["daily"]):
        if row["nav_fen"] is not None:
            require(row["nav_fen"] == row["cash_fen"]+row["held_shares"]*s["close_fen"], "benchmark NAV identity")
    last = b["daily"][-1]["nav_fen"]
    available = b["status"] == "EVALUATED" and all(r["nav_fen"] is not None for r in b["daily"])
    ret = ratio(last-principal, principal) if available else None
    strategy_return = window["net_return"]
    return dict(status=b["status"] if available else "NOT_EVALUATED", reason=b["reason"] if available else
                (b["reason"] or "missing valuation"), version=b["benchmark_version"],
                initial_nav_fen=principal, ending_nav_fen=last if available else None,
                net_return=ret, max_drawdown=drawdown(principal, [r["nav_fen"] for r in b["daily"]]) if available else None,
                model_fee_fen=sum(sum(f["fees"].values()) for f in b["fills"]),
                entry_day=b["fills"][0]["day"] if b["fills"] else None,
                ending_shares=b["daily"][-1]["held_shares"], ending_pending_orders=b["daily"][-1]["pending_orders"],
                excess_net_return=str(Decimal(strategy_return)-Decimal(ret)) if ret is not None and strategy_return is not None else None,
                ledger_head=b["ledger_head"], report_sha256=sha(out / "benchmark.json"),
                note="independent fixed100 first-close/next-open entry; includes residual cash; no terminal sale, not risk-matched alpha")


def evaluate(a, out):
    dataset, split, quality = read(a.input), read(a.split), read(a.audit)
    input_sha = sha(a.input)
    expected = split_for(dataset)
    expected["input_sha256"] = input_sha
    require(split == expected, "split/protocol changed after freeze or not the fixed chronological 70/30 rule")
    require(quality["input_sha256"] == input_sha and quality["protocol_sha256"] == sha(PROTOCOL_FILE), "audit binding mismatch")
    require(quality["selected_window"] == "COMPLETE", "selected data quality is BLOCKED")
    for key, value in quality["raw_sha256"].items():
        require(sha(a.source_dir / f"{key}.json") == value, "raw frozen source changed")
    with contextlib.redirect_stdout(io.StringIO()):
        adapter.prepare(a.source_dir, out / "verified-input", quality["selected_start"], quality["selected_end"])
    require(a.input.read_bytes() == (out / "verified-input/dataset.json").read_bytes(), "input cannot be reproduced from frozen raw")
    report = verify_reports(a.exe, a.input, a.ledger, a.report, out)
    require(report["input_sha256"] == input_sha and report["strategy_version"] == "sma5-20-cross-fixed100-v1"
            and report["execution_model"] == "next-open-adverse-tick-100-v1", "strategy/model identity mismatch")
    config = report["config"]
    require((config["initial_capital"], config["account_limits"]["max_order_commitment"],
             config["account_limits"]["max_exposure"], config["strategy_limits"]["max_exposure"],
             config["account_limits"]["daily_loss"], config["account_limits"]["drawdown"]) == CAPITAL,
            "capital/risk configuration differs from frozen protocol")
    verify_accounting(dataset, report)
    n, k = len(report["daily"]), split["development_count"]
    require(n >= 2 and 0 < k < n, "INSUFFICIENT_EVIDENCE: not enough days for a split")
    windows = {}
    for name, start, end in (("full", 0, n), ("development", 0, k), ("holdout", k, n)):
        window = window_metrics(report, start, end)
        window["data_gap_days"] = quality["selected_missing_days"]
        window["buy_hold_benchmark"] = benchmark(a.exe, a.input, input_sha, window, out / ("benchmark-"+name))
        windows[name] = window
    insufficient = []
    if n < 504:
        insufficient.append("full window fewer than 504 sessions")
    if n-k < 126:
        insufficient.append("holdout fewer than 126 sessions")
    if windows["holdout"]["completed_round_trips"] < 20:
        insufficient.append("holdout fewer than 20 complete in-window round trips")
    if any(r["nav_fen"] is None for r in report["daily"]):
        insufficient.append("missing trusted NAV")
    result = dict(evaluation_schema=1, protocol=split, input_sha256=input_sha,
                  strategy_version=report["strategy_version"], execution_model=report["execution_model"],
                  fee_assumption=report["fee_assumption"], config=report["config"],
                  slippage_assumption=dict(adverse_fen_per_share=1, fixed_capacity_shares_per_session=100,
                                           kind="historical_ex_post_execution_assumption_not_market_capacity_evidence"),
                  ledger_head=report["ledger_head"], reports_sha256={name: sha(a.report / name) for name in NAMES},
                  data_coverage=dict(target=quality["data_coverage"], selected_window=quality["selected_window"],
                                     selected_sessions=n, missing_days=quality["selected_missing_days"],
                                     target_blockers=quality["target_blockers"]),
                  research_evidence="INSUFFICIENT_EVIDENCE" if insufficient else "DESCRIPTIVE_ONLY",
                  insufficient_reasons=insufficient, engineering="PASS_SELF_TEST_NOT_INDEPENDENT_ACCEPTANCE",
                  independent_acceptance="NOT_VERIFIED", windows=windows,
                  source_type=quality["source_type"], raw_sha256=quality["raw_sha256"],
                  limitations=["extraction time is not historical PIT; revisions unavailable",
                               "retrospective previously exposed historical holdout; not prospective OOS",
                               "no corporate action accounting; unsupported history is DATA_BLOCKED",
                               "benchmark is an isolated hypothetical comparison, not simultaneous extra capital",
                               "posthoc_cost_bound is not scenario_backtest or new risk simulation",
                               "paper-only, no statistical edge, live qualification or M1 completion claim"])
    write(out / "evaluation.json", result)
    columns = ("window", "first_day", "last_day", "days", "valid_nav_days", "proposals", "fills", "risk_rejections",
               "initial_nav_fen", "ending_nav_fen", "ending_cash_fen", "ending_shares", "ending_pending_orders",
               "net_return", "max_drawdown", "model_fee_fen", "buy_hold_net_return", "excess_net_return")
    with (out / "evaluation.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for name, window in windows.items():
            row = {key: window.get(key) for key in columns}
            row.update(window=name, buy_hold_net_return=window["buy_hold_benchmark"].get("net_return"),
                       excess_net_return=window["buy_hold_benchmark"].get("excess_net_return"))
            writer.writerow(row)
    return result


def evaluate_synthetic(a, out):
    """Engineering-only adapter for the already-trusted, byte-fixed v1 fixture.

    No new strategy, fill, money or research-qualification logic is introduced.
    The historical SMA gate is intentionally NOT relaxed to admit fake history.
    """
    require(a.input.read_bytes() == (ROOT / "samples/m0-pr03-synthetic.json").read_bytes(),
            "synthetic evaluation accepts only the existing repository fixture")
    dataset = read(a.input)
    report = verify_reports(a.exe, a.input, a.ledger, a.report, out)
    require(report["input_sha256"] == sha(a.input)
            and report["strategy_version"] == "first-buy-second-sell-third-risk-probe-v1"
            and dataset["mode"] == "synthetic_test", "synthetic identity mismatch")
    config = report["config"]
    require((config["initial_capital"], config["account_limits"]["max_order_commitment"],
             config["account_limits"]["max_exposure"], config["strategy_limits"]["max_exposure"],
             config["account_limits"]["daily_loss"], config["account_limits"]["drawdown"]) == CAPITAL,
            "synthetic configuration differs from the fixed protocol")
    verify_accounting(dataset, report)
    result = dict(evaluation_schema=1, input_sha256=sha(a.input), strategy_version=report["strategy_version"],
                  research_evidence="SYNTHETIC_TEST_ONLY", engineering="PASS_SELF_TEST_NOT_INDEPENDENT_ACCEPTANCE",
                  independent_acceptance="NOT_VERIFIED", data_coverage="NOT_MARKET_DATA",
                  insufficient_reasons=["artificial fixture is engineering evidence only"],
                  windows=dict(full=window_metrics(report, 0, len(report["daily"]))),
                  ledger_head=report["ledger_head"], reports_sha256={name: sha(a.report / name) for name in NAMES},
                  fee_assumption=dataset["fee"],
                  limitations=["synthetic_test; no market observations, SMA qualification or forward evidence",
                               "cash benchmark is a calculation; no historical holdout or buy-hold research claim"])
    write(out / "evaluation.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    audit_parser = commands.add_parser("audit")
    audit_parser.add_argument("--source-dir", type=Path, required=True)
    audit_parser.add_argument("--out", type=Path, required=True)
    evaluate_parser = commands.add_parser("evaluate")
    for flag in ("input", "split", "audit", "source-dir", "ledger", "report", "exe", "out"):
        evaluate_parser.add_argument("--"+flag, type=Path, required=True)
    synthetic_parser = commands.add_parser("evaluate-synthetic")
    for flag in ("input", "ledger", "report", "exe", "out"):
        synthetic_parser.add_argument("--"+flag, type=Path, required=True)
    dividend_parser = commands.add_parser("evaluate-cash-dividend")
    for flag in ("input", "source", "ledger", "report", "exe", "out"):
        dividend_parser.add_argument("--"+flag, type=Path, required=True)
    dividend_audit = commands.add_parser("audit-cash-dividend-source")
    for flag in ("evidence", "out"):
        dividend_audit.add_argument("--"+flag, type=Path, required=True)
    args = parser.parse_args()
    out = new_output(args.out)
    if args.action in ("evaluate-cash-dividend", "audit-cash-dividend-source"):
        spec = importlib.util.spec_from_file_location("dividend", Path(__file__).with_name("cash-dividend-evaluate.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.evaluate(args, out) if args.action == "evaluate-cash-dividend" else module.audit_real_source(args.evidence, out)
    elif args.action == "audit":
        result = audit(args.source_dir, out)
    elif args.action == "evaluate-synthetic":
        result = evaluate_synthetic(args, out)
    else:
        result = evaluate(args, out)
    # No raw rows, full report/events or credentials printed.
    print(json.dumps({k: result[k] for k in ("data_coverage", "research_evidence", "engineering") if k in result}))
    if args.action == "audit-cash-dividend-source":
        print("BLOCKED: real event not eligible; source comparison only")
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        print("BLOCKED research evaluation: " + str(error), file=sys.stderr)
        sys.exit(2)
