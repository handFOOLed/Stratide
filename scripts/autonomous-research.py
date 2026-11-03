"""Local deterministic autonomous research. No HTTP, credentials or Agent dispatch."""
from decimal import InvalidOperation
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"research"))
import autonomous_research as a

if __name__ == "__main__":
    try:
        print(json.dumps(a.cli(), ensure_ascii=False, sort_keys=True, allow_nan=False), flush=True)
    except a.Error as exc:
        print(json.dumps(dict(**a.m.SAFE, state="BLOCKED", reason=str(exc))), flush=True)
        sys.exit(2)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, InvalidOperation):
        print(json.dumps(dict(**a.m.SAFE, state="BLOCKED", reason="LOCAL_IO_SCHEMA_OR_CONFIG_ERROR")), flush=True)
        sys.exit(2)
