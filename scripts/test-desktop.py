"""Disposable standalone checkout only: real HTTP + original recorded Gate.

All inputs, accounts and metering are synthetic_test/TST; no paid Provider.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
EXE=ROOT/'target/debug'/('stratided.exe' if os.name=='nt' else 'stratided')
STATE=ROOT/'state/desktop-test'
FLAGS=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0

def cli(script,*args):
    r=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),*map(str,args)],cwd=ROOT,capture_output=True,timeout=120)
    assert r.returncode==0,(script,r.stdout.decode(errors='replace')[:1000],r.stderr.decode(errors='replace')[:1000])
    return json.loads(r.stdout)

def main():
    common=subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],cwd=ROOT).decode().strip()
    assert Path(common).resolve().parent==ROOT,'Requires disposable standalone checkout; never bind the Owner checkout'
    assert not STATE.exists(),'Use a fresh disposable checkout for this test'
    STATE.mkdir(parents=True)
    agent=STATE/'agent'
    subprocess.run([str(EXE),'--agent-init-fake',str(agent)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    cli('risk-portfolio.py','init','--agent-dir',agent)
    cli('risk-portfolio.py','configure-recorded')
    cli('risk-portfolio.py','--name','desktop-recorded','synthetic-freeze','--scenario','calm','--strategy-version','synthetic_test-v1')
    cli('risk-portfolio.py','enable')
    config=STATE/'dashboard.json'
    config.write_text(json.dumps(dict(schema_version=1,python=sys.executable,workspace=str(ROOT),
        operations=[dict(id='recorded',label='离线录制研究',kind='recorded_fusion',batch='desktop-recorded')],
        timesfm_batches=[],fusion_batches=[],evaluation_dirs=[],registry_dirs=[str(ROOT/'state/candidates/desktop-recorded')],evidence_files=[],backup_manifest=None)),encoding='utf-8')
    token=(agent/'owner-token').read_text().strip()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,body=None,expected=200,*,owner=True,origin=True):
        headers={}
        if owner:headers['X-Stratide-Owner']=token
        if origin:headers['Origin']=base
        if body is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:r=opener.open(req,timeout=30)
        except urllib.error.HTTPError as e:r=e
        with r:
            v=json.load(r);assert r.status==expected,(path,r.status,v.get('error'));return v['data']
    def start():
        p=subprocess.Popen([str(EXE),'--assets-dir',str(ROOT/'apps/dashboard/dist'),'--port',str(port),'--agent-dir',str(agent),'--desktop-config',str(config)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=FLAGS)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            assert p.poll() is None,p.stderr.read().decode()
            try:request('/api/health');return p
            except OSError:time.sleep(.1)
        raise AssertionError('local readiness timeout')
    process=start()
    try:
        request('/api/agent/inbox',expected=401,owner=False)
        key=uuid.uuid4().hex
        request('/api/agent/approvals',dict(id=key,operation='recorded'),expected=403,origin=False)
        budget=request('/api/agent/status')['budget']
        assert request('/api/v1/workspace')['studies'][0]['state']=='FROZEN_NOT_RUN'
        assert request('/api/agent/status')['budget']==budget
        first=request('/api/agent/approvals',dict(id=key,operation='recorded'))
        assert request('/api/agent/approvals',dict(id=key,operation='recorded'))==first
        request('/api/agent/decide',dict(id=key,decision='start'),expected=409)
        request('/api/agent/decide',dict(id=key,decision='approve'))
        request('/api/agent/decide',dict(id=key,decision='start'))
        request('/api/agent/decide',dict(id=key,decision='start'),expected=409)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            item=next(v for v in request('/api/agent/inbox')['approvals'] if v['id']==key)
            if item['status']!='running':break
            time.sleep(.1)
        assert item['status']=='completed',item
        w=request('/api/v1/workspace')
        assert w['studies'][0]['state']=='RESEARCH_ONLY' and w['studies'][0]['summary']['real_cloud_calls']==0
        assert w['candidates'] and all(c.get('paper_allowed') is False and c.get('live_allowed') is False for c in w['candidates'])
        after=request('/api/agent/status')['budget'];assert after['currency']=='TST'
        for _ in range(2):request('/api/v1/workspace')
        assert request('/api/agent/status')['budget']==after
        with closing(sqlite3.connect(agent/'agent.sqlite')) as db:
            calls=db.execute('SELECT count(*) FROM calls').fetchone()[0]
            assert calls==2
        assert request('/api/agent/prompts')['version']=='fusion-researcher-v1'
    finally:process.terminate();process.wait(timeout=10);process.stderr.close()
    process=start()
    try:
        assert next(v for v in request('/api/agent/inbox')['approvals'] if v['id']==key)['status']=='completed'
        assert request('/api/agent/status')['budget']==after
    finally:process.terminate();process.wait(timeout=10);process.stderr.close()
    print(json.dumps(dict(state='PASS',input_mode='synthetic_test',billing='TST_RECORDED_NOT_REAL',http_auth_origin='PASS',
        approval_idempotency='PASS',original_task_budget_registry='PASS',restart='PASS',refresh_calls_added=0,real_cloud_calls=0,paper_orders=0)))

if __name__=='__main__':main()
