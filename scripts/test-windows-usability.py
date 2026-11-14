"""Isolated Windows launcher/daemon acceptance with fake Python actions and no provider calls.

Pass the compiled bin directory (source) or dist/app (packaged). The fixture
creates its own runtime home and replaces the helper scripts inside a temp app.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from textwrap import indent
import time
import urllib.error
import urllib.request

WATCH = """
import json, os, pathlib, subprocess, sys, time
data = pathlib.Path(os.environ["STRATIDE_STATE_ROOT"])
action = sys.argv[2]
if action in ("watch", "backfill"):
    leaf = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    marker = data / (action + ".json")
    pending = marker.with_suffix(".new")
    pending.write_text(json.dumps(dict(pid=os.getpid(), leaf=leaf.pid,
                                       workspace=os.environ.get("STRATIDE_WSL_WORKSPACE"))))
    pending.replace(marker)
    if action == "watch":
        time.sleep(90)
    progress = data / "fixture-progress.new"
    progress.write_text(json.dumps(dict(phase="RUNNING", sessions_ready=30, remaining=54)))
    progress.replace(data / "backfill.progress.json")
    while not (data / "release-backfill").exists():
        time.sleep(.05)
    if (data / "fail-backfill").exists():
        raise SystemExit(2)
elif action == "status":
    print(json.dumps(dict(sessions_ready=84, gaps=[], coverage_complete=True)))
else:
    print("{}")
