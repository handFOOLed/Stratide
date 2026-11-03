"""Issue #61 offline research CLI. Writes only fresh ignored experiment folders."""
import argparse
from decimal import InvalidOperation, localcontext
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import multistock_research as m


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("inspect","plan","run","report","query","verify"))
    parser.add_argument("--v1-root",type=Path)
    parser.add_argument("--v2-root",type=Path)
    parser.add_argument("--start",default=m.data.v1.START)
    parser.add_argument("--end",default=m.data.v1.END)
    parser.add_argument("--v1-version",type=int)
    parser.add_argument("--v2-version",type=int)
    parser.add_argument("--config",type=Path)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--date")
    parser.add_argument("--symbols",default="")
    parser.add_argument("--limit",type=int,default=5)
    parser.add_argument("--full",action="store_true")
    args=parser.parse_args()
    if args.command in ("report","verify"):
        m.require(args.out is not None,"OUTPUT_REQUIRED")
        verification=m.verify(args.out)
        if args.command=="verify":return verification
        result=json.loads((args.out/"results.json").read_bytes())
        return dict(report=result if args.full else m.brief(result),verification=verification,
                    execution=json.loads((args.out/"execution.json").read_bytes()))
    m.require(args.v1_root is not None and args.v2_root is not None,"EXPLICIT_V1_V2_ROOTS_REQUIRED")
    ds=m.data.Dataset(args.v1_root,args.v2_root,args.start,args.end,args.v1_version,args.v2_version)
    config=m.default_config(args.start,args.end)
    if args.config:
        overrides=json.loads(args.config.read_bytes())
        m.require(set(overrides)<=set(config),"CONFIG_FIELDS")
        config.update(overrides)
    if args.command=="run":
        m.require(args.out is not None,"OUTPUT_REQUIRED")
        def progress(value):
            print(json.dumps(dict(progress=value)),file=sys.stderr,flush=True)
        result=m.run(ds,config,args.out,progress)
        return dict(report=m.brief(result["results"]),execution=result["execution"],output_sha=result["output_sha"])
    with localcontext() as ctx:
        ctx.prec=50
        with ds:
            if args.command=="inspect":return ds.inspect()
            if args.command=="plan":
                frozen=m.plan(ds,config)
                return frozen if args.full else dict(plan_sha=frozen["plan_sha"],config=config,source=ds.inspect(),code_sha=frozen["code_sha"])
            m.require(args.date is not None and 1<=args.limit<=100,"QUERY_DATE_AND_LIMIT_1_TO_100_REQUIRED")
            symbols=tuple(filter(None,args.symbols.split(',')))
            day=ds.read_day(args.date,symbols)
            rows=day.pop("rows")
            return dict(**m.SAFE,source_origin=ds.origin,query_sha=ds.query_sha,source_sha=ds.source_sha,
                rows=rows[:args.limit],count=len(rows[:args.limit]),has_more=len(rows)>args.limit,**day)


if __name__=="__main__":
    try:
        print(json.dumps(cli(),ensure_ascii=False,sort_keys=True,allow_nan=False),flush=True)
    except m.Error as e:
        print(json.dumps(dict(**m.SAFE,state="BLOCKED",reason=str(e))),flush=True)
        sys.exit(2)
    except (OSError,ValueError,sqlite3.Error,InvalidOperation):
        print(json.dumps(dict(**m.SAFE,state="BLOCKED",reason="LOCAL_IO_SCHEMA_OR_CONFIG_ERROR")),flush=True)
        sys.exit(2)
