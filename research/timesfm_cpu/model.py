"""Pinned TimesFM 2.5 only. Provisioning is the only network-capable operation."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys
import time

MODEL = "google/timesfm-2.5-200m-pytorch"
REVISION = "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
WEIGHT_SHA = "2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8"
VERSIONS = {"timesfm": "2.0.2", "torch": "2.8.0+cpu", "numpy": "2.2.6",
            "huggingface-hub": "0.34.4", "safetensors": "0.6.2"}
MAX_INPUT, MAX_OUTPUT = 2 * 1024 * 1024, 512 * 1024
MEMORY_MAX = 6 * 1024 ** 3


class Rejected(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Rejected(code)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def loads(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, "DUPLICATE_JSON_KEY")
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(Rejected("NONFINITE_JSON")))


def versions():
    actual = {k: importlib.metadata.version(k) for k in VERSIONS}
    require(actual == VERSIONS and sys.version_info[:2] == (3, 12), "DEPENDENCY_VERSION_MISMATCH")
    for line in Path(__file__).with_name("requirements.lock").read_text().splitlines():
        if not line or line.startswith("#") or ("sys_platform" in line and sys.platform != "win32"):
            continue
        name, version = line.split(";",1)[0].strip().split("==")
        name = name.split("[")[0]
        require(importlib.metadata.version(name) == version,"DEPENDENCY_VERSION_MISMATCH")
    return actual


def verify_model(directory):
    root = Path(directory)
    try:
        require(not root.is_symlink(), "MODEL_NOT_PROVISIONED")
        manifest = loads((root / "manifest.json").read_bytes())
        require(manifest["model"] == MODEL and manifest["revision"] == REVISION
                and manifest["license"] == "Apache-2.0" and manifest["versions"] == VERSIONS
                and set(manifest["files"]) == {"model.safetensors", "config.json", "README.md", "LICENSE"},
                "MODEL_NOT_PROVISIONED")
        require(manifest["files"]["model.safetensors"] == WEIGHT_SHA, "MODEL_NOT_PROVISIONED")
        for name, expected in manifest["files"].items():
            path = root / name
            require(path.is_file() and not path.is_symlink() and sha_file(path) == expected, "MODEL_NOT_PROVISIONED")
        return manifest
    except (OSError, KeyError, ValueError, TypeError):
        raise Rejected("MODEL_NOT_PROVISIONED") from None


def validate_request(v):
    require(isinstance(v, dict) and set(v) == {"schema_version", "input_mode", "horizon", "max_context", "batch_size", "threads", "series", "repeats"}, "WORKER_SCHEMA")
    require(v["schema_version"] == 1 and v["input_mode"] in ("synthetic_test", "historical_research_only") and v["horizon"] == 20, "WORKER_RESEARCH_SCOPE")
    require(type(v["max_context"]) is int and v["max_context"] in (64, 128, 256, 512)
            and type(v["batch_size"]) is int and 1 <= v["batch_size"] <= 4
            and type(v["threads"]) is int and 1 <= v["threads"] <= 4
            and type(v["repeats"]) is int and 1 <= v["repeats"] <= 5, "WORKER_BOUNDS")
    require(isinstance(v["series"], list) and 1 <= len(v["series"]) <= 100, "WORKER_SERIES_BOUND")
    names = set()
    for s in v["series"]:
        require(isinstance(s, dict) and set(s) == {"instrument", "values"}, "WORKER_SERIES_SCHEMA")
        name = s["instrument"]
        require(isinstance(name, str) and 1 <= len(name) <= 32 and name.isascii()
                and all(c.isalnum() or c in "._-" for c in name) and name not in names, "WORKER_SERIES_ID")
        names.add(name)
        require(isinstance(s["values"], list) and 64 <= len(s["values"]) <= v["max_context"]
                and all(type(x) in (float, int) and math.isfinite(x) and 0 <= x <= .35 for x in s["values"]), "WORKER_RMS_UNITS")
    return v


def forecasts(values):
    # Reject negatives rather than silently clamping a risk forecast.
    require(len(values) == 20 and all(type(x) in (float, int) and math.isfinite(x) and 0 <= x <= .35 for x in values), "FORECAST_UNITS_OR_NEGATIVE")
    return values


class Engine:
    def __init__(self, directory, request):
        import os
        require(os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1", "OFFLINE_REQUIRED")
        self.manifest = verify_model(directory)
        versions()
        import numpy as np
        import torch
        import timesfm
        require(torch.version.cuda is None and not torch.cuda.is_available(), "CPU_ONLY_REQUIRED")
        torch.set_num_threads(request["threads"])
        torch.set_num_interop_threads(1)
        torch.set_float32_matmul_precision("high")
        self.np, self.torch = np, torch
        started = time.perf_counter()
        self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            str(Path(directory).resolve()), local_files_only=True, token=False, torch_compile=False)
        require(str(self.model.model.device) == "cpu" and all(p.device.type == "cpu" for p in self.model.model.parameters()), "CPU_ONLY_REQUIRED")
        self.model.compile(timesfm.ForecastConfig(max_context=request["max_context"], max_horizon=20,
            per_core_batch_size=request["batch_size"], normalize_inputs=True,
            use_continuous_quantile_head=False, force_flip_invariance=False,
            infer_is_positive=False, fix_quantile_crossing=False))
        self.load_seconds = time.perf_counter() - started

    def predict(self, request):
        results, times = [], []
        for start in range(0, len(request["series"]), request["batch_size"]):
            rows = request["series"][start:start + request["batch_size"]]
            t = time.perf_counter()
            with self.torch.inference_mode():
                point, _ = self.model.forecast(horizon=20, inputs=[self.np.asarray(s["values"], dtype=self.np.float32) for s in rows])
            require(point.shape == (len(rows), 20), "FORECAST_SHAPE")
            times.append(dict(seconds=time.perf_counter() - t, series=len(rows)))
            results.extend(dict(instrument=s["instrument"], values=forecasts(p.tolist())) for s, p in zip(rows, point))
        return results, times
