"""BLOCKED/identity contract for the Windows -> existing WSL2 TimesFM bridge.

Every invocation here is a recorded fake wsl.exe transcript: no WSL process,
model file, Agent task or cloud request is used. Real CPU inference is proved
separately by scripts/test-wsl-timesfm-agent.py on an isolated state root.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/timesfm_cpu"))
import cli
import model
import runtime

ENV = dict(STRATIDE_WSL_DISTRIBUTION="Ubuntu-24.04",
           STRATIDE_WSL_WORKSPACE="/home/owner/Stratide",
           STRATIDE_WSL_PYTHON=".venv/bin/python",
           STRATIDE_WSL_MODEL="models/timesfm-2.5")


@contextlib.contextmanager
def environment(**values):
    """Start from one complete configured bridge; None removes a variable."""
    saved = {key: os.environ[key] for key in ENV if key in os.environ}
    for key in ENV:
        os.environ.pop(key, None)
    os.environ.update(ENV)
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    runtime._DISTROS.update(at=0.0, names=[])
    try:
        yield
    finally:
        for key in ENV:
            os.environ.pop(key, None)
        os.environ.update(saved)
        runtime._DISTROS.update(at=0.0, names=[])


def completed(value, code=0):
    body = json.dumps(value).encode() if isinstance(value, dict) else value
    return subprocess.CompletedProcess([], code, body, b"")


DISTROS = completed("Ubuntu-24.04\r\n".encode("utf-16-le"))


@contextlib.contextmanager
def bridge_run(response, recorded=None):
    """Answer the distro listing, then the bridge call with one recorded value."""
    def run(command, **options):
        if recorded is not None:
            recorded.append(command)
        if command[1:3] == ["-l", "-q"]:
            return DISTROS
        return response(command) if callable(response) else response
    def bounded(command, raw, *, timeout, heartbeat, decode):
        assert heartbeat, "WSL bridge must retain its parent lease"
        result = run(command, input=raw, timeout=timeout)
        return decode(result.returncode, result.stdout)

    with patch.object(runtime.subprocess, "run", side_effect=run) as listing, \
            patch.object(runtime, "communicate_bounded", side_effect=bounded) as bridge:
        yield listing, bridge


@unittest.skipUnless(os.name == "nt", "installed-state WSL bridge is Windows only")
class Tests(unittest.TestCase):
    def test_01_unconfigured_state_blocks_without_spawning_wsl(self):
        nothing = dict(STRATIDE_WSL_DISTRIBUTION=None, STRATIDE_WSL_WORKSPACE=None)
        with environment(**nothing), patch.object(runtime.subprocess, "run") as run:
            self.assertIsNone(runtime.wsl_settings())
            self.assertFalse(runtime.uses_wsl())
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_NOT_CONFIGURED"):
                runtime.run(b"probe")
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_NOT_CONFIGURED"):
                cli.model_manifest()
        run.assert_not_called()

    def test_02_incomplete_or_malformed_settings_are_rejected(self):
        with environment(STRATIDE_WSL_WORKSPACE=""), \
                self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_CONFIG_INCOMPLETE"):
            runtime.wsl_settings()
        with environment(STRATIDE_WSL_WORKSPACE="home/owner/Stratide"), \
                self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_WORKSPACE_INVALID"):
            runtime.wsl_settings()
        with environment(STRATIDE_WSL_PYTHON=".venv/bin\npython"), \
                self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_PATH_INVALID"):
            runtime.wsl_settings()
        with environment(), patch.dict(os.environ, dict(STRATIDE_WSL_TIMEOUT="0")), \
                self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_TIMEOUT_INVALID"):
            runtime.wsl_timeout()

    def test_03_distro_listing_is_decoded_and_bounded(self):
        with environment(), bridge_run(DISTROS) as (run, bridge):
            self.assertEqual(runtime.wsl_distros(), ["Ubuntu-24.04"])
            self.assertEqual(runtime.wsl_distros(), ["Ubuntu-24.04"])
            self.assertEqual(run.call_count, 1)
            bridge.assert_not_called()

    def test_04_missing_distro_or_venv_blocks_before_the_worker(self):
        with environment(STRATIDE_WSL_DISTRIBUTION="Ubuntu-9.99"), bridge_run(completed(b"", 1)) as (run, bridge):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_DISTRO_MISSING"):
                runtime.run(b"probe")
            self.assertEqual(run.call_count, 1)  # listing only, no worker launch
            bridge.assert_not_called()
        with environment(), bridge_run(completed(b"", 127)) as (run, bridge):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_VENV_MISSING"):
                runtime.wsl_manifest()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(bridge.call_count, 1)

    def test_05_worker_error_codes_and_protocol_errors_are_propagated(self):
        missing = completed({"state": "BLOCKED", "error_code": "TIMESFM_WSL_MODEL_MISSING"}, 2)
        with environment(), bridge_run(missing):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_MODEL_MISSING"):
                runtime.wsl_manifest()
        with environment(), bridge_run(completed(b"not-json")):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_PROTOCOL_INVALID"):
                runtime.wsl_manifest()
        with environment(), bridge_run(completed({"state": "BLOCKED"}, 2)):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_BRIDGE_FAILED"):
                runtime.wsl_manifest()
        with environment(), bridge_run(completed(b"")):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_BRIDGE_FAILED"):
                runtime.wsl_manifest()

    def test_06_timeout_and_launch_failure_stay_blocked(self):
        def timeout(command):
            raise model.Rejected("WORKER_TIMEOUT")
        with environment(), bridge_run(timeout):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_TIMEOUT"):
                runtime.wsl_manifest()
        with environment(), patch.object(runtime.subprocess, "run", side_effect=OSError("denied")):
            with self.assertRaisesRegex(model.Rejected, "TIMESFM_WSL_UNAVAILABLE"):
                runtime.wsl_distros()

    def test_07_code_and_model_identity_must_match(self):
        manifest = dict(state="READY", manifest_sha256="a" * 64, weight_sha256="b" * 64,
                        model_revision=model.REVISION, manifest={"revision": model.REVISION},
                        code_bundle_sha256=runtime.code_bundle_sha())
        with environment(), bridge_run(completed(manifest)):
            self.assertEqual(runtime.wsl_manifest()["source"], "WSL2_TIMESFM_CPU")
        for override, code in ((dict(manifest_sha256="not-a-digest"), "TIMESFM_WSL_PROTOCOL_INVALID"),
                               (dict(weight_sha256="not-a-digest"), "TIMESFM_WSL_PROTOCOL_INVALID"),
                               (dict(code_bundle_sha256="d" * 64), "TIMESFM_WSL_CODE_MISMATCH")):
            with self.subTest(code=code, override=override), environment(), \
                    bridge_run(completed(dict(manifest, **override))):
                with self.assertRaisesRegex(model.Rejected, code):
                    runtime.wsl_manifest()

    def test_08_worker_response_must_prove_request_and_model(self):
        expected = dict(model_revision=model.REVISION, weight_sha256="b" * 64)
        raw = b'{"threads":2}'
        digest = hashlib.sha256(raw).hexdigest()
        response = dict(request_sha256=digest, **expected)
        cli.require_wsl_identity(raw, expected, response)
        for override, code in ((dict(request_sha256="0" * 64), "TIMESFM_WSL_REQUEST_IDENTITY_MISMATCH"),
                               (dict(model_revision="other"), "TIMESFM_WSL_MODEL_IDENTITY_MISMATCH"),
                               (dict(weight_sha256="0" * 64), "TIMESFM_WSL_MODEL_IDENTITY_MISMATCH")):
            with self.subTest(code=code, override=override), \
                    self.assertRaisesRegex(model.Rejected, code):
                cli.require_wsl_identity(raw, expected, dict(response, **override))

    def test_09_windows_paths_are_converted_for_wsl(self):
        path = runtime.windows_to_wsl(ROOT)
        self.assertTrue(path.startswith("/mnt/"), path)
        self.assertNotIn("\\", path)
        self.assertTrue(path.endswith(str(ROOT).replace("\\", "/")[2:]))

    def test_10_owner_pipe_closure_stops_a_running_bridge(self):
        program = """
import os, sys, time
from owner_pipe import read_request_line, watch_owner
raw, pending = read_request_line(0, 5)
assert raw == b'probe'
watch_owner(0, pending, lambda: os._exit(73))
print('running', flush=True)
time.sleep(20)
"""
        with subprocess.Popen([sys.executable, "-B", "-c", program],
                              cwd=ROOT / "research/timesfm_cpu",
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE) as bridge:
            try:
                bridge.stdin.write(b"probe\n.\n")
                bridge.stdin.flush()
                self.assertEqual(bridge.stdout.readline().strip(), b"running")
                bridge.stdin.close()
                self.assertEqual(bridge.wait(3), 73)
            finally:
                if bridge.poll() is None:
                    bridge.kill()

if __name__ == "__main__":
    unittest.main(verbosity=2)
