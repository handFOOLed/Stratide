// Test-only fixture publisher. The production launcher has no default dataset.
//
// 用法：node tests/serve-fixture.mjs <scenario> <port>
// 场景：synthetic | empty | invalid | missing-nav | agent | agreement
// 外部可执行文件：设置 STRATIDE_DASHBOARD_BIN 指向交叉构建的 stratided.exe；
// 未设置时依次尝试仓库下 dist/app、target/debug、target/release、
// target/x86_64-pc-windows-gnu/release（当前宿主平台可执行文件名）。
import { spawn, spawnSync } from 'node:child_process';
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const [scenario, port] = process.argv.slice(2);
if (!scenario || !port) throw new Error('用法：node tests/serve-fixture.mjs <scenario> <port>');

const exeName = process.platform === 'win32' ? 'stratided.exe' : 'stratided';
function locateExe() {
  if (process.env.STRATIDE_DASHBOARD_BIN) return process.env.STRATIDE_DASHBOARD_BIN;
  const candidates = [
    path.join(root, 'dist/app', exeName),
    path.join(root, 'target/debug', exeName),
    path.join(root, 'target/release', exeName),
    path.join(root, 'target/x86_64-pc-windows-gnu/release', exeName),
    path.join(root, 'target/x86_64-pc-windows-gnu/debug', exeName),
  ];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error('未找到 stratided 可执行文件；请设置 STRATIDE_DASHBOARD_BIN 指向交叉构建产物。已尝试：\n' + candidates.join('\n'));
  }
  return found;
}
const exe = locateExe();
const assets = process.env.STRATIDE_DASHBOARD_ASSETS || path.join(root, 'apps/dashboard/dist');
const reportFixture = path.join(root, 'docs/evidence/m0-pr03/sample-report');
const runtime = await mkdtemp(path.join(tmpdir(), 'stratide-browser-' + scenario + '-'));
const runtimeHome = path.join(runtime, 'runtime-home');
const agentDir = path.join(runtime, 'agent');

/** 生成一份本地 fake 研究 Agent，并把测试预算改成 CNY ¥5/日、¥100/月。 */
async function initAgent() {
  const init = spawnSync(exe, ['--agent-init-fake', agentDir], { cwd: root, stdio: 'pipe', windowsHide: true });
  if (init.status !== 0) {
    throw new Error('agent fixture 初始化失败：' + (init.stderr?.toString() || init.status));
  }
  const settingsPath = path.join(agentDir, 'settings.json');
  const settings = JSON.parse(await readFile(settingsPath, 'utf8'));
  settings.budget = {
    currency: 'CNY',
    timezone: 'Asia/Shanghai',
    daily_limit_micro: 5_000_000,
    monthly_limit_micro: 100_000_000,
  };
  for (const model of settings.models) {
    if (model.price) model.price.currency = 'CNY';
  }
  await writeFile(settingsPath, JSON.stringify(settings, null, 2));
  // --agent-init-fake 已写入 TST 预算身份；重建存储与 owner-token，避免币种身份冲突。
  for (const name of ['agent.sqlite', 'agent.sqlite-wal', 'agent.sqlite-shm', 'agent.sqlite-journal', 'owner-token', 'agent.lock']) {
    await rm(path.join(agentDir, name), { force: true });
  }
}

const args = ['--port', String(port), '--assets-dir', assets, '--agent-dir', agentDir, '--runtime-home', runtimeHome];
if (scenario === 'synthetic' || scenario === 'agent' || scenario === 'agreement') {
  args.push('--report-dir', reportFixture);
} else if (scenario === 'historical') {
  if (!process.env.STRATIDE_HISTORICAL_REPORT) throw new Error('需要显式设置 STRATIDE_HISTORICAL_REPORT');
  args.push('--report-dir', process.env.STRATIDE_HISTORICAL_REPORT);
  if (process.env.STRATIDE_EVALUATION_FILE) args.push('--evaluation-file', process.env.STRATIDE_EVALUATION_FILE);
} else if (scenario === 'invalid' || scenario === 'missing-nav') {
  const report = path.join(runtime, 'report');
  await cp(reportFixture, report, { recursive: true });
  if (scenario === 'invalid') {
    await writeFile(path.join(report, 'daily.csv'), 'broken');
  } else {
    const raw = JSON.parse(await readFile(path.join(report, 'report.json'), 'utf8'));
    raw.daily.at(-1).nav_fen = null;
    raw.daily.at(-1).valuation_error = '测试专用：缺少可信收盘估值';
    raw.ending_nav_fen = null;
    raw.total_return_bps = null;
    raw.max_daily_observation_drawdown_bps = null;
    await writeFile(path.join(report, 'report.json'), JSON.stringify(raw));
    const headers = (await readFile(path.join(reportFixture, 'daily.csv'), 'utf8')).split('\n')[0].split(',');
    const cell = (value) => value === null ? '' : /[,"\n]/.test(String(value)) ? '"' + String(value).replaceAll('"', '""') + '"' : String(value);
    await writeFile(path.join(report, 'daily.csv'), headers.join(',') + '\n' + raw.daily.map((row) => headers.map((header) => cell(row[header])).join(',')).join('\n') + '\n');
  }
  args.push('--report-dir', report);
} else if (scenario !== 'empty') {
  throw new Error('未知场景：' + scenario);
}

await initAgent();
const child = spawn(exe, args, { cwd: root, stdio: 'inherit', windowsHide: true });
child.on('error', (error) => { console.error(error.message); process.exit(1); });
child.on('exit', (code) => process.exit(code ?? 1));

const origin = 'http://127.0.0.1:' + port;
async function api(requestPath, init = {}) {
  const headers = {
    Accept: 'application/json',
    Origin: origin,
    ...(init.body === undefined ? {} : { 'Content-Type': 'application/json' }),
    ...(init.headers || {}),
  };
  return fetch(origin + requestPath, { ...init, headers });
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

try {
  let healthy = false;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) throw new Error('fixture 服务提前退出：' + child.exitCode);
    try {
      if ((await fetch(origin + '/api/health')).ok) { healthy = true; break; }
    } catch { /* 等待服务启动 */ }
    await sleep(200);
  }
  if (!healthy) throw new Error('fixture 服务未在限定时间内就绪');
  if (scenario !== 'agreement') {
    // 首次使用协议：测试启动时通过真实接口接受，页面之后直接进入主界面。
    const status = await (await api('/api/agent/consent')).json();
    if (status.data?.required) {
      const accepted = await api('/api/agent/consent', { method: 'POST', body: '{}' });
      if (!accepted.ok) throw new Error('接受首次使用协议失败：' + accepted.status + ' ' + (await accepted.text()));
    }
  }
} catch (error) {
  child.kill();
  console.error(error.message);
  process.exit(1);
}

for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { child.kill(); process.exit(0); });
process.on('exit', () => { if (child.exitCode === null) child.kill(); });
