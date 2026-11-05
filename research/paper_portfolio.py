"""Trusted #84 runner: read original market/Agent records, drive one Rust Ledger.

No provider request, paid call, model weight, or financial database lives here.
The binding is only a local path; Owner policy and all financial facts are in
the existing paper ledger. Incomplete corporate-action sources yield NO_FILL.
"""
import argparse
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path
import subprocess

import market_eod as m
import market_research as mr

ROOT = Path(__file__).resolve().parents[1]


def binding_path():
    return m.common_root() / "state/paper-portfolio/binding.json"


def bridge(ledger, action, value=None):
    exe = ROOT / "target/debug" / ("stratide-cli.exe" if os.name == "nt" else "stratide-cli")
    result = subprocess.run([str(exe), "paper-portfolio", str(ledger), action],
                            input=m.canonical(value or {}), capture_output=True, timeout=60)
    m.require(result.returncode == 0, "PAPER_LEDGER_COMMAND_REJECTED")
    return json.loads(result.stdout)


def milliseconds(value):
    return int(m.instant(value).timestamp() * 1000)


def instrument(code):
    m.require(len(code) == 9 and code[6:] in (".SH", ".SZ", ".BJ") and code[:6].isdigit(), "PAPER_SECURITY_IDENTITY")
    return dict(market={".SH": "Shanghai", ".SZ": "Shenzhen", ".BJ": "Beijing"}[code[6:]], code=code[:6])


def code(i):
    return i["code"] + {"Shanghai": ".SH", "Shenzhen": ".SZ", "Beijing": ".BJ"}[i["market"]]


def fen(value):
    n = Decimal(str(value)) * 100
    m.require(n.is_finite() and n >= 0 and n == n.to_integral_value(), "PAPER_PRICE_PRECISION")
    return int(n)


def factors(parts):
    # Exact, normalized source decimals; never infer actions_verified from this.
    result = {}
    for row in parts.get("adj_factor", []):
        value = Decimal(row["adj_factor"])
        m.require(value.is_finite() and value > 0, "PAPER_ADJUSTMENT_FACTOR_INVALID")
        result[row["ts_code"]] = format(value.normalize(), "f")
    return result


def load_day(market, day):
    with market.read(inspect_raw_paths=False) as db:
        snapshot = market.load_snapshot(db, day)
        m.require(snapshot is not None, "PAPER_MARKET_SNAPSHOT_MISSING")
        parts = {}
        calendar, refs = {}, []
        for ref in snapshot["sources"]:
            if ref["status"] not in m.GOOD:
                continue
            rows = market.response(db, ref["id"])["rows"]
            if ref["api"] == "trade_cal":
                refs.append(ref)
                for r in rows:
                    calendar.setdefault(r["cal_date"], {})[r["exchange"]] = r["is_open"] == "1"
            elif ref["api"] in ("daily", "adj_factor", "suspend_d"):
                parts.setdefault(ref["api"], {}).update({m.canonical(r).decode(): r for r in rows})
        return snapshot, {api: list(rows.values()) for api, rows in parts.items()}, calendar, refs


