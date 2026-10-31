"""Offline Corporate Action Evidence Bundle V1; no network or financial writes."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.corporate_actions import main

if __name__ == "__main__":
    sys.exit(main())
