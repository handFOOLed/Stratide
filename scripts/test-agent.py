"""Issue #22 real-process fault evidence. All Provider calls are local fake.

Independent black-box/SQL assertions do not call the Rust budget calculator.
No market requests, cloud credentials, financial writes or generated code.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/evidence/m0-pr03/sample-report'
FLAGS = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0


def fingerprints():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in REPORT.iterdir() if p.is_file()}


def wait(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError('condition did not complete within deadline')


class Service:
    def __init__(self, binary, directory):
        self.binary, self.directory = binary, directory
        self.token = (directory / 'owner-token').read_text().strip()
        self.process = None

    def start(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.process = subprocess.Popen([str(self.binary), '--port', str(port), '--agent-dir', str(self.directory),
                                         '--report-dir', str(REPORT), '--assets-dir', str(ROOT/'apps/dashboard/dist')],
                                        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=FLAGS)
        def ready():
            if self.process.poll() is not None:
                raise AssertionError('service exited before ready: ' + self.process.stderr.read().decode(errors='replace'))
            try:
                return self.request('/api/health')['data']['service'] == 'online'
            except OSError:
                return False
        wait(ready)

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        if self.process:
            self.process.stderr.close()

    def request(self, path, body=None, expected=200, token=True, origin=True, headers=None):
        h = {'X-Stratide-Owner': self.token} if token else {}
        if body is not None:
            h['Content-Type'] = 'application/json'
            if origin:
                h['Origin'] = self.url
        h.update(headers or {})
        req = urllib.request.Request(self.url+path, data=None if body is None else json.dumps(body).encode(), headers=h)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result = json.load(response)
            assert response.status == expected, (path, response.status, expected, result.get('error'))
            assert response.headers.get('Access-Control-Allow-Origin') is None
            return result

    def control(self, action, **values):
        return self.request('/api/agent/control', {'action': action, **values})['data']

    def create(self, name='真实进程 fake 研究'):
        return self.request('/api/agent/tasks', {'name': name, 'goal': '验证摘要、成本假设和反证', 'scope': '当前已发布 Paper 摘要',
                                              'start_day': '2026-10-01', 'end_day': '2026-10-29', 'task_budget_micro': None})['data']['id']

    def task(self, task_id):
        return self.request('/api/agent/tasks/'+task_id)['data']


def run(binary):
    before = fingerprints()
    evidence = {'provider': 'local_fake_only', 'real_provider': 'REAL_PROVIDER_NOT_VERIFIED', 'checks': []}
    with tempfile.TemporaryDirectory(prefix='stratide-issue22-') as temp:
        directory = Path(temp)/'agent'
        subprocess.run([str(binary), '--agent-init-fake', str(directory)], check=True, cwd=ROOT, capture_output=True, creationflags=FLAGS)
        service = Service(binary, directory)
        service.start()
        try:
            account = service.request('/api/account')
            baseline = json.dumps(account, sort_keys=True)
            service.request('/api/agent/status', expected=401, token=False)
            service.request('/api/agent/control', {'action':'pause'}, expected=403, origin=False)
            service.request('/api/agent/control', {'action':'pause'}, expected=403, headers={'Origin':'https://evil.example'})
            service.request('/api/agent/control', {'action':'pause'}, expected=401, token=False)
            service.request('/api/agent/control', {'action':'pause'}, expected=403, headers={'Sec-Fetch-Site':'cross-site'})
            service.request('/api/agent/control', {'action':'set-budget', 'limit':999999}, expected=409)
            service.request('/api/orders', {}, expected=405)
            service.request('/api/account', {}, expected=405)
            service.request('/api/agent/config', {}, expected=404)
            service.request('/api/agent/tasks/1/../../secrets', expected=404)
            service.request('/api/agent/tasks', {'name':'malicious','shell':'paper-apply','url':'http://127.0.0.1'}, expected=409)
            service.request('/api/agent/control', {'action':'model','model_id':'https://evil.example'}, expected=409)
            evidence['checks'].append('Owner-token + explicit Origin + fetch-site + narrow routes reject forgery/CSRF/commands/URLs')

            service.control('pause')
            queued = service.create('跨进程排队任务')
            cancelled = service.create('排队取消')
            service.request('/api/agent/tasks/'+cancelled+'/cancel', {})
            assert service.task(cancelled)['status'] == 'cancelled'
            service.control('model', model_id='fake-unknown')
            service.stop(); service.start()
            assert service.request('/api/agent/status')['data']['paused'] is True
            assert service.task(queued)['status'] == 'queued'
            service.control('resume')
            wait(lambda: service.task(queued)['status'] == 'completed')
            assert service.task(queued)['provider_id'] == 'fake'
            assert service.task(queued)['result']['synthetic_provider'] is True
            evidence['checks'].append('Persistent queue, graceful pause, queued cancellation and pinned default survive real process restart')

            unknown = service.create('未知付费结果')
            wait(lambda: service.task(unknown)['status'] == 'outcome_uncertain')
            service.request('/api/agent/tasks/'+unknown+'/retry', {}, expected=409)
            unknown_max = int(service.task(unknown)['calls'][0]['maximum_micro'])
            service.control('model', model_id='fake-slow')
            running = service.create('运行中取消')
            wait(lambda: len(service.task(running)['calls']) == 1)
            start = time.monotonic()
            for route in ['/api/account','/api/equity','/api/orders','/api/positions']:
                service.request(route)
            evidence['paper_gets_during_research_ms'] = round((time.monotonic()-start)*1000)
            assert evidence['paper_gets_during_research_ms'] < 1000
            service.request('/api/agent/tasks/'+running+'/cancel', {})
            wait(lambda: service.task(running)['status'] == 'cancelled')
            assert service.task(running)['result'] is not None
            assert int(service.task(running)['calls'][0]['settled_micro']) > 0
            evidence['checks'].append('Running cancellation keeps actual fake result/cost; slow Provider does not block Paper GETs')

            crash = service.create('提交后故障注入')
            wait(lambda: len(service.task(crash)['calls']) == 1 and service.task(crash)['calls'][0]['state'] == 'dispatched')
            service.stop(); service.start()
            assert service.task(crash)['status'] == 'outcome_uncertain'
            service.control('backup', model_id='fake')
            service.control('model', model_id='fake')
            time.sleep(0.6)
            assert len(service.task(crash)['calls']) == 1
            assert len(service.task(unknown)['calls']) == 1
            # Independent persisted SQL oracle, outside the Rust gate implementation.
            with closing(sqlite3.connect(directory/'agent.sqlite')) as db:
                holds = db.execute("SELECT SUM(maximum_micro) FROM calls WHERE state NOT IN ('settled','no_charge')").fetchone()[0]
                sql_calls = db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]
            status = service.request('/api/agent/status')['data']
            assert int(status['budget']['reserved_micro']) == holds >= 2*unknown_max
            assert status['automatic_fallback'] == 'disabled_explicit_owner_switch_required'
            assert status['eod']['enabled'] is False
            evidence['checks'].append('Hard process kill after dispatch preserves both unknown holds, no retry/fallback/reset; independent SQLite sum agrees')

            for _ in range(3):
                service.task(queued)
                service.request('/api/agent/tasks')
            with closing(sqlite3.connect(directory/'agent.sqlite')) as db:
                assert db.execute('SELECT COUNT(*) FROM calls').fetchone()[0] == sql_calls
            assert json.dumps(service.request('/api/account'),sort_keys=True) == baseline
            assert fingerprints() == before
            evidence['checks'].append('List/details do not infer; pinned NAV and original six-file bytes unchanged')
            evidence['frozen_report_sha256'] = before
            service.stop()
            (directory/'settings.json').write_text('{invalid',encoding='utf-8')
            service.start()
            assert json.dumps(service.request('/api/account'),sort_keys=True) == baseline
            service.request('/api/agent/status',expected=503)
            evidence['checks'].append('Invalid research configuration fails research closed while Paper API remains online')
        finally:
            service.stop()
    evidence['result'] = 'PASS'
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, default=ROOT/'target/debug/stratided.exe')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run(args.binary.resolve())
    encoded = json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(encoded+'\n',encoding='utf-8')
    print(encoded)
