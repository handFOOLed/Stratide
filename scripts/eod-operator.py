"""Production CLI: real clock and existing collector, no fixture/HTTP override."""
import os
from pathlib import Path
import sys

# The supervisor releases the script only after assigning it to its Windows Job.
if __name__ == "__main__" and os.environ.pop("STRATIDE_EOD_SUPERVISOR_GATE", None) == "1":
    if sys.stdin.buffer.read(1) != b"1":
        raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from eod_operator import main

if __name__ == "__main__":
    raise SystemExit(main())
