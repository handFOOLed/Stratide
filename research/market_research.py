"""MarketDaySnapshot consumer of the existing foreground EOD Operator.

One Agent database, one CPU Worker, one cloud budget. No network/data collection
here; absent qualified history is a visible block, never a historical substitute.
"""
import contextlib
import datetime as dt
from collections import Counter
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import candidates as c
import data_snapshot as d
import eod_journal as j
import market_eod as m
import portfolio_research as rp

import stratide_paths as paths

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
import model as timesfm_model

POLICY = "market-research-v1"
CONFIG = "market_research_config_v1"
RUN = "market_research_run:"
WSL_BLOCK_COOLDOWN_SECONDS = 600
# Frozen deterministic policy, independent of LLM output.
RULES = dict(version="market-screen-v1", context=84, min_listing_days=180,
             min_amount_thousand_yuan="10000", max_amount_thousand_yuan="100000000",
             max_abs_daily_return="0.30", ranking="amount_desc_then_symbol")


def bridge(action, value=None):
    exe = paths.executable("market-research-agent")
    p = subprocess.run([str(exe), action], input=json.dumps(value or {}, allow_nan=False).encode(),
                       cwd=ROOT, capture_output=True, timeout=150)
    if p.stderr:
        # Local bridge diagnostics (sanitized by the bridge) stay on stderr so a
        # rejected provider response can be investigated without re-sending it.
        sys.stderr.write(p.stderr.decode("utf-8", errors="replace"))
        sys.stderr.flush()
    v = j.loads(p.stdout)
    j.require(p.returncode == 0, v.get("error_code", "MARKET_RESEARCH_BRIDGE_FAILED"))
    return v


@contextlib.contextmanager
def database(write=False):
    b = rp.binding()
    path = Path(b["agent_dir"]) / "agent.sqlite"
    with contextlib.closing(sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                                           uri=True, timeout=5)) as db:
        rp.verify_authority(db, b)
        if write:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
        yield db
        if write:
            db.commit()


def get(db, key):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return j.loads(row[0]) if row else None


def save(day, value):
    with database(True) as db:
        db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (RUN + day, j.canonical(value).decode()))
        if value.get("reason"):
            code = value["reason"]
            request = dict(name="全市场研究阻断 " + day, goal=code, scope="owner_task",
                           start_day=m.h.day(day).isoformat(), end_day=m.h.day(day).isoformat(), task_budget_micro=None)
            summary = dict(version=POLICY + ":notice", source_day=m.h.day(day).isoformat(), mode="no_input",
                           scopes=["owner_task"], summary=dict(source_day=day, reason=code), eod_eligible=False)
            # A finished, non-dispatchable status task enters the existing inbox.
            # It is explicitly not a model result and never creates a call row.
            db.execute("INSERT OR IGNORE INTO tasks(request,input,provider_id,provider_hash,status,reason,created_at,finished_at,trigger_key) "
                       "VALUES(?,?,'market-research-status',?,'blocked',?,?,?,?)",
                       (j.canonical(request).decode(), j.canonical(summary).decode(), rp.digest(summary), code,
                        m.h.now(), m.h.now(), POLICY + ":notice:" + day + ":" + code))


