"""Offline ex-post bridge; original sources, old prepares and admission stay closed."""
import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from . import corporate_actions as ca

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "historical_dividend_scenario_v1"
SOURCE_NAMES = ("daily", "calendar", "limits", "suspensions", "extraction")
CAPITAL = (10_000_000, 500_000, 2_000_000, 2_000_000, 100_000, 500_000)
MODEL_FIELDS = ("announcement_at", "record_at", "ex_at", "payment_at", "withholding_ppm",
                "share_change_ratio", "other_actions", "opening", "eod_availability", "rules")
BLOCKERS = ("PIT_NOT_VERIFIED", "TAX_ACCOUNT_UNKNOWN", "PAYMENT_UNKNOWN",
            "REVISION_HISTORY_NOT_VERIFIED", "OPENING_SOURCE_BLOCKED", "REAL_PROVIDER_NOT_VERIFIED")


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT/"scripts"/(name+".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


h = module("historical-data")
v = module("cash-dividend-evaluate")
require, read, sha, write = v.require, v.read, v.sha, v.write


def isolated(out):
    require(subprocess.run(["git", "check-ignore", "--quiet", "--", str(out.resolve()/"dataset.json")],
                           cwd=ROOT).returncode == 0, "OUTPUT_MUST_BE_GITIGNORED")


def ms(value):
    return int(ca.timestamp(value).timestamp()*1000)


def build(source, bundle, assumption_path):
    """Preflight is pure/read-only: no ledger, source mutation, fetch or publication."""
    for path in [*(source/(n+".json") for n in SOURCE_NAMES), bundle/"bundle.json", assumption_path]:
        require(path.is_file(), "SOURCE_MISSING")
    a = read(assumption_path)
    require(a["protocol"] == PROTOCOL and a["version"] and
            a["evidence_class"] == "EXPLORATORY_EX_POST" and
            a["license_scope"] == "Owner-authorized personal noncommercial local research; no redistribution",
            "ASSUMPTION_SCOPE_INVALID")
    kind = a["input_kind"]
    require(kind in ("synthetic_test", "frozen_authorized_history"), "INPUT_KIND_INVALID")
    start, end = a["selected_start"], a["selected_end"]
    require(start == "20260706" and "20260716" <= end <= "20261028", "WINDOW_OUTSIDE_PRECOMMITTED_SCOPE")
    require(a["window_policy"] == "fixed_before_execution_not_selected_by_NAV", "WINDOW_POLICY_REQUIRED")
    if kind == "frozen_authorized_history":
        require(end == "20261028", "REAL_WINDOW_FIXED_BEFORE_RUN")
    m = a["models"]
    require(set(m) == set(MODEL_FIELDS), "MODEL_FIELDS_MISSING_OR_UNSUPPORTED")
    for field in MODEL_FIELDS:
        item = m[field]
        require(item["modeled_only"] is True and item["version"] and item["reason"] and item["sensitivity"]
                and item["as_of_class"] == "EX_POST_MODEL_ONLY", "UNLABELED_MODEL_ASSUMPTION:"+field)
    value = {k: m[k]["value"] for k in m}
    require(value["share_change_ratio"] == "0" and value["other_actions"] == "none_in_selected_window" and
            value["opening"] == "daily_open_ex_post_next_open_adverse_1fen" and
            value["eod_availability"] == "18:00_Asia_Shanghai_assumed_not_received" and
            value["rules"] == "ordinary_SSE_A_TPlusOne_100shares_1fen_ex_post", "UNSUPPORTED_ACTION_OR_CLOCK")
    rate = value["withholding_ppm"]
    require(type(rate) is int and 0 <= rate <= 1_000_000, "TAX_MODEL_OUT_OF_RANGE")
    hashes = {n: sha(source/(n+".json")) for n in SOURCE_NAMES}
    require(hashes == a["source_sha256"], "FROZEN_SOURCE_SHA_MISMATCH")
    evidence = ca.status(bundle)  # Rechecks PDF/text, quotes, references and version conflicts.
    require(evidence["bundle_sha256"] == a["evidence_bundle_sha256"], "EVIDENCE_BUNDLE_SHA_MISMATCH")
    require(not evidence["conflicting_fields"] and len(evidence["events"]) == 1, "CONFLICTING_OR_DUPLICATE_EVENT")
    require(not any(b.startswith("DISCLOSED_AFTER_DECISION") for b in evidence["blockers"]), "LATE_DISCLOSURE")
    if kind == "frozen_authorized_history":
        prior = read(ROOT/"docs/evidence/m1-pr07b/real-summary.json")
        require(evidence == prior, "REAL_SOURCE_MUST_BE_ORIGINAL_PR38_BUNDLE")
        require(hashes == prior["historical_baseline"]["raw_sha256"], "REAL_SOURCE_MUST_BE_ORIGINAL_FIVE_FILES")
    else:
        require(evidence["evidence_kind"] == "synthetic_test", "ARTIFICIAL_SOURCE_CANNOT_CLAIM_REAL")
    fact = evidence["events"][0]["facts"]
    expected = dict(symbol="600000.SH", event_type="CASH_DIVIDEND", cash_amount="0.42", cash_unit="CNY_PER_SHARE",
                    currency="CNY", tax_basis="GROSS", record_date="2026-07-15", ex_date="2026-07-16")
    require(all(fact[k] == val for k, val in expected.items()), "EVENT_FACT_UNIT_DATE_OR_AMOUNT_CONFLICT")
    require(all(evidence["field_coverage"][k] == "VERIFIED_LITERAL" for k in expected), "EVENT_FACT_REFERENCE_MISSING")
    require(all(fact[k] in (None, "0") for k in ("stock_dividend_ratio", "capitalization_ratio", "rights_ratio")),
            "KNOWN_MIXED_ACTION_NOT_SUPPORTED")
    extraction = read(source/"extraction.json")
    params = extraction["params"]
    require(params["ts_code"] == "600000.SH" and params["exchange"] == "SSE" and
            params["start_date"] <= start <= end <= params["end_date"], "SOURCE_QUERY_SCOPE")
    require(ms(extraction["extracted_at_utc"]) >= h.stamp(end, 18), "EXTRACTION_BEFORE_HISTORY_END")
    cal = h.index(h.rows(source/"calendar.json"), "cal_date", start, end, True)
    dates = {(h.day(start)+dt.timedelta(days=i)).strftime("%Y%m%d")
             for i in range((h.day(end)-h.day(start)).days+1)}
    require(set(cal) == dates and all(str(r["is_open"]) in ("0", "1") for r in cal.values()), "CALENDAR_GAP")
    opened = sorted(d for d in cal if str(cal[d]["is_open"]) == "1")
    daily = h.index(h.rows(source/"daily.json"), "trade_date", start, end)
    limits = h.index(h.rows(source/"limits.json"), "trade_date", start, end)
    require(opened and set(daily) == set(opened) and set(limits) == set(opened), "MISSING_OR_EXTRA_PRICE_RULE_DATE")
    suspended = set()
    for row in h.rows(source/"suspensions.json"):
        if start <= str(row["trade_date"]) <= end:
            require(row["ts_code"] == "600000.SH", "SUSPENSION_SYMBOL_MISMATCH")
            require(row["suspend_type"] in ("S", "R"), "UNKNOWN_SUSPENSION_STATUS")
            suspended.add(str(row["trade_date"]))  # Any intraday suspension => no modeled fill.
    sessions, discontinuities = [], []
    previous = None
    for i, date in enumerate(opened):
        require(not i or str(cal[date]["pretrade_date"]) == opened[i-1], "CALENDAR_PREDECESSOR_MISMATCH")
        row = daily[date]
        prices = {k+"_fen": h.exact(row[k], 100) for k in ("open", "high", "low", "close")}
        low, high, op, close = (prices[k+"_fen"] for k in ("low", "high", "open", "close"))
        require(0 < low <= min(op, close) <= max(op, close) <= high, "INVALID_OHLC")
        pre = h.exact(row["pre_close"], 100)
        if previous is not None and pre != previous:
            require(date == "20260716" and previous-pre == h.exact(fact["cash_amount"], 100),
                    "UNEXPLAINED_OR_CONFLICTING_DISCONTINUITY")
            discontinuities.append(dict(day=date, previous_close_fen=previous, pre_close_fen=pre,
                evidence_event_id=fact["event_id"], event_type=fact["event_type"],
                interpretation="observed_breakpoint_ex_post_cash_scenario_only_not_PIT"))
        previous = close
        lower, upper = h.exact(limits[date]["down_limit"], 100), h.exact(limits[date]["up_limit"], 100)
        require(0 < lower < upper and all(lower <= p <= upper for p in prices.values()), "PRICE_BAND_CONFLICT")
        volume = h.exact(row["vol"], 100)
        require(volume >= 100, "VOLUME_INVALID")
        available = h.stamp(date, 18)
        sessions.append(dict(day=int(date), opens_at=h.stamp(date, 9, 30), closes_at=h.stamp(date, 15),
            available_at=available, **prices, volume_shares=volume, capacity_shares=100, status_verified=True,
            opening=None, rules=dict(available_at=available,
                source="historical stk_limit + suspend_d; SSE-20260706 ordinary-A model (not PIT)",
                tradable=date not in suspended, settlement="TPlusOne", buy_lot=100, sell_lot=100,
                allow_odd_lot_liquidation=True, tick_size_fen=1, min_price_fen=lower, max_price_fen=upper)))
    require([d["day"] for d in discontinuities] == ["20260716"], "EXPECTED_OBSERVED_BREAKPOINT_MISSING")
    by_day = {s["day"]: s for s in sessions}
    announcement, record, ex, payment = (ms(value[k]) for k in ("announcement_at", "record_at", "ex_at", "payment_at"))
    record_day, ex_day, payment_day = (int(ca.timestamp(value[k]).astimezone(ca.ZONE).strftime("%Y%m%d"))
                                      for k in ("record_at", "ex_at", "payment_at"))
    require(record_day == 20260715 and ex_day == 20260716 and payment_day in by_day,
            "MODEL_EVENT_DATE_MISMATCH_OR_MISSING")
    require(record == h.stamp("20260715", 19) and ex == by_day[ex_day]["opens_at"] and
            payment >= ex and payment == by_day[payment_day]["opens_at"], "MODEL_EVENT_CLOCK_INVALID")
    require(ca.timestamp(value["announcement_at"]).astimezone(ca.ZONE).date().isoformat() == fact["announcement_date"]
            and announcement <= by_day[record_day]["closes_at"], "ANNOUNCEMENT_CLOCK_CONFLICT")
    source_id = evidence["events"][0]["source_id"]
    acquired_at = evidence["obtained_at"][source_id]
    event = dict(schema="CASH_DIVIDEND_V1", event_id="600000-20260716-cash-scenario", version=a["version"],
        instrument=dict(market="Shanghai", code="600000"), mode="historical_replay",
        evidence_basis="historical_ex_post_assumption", fact_status="EX_POST_MODEL_ONLY",
        source_sha256=evidence["bundle_sha256"], source_available_at=ms(acquired_at), announcement_at=announcement,
        record_day=record_day, record_close_at=by_day[record_day]["closes_at"], record_at=record,
        ex_day=ex_day, ex_at=ex, payment_day=payment_day, payment_at=payment,
        currency="CNY", cash_amount_fen=42, cash_unit="per_share",
        tax=dict(version=m["withholding_ppm"]["version"], basis="historical_ex_post_assumption",
            identity="modeled_withholding_only_not_real_account", withholding_ppm=rate, rounding="ceil_per_event_fen_v1"),
        historical_pit="NOT_VERIFIED", real_account_eligible=False)
    manifest = dict(protocol=PROTOCOL, source_sha256=hashes, assumption_sha256=sha(assumption_path),
        evidence_bundle_sha256=evidence["bundle_sha256"], evidence_summary_sha256=ca.sha(ca.canonical(evidence)),
        extraction=extraction, actual_announcement_obtained_at=acquired_at,
        historical_published_at=next(d["published_at"] for d in evidence["documents"] if d["id"] == source_id),
        event_fact_status=evidence["event_fact_status"], event_facts=fact,
        historical_availability="PIT_NOT_VERIFIED; actual receipt retained; model clocks never historical receipt",
        selected_start=start, selected_end=end, window_policy=a["window_policy"], sessions=len(sessions),
        discontinuities=discontinuities, assumptions=a,
        fee_validity="20260706..20261231 explicit unchanged paper model; not actual broker tariff")
    fee = dict(version="paper-cost-assumption-20260706-v1",
        source="explicit model: inclusive commission 300ppm min500fen; transfer10ppm; sell tax500ppm; per-fill ceil fen, not broker tariff",
        valid_from=20260706, valid_through=20261231, commission_ppm=300, minimum_commission_fen=500,
        transfer_ppm=10, sell_tax_ppm=500)
    dataset = dict(schema_version=4, mode="historical_replay",
        source="Tushare personal local research" if kind == "frozen_authorized_history" else "artificial historical model fixture; no market evidence",
        license=a["license_scope"], source_version=PROTOCOL, timezone="Asia/Shanghai",
        price_semantics="unadjusted_cny_fen", instrument=event["instrument"], fee=fee,
        historical=dict(availability=h.AVAILABILITY, execution="historical_ex_post_execution_assumption",
            strategy="sma5-20-cross-fixed100-v1", completeness="complete_calendar_and_daily_rows", source_manifest=manifest),
        scenario=dict(protocol=PROTOCOL, evidence_class="EXPLORATORY_EX_POST", input_kind=kind,
            assumption_sha256=sha(assumption_path), evidence_bundle_sha256=evidence["bundle_sha256"],
            real_historical_eligibility="DENIED", real_pit_days_added=0, manifest=manifest),
        cash_dividends=[event], sessions=sessions)
    require(hashes == {n: sha(source/(n+".json")) for n in SOURCE_NAMES}, "SOURCE_CHANGED_DURING_PREPARATION")
    return dataset, manifest


def freeze(source, bundle, assumptions, out):
    isolated(out)
    dataset, manifest = build(source, bundle, assumptions)
    out.mkdir(parents=True, exist_ok=False)
    (out/"dataset.json").write_bytes(ca.canonical(dataset))
    (out/"manifest.json").write_bytes(ca.canonical(manifest))
    result = public(dataset, scenario_engineering_status="PREPARED_PENDING_REPLAY", input_sha256=sha(out/"dataset.json"))
    write(out/"summary.json", result)
    return result


def public(dataset, **extra):
    s = dataset["scenario"]
    return dict(protocol=PROTOCOL, input_kind=s["input_kind"], evidence_class="EXPLORATORY_EX_POST",
        first_day=dataset["sessions"][0]["day"], last_day=dataset["sessions"][-1]["day"], sessions=len(dataset["sessions"]),
        source_sha256=s["manifest"]["source_sha256"], assumption_sha256=s["assumption_sha256"],
        evidence_bundle_sha256=s["evidence_bundle_sha256"], real_historical_eligibility="DENIED",
        blockers=list(BLOCKERS), research_evidence="INSUFFICIENT_EVIDENCE", historical_pit="PIT_NOT_VERIFIED",
        eligibility="ELIGIBILITY_DENIED", opening_source="BLOCKED", real_provider="NOT_VERIFIED",
        real_pit_days_added=0, live_trading_allowed=False, **extra)


def preflight(dataset, source, bundle, assumptions):
    """Second raw-to-frozen check, separate from the preparation constructor."""
    from decimal import Decimal
    a = read(assumptions)
    meta = dataset["scenario"]["manifest"]
    require(dataset["schema_version"] == 4 and dataset["mode"] == "historical_replay" and
            dataset["scenario"]["protocol"] == PROTOCOL, "PREFLIGHT_PROTOCOL")
    require(meta["assumptions"] == a and meta["assumption_sha256"] == sha(assumptions) and
            meta["source_sha256"] == {n: sha(source/(n+".json")) for n in SOURCE_NAMES}, "PREFLIGHT_SHA_BINDING")
    evidence = ca.status(bundle)
    require(meta["evidence_summary_sha256"] == ca.sha(ca.canonical(evidence)) and
            meta["evidence_bundle_sha256"] == evidence["bundle_sha256"], "PREFLIGHT_EVIDENCE")
    raw = {int(r["trade_date"]): r for r in h.rows(source/"daily.json")
           if a["selected_start"] <= str(r["trade_date"]) <= a["selected_end"]}
    calendar = h.rows(source/"calendar.json")
    opened = sorted(int(r["cal_date"]) for r in calendar if str(r["is_open"]) == "1" and
                    a["selected_start"] <= str(r["cal_date"]) <= a["selected_end"])
    require([s["day"] for s in dataset["sessions"]] == opened == sorted(raw), "PREFLIGHT_CALENDAR")
    previous, breaks = None, []
    for s in dataset["sessions"]:
        r = raw[s["day"]]
        # Decimal here does not call the preparation adapter's exact().
        for k in ("open", "high", "low", "close"):
            require(Decimal(str(r[k]))*100 == s[k+"_fen"], "PREFLIGHT_PRICE")
        pre = Decimal(str(r["pre_close"]))*100
        if previous is not None and pre != previous:
            require(s["day"] == 20260716 and previous-pre == 42, "PREFLIGHT_UNEXPLAINED_BREAK")
            breaks.append(s["day"])
        previous = Decimal(str(r["close"]))*100
        date = dt.datetime.strptime(str(s["day"]), "%Y%m%d").replace(tzinfo=ca.ZONE)
        for key, hour, minute in (("opens_at", 9, 30), ("closes_at", 15, 0), ("available_at", 18, 0)):
            require(s[key] == int(date.replace(hour=hour, minute=minute).timestamp())*1000, "PREFLIGHT_CLOCK")
        require(s["opening"] is None and s["capacity_shares"] == 100, "PREFLIGHT_FORWARD_EVIDENCE_DENIED")
    require(breaks == [20260716] and len(dataset["cash_dividends"]) == 1, "PREFLIGHT_EVENT_COUNT")
    e = dataset["cash_dividends"][0]
    facts = evidence["events"][0]["facts"]
    require(e["cash_amount_fen"] == Decimal(facts["cash_amount"])*100 and e["cash_unit"] == "per_share" and
            e["currency"] == "CNY" and e["source_available_at"] == ms(meta["actual_announcement_obtained_at"]) and
            e["fact_status"] == "EX_POST_MODEL_ONLY" and e["historical_pit"] == "NOT_VERIFIED" and
            e["real_account_eligible"] is False, "PREFLIGHT_EVENT_IDENTITY")
    require(all(e[k] == ms(a["models"][k]["value"]) for k in ("announcement_at", "record_at", "ex_at", "payment_at"))
            and e["tax"]["withholding_ppm"] == a["models"]["withholding_ppm"]["value"], "PREFLIGHT_MODEL_CLOCK_OR_TAX")
    return dict(protocol=PROTOCOL, status="PASS", algorithm="separate raw Decimal/calendar/event/time binding",
                historical_admission="DENIED", real_pit_days_added=0)


def audit_timeline(dataset, report):
    """Recompute frozen SMA signals from prefix closes, independently of Rust."""
    identity = report["config"]["deployment"]["strategy_id"]
    versions = {"sma-cross": "sma5-20-cross-fixed100-v1", "scenario-buy-hold": "first-close-next-open-fixed100-v1",
                "scenario-cash": "cash-no-orders-v1"}
    require(identity in versions and report["strategy_version"] == versions[identity] and
            report["config"]["deployment"]["frozen_version"] == versions[identity], "FROZEN_STRATEGY_IDENTITY")
    expected, closes, previous = [], [], None
    signals = []
    for s in dataset["sessions"]:
        expected.append((s["opens_at"], 1, "HistoricalNextOpenV1", s["day"], None))
        closes.append(s["close_fen"])
        signal = None
        if identity == "scenario-buy-hold" and len(closes) == 1:
            signal = "Buy"
        elif identity == "sma-cross" and len(closes) >= 20:
            above = sum(closes[-5:])*4 > sum(closes[-20:])
            if previous is not None and previous != above:
                signal = "Buy" if above else "Sell"
            previous = above
        if signal:
            limit = (min(s["close_fen"]+(s["close_fen"]+49)//50, s["rules"]["max_price_fen"]-1) if signal == "Buy"
                     else max(s["close_fen"]-(s["close_fen"]+49)//50, s["rules"]["min_price_fen"]+1))
            p = dict(proposal_id=1 if identity == "scenario-buy-hold" else s["day"],
                account_id=report["config"]["account_id"], deployment=report["config"]["deployment"],
                instrument=dataset["instrument"], side=signal, quantity=100, limit_price=limit,
                decision_at=s["available_at"], data_available_at=s["available_at"],
                earliest_execution_at=s["available_at"]+1, expires_at=s["available_at"]+14*86_400_000)
            signals.append(p)
            expected.append((s["available_at"], 1, "Submit", s["day"], p))
    for e in dataset["cash_dividends"]:
        for phase in ("record", "ex", "payment"):
            expected.append((e[phase+"_at"], 0, "CashDividendV1", e[phase+"_day"], phase))
    expected.sort(key=lambda row: (row[0], row[1]))
    require(len(expected) == len(report["events"]), "MISSING_OR_EXTRA_FROZEN_COMMAND")
    sessions = {s["day"]: s for s in dataset["sessions"]}
    for item, audit in zip(expected, report["events"]):
        _, _, kind, day, value = item
        require(list(audit["command"]) == [kind], "CORPORATE_ACTION_CLOCK_ORDER")
        cmd = audit["command"][kind]
        s = sessions[day]
        rules = dict(instrument=dataset["instrument"], trading_day=day,
            **{k: val for k, val in s["rules"].items() if not k.endswith("_fen")},
            tick_size=s["rules"]["tick_size_fen"], min_price=s["rules"]["min_price_fen"], max_price=s["rules"]["max_price_fen"])
        if kind == "HistoricalNextOpenV1":
            bar = cmd["bar"]
            require(bar["day"] == day and cmd["now"] == s["available_at"] and
                    all(bar[k] == s[k+"_fen"] for k in ("open", "high", "low", "close")) and
                    all(bar[k] == s[k] for k in ("opens_at", "closes_at", "available_at", "volume_shares", "capacity_shares", "status_verified")),
                    "FROZEN_PRICE_OR_SESSION_CHANGED")
            require(cmd["rules"] == rules, "FROZEN_RULES_CHANGED")
        elif kind == "Submit":
            require(cmd["proposal"] == value and cmd["now"] == s["available_at"] and cmd["day"] == day,
                    "FROZEN_SMA_OR_BENCHMARK_CHANGED_OR_LOOKAHEAD")
            fee = dataset["fee"]
            expected_fee = {k: val for k, val in fee.items() if k != "minimum_commission_fen"}
            expected_fee.update(minimum_commission=fee["minimum_commission_fen"], instrument=dataset["instrument"])
            require(cmd["rules"] == rules and cmd["fees"] == expected_fee, "SUBMISSION_RULE_OR_FEE_CHANGED")
        else:
            require(cmd["phase"] == value and cmd["day"] == day, "MODEL_PHASE_CHANGED")
    require([o["proposal"] for o in report["orders"]] == signals, "ORDER_LIST_DIFFERS_FROM_PREFIX_SIGNALS")
    require(report["historical_dividend_scenario"] == dataset["scenario"] and
            report["real_historical_eligibility"] == "DENIED" and report["real_pit_days_added"] == 0,
            "SCENARIO_MUST_NOT_GRANT_ADMISSION")


def verify_files(dataset, ledger, directory):
    report = read(directory/"report.json")
    audit_timeline(dataset, report)
    return v.verify_files(dataset, ledger, directory, historical_scenario=True)


def evaluate(dataset, input_path, ledger, report_dir, exe, out):
    out.mkdir(parents=True, exist_ok=False)
    original = {str(p): sha(p) for p in [input_path, ledger/"ledger.sqlite", *(report_dir/n for n in v.NAMES)]}
    backup = out/"verified-ledger"
    backup.mkdir()
    with sqlite3.connect((ledger/"ledger.sqlite").resolve().as_uri()+"?mode=ro", uri=True) as src:
        with sqlite3.connect(backup/"ledger.sqlite") as dst:
            src.backup(dst)
    v.cli(exe, "paper-historical-dividend-report", input_path, backup, out/"verified-report", "--sha256", sha(input_path))
    for name in v.NAMES:
        require((out/"verified-report"/name).read_bytes() == (report_dir/name).read_bytes(), "REEXPORT_DIFFERS:"+name)
    result = verify_files(dataset, backup, out/"verified-report")
    comparisons = {}
    flags = [x for pair in zip(v.FLAGS, CAPITAL) for x in pair]
    for kind, command in (("buy-hold", "paper-historical-dividend-benchmark"), ("cash", "paper-historical-dividend-cash-benchmark")):
        v.cli(exe, command, input_path, out/(kind+"-ledger"), out/(kind+"-report"), "--sha256", sha(input_path), *flags)
        comparisons[kind] = verify_files(dataset, out/(kind+"-ledger"), out/(kind+"-report"))
    require(comparisons["cash"]["ending_nav_fen"] == CAPITAL[0] and comparisons["cash"]["gross_income_fen"] == 0,
            "CASH_BENCHMARK_NOT_CASH")
    require(comparisons["buy-hold"]["gross_income_fen"] == 4200, "FIXED_BUY_HOLD_DID_NOT_ACQUIRE_RECORD_ENTITLEMENT")
    require(original == {p: sha(p) for p in original}, "EVALUATOR_MODIFIED_INPUT")
    evaluation = public(dataset, scenario_engineering_status="ENGINEERING_RUNNABLE", input_sha256=sha(input_path),
        accounting_audit="PASS", time_audit="PASS", strategy=result, benchmarks=comparisons,
        evaluator_version="historical-dividend-independent-accounting-v1",
        evaluator_sha256=sha(Path(__file__)), accounting_algorithm_sha256=sha(ROOT/"scripts/cash-dividend-evaluate.py"),
        ledger_head=read(report_dir/"report.json")["ledger_head"],
        acceptance="Sol self-test with independent Python arithmetic; not independent reviewer acceptance")
    write(out/"evaluation.json", evaluation)
    return evaluation


def run(source, bundle, assumptions, exe, out):
    isolated(out)
    out.mkdir(parents=True, exist_ok=False)
    freeze(source, bundle, assumptions, out/"frozen")
    dataset_path = out/"frozen/dataset.json"
    dataset = read(dataset_path)
    write(out/"preflight.json", preflight(dataset, source, bundle, assumptions))
    flags = [x for pair in zip(v.FLAGS, CAPITAL) for x in pair]
    for name in ("a", "b"):
        frozen_input = dataset_path
        if name == "b":
            freeze(source, bundle, assumptions, out/name/"frozen")
            frozen_input = out/name/"frozen/dataset.json"
            require(frozen_input.read_bytes() == dataset_path.read_bytes(), "TWO_FREEZES_DIFFER")
            preflight(read(frozen_input), source, bundle, assumptions)
        v.cli(exe, "paper-historical-dividend-replay", frozen_input, out/name/"ledger", out/name/"report",
              "--sha256", sha(frozen_input), *flags)
        evaluate(dataset, frozen_input, out/name/"ledger", out/name/"report", exe, out/name/"evaluation")
    require(v.journal(out/"a/ledger/ledger.sqlite") == v.journal(out/"b/ledger/ledger.sqlite"), "TWO_LEDGER_RESULTS_DIFFER")
    for name in v.NAMES:
        require((out/"a/report"/name).read_bytes() == (out/"b/report"/name).read_bytes(), "TWO_REPORTS_DIFFER:"+name)
    require(read(out/"a/evaluation/evaluation.json") == read(out/"b/evaluation/evaluation.json"), "TWO_EVALUATIONS_DIFFER")
    for kind in ("buy-hold", "cash"):
        for name in v.NAMES:
            require((out/"a/evaluation"/(kind+"-report")/name).read_bytes() ==
                    (out/"b/evaluation"/(kind+"-report")/name).read_bytes(), "TWO_BENCHMARKS_DIFFER")
    result = public(dataset, scenario_engineering_status="ENGINEERING_RUNNABLE", input_sha256=sha(dataset_path),
        two_fresh_runs_identical=True, accounting_identity="cash + shares*mark + receivable - tax_liability = NAV",
        income_identity="NAV - initial = realized + unrealized + dividend_gross - dividend_tax; external_flow=0",
        independent_python_accounting_and_time_audit="PASS", benchmark_entitled_shares=100,
        observed_breakpoint="20260716", original_sources_unchanged=True,
        acceptance="Sol self-test; no independent reviewer acceptance")
    require(dataset["scenario"]["manifest"]["source_sha256"] == {n: sha(source/(n+".json")) for n in SOURCE_NAMES},
            "ORIGINAL_SOURCES_CHANGED")
    write(out/"public-summary.json", result)
    return result


def fixture(out):
    """Materialize the committed artificial source and literal evidence fixture."""
    isolated(out)
    out.mkdir(parents=True, exist_ok=False)
    raw = read(ROOT/"samples/historical-dividend/source-fixture.json")
    source = out/"source"
    source.mkdir()
    for name in SOURCE_NAMES:
        write(source/(name+".json"), raw[name])
    facts = dict(symbol="600000.SH", event_id="artificial-cash-2026", event_type="CASH_DIVIDEND",
        announcement_date="2026-07-09", record_date="2026-07-15", ex_date="2026-07-16",
        scheduled_pay_date="2026-07-16", cash_amount="0.42", cash_unit="CNY_PER_SHARE", currency="CNY", tax_basis="GROSS",
        tax_terms="人工合成每股现金红利含税", **{k: None for k in ("net_cash_amount", "stock_dividend_ratio",
            "capitalization_ratio", "rights_ratio", "stock_listing_date", "sellable_date", "actual_account_cash_received_at")})
    text = "synthetic_test 600000 artificial-cash-2026 现金红利 每股人民币0.42元（含税） 公告2026-07-09 登记2026-07-15 除息发放2026-07-16 人工合成每股现金红利含税"
    evidence_dir = out/"evidence"
    evidence_dir.mkdir()
    (evidence_dir/"artificial.txt").write_text(text, encoding="utf-8")
    document = dict(id="artificial", role="implementation", version="artificial-v1", supersedes=None,
        document_id="artificial-cash-2026", path="artificial.txt", sha256=sha(evidence_dir/"artificial.txt"),
        text_path="artificial.txt", text_sha256=sha(evidence_dir/"artificial.txt"), public_url=None,
        obtained_at="2026-10-31T13:50:22Z", disclosed_on="2026-07-09", published_at=None,
        disclosure_basis="document_signed_date", review_method="operator_manual_document_text_crosscheck")
    manifest = dict(schema_version=1, evidence_kind="synthetic_test", symbol="600000.SH", breakpoint="2026-07-16",
        decision_at="2026-07-16T01:30:00Z", documents=[document], events=[dict(source_id="artificial", facts=facts,
            references={k: dict(page=1, quote=text) for k, val in facts.items() if val is not None})], historical_source=None)
    write(evidence_dir/"manifest.json", manifest)
    evidence = ca.audit(evidence_dir/"manifest.json", out/"bundle")
    a = read(ROOT/"samples/historical-dividend/real-assumptions.example.json")
    a.update(input_kind="synthetic_test", selected_end="20260828", evidence_bundle_sha256=evidence["bundle_sha256"],
             source_sha256={n: sha(source/(n+".json")) for n in SOURCE_NAMES})
    write(out/"assumptions.json", a)
    return source, out/"bundle", out/"assumptions.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "evaluate", "demo"))
    parser.add_argument("--out", type=Path, required=True)
    for name in ("source-dir", "evidence-bundle", "assumptions"):
        parser.add_argument("--"+name, type=Path)
    for name in ("exe", "input", "ledger", "report"):
        parser.add_argument("--"+name, type=Path)
    args = parser.parse_args()
    isolated(args.out)
    existed = args.out.exists()
    try:
        if args.action == "demo":
            require(args.exe is not None, "EXE_REQUIRED")
            args.out.mkdir(parents=True, exist_ok=False)
            source, bundle, assumptions = fixture(args.out/"fixture")
            result = run(source, bundle, assumptions, args.exe, args.out/"run")
        elif args.action == "prepare":
            require(all((args.source_dir, args.evidence_bundle, args.assumptions)), "SOURCE_ARGUMENTS_REQUIRED")
            result = freeze(args.source_dir, args.evidence_bundle, args.assumptions, args.out)
        elif args.action == "run":
            require(all((args.exe, args.source_dir, args.evidence_bundle, args.assumptions)), "SOURCE_AND_EXE_REQUIRED")
            result = run(args.source_dir, args.evidence_bundle, args.assumptions, args.exe, args.out)
        else:
            require(all((args.exe, args.input, args.ledger, args.report)), "EVALUATION_ARGUMENTS_REQUIRED")
            dataset, _ = build(args.source_dir, args.evidence_bundle, args.assumptions)
            require(args.input.read_bytes() == ca.canonical(dataset), "INPUT_DIFFERS_FROM_SOURCE_PREFLIGHT")
            preflight(dataset, args.source_dir, args.evidence_bundle, args.assumptions)
            result = evaluate(dataset, args.input, args.ledger, args.report, args.exe, args.out)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, ca.Rejected, subprocess.TimeoutExpired) as error:
        # No raw provider data, paths or exception payloads enter public summaries.
        prepared = (args.out/"frozen/dataset.json").exists() or (args.out/"run/frozen/dataset.json").exists()
        blocked = dict(protocol=PROTOCOL, scenario_engineering_status="ENGINEERING_BLOCKED" if prepared else "DATA_BLOCKED", real_historical_eligibility="DENIED",
            blockers=[str(error) if isinstance(error, (ValueError, ca.Rejected)) else type(error).__name__],
            research_evidence="INSUFFICIENT_EVIDENCE", real_pit_days_added=0)
        if not args.out.exists():
            args.out.mkdir(parents=True)
        if not existed and not (args.out/"blocker.json").exists():
            write(args.out/"blocker.json", blocked)
        print(json.dumps(blocked, ensure_ascii=False))
        return 2
