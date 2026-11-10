import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildSync } from 'esbuild';
import { mkdirSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { JSDOM } from 'jsdom';
import { marketSummaryFrom, mergeMarketRead } from '../src/lib/runtimeRefresh.ts';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://127.0.0.1/',
  pretendToBeVisual: true,
});
const { window } = dom;
globalThis.window = window;
globalThis.document = window.document;
globalThis.localStorage = window.localStorage;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.MutationObserver = window.MutationObserver;
globalThis.getComputedStyle = window.getComputedStyle.bind(window);
window.matchMedia = () => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
});
globalThis.matchMedia = window.matchMedia;

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '.render-tmp');
mkdirSync(dir, { recursive: true });
const outfile = path.join(dir, 'surfaces.js');
buildSync({
  stdin: {
    contents: `
      import { createElement, act } from 'react';
      import { createRoot } from 'react-dom/client';
      import { OverviewPage } from './src/pages/OverviewPage.tsx';
      import { RuntimePanel } from './src/components/domain/RuntimePanel.tsx';
      import { ThemeProvider } from './src/state/ThemeProvider.tsx';
      import { ToastProvider } from './src/components/ui/Toast.tsx';
      import { useRuntime } from './src/state/useRuntime.ts';

      export { act };

      export function mount(node) {
        const host = document.createElement('div');
        document.body.appendChild(host);
        const root = createRoot(host);
        const view = {
          host,
          render(next) {
            act(() => {
              root.render(next);
            });
          },
          unmount() {
            act(() => {
              root.unmount();
            });
            host.remove();
          },
        };
        view.render(node);
        return view;
      }

      export function overviewNode(props) {
        return createElement(ToastProvider, null, createElement(OverviewPage, props));
      }

      export function settingsNode(props) {
        return createElement(
          ThemeProvider,
          null,
          createElement(ToastProvider, null, createElement(RuntimePanel, props)),
        );
      }

      export function mountRuntime(holder, settings) {
        function Probe() {
          holder.current = useRuntime();
          const market = holder.current.market;
          holder.seen.push(
            market === null
              ? null
              : { complete: market.backfillComplete, verification: market.verification },
          );
          return settings ? settingsNode({ ...settings, runtime: holder.current }) : null;
        }
        return mount(createElement(Probe));
      }
    `,
    resolveDir: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
    sourcefile: 'surfaces.tsx',
    loader: 'tsx',
  },
  bundle: true,
  format: 'esm',
  platform: 'browser',
  outfile,
    jsx: 'automatic',
    define: {
      __UI_VERSION__: '"0.3.2"',
      __BUILD_SHA__: '"test"',
    },
    external: ['react', 'react-dom', 'react-dom/client'],
  });

const ui = await import(pathToFileURL(outfile).href);

const fullProgress = { running: false, progress: { sessions: 84, sessions_ready: 84, remaining: 0 } };

function report(flag, sessions = 84) {
  return { sessions_ready: sessions, gaps: [], coverage_complete: flag };
}

function dep(state) {
  return { state, reason: null, note: null };
}

const runtimeStatus = {
  managed: true,
  product_version: '0.3.2',
  build: { version: '0.3.2', commit: 'test', built_at: null },
  repo_url: null,
  issues_url: null,
  home: 'C:/Stratide',
  app_dir: 'C:/Stratide',
  data_root: 'C:/Stratide/data',
  logs_dir: 'C:/Stratide/logs',
  port: 8730,
  config_error: null,
  setup_complete: true,
  autostart: { task_name: 'Stratide', exists: false, enabled: false, mechanism: 'none', detail: '' },
  supervisor: {
    running: true,
    status: 'RUNNING',
    reason: 'OK',
    pid: 1,
    instance_id: 'i',
    started_at: '2026-11-06T00:00:00Z',
    updated_at: '2026-11-06T00:00:00Z',
    dashboard: null,
    watch: { pid: 2, started_at: '2026-11-06T00:00:00Z', restarts: 0 },
  },
  service: { healthy: true, instance_id: 'i' },
  dependencies: {
    python: dep('READY'),
    wsl: dep('READY'),
    timesfm: dep('READY'),
    tushare_credential: dep('CONFIGURED'),
    market_eod: dep('INITIALIZED'),
    paper_account: dep('INITIALIZED'),
    agent: dep('READY'),
  },
  log_tail: [],
};

