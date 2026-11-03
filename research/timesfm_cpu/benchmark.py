"""Synthetic only. Development hardware results never qualify an N100."""
import datetime as dt
import json
import math
import os
from pathlib import Path
import platform
import statistics
import time

from model import MEMORY_MAX, Rejected, digest, verify_model
import runtime


def machine():
    cpu = platform.processor()
    memory = None
    physical = None
    if os.name == "nt":
        import ctypes as c
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            cpu = winreg.QueryValueEx(k,"ProcessorNameString")[0].strip()
        class Memory(c.Structure):
            _fields_ = [("length",c.c_ulong),("load",c.c_ulong)] + [(n,c.c_ulonglong) for n in
                       ("total_physical","available_physical","total_page","available_page","total_virtual","available_virtual","extended")]
        mem = Memory()
        mem.length = c.sizeof(mem)
        c.windll.kernel32.GlobalMemoryStatusEx(c.byref(mem))
        memory = mem.total_physical
        size=c.c_ulong()
        c.windll.kernel32.GetLogicalProcessorInformationEx(0,None,c.byref(size))
        buf=c.create_string_buffer(size.value)
        if c.windll.kernel32.GetLogicalProcessorInformationEx(0,buf,c.byref(size)):
            offset,physical=0,0
            while offset<size.value:
                relation=c.c_ulong.from_buffer(buf,offset).value
                length=c.c_ulong.from_buffer(buf,offset+4).value
                if not length:
                    break
                physical += int(relation==0)
                offset += length
    elif Path("/proc/cpuinfo").exists():
        lines = Path("/proc/cpuinfo").read_text().splitlines()
        cpu = next((l.split(":",1)[1].strip() for l in lines if l.startswith("model name")),cpu)
        pairs, package, core = set(),None,None
        for line in lines+[""]:
            if line.startswith("physical id"):
                package = line.split(":")[1].strip()
            elif line.startswith("core id"):
                core = line.split(":")[1].strip()
            elif not line and core is not None:
                pairs.add((package,core))
        physical = len(pairs) or None
        memory = os.sysconf("SC_PHYS_PAGES")*os.sysconf("SC_PAGE_SIZE")
    return dict(cpu=cpu,logical_threads=os.cpu_count(),physical_cores=physical,
                physical_cores_status="MEASURED" if physical else "NOT_MEASURED",memory_bytes=memory,
                system=platform.system(),release=platform.release(),architecture=platform.machine(),python=platform.python_version())


