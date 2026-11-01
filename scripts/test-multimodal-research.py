"""Actual PR33 -> local math -> Rust Agent fake/Budget -> original Inbox.

All sources are new synthetic 1041 journals. Fault/clock injection exists only
in this runner; production CLI has no equivalent flags. No public requests.
"""
import argparse
import copy
import datetime as dt
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "scripts"))
import multimodal as m
import multimodal_experts as e
import review

spec = importlib.util.spec_from_file_location("mm_snapshot_fixtures", ROOT / "scripts/test-data-snapshot.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
RUN = "mm-test-" + os.urandom(4).hex()
WORK = ROOT / "state/multimodal-tests" / RUN
TODAY = dt.datetime.now(m.j.ZONE).date()
DAYS = [(TODAY - dt.timedelta(days=24-i)).strftime("%Y%m%d") for i in range(25)]
COMMANDS, RESULTS = [], []
EVIDENCE = None


def fingerprint(paths):
    return {str(file): (file.stat().st_mtime_ns, m.j.sha(file.read_bytes())) for path in paths
            for file in ([path] if path.is_file() else path.rglob("*") if path.exists() else []) if file.is_file()}


def counts(name=None):
    with m.agent_db() as db:
        where, values = (" WHERE trigger_key LIKE ?", ("multimodal-v1:" + name + ":%",)) if name else ("", ())
        tasks = db.execute("SELECT id FROM tasks" + where, values).fetchall()
        ids = [row[0] for row in tasks]
        calls = db.execute("SELECT COUNT(*) FROM calls WHERE task_id IN (" + ",".join("?" for _ in ids) + ")", ids).fetchone()[0] if ids else 0
        return len(ids), calls


def fixture_cli(request):
    assert request["name"].startswith("mm-test-")
    def fault(point):
        if point == request.get("fault"):
            os._exit(86)
        if point == request.get("pause"):
            Path(request["marker"]).write_text(point)
            while not Path(request["release"]).exists():
                time.sleep(.02)
    def clock():
        return request.get("at") or m.s.clock_ms()
    # Python's runner never needs a socket. Rust's restricted Settings/authorize
    # tests prove every supported new-scope Provider is fake before DNS/key lookup.
    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(patch("socket.socket", side_effect=AssertionError("Python network denied")))
        if request.get("expert_failure") == "inconsistent":
            stack.enter_context(patch.object(e.TimeSeriesAdapter, "predict", return_value=dict(
                expected_return_ratio="0.9", volatility_ratio="0.1")))
        elif request.get("expert_failure") == "error":
            stack.enter_context(patch.object(e.TimeSeriesAdapter, "predict", side_effect=m.j.Rejected("TIMESERIES_EXPERT_FAILED")))
        return m.main(["--name", request["name"], *request["args"]], clock=clock, fault=fault)


def launch(name, *args, fixture=False, **options):
    if fixture:
        WORK.mkdir(parents=True, exist_ok=True)
        path = WORK / ("request-" + os.urandom(5).hex() + ".json")
        request = dict(name=name, args=list(map(str, args)), marker=str(path.with_suffix(".marker")),
                       release=str(path.with_suffix(".release")), **options)
        path.write_bytes(m.j.canonical(request))
        command = [sys.executable, "-X", "utf8", "-B", str(Path(__file__).absolute()), "--fixture-cli", str(path)]
    else:
        request = dict(name=name, args=list(map(str, args)))
        command = [sys.executable, "-X", "utf8", "-B", str(ROOT / "scripts/multimodal-research.py"), "--name", name, *map(str, args)]
    p = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.request, p.command = request, command
    return p


def finish(p, code=0):
    out, err = p.communicate(timeout=90)
    COMMANDS.append(dict(command=p.command, args=p.request["args"], name=p.request["name"],
                         exit_code=p.returncode, fault=p.request.get("fault")))
    if p.returncode != code:
        raise AssertionError(f"{p.request}: expected {code}, got {p.returncode}: {out[:3000]!r} {err[:3000]!r}")
    return json.loads(out) if out else None


def call(name, *args, code=0, **options):
    return finish(launch(name, *args, **options), code)


def setup(label, days=25, *, enable=True, falling=False, forward_mode_negative=False):
    name = RUN + "-" + label + "-" + os.urandom(2).hex()
    work = WORK / name
    work.mkdir(parents=True)
    source = work / "forward.sqlite"
    selected = DAYS[-days:]
    events = f.base_events()[:1]
    events[0]["config"]["observation_id"] = name
    events[0]["started_at"] = f.stamp(selected[0]) - 1000
    if forward_mode_negative:
        events[0]["host"] = "forward-mode-negative-fixture-not-real-observation"
    for i, day in enumerate(selected):
        fen = (1080-i*2 if falling else 1000+i*2) + (3 if i % 3 == 1 else 0)
        f.append_day(events, day, close=format(Decimal(fen) / 100, ".2f"))
    f.save_journal(source, events)
    process = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/research-data.py"), "--store", name,
                              "sync", "--observer", str(source)], capture_output=True, timeout=30)
    COMMANDS.append(dict(command=["research-data.py", "--store", name, "sync", "--observer", "synthetic_test"], exit_code=process.returncode))
    assert process.returncode == 0, process.stdout
    call(name, "init", "--snapshot-store", name)
    if enable:
        call(name, "enable")
    return name, source, events


