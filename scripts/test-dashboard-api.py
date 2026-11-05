#!/usr/bin/env python3
"""Dashboard/Agent API integration checks for the Stratide UI contract.

Default mode is READ-ONLY: only GET requests are sent to an existing local
instance. Writes are performed only in --launch-fixture mode, against a
throw-away tempdata instance created from the given exe.

Usage (read-only against the running real install):
    python scripts/test-dashboard-api.py --base-url http://127.0.0.1:8710

Usage (cross-built exe, isolated fixture, includes write checks):
    python scripts/test-dashboard-api.py --launch-fixture \
        --exe F:/Desktop/Documents/Codex/Stratide/issue85-worktree/dist/app/stratided.exe \
        --assets-dir apps/dashboard/dist --expect-new-fields

Exit code: 0 = all checks pass (skips allowed), 1 = failure.
No third-party dependencies; stdlib only. Never calls a Provider: the fixture
uses the deterministic "fake" model committed by --agent-init-fake.
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

FAILURES = []
CHECKS = 0
SKIPS = 0


def check(ok, label, detail=""):
    global CHECKS
    CHECKS += 1
    if ok:
        print("PASS  " + label)
    else:
        msg = label if detail == "" else label + " :: " + str(detail)
        print("FAIL  " + msg)
        FAILURES.append(msg)


def skip(label, why):
    global SKIPS
    SKIPS += 1
    print("SKIP  " + label + " (" + why + ")")


def get_json(url, timeout=10):
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(body)
        except ValueError:
            return error.code, {"raw": body}


def post_json(url, body, timeout=15):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": base_origin(url),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(body)
        except ValueError:
            return error.code, {"raw": body}


def base_origin(url):
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return parts.scheme + "://" + parts.netloc


def envelope_ok(payload):
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("api_version"), int)
        and "data" in payload
        and "error" in payload
    )


def data_of(payload):
    return None if not isinstance(payload, dict) else payload.get("data")


def wait_health(base_url, timeout_seconds=25):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        try:
            status, payload = get_json(base_url + "/api/health", timeout=3)
            if status == 200 and envelope_ok(payload) and (data_of(payload) or {}).get("service") == "online":
                return True
            last = status
        except (urllib.error.URLError, ConnectionError, OSError) as error:
            last = str(error)
        time.sleep(0.4)
    print("health wait failed: " + str(last))
    return False


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Fixture:
    def __init__(self, exe, assets_dir, keep, fixture_root=None):
        self.exe = os.path.abspath(exe)
        self.assets_dir = os.path.abspath(assets_dir)
        self.keep = keep
        # The packaged unsigned exe may be denied writes under %TEMP% by host
        # policy, so default the throw-away instance to the gitignored state/
        # directory next to the repo (never the real install data root).
        if fixture_root is None:
            # Prefer the workspace-root state/ dir (gitignored, not repo, and
            # writable by the packaged exe). Fall back to the repo state/ dir.
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            fixture_root = os.path.join(os.path.dirname(repo_root), "state")
            if not os.path.isdir(fixture_root):
                fixture_root = os.path.join(repo_root, "state")
        os.makedirs(fixture_root, exist_ok=True)
        self.root = tempfile.mkdtemp(prefix="api-fixture-", dir=fixture_root)
        self.agent_dir = os.path.join(self.root, "agent")
        self.home = os.path.join(self.root, "runtime-home")
        self.data_root = os.path.join(self.root, "data")
        self.port = free_port()
        self.base_url = "http://127.0.0.1:" + str(self.port)
        self.proc = None
        self.stdout = None
        self.stderr = None

    def setup(self):
        os.makedirs(self.agent_dir, exist_ok=True)
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.data_root, exist_ok=True)
        # The supervisor normally creates these; the managed runtime API expects
        # the layout directories to exist before writing setup markers.
        os.makedirs(os.path.join(self.home, "runtime"), exist_ok=True)
        os.makedirs(os.path.join(self.home, "logs"), exist_ok=True)
        init = subprocess.run(
            [self.exe, "--agent-init-fake", self.agent_dir],
            cwd=os.path.dirname(self.exe),
            capture_output=True,
            timeout=120,
        )
        if init.returncode != 0:
            raise RuntimeError("--agent-init-fake failed: " + init.stderr.decode("utf-8", "replace"))
        config = {
            "schema_version": 1,
            "port": self.port,
            "data_root": self.data_root,
            "python": None,
            "wsl": None,
        }
        with open(os.path.join(self.home, "runtime.json"), "w", encoding="utf-8") as handle:
            json.dump(config, handle)
        self.stdout = open(os.path.join(self.root, "server.out.log"), "w", encoding="utf-8")
        self.stderr = open(os.path.join(self.root, "server.err.log"), "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [
                self.exe,
                "--assets-dir", self.assets_dir,
                "--port", str(self.port),
                "--agent-dir", self.agent_dir,
                "--runtime-home", self.home,
            ],
            cwd=os.path.dirname(self.exe),
            stdout=self.stdout,
            stderr=self.stderr,
        )
        if not wait_health(self.base_url):
            raise RuntimeError("fixture server did not become healthy; see " + self.stderr.name)

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        for handle in (self.stdout, self.stderr):
            if handle is not None:
                handle.close()
        if not self.keep:
            shutil.rmtree(self.root, ignore_errors=True)


def check_runtime_status(base_url, expect_new):
    url = base_url + "/api/runtime/status"
    try:
        status, payload = get_json(url, timeout=60)
    except (urllib.error.URLError, OSError) as error:
        check(False, "GET /api/runtime/status", error)
        return
    check(status == 200 and envelope_ok(payload), "GET /api/runtime/status returns v1 envelope", status)
    data = data_of(payload) or {}
    for key in ("managed", "product_version", "setup_complete", "supervisor", "service", "dependencies", "log_tail"):
        check(key in data, "runtime.status has " + key)
    deps = data.get("dependencies") or {}
    check(
        set(deps.keys()) == {"python", "wsl", "timesfm", "tushare_credential", "market_eod", "paper_account", "agent"},
        "runtime.status dependencies list is stable",
        sorted(deps.keys()),
    )
    if expect_new:
        build = data.get("build")
        check(isinstance(build, dict), "runtime.status.build is an object", build)
        if isinstance(build, dict):
            check(set(build.keys()) >= {"version", "commit", "built_at"}, "runtime.status.build has version/commit/built_at", build)
        check(data.get("repo_url") == "https://github.com/handFOOLed/Stratide", "runtime.status.repo_url", data.get("repo_url"))
        check(data.get("issues_url") == "https://github.com/handFOOLed/Stratide/issues", "runtime.status.issues_url", data.get("issues_url"))
    else:
        skip("runtime build/repo/issues fields", "old binary; run with --expect-new-fields after cross-build")


def check_agent_status(base_url, expect_new):
    try:
        status, payload = get_json(base_url + "/api/agent/status")
    except (urllib.error.URLError, OSError) as error:
        check(False, "GET /api/agent/status", error)
        return None
    check(status == 200 and envelope_ok(payload), "GET /api/agent/status returns v1 envelope", status)
    data = data_of(payload)
    if not isinstance(data, dict):
        check(False, "agent.status data is object", status)
        return None
    for key in ("service", "paused", "worker_error", "models", "budget", "eod", "input"):
        check(key in data, "agent.status has " + key)
    if expect_new:
        check("worker_error_text" in data, "agent.status.worker_error_text present")
        eod = data.get("eod") or {}
        latest = eod.get("latest")
        if latest is None:
            skip("agent.status.eod.latest.reason_text", "no EOD task yet")
        else:
            check("reason_text" in latest, "agent.status.eod.latest.reason_text present", latest)
        models = data.get("models") or []
        if models:
            check("authorization_text" in models[0], "agent.status.models[0].authorization_text present", models[0])
        else:
            skip("agent.status.models[].authorization_text", "no models configured")
    else:
        skip("agent.status reason_text fields", "old binary; run with --expect-new-fields")
    return data


def check_tasks(base_url, expect_new):
    try:
        status, payload = get_json(base_url + "/api/agent/tasks")
    except (urllib.error.URLError, OSError) as error:
        check(False, "GET /api/agent/tasks", error)
        return []
    check(status == 200 and envelope_ok(payload), "GET /api/agent/tasks returns v1 envelope", status)
    data = data_of(payload) or {}
    tasks = data.get("tasks")
    check(isinstance(tasks, list), "agent.tasks.tasks is list")
    if not isinstance(tasks, list):
        return []
    for task in tasks:
        for key in ("id", "name", "status", "reason", "provider_id", "conclusion", "calls", "retryable"):
            check(key in task, "task " + str(task.get("id")) + " has " + key)
        if expect_new:
            check("reason_text" in task, "task " + str(task.get("id")) + ".reason_text present")
            check("kind" in task, "task " + str(task.get("id")) + ".kind present")
            check(task.get("kind") in ("research_task", "research_blocked_notice"), "task kind is research_task|research_blocked_notice", task.get("kind"))
        break  # one representative task is enough for the list contract
    if expect_new and tasks:
        task_id = tasks[0].get("id")
        try:
            detail_status, detail_payload = get_json(base_url + "/api/agent/tasks/" + str(task_id))
        except (urllib.error.URLError, OSError) as error:
            check(False, "GET /api/agent/tasks/<id>", error)
            return tasks
        check(detail_status == 200 and envelope_ok(detail_payload), "GET /api/agent/tasks/<id> returns v1 envelope", detail_status)
        detail = data_of(detail_payload) or {}
        check(detail.get("id") == task_id, "task detail id matches", detail.get("id"))
        check("reason_text" in detail, "task detail reason_text present")
        check(detail.get("kind") in ("research_task", "research_blocked_notice"), "task detail kind", detail.get("kind"))
        calls = detail.get("calls")
        check(isinstance(calls, list), "task detail calls is list")
        for call in calls if isinstance(calls, list) else []:
            check("reason_text" in call, "task call " + str(call.get("id")) + ".reason_text present")
    elif not expect_new:
        skip("agent.tasks reason_text/kind", "old binary")
    return tasks


def check_inbox(base_url, expect_new):
    try:
        status, payload = get_json(base_url + "/api/agent/inbox")
    except (urllib.error.URLError, OSError) as error:
        check(False, "GET /api/agent/inbox", error)
        return None
    check(status == 200 and envelope_ok(payload), "GET /api/agent/inbox returns v1 envelope", status)
    data = data_of(payload) or {}
    notifications = data.get("notifications")
    check(isinstance(notifications, list), "inbox.notifications is list")
    if expect_new:
        check("unread_count" in data, "inbox.unread_count present")
        if isinstance(data.get("unread_count"), int):
            expected = sum(1 for item in notifications if isinstance(item, dict) and item.get("read") is False)
            check(data["unread_count"] >= expected, "inbox.unread_count covers at least current page unread", (data["unread_count"], expected))
        for item in (notifications if isinstance(notifications, list) else []):
            for key in ("name", "conclusion", "provider_id", "kind"):
                check(key in item, "notification " + str(item.get("id")) + " has " + key)
            check(item.get("kind") in ("research_task", "research_blocked_notice"), "notification kind is research_task|research_blocked_notice", item.get("kind"))
            break
    else:
        skip("inbox name/conclusion/provider_id/kind/unread_count", "old binary")
    return data


def check_paper_envelopes(base_url):
    path = "/api/health"
    try:
        status, payload = get_json(base_url + path)
    except (urllib.error.URLError, OSError) as error:
        check(False, "GET " + path, error)
        return
    check(status == 200 and envelope_ok(payload), "GET " + path + " returns v1 envelope", status)
    data = data_of(payload) or {}
    check(data.get("paper_only") is True, "health.paper_only is true")
    check("service" in data, "health has service")
    snapshot = payload.get("snapshot")
    if snapshot is None:
        skip("snapshot metadata", "no report/ledger configured on this instance")
    else:
        for key in ("snapshot_id", "market_freshness"):
            check(key in snapshot, "snapshot has " + key)
        check("as_of" in snapshot and "last_day" in snapshot, "snapshot has as_of/last_day")


def wait_for_completed_task(base_url, task_id, timeout_seconds=20):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        status, payload = get_json(base_url + "/api/agent/tasks/" + str(task_id), timeout=5)
        detail = data_of(payload) or {}
        last = detail.get("status")
        if last in ("completed", "failed", "blocked", "outcome_uncertain", "cancelled"):
            return last
        time.sleep(0.5)
    return last


def check_writes(base_url, expect_new):
    """Write checks are only called for the throw-away fixture instance."""
    print("-- write checks on fixture --")
    # 1) Create a deterministic local fake research task (no cloud).
    body = {
        "name": "API contract probe",
        "goal": "Verify reason_text/notification fields without any paid call.",
        "scope": "owner_task",
        "start_day": "2026-11-05",
        "end_day": "2026-11-05",
        "task_budget_micro": None,
    }
    status, payload = post_json(base_url + "/api/agent/tasks", body)
    check(status == 200 and envelope_ok(payload), "POST /api/agent/tasks enqueues fake task", (status, payload.get("error")))
    created = data_of(payload) or {}
    task_id = created.get("id")
    check(task_id is not None, "created task has id")
    if task_id is None:
        return
    final = wait_for_completed_task(base_url, task_id)
    check(final in ("completed", "failed"), "fixture fake task finished", final)

    status, payload = get_json(base_url + "/api/agent/tasks/" + str(task_id))
    detail = data_of(payload) or {}
    if expect_new:
        check("reason_text" in detail, "detail.reason_text present after completion", detail.get("reason"))
        calls = detail.get("calls") or []
        check(len(calls) >= 1, "fake task recorded at least one call")
        for call in calls:
            check("reason_text" in call, "call.reason_text present", call.get("state"))
    status, payload = get_json(base_url + "/api/agent/inbox")
    inbox = data_of(payload) or {}
    notifications = inbox.get("notifications") or []
    match = next((item for item in notifications if item.get("id") == task_id), None)
    check(match is not None, "finished task appears in inbox", task_id)
    if match is not None and expect_new:
        check(match.get("provider_id") == "fake", "inbox notification provider_id", match.get("provider_id"))
        check(match.get("kind") == "research_task", "inbox notification kind", match.get("kind"))
        check(match.get("name") == body["name"], "inbox notification name matches task request", match.get("name"))
        check(isinstance(match.get("conclusion"), str) and match["conclusion"] != "", "inbox notification conclusion saved", match.get("conclusion"))
    # 2) Per-item read must flip read + reduce unread_count.
    if match is not None:
        before = inbox.get("unread_count")
        status, payload = post_json(base_url + "/api/agent/read-notifications", {"ids": [str(task_id)]})
        check(status == 200 and envelope_ok(payload), "POST read-notifications marks one item", (status, payload.get("error")))
        status, payload = get_json(base_url + "/api/agent/inbox")
        after = data_of(payload) or {}
        item = next((x for x in (after.get("notifications") or []) if x.get("id") == task_id), None)
        check(item is not None and item.get("read") is True, "notification read flag flipped")
        if expect_new and isinstance(before, int) and isinstance(after.get("unread_count"), int):
            check(after["unread_count"] == before - 1, "unread_count decreased by one", (before, after["unread_count"]))

    # 3) setup-complete revoke then re-complete (no financial effect; new contract only).
    if expect_new:
        status, payload = post_json(base_url + "/api/runtime/setup-complete", {"completed": False})
        check(status == 200 and envelope_ok(payload), "POST setup-complete {completed:false} accepted", (status, payload.get("error")))
        setup = data_of(payload) or {}
        check(setup.get("setup_complete") is False, "setup-complete revoke returns setup_complete=false", setup)
        status, payload = get_json(base_url + "/api/runtime/status")
        check((data_of(payload) or {}).get("setup_complete") is False, "runtime.status reflects revoked setup marker")
        status, payload = post_json(base_url + "/api/runtime/setup-complete", {})
        check(status == 200 and envelope_ok(payload), "POST setup-complete {} accepted")
        check((data_of(payload) or {}).get("setup_complete") is True, "setup-complete restore returns setup_complete=true")
    else:
        skip("setup-complete revoke contract", "old binary")

    # 4) Budget update with identical limits (no semantic change), only if endpoint exists.
    status, payload = post_json(
        base_url + "/api/agent/budget",
        {"daily_limit_micro": "1000000", "monthly_limit_micro": "10000000", "confirm_below_committed": False},
    )
    if status == 404:
        skip("POST /api/agent/budget", "budget endpoint not implemented yet")
    else:
        check(status == 200 and envelope_ok(payload), "POST /api/agent/budget accepts same limits", (status, payload.get("error")))
        budget = (data_of(payload) or {}).get("budget") or {}
        check(budget.get("daily_limit_micro") == "1000000", "budget response daily_limit_micro", budget.get("daily_limit_micro"))
        status, payload = get_json(base_url + "/api/agent/status")
        current = (data_of(payload) or {}).get("budget") or {}
        check(current.get("daily_limit_micro") == "1000000", "agent.status budget reflects update", current.get("daily_limit_micro"))
        # Failure semantics: daily > monthly must be rejected and must not write.
        status, payload = post_json(
            base_url + "/api/agent/budget",
            {"daily_limit_micro": "2000000", "monthly_limit_micro": "1000", "confirm_below_committed": False},
        )
        check(status == 400 and (payload.get("error") or {}).get("code") == "BUDGET_INPUT_INVALID", "budget daily>monthly rejected 400", (status, payload.get("error")))
        status, payload = get_json(base_url + "/api/agent/status")
        unchanged = (data_of(payload) or {}).get("budget") or {}
        check(unchanged.get("monthly_limit_micro") == "10000000", "rejected budget did not modify settings", unchanged.get("monthly_limit_micro"))
        # Currency/timezone identity is immutable after first configuration.
        status, payload = post_json(
            base_url + "/api/agent/budget",
            {"daily_limit_micro": "1000000", "monthly_limit_micro": "10000000", "confirm_below_committed": False, "currency": "USD"},
        )
        check(status == 409 and (payload.get("error") or {}).get("code") == "BUDGET_CURRENCY_TIMEZONE_IMMUTABLE", "budget currency change rejected 409", (status, payload.get("error")))


def main(argv):
    parser = argparse.ArgumentParser(description="Stratide Dashboard/Agent API contract checks")
    parser.add_argument("--base-url", default="http://127.0.0.1:8710", help="existing instance (read-only)")
    parser.add_argument("--launch-fixture", action="store_true", help="launch a temp instance from --exe and run write checks")
    parser.add_argument("--exe", default="F:/Desktop/Documents/Codex/Stratide/issue85-worktree/dist/app/stratided.exe")
    parser.add_argument("--assets-dir", default="apps/dashboard/dist")
    parser.add_argument("--expect-new-fields", action="store_true", help="assert task-9/task-12 backend fields exist")
    parser.add_argument("--keep", action="store_true", help="keep fixture temp dir for diagnosis")
    parser.add_argument("--fixture-root", default=None, help="parent dir for the throw-away fixture (default: <workspace>/state)")
    args = parser.parse_args(argv)

    fixture = None
    try:
        if args.launch_fixture:
            fixture = Fixture(args.exe, args.assets_dir, args.keep, args.fixture_root)
            try:
                fixture.setup()
            except Exception as error:  # noqa: BLE001 - report setup failure and exit non-zero
                check(False, "launch fixture", error)
                return 1
            base_url = fixture.base_url
        else:
            base_url = args.base_url.rstrip("/")

        if not wait_health(base_url):
            return 1
        print("target: " + base_url + (" (fixture)" if fixture is not None else " (existing, read-only)"))
        check_paper_envelopes(base_url)
        check_runtime_status(base_url, args.expect_new_fields)
        check_agent_status(base_url, args.expect_new_fields)
        check_tasks(base_url, args.expect_new_fields)
        check_inbox(base_url, args.expect_new_fields)
        if fixture is not None:
            check_writes(base_url, args.expect_new_fields)
        else:
            skip("write checks", "read-only mode; use --launch-fixture")
    finally:
        if fixture is not None:
            fixture.stop()

    print("")
    print("checks=%d failures=%d skips=%d" % (CHECKS, len(FAILURES), SKIPS))
    if FAILURES:
        print("FAILED:")
        for item in FAILURES:
            print("  - " + item)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
