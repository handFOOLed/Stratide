"""Explicit install step; never imported by runtime/verify/status."""
from pathlib import Path
import json
import urllib.request

from model import MODEL, REVISION, VERSIONS, WEIGHT_SHA, require, sha_file, verify_model, versions


def provision(directory):
    versions()
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    for name in ("model.safetensors", "config.json", "README.md"):
        target = root / name
        if target.exists() and name == "model.safetensors" and sha_file(target) == WEIGHT_SHA:
            continue
        url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}"
        with urllib.request.urlopen(url, timeout=120) as response, open(target.with_suffix(target.suffix + ".part"), "wb") as out:
            while block := response.read(4 * 1024 * 1024):
                out.write(block)
        target.with_suffix(target.suffix + ".part").replace(target)
    # Package license is part of the exact pinned wheel, not mutable master.
    import importlib.metadata
    dist = importlib.metadata.distribution("timesfm")
    license_path = next(p for p in dist.files if str(p).endswith("licenses/LICENSE"))
    (root / "LICENSE").write_bytes(dist.locate_file(license_path).read_bytes())
    require(sha_file(root / "model.safetensors") == WEIGHT_SHA, "OFFICIAL_WEIGHT_SHA_MISMATCH")
    manifest = dict(schema_version=1, model=MODEL, revision=REVISION, license="Apache-2.0", versions=VERSIONS,
                    files={n: sha_file(root / n) for n in ("model.safetensors", "config.json", "README.md", "LICENSE")})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verify_model(root)
    return manifest


if __name__ == "__main__":
    import sys
    print(json.dumps(provision(sys.argv[1])))
