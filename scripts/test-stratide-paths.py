"""Installed-mode path selection (Issue #85). No Git required."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import stratide_paths as paths

STATE = ROOT / "state" / "issue85-test" / "paths-test"
STATE.mkdir(parents=True, exist_ok=True)
BIN = STATE / "bin"
BIN.mkdir(parents=True, exist_ok=True)

os.environ["STRATIDE_STATE_ROOT"] = str(STATE)
os.environ["STRATIDE_BIN_DIR"] = str(BIN)
assert paths.common_root() == STATE.resolve()
assert paths.local_root() == STATE.resolve()
assert paths.bin_dir() == BIN
assert paths.executable("stratide-cli").name.startswith("stratide-cli")
assert paths.ignored(STATE / "state" / "x.json")
assert not paths.ignored(ROOT / "research" / "not-state.json")

os.environ.pop("STRATIDE_STATE_ROOT")
os.environ.pop("STRATIDE_BIN_DIR")
git_root = paths.common_root()
assert git_root != STATE.resolve()
assert (git_root / ".git").exists() or (git_root / ".git").is_file()
assert paths.local_root() == ROOT
print("PASS installed and checkout path selection")
