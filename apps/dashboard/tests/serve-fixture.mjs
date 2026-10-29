// Test-only fixture publisher. The production launcher has no default dataset.
import { spawn, spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, cp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const [scenario, port] = process.argv.slice(2);
const args = ['--port',port];
const fixture = path.join(root,'docs/evidence/m0-pr03/sample-report');
if (scenario === 'synthetic' || scenario === 'agent') args.push('--report-dir',fixture);
else if (scenario === 'historical') {
  if (!process.env.STRATIDE_HISTORICAL_REPORT) throw new Error('Explicit historical report required');
  args.push('--report-dir',process.env.STRATIDE_HISTORICAL_REPORT);
  if (process.env.STRATIDE_EVALUATION_FILE) args.push('--evaluation-file',process.env.STRATIDE_EVALUATION_FILE);
} else if (scenario === 'invalid' || scenario === 'missing-nav') {
  const temp = await mkdtemp(path.join(tmpdir(),'stratide-dashboard-test-'));
  const report = path.join(temp,'report');
  await cp(fixture,report,{recursive:true});
  if (scenario === 'invalid') await writeFile(path.join(report,'daily.csv'),'broken');
  else {
    const raw = JSON.parse(await readFile(path.join(report,'report.json'),'utf8'));
    raw.daily.at(-1).nav_fen = null; raw.daily.at(-1).valuation_error = '测试专用：缺少可信收盘估值';
    raw.ending_nav_fen = null; raw.total_return_bps = null; raw.max_daily_observation_drawdown_bps = null;
    await writeFile(path.join(report,'report.json'),JSON.stringify(raw));
    const headers = (await readFile(path.join(fixture,'daily.csv'),'utf8')).split('\n')[0].split(',');
    const cell = value => value === null ? '' : /[,"\n]/.test(String(value)) ? `"${String(value).replaceAll('"','""')}"` : String(value);
    await writeFile(path.join(report,'daily.csv'),`${headers.join(',')}\n${raw.daily.map(r=>headers.map(h=>cell(r[h])).join(',')).join('\n')}\n`);
  }
  args.push('--report-dir',report);
}
args.push('--assets-dir',path.join(root,'apps/dashboard/dist'));
const exe = process.env.STRATIDE_DASHBOARD_BIN || path.join(root,'target/debug',process.platform === 'win32' ? 'stratided.exe' : 'stratided');
if (scenario === 'agent') {
  const dir=await mkdtemp(path.join(tmpdir(),'stratide-agent-browser-'));
  const init=spawnSync(exe,['--agent-init-fake',dir],{cwd:root,stdio:'pipe',windowsHide:true});
  if(init.status!==0) throw new Error('fake fixture initialization failed');
  const evidence=path.join(root,'state/issue22-browser'); await mkdir(evidence,{recursive:true});
  await writeFile(path.join(evidence,'session.json'),JSON.stringify({token:(await readFile(path.join(dir,'owner-token'),'utf8')).trim()}));
  args.push('--agent-dir',dir);
}
const child = spawn(exe,args,{cwd:root,stdio:'inherit',windowsHide:true});
child.on('error', error=>{ console.error(error.message); process.exit(1); });
child.on('exit', code=>process.exit(code ?? 1));
for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>{ child.kill(); });
process.on('exit',()=>{ child.kill(); });
