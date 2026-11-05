"""Linux-only production launcher. No shell, network client or billing provider."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import signal
import secrets
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import MAX_INPUT, MAX_OUTPUT, MEMORY_MAX, Rejected, loads, require

ROOT = Path(__file__).resolve().parents[2]
UNIT = "stratide-timesfm-cpu.service"
TIMEOUT = 600


def clean_env(threads=2):
    # The installed product selects its state root with this non-secret path;
    # every other arbitrary variable (tokens, keys) remains excluded.
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "PATH", "XDG_RUNTIME_DIR",
                                      "DBUS_SESSION_BUS_ADDRESS", "STRATIDE_STATE_ROOT") if k in os.environ}
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
               HF_HUB_DISABLE_IMPLICIT_TOKEN="1", CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS=str(threads),
               MKL_NUM_THREADS=str(threads), OPENBLAS_NUM_THREADS=str(threads), PYTHONNOUSERSITE="1")
    return env


@contextlib.contextmanager
def lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Rejected("WORKER_BUSY") from None
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)



# ---------------------------------------------------------------------------
# Windows installed-state -> existing WSL2 TimesFM worker
#
# The Windows service keeps the only scheduler, Agent DB, budget gate and Paper
# ledger. This adapter only forwards one already-frozen, numeric worker request
# into the Owner's existing WSL2 venv/model through the unmodified Worker
# isolation. It never sends a token, market raw data, account state or a cloud
# request into WSL.
# ---------------------------------------------------------------------------

_DISTROS = {"at": 0.0, "names": []}


def wsl_settings():
    if os.name != "nt":
        return None
    distribution = os.environ.get("STRATIDE_WSL_DISTRIBUTION", "").strip()
    workspace = os.environ.get("STRATIDE_WSL_WORKSPACE", "").strip()
    if not distribution and not workspace:
        return None
    require(bool(distribution) and bool(workspace), "TIMESFM_WSL_CONFIG_INCOMPLETE")
    require(len(distribution) <= 128 and all(ord(c) >= 32 for c in distribution),
            "TIMESFM_WSL_DISTRIBUTION_INVALID")
    require(workspace.startswith("/") and len(workspace) <= 4096
            and all(ord(c) >= 32 for c in workspace), "TIMESFM_WSL_WORKSPACE_INVALID")
    python = os.environ.get("STRATIDE_WSL_PYTHON", ".venv/bin/python").strip()
    model = os.environ.get("STRATIDE_WSL_MODEL", "models/timesfm-2.5").strip()
    for value in (python, model):
        require(bool(value) and len(value) <= 4096
                and all(ord(c) >= 32 for c in value), "TIMESFM_WSL_PATH_INVALID")
    return dict(distribution=distribution, workspace=workspace, python=python, model=model)


def uses_wsl():
    return os.name == "nt" and wsl_settings() is not None


def _wsl_absolute(workspace, value):
    if value.startswith("/"):
        return posixpath.normpath(value)
    return posixpath.normpath(posixpath.join(workspace, value))


def wsl_paths(settings):
    workspace = posixpath.normpath(settings["workspace"])
    return (_wsl_absolute(workspace, settings["python"]),
            _wsl_absolute(workspace, settings["model"]))


def windows_to_wsl(path):
    resolved = Path(path).resolve()
    drive = resolved.drive
    require(len(drive) == 2 and drive[1] == ":", "TIMESFM_WSL_APP_PATH_UNSUPPORTED")
    return "/mnt/" + drive[0].lower() + resolved.as_posix()[2:]


def code_bundle_sha(directory=None):
    root = Path(directory) if directory is not None else Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def wsl_timeout():
    raw = os.environ.get("STRATIDE_WSL_TIMEOUT", "900")
    require(raw.isdigit() and 1 <= int(raw) <= 3600, "TIMESFM_WSL_TIMEOUT_INVALID")
    return int(raw)


def wsl_distros():
    now = time.monotonic()
    if now - _DISTROS["at"] < 60:
        return list(_DISTROS["names"])
    require(shutil.which("wsl.exe") is not None, "TIMESFM_WSL_UNAVAILABLE")
    try:
        result = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise Rejected("TIMESFM_WSL_UNAVAILABLE") from None
    require(result.returncode == 0, "TIMESFM_WSL_UNAVAILABLE")
    raw = result.stdout
    if raw[:2] == b"\xff\xfe":
        text = raw[2:].decode("utf-16-le", errors="replace")
    elif b"\x00" in raw[:40]:
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    names = [line.strip().lstrip("\ufeff").strip() for line in text.splitlines()]
    names = [name for name in names if name]
    _DISTROS.update(at=now, names=names)
    return names


def _wsl_command(settings, mode):
    require(shutil.which("wsl.exe") is not None, "TIMESFM_WSL_UNAVAILABLE")
    require(settings["distribution"] in wsl_distros(), "TIMESFM_WSL_DISTRO_MISSING")
    python_path, model_path = wsl_paths(settings)
    bridge = windows_to_wsl(Path(__file__).with_name("wsl_bridge.py"))
    app_code = windows_to_wsl(Path(__file__).resolve().parent)
    return ["wsl.exe", "-d", settings["distribution"], "--cd", settings["workspace"],
            "--exec", python_path, "-I", "-B", bridge, "--mode", mode,
            "--app-code", app_code, "--model", model_path]


def _wsl_execute(command, raw, timeout):
    try:
        result = subprocess.run(command, input=raw, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Rejected("TIMESFM_WSL_TIMEOUT") from None
    except (OSError, subprocess.SubprocessError):
        raise Rejected("TIMESFM_WSL_UNAVAILABLE") from None
    if result.returncode in (126, 127):
        raise Rejected("TIMESFM_WSL_VENV_MISSING")
    require(len(result.stdout) <= MAX_OUTPUT + 4096, "TIMESFM_WSL_OUTPUT_LIMIT")
    require(bool(result.stdout.strip()), "TIMESFM_WSL_BRIDGE_FAILED")
    try:
        value = loads(result.stdout)
    except Exception:
        raise Rejected("TIMESFM_WSL_PROTOCOL_INVALID") from None
    require(isinstance(value, dict), "TIMESFM_WSL_PROTOCOL_INVALID")
    if result.returncode != 0:
        code = value.get("error_code")
        require(isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", code) is not None,
                "TIMESFM_WSL_BRIDGE_FAILED")
        raise Rejected(code)
    return value


def wsl_preflight(threads=2):
    settings = wsl_settings()
    require(settings is not None, "TIMESFM_WSL_NOT_CONFIGURED")
    value = _wsl_execute(_wsl_command(settings, "preflight"), b"", 120)
    require(value.get("state") == "READY", value.get("error_code", "TIMESFM_WSL_PREFLIGHT_FAILED"))
    require(value.get("code_bundle_sha256") == code_bundle_sha(), "TIMESFM_WSL_CODE_MISMATCH")
    return value


def wsl_manifest():
    settings = wsl_settings()
    require(settings is not None, "TIMESFM_WSL_NOT_CONFIGURED")
    value = _wsl_execute(_wsl_command(settings, "manifest"), b"", wsl_timeout())
    require(value.get("state") == "READY", value.get("error_code", "TIMESFM_WSL_MANIFEST_FAILED"))
    require(value.get("code_bundle_sha256") == code_bundle_sha(), "TIMESFM_WSL_CODE_MISMATCH")
    require(isinstance(value.get("manifest_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", value["manifest_sha256"]) is not None,
            "TIMESFM_WSL_PROTOCOL_INVALID")
    require(isinstance(value.get("weight_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", value["weight_sha256"]) is not None,
            "TIMESFM_WSL_PROTOCOL_INVALID")
    require(isinstance(value.get("model_revision"), str) and bool(value["model_revision"]),
            "TIMESFM_WSL_PROTOCOL_INVALID")
    value["source"] = "WSL2_TIMESFM_CPU"
    return value


def wsl_run(raw):
    settings = wsl_settings()
    require(settings is not None, "TIMESFM_WSL_NOT_CONFIGURED")
    value = _wsl_execute(_wsl_command(settings, "worker"), raw, wsl_timeout())
    if raw != b"probe":
        require(value.get("request_sha256") == hashlib.sha256(raw).hexdigest(),
                "TIMESFM_WSL_PROTOCOL_INVALID")
    return value


def preflight(threads=2):
    if os.name == "nt":
        return wsl_preflight(threads)
    return command(threads)


def command(threads):
    require(sys.platform == "linux" and all(shutil.which(x) for x in ("systemd-run", "systemctl", "bwrap")), "LINUX_ISOLATION_UNAVAILABLE")
    require(Path("/sys/fs/cgroup/cgroup.controllers").is_file(), "CGROUP_V2_REQUIRED")
    require((ROOT / ".venv/bin/python").is_file(), "PINNED_RUNTIME_NOT_INSTALLED")
    args = ["systemd-run", "--user", "--pipe", "--wait", "--collect", "--quiet", "--unit=" + UNIT,
            "--property=MemoryMax=" + str(MEMORY_MAX), "--property=MemorySwapMax=0",
            "--property=OOMPolicy=kill", "--property=TasksMax=64",
            "--property=CPUQuota=200%", "--property=RuntimeMaxSec=" + str(TIMEOUT),
            "--property=TimeoutStopSec=5", "--property=KillMode=control-group", "--property=NoNewPrivileges=yes",
            shutil.which("bwrap"), "--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts",
            "--die-with-parent", "--new-session", "--cap-drop", "ALL",
            "--clearenv", "--ro-bind", "/usr", "/usr"]
    for lib in ("/lib", "/lib64"):
        if Path(lib).exists():
            args += ["--ro-bind", lib, lib]
    args += ["--ro-bind", str(ROOT / ".venv"), "/runtime", "--ro-bind", str(ROOT / "research/timesfm_cpu"), "/app",
             "--ro-bind", str(ROOT / "models/timesfm-2.5"), "/model", "--ro-bind", "/sys/fs/cgroup", "/sys/fs/cgroup",
             "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--chdir", "/tmp"]
    for k, v in clean_env(threads).items():
        # The Windows state root is meaningless inside the sandbox and is used
        # only by Windows-side helpers, so it never enters the Worker.
        if k not in ("PATH", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "STRATIDE_STATE_ROOT"):
            args += ["--setenv", k, v]
    return args + ["--setenv", "PATH", "/runtime/bin:/usr/bin", "/runtime/bin/python", "-I", "-B", "/app/worker.py"]


def stop():
    require(sys.platform == "linux" and shutil.which("systemctl"), "LINUX_ISOLATION_UNAVAILABLE")
    result = subprocess.run(["systemctl", "--user", "stop", UNIT], env=clean_env(), capture_output=True, timeout=15)
    if result.returncode != 0:
        status=subprocess.run(["systemctl","--user","show",UNIT,"--property=LoadState,ActiveState"],
                              env=clean_env(),capture_output=True,timeout=15)
        fields=dict(line.split("=",1) for line in status.stdout.decode(errors="replace").splitlines() if "=" in line)
        require(status.returncode == 0 and fields.get("LoadState")=="not-found"
                and fields.get("ActiveState")=="inactive","WORKER_STOP_FAILED")
    return dict(state="STOPPED", billing="LOCAL_NO_BILLING")


def communicate_bounded(argv, raw, *, timeout=TIMEOUT + 15, env=None, cleanup=None, heartbeat=False, on_spawn=None):
    """Drain both pipes with bounded storage; kill and reap before returning failure."""
    require(len(raw) <= MAX_INPUT, "WORKER_INPUT_LIMIT")
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env or clean_env(), cwd=ROOT, start_new_session=(os.name != "nt"))
    guard = None
    try:
        if on_spawn:
            guard = on_spawn(process)
    except BaseException:
        process.kill()
        process.wait()
        for stream in (process.stdin,process.stdout,process.stderr):
            stream.close()
        raise
    out, failed = bytearray(), threading.Event()
    def reader(stream, retain, limit):
        size = 0
        while block := stream.read(4096):
            size += len(block)
            if size > limit:
                failed.set()
            elif retain:
                out.extend(block)
    def writer():
        try:
            process.stdin.write(raw + (b"\n" if heartbeat else b""))
            process.stdin.flush()
            while heartbeat and process.poll() is None:
                time.sleep(.5)
                process.stdin.write(b".\n")
                process.stdin.flush()
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    threads = [threading.Thread(target=reader, args=(process.stdout, True, MAX_OUTPUT), daemon=True),
               threading.Thread(target=reader, args=(process.stderr, False, 16384), daemon=True),
               threading.Thread(target=writer, daemon=True)]
    for thread in threads:
        thread.start()
    started = time.monotonic()
    try:
        while process.poll() is None:
            require(not failed.is_set(), "WORKER_OUTPUT_LIMIT")
            require(time.monotonic() - started < timeout, "WORKER_TIMEOUT")
            time.sleep(.02)
        for thread in threads:
            thread.join(timeout=2)
        require(not any(t.is_alive() for t in threads), "WORKER_ORPHAN_PIPE")
        require(not failed.is_set(), "WORKER_OUTPUT_LIMIT")
        if process.returncode != 0 and not out:
            raise Rejected("WORKER_KILLED_OR_OOM" if process.returncode in (-9,137) else "WORKER_EXIT_FAILED")
        value = loads(out)
        require(process.returncode == 0, value.get("error_code", "WORKER_EXIT_FAILED"))
        if guard:
            value.setdefault("metrics",{}).update(guard.snapshot())
        return value
    finally:
        # Always stop the cgroup, including after a killed/failed supervisor.
        try:
            if cleanup:
                cleanup()
        finally:
            # A failed systemctl stop must not skip local kill/reap/pipe closure.
            if guard:
                guard.close()
            if process.poll() is None:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            process.wait(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                # A dead peer can leave a heartbeat buffered on stdin. Preserve
                # the original Worker failure while still closing every pipe.
                with contextlib.suppress(BrokenPipeError):stream.close()
            for thread in threads:
                thread.join(timeout=2)


def run(raw):
    if os.name == "nt":
        return wsl_run(raw)
    threads = 2 if raw == b"probe" else loads(raw)["threads"]
    tag="STRATIDE_TIMESFM_RUN="+secrets.token_hex(16)
    args=command(threads)
    args.insert(1,"--setenv="+tag)
    return communicate_bounded(args, raw, cleanup=lambda:stop_owned(tag), heartbeat=True)


def stop_owned(tag):
    # A rejected second launch must not stop another checkout's existing unit.
    current=subprocess.run(["systemctl","--user","show",UNIT,"--property=Environment","--value"],
                           env=clean_env(),capture_output=True,timeout=15)
    if current.returncode==0 and tag in current.stdout.decode("utf-8",errors="replace").split():
        subprocess.run(["systemctl","--user","stop",UNIT],env=clean_env(),capture_output=True,timeout=15)