const agent = {
  token: null,
  phase: 'ready',
  status: {
    default_model: 'market-deepseek-fusion',
    paused: false,
    worker_error: null,
    worker_error_text: null,
    eod: { enabled: false, latest: null },
    models: [{ id: 'market-deepseek-fusion' }],
    budget: {
      state: 'configured',
      currency: 'CNY',
      daily_limit_micro: '5000000',
      monthly_limit_micro: '100000000',
      daily_settled_micro: '0',
      monthly_settled_micro: '0',
      reserved_micro: '0',
    },
  },
  tasks: [],
  error: null,
  busy: null,
  refreshing: false,
  lastUpdated: null,
};

const health = {
  data: {
    service: 'online',
    paper_only: true,
    market_data: 'local',
    forward_account: 'paper',
    agent: 'off',
    notifications: 'off',
    refresh_policy: 'manual',
  },
  error: null,
  checking: false,
  checkedAt: 1,
  refresh() {},
};

const deployment = { deployment_id: 'd', frozen_version: 'v', group_id: 'g', strategy_id: 's' };

const paper = {
  phase: 'ready',
  bundle: {
    account: {
      account_id: 'paper',
      day: '20261105',
      nav_fen: '100',
      cash_fen: '100',
      available_cash_fen: '100',
      reserved_cash_fen: '0',
      session_pnl_fen: '0',
      cumulative_pnl_fen: '0',
      total_return_bps: '0',
      max_daily_observation_drawdown_bps: '0',
      total_fee_fen: '0',
      initial_nav_fen: '100',
      external_flow_total_fen: '0',
      valuation_error: null,
      risk: {
        account_id: 'paper',
        cash_flow_adjusted_peak: '100',
        account_freezes: [],
        strategy_freezes: [],
        deployment,
      },
      deployment,
    },
    equity: [],
    positions: [],
    strategies: [],
    fills: [],
    orders: [],
  },
  meta: {
    as_of: '20261105',
    last_day: '20261105',
    first_day: '20261105',
    last_valid_valuation_at: '2026-11-05T08:00:00Z',
    mode: 'synthetic',
    source: 'fixture',
    source_version: '0',
    evidence_class: 'synthetic',
    publication: 'local',
    refresh_policy: 'manual',
    forward_account: 'paper',
    market_freshness: 'stale',
    gaps: [],
    snapshot_id: 'snap',
    report_sha256: 'r',
    input_sha256: 'i',
    ledger_head: 'h',
    validation: 'ok',
  },
  error: null,
  refreshing: false,
  loadedAt: Date.parse('2026-11-06T00:00:00Z'),
  stale: false,
  refresh() {},
};

function runtimeState(market) {
  return {
    status: runtimeStatus,
    error: null,
    checking: false,
    checkedAt: 1,
    market,
    refresh() {},
  };
}

function storageFlag() {
  return window.localStorage.getItem('stratide.checklist-dismissed');
}

function meterText(host) {
  const meter = host.querySelector('.backfill-meter');
  assert.ok(meter, 'backfill meter missing');
  return meter.textContent;
}

function backfillText(host) {
  const block = host.querySelector('.backfill');
  assert.ok(block, 'settings backfill block missing');
  return block.textContent;
}

