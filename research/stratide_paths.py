"""One state-root rule for a Git checkout and an installed Windows product.

A Git worktree keeps the historical repository-shared state. The installed
product has no Git; the supervisor sets STRATIDE_STATE_ROOT to the Owner-chosen
data directory and every mutable store lives below it. Path selection only:
no financial, budget or credential value is changed here.
"""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def installed_root():
    value = os.environ.get("STRATIDE_STATE_ROOT")
    return Path(value).resolve() if value else None


def _git_root():
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")}
    result = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=ROOT, env=env, capture_output=True, check=True)
    return Path(os.fsdecode(result.stdout).strip()).resolve().parent


def common_root():
    root = installed_root()
    return root if root is not None else _git_root()


def local_root():
    """Repository-local state directory; the data directory after installation."""
    root = installed_root()
    return root if root is not None else ROOT


def bin_dir():
    value = os.environ.get("STRATIDE_BIN_DIR")
    return Path(value) if value else ROOT / "target/debug"


def executable(name):
    return bin_dir() / (name + (".exe" if os.name == "nt" else ""))


def ignored(path):
    """Refuse to place mutable state outside an ignored or Owner data root."""
    root = installed_root()
    if root is not None:
        target = Path(path).resolve()
        return target == root or root in target.parents
    return subprocess.run(["git", "check-ignore", "--quiet", "--", str(path)],
                          cwd=ROOT).returncode == 0
