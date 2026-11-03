"""Developer E2E and fault evidence. All data/keys/bills are synthetic.

The production CLI uses recorded transport. The libtest process driver changes
only transport to loopback and exposes commit-point faults, absent from the
production executable. Never issues a public Provider request.
"""
import argparse
import contextlib
import copy
import datetime as dt
from decimal import Decimal, localcontext
import http.server
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "scripts"))
import portfolio_research as p
import review

RUN = "rp-test-" + os.urandom(4).hex()
COMMANDS, FACTS = [], []
EVIDENCE = None
DRIVER = None


def fingerprint(paths):
    return {str(file): dict(sha256=p.j.sha(file.read_bytes()), mtime_ns=file.stat().st_mtime_ns, bytes=file.stat().st_size)
            for path in paths for file in ([path] if path.is_file() else path.rglob("*") if path.exists() else [])
            if file.is_file() and file.name not in ("owner-token", "settings.json")}


def cli(*args, code=0):
    command = [sys.executable, "-X", "utf8", "-B", "scripts/risk-portfolio.py", *map(str, args)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=160)
    COMMANDS.append(dict(command=["python", *command[1:]], exit_code=result.returncode))
    assert result.returncode == code, (args, result.returncode, result.stdout[:1500], result.stderr[:1500])
    return json.loads(result.stdout)


def settings():
    return p.read(p.settings_path())


def save_settings(value):
    p.c.write(p.settings_path(), value)


def setup(label, scenario="calm", version="novel-v1"):
    name = RUN + "-" + label + "-" + os.urandom(2).hex()
    cli("--name", name, "synthetic-freeze", "--scenario", scenario, "--strategy-version", version)
    return p.Run(name)


def queue(run, phase="risk"):
    return p.bridge("queue", run.name, phase)