test('a deferred credential check does not open setup or remount an edited token field', () => {
  const state = runtimeState(null);
  const light = {
    ...runtimeStatus,
    status_refresh: 'light',
    dependencies: {
      ...runtimeStatus.dependencies,
      tushare_credential: { state: 'UNKNOWN', reason: 'CREDENTIAL_CHECK_DEFERRED' },
    },
  };
  const view = ui.mount(ui.settingsNode({ health, runtime: state, paper, agent }));
  const setup = view.host.querySelector('[data-testid="setup-block"]');
  assert.equal(setup.open, false);
  view.render(ui.settingsNode({ health, runtime: { ...state, status: light }, paper, agent }));
  assert.ok(view.host.querySelector('[data-testid="setup-block"]') === setup, 'setup was replaced on a light snapshot');
  assert.equal(setup.open, false);
  const token = setup.querySelector('input');
  setup.open = true;
  ui.act(() => setup.dispatchEvent(new window.Event('toggle')));
  token.focus();
  view.render(ui.settingsNode({ health, runtime: state, paper, agent }));
  assert.equal(setup.open, true);
  assert.equal(document.activeElement, token);
  setup.open = false;
  ui.act(() => setup.dispatchEvent(new window.Event('toggle')));
  const missing = { ...light, status_refresh: undefined,
    dependencies: { ...light.dependencies, tushare_credential: dep('MISSING') } };
  view.render(ui.settingsNode({ health, runtime: { ...state, status: missing }, paper, agent }));
  assert.equal(setup.open, true);
  assert.match(token.placeholder, /粘贴/);
  view.unmount();
});

test('settings panel renders 84/84 false as unverified, then true, then a failed read', () => {
  const rejected = marketSummaryFrom(fullProgress, report(false));
  const view = ui.mount(ui.settingsNode({ health, runtime: runtimeState(rejected), paper, agent }));
  let text = backfillText(view.host);
  assert.match(text, /待校验/);
  assert.match(text, /100%/);
  assert.match(text, /已下载 84\/84/);
  assert.equal(text.includes('已就绪'), false);
  assert.equal(text.includes('历史行情已就绪'), false);
  assert.equal(view.host.querySelector('[data-testid="backfill-restart"]'), null);
  assert.ok(view.host.querySelector('[data-testid="backfill-start"]'));

  const verified = marketSummaryFrom(fullProgress, report(true));
  view.render(ui.settingsNode({ health, runtime: runtimeState(verified), paper, agent }));
  text = backfillText(view.host);
  assert.match(text, /已完成/);
  assert.match(text, /历史行情已就绪/);
  assert.ok(view.host.querySelector('[data-testid="backfill-restart"]'));

  const failed = mergeMarketRead(
    verified,
    marketSummaryFrom(fullProgress, null, 'MARKET_STATUS_TIMEOUT'),
  );
  const stale = mergeMarketRead(failed, marketSummaryFrom(fullProgress, null, 'MARKET_STATUS_TIMEOUT'));
  view.render(ui.settingsNode({ health, runtime: runtimeState(stale), paper, agent }));
  text = backfillText(view.host);
  assert.match(text, /无法读取/);
  assert.match(text, /—/);
  assert.equal(text.includes('已就绪'), false);
  assert.equal(text.includes('100%'), false);
  view.unmount();
});

test('overview checklist storage follows a fresh false across reload', async () => {
  window.localStorage.setItem('stratide.checklist-dismissed', '1');
  const verified = marketSummaryFrom(fullProgress, report(true));
  const rejected = marketSummaryFrom(fullProgress, report(false));

  const hidden = ui.mount(
    ui.overviewNode({ paper, health, runtime: runtimeState(verified), agent }),
  );
  assert.equal(hidden.host.querySelector('.checklist'), null);
  assert.equal(hidden.host.textContent.includes('历史行情已就绪'), false);
  assert.equal(storageFlag(), '1');
  hidden.unmount();

  window.localStorage.setItem('stratide.checklist-dismissed', '1');
  const shown = ui.mount(
    ui.overviewNode({ paper, health, runtime: runtimeState(null), agent }),
  );
  assert.equal(shown.host.querySelector('.checklist'), null);
  assert.equal(shown.host.textContent.includes('历史行情已就绪'), false);
  shown.render(ui.overviewNode({ paper, health, runtime: runtimeState(rejected), agent }));
  assert.ok(shown.host.querySelector('.checklist'));
  const fresh = meterText(shown.host);
  assert.match(fresh, /校验未通过/);
  assert.equal(fresh.includes('已就绪'), false);
  assert.equal(storageFlag(), '0');
  shown.unmount();

  window.localStorage.setItem('stratide.checklist-dismissed', '1');
  const reloaded = ui.mount(
    ui.overviewNode({ paper, health, runtime: runtimeState(rejected), agent }),
  );
  assert.ok(reloaded.host.querySelector('.checklist'), 'fresh false stayed hidden after reload');
  assert.equal(meterText(reloaded.host).includes('已就绪'), false);
  assert.equal(storageFlag(), '0');
  reloaded.unmount();
});

