"""Bounded Windows->WSL2 bridge for the existing TimesFM CPU Worker.

This file runs *inside* WSL with the Owner's existing venv. It copies the
installed application's TimesFM code into a per-run staging root, symlinks the
existing venv and model into that root, and then calls the unmodified
research/timesfm_cpu/runtime.py from the staging copy. It never downloads a
model, never touches the Windows Agent DB and never calls a cloud provider.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


class BridgeError(Exception):
    pass


def require(ok, code):
    if not ok:
        raise BridgeError(code)


def code_bundle_sha(code_dir):
    digest = hashlib.sha256()
    for path in sorted(Path(code_dir).glob("*.py")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def prepare(app_code, model_dir):
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "stratide" / "timesfm"
    cache.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="run-", dir=cache))
    code = stage / "research" / "timesfm_cpu"
    code.parent.mkdir(parents=True)
    shutil.copytree(app_code, code)
    model_target = stage / "models" / "timesfm-2.5"
    model_target.mkdir(parents=True)
    source = Path(model_dir).resolve()
    require(source.is_dir() and not source.is_symlink() and not model_dir.is_symlink(),
            "TIMESFM_WSL_MODEL_MISSING")
    try:
        for entry in source.iterdir():
            if entry.is_file() and not entry.is_symlink():
                os.link(entry, model_target / entry.name)
    except OSError:
        raise BridgeError("TIMESFM_WSL_MODEL_LINK_UNSUPPORTED") from None
    os.symlink(Path(sys.prefix), stage / ".venv")
    return stage


def load_runtime(stage):
    sys.path.insert(0, str(stage / "research" / "timesfm_cpu"))
    import runtime
    runtime.ROOT = stage
    return runtime


def load_model(stage):
    sys.path.insert(0, str(stage / "research" / "timesfm_cpu"))
    import model
    return model


def emit(value, code=0):
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preflight", "manifest", "worker"), required=True)
    parser.add_argument("--app-code", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()))
    os.environ.setdefault("XDG_RUNTIME_DIR", str(runtime_dir))
    bus = runtime_dir / "bus"
    if bus.exists():
        os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=" + str(bus))
    stage = None
    try:
        app_code = Path(args.app_code)
        model_dir = Path(args.model)
        require(app_code.is_dir() and not app_code.is_symlink(), "TIMESFM_WSL_APP_CODE_MISSING")
        require(model_dir.is_dir(), "TIMESFM_WSL_MODEL_MISSING")
        stage = prepare(app_code, model_dir)
        model_module = load_model(stage)
        if args.mode == "preflight":
            runtime = load_runtime(stage)
            runtime.command(2)
            model_module.versions()
            manifest_path = stage / "models" / "timesfm-2.5" / "manifest.json"
            require(manifest_path.is_file(), "TIMESFM_WSL_MODEL_MISSING")
            manifest = model_module.loads(manifest_path.read_bytes())
            require(manifest.get("model") == model_module.MODEL
                    and manifest.get("revision") == model_module.REVISION,
                    "TIMESFM_WSL_MODEL_MISMATCH")
            return emit(dict(state="READY", platform=sys.platform, python=sys.executable,
                             venv=str(Path(sys.prefix)), model=str(model_dir), workspace=os.getcwd(),
                             code_bundle_sha256=code_bundle_sha(app_code),
                             systemd_run=shutil.which("systemd-run"), bwrap=shutil.which("bwrap"),
                             systemctl=shutil.which("systemctl"), uid=os.getuid()))
        if args.mode == "manifest":
            manifest = model_module.verify_model(stage / "models" / "timesfm-2.5")
            return emit(dict(state="READY", manifest_sha256=model_module.digest(manifest),
                             model_revision=manifest["revision"],
                             weight_sha256=manifest["files"]["model.safetensors"],
                             code_bundle_sha256=code_bundle_sha(app_code), manifest=manifest))
        raw = sys.stdin.buffer.read(model_module.MAX_INPUT + 1)
        require(len(raw) <= model_module.MAX_INPUT, "WORKER_INPUT_LIMIT")
        runtime = load_runtime(stage)
        response = runtime.run(raw)
        require(isinstance(response, dict), "TIMESFM_WSL_PROTOCOL_INVALID")
        if raw != b"probe":
            require(response.get("request_sha256") == hashlib.sha256(raw).hexdigest(),
                    "TIMESFM_WSL_PROTOCOL_INVALID")
        return emit(response)
    except BridgeError as error:
        return emit(dict(state="BLOCKED", error_code=str(error)), 2)
    except Exception as error:
        text = str(error)
        code = text if re.fullmatch(r"[A-Z][A-Z0-9_]{0,100}", text) else "TIMESFM_WSL_BRIDGE_FAILED"
        return emit(dict(state="BLOCKED", error_code=code), 2)
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