def prefix(market, day, as_of):
    """All sessions come from the trusted calendar, not a weekday guess."""
    with market.read(inspect_raw_paths=False) as db:
        current = market.load_snapshot(db, day)
        j.require(current is not None and current["state"] == "READY", "MARKET_DAY_NOT_QUALIFIED")
        j.require(current["catalog_state"] == "VERIFIED" and current["market_denominator_verified"],
                  "CATALOG_SCOPE_NOT_VERIFIED")
        j.require(current["catalog_source_day"] == day and not current["late_backfill"],
                  "LATE_OR_FUTURE_CATALOG_NOT_DECISION_EVIDENCE")
        at = m.instant(as_of)
        j.require(at <= dt.datetime.now(dt.timezone.utc) and at >= m.instant(current["available_at"]),
                  "SOURCE_NOT_AVAILABLE_AT_DECISION")
        calendar = market.latest_objects(db, "trade_cal")
        scopes = [sorted(r["cal_date"] for r in calendar if r["exchange"] == e
                         and r["is_open"] == "1" and r["cal_date"] <= day)[-RULES["context"]:]
                  for e in ("SSE", "SZSE")]
        j.require(scopes[0] == scopes[1] and len(scopes[0]) == RULES["context"] and scopes[0][-1] == day,
                  "MARKET_HISTORY_CONTEXT_UNAVAILABLE")
        days, snapshots, sources = scopes[0], [], []
        for date in days:
            v = market.load_snapshot(db, date)
            j.require(v is not None and v["state"] == "READY" and m.instant(v["available_at"]) <= at,
                      "MARKET_HISTORY_NOT_READY_AT_DECISION")
            snapshots.append(v)
            parts = {}
            for ref in v["sources"]:
                if ref["api"] in ("daily", "adj_factor", "suspend_d"):
                    j.require(ref["status"] in m.GOOD, "MARKET_HISTORY_SOURCE_BLOCKED")
                    parts.setdefault(ref["api"], {})
                    # Existing response() verifies raw and normalized SHA.
                    for row in market.response(db, ref["id"])["rows"]:
                        parts.setdefault(ref["api"], {})[j.canonical(row).decode()] = row
            sources.append({api: list(rows.values()) for api, rows in parts.items()})
        return days, snapshots, sources


def screen(days, snapshots, sources, as_of, count):
    """One linear scan; no per-stock inference and no future input."""
    current = snapshots[-1]
    eligible = set(current["eligible_symbols"])
    prices = [{r["ts_code"]: r for r in p["daily"]} for p in sources]
    factors = [{r["ts_code"]: r for r in p["adj_factor"]} for p in sources]
    suspensions = [{r["ts_code"] for r in p["suspend_d"] if r["suspend_type"] == "S"} for p in sources]
    rejected, features = [], []
    for security in current["securities"]:
        code, reason = security["ts_code"], None
        if code not in eligible:
            reason = security["reasons"][0] if security["reasons"] else security["category"]
        elif (m.h.day(days[-1]) - m.h.day(security["list_date"])).days < RULES["min_listing_days"]:
            reason = "LISTING_TOO_SHORT"
        elif any(code not in p or code not in f for p, f in zip(prices, factors)):
            reason = "CONTINUOUS_HISTORY_OR_ACTION_EVIDENCE_MISSING"
        elif any(code in s for s in suspensions):
            reason = "SUSPENSION_IN_CONTEXT"
        elif len({f[code]["adj_factor"] for f in factors}) != 1:
            reason = "CORPORATE_ACTION_DISCONTINUITY"
        else:
            rows = [p[code] for p in prices]
            previous = None
            for row in rows:
                op, hi, lo, close, pre, volume, amount = (Decimal(row[k]) for k in
                    ("open", "high", "low", "close", "pre_close", "vol", "amount"))
                if (row.get("quality_flags") or not 0 < lo <= min(op, close) <= max(op, close) <= hi
                        or volume <= 0 or amount <= 0 or pre <= 0):
                    reason = "PRICE_OR_VOLUME_QUALITY"
                    break
                if (previous is not None and pre != previous) or abs(close / pre - 1) > Decimal(RULES["max_abs_daily_return"]):
                    reason = "EXTREME_RETURN_OR_ACTION_GAP"
                    break
                previous = close
            if reason is None:
                amount = Decimal(rows[-1]["amount"])
                if not Decimal(RULES["min_amount_thousand_yuan"]) <= amount <= Decimal(RULES["max_amount_thousand_yuan"]):
                    reason = "LIQUIDITY_OUTSIDE_FROZEN_BOUNDS"
                else:
                    features.append(dict(instrument=code, amount_thousand_yuan=str(amount),
                                         as_of=as_of, source_day=days[-1]))
        if reason:
            rejected.append(dict(instrument=code, reason=reason))
    features.sort(key=lambda r: (-Decimal(r["amount_thousand_yuan"]), r["instrument"]))
    selected = features[:count]
    rejected.extend(dict(instrument=r["instrument"], reason="RESOURCE_TOP_LIMIT") for r in features[count:])
    return dict(rules=RULES, rules_sha256=rp.digest(RULES), implementation_sha256=j.sha(Path(__file__).read_bytes()),
                universe_sha256=current["catalog_sha256"],
                snapshot_sha256=current["snapshot_sha256"], context_snapshots=[s["snapshot_sha256"] for s in snapshots],
                source_day=days[-1], as_of=as_of, universe_count=len(current["securities"]),
                qualified_count=len(features), selected=selected, rejected=rejected,
                rejection_counts=dict(sorted(Counter(r["reason"] for r in rejected).items())),
                historical_pit_status="NOT_VERIFIED", corporate_actions="EX_POST_NO_DETECTED_ACTION_NOT_VERIFIED")