test('a verified checklist hides, a later false brings it back, and recovery hides it again', () => {
  window.localStorage.removeItem('stratide.checklist-dismissed');
  const verified = marketSummaryFrom(fullProgress, report(true));
  const view = ui.mount(
    ui.overviewNode({ paper, health, runtime: runtimeState(verified), agent }),
  );
  assert.equal(view.host.querySelector('.checklist'), null);
  assert.equal(storageFlag(), '1');

  const rejected = mergeMarketRead(verified, marketSummaryFrom(fullProgress, report(false)));
  view.render(ui.overviewNode({ paper, health, runtime: runtimeState(rejected), agent }));
  assert.ok(view.host.querySelector('.checklist'));
  assert.match(meterText(view.host), /校验未通过/);
  assert.equal(meterText(view.host).includes('已就绪'), false);
  assert.equal(storageFlag(), '0');

  view.unmount();
  window.localStorage.setItem('stratide.checklist-dismissed', '1');
  const stillFalse = ui.mount(
    ui.overviewNode({ paper, health, runtime: runtimeState(rejected), agent }),
  );
  assert.ok(stillFalse.host.querySelector('.checklist'));
  stillFalse.unmount();

  const failed = mergeMarketRead(
    rejected,
    marketSummaryFrom(fullProgress, null, 'MARKET_STATUS_TIMEOUT'),
  );
  const failedView = ui.mount(
    ui.overviewNode({ paper, health, runtime: runtimeState(failed), agent }),
  );
  assert.ok(failedView.host.querySelector('.checklist'));
  assert.match(meterText(failedView.host), /超时|无法读取/);
  assert.equal(meterText(failedView.host).includes('已就绪'), false);
  assert.equal(storageFlag(), '0');
  failedView.unmount();

  const recovered = mergeMarketRead(failed, marketSummaryFrom(fullProgress, report(true)));
  const done = ui.mount(
    ui.overviewNode({ paper, health, runtime: runtimeState(recovered), agent }),
  );
  assert.equal(done.host.querySelector('.checklist'), null);
  assert.equal(done.host.textContent.includes('历史行情已就绪'), false);
  assert.equal(storageFlag(), '1');
  done.unmount();
});

