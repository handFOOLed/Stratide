"""Owner-local research Inbox and explicit fixed-template review."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from review import main

if __name__ == "__main__":
    raise SystemExit(main())
