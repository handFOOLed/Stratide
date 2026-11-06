import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  backfillReadFailure,
  createRuntimeRefreshLocks,
  marketSummaryFrom,
  refreshRuntimeSnapshot,
} from '../src/lib/runtimeRefresh.ts';

async function flush() {
  for (let i = 0; i < 8; i += 1) await Promise.resolve();
}

test('delayed market summary does not skip the next runtime status poll', async () => {
  const locks = createRuntimeRefreshLocks();
  const seen = [];
  let releaseMarket;
  const lateMarket = new Promise((resolve) => {
    releaseMarket = () => resolve({ tag: 'late' });
  });

  const first = refreshRuntimeSnapshot(locks, {
    loadStatus: async () => ({ status_refresh: 'light' }),
    loadMarket: () => lateMarket,
    onStatus: (status) => seen.push(status.status_refresh),
    onStatusError: () => seen.push('status-error'),
    onMarket: (market) => seen.push(market.tag),
    onMarketMiss: () => seen.push('market-miss'),
  });

  assert.equal(await first, 'ok');
  assert.deepEqual(seen, ['light']);
  assert.equal(locks.statusBusy, false);
  assert.equal(locks.marketBusy, true);

  const second = await refreshRuntimeSnapshot(locks, {
    loadStatus: async () => ({}),
    loadMarket: async () => ({ tag: 'next' }),
    onStatus: () => seen.push('full'),
    onStatusError: () => seen.push('status-error'),
    onMarket: (market) => seen.push(market.tag),
    onMarketMiss: () => seen.push('market-miss'),
  });

  assert.equal(second, 'ok');
  assert.deepEqual(seen, ['light', 'full']);

  releaseMarket();
  await flush();
  assert.deepEqual(seen, ['light', 'full', 'late', 'next']);
  assert.equal(locks.statusBusy, false);
  assert.equal(locks.marketBusy, false);
});

test('an in-flight runtime status request is not stacked', async () => {
  const locks = createRuntimeRefreshLocks();
  let releaseStatus;
  const statusGate = new Promise((resolve) => {
    releaseStatus = () => resolve({ status_refresh: 'light' });
  });
  let secondLoaded = false;
  const first = refreshRuntimeSnapshot(locks, {
    loadStatus: () => statusGate,
    loadMarket: async () => ({ tag: 'market' }),
    onStatus: () => {},
    onStatusError: () => {},
    onMarket: () => {},
    onMarketMiss: () => {},
  });
  const second = await refreshRuntimeSnapshot(locks, {
    loadStatus: async () => {
      secondLoaded = true;
      return {};
    },
    loadMarket: async () => ({ tag: 'other' }),
    onStatus: () => {},
    onStatusError: () => {},
    onMarket: () => {},
    onMarketMiss: () => {},
  });
  assert.equal(second, 'skipped');
  assert.equal(secondLoaded, false);
  assert.equal(locks.statusBusy, true);
  releaseStatus();
  assert.equal(await first, 'ok');
});

test('market summary keeps backfill progress when warehouse status fails', () => {
  const summary = marketSummaryFrom(
    { running: true, progress: { sessions: 84, sessions_ready: 10, remaining: 74 } },
    null,
    'MARKET_COMMAND_FAILED_1_WAREHOUSE_WRITER_BUSY',
  );
  assert.equal(summary.backfillRunning, true);
  assert.equal(summary.backfillComplete, false);
  assert.equal(summary.sessionsReady, 10);
  assert.equal(summary.remaining, 74);
  assert.equal(summary.statusKnown, false);
  assert.match(summary.statusError, /WAREHOUSE_WRITER_BUSY/);
});

test('market summary is complete from a finished progress file', () => {
  const summary = marketSummaryFrom(
    { running: false, progress: { sessions: 84, sessions_ready: 84, remaining: 0 } },
    null,
    'MARKET_STATUS_UNAVAILABLE',
  );
  assert.equal(summary.backfillRunning, false);
  assert.equal(summary.backfillComplete, true);
  assert.equal(summary.remaining, 0);
});

test('market summary is complete when the warehouse has sessions and no gaps', () => {
  const summary = marketSummaryFrom(
    { running: false, progress: null },
    { sessions_ready: 84, gaps: [], last_successful_date: '20261105' },
  );
  assert.equal(summary.backfillComplete, true);
  assert.equal(summary.statusKnown, true);
  assert.equal(summary.statusError, null);
  assert.equal(summary.sessionsReady, 84);
});

test('an idle warehouse failure keeps a stable diagnostic code', () => {
  const busy = backfillReadFailure('MARKET_COMMAND_FAILED_1_WRITER_ACTIVE_OR_RECOVERY_REQUIRED');
  assert.equal(busy.diagnosticCode, 'MARKET_COMMAND_FAILED_1_WRITER_ACTIVE_OR_RECOVERY_REQUIRED');
  assert.match(busy.hint, /正在写入/);
  const timeout = backfillReadFailure('MARKET_STATUS_TIMEOUT');
  assert.equal(timeout.diagnosticCode, 'MARKET_STATUS_TIMEOUT');
  assert.match(timeout.hint, /超时/);
  const other = backfillReadFailure('MARKET_COMMAND_FAILED_1_CREDENTIAL_UNAVAILABLE');
  assert.equal(other.diagnosticCode, 'MARKET_COMMAND_FAILED_1_CREDENTIAL_UNAVAILABLE');
  assert.match(other.hint, /暂时读不到/);
});

test('market summary is not complete when status is missing and backfill is idle', () => {
  const summary = marketSummaryFrom({ running: false, progress: null }, null, null);
  assert.equal(summary.backfillComplete, false);
  assert.equal(summary.backfillRunning, false);
  assert.equal(summary.statusKnown, false);
  assert.equal(summary.remaining, null);
});
