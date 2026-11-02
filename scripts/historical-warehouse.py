"""Explicit foreground historical warehouse CLI. See docs/M2_PR12.md."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[1] / "research" / "historical_warehouse.py"), run_name="__main__")
