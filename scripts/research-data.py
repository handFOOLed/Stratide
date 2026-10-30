"""Local entry point; no network, Provider, Agent database or trading imports."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.data_snapshot import main

if __name__ == "__main__":
    sys.exit(main())
