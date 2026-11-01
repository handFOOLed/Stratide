"""Independent CASH_DIVIDEND_V1 accounting protocol, stdlib only, no qualification.

Reads frozen source/event/prices and confirmed modeled fills, never the Rust
state NAV as an input. SQLite backup + CLI re-export verifies the entire chain.
All new artifacts are isolated; the supplied ledger/reports are read-only.
"""
import argparse
import csv
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

PROTOCOL = "cash-dividend-independent-accounting-v1"
NAMES = ("report.json", "events.json", "daily.csv", "orders.csv", "fills.csv",
         "positions.csv", "cash-dividends.json")
FLAGS = ("--initial-cash-fen", "--max-order-fen", "--account-cap-fen",
         "--strategy-cap-fen", "--daily-loss-fen", "--drawdown-fen")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def cli(exe, *args):
    p = subprocess.run([str(exe.resolve()), *map(str, args)], capture_output=True, timeout=120)
    require(p.returncode == 0, "CLI failed: " + p.stderr.decode("utf-8", errors="replace"))


def journal(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        require(db.execute("pragma user_version").fetchone()[0] == 4, "expected explicit v4 ledger")
        rows = db.execute("select seq,event_id,payload,digest from events order by seq").fetchall()
        require(db.execute("select seq,digest from checkpoint where id=1").fetchone() ==
                (rows[-1][0], rows[-1][3]), "checkpoint differs")
    return rows


def charge(amount, ppm):
    # Decimal quantization, deliberately independent of Rust's integer ceiling.
    return int((Decimal(amount) * Decimal(ppm) / Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING))


def source_check(dataset, source):
    require(dataset["schema_version"] == 3 and dataset["mode"] == "synthetic_test", "synthetic schema3 required")
    raw = read(source)
    require(raw["schema"] == "synthetic_cash_dividend_source_v1" and
            raw["evidence_basis"] == "synthetic_assumption", "real/unknown source rejected")
    for e in dataset["cash_dividends"]:
        require(e["source_sha256"] == sha(source), "event source SHA differs")
        require(e["schema"] == "CASH_DIVIDEND_V1" and e["mode"] == "synthetic_test"
                and e["fact_status"] == "SYNTHETIC_MODEL"
                and e["evidence_basis"] == "synthetic_assumption"
                and e["historical_pit"] == "NOT_VERIFIED" and e["real_account_eligible"] is False,
                "event cannot claim real or PIT qualification")
        require(e["tax"]["basis"] == "synthetic_assumption" and e["tax"]["version"] and
                e["tax"]["rounding"] == "ceil_per_event_fen_v1", "tax unknown")
        for key in ("currency", "cash_amount_fen", "cash_unit", "record_day", "ex_day", "payment_day"):
            require(e[key] == raw[key], "source fact differs: " + key)
        require(e["tax"]["withholding_ppm"] == raw["tax_withholding_ppm"] and
                e["tax"]["identity"] == raw["tax_identity"], "tax identity differs")


def verify(dataset, rows, report):
    """Pure cross-check: frozen events + trusted input prices + fill list only."""
    g = json.loads(rows[0][2])
    config = g["genesis"]["config"]
    require(report["report_schema"] == 2 and report["ledger_schema"] == 4 and
            report["cash_dividend_protocol"] == "CASH_DIVIDEND_V1", "wrong report protocol")
    require(g["cash_dividends"] == dataset["cash_dividends"], "genesis events differ from frozen input")
    initial = config["initial_capital"]
    cash, held, fees, realized = initial, 0, 0, 0
    lots, fill_ids = [], set()
    events = {e["event_id"]: e for e in g["cash_dividends"]}
    require(len(events) == len(g["cash_dividends"]), "event ID/version conflict")
    phases = {key: 0 for key in events}
    entitlement, gross, tax = {}, {}, {}
    sessions = {s["day"]: s for s in dataset["sessions"]}
    require(len(rows) == len(report["events"]) + 1, "missing audit events")
    require(report["external_flow_total_fen"] == 0, "dividend is not Owner flow")
    mark, previous_nav, day_start, peak = 0, initial, initial, initial
    day = g["genesis"]["day"]
    freezes = {"account_freezes": set(), "strategy_freezes": set()}
    by_day, actions, all_fills = {}, [], []

    def totals():
        return dict(receivable_fen=sum(gross[k] for k in gross if phases[k] == 2),
                    liability_fen=sum(tax[k] for k in tax if phases[k] == 2),
                    gross_income_fen=sum(gross.values()), tax_expense_fen=sum(tax.values()),
                    cash_paid_fen=sum(gross[k]-tax[k] for k in gross if phases[k] == 3))

    def nav():
        t = totals()
        return cash + held*mark + t["receivable_fen"] - t["liability_fen"]

    def observe():
        nonlocal peak, previous_nav
        value = nav()
        require(value >= 0, "negative net assets")
        peak = max(peak, value)
        for scope, limits in (("account_freezes", config["account_limits"]),
                              ("strategy_freezes", config["strategy_limits"])):
            if day_start - value >= limits["daily_loss"]:
                freezes[scope].add("DailyLoss")
            if peak - value >= limits["drawdown"]:
                freezes[scope].add("Drawdown")
        previous_nav = value

    for expected_seq, ((seq, event_id, payload, digest), audit) in enumerate(zip(rows[1:], report["events"]), 1):
        require(seq == expected_seq and audit["seq"] == seq and audit["event_id"] == event_id and
                audit["ledger_digest"] == digest and audit["command"] == json.loads(payload), "audit/journal mismatch")
        kind, cmd = next(iter(json.loads(payload).items()))
        next_day = cmd.get("day", day)
        if next_day > day:
            day_start, day = previous_nav, next_day
        require(next_day == day, "backdated command")
        require(kind in ("Match", "Submit", "CashDividendV1"), "unsupported financial command")
        s = sessions[day]
        if kind == "CashDividendV1":
            key, phase = cmd["event_id"], cmd["phase"]
            e = events[key]
            step = ("record", "ex", "payment").index(phase)
            require(phases[key] == step, "duplicate/out-of-order corporate action")
            require(cmd["now"] == e[phase+"_at"] and day == e[phase+"_day"], "phase timestamp differs")
            mark = s["close_fen"] if phase == "record" else s["opening"]["price_fen"]
            if phase == "record":
                entitlement[key] = held
            elif phase == "ex":
                divisor = 10 if e["cash_unit"] == "per_ten_shares" else 1
                per_share = Decimal(e["cash_amount_fen"]) / Decimal(divisor)
                require(per_share == per_share.to_integral_value(), "fractional fen rejected")
                gross[key] = int(per_share * Decimal(entitlement[key]))
                tax[key] = charge(gross[key], e["tax"]["withholding_ppm"])
            else:
                cash += gross[key] - tax[key]
            phases[key] += 1
            actions.append((seq, key, phase, entitlement[key]))
        elif kind == "Match":
            mark = s["opening"]["price_fen"]
            observe()  # opening risk must see receivable AND withholding
            for f in audit["new_fills"]:
                require(f["event_id"] not in fill_ids, "duplicate fill")
                fill_ids.add(f["event_id"])
                o = next(o for o in report["orders"] if o["proposal"]["proposal_id"] == f["order_id"])
                p = o["proposal"]
                require(f["day"] == day and f["quantity"] > 0 and f["price"] == p["limit_price"] and
                        p["decision_at"] < s["opens_at"] and p["data_available_at"] < s["opens_at"] and
                        s["closes_at"] < p["expires_at"] and p["side"] == f["side"], "invalid modeled fill/time")
                require(f["evidence"]["provenance"]["dataset_hash"] == report["input_sha256"], "fill input differs")
                q, price = f["quantity"], f["price"]
                amount = q*price
                rate = dataset["fee"]
                expected = dict(commission=max(charge(amount, rate["commission_ppm"]), rate["minimum_commission_fen"]),
                                transfer=charge(amount, rate["transfer_ppm"]),
                                tax=charge(amount, rate["sell_tax_ppm"]) if f["side"] == "Sell" else 0)
                require(f["fees"] == expected, "fill fees differ")
                cost = sum(expected.values())
                fees += cost
                if f["side"] == "Buy":
                    cash -= amount + cost
                    held += q
                    lots.append([q, amount+cost])
                else:
                    require(f["side"] == "Sell" and q <= held, "unowned sale")
                    cash += amount - cost
                    held -= q
                    remaining, basis = q, 0
                    while remaining:
                        require(bool(lots), "FIFO shares missing")
                        take = min(remaining, lots[0][0])
                        taken = lots[0][1]*take//lots[0][0]
                        basis += taken
                        lots[0][0] -= take
                        lots[0][1] -= taken
                        remaining -= take
                        if not lots[0][0]:
                            lots.pop(0)
                    realized += amount-cost-basis
                require(cash >= 0 and held >= 0, "unfunded cash/share accounting")
                all_fills.append(f)
                observe()  # fee loss at execution is not deferred to next day
            mark = s["close_fen"]
        else:
            require(not audit["new_fills"], "submit cannot be a dividend/fill")
        observe()
        require(audit["cash_fen"] == cash and audit["held_shares"] == held and
                audit["cash_dividend"] == totals() and audit["nav_fen"] == nav() and
                audit["valuation_error"] is None, "independent audit asset identity failed")
        require(audit["risk"]["cash_flow_adjusted_peak"] == peak, "risk peak includes fictitious/dividend double profit")
        for scope in freezes:
            require(set(audit["risk"][scope]) == freezes[scope], "risk freeze differs")
        by_day[day] = dict(cash_fen=cash, nav_fen=nav(), held_shares=held,
                           cumulative_fee_fen=fees, external_flow_total_fen=0,
                           realized_pnl_fen=realized, remaining_cost_basis_fen=sum(l[1] for l in lots),
                           unrealized_pnl_fen=held*mark-sum(l[1] for l in lots), cash_dividend=totals())

    require(all(v == 3 for v in phases.values()), "lifecycle incomplete")
    require(all_fills == report["fills"], "fill list differs")
    require([d["day"] for d in report["daily"]] == list(sessions), "daily coverage differs")
    for row in report["daily"]:
        expected = by_day[row["day"]]
        require(all(row[k] == v for k, v in expected.items()), "daily independent accounting differs")
        require(row["nav_fen"]-initial == row["realized_pnl_fen"]+row["unrealized_pnl_fen"]+
                row["cash_dividend"]["gross_income_fen"]-row["cash_dividend"]["tax_expense_fen"], "income/expense identity failed")
        require(row["cash_fen"]-row["reserved_cash_fen"] == row["available_cash_fen"] >= 0,
                "receivable leaked into spendable cash")
    require([(a["ledger_seq"], a["event"]["event_id"], a["phase"], a["entitled_shares"])
             for a in report["cash_dividend_actions"]] == actions, "corporate-action detail differs")
    for a in report["cash_dividend_actions"]:
        key = a["event"]["event_id"]
        require(a["event"] == events[key] and a["gross_fen"] == gross[key] and
                a["tax_fen"] == tax[key] and a["net_fen"] == gross[key]-tax[key], "entitlement/payment amount differs")
    require(report["ending_cash_fen"] == cash and report["ending_nav_fen"] == nav() and
            report["ending_held_shares"] == held and report["total_fee_fen"] == fees and
            report["cash_dividend"] == totals(), "ending asset totals differ")
    return dict(ending_cash_fen=cash, ending_nav_fen=nav(), held_shares=held,
                net_pnl_fen=nav()-initial, trading_fee_fen=fees, **totals())


def verify_files(dataset, ledger, directory):
    report = read(directory / "report.json")
    result = verify(dataset, journal(ledger / "ledger.sqlite"), report)
    require(read(directory / "events.json") == report["events"] and
            read(directory / "cash-dividends.json") == report["cash_dividend_actions"], "detail JSON differs")
    with (directory / "daily.csv").open(encoding="utf-8", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    require(len(csv_rows) == len(report["daily"]), "CSV day count differs")
    for csv_row, row in zip(csv_rows, report["daily"]):
        for key in ("day", "nav_fen", "cash_fen", "held_shares", "available_cash_fen"):
            require(int(csv_row[key]) == row[key], "CSV differs: " + key)
        for col, key in (("receivable_fen", "receivable_fen"), ("liability_fen", "liability_fen"),
                         ("dividend_gross_income_fen", "gross_income_fen"), ("dividend_tax_expense_fen", "tax_expense_fen"),
                         ("dividend_cash_paid_fen", "cash_paid_fen")):
            require(int(csv_row[col]) == row["cash_dividend"][key], "dividend CSV differs")
    return result


def evaluate(args, out):
    dataset = read(args.input)
    source_check(dataset, args.source)
    original = {str(p): sha(p) for p in [args.input, args.source, args.ledger/"ledger.sqlite",
                                       *(args.report/n for n in NAMES)]}
    backup = out / "verified-ledger"
    backup.mkdir()
    with sqlite3.connect((args.ledger/"ledger.sqlite").resolve().as_uri()+"?mode=ro", uri=True) as src:
        with sqlite3.connect(backup/"ledger.sqlite") as dst:
            src.backup(dst)
    cli(args.exe, "paper-dividend-report", args.input, backup, out/"verified-report", "--sha256", sha(args.input))
    for name in NAMES:
        require((out/"verified-report"/name).read_bytes() == (args.report/name).read_bytes(), "report differs: " + name)
    strategy = verify_files(dataset, backup, out/"verified-report")
    r = read(args.report/"report.json")
    c = r["config"]
    capital = (c["initial_capital"], c["account_limits"]["max_order_commitment"], c["account_limits"]["max_exposure"],
               c["strategy_limits"]["max_exposure"], c["account_limits"]["daily_loss"], c["account_limits"]["drawdown"])
    flags = [item for pair in zip(FLAGS, capital) for item in pair]
    cli(args.exe, "paper-dividend-benchmark", args.input, out/"benchmark-ledger", out/"benchmark-report",
        "--sha256", sha(args.input), *flags)
    benchmark = verify_files(dataset, out/"benchmark-ledger", out/"benchmark-report")
    cli(args.exe, "paper-dividend-cash-benchmark", args.input, out/"cash-ledger", out/"cash-report",
        "--sha256", sha(args.input), *flags)
    cash_benchmark = verify_files(dataset, out/"cash-ledger", out/"cash-report")
    require(original == {p: sha(p) for p in original}, "source ledger/reports were modified")
    result = dict(protocol=PROTOCOL, protocol_sha256=sha(Path(__file__)), input_sha256=sha(args.input),
                  source_sha256=sha(args.source), ledger_head=r["ledger_head"], mode="synthetic_test",
                  engineering="PASS", independent_accounting_algorithm="PASS",
                  acceptance="Sol self-test, not independent reviewer acceptance", strategy=strategy,
                  buy_hold_benchmark=benchmark, cash_benchmark=cash_benchmark,
                  research_evidence="INSUFFICIENT_EVIDENCE", historical_pit="NOT_VERIFIED",
                  eligibility="ELIGIBILITY_DENIED", opening_source="BLOCKED", live_trading_allowed=False,
                  original_inputs_unchanged=True, real_supported_history_days_added=0)
    write(out/"evaluation.json", result)
    return result


def audit_real_source(evidence, out):
    """Read the already published PR38 evidence snapshot; do not recertify it."""
    r = read(evidence)
    require(r["evidence_kind"] == "public_document" and r["symbol"] == "600000.SH", "wrong evidence snapshot")
    facts = r["events"][0]["facts"]
    result = dict(protocol=PROTOCOL, evidence_snapshot_sha256=sha(evidence),
                  prior_bundle_sha256=r["bundle_sha256"], facts=facts,
                  event_fact_status=r["event_fact_status"], historical_pit=r["historical_pit_status"],
                  status="BLOCKED", real_event_activation=False,
                  model_accounting_support="CASH_DIVIDEND_V1_IMPLEMENTED_IN_ISOLATION",
                  blockers=["REAL_ACCOUNT_TAX_IDENTITY_UNKNOWN", "REAL_DEFERRED_TAX_NOT_MODELED",
                            "ACTUAL_ACCOUNT_PAYMENT_NOT_VERIFIED", "PIT_NOT_VERIFIED",
                            "REAL_EVENT_VERSION_HISTORY_NOT_VERIFIED", "OPENING_SOURCE_BLOCKED"],
                  historical_replay_eligible=False, eligibility="ELIGIBILITY_DENIED",
                  opening_source="BLOCKED", real_supported_history_days_added=0,
                  note="PR38 snapshot read-only comparison; no new source/PIT authentication and no ledger injection")
    write(out/"source-audit.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "source", "ledger", "report", "exe", "out"):
        p.add_argument("--"+name, type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    require(subprocess.run(["git", "check-ignore", "--quiet", str(args.out.resolve()/"evaluation.json")], cwd=root).returncode == 0,
            "new output must be gitignored")
    args.out.mkdir(parents=True, exist_ok=False)
    print(json.dumps(evaluate(args, args.out), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        print("BLOCKED cash-dividend evaluation: " + str(error), file=sys.stderr)
        sys.exit(2)
