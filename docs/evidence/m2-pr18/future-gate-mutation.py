import pathlib,subprocess,sys,json,os
root=pathlib.Path.cwd();tree=root/'state/test-tree';p=tree/'research/agent/src/risk_cpu.rs';source=p.read_text()
start=source.index('        self.frozen.validate(if fresh {');end=source.index('        })?;',start)+len('        })?;')
mutant=source[:start]+'        if false {\n'+source[start:end]+'\n        }'+source[end:]
env=os.environ.copy();env['TEMP']=env['TMP']=str(root/'state/tmp');env['CARGO_INCREMENTAL']='0'
def build():
 with (root/'state/red-green-build.log').open('a') as log:return subprocess.run(['pwsh','-NoProfile','-File',str(tree/'scripts/with-msvc.ps1'),'build','-p','stratide-research','--bins','--locked','--offline'],cwd=tree,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
def check(label):
 with (root/f'state/{label}.log').open('w') as log:return subprocess.run([sys.executable,'-X','utf8','-B','scripts/test-timesfm-cpu.py','Tests.test_02_future_observation_rejected'],cwd=tree,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
try:
 p.write_text(mutant)
 assert build()==0
 red=check('red-future-gate-mutant')
finally:p.write_text(source)
assert build()==0
green=check('green-future-gate')
(root/'state/red-green.json').write_text(json.dumps(dict(kind='DELIBERATE_MUTATION_COUNTEREXAMPLE_NOT_BASELINE_BUG',mutation='omit Frozen.validate',test='Tests.test_02_future_observation_rejected',red_exit=red,green_exit=green),indent=2))
print('red',red,'green',green)
assert red==1 and green==0
