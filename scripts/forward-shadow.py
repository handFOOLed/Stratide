"""Owner-local shadow CLI; no clock, dynamic code, HTTP or provider options."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from shadow import main

if __name__ == "__main__":
    raise SystemExit(main())
