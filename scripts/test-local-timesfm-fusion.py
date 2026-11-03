"""Standalone synthetic checkout only. Loopback is libtest-only; zero paid calls."""
import copy
import contextlib
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import local_fusion as f
import portfolio_research as rp
import candidates as c
sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
import cli as cpu
import model
spec = importlib.util.spec_from_file_location("cpu_test_fixture", ROOT / "scripts/test-timesfm-cpu.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
DRIVER = Path(os.environ["PR19_TEST_DRIVER"])


class Server:
    def __init__(self, scenario="success"):
        outer = self
        self.count = 0
        self.bodies = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                outer.count += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.bodies.append(body)
                if scenario in ("429", "500"):
                    self.send_response(int(scenario)); self.end_headers(); return
                if scenario == "disconnect":
                    self.connection.shutdown(socket.SHUT_RDWR); self.connection.close(); return
                if scenario == "timeout":
                    time.sleep(.6)
                user = json.loads(body["messages"][1]["content"])
                p = user["output_contract"]
                p.update(proposal_id="fixture-cash", strategy_definition="Test whether risk ranking predicts later realized RMS.")
                p["rationale"] = "Only synthetic risk evidence; no return or account evidence."
                if scenario == "weights":
                    p["cash_weight_bps"] = 9999
                if scenario == "instrument":
                    p["candidate_instruments"] = ["999999.SZ"]
                    p["positions"] = [dict(instrument="999999.SZ", target_weight_bps=100)]
                    p["cash_weight_bps"] = 9900
                if scenario == "echo":
                    p["rationale"] = self.headers["Authorization"].removeprefix("Bearer ")
                if scenario == "source":
                    p["source_refs"][0] = "a" * 64
                value = dict(id="test-request-19", model="deepseek-flash", system_fingerprint="fixture-v1",
                             usage=dict(prompt_tokens=300, completion_tokens=500, total_tokens=800),
                             choices=[dict(index=0, finish_reason="stop", message=dict(role="assistant", content=json.dumps(p)))])
                if scenario == "usage":
                    value.pop("usage")
                raw = json.dumps(value).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(raw))); self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
    def __enter__(self):
        self.thread.start()
        return self
    def __exit__(self, *args):
        self.http.shutdown(); self.http.server_close(); self.thread.join()


def driver(name, port=1, action="once", env=None):
    e = dict(os.environ, STRATIDE_PR19_DRIVER="1", STRATIDE_PR19_LOOPBACK_PORT=str(port))
    e.update(env or {})
    p = subprocess.run([str(DRIVER), "--exact", "local_fusion_tests::process_driver", "--nocapture"],
                       input=json.dumps(dict(batch=name, action=action)).encode(), capture_output=True, env=e, timeout=15)
    assert p.returncode == 0, p.stderr.decode()
    line = next(line for line in p.stdout.decode().splitlines() if line.startswith("PR19_RESULT="))
    return json.loads(line.split("=", 1)[1])