def freeze_cpu(market, days, snapshots, sources, selected, as_of, batch, replace=False):
    sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
    import cli as cpu
    import history
    symbols = [r["instrument"] for r in selected]
    descriptor = cpu.bridge("descriptor")
    # Preserve the existing immutable historical CPU contract and labels.
    with market.read(inspect_raw_paths=False) as db:
        catalog = {s["ts_code"]: s for s in snapshots[-1]["securities"] if s["ts_code"] in symbols}
        # Exact snapshot-native versions, rather than the V1 historical-query
        # API whose authorization deliberately ends at 2026-10-30.
        daily = dict(rows=[])
        for snapshot in snapshots:
            rows = db.execute("SELECT d.row_json,v.id,v.status,v.source_sha,v.manifest FROM day_versions v "
                "JOIN day_rows r ON r.version_id=v.id JOIN daily_rows d "
                "ON d.ts_code=r.ts_code AND d.trade_date=r.trade_date AND d.row_sha=r.row_sha WHERE v.id=? "
                "AND d.ts_code IN (" + ",".join("?" for _ in symbols) + ") ORDER BY d.ts_code",
                [snapshot["native_day_version"], *symbols]).fetchall()
            daily["rows"].extend(dict(values=j.loads(row[0]), version_id=row[1], partition_status=row[2],
                                      source_sha=row[3], availability=j.loads(row[4])) for row in rows)
    j.require(all(max(m.instant(a["obtained_at"]) for a in row["availability"]["attempts"]) <= m.instant(as_of)
                  for row in daily["rows"]), "MARKET_HISTORY_NOT_READY_AT_DECISION")
    factor = dict(rows=[dict(data=r) for p in sources for r in p["adj_factor"] if r["ts_code"] in symbols],
                  partitions=[r for s in snapshots for r in s["sources"] if r["api"] == "adj_factor"])
    susp = dict(rows=[dict(data=r) for p in sources for r in p["suspend_d"] if r["ts_code"] in symbols],
                partitions=[r for s in snapshots for r in s["sources"] if r["api"] == "suspend_d"])
    f, history_input = history.assemble(descriptor, symbols, as_of, days, catalog, daily, factor, susp,
        dict(market_snapshots=[s["snapshot_sha256"] for s in snapshots]), dict(source="MarketDaySnapshot"))
    plan = dict(batch=batch, frozen=f, history=history_input,
                manifest_sha256=cpu.planning_manifest()["manifest_sha256"],
                code_sha256=descriptor["code_sha256"], max_context=256, batch_size=1, threads=2)
    cpu.bridge("project", plan)
    path = cpu.batch_path(batch) / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        j.require(cpu.read_plan(batch) == plan, "MARKET_RESEARCH_PLAN_CHANGED")
    else:
        c.write(path, plan)
    return plan


def finish_fusion(day, run, task):
    run["fusion_task_id"] = task["id"]
    j.require(task["status"] == "completed", task["reason"])
    run["state"] = "FUSION_DONE"
    if "FUSION_DONE" not in run["events"]:
        run["events"].append("FUSION_DONE")
    save(day, run)
    registry = c.Registry("market-" + day, create=True)
    with registry.locked():
        export = registry.root / "market-task.json"
        c.write(export, task)
        registration = registry.register(None, export)
    run.update(state="CANDIDATE_FROZEN", registration_sha256=registration["registration_sha256"],
               candidate_sha256=rp.digest(task["result"]["research"]["risk_portfolio"]["portfolio"]),
               cloud_status="FUSION_DONE", reason=None)
    run["events"].append("CANDIDATE_FROZEN")
    run.pop("retry_pending", None)
    save(day, run)
    return run