def run_request(request, diagnostic=False, raw=None):
    raw = raw if raw is not None else json.dumps(request,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    if not diagnostic:
        return runtime.run(raw)
    # Explicit development-only path. Cannot be passed into the production once command.
    python = runtime.ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    env = runtime.clean_env(request["threads"])
    env["STRATIDE_TIMESFM_MODEL"] = str(runtime.ROOT/"models/timesfm-2.5")
    guard = None
    if os.name == "nt":
        from windows import Job
        guard = Job
    return runtime.communicate_bounded([str(python),"-I","-B",str(runtime.ROOT/"research/timesfm_cpu/worker.py"),
                                        "--development-cpu-diagnostic"],raw,env=env,on_spawn=guard)


def percentile(values, q):
    values = sorted(values)
    return values[max(0,math.ceil(len(values)*q)-1)]


def measure(n, context, diagnostic):
    request = dict(schema_version=1,input_mode="synthetic_test",horizon=20,max_context=context,batch_size=1,threads=2,repeats=3,
                   series=[dict(instrument=f"synthetic-{i}",values=[.01+.002*math.sin(t*.2+i)+.001*math.sin(t*.05) for t in range(context)]) for i in range(n)])
    started = time.perf_counter()
    result = run_request(request,diagnostic)
    m = result["metrics"]
    hot = [v["seconds"]/v["series"] for v in m["batch_timings"][n:]]
    return dict(series=n,context=context,batch_size=1,threads=2,repeats=3,status="PASS",failures=0,
                process_wall_seconds=time.perf_counter()-started,load_seconds=m["load_seconds"],
                first_batch_seconds=m["batch_timings"][0]["seconds"],worker_wall_seconds=m["wall_seconds"],cpu_seconds=m["cpu_seconds"],
                hot_per_series_p50_seconds=statistics.median(hot),hot_per_series_p95_seconds=percentile(hot,.95),
                hot_per_series_mean_seconds=statistics.mean(hot),peak_rss_bytes=m["peak_rss_bytes"],
                process_resources={k:v for k,v in m.items() if k.startswith(("job_","cgroup_")) or k=="resource_scope"},
                output_sha256=digest(result["forecasts"]),repeatability="THREE_IDENTICAL_FORECASTS",isolation=result["isolation"])


def walk_forward(diagnostic=False):
    # All closes are synthetic. Targets are kept outside each model request.
    from cli import bridge,frozen
    desc = bridge("descriptor")
    calendar, day = [],dt.date(2025,1,2)
    while len(calendar)<144:
        if day.weekday()<5:
            calendar.append(day.isoformat())
        day += dt.timedelta(days=1)
    closes = [10000+3*t+int(70*math.sin(t*.32)+50*math.sin(t*.08)) for t in range(144)]
    all_returns = [b/a-1 for a,b in zip(closes,closes[1:])]
    all_rms = [math.sqrt(sum(x*x for x in all_returns[t:t+20])/20) for t in range(len(all_returns)-19)]
    records,errors = [],{key:[] for key in ("timesfm","naive","ewma")}
    failures=0
    for cut in (84,104,124):
        f = frozen(desc,1)
        f["calendar"] = calendar[:cut+20]
        f["as_of"] = calendar[cut-1]+"T16:00:00Z"
        f["series"][0]["observations"] = [dict(trade_day=d,available_at=d+"T15:00:00Z",close_fen=p) for d,p in zip(calendar[:cut],closes[:cut])]
        f["snapshot_ref"] = digest(dict(series=f["series"],calendar=f["calendar"]))
        plan = dict(batch=f"walk-{cut}",frozen=f,manifest_sha256=digest(verify_model(runtime.ROOT/"models/timesfm-2.5")),
                    code_sha256=desc["code_sha256"],max_context=256,batch_size=1,threads=2)
        projected = bridge("evaluate-project",plan)
        request = json.loads(projected["worker_request_json"])
        base = projected["baselines"][0]
        actual = all_rms[cut-20:cut]
        assert len(actual)==20 and len(request["series"][0]["values"])==cut-20
        record = dict(prefix_closes=cut,context=cut-20,as_of=f["as_of"],request_sha256=digest(request),target_sent_to_worker=False)
        try:
            result = run_request(request,diagnostic,projected["worker_request_json"].encode())
            risk_result=bridge("decode-development" if diagnostic else "decode",dict(plan=plan,response=result))
            record["risk_experts"]=risk_result["risk_experts"]
            record["development_only"]=risk_result["receipt"]["development_only"]
            pred = result["forecasts"][0]["values"]
            predictions = dict(timesfm=pred,naive=[base["naive"]]*20,ewma=[base["ewma"]]*20)
            record["horizon_mean_absolute_errors"]={}
            for model,values in predictions.items():
                errors[model].extend(a-b for a,b in zip(values,actual))
                record["horizon_mean_absolute_errors"][model] = {str(h):abs(statistics.mean(values[:h])-statistics.mean(actual[:h])) for h in (5,20)}
            record["status"]="PASS"
        except Rejected as e:
            failures += 1
            record.update(status="FAILED",error_code=str(e))
        records.append(record)
    metrics={k:dict(mae=statistics.mean(abs(x) for x in v),rmse=math.sqrt(statistics.mean(x*x for x in v)),points=len(v)) if v else
             dict(mae=None,rmse=None,points=0) for k,v in errors.items()}
    return dict(mode="SYNTHETIC_SEQUENTIAL_AS_OF_WALK_FORWARD",folds=records,metrics=metrics,missing=0,failures=failures,
                authority="RESEARCH_ONLY",eligibility="ELIGIBILITY_DENIED")


def benchmark(diagnostic=False):
    manifest = verify_model(runtime.ROOT/"models/timesfm-2.5")
    rows=[]
    for context in (64,128,256,512):
        for n in (10,30,50,100):
            try:
                row=measure(n,context,diagnostic)
            except Rejected as e:
                row=dict(series=n,context=context,status="FAILED",failures=n,error_code=str(e))
            rows.append(row)
            print(json.dumps(dict(progress=dict(context=context,series=n,status=row["status"]))),file=__import__("sys").stderr,flush=True)
    return dict(label="DEVELOPMENT_CPU_BENCHMARK",N100_ACCEPTANCE="NOT_VERIFIED",machine=machine(),
                manifest=manifest,model_manifest_sha256=digest(manifest),memory_budget_bytes=MEMORY_MAX,
                isolation_acceptance="NOT_VERIFIED" if diagnostic else "MEASURED_BY_WORKER",
                matrix=rows,walk_forward=walk_forward(diagnostic),paper_allowed=False,live_allowed=False,billing="LOCAL_NO_BILLING")
