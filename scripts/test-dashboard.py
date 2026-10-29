"""Issue #20 real-process acceptance. Read existing reports; never run/replay a ledger.

Requires a built frontend and stratided. Optional historical/evaluation paths are
explicit Owner-selected local inputs. Output contains structural evidence, no prices.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FILES = ('report.json', 'events.json', 'daily.csv', 'orders.csv', 'fills.csv', 'positions.csv')


def fingerprints(report):
    paths = [report / name for name in FILES]
    ledger = report.parent / 'ledger'
    if ledger.is_dir():
        paths += sorted(p for p in ledger.rglob('*') if p.is_file())
    return {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in paths}


def get(url, expected=200, method='GET', headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == expected, f'HTTP {response.status}, expected {expected}'
        assert response.headers.get('Access-Control-Allow-Origin') is None
        return json.load(response)


def start(binary, report, evaluation=None):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    args = [str(binary), '--port', str(port), '--report-dir', str(report),
            '--assets-dir', str(ROOT / 'apps/dashboard/dist')]
    if evaluation:
        args += ['--evaluation-file', str(evaluation)]
    process = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
    url = f'http://127.0.0.1:{port}'
    try:
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            assert process.poll() is None, 'service exited before readiness'
            try:
                if get(url+'/api/health')['data']['service'] == 'online':
                    return process, url
            except OSError:
                time.sleep(0.05)
        raise AssertionError('service readiness timeout')
    except BaseException:
        process.terminate()
        process.wait(timeout=5)
        raise


def stop(process):
    process.terminate()
    process.wait(timeout=5)


def run_case(binary, report, mode, evaluation=None):
    report = report.resolve()
    before = fingerprints(report)
    raw = json.loads((report/'report.json').read_bytes())
    assert raw['mode'] == mode
    process, url = start(binary, report, evaluation)
    try:
        a = get(url+'/api/account')
        assert a['snapshot']['mode'] == mode
        assert a['snapshot']['source_version'] == raw['source_version']
        assert a['snapshot']['last_day'] == str(raw['last_day'])
        assert a['data']['nav_fen'] == (str(raw['ending_nav_fen']) if raw['ending_nav_fen'] is not None else None)
        assert a['data']['cash_fen'] == str(raw['ending_cash_fen'])
        equity = get(url+'/api/equity')['data']
        fills = get(url+'/api/fills')['data']
        orders = get(url+'/api/orders')['data']
        assert len(equity) == len(raw['daily'])
        assert len(fills) == len(raw['fills'])
        assert len(orders) == len(raw['orders'])
        for row, original in zip(equity, raw['daily']):
            assert row['nav_fen'] == (str(original['nav_fen']) if original['nav_fen'] is not None else None)
        assert sum(int(f['fee_fen']) for f in fills) == raw['total_fee_fen']
        for order in orders:
            expected = sum(f['quantity'] for f in raw['fills'] if str(f['order_id']) == order['order_id'])
            assert int(order['confirmed_filled_shares']) == expected
        assert get(url+'/api/orders', 405, method='POST')['error']['code'] == 'READ_ONLY'
        assert get(url+'/api/account?path=../../secret', 404)['data'] is None
        assert get(url+'/api/account', 403, headers={'Origin': 'https://untrusted.example'})['data'] is None
        assert get(url+'/api/account') == a, 'refresh must retain the pinned account'
        if evaluation:
            assert get(url+'/api/research')['data']['results'][0]['account_inclusion'] is False
    finally:
        stop(process)
    restarted, url = start(binary, report, evaluation)
    try:
        assert get(url+'/api/account') == a, 'same source must yield identical account after restart'
    finally:
        stop(restarted)
    assert before == fingerprints(report), 'original frozen reports/ledger files changed'
    if mode == 'historical_replay':
        assert len(equity) == 68, 'this acceptance requires the explicit 68-day frozen output'
    return dict(mode=mode, source_version=raw['source_version'], first_day=raw['first_day'],
                last_day=raw['last_day'], sessions=len(equity), fills=len(fills), orders=len(orders),
                report_sha256=hashlib.sha256((report/'report.json').read_bytes()).hexdigest(),
                original_files_checked=len(before), original_bytes_and_mtime_unchanged=True,
                refresh_pinned=True, restart_identical=True, read_only_http=True,
                financial_values_match_report=True, research_separate=True if evaluation else 'NOT_CONFIGURED')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, default=ROOT/'target/debug/stratided.exe')
    p.add_argument('--historical-report', type=Path)
    p.add_argument('--evaluation-file', type=Path)
    p.add_argument('--out', type=Path, default=ROOT/'state/issue20-selftest.json')
    args = p.parse_args()
    cases = [run_case(args.binary.resolve(), ROOT/'docs/evidence/m0-pr03/sample-report', 'synthetic_test')]
    if args.historical_report:
        cases.append(run_case(args.binary.resolve(), args.historical_report, 'historical_replay', args.evaluation_file))
    result = dict(scope='developer_self_test_not_independent_acceptance', cases=cases,
                  historical_68='VERIFIED' if args.historical_report else 'NOT_VERIFIED')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