def resume_fusion(run):
    day = run["source_day"]
    task_id = run["fusion_task_id"]
    if not run.get("retry_pending"):
        # An older Dashboard may already have queued the same safe task.
        run["retry_pending"] = True
        save(day, run)
    try:
        task = bridge("once", dict(source_day=day, resume_task_id=int(task_id)))
        j.require(task["id"] == task_id, "MARKET_RETRY_RUN_UNAVAILABLE")
        if task["status"] == "completed":
            return finish_fusion(day, run, task)
        run.pop("retry_pending", None)
        run.update(state="REJECTED", reason=task["reason"], cloud_status="CLOUD_RESEARCH_BLOCKED")
        save(day, run)
        return run
    except Exception as error:
        # Keep the intent across worker-lock contention and process death.
        # The bridge recovers the same task and retains any dispatch marker.
        reason = str(error) if isinstance(error, j.Rejected) else "MARKET_RESEARCH_LOCAL_FAILURE"
        return dict(run, state="BLOCKED", reason=reason)


def once(market):
    """Called only by the original market once/watch loop or explicit Owner CLI."""
    with database() as db:
        config = get(db, CONFIG)
    if config is None or not config["automatic_timesfm"]:
        return dict(state="DISABLED", **rp.SAFE)
    # Cross-process OS exclusion releases after a crash, unlike expiring guesses.
    with d.writer(Path(rp.binding()["agent_dir"]) / "market-research.lock"):
        with database() as db:
            config = get(db, CONFIG)
            pending = None
            if config and config["automatic_timesfm"] and config["automatic_deepseek"] and not get(db, "paused"):
                pending = db.execute("""
                    SELECT m.value FROM tasks t JOIN meta m
                    ON m.key='market_research_run:' || substr(t.trigger_key, length(?) + 1)
                    WHERE t.provider_id='market-deepseek-fusion'
                    AND CAST(t.id AS TEXT)=json_extract(m.value, '$.fusion_task_id')
                    AND (json_extract(m.value, '$.retry_pending')=1
                        OR (json_extract(m.value, '$.state')='REJECTED'
                            AND t.status='queued' AND t.reason='OWNER_SAFE_RETRY'
                            AND NOT EXISTS (SELECT 1 FROM calls WHERE task_id=t.id
                                AND (state!='no_charge' OR COALESCE(reason,'')!='RESTART_BEFORE_DISPATCH'))))
                    ORDER BY t.id LIMIT 1
                """, (POLICY + ":",)).fetchone()
        if pending:
            return resume_fusion(j.loads(pending[0]))
        if config is None or not config["automatic_timesfm"]:
            return dict(state="DISABLED", **rp.SAFE)
        status = market.report()
        latest = status["latest"]
        if latest is None:
            return dict(state="BLOCKED", reason="NO_FROZEN_MARKET_SNAPSHOT", **rp.SAFE)
        day = latest["source_day"]
        with database() as db:
            run = get(db, RUN + day)
        if run and run["state"] in ("CANDIDATE_FROZEN", "REJECTED"):
            return run
        if run and run.get("state") == "BLOCKED":
            reason = run.get("reason")
            blocked_at = run.get("blocked_at")
            if isinstance(reason, str) and reason.startswith(
                    ("TIMESFM_WSL_", "WORKER_", "MARKET_RESEARCH_LOCAL_FAILURE",
                     "MARKET_RESEARCH_BRIDGE_FAILED", "RESEARCH_UNAVAILABLE")) and blocked_at:
                try:
                    age = (m.instant(m.h.now()) - m.instant(blocked_at)).total_seconds()
                except (TypeError, ValueError):
                    age = WSL_BLOCK_COOLDOWN_SECONDS
                if 0 <= age < WSL_BLOCK_COOLDOWN_SECONDS:
                    return run
        if run is None:
            run = dict(state="EOD_RECEIVED", source_day=day, as_of=m.h.now(), events=["EOD_RECEIVED"],
                       data_mode=latest["data_mode"], config=config, config_sha256=rp.digest(config), batch="market-" + day, **rp.SAFE)
            save(day, run)
        try:
            # Config changes affect future days; pause/revocation still gate dispatch.
            recovering = ("fusion_task_id" not in run
                          and run.get("state") in ("BLOCKED", "TIMESFM_DONE", "SCREENED", "EOD_RECEIVED"))
            refresh = "screen" not in run
            if not refresh:
                current = (run["screen"]["rules_sha256"], run["screen"]["implementation_sha256"])
                expected = (rp.digest(RULES), j.sha(Path(__file__).read_bytes()))
                if current != expected:
                    # A code/rule update must not deadlock automation forever: a blocked
                    # run that never froze a plan or cloud task may be re-screened with
                    # the new implementation at the current time.
                    j.require("fusion_task_id" not in run,
                              "SCREEN_IMPLEMENTATION_CHANGED_NEW_RUN_REQUIRED")
                    run.pop("screen", None)
                    run.pop("screen_sha256", None)
                    run.pop("plan_sha256", None)
                    run["state"] = "EOD_RECEIVED"
                    run["events"] = ["EOD_RECEIVED"]
                    save(day, run)
                    refresh = True
            if refresh:
                # A blocked collection has not made a research decision yet.
                # Freeze the decision time only when the source is admitted.
                run["as_of"] = m.h.now()
                days, snapshots, sources = prefix(market, day, run["as_of"])
                run["screen"] = screen(days, snapshots, sources, run["as_of"], run["config"]["candidate_count"])
                run["screen_sha256"] = rp.digest(run["screen"])
                run["state"] = "SCREENED"
                run["events"].append("SCREENED")
                save(day, run)
            j.require(run["screen"]["selected"], "NO_QUALIFIED_RESEARCH_CANDIDATES")
            sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
            sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
            import cli as cpu
            if "plan_sha256" not in run:
                days, snapshots, sources = prefix(market, day, run["as_of"])
                plan = freeze_cpu(market, days, snapshots, sources, run["screen"]["selected"], run["as_of"], run["batch"], replace=recovering)
                run["plan_sha256"] = rp.digest(plan)
                save(day, run)
            with database() as db:
                live_config = get(db, CONFIG)
            j.require(live_config is not None and live_config["automatic_timesfm"], "MARKET_RESEARCH_DISABLED")
            cpu.bridge("enable")
            result = cpu.once(run["batch"])
            j.require(result["state"] == "completed", result.get("reason", "TIMESFM_PARTIAL_OR_FAILED"))
            if "TIMESFM_DONE" not in run["events"]:
                run["state"] = "TIMESFM_DONE"
                run["events"].append("TIMESFM_DONE")
                save(day, run)
            if not run["config"]["automatic_deepseek"]:
                run["cloud_status"] = "CLOUD_RESEARCH_BLOCKED"
                run["reason"] = "AUTOMATIC_CLOUD_DISABLED"
                save(day, run)
                return run
            return finish_fusion(day, run, bridge("once", dict(source_day=day)))
        except Exception as error:
            known = isinstance(error, (j.Rejected, c.Rejected, m.Error, timesfm_model.Rejected))
            code = str(error) if known else "MARKET_RESEARCH_LOCAL_FAILURE"
            # A failed/unknown paid task is terminal. A readiness/grant block can
            # resume without replacing input or creating another daily task.
            if "fusion_task_id" in run:
                if run["state"] != "FUSION_DONE":
                    run["state"] = "REJECTED"
                    run["events"].append("REJECTED")
            else:
                run["state"] = "BLOCKED"
            run.update(reason=code, cloud_status="CLOUD_RESEARCH_BLOCKED")
            if not known:
                run["local_error"] = dict(type=type(error).__name__)
            if isinstance(code, str) and code.startswith(
                    ("TIMESFM_WSL_", "WORKER_", "MARKET_RESEARCH_LOCAL_FAILURE")):
                run["blocked_at"] = m.h.now()
            save(day, run)
            return run


def provenance(task, store_name):
    j.require(store_name is None, "MARKET_RESEARCH_SOURCE_ONLY")
    original = bridge("task", dict(task_id=int(task["id"])))
    j.require(original == task and task["status"] == "completed", "ORIGINAL_MARKET_FUSION_REQUIRED")
    return dict(snapshot_sha256=task["input"]["summary"]["screen_sha256"],
                task_origin="ORIGINAL_AGENT_SQLITE_VERIFIED_BY_RUNNER", data_mode=task["input"]["mode"],
                historical_pit_status="NOT_VERIFIED", restriction="RESEARCH_ONLY",
                eod_eligible=False, can_execute_forward_paper=False, live_allowed=False)
