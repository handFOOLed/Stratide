"""Explicit Owner management; watch remains in eod-operator market watch."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import market_research as r
import market_eod as m
import eod_journal as j
p=argparse.ArgumentParser()
p.add_argument("action",choices=["status","install-model","configure","grant","revoke","pause","preview","once"])
p.add_argument("--input",type=Path)
p.add_argument("--day")
p.add_argument("--root",type=Path)
a=p.parse_args()
try:
    value=j.loads(a.input.read_bytes()) if a.input else (dict(source_day=a.day) if a.day else {})
    out=r.once(m.Market(a.root or m.default_root())) if a.action=="once" else r.bridge(a.action,value)
    print(json.dumps(out,ensure_ascii=False,allow_nan=False))
except (OSError,ValueError,j.Rejected) as e:
    print(json.dumps(dict(state="BLOCKED",error_code=str(e) if isinstance(e,j.Rejected) else "MARKET_RESEARCH_COMMAND_FAILED")))
    raise SystemExit(2)
