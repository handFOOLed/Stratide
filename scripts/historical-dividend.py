"""Offline historical dividend scenario prepare/run/evaluate; no provider calls."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.historical_dividend import main

if __name__ == "__main__":
    sys.exit(main())