@contextlib.contextmanager
def database(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert cpu.common_root() == ROOT, "Run only in a disposable standalone Git checkout"
        assert not (rp.root()/"agent-binding.json").exists(), "Fresh disposable checkout required; never reconfigure an existing Owner Agent"
        cls.owner = ROOT / "state/owner-agent-cny"
        cls.key = ROOT / "state/fixture-key.md"
        cls.key.parent.mkdir(parents=True, exist_ok=True)
        cls.key.write_text("sk-" + "Q" * 32)
        cls.cfg = ROOT / "state/fusion-config.json"
        now = dt.datetime.now(dt.timezone.utc)
        cls.cfg.write_text(json.dumps(dict(version=1, key_file=str(cls.key), grant_version="deepseek-synthetic-fusion-grant-v1",
            synthetic_only=True, provider_terms_reviewed=True, authorized_at=now.isoformat(),
            price_reviewed_at=now.isoformat(), price_valid_until=(now+dt.timedelta(days=1)).isoformat(), max_call_micro=100000)))
        f.bridge("init-cny")
        f.bridge("configure", cls.cfg)
        cpu.bridge("enable")
        cls.counter = 0
        cls.tag = os.urandom(3).hex()

    def batch(self):
        Tests.counter += 1
        name = "rp-test-pr19-" + Tests.tag + "-" + str(Tests.counter)
        desc = cpu.bridge("descriptor")
        plan = dict(batch=name, frozen=cpu.frozen(desc, 1), manifest_sha256="a"*64,
                    code_sha256=desc["code_sha256"], max_context=256, batch_size=1, threads=2)
        # Leave a small wall-clock margin for VM clock synchronization; the
        # production future-data gate is unchanged.
        stamp = dt.datetime.fromisoformat(plan["frozen"]["as_of"].replace("Z", "+00:00"))
        plan["frozen"]["as_of"] = (stamp-dt.timedelta(minutes=5)).isoformat()
        path = cpu.batch_path(name)
        path.mkdir(parents=True)
        (path/"plan.json").write_text(json.dumps(plan))
        prior = cpu.bridge("begin", plan)
        response = fixture.fixture_response(cpu.bridge("project", plan)["worker_request_json"].encode())
        cpu.bridge("complete", dict(id=int(prior["id"]), plan=plan, response=response))
        return name

    def mutate(self, sql, values=()):
        with database(self.owner/"agent.sqlite") as db:
            db.execute(sql, values)

    def calls(self, name):
        with rp.agent_db() as db:
            return list(db.execute("SELECT c.state,c.maximum_micro,c.input_tokens,c.output_tokens FROM calls c JOIN tasks t "
                                   "ON t.id=c.task_id WHERE json_extract(t.input,'$.summary.batch')=?", (name,)))

    def test_01_full_task_projection_archive_inbox_and_readonly_verify(self):
        name = self.batch()
        f.bridge("enable", name)
        with Server() as server:
            value = driver(name, server.http.server_port)
            self.assertEqual(value["status"], "completed")
            self.assertEqual(driver(name, server.http.server_port), value)
            self.assertEqual(server.count, 1)
            body = server.bodies[0]
            self.assertEqual(body["model"], "deepseek-flash")
            self.assertEqual(body["thinking"], dict(type="disabled"))
            self.assertNotIn("tools", body)
            text = json.dumps(body)
            for forbidden in ("close_fen", "observations", "rolling_context", str(self.key), self.key.read_text()):
                self.assertNotIn(forbidden, text)
            self.assertEqual(self.calls(name)[0][:2], ("usage_received", 98304))
            verified = driver(name, action="verify")
            self.assertTrue(verified["verified"])
            self.assertEqual(verified["result"]["research"]["risk_portfolio"]["portfolio"]["cash_weight_bps"], 10000)
            self.assertEqual(verified["result"]["research"]["risk_portfolio"]["receipt"]["verification"], "TEST_LOOPBACK_NOT_REAL_PROVIDER")
        original = f.bridge
        def offline(action, arg=None):
            return driver(arg, action="verify") if action == "verify" else original(action, arg)
        with patch.object(f, "bridge", side_effect=offline):
            run = f.Run(name)
            run.root.mkdir(parents=True, exist_ok=True)
            run.archive(f.task(value["id"]))
            report = run.report()
            self.assertTrue(report["verified"])
            from review import Review
            inbox = Review(name, local_fusion=True).inbox()
            self.assertTrue(inbox)
            wire = run.root/"local-fusion-wire.json"
            original_wire = wire.read_bytes()
            try:
                wire.write_bytes(original_wire+b" ")
                self.assertEqual(driver(name, action="verify")["error_code"], "FUSION_WIRE_AUDIT_CHANGED")
            finally:
                wire.write_bytes(original_wire)
        self.assertEqual(len(self.calls(name)), 1)

    def test_02_bad_parent_status_sha_provider_development_and_cross_authority(self):
        for column, changed in (("status", "failed"), ("status", "cancelled"), ("result", "{}"),
                                ("provider_id", "other-agent"), ("provider_hash", "0"*64)):
            name = self.batch()
            with database(self.owner/"agent.sqlite") as db:
                db.execute("UPDATE tasks SET "+column+"=? WHERE trigger_key=?", (changed, "timesfm-cpu-v1:"+name))
            with self.assertRaises(Exception):
                f.bridge("preflight", name)
            self.assertEqual(self.calls(name), [])
        name = self.batch()
        self.mutate("UPDATE tasks SET result=json_set(result,'$.research.risk_portfolio.receipt.development_only',json('true')) WHERE trigger_key=?",
                    ("timesfm-cpu-v1:"+name,))
        with self.assertRaises(Exception):
            f.bridge("preflight", name)
        self.assertEqual(self.calls(name), [])
        name = self.batch()
        view = f.bridge("status", name)
        f.bridge("enable", name)
        f.bridge("queue", name)
        self.mutate("UPDATE tasks SET input=json_set(input,'$.summary.authority_id',?) WHERE trigger_key LIKE ?",
                    ("0"*64, "local_timesfm_fusion_v1:"+str(view["context"]["parent_task_id"])+":%"))
        result = driver(name)
        self.assertEqual(result.get("reason", result.get("error_code")), "FUSION_CROSS_AGENT_DENIED")
        self.assertEqual(self.calls(name), [])

    def test_03_grant_revocation_and_disabled_gate_do_not_dispatch(self):
        for what in ("disable", "revoke", "structured-purpose"):
            name = self.batch()
            f.bridge("enable", name)
            f.bridge("queue", name)
            path = self.owner/"settings.json"
            original = path.read_bytes()
            try:
                if what == "disable":
                    f.bridge("disable")
                else:
                    s = json.loads(original)
                    m = next(m for m in s["models"] if m["id"] == "ds4.1flash-fusion")
                    if what == "revoke":
                        m["grant"]["revoked"] = True
                    else:
                        m["grant"]["purpose"] = "cloud_structured_research_v1"
                    path.write_text(json.dumps(s))
                with Server() as server:
                    value = driver(name, server.http.server_port)
                    self.assertNotEqual(value.get("status"), "completed")
                    self.assertEqual(server.count, 0)
                    self.assertEqual(self.calls(name), [])
            finally:
                path.write_bytes(original)

    def test_04_http_and_output_faults_hold_maximum_and_never_repeat(self):
        for scenario in ("429", "500", "timeout", "disconnect", "usage", "weights", "instrument", "source", "echo"):
            name = self.batch()
            f.bridge("enable", name)
            with Server(scenario) as server:
                value = driver(name, server.http.server_port)
                self.assertEqual(value["status"], "outcome_uncertain", scenario)
                self.assertNotIn(self.key.read_text(), json.dumps(value))
                self.assertEqual(driver(name, server.http.server_port), value)
                self.assertEqual(server.count, 1, scenario)
                self.assertEqual(self.calls(name)[0][:2], ("outcome_uncertain", 98304))
                wire = rp.root()/name/"local-fusion-wire.json"
                if scenario == "echo":
                    self.assertFalse(wire.exists())
                elif wire.exists():
                    self.assertNotIn(self.key.read_text().encode(), wire.read_bytes())
                with self.assertRaises(Exception):
                    f.bridge("enable", name)
            self.assertEqual(len(self.calls(name)), 1)

    def test_05_final_dispatch_revocation_releases_only_confirmed_not_sent(self):
        name = self.batch()
        f.bridge("enable", name)
        folder = rp.root()/name
        folder.mkdir(parents=True)
        fault = json.dumps(dict(point="after_reserve", batch=name, behavior="wait"))
        with Server() as server:
            env = dict(os.environ, STRATIDE_PR19_DRIVER="1", STRATIDE_PR19_LOOPBACK_PORT=str(server.http.server_port),
                       STRATIDE_RP_TEST_FAULT=fault)
            p = subprocess.Popen([str(DRIVER), "--exact", "local_fusion_tests::process_driver", "--nocapture"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            p.stdin.write(json.dumps(dict(batch=name)).encode()); p.stdin.close(); p.stdin = None
            end = time.monotonic()+10
            while not (folder/"test-marker").exists() and time.monotonic() < end:
                time.sleep(.01)
            self.assertTrue((folder/"test-marker").exists())
            f.bridge("disable")
            (folder/"test-release").write_text("continue")
            out, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0, err)
            self.assertEqual(server.count, 0)
            self.assertEqual(self.calls(name)[0][0], "no_charge")

    def test_06_init_cannot_relabel_TST_or_reset_history(self):
        with rp.agent_db() as db:
            count = db.execute("SELECT count(*) FROM calls").fetchone()[0]
        f.bridge("init-cny")
        with rp.agent_db() as db:
            self.assertEqual(count, db.execute("SELECT count(*) FROM calls").fetchone()[0])
        self.assertEqual(f.bridge("budget")["currency"], "CNY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
