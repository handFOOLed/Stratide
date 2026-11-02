"""Explicit foreground CLI; only preflight/backfill/resume access Tushare."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parents[1]/"research"/"historical_sidecar.py"),run_name="__main__")