"""

PROBE = """
import json, os, pathlib
reason = (pathlib.Path(os.environ["STRATIDE_STATE_ROOT"]) / "probe-error").read_text()
print(json.dumps(dict(state="BLOCKED", error_code=reason)))
raise SystemExit(2)
"""


def wait_for(check, label, seconds=15):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            value = check()
            if value:
                return value
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(.10)
    raise AssertionError(label)


def alive(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        assert ctypes.get_last_error() == 87, "cannot inspect fixture process"
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


def run(binaries, root):
    app = root / "app"
    home = root / "home"
    data = home / "data"
    scripts = app / "scripts"
    dashboard = app / "dashboard"
    for directory in (scripts, dashboard, home / "runtime"):
        directory.mkdir(parents=True, exist_ok=True)
    for name in ("stratide-launcher.exe", "stratided.exe", "VERSION", "BUILD_INFO.json"):
        if (binaries / name).is_file():
            shutil.copyfile(binaries / name, app / name)
    if (binaries / "dashboard/index.html").is_file():
        shutil.copytree(binaries / "dashboard", dashboard, dirs_exist_ok=True)
    else:
        (dashboard / "assets").mkdir()
        (dashboard / "assets/app.js").touch()
        (dashboard / "assets/app.css").touch()
        (dashboard / "index.html").write_text("<!doctype html><title>Fixture</title>", encoding="utf-8")
    for script, fake_path, body in (
        ("eod-operator.py", "research/eod_operator.py", WATCH),
        ("timesfm-cpu.py", "research/timesfm_cpu/cli.py", PROBE),
    ):
        wrapper = binaries / "scripts" / script
        shutil.copyfile(wrapper if wrapper.is_file() else Path(__file__).with_name(script), scripts / script)
        fake = app / fake_path
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_text("def main():\n" + indent(body.strip() + "\n", "    "), encoding="utf-8")
    shutil.copyfile(Path(os.environ["SystemRoot"]) / "System32/where.exe", app / "wsl.exe")
    if (binaries / "runtime/python/python.exe").is_file():
        shutil.copytree(binaries / "runtime/python", app / "runtime/python")
        python = app / "runtime/python/python.exe"
    else:
        python = Path(sys.executable)
    warehouse = data / "state/historical-warehouse/market-eod/warehouse.sqlite"
    warehouse.parent.mkdir(parents=True)
    warehouse.touch()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    config = dict(schema_version=1, port=port, data_root=str(data), python=str(python),
                  wsl=dict(distribution="Fixture", workspace="/before"))
    (home / "runtime.json").write_text(json.dumps(config), encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("STRATIDE_", "PYTHON"))}
    env.update(STRATIDE_APP_DIR=str(app), STRATIDE_HOME=str(home),
               PATH=str(app) + os.pathsep + env["PATH"])
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(path, body=None, status=200):
        request = urllib.request.Request(origin + "/api/" + path, headers={
            "Origin": origin, "Content-Type": "application/json",
        }, data=None if body is None else json.dumps(body).encode())
        try:
            response = http.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            value = json.load(response)
            assert response.status == status, (path, response.status, value)
            return value["data"] if status == 200 else value["error"]["code"]

    def watch():
        return json.loads((data / "watch.json").read_text())

    def backfill_state():
        return call("runtime/market", {"action": "backfill-state"})

    def budget(day, month, confirmed=False, status=200):
        return call("agent/budget", dict(daily_limit_micro=str(day), monthly_limit_micro=str(month),
                                         confirm_below_committed=confirmed), status)

    supervisor = subprocess.Popen([str(app / "stratide-launcher.exe"), "--background", "--quiet"],
                                  cwd=app, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    stop = home / "runtime/stop.request"
    try:
        first = wait_for(watch, "initial watch did not start")
        wait_for(lambda: call("health"), "isolated dashboard did not start")
        assert first["workspace"] == "/before" and alive(first["leaf"])
        if (app / "BUILD_INFO.json").is_file():
            info = json.loads((app / "BUILD_INFO.json").read_text(encoding="utf-8-sig"))
            assert call("runtime/status")["build"]["commit"] == info["commit"]
            print("PASS packaged BUILD_INFO projection", info["commit"], flush=True)

        accepted = call("runtime/market", {"action": "backfill"})
        assert accepted["state"] == "QUEUED"
        wait_for(lambda: backfill_state()["progress"].get("sessions_ready") == 30, "backfill progress missing")
        batch = json.loads((data / "backfill.json").read_text())
        assert not alive(first["leaf"]), "watch descendant survived start backfill"
        assert backfill_state()["phase"] == "RUNNING"
        print("PASS queued/running progress and watch tree stopped for backfill", flush=True)

        assert call("runtime/wsl", dict(distribution="Fixture", workspace="/after"))["watch_restart"]
        assert not call("runtime/wsl", dict(distribution="Fixture", workspace="/after"))["watch_restart"]
        (data / "release-backfill").touch()
        wait_for(lambda: backfill_state()["phase"] == "VERIFYING", "batch exit did not await verification")
        assert not alive(batch["leaf"]), "backfill descendant survived batch exit"
        assert call("runtime/market", {"action": "status"})["coverage_complete"]
        second = wait_for(lambda: watch() if watch()["workspace"] == "/after" else None, "saved WSL config not in new watch")

        config["wsl"]["workspace"] = "/without-notice"
        pending = home / "runtime.new"
        pending.write_text(json.dumps(config), encoding="utf-8")
        pending.replace(home / "runtime.json")
        third = wait_for(lambda: watch() if watch()["workspace"] == "/without-notice" else None, "watch missed durable WSL change")
        assert not alive(second["leaf"]), "watch descendant survived WSL change"
        print("PASS latest saved WSL config, including update without restart notice", flush=True)

        probe = data / "state/timesfm-wsl-probe.json"
        probe.write_text(json.dumps(dict(schema_version=1, state="READY", reason=None,
                         fingerprint="Fixture|/without-notice|.venv/bin/python|models/timesfm-2.5",
                         probed_at=datetime.now(timezone.utc).isoformat())), encoding="utf-8")
        before = probe.read_bytes()
        (data / "probe-error").write_text("WORKER_BUSY")
        busy = call("runtime/wsl-probe", {})
        assert busy["state"] == "BUSY" and not busy["persisted"] and probe.read_bytes() == before
        (data / "probe-error").write_text("TIMESFM_WSL_MODEL_MISSING")
        blocked = call("runtime/wsl-probe", {})
        assert blocked["state"] == "BLOCKED" and blocked["persisted"]
        assert json.loads(probe.read_bytes())["reason"] == "TIMESFM_WSL_MODEL_MISSING"
        print("PASS busy probe preserved READY evidence and real failure persisted", flush=True)

        (data / "fail-backfill").touch()
        call("runtime/market", {"action": "backfill"})
        wait_for(lambda: backfill_state()["phase"] == "FAILED", "failed backfill exit not visible")
        fourth = wait_for(lambda: watch() if watch()["pid"] != third["pid"] else None, "watch did not resume after failure")
        assert budget(5_000_000, 100_000_000)["budget"]["daily_limit_micro"] == "5000000"
        assert budget(10_000_000, 100_000_000, status=409) == "MARKET_SHARED_BUDGET_CAP_REQUIRED"
        assert budget(5_000_000, 101_000_000, status=409) == "MARKET_SHARED_BUDGET_CAP_REQUIRED"
        assert call("agent/status")["budget"]["daily_limit_micro"] == "5000000"
        assert budget(4_000_000, 50_000_000)["budget"]["daily_limit_micro"] == "4000000"
        assert call("agent/status")["budget"]["monthly_limit_micro"] == "50000000"
        print("PASS failed backfill and attached budget acceptance/rejection", flush=True)

        last_batch = json.loads((data / "backfill.json").read_text())["pid"]
        (data / "release-backfill").unlink()
        call("runtime/market", {"action": "backfill"})
        wait_for(lambda: backfill_state()["progress"].get("sessions_ready") == 30, "last batch did not run")
        active = json.loads((data / "backfill.json").read_text())
        assert active["pid"] != last_batch and alive(active["leaf"])
        stop.write_text("{}")
        assert supervisor.wait(15) == 0
        assert not alive(fourth["leaf"]), "watch descendant survived the last backfill"
        assert not alive(active["leaf"]), "backfill descendant survived owner stop"
        assert json.loads((data / "backfill.progress.json").read_text())["reason"] == "BACKFILL_INTERRUPTED"
        print("PASS controlled stop", flush=True)
    except Exception:
        for log in sorted((home / "logs").glob("*.log")):
            tail = log.read_bytes()[-1200:].decode("utf-8", errors="replace").strip()
            if tail:
                print(log.name, tail, file=sys.stderr)
        raise
    finally:
        if supervisor.poll() is None:
            stop.write_text("{}")
            try:
                supervisor.wait(15)
            except subprocess.TimeoutExpired:
                supervisor.kill()
                supervisor.wait(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binaries", type=Path)
    args = parser.parse_args()
    assert os.name == "nt"
    with tempfile.TemporaryDirectory(prefix="stratide-usability-") as temp:
        run(args.binaries.resolve(), Path(temp))