test('starting backfill keeps setup closed and publishes progress through slow warehouse reads', async () => {
  const envelope = (data) => ({ ok: true, status: 200, json: async () => ({ api_version: 1, data }) });
  const pending = [];
  const timers = new Map();
  const { setInterval, clearInterval } = window;
  let timer = 0;
  let statusReads = 0;
  let phase = 'IDLE';
  window.setInterval = (fn, delay) => { timers.set(++timer, { fn, delay }); return timer; };
  window.clearInterval = (id) => timers.delete(id);
  const light = {
    ...runtimeStatus,
    status_refresh: 'light',
    dependencies: {
      ...runtimeStatus.dependencies,
      tushare_credential: { state: 'UNKNOWN', reason: 'CREDENTIAL_CHECK_DEFERRED' },
    },
  };
  globalThis.fetch = async (url, init) => {
    if (url === '/api/runtime/status') {
      statusReads += 1;
      return envelope(phase === 'IDLE' ? runtimeStatus : light);
    }
    const { action } = JSON.parse(init.body);
    if (action === 'backfill') {
      phase = 'QUEUED';
      return envelope({ state: 'QUEUED' });
    }
    if (action === 'backfill-state') {
      return envelope({
        phase,
        running: ['QUEUED', 'RUNNING'].includes(phase),
        progress: phase === 'RUNNING' ? { sessions_ready: 30, remaining: 54 } : null,
      });
    }
    assert.equal(action, 'status');
    if (phase === 'IDLE') return envelope(report(false, 0));
    return new Promise((resolve) => pending.push({ resolve, signal: init.signal }));
  };
  const holder = { current: null, seen: [] };
  const view = ui.mountRuntime(holder, { health, paper, agent });
  const tick = async () => ui.act(async () => {
    for (const entry of [...timers.values()]) if (entry.delay === 2000) entry.fn();
  });
  try {
    await ui.act(async () => {});
    const setup = view.host.querySelector('[data-testid="setup-block"]');
    await ui.act(async () => view.host.querySelector('[data-testid="backfill-start"]').click());
    assert.match(backfillText(view.host), /启动中/);
    assert.equal(setup.open, false);

    phase = 'RUNNING';
    await tick();
    assert.match(backfillText(view.host), /进行中/);
    assert.match(backfillText(view.host), /30\/84/);
    assert.equal(pending.length, 0, 'do not open the warehouse while the batch holds the writer lock');

    phase = 'VERIFYING';
    await tick();
    assert.match(backfillText(view.host), /待校验/);
    assert.equal(pending.length, 1);
    const before = statusReads;
    await tick();
    await tick();
    assert.equal(statusReads, before + 2);
    assert.equal(pending.length, 1);
    assert.equal(pending[0].signal.aborted, false);
    await ui.act(async () => pending[0].resolve(envelope(report(true))));
    assert.match(backfillText(view.host), /已完成/);
    assert.equal(setup.open, false);
  } finally {
    view.unmount();
    window.setInterval = setInterval;
    window.clearInterval = clearInterval;
  }
});

test('a cancelled market poll cannot publish a stale true over a later false', async () => {
  const queue = [];
  globalThis.fetch = async (url, init) => {
    const path = String(url);
    if (path === '/api/runtime/status') {
      return { ok: true, status: 200, json: async () => ({ api_version: 1, data: runtimeStatus, error: null }) };
    }
    if (path === '/api/runtime/market') {
      const body = JSON.parse(init.body);
      if (body.action === 'backfill-state') {
        return { ok: true, status: 200, json: async () => ({ api_version: 1, data: fullProgress, error: null }) };
      }
      if (body.action === 'status') {
        return new Promise((resolve) => {
          queue.push({ resolve, signal: init.signal });
        });
      }
    }
    throw new Error('unexpected fetch ' + path);
  };

  const holder = { current: null, seen: [] };
  const view = ui.mountRuntime(holder);
  await ui.act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  assert.equal(queue.length, 1);
  assert.equal(holder.seen.some((item) => item !== null && item.complete === true), false);

  ui.act(() => {
    holder.current.refresh();
  });
  queue[0].resolve({
    ok: true,
    status: 200,
    json: async () => ({ api_version: 1, data: report(true), error: null }),
  });
  await ui.act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  assert.equal(holder.seen.some((item) => item !== null && item.complete === true), false);
  assert.ok(queue.length >= 2);

  queue[queue.length - 1].resolve({
    ok: true,
    status: 200,
    json: async () => ({ api_version: 1, data: report(false), error: null }),
  });
  await ui.act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  assert.equal(holder.current.market.backfillComplete, false);
  assert.equal(holder.current.market.verification, 'rejected');
  assert.equal(holder.seen.some((item) => item !== null && item.complete === true), false);
  view.unmount();
  rmSync(dir, { recursive: true, force: true });
});
