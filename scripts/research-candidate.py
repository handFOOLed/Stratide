"""Offline register/freeze/evaluate/status entrypoint; see docs/M2_PR04.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from candidates import main

if __name__ == "__main__":
    sys.exit(main())
