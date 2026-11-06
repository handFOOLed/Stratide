import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  dataStatusView,
  dependencyStatusView,
  failureReasonText,
  humanReasonText,
  overallSystemStatus,
  protectionStatusView,
  researchStatusView,
  researchTaskName,
  supervisorDisplayView,
  taskStatusView,
} from '../src/lib/status.ts';
import { countText, currencySymbol, formatMicroMoney } from '../src/lib/format.ts';

const agentStatus = {
  paused: false,
  worker_error: null,
  default_model: 'deepseek',
  models: [{ id: 'deepseek' }],
  budget: { state: 'configured' },
};

test('task status uses only the five unified states and never renders raw enums', () => {
  assert.equal(taskStatusView('queued', null, null).label, '排队中');
  assert.equal(taskStatusView('running', null, null).kind, 'progress');
  assert.equal(taskStatusView('completed', 'RESEARCH_SAVED', '结论 A').reason, '结论 A');
  const failed = taskStatusView('failed', 'PROVIDER_UNREACHABLE', null);
  assert.equal(failed.kind, 'error');
  assert.equal(failed.reason, '无法连接 AI 服务');
  assert.equal(taskStatusView('failed', null, null).reason, '原因未记录');
  assert.equal(taskStatusView('failed', 'UNKNOWN_NEW_CODE', null).reason, '原因未记录');
  assert.equal(taskStatusView('mystery_state', null, null).label, '状态未知');
  assert.equal(taskStatusView('cancelled', null, null).kind, 'unset');
});

test('known production reasons are translated; unknown codes stay in diagnostics', () => {
  assert.equal(humanReasonText('MARKET_RESEARCH_LOCAL_FAILURE'), '本地研究阶段出现异常，研究已安全停止');
  assert.equal(humanReasonText('LATE_OR_FUTURE_CATALOG_NOT_DECISION_EVIDENCE'), '行情目录为晚到或回填数据，不能作为当日研究依据');
  assert.equal(humanReasonText('SOME_FUTURE_CODE'), null);
  assert.equal(humanReasonText('这是一句人话'), '这是一句人话');
  assert.equal(failureReasonText(null), '原因未记录');
});

test('trade protection never treats a missing risk record as safe', () => {
  assert.equal(protectionStatusView({ risk: null, dataMissing: false }).kind, 'unset');
  assert.equal(protectionStatusView({ risk: null, dataMissing: false }).label, '交易保护状态未记录');
  const empty = protectionStatusView({ risk: { account_freezes: [], strategy_freezes: [] }, dataMissing: false });
  assert.equal(empty.kind, 'ok');
  assert.equal(empty.label, '交易保护正常');
  const locked = protectionStatusView({ risk: { account_freezes: ['DailyLoss'], strategy_freezes: ['Manual'] }, dataMissing: false });
  assert.equal(locked.kind, 'attention');
  assert.match(locked.reason, /当日亏损达到限制/);
  assert.match(locked.reason, /人工暂停交易/);
});

test('dependency states map to unified states, including the local prediction engine', () => {
  assert.equal(dependencyStatusView('timesfm', 'CONFIGURED', 'WSL_PROBE_REQUIRED', null).kind, 'attention');
  assert.match(
    dependencyStatusView('timesfm', 'CONFIGURED', 'WSL_PROBE_REQUIRED', null).reason,
    /需要先检测/,
  );
  assert.equal(dependencyStatusView('timesfm', 'READY', null, null).kind, 'ok');
  assert.equal(dependencyStatusView('market_eod', 'NOT_CONFIGURED', null, null).kind, 'unset');
  assert.equal(dependencyStatusView('tushare_credential', 'MISSING', null, null).kind, 'attention');
  assert.equal(dependencyStatusView('python', 'READY', null, null).kind, 'ok');
});

test('overall status counts persisted timesfm ready toward 7/7', () => {
  const runtime = {
    service: { healthy: true },
    supervisor: { status: 'RUNNING', reason: 'OK' },
    dependencies: {
      python: { state: 'READY' },
      wsl: { state: 'READY', configured: true },
      timesfm: { state: 'READY' },
      tushare_credential: { state: 'READY' },
      market_eod: { state: 'INITIALIZED' },
      paper_account: { state: 'CONFIGURED' },
      agent: { state: 'RUNNING' },
    },
  };
  const overall = overallSystemStatus({
    serviceOnline: true,
    healthChecking: false,
    healthErrorCode: null,
    runtime,
    runtimeErrorCode: null,
  });
  assert.equal(overall.readyCount, 7);
  assert.equal(overall.problems.length, 0);
});

test('supervisor display avoids STARTING badge with OK running copy', () => {
  const starting = supervisorDisplayView('STARTING', 'OK');
  assert.equal(starting.kind, 'progress');
  assert.equal(starting.label, '正在启动');
  assert.match(starting.reason, /健康检查/);
  const running = supervisorDisplayView('RUNNING', 'OK');
  assert.equal(running.kind, 'ok');
  assert.equal(running.reason, '后台任务运行正常');
});

test('research status reports a blocked latest task instead of claiming normal', () => {
  const ready = researchStatusView({
    ready: true,
    paused: false,
    status: agentStatus,
    errorCode: null,
    runningTasks: 0,
    latestTaskStatus: 'blocked',
    latestTaskReason: 'MARKET_RESEARCH_LOCAL_FAILURE',
  });
  assert.equal(ready.kind, 'attention');
  assert.equal(ready.label, '最近一次研究未运行');
  assert.match(ready.reason, /本地研究阶段出现异常/);
  const normal = researchStatusView({
    ready: true,
    paused: false,
    status: agentStatus,
    errorCode: null,
    runningTasks: 0,
    latestTaskStatus: 'completed',
    latestTaskReason: 'RESEARCH_SAVED',
  });
  assert.equal(normal.kind, 'ok');
});

test('data status is honest about missing snapshots', () => {
  const missing = dataStatusView({ meta: null, errorCode: 'NO_SNAPSHOT', errorMessage: null, gaps: 0 });
  assert.equal(missing.kind, 'attention');
  assert.equal(missing.label, '未设置');
  const gaps = dataStatusView({ meta: { last_day: '20261102' }, errorCode: null, errorMessage: null, gaps: 1 });
  assert.equal(gaps.kind, 'attention');
});

test('counts, budgets and task names share one format', () => {
  assert.equal(countText('0', '笔'), '0 笔');
  assert.equal(countText(null, '只'), '— 只');
  assert.equal(currencySymbol('CNY'), '¥');
  assert.equal(formatMicroMoney('5000000', 'CNY'), '¥5.00');
  assert.equal(formatMicroMoney('8469', 'CNY'), '¥0.01');
  assert.equal(formatMicroMoney('-1000000', 'CNY'), '−¥1.00');
  assert.equal(formatMicroMoney('1000000', 'TST'), '1.00 TST');
  assert.equal(researchTaskName('2026-11-05T13:06:25Z', '全市场研究阻断 20261105'), '2026-11-05 · 全市场研究阻断 20261105');
  assert.equal(researchTaskName(null, null), '研究任务');
});
