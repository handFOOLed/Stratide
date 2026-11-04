"""Core-only CLI, no provider calls; full market metrics remain in local files."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from risk_evaluation import main
if __name__ == "__main__":
    raise SystemExit(main())
