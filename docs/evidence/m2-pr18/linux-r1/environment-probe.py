import datetime,hashlib,importlib.metadata as md,json,os,platform,re,subprocess
from pathlib import Path
from packaging.requirements import Requirement
r=Path.cwd();env={}
def out(*cmd):return subprocess.check_output(cmd,text=True,stderr=subprocess.STDOUT).strip()
env['label']='WSL2_EXT4_LINUX_CPU_ENGINEERING_ACCEPTANCE';env['collected_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();env['N100_ACCEPTANCE']='NOT_VERIFIED'
env['os_release']={k:v.strip('"') for k,v in (line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines()) if k in ('NAME','VERSION_ID','VERSION','PRETTY_NAME')}
env['kernel']=platform.release();env['python']=platform.python_version();env['uid']=os.getuid()
env['rust']=out('rustc','--version');env['cargo']=out('cargo','--version');env['systemd']=out('systemctl','--version').splitlines()[0];env['user_manager']=out('systemctl','--user','is-system-running');env['bubblewrap']=out('bwrap','--version')
env['filesystems']={k:out('findmnt','-n','-o','FSTYPE','--target',str(r/p)) for k,p in (('worktree','.'),('venv','.venv'),('model','models/timesfm-2.5'),('cargo_target','target'))}
env['cgroup_type']=out('stat','-fc','%T','/sys/fs/cgroup');env['cgroup_controllers']=Path('/sys/fs/cgroup/cgroup.controllers').read_text().split()
env['cpu_model']=next(x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name'))
env['logical_cpus']=os.cpu_count();env['host_memtotal_bytes']=int(re.search(r'^MemTotal:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024
pins={};excluded=[]
for line in (r/'research/timesfm_cpu/requirements.lock').read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#'):continue
    req=Requirement(line)
    if req.marker is not None and not req.marker.evaluate():excluded.append(str(req));continue
    installed=md.version(req.name);assert req.specifier.contains(installed),(line,installed);pins[req.name]=installed
env['dependency_versions']=pins;env['dependencies_excluded_by_platform_marker']=excluded
import torch
env['torch_cuda_build']=torch.version.cuda;env['torch_cuda_available']=torch.cuda.is_available();assert env['torch_cuda_build'] is None and env['torch_cuda_available'] is False
manifest=json.loads((r/'models/timesfm-2.5/manifest.json').read_text());actual={}
for name,expected in manifest['files'].items():
    f=r/'models/timesfm-2.5'/name;h=hashlib.sha256()
    with f.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):h.update(block)
    assert h.hexdigest()==expected
    actual[name]=dict(bytes=f.stat().st_size,sha256=h.hexdigest())
env['model']={k:manifest[k] for k in ('model','revision','license')};env['model']['files']=actual
assert manifest['revision']=='1d952420fba87f3c6dee4f240de0f1a0fbc790e3'
env['main_sha']=out('git','-C',str(Path.home()/'projects/Stratide'),'rev-parse','HEAD');env['implementation_start_sha']=out('git','rev-parse','HEAD')
env['main_worktree_clean']=not bool(out('git','-C',str(Path.home()/'projects/Stratide'),'status','--porcelain'))
(r/'state/linux-r1/environment.json').write_text(json.dumps(env,indent=2)+'\n')
print(json.dumps({k:v for k,v in env.items() if k not in ('dependency_versions','model')}))