def settings_update(callback):
    path = m.base_root() / ".agent/settings.json"
    value = m.c.read(path)
    callback(value)
    m.c.write(path, value)


class MultimodalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert m.EXE.is_file(), "cargo build --workspace first; no skipped E2E"
        assert dt.datetime.now(m.j.ZONE).hour >= 16, "synthetic production CLI E2E uses today's real after-close clock"
        cls.old_evidence = fingerprint([ROOT / "docs/evidence/m2-pr05", ROOT / "docs/evidence/m2-pr06",
            ROOT / "docs/evidence/m2-pr07", ROOT / "docs/evidence/m2-pr08", ROOT / "docs/evidence/m2-pr09",
            ROOT / "docs/evidence/m1-pr10", ROOT / "samples"])

    def setUp(self):
        path = m.base_root() / ".agent/settings.json"
        self.settings_before = path.read_bytes() if path.exists() else None

    def tearDown(self):
        if self.settings_before is not None:
            (m.base_root() / ".agent/settings.json").write_bytes(self.settings_before)

    @classmethod
    def tearDownClass(cls):
        assert cls.old_evidence == fingerprint([ROOT / "docs/evidence/m2-pr05", ROOT / "docs/evidence/m2-pr06",
            ROOT / "docs/evidence/m2-pr07", ROOT / "docs/evidence/m2-pr08", ROOT / "docs/evidence/m2-pr09",
            ROOT / "docs/evidence/m1-pr10", ROOT / "samples"])
        RESULTS.append(dict(check="protected_old_evidence", files=len(cls.old_evidence), unchanged=True))

    def test_01_two_independent_25_day_production_cli_e2e_and_inbox(self):
        for label, falling in (("e2e-a", False), ("e2e-b", True)):
            name, source, _ = setup(label, falling=falling)
            before = fingerprint([source, m.d.Store(name).path])
            first = call(name, "once")
            self.assertEqual(first["state"], "ARCHIVED")
            key = first["task_id"]
            report = call(name, "report", key)
            self.assertEqual(report["comparison"]["evaluated"], 4)
            self.assertEqual(report["comparison"]["refused"], 0)
            self.assertNotEqual(report["baseline"]["result"]["expected_return_ratio"], report["time_series"]["result"]["expected_return_ratio"])
            self.assertTrue(call(name, "once")["reused"])
            self.assertEqual(counts(name), (1, 1))
            task = m.task(first["agent_task_id"])
            self.assertEqual(task["input"]["summary"]["task_id"], key)
            self.assertEqual(task["calls"][0]["state"], "settled")
            self.assertEqual(task["provider_hash"], m.model_descriptor("fake")["provider_hash"])
            self.assertEqual(task["calls"][0]["price_version"], "synthetic-price-v1")
            # Independent label/MAE computation from original prices, not the
            # production comparison helper or its frozen expected values.
            content = m.d.Store(name).read_snapshot()[0]["content"]
            values = [Decimal(v["bar"]["close_fen"]) for v in content["bars"]]
            naive_errors, ts_errors = [], []
            for end in range(21, len(values)):
                returns = [values[i] / values[i-1] - 1 for i in range(end-20, end)]
                prediction = sum(returns) / 40
                label_return = values[end] / values[end-1] - 1
                naive_errors.append(abs(label_return))
                ts_errors.append(abs(prediction - label_return))
            errors = report["comparison"]["mean_absolute_error_ratio"]
            self.assertLess(abs(Decimal(errors["naive"]) - sum(naive_errors)/4), Decimal("2e-12"))
            self.assertLess(abs(Decimal(errors["time_series"]) - sum(ts_errors)/4), Decimal("2e-12"))
            inbox_process = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/research-review.py"),
                    "--multimodal", name, "inbox"], capture_output=True, timeout=30)
            self.assertEqual(inbox_process.returncode, 0, inbox_process.stdout)
            inbox = json.loads(inbox_process.stdout)
            self.assertEqual(inbox["items"][0]["state"], "AWAITING_OWNER_TEMPLATE")
            self.assertEqual(inbox["items"][0]["parent"]["parent_registration_sha256"], first["registration_sha256"])
            # Real read-only commands cannot even change mtimes or sidecars.
            protected = [m.base_root() / ".agent", m.Run(name).root, m.c.Registry(name).root, source, m.d.Store(name).root]
            snapshot = fingerprint(protected)
            for command in (("status",), ("history",), ("verify", key), ("report", key)):
                call(name, *command)
            self.assertEqual(snapshot, fingerprint(protected))
            self.assertEqual(before, fingerprint([source, m.d.Store(name).path]))
            self.assertFalse((m.c.Registry(name).root / "candidates").exists())
            if label == "e2e-a":
                owner_review = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/research-review.py"),
                    "--multimodal", name, "review", first["registration_sha256"], "--owner-input",
                    str(ROOT / "research/synthetic-candidate.example.json"), "--evidence-class", "synthetic_test"],
                    capture_output=True, timeout=60)
                self.assertEqual(owner_review.returncode, 0, owner_review.stdout + owner_review.stderr)
                evaluated = json.loads(owner_review.stdout)
                self.assertEqual(evaluated["state"], "EVALUATED")
                self.assertEqual(evaluated["research_evidence"], "SYNTHETIC_TEST_ONLY")
                self.assertEqual(evaluated["handoff"]["eligibility"], "ELIGIBILITY_DENIED")
                self.assertFalse(evaluated["live_allowed"])
                self.assertEqual(counts(name), (1, 1))
                RESULTS.append(dict(check="explicit_owner_review_reuses_original_evaluator",
                    candidate_sha256=evaluated["candidate_sha256"], evaluation_sha256=evaluated["evaluation_sha256"],
                    qualification="SYNTHETIC_TEST_ONLY", automated_template_selections=0, additional_agent_calls=0))
            RESULTS.append(dict(check="production_cli_e2e", name=name, source_days=25,
                task_id=key, report_sha256=report["report_sha256"], input_snapshot_sha256=first["input_snapshot_sha256"],
                baseline_sha256=first["baseline_sha256"], time_series_sha256=first["time_series_sha256"],
                fusion_sha256=first["fusion_sha256"], task_detail_sha256=first["task_detail_sha256"],
                registration_sha256=first["registration_sha256"], calls=first["calls"],
                walk_forward=report["comparison"], public_requests=0, provider="ORIGINAL_RUST_FAKE",
                readonly_byte_and_mtime_preserved=True))
            if EVIDENCE:
                m.c.write(EVIDENCE / (label + "-report.json"), report)

    def test_02_independent_adapter_replacement_and_no_fusion_control(self):
        name, _, _ = setup("adapter")
        first = call(name, "once")
        call(name, "experiment", "--time-series-model", "local-test-momentum", "--label", "momentum-v1")
        second = call(name, "once")
        self.assertNotEqual(first["task_id"], second["task_id"])
        report = call(name, "report", second["task_id"])
        self.assertEqual(report["time_series"]["model_id"], "local-test-momentum")
        self.assertEqual(counts(name), (2, 2))
        call(name, "experiment", "--without-fusion", "--label", "no-fusion-control")
        control = call(name, "once")
        self.assertEqual(control["state"], "COMPARISON_COMPLETED")
        self.assertIsNone(control["fusion"])
        self.assertEqual(counts(name), (2, 2))
        self.assertEqual(len(call(name, "history")["runs"]), 3)
        self.assertEqual(call(name, "verify", first["task_id"])["state"], "ARCHIVED")
        RESULTS.append(dict(check="adapter_replaced_and_no_fusion_control", first=first["task_id"], second=second["task_id"],
                            control=control["task_id"], original_agent_counts=list(counts(name))))

    def test_03_four_abrupt_exit_restarts_reuse_original_records(self):
        for point in ("after_freeze", "after_experts", "after_queue", "after_fusion"):
            name, source, events = setup(point)
            finish(launch(name, "once", fixture=True, fault=point), 86)
            prior = counts(name)
            self.assertEqual(prior, (1, 1) if point == "after_fusion" else (1, 0) if point == "after_queue" else (0, 0))
            if point == "after_fusion":
                self.assertEqual(list((m.c.Registry(name).root / "registrations").glob("*.json")), []) if (m.c.Registry(name).root / "registrations").exists() else None
                # A subsequent revision cannot erase or rerun the original
                # already-settled research; recovery uses its retained PR33 SHA.
                f.append_day(events, DAYS[-1], close="11.50")
                f.save_journal(source, events)
                self.assertTrue(m.d.Store(name).sync()["can_research"])
            resumed = call(name, "once")
            self.assertEqual(resumed["state"], "ARCHIVED")
            self.assertEqual(counts(name), (1, 1))
            if point == "after_fusion":
                self.assertEqual(call(name, "once", code=2)["reason"], "REVISED_OR_LATE_SOURCE_REJECTED")
                self.assertEqual(call(name, "verify", resumed["task_id"])["state"], "ARCHIVED")
            else:
                self.assertTrue(call(name, "once")["reused"])
            RESULTS.append(dict(check="abrupt_restart", point=point, before=list(prior), after=list(counts(name)),
                                task_id=resumed["task_id"], settled_without_candidate_reused=point == "after_fusion"))

    def test_04_two_processes_and_disable_enable_fence(self):
        name, _, _ = setup("concurrent")
        process = launch(name, "once", fixture=True, pause="after_experts")
        marker = Path(process.request["marker"])
        deadline = time.monotonic() + 20
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(marker.exists())
        self.assertEqual(call(name, "once", code=2)["reason"], "STORE_BUSY")
        call(name, "disable")
        Path(process.request["release"]).touch()
        blocked = finish(process, 2)
        self.assertEqual(blocked["reason"], "OWNER_DISABLED")
        self.assertEqual(counts(name), (0, 0))
        call(name, "enable")
        # Explicit new experiment after the recorded terminal failure.
        call(name, "experiment", "--label", "owner-reenabled")
        first, second = launch(name, "once"), launch(name, "once")
        aout, aerr = first.communicate(timeout=90)
        bout, berr = second.communicate(timeout=90)
        self.assertIn(first.returncode, (0, 2), aerr)
        self.assertIn(second.returncode, (0, 2), berr)
        self.assertEqual(counts(name), (1, 1))
        self.assertTrue(json.loads(aout).get("state") == "ARCHIVED" or json.loads(bout).get("state") == "ARCHIVED")
        RESULTS.append(dict(check="two_processes_disable_fence", duplicate_tasks=0, duplicate_calls=0,
                            disabled_new_calls=0, final_counts=list(counts(name))))

    def test_05_shared_account_rename_cannot_reset_budget_or_source_claim(self):
        name, _, _ = setup("owner")
        alias = RUN + "-alias-" + os.urandom(3).hex()
        call(alias, "init", "--snapshot-store", name)
        self.assertEqual(call(alias, "enable", code=2)["reason"], "MULTIMODAL_SOURCE_OWNED")
        self.assertEqual(counts(alias), (0, 0))
        config = m.Run(alias).config()
        self.assertEqual(config["agent_dir"], ".agent")
        self.assertEqual(m.Run(name).config()["agent_dir"], ".agent")

    def test_06_insufficient_21_history_forward_does_not_get_synthetic_warmup(self):
        name, source, events = setup("short", days=20)
        value = call(name, "once", code=2)
        self.assertEqual(value["reason"], "INSUFFICIENT_HISTORY")
        self.assertEqual(counts(name), (0, 0))
        content = m.j.verify_rows(f.chained(events))
        content["data_mode"] = "forward_observed_eod"
        with self.assertRaisesRegex(m.j.Rejected, "INSUFFICIENT_FORWARD_HISTORY"):
            e.source_window(dict(saved=dict(content=content), attempt=m.d.Store(name).read_snapshot()[1]), m.s.clock_ms())
        content["data_mode"] = "historical_replay"
        with self.assertRaisesRegex(m.j.Rejected, "HISTORICAL_REPLAY_EX_POST_ONLY"):
            e.source_window(dict(saved=dict(content=content), attempt=m.d.Store(name).read_snapshot()[1]), m.s.clock_ms())
        forward, _, _ = setup("forward-short", days=2, forward_mode_negative=True)
        self.assertEqual(call(forward, "once", code=2)["reason"], "INSUFFICIENT_FORWARD_HISTORY")
        self.assertEqual(counts(forward), (0, 0))
        full, _, _ = setup("forward-ca-blocked", forward_mode_negative=True)
        self.assertEqual(call(full, "once", code=2)["reason"], "CORPORATE_ACTION_PIT_NOT_VERIFIED")
        self.assertEqual(counts(full), (0, 0))
        RESULTS.append(dict(check="forward_mode_negative_fixtures_not_real_observations", short_reason="INSUFFICIENT_FORWARD_HISTORY",
                            sufficient_bars_but_ca_unknown="CORPORATE_ACTION_PIT_NOT_VERIFIED", generated_predictions=0))

    def test_07_budget_daily_monthly_revocation_cloud_and_unknown_are_not_retried(self):
        scenarios = (("daily", lambda raw: raw["budget"].update(daily_limit_micro=1), "DAILY_BUDGET_EXHAUSTED"),
                     ("month", lambda raw: raw["budget"].update(monthly_limit_micro=1), "MONTHLY_BUDGET_EXHAUSTED"))
        for label, change, reason in scenarios:
            name, _, _ = setup(label)
            original_settings = (m.base_root() / ".agent/settings.json").read_bytes()
            settings_update(change)
            value = call(name, "once", code=2)
            self.assertEqual(value["reason"], reason)
            self.assertEqual(counts(name), (1, 0))
            call(name, "once", code=2)
            self.assertEqual(counts(name), (1, 0))
            (m.base_root() / ".agent/settings.json").write_bytes(original_settings)
        name, _, _ = setup("revoked")
        settings_update(lambda raw: raw["models"][0]["grant"].update(revoked=True))
        call(name, "experiment", "--label", "revoked")
        self.assertEqual(call(name, "once", code=2)["reason"], "AUTHORIZATION_REQUIRED")
        self.assertEqual(counts(name), (0, 0))
        (m.base_root() / ".agent/settings.json").write_bytes(original_settings)
        name, _, _ = setup("cloud")
        settings_update(lambda raw: raw["models"][0].update(kind="chat_completions_v1",
                       endpoint="https://provider.example.com/v1/chat/completions", api_key_env="STRATIDE_RESEARCH_KEY_MM_UNSET", fake_scenario=None))
        self.assertEqual(call(name, "once", code=2)["reason"], "MULTIMODAL_LOCAL_FAKE_ONLY")
        self.assertEqual(counts(name), (0, 0))
        (m.base_root() / ".agent/settings.json").write_bytes(original_settings)
        name, _, _ = setup("unknown")
        call(name, "experiment", "--fusion-model", "fake-unknown", "--label", "unknown")
        unknown = call(name, "once", code=2)
        self.assertEqual(unknown["reason"], "FAKE_TIMEOUT_AFTER_POSSIBLE_CHARGE")
        call(name, "once", code=2)
        self.assertEqual(counts(name), (1, 1))
        with m.agent_db() as db:
            row = db.execute("SELECT maximum_micro,state FROM calls JOIN tasks ON calls.task_id=tasks.id WHERE trigger_key LIKE ?", ("multimodal-v1:" + name + ":%",)).fetchone()
        self.assertEqual(row[1], "outcome_uncertain")
        self.assertGreater(row[0], 0)
        name2, _, _ = setup("unknown-held")
        settings_update(lambda raw: raw["budget"].update(daily_limit_micro=row[0]))
        self.assertEqual(call(name2, "once", code=2)["reason"], "DAILY_BUDGET_EXHAUSTED")
        self.assertEqual(counts(name2), (1, 0))
        RESULTS.append(dict(check="budgets_revoked_cloud_unknown", public_requests=0, unknown_calls=1,
                            unknown_reservation_retained=True, daily_and_monthly_calls=0))

    def test_08_external_expert_and_fusion_format_failures_are_structured(self):
        name, _, _ = setup("no-external")
        call(name, "experiment", "--time-series-model", "external", "--label", "external")
        value = call(name, "once", code=2)
        self.assertEqual(value["reason"], "EXTERNAL_TIMESERIES_NOT_CONFIGURED")
        self.assertEqual(call(name, "history")["runs"][0]["state"], "FAILED")
        self.assertEqual(counts(name), (0, 0))
        self.assertEqual(call(name, "report", code=2)["state"], "FAILED")
        for failure, reason in (("inconsistent", "EXPERT_ARITHMETIC_MISMATCH"), ("error", "TIMESERIES_EXPERT_FAILED")):
            name, _, _ = setup("expert-" + failure)
            self.assertEqual(call(name, "once", fixture=True, expert_failure=failure, code=2)["reason"], reason)
            self.assertEqual(call(name, "report", code=2)["state"], "FAILED")
            self.assertEqual(counts(name), (0, 0))
        name, _, _ = setup("malicious")
        call(name, "experiment", "--fusion-model", "fake-text", "--label", "malicious")
        bad = call(name, "once", code=2)
        self.assertEqual(bad["reason"], "FUSION_COMMAND_OR_URL_REJECTED")
        self.assertEqual(counts(name), (1, 1))
        self.assertEqual(call(name, "report", code=2)["state"], "FUSION_FAILED")
        call(name, "once", code=2)
        self.assertEqual(counts(name), (1, 1))

    def test_09_malicious_expert_identity_numeric_schema_timezone_size(self):
        name, _, _ = setup("expert-negative")
        complete = call(name, "once")
        frozen = m.read(m.Run(name).path(complete["task_id"]) / "input.json")
        original = m.read(m.Run(name).path(complete["task_id"]) / "time-series.json")
        mutations = [lambda v: v.update(authority="TRADE"), lambda v: v.update(command="powershell"),
                     lambda v: v.update(calibrated_interval=[0, 1]), lambda v: v.update(generated_at="2026-11-01T17:00:00+08:00"),
                     lambda v: v.update(generated_at=e.utc(m.s.clock_ms()+86400000)),
                     lambda v: v.update(input_snapshot_sha256="0"*64), lambda v: v["result"].update(expected_return_ratio="NaN"),
                     lambda v: v["result"].update(expected_return_ratio="0.9"),
                     lambda v: v["cost"].update(daily_limit_micro=9999999), lambda v: v.update(limitations=["x"*20000])]
        for mutate in mutations:
            altered = copy.deepcopy(original)
            mutate(altered)
            with self.assertRaises((m.j.Rejected, ValueError, TypeError)):
                e.validate_expert(altered, frozen, "time_series")
        for text in ("https://provider.example.com/x", "C:\\secret.txt", "/tmp/secret", "$(Get-Content secrets)"):
            output = copy.deepcopy(m.task(complete["agent_task_id"])["result"]["research"]["fusion"])
            output["hypothesis"] = text
            with self.assertRaises(m.j.Rejected):
                m.validate_fusion(output)
        for key in ("authority", "command", "risk_limit", "positions", "budget", "script", "url"):
            output = copy.deepcopy(m.task(complete["agent_task_id"])["result"]["research"]["fusion"])
            output[key] = "TRADE"
            with self.assertRaises(m.j.Rejected):
                m.validate_fusion(output)
        forged = copy.deepcopy(m.task(complete["agent_task_id"]))
        forged["result"]["research"]["hypothesis"] = "forged success"
        with self.assertRaisesRegex(m.j.Rejected, "ORIGINAL_AGENT_TASK_MISMATCH"):
            m.provenance(forged, name)
        RESULTS.append(dict(check="malicious_expert_and_fusion", expert_rejections=len(mutations),
                            fusion_rejections=11, forged_original_task_rejected=True))

    def test_10_source_revision_gap_future_label_stale_mode_and_clock(self):
        name, source, events = setup("source-negative")
        src = m.s.source(m.d.Store(name))
        at = m.s.clock_ms()
        variants = [lambda v: v["versions"][-1].update(available_at=at+86400000),
                    lambda v: v["versions"][-1]["bar"].update(next_day_return=".5"),
                    lambda v: v["versions"][-1].update(revision_of=1),
                    lambda v: v["coverage"][-2].update(state="missing_valid_eod"),
                    lambda v: v.update(as_of_journal_event_at=at+86400000),
                    lambda v: v.update(data_mode="historical_replay")]
        for mutate in variants:
            altered = copy.deepcopy(src)
            mutate(altered["saved"]["content"])
            with self.assertRaises((m.j.Rejected, ValueError, KeyError)):
                e.source_window(altered, at)
        stale = copy.deepcopy(src)
        stale["attempt"]["started_at"] -= m.d.MAX_SYNC_AGE_MS+1
        stale["attempt"]["finished_at"] -= m.d.MAX_SYNC_AGE_MS+1
        with self.assertRaises(m.j.Rejected):
            e.source_window(stale, at)
        call(name, "once")
        earlier = at - 1
        self.assertEqual(call(name, "once", fixture=True, at=earlier, code=2)["reason"], "MULTIMODAL_CLOCK_REGRESSED")
        # Real original observer revision invalidates source until resync;
        # resync then exposes revised/late version rather than silently replacing.
        f.append_day(events, DAYS[-1], close="11.50")
        f.save_journal(source, events)
        self.assertEqual(call(name, "once", code=2)["reason"], "SOURCE_CHANGED_SINCE_SYNC")
        m.d.Store(name).sync()
        self.assertEqual(call(name, "once", code=2)["reason"], "REVISED_OR_LATE_SOURCE_REJECTED")
        self.assertEqual(counts(name), (1, 1))


def main():
    global EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-cli", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.fixture_cli:
        return fixture_cli(m.j.loads(args.fixture_cli.read_bytes()))
    EVIDENCE = args.evidence
    if EVIDENCE:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MultimodalTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=True)
        value = dict(schema_version=1, run=RUN, tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                     results=RESULTS, commands=COMMANDS, public_requests=0, true_paid_calls=0,
                     token_and_cost_source="ORIGINAL_AGENT_SQLITE_TST_NOT_CLOUD_BILLING", independent_acceptance="NOT_VERIFIED")
        authority_root = str(m.s.common_root())
        def portable(value):
            if isinstance(value, str):
                return value.replace(str(ROOT), "<checkout>").replace(authority_root, "<authority>").replace(sys.executable, "python")
            if isinstance(value, dict):
                return {key: portable(item) for key, item in value.items()}
            if isinstance(value, list):
                return [portable(item) for item in value]
            return value
        m.c.write(args.evidence / "checks.json", portable(value))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