def driver(run, task, *, point=None, behavior="wait", port=None, hold=False, legacy=False, at=None, model=None):
    env = dict(os.environ, STRATIDE_RP_TEST_DRIVER="1",
               STRATIDE_RESEARCH_KEY_GOOGLE="never-send-real-env-secret-55",
               STRATIDE_RESEARCH_KEY_DEEPSEEK="never-send-real-env-secret-55",
               HTTP_PROXY="http://127.0.0.1:1", HTTPS_PROXY="http://127.0.0.1:1", ALL_PROXY="http://127.0.0.1:1")
    for path in (run.root / "test-marker", run.root / "test-release"):
        if path.exists():
            path.unlink()
    if point:
        env["STRATIDE_RP_TEST_FAULT"] = json.dumps(dict(batch=run.name, point=point, behavior=behavior))
    if port:
        env["STRATIDE_RP_TEST_LOOPBACK_PORT"] = str(port)
    process = subprocess.Popen([str(DRIVER), "--exact", "risk_portfolio_tests::process_driver", "--nocapture"],
                               cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdin.write(json.dumps(dict(batch=run.name, task_id=int(task["id"]) if task else None, hold_lock=hold, legacy=legacy, at=at, model=model)).encode())
    process.stdin.close()
    process.stdin = None
    return process


def finish(process, code=0):
    out, err = process.communicate(timeout=20)
    assert process.returncode == code, (process.returncode, out[:2000], err[:2000])
    assert b"never-send-real-env-secret-55" not in out + err
    return out


def marker(run):
    until = time.monotonic() + 10
    while not (run.root / "test-marker").exists():
        assert time.monotonic() < until, "fault marker not reached"
        time.sleep(.01)


@contextlib.contextmanager
def server(response, mode="ok"):
    requests = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            assert self.headers["Authorization"] == "Bearer offline-google-oauth-or-deepseek-bearer-fixture"
            assert b"never-send-real-env-secret-55" not in body
            requests.append((self.path, json.loads(body)))
            if mode == "timeout":
                time.sleep(.6)
                return
            self.send_response(302 if mode == "redirect" else 200)
            if mode == "redirect":
                self.send_header("Location", "https://api.deepseek.com/chat/completions")
            self.end_headers()
            try:
                self.wfile.write(response)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, capture_output=True, check=True)
        assert Path(os.fsdecode(common.stdout).strip()).resolve().parent == ROOT, "Use an isolated Git checkout; never bind the Owner's checkout for tests"
        cls.owner = ROOT / "state/original-owner-agent"
        fresh = not cls.owner.exists()
        if fresh:
            original = subprocess.run([str(ROOT / "target/debug" / ("stratided.exe" if os.name == "nt" else "stratided")), "--agent-init-fake", str(cls.owner)], cwd=ROOT, capture_output=True)
            assert original.returncode == 0
        else:
            assert Path(p.binding()["agent_dir"]).resolve() == cls.owner.resolve()
        prior = p.read(cls.owner / "settings.json")
        if fresh:
            assert cli("init", code=2)["reason"] == "CLOUD_AGENT_BINDING_REQUIRED"
        assert not (p.root() / ".agent").exists()
        cli("init", "--agent-dir", cls.owner)
        assert p.read(cls.owner / "settings.json") == prior
        cli("configure-recorded")
        cls.original = settings()
        assert cls.original["budget"]["currency"] == "TST"
        assert cls.original["budget"] == prior["budget"] and cls.original["models"][:len(prior["models"])] == prior["models"]
        assert all(m["cloud"]["transport"] == "recorded" for m in cls.original["models"] if m["kind"] != "fake")
        with p.agent_db() as db:
            assert dict(db.execute("SELECT key,value FROM meta"))["default_model"] == "fake"
        cli("enable")

    def tearDown(self):
        save_settings(self.original)
        cli("enable")

    def test_01_two_scenarios_original_inbox_versions_readonly_and_fee_baselines(self):
        reports = []
        for scenario, version in (("calm", "novel-v1"), ("stress", "novel-v2")):
            run = setup(scenario, scenario, version)
            report = cli("--name", run.name, "once")
            assert len(report["risk_experts"]) == 3
            assert report["portfolio"]["cash_weight_bps"] == (10000 if scenario == "stress" else 4000)
            assert {e["market_regime"] for e in report["risk_experts"]} == {"HIGH_VOLATILITY" if scenario == "stress" else "NORMAL_VOLATILITY"}
            assert report["discovery"][0]["status"] == "DISCOVERY_UNVERIFIED"
            assert report["real_cloud_calls"] == report["orders"] == report["fills"] == 0
            assert cli("--name", run.name, "once") == report
            paths = [p.root(), ROOT / "state/candidates" / run.name]
            before = fingerprint(paths)
            assert cli("--name", run.name, "verify") == report
            assert cli("--name", run.name, "report") == report
            cli("status"); cli("models"); cli("history")
            inbox = cli("--name", run.name, "inbox")
            assert inbox["items"][0]["state"] == "AWAITING_OWNER_TEMPLATE"
            assert before == fingerprint(paths), "read-only commands changed durable evidence"
            # Independent synthetic future values are never placed in model inputs.
            comparisons = []
            for expert, series in zip(report["risk_experts"], run.frozen()["series"]):
                i = run.frozen()["series"].index(series)
                future = [10000+n*3+(int(450*math.sin(n*1.8+i)) if scenario == "stress" else int(30*math.sin(n+i))) for n in range(84,104)]
                with localcontext() as ctx:
                    ctx.prec = 40
                    close = [Decimal(o["close_fen"]) for o in series["observations"]] + list(map(Decimal, future))
                    returns = [b/a-1 for a,b in zip(close,close[1:])]
                    realized = [sum(x*x for x in returns[n-19:n+1])/20 for n in range(83,103)]
                    realized = [v.sqrt() for v in realized]
                for n in (5,20):
                    truth = float(sum(realized[:n])/n)
                    forecast = next(v["value_ratio"] for v in expert["volatility_forecast"] if v["sessions"] == n)
                    comparisons.append(dict(instrument=expert["instrument"], horizon=n, synthetic_realized_proxy=truth,
                        cloud_recording_absolute_error=abs(forecast-truth), naive_absolute_error=abs(expert["baseline_comparison"]["naive"]-truth),
                        ewma_absolute_error=abs(expert["baseline_comparison"]["ewma"]-truth)))
            FACTS.append(dict(case=scenario, comparisons=comparisons, predictive_claim="NONE_SYNTHETIC_RECORDED_ONLY", refusal_rate=0))
            if EVIDENCE:
                p.c.write(EVIDENCE / f"synthetic-{scenario}.json", report)
                p.c.write(EVIDENCE / f"synthetic-{scenario}-input.json", run.frozen())
                p.c.write(EVIDENCE / f"synthetic-{scenario}-inbox.json", inbox)
            reports.append(report)
        assert reports[0]["portfolio"]["strategy_hash"] != reports[1]["portfolio"]["strategy_hash"]
        # Reuse the original independently frozen evaluator, with explicit test Owner template.
        # This evaluates ONLY the fixed synthetic template, never certifies the new portfolio.
        parent = reports[0]["registration_sha256"]
        value = review.Review(reports[0]["name"], portfolio=True).run(parent, ROOT / "research/synthetic-candidate.example.json", "synthetic_test", None)
        assert value["handoff"]["eligibility"] == "ELIGIBILITY_DENIED"
        if EVIDENCE:
            p.c.write(EVIDENCE / "original-evaluator.json", value)

    def test_02_loopback_production_requests_auth_projection_and_no_proxy(self):
        run = setup("loopback")
        for phase in ("risk", "fusion"):
            q = queue(run, phase)
            with server((run.root / f"{phase}-recording.json").read_bytes()) as (port, requests):
                finish(driver(run, q, port=port))
                assert len(requests) == 1
                path, body = requests[0]
                if phase == "risk":
                    assert path.endswith("/projects/stratide-offline/queries")
                    assert body["query"].startswith("SELECT instrument, forecast_timestamp")
                    assert len(body["queryParameters"][0]["parameterValue"]["arrayValues"]) == 192
                    assert body["maximumBytesBilled"] == "10485760"
                else:
                    assert path == "/chat/completions"
                    assert "max_tokens" in body and "max_completion_tokens" not in body
                    assert "tools" not in body
                    assert "close_fen" not in json.dumps(body) and "available_at" not in json.dumps(body)
            assert p.task(q["id"])["status"] == "completed"
        FACTS.append(dict(case="production-loopback", requests=2, real_cloud_calls=0, real_key_sent=False, system_proxy_bypassed=True))

    def test_03_timeout_and_redirect_never_resend_or_release_budget(self):
        for mode in ("timeout", "redirect"):
            run = setup(mode)
            q = queue(run)
            with server(b"{}", mode) as (port, requests):
                finish(driver(run, q, port=port))
                assert len(requests) == 1
            t = p.task(q["id"])
            assert t["status"] == "outcome_uncertain" and t["calls"][0]["state"] == "outcome_uncertain"
            assert t["calls"][0]["maximum_micro"] == "1000" and t["calls"][0]["settled_micro"] == "0"
            result = cli("--name", run.name, "once", code=2)
            assert result["task_id"] == q["id"] and len(p.task(q["id"])["calls"]) == 1
            FACTS.append(dict(case=mode, post_dispatch="OUTCOME_UNCERTAIN", reservation_held=1000, requests=1, retries=0))

    def test_04_real_kill_at_dispatch_result_and_settlement_commit(self):
        for point in ("after_dispatch", "after_provider_result", "after_settled"):
            run = setup(point)
            q = queue(run)
            process = driver(run, q, point=point)
            marker(run)
            process.kill()
            process.communicate(timeout=5)
            bridge = p.bridge("tick", run.name, "risk")  # original Agent::recover
            assert bridge["status"] == "outcome_uncertain" and len(bridge["calls"]) == 1
            assert bridge["calls"][0]["state"] == ("settled" if point == "after_settled" else "outcome_uncertain")
            assert p.bridge("tick", run.name, "risk") == bridge
            FACTS.append(dict(case=point, actual_process_kill=True, recovered=bridge["status"], calls=1,
                              call_state=bridge["calls"][0]["state"], retries=0))

    def test_05_reserve_dispatch_rechecks_revocation_receipt_and_lowered_caps(self):
        for point, change in (("before_reserve", "revoke"), ("after_reserve", "revoke"), ("after_reserve", "cap"), ("after_reserve", "receipt"), ("after_reserve", "disable")):
            run = setup(change + point[:3])
            q = queue(run)
            process = driver(run, q, point=point)
            marker(run)
            if change == "disable":
                assert cli("disable")["enabled"] is False
            elif change == "receipt":
                frozen = run.frozen(); frozen["readiness_ref"] = "changed-receipt"
                p.c.write(run.root / "frozen.json", frozen)
            else:
                config = settings()
                if change == "revoke":
                    next(m for m in config["models"] if m["id"] == "risk-timesfm")["grant"]["revoked"] = True
                else:
                    config["budget"]["daily_limit_micro"] = 1
                save_settings(config)
            (run.root / "test-release").write_text("continue")
            finish(process)
            t = p.task(q["id"])
            assert t["status"] in ("cancelled", "failed")
            assert len(t["calls"]) == (0 if point == "before_reserve" else 1)
            assert all(v["state"] == "no_charge" for v in t["calls"])
            FACTS.append(dict(case=change, boundary=point, dispatched=0, durable_reason=t["reason"]))
            save_settings(self.original)
            cli("enable")

    def test_06_single_daily_monthly_batch_caps_two_processes_and_cross_period_holds(self):
        run = setup("caps")
        f = run.frozen(); f["batch_budget_micro"] = 1; p.c.write(run.root / "frozen.json", f)
        assert cli("--name", run.name, "once", code=2)["reason"] == "BATCH_BUDGET_EXHAUSTED"
        for cap in ("daily_limit_micro", "monthly_limit_micro"):
            config = settings(); config["budget"][cap] = 1; save_settings(config)
            run = setup(cap[:3])
            assert cli("--name", run.name, "once", code=2)["reason"] in ("DAILY_BUDGET_EXHAUSTED", "MONTHLY_BUDGET_EXHAUSTED")
            save_settings(self.original)
        run = setup("lock")
        process = driver(run, None, point="holding_lock", hold=True)
        marker(run)
        assert cli("--name", run.name, "once", code=2)["reason"] == "AGENT_ALREADY_RUNNING"
        (run.root / "test-release").write_text("continue"); finish(process)
        q = queue(run)
        # A durable prior-period unknown bill is kept in the same original calls table.
        with contextlib.closing(sqlite3.connect(p.agent_dir() / "agent.sqlite")) as db, db:
            db.execute("INSERT INTO calls(task_id,day,month,maximum_micro,price_version,state,created_at) VALUES(?,?,?,?,?,'outcome_uncertain',?)",
                       (int(q["id"]), "2026-10-31", "2026-10", 1000000, "synthetic-cross-period", "2026-10-31T23:59:00Z"))
        fresh = setup("held")
        assert cli("--name", fresh.name, "once", code=2)["reason"] == "DAILY_BUDGET_EXHAUSTED"
        # Explicit synthetic test cleanup is a bill settlement, never deleting reservations/history.
        with contextlib.closing(sqlite3.connect(p.agent_dir() / "agent.sqlite")) as db, db:
            db.execute("UPDATE calls SET state='settled',settled_micro=0,reason='SYNTHETIC_TEST_INVOICE_ZERO' WHERE price_version='synthetic-cross-period'")
        FACTS.append(dict(case="caps-and-two-process-exclusion", batch_daily_monthly_rejected=True, cross_period_maximum_held=True))

    def test_07_bad_input_weights_receipts_never_self_approve(self):
        for change in ("context", "future", "real", "weights", "unknown_position", "infinite", "receipt"):
            run = setup(change)
            frozen = run.frozen()
            if change == "context":
                frozen["series"][0]["observations"] = frozen["series"][0]["observations"][:21]
            elif change == "future":
                frozen["series"][0]["observations"][-1]["available_at"] = "2099-01-01T00:00:00Z"
            elif change == "real":
                frozen["input_mode"] = "forward_observed_eod"
            elif change == "receipt":
                (run.root / "risk-recording.json").write_bytes(b"{}")
            else:
                recording = p.read(run.root / "fusion-recording.json")
                proposal = json.loads(recording["choices"][0]["message"]["content"])
                if change == "weights":
                    proposal["cash_weight_bps"] = 4001
                elif change == "unknown_position":
                    proposal["positions"][0]["instrument"] = "300999.SZ"
                else:
                    proposal["positions"][0]["target_weight_bps"] = 1e300
                recording["choices"][0]["message"]["content"] = json.dumps(proposal)
                p.c.write(run.root / "fusion-recording.json", recording)
                frozen["fusion_recording_sha256"] = p.j.sha((run.root / "fusion-recording.json").read_bytes())
            if change in ("context", "future"):
                frozen["snapshot_ref"] = p.digest(dict(series=frozen["series"], calendar=frozen["calendar"]))
            p.c.write(run.root / "frozen.json", frozen)
            result = cli("--name", run.name, "once", code=2)
            assert result["live_allowed"] is False and result["can_execute_forward_paper"] is False
            expected = dict(context="INSUFFICIENT_MODEL_CONTEXT", future="BAD_OR_FUTURE_OBSERVATION", real="REAL_READINESS_BLOCKED",
                            weights="TARGET_PORTFOLIO_INVALID", unknown_position="PORTFOLIO_SOURCE_OR_INSTRUMENT_UNVERIFIED",
                            infinite="PORTFOLIO_SCHEMA", receipt="OUTBOUND_RECEIPT_CHANGED_NEW_TASK_REQUIRED")
            assert result["reason"] == expected[change], (change, result["reason"])
            assert not (run.root / "archive.json").exists()
            FACTS.append(dict(case=change, result="REJECTED_ENTIRE_PROPOSAL_OR_INPUT", reason=result["reason"], automatic_repairs=0))

    def test_08_sensitive_error_is_hashed_and_redacted_with_held_reservation(self):
        run = setup("secret-response")
        q = queue(run)
        with server(b'{"error":{"message":"never-send-real-env-secret-55"}}') as (port, requests):
            finish(driver(run, q, port=port))
            assert len(requests) == 1
        t = p.task(q["id"])
        assert t["status"] == "outcome_uncertain"
        receipt = t["result"]["cloud_failure"]
        assert receipt["raw_result_sha256"] and receipt["retry_allowed"] is False
        assert "never-send-real-env-secret-55" not in json.dumps(t)
        assert receipt["raw_error_body"] == "NOT_STORED_OR_LOGGED"
        FACTS.append(dict(case="sensitive-error-redaction", raw_error_saved=False, raw_result_hash_saved=True, reservation_held=True))

    def test_09_renaming_batches_or_git_environment_cannot_reset_shared_authority(self):
        run = setup("owner")
        q = queue(run)
        name = RUN + "-copied"
        copied = p.Run(name)
        copied.root.mkdir()
        for file in ("frozen.json", "risk-recording.json", "fusion-recording.json"):
            (copied.root / file).write_bytes((run.root / file).read_bytes())
        assert cli("--name", name, "once", code=2)["reason"] == "FROZEN_BATCH_OWNED_BY_ANOTHER_NAME"
        authority = p.root()
        with patch.dict(os.environ, dict(GIT_DIR=str(ROOT / "state/nonexistent-git-dir"), GIT_WORK_TREE="invalid", GIT_COMMON_DIR="invalid")):
            assert p.root() == authority
            assert "risk-timesfm" in {m["id"] for m in p.bridge("descriptor")}
        assert p.task(q["id"])["calls"] == []
        FACTS.append(dict(case="immutable-authority-and-batch-owner", copied_batch_dispatched=0, git_environment_reset=False))

    def test_10_actual_task_provider_must_match_the_frozen_stage_pin(self):
        config = settings()
        extra = copy.deepcopy(next(m for m in config["models"] if m["id"] == "risk-timesfm")); extra["id"] = "other-risk-provider"
        config["models"].append(extra); save_settings(config)
        run = setup("wrong-model")
        q = queue(run)
        # Simulate a wrong caller choosing another otherwise configured/authorized model.
        descriptor = {m["id"]: m for m in p.bridge("descriptor")}
        with contextlib.closing(sqlite3.connect(p.agent_dir() / "agent.sqlite")) as db, db:
            db.execute("UPDATE tasks SET provider_id=?,provider_hash=? WHERE id=?",
                       (extra["id"], descriptor[extra["id"]]["fingerprint"], int(q["id"])))
        result = p.bridge("tick", run.name, "risk")
        assert result["reason"] == "PINNED_CLOUD_TASK_MODEL_MISMATCH" and result["calls"] == []
        FACTS.append(dict(case="actual-provider-pin-mismatch", calls=0, rejected=True))

    def test_11_original_agent_spend_and_both_cloud_stages_share_daily_monthly_caps(self):
        for period in ("daily", "monthly"):
            legacy_run = setup("legacy-spend-" + period)
            encoded = finish(driver(legacy_run, None, legacy=True))
            legacy = json.loads(next(line.removeprefix(b"RP_RESULT=") for line in encoded.splitlines() if line.startswith(b"RP_RESULT=")))
            assert legacy["status"] == "completed" and legacy["result"]["provider_kind"] == "fake"
            assert int(legacy["calls"][0]["settled_micro"]) > 0
            view = p.status()
            descriptor = {m["id"]: m for m in p.bridge("descriptor")}
            maximum = descriptor["risk-timesfm"]["maximum_micro"] + descriptor["fusion-deepseek"]["maximum_micro"]
            config = settings()
            config["budget"]["daily_limit_micro"] = view["daily_settled_micro"] + view["held_maximum_micro"] + maximum + 100000
            config["budget"]["monthly_limit_micro"] = view["monthly_settled_micro"] + view["held_maximum_micro"] + maximum + 100000
            config["budget"][period + "_limit_micro"] -= 100001
            save_settings(config)
            run = setup("shared-" + period)
            result = cli("--name", run.name, "once", code=2)
            assert result["phase"] == "fusion" and result["reason"] == period.upper() + "_BUDGET_EXHAUSTED"
            assert len(run.task_for(run.intent("risk"))["calls"]) == 1
            assert run.task_for(run.intent("fusion"))["calls"] == []
            with p.agent_db() as db:
                assert db.execute("SELECT settled_micro FROM calls WHERE id=?", (int(legacy["calls"][0]["id"]),)).fetchone()[0] > 0
                assert dict(db.execute("SELECT key,value FROM meta"))["default_model"] == "fake"
                assert db.execute("SELECT COUNT(*) FROM tasks WHERE trigger_key=?", ("legacy-owner-fixture:" + legacy_run.name,)).fetchone()[0] == 1
            FACTS.append(dict(case="original-agent-spend-shared-" + period, legacy_task=legacy["id"], legacy_call=legacy["calls"][0]["id"],
                              cloud_risk_task=result["task_id"], rejected=result["reason"], same_existing_database=True, default_model_unchanged=True))
            save_settings(self.original)

    def test_12_original_agent_unknown_cost_survives_month_boundary_into_cloud_gate(self):
        run = setup("legacy-month")
        prior = dt.datetime.now(p.j.ZONE).replace(day=1,hour=0,minute=0,second=0,microsecond=0) - dt.timedelta(minutes=1)
        encoded = finish(driver(run, None, legacy=True, model="fake-unknown", at=prior.isoformat()))
        legacy = json.loads(next(line.removeprefix(b"RP_RESULT=") for line in encoded.splitlines() if line.startswith(b"RP_RESULT=")))
        call = legacy["calls"][0]
        assert legacy["status"] == "outcome_uncertain" and call["state"] == "outcome_uncertain"
        assert call["month"] != dt.datetime.now(p.j.ZONE).strftime("%Y-%m")
        view = p.status(); descriptor = {m["id"]: m for m in p.bridge("descriptor")}
        config = settings()
        config["budget"]["daily_limit_micro"] = view["daily_settled_micro"] + view["held_maximum_micro"] + descriptor["risk-timesfm"]["maximum_micro"] + descriptor["fusion-deepseek"]["maximum_micro"] - 1
        save_settings(config)
        cloud_run = setup("new-month-cloud")
        blocked = cli("--name", cloud_run.name, "once", code=2)
        assert blocked["phase"] == "fusion" and blocked["reason"] == "DAILY_BUDGET_EXHAUSTED"
        with p.agent_db() as db:
            state, maximum, settled = db.execute("SELECT state,maximum_micro,settled_micro FROM calls WHERE id=?", (int(call["id"]),)).fetchone()
            assert state == "outcome_uncertain" and maximum == int(call["maximum_micro"]) and settled == 0
        FACTS.append(dict(case="legacy-month-boundary-unknown", legacy_task=legacy["id"], legacy_call=call["id"],
                          maximum_held=maximum, old_month=call["month"], new_cloud_rejected=blocked["reason"], retries=0, database_rebuilt=False))

    def test_13_binding_does_not_create_or_switch_cost_authority(self):
        other = ROOT / ("state/other-original-agent-" + os.urandom(3).hex())
        init = subprocess.run([str(ROOT / "target/debug" / ("stratided.exe" if os.name == "nt" else "stratided")), "--agent-init-fake", str(other)], cwd=ROOT, capture_output=True)
        assert init.returncode == 0
        before = p.status()
        denied = cli("init", "--agent-dir", other, code=2)
        assert denied["reason"] == "CLOUD_AGENT_BINDING_IMMUTABLE"
        assert p.status() == before and not (p.root() / ".agent").exists()
        original = (p.root() / "agent-binding.json").read_bytes()
        mutated = p.binding(); mutated["authority_id"] = "f" * 64
        p.c.write(p.root() / "agent-binding.json", mutated)
        try:
            assert cli("status", code=2)["reason"] == "CLOUD_AGENT_AUTHORITY_CHANGED"
        finally:
            (p.root() / "agent-binding.json").write_bytes(original)
        assert p.status() == before
        FACTS.append(dict(case="explicit-existing-authority-binding", silent_new_database=False, rebinding_rejected=True,
                          changed_authority_rejected=True, budget_and_calls_unchanged=True))


def main():
    global DRIVER, EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--driver", type=Path, required=True)
    args = parser.parse_args()
    DRIVER, EVIDENCE = args.driver.absolute(), args.evidence
    if EVIDENCE:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PortfolioTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if EVIDENCE:
        p.c.write(EVIDENCE / "checks.json", dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), facts=FACTS,
            commands=COMMANDS, real_cloud_calls=0, billable_calls=0, paper_live_orders=0, independent_acceptance="NOT_VERIFIED"))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