def rule(security, row, day, at):
    i = instrument(security["ts_code"])
    # Only an explicit ordinary main-board hypothesis is implemented. Catalog
    # names do not certify complete historical ST identity or corporate actions.
    ordinary = ((i["market"] == "Shanghai" and i["code"].startswith("60")) or
                (i["market"] == "Shenzhen" and i["code"].startswith("00")))
    supported = (ordinary and security["category"] == "QUOTED" and security["list_status"] == "L"
                 and "ST" not in security["name"].upper() and "退" not in security["name"]
                 and (m.h.day(day) - m.h.day(security["list_date"])).days >= 180 and row is not None)
    pre = Decimal(row["pre_close"]) if row else Decimal(0)
    low = int((pre * 90).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    high = int((pre * 110).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return supported, dict(instrument=i, trading_day=int(day), available_at=at,
        source="ordinary-mainboard-10pct-paper-hypothesis-v1 / " + security["rule_source"],
        tradable=supported, settlement="TPlusOne", buy_lot=100, sell_lot=100,
        allow_odd_lot_liquidation=True, tick_size=1, min_price=low, max_price=high)


def research(market, day, snapshot):
    with mr.database() as db:
        run = mr.get(db, mr.RUN + day)
    m.require(run is not None and run["state"] == "CANDIDATE_FROZEN", "RESEARCH_NOT_READY_84_SESSIONS_REQUIRED")
    task = mr.bridge("task", dict(task_id=run["fusion_task_id"]))
    m.require(task["status"] == "completed" and task["input"]["mode"] == "historical_research_only"
              and task["result"]["synthetic_provider"] is False, "REAL_ORIGINAL_MARKET_RESEARCH_REQUIRED")
    registration = mr.c.Registry("market-" + day).registration(run["registration_sha256"])
    material = registration["material"]
    screen = run["screen"]
    m.require(material["saved_agent_task"] == task and material["authority"] == "research_only"
              and material["snapshot_provenance"]["can_execute_forward_paper"] is False
              and screen["snapshot_sha256"] == snapshot["snapshot_sha256"]
              and screen["rules_sha256"] == mr.rp.digest(mr.RULES)
              and screen["implementation_sha256"] == mr.j.sha(Path(mr.__file__).read_bytes())
              and run["screen_sha256"] == mr.rp.digest(screen)
              and len(screen["context_snapshots"]) == 84
              and run["candidate_sha256"] == mr.rp.digest(task["result"]["research"]["risk_portfolio"]["portfolio"]),
              "ORIGINAL_RESEARCH_REGISTRY_OR_SOURCE_CHANGED")
    days, snapshots, sources = mr.prefix(market, day, run["as_of"])
    expected_screen = mr.screen(days, snapshots, sources, run["as_of"], run["config"]["candidate_count"])
    m.require(expected_screen == screen and milliseconds(registration["registered_at"]) <= milliseconds(m.h.now()),
              "RESEARCH_SCREEN_OR_REGISTRATION_TIME_CHANGED")
    # The model's text and proposed weights are intentionally never projected.
    return dict(task_id=str(task["id"]), candidate_sha256=run["candidate_sha256"],
        registration_sha256=run["registration_sha256"],
        model_version=task["result"]["research"]["risk_portfolio"]["receipt"]["model_version"],
        generated_at=milliseconds(task["result"]["generated_at"]), finished_at=milliseconds(task["finished_at"]),
        ready_sessions=84, restriction="RESEARCH_ONLY", eligibility="ELIGIBILITY_DENIED",
        can_execute_forward_paper=False, selected=[instrument(s["instrument"]) for s in screen["selected"]])


def decision(snapshot, parts, calendar, refs, r, now):
    day = snapshot["source_day"]
    at = milliseconds(snapshot["available_at"])
    prices = {p["ts_code"]: p for p in parts.get("daily", [])}
    adjustments = factors(parts)
    securities, marks = [], []
    for s in snapshot["securities"]:
        row = prices.get(s["ts_code"])
        supported, rules = rule(s, row, day, at)
        close = fen(row["close"]) if row else 0
        securities.append(dict(instrument=instrument(s["ts_code"]), close=close, rules=rules, supported=supported,
            amount_thousand_yuan=int(Decimal(row["amount"])) if row else 0, reason=s["category"], adjustment_factor=adjustments.get(s["ts_code"])))
        if row:
            marks.append(dict(instrument=instrument(s["ts_code"]), price=close, as_of=at, available_at=at,
                              source=snapshot["snapshot_sha256"]))
    dates = []
    for date, exchanges in sorted(calendar.items()):
        if date < day:
            continue
        m.require(set(exchanges) == {"SSE", "SZSE"}, "PAPER_CALENDAR_EXCHANGE_MISSING")
        dates.append(dict(day=int(date), sse_open=exchanges["SSE"], szse_open=exchanges["SZSE"]))
        if date > day and exchanges["SSE"] and exchanges["SZSE"]:
            break
    return dict(now=now, day=int(day), source_sha256=snapshot["snapshot_sha256"], received_at=at,
        calendar_sha256=m.sha(m.canonical(refs)), calendar_received_at=max((milliseconds(x["available_at"]) for x in refs), default=now),
        calendar=dates, research=r, securities=securities, marks=marks,
        source_ready=snapshot["state"] == "READY" and not snapshot["late_backfill"], reason=",".join(snapshot["blockers"]))


def confirmation(state, snapshot, parts, now):
    day = snapshot["source_day"]
    at = milliseconds(snapshot["available_at"])
    prices = {p["ts_code"]: p for p in parts.get("daily", [])}
    adjustments = factors(parts)
    quotes = []
    wanted = {code(l["instrument"]) for l in state["snapshot"]["positions"]} | {code(o["instrument"]) for o in state["snapshot"]["pending_orders"]}
    for s in snapshot["securities"]:
        if s["ts_code"] not in wanted:
            continue
        row = prices.get(s["ts_code"])
        if row is None:
            continue
        supported, rules = rule(s, row, day, at)
        quotes.append(dict(bar=dict(provenance=state["provenance"], instrument=instrument(s["ts_code"]), day=int(day),
            opens_at=milliseconds(m.h.day(day).isoformat()+"T09:30:00+08:00"),
            closes_at=milliseconds(m.h.day(day).isoformat()+"T15:00:00+08:00"), available_at=at,
            open=fen(row["open"]), high=fen(row["high"]), low=fen(row["low"]), close=fen(row["close"]),
            volume_shares=int(Decimal(row["vol"])*100), capacity_shares=state["portfolio"]["policy"]["capacity_shares"],
            status_verified=supported), rules=rules, corporate_actions_verified=False,
            reason="CORPORATE_ACTIONS_UNVERIFIED / EX_POST_PAPER_ASSUMPTION",
            paper_assumption=dict(pre_close=fen(row["pre_close"]),adjustment_factor=adjustments[s["ts_code"]]) if s["ts_code"] in adjustments else None))
    return dict(now=now, day=int(day), source_sha256=snapshot["snapshot_sha256"], received_at=at, quotes=quotes)


def once(market, phase="all"):
    path = binding_path()
    if not path.is_file():
        return dict(state="NOT_CONFIGURED")
    b = json.loads(path.read_text(encoding="utf-8"))
    ledger = Path(b["ledger"])
    # Serialize cooperating runners through the existing OS lock primitive.
    with mr.d.writer(path.parent / "runner.lock"):
        view = bridge(ledger, "status")
        state, book = view["state"], view["state"].get("portfolio")
        m.require(book is not None, "OWNER_PORTFOLIO_POLICY_REQUIRED")
        now = milliseconds(m.h.now())
        today = dt.datetime.fromtimestamp(now/1000, m.TZ).strftime("%Y%m%d")
        if book["pending"] is not None and phase in ("all", "confirm"):
            batch = book["batches"][book["pending"]]
            target = str(batch["target_day"])
            end = milliseconds(m.h.day(target).isoformat()+"T18:00:00+08:00")
            if now >= end:
                bridge(ledger, "confirm", dict(now=now, day=int(target), source_sha256=m.sha(b"NO_SOURCE_EXPIRED"), received_at=now, quotes=[]))
            elif today == target and now >= milliseconds(m.h.day(target).isoformat()+"T16:00:00+08:00"):
                try:
                    snapshot, parts, _, _ = load_day(market, target)
                except m.Error as error:
                    return dict(state="WAITING_FOR_EOD_OR_DEADLINE", reason=str(error))
                bridge(ledger, "confirm", confirmation(state, snapshot, parts, now))
            else:
                return dict(state="WAITING_FOR_TARGET_EOD", target_day=target)
            view = bridge(ledger, "status")
            state, book = view["state"], view["state"]["portfolio"]
        if book["pending"] is None and state["valuation_error"] is not None and int(today) > state["snapshot"]["trading_day"]:
            snapshot, parts, _, _ = load_day(market, today)
            bridge(ledger, "recover", confirmation(state, snapshot, parts, now))
            view = bridge(ledger, "status")
            state, book = view["state"], view["state"]["portfolio"]
        if phase == "confirm":
            return dict(state="CONFIRMATION_CHECKED", ledger_head=view["ledger_head"])
        if not book["automatic"]:
            return dict(state="OWNER_PAUSED")
        if any(x["decision"]["day"] == int(today) for x in book["batches"]):
            return dict(state="ALREADY_FROZEN", ledger_head=view["ledger_head"])
        snapshot, parts, calendar, refs = load_day(market, today)
        m.require(snapshot["data_mode"] == "tushare_incremental_eod", "REAL_MARKET_SOURCE_REQUIRED")
        r = research(market, today, snapshot)
        wanted = {code(i) for i in r["selected"]} | {code(l["instrument"]) for l in state["snapshot"]["positions"]}
        projected = dict(snapshot, securities=[s for s in snapshot["securities"] if s["ts_code"] in wanted])
        value = decision(projected, parts, calendar, refs, r, now)
        bridge(ledger, "freeze", value)
        return dict(state="PAPER_HYPOTHESIS_FROZEN", opening_observed="NOT_VERIFIED", live_allowed=False)


def optional_step(market, phase):
    # Independent operational failure boundary, after durable collection. Never
    # infer that an uncertain ledger commit failed; next poll reads it first.
    try:
        return once(market, phase)
    except Exception:
        return dict(state="BLOCKED", reason="PAPER_LOCAL_INPUT_OR_LEDGER_UNAVAILABLE")


def main(argv=None):
    parser = argparse.ArgumentParser(description="多证券共享 Paper；Owner 本机配置，不接 Broker")
    parser.add_argument("action", choices=("bind", "configure", "status", "once", "pause", "resume"))
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    try:
        path = binding_path()
        if args.action == "bind":
            m.require(args.ledger is not None, "EXISTING_LEDGER_REQUIRED")
            ledger = args.ledger.resolve(strict=True)
            bridge(ledger, "status")
            path.parent.mkdir(parents=True, exist_ok=True)
            mr.c.write(path, dict(ledger=str(ledger)))
            result = dict(state="BOUND_EXISTING_LEDGER")
        elif args.action == "once":
            result = once(m.Market(m.default_root()))
        else:
            ledger = json.loads(path.read_text(encoding="utf-8"))["ledger"]
            if args.action == "configure":
                m.require(args.input is not None, "OWNER_POLICY_INPUT_REQUIRED")
            value = json.loads(args.input.read_text(encoding="utf-8")) if args.action == "configure" else None
            result = bridge(ledger, args.action, value)
        print(json.dumps(result, ensure_ascii=False))
    except (m.Error, OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps(dict(state="BLOCKED", reason="PAPER_LOCAL_INPUT_OR_LEDGER_UNAVAILABLE")))
        return 1
    return 0
