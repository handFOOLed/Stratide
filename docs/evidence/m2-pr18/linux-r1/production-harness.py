import contextlib,datetime,hashlib,json,os,sqlite3,subprocess,threading,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=BASE/'production-checkout'
assert ROOT.is_dir() and (ROOT/'.git').is_dir()
OWNER=ROOT/'state/disposable-synthetic-owner'
STEPS=[];SAMPLES=[];PIDS=set();HALT=threading.Event()
UNIT='stratide-timesfm-cpu.service'
def run(args,*,json_output=True):
    started=time.monotonic()
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=650)
    row=dict(argv=[str(a) for a in args],exit=p.returncode,wall_seconds=time.monotonic()-started)
    if json_output:
        row['output']=json.loads(p.stdout)
    else:row['stdout']=p.stdout.strip()
    STEPS.append(row)
    (BASE/'production-steps.json').write_text(json.dumps(STEPS,indent=2)+'\n')
    if p.returncode:raise RuntimeError(f'command failed: {args[0]} exit {p.returncode}: {p.stderr[:600]} {p.stdout[:400]}')
    return row.get('output')
def cli(command,*args):return run(['python3.12','-B','scripts/timesfm-cpu.py',command,*args])
def properties(*keys):
    p=subprocess.run(['systemctl','--user','show',UNIT,'--property='+','.join(keys)],capture_output=True,text=True,timeout=5)
    return dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
def sample():
    while not HALT.is_set():
        try:
            fields=properties('ActiveState','ControlGroup','MemoryMax','MemorySwapMax','OOMPolicy','KillMode','CPUQuotaPerSecUSec')
            if fields.get('ActiveState')=='active' and fields.get('ControlGroup'):
                cg=Path('/sys/fs/cgroup')/fields['ControlGroup'].lstrip('/')
                item=dict(unit={k:v for k,v in fields.items() if k!='ControlGroup'},kernel={k:(cg/k).read_text().strip() for k in ('memory.max','memory.swap.max','memory.oom.group','memory.current','memory.peak')},workers=[])
                for pid in (cg/'cgroup.procs').read_text().split():
                    PIDS.add(int(pid));proc=Path('/proc')/pid
                    args=(proc/'cmdline').read_bytes().split(b'\0')
                    if not args or b'python' not in args[0] or b'/app/worker.py' not in args:continue
                    rss=int(next(line.split()[1] for line in (proc/'status').read_text().splitlines() if line.startswith('VmRSS:')))*1024
                    worker=dict(pid=int(pid),rss_bytes=rss)
                    try:
                        worker['net_namespace_distinct']=os.readlink(proc/'ns/net')!=os.readlink('/proc/self/ns/net')
                        worker['interfaces']=[line.split(':')[0].strip() for line in (proc/'net/dev').read_text().splitlines() if ':' in line]
                        mounts=[line.split() for line in (proc/'mountinfo').read_text().splitlines()]
                        worker['model_mount_readonly']=any(parts[4]=='/model' and 'ro' in parts[5].split(',') for parts in mounts)
                    except OSError as error:worker['proc_inspection_error']=type(error).__name__
                    item['workers'].append(worker)
                SAMPLES.append(item)
        except (OSError,StopIteration,subprocess.SubprocessError):pass
        HALT.wait(.05)

common=subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],cwd=ROOT,text=True).strip()
assert Path(common).resolve().parent==ROOT
run([str(ROOT/'target/debug/stratided'),'--agent-init-fake',str(OWNER)],json_output=False)
run(['python3.12','-B','scripts/risk-portfolio.py','init','--agent-dir',str(OWNER)])
config_before=hashlib.sha256((OWNER/'settings.json').read_bytes()).hexdigest()
cli('preflight');cli('enable');cli('synthetic-freeze','--name','linux-real-risk','--series','4')
watcher=threading.Thread(target=sample,daemon=True);watcher.start()
try:result=cli('once','--name','linux-real-risk')
finally:HALT.set();watcher.join(timeout=10)
assert result['state']=='completed'
status=cli('status','--name','linux-real-risk')
verified=cli('verify','--name','linux-real-risk');assert verified['verified'] is True
stopped=cli('stop');assert stopped['state']=='STOPPED'
bundle=result['result']['research']['risk_portfolio'];metrics=result['result']['worker_response']['metrics']
assert bundle['receipt']['development_only'] is False
assert bundle['authority']=='RESEARCH_ONLY' and bundle['eligibility']=='ELIGIBILITY_DENIED'
assert bundle['paper_allowed'] is False and bundle['live_allowed'] is False and bundle['can_execute_forward_paper'] is False
with sqlite3.connect(OWNER/'agent.sqlite') as db:
    tasks=db.execute('SELECT id,status,reason FROM tasks').fetchall();calls=db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]
    enabled=db.execute("SELECT value FROM meta WHERE key='timesfm_cpu_enabled'").fetchone()[0]
assert calls==0 and len(tasks)==1 and tasks[0][1]=='completed' and enabled=='false'
workers=[w for s in SAMPLES for w in s['workers']]
assert workers and max(w['rss_bytes'] for w in workers)>1024**3
assert all(s['kernel']['memory.max']=='6442450944' and s['kernel']['memory.swap.max']=='0' and s['kernel']['memory.oom.group']=='1' for s in SAMPLES)
assert all(w.get('net_namespace_distinct') and set(w.get('interfaces',[]))<={'lo'} and w.get('model_mount_readonly') for w in workers)
for _ in range(50):
    alive=[pid for pid in PIDS if Path('/proc',str(pid)).exists()]
    if not alive:break
    time.sleep(.1)
assert not alive
unit_after=properties('LoadState','ActiveState');assert unit_after['ActiveState']=='inactive'
assert hashlib.sha256((OWNER/'settings.json').read_bytes()).hexdigest()==config_before
proof=dict(label='WSL2_LINUX_CPU_PRODUCTION_ENGINEERING_E2E',N100_ACCEPTANCE='NOT_VERIFIED',data_mode='synthetic_test',tasks=tasks,calls=calls,billing='LOCAL_NO_BILLING',enabled_after_stop=enabled,
    verified=verified['verified'],paper_allowed=False,live_allowed=False,metrics=metrics,baseline_comparison=[e['baseline_comparison'] for e in bundle['risk_experts']],
    original_settings_unchanged=True,host_sample_count=len(SAMPLES),host_peak_memory_bytes=max(int(s['kernel']['memory.peak']) for s in SAMPLES),
    host_worker_peak_rss_bytes=max(w['rss_bytes'] for w in workers),observed_pids=sorted(PIDS),orphan_pids_after_stop=alive,unit_after_stop=unit_after,host_network_namespace_isolated=True,
    host_model_mount_readonly=True,host_observations=SAMPLES,source_code_sha256=bundle['receipt']['code_sha256'])
(BASE/'production-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:v for k,v in proof.items() if k not in ('host_observations','baseline_comparison')}))
