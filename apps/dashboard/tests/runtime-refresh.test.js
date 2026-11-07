import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  backfillPresentation,
  backfillReadFailure,
  createRuntimeRefreshLocks,
  marketSummaryFrom,
  mergeMarketRead,
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

test('a full progress file without a warehouse report is not verified complete', () => {
  const summary = marketSummaryFrom(
    { running: false, progress: { sessions: 84, sessions_ready: 84, remaining: 0 } },
    null,
    'MARKET_STATUS_UNAVAILABLE',
  );
  assert.equal(summary.backfillRunning, false);
  assert.equal(summary.backfillComplete, false);
  assert.equal(summary.verification, 'unknown');
  assert.equal(summary.downloadPercent, 100);
  assert.equal(summary.remaining, 0);
});

test('a progress file with remaining 0 but too few sessions is not complete', () => {
  const summary = marketSummaryFrom(
    { running: false, progress: { sessions: 84, sessions_ready: 10, remaining: 0 } },
    null,
    'MARKET_STATUS_UNAVAILABLE',
  );
  assert.equal(summary.backfillComplete, false);
});

test('market summary is complete only when coverage is explicit and the target is met', () => {
  const summary = marketSummaryFrom(
    { running: false, progress: null },
    { sessions_ready: 84, gaps: [], last_successful_date: '20261105', coverage_complete: true },
  );
  assert.equal(summary.backfillComplete, true);
  assert.equal(summary.statusKnown, true);
  assert.equal(summary.statusError, null);
  assert.equal(summary.sessionsReady, 84);

  const short = marketSummaryFrom(
    { running: false, progress: null },
    { sessions_ready: 10, gaps: [], coverage_complete: false },
  );
  assert.equal(short.backfillComplete, false);

  const uncovered = marketSummaryFrom(
    { running: false, progress: null },
    { sessions_ready: 84, gaps: [], coverage_complete: false },
  );
  assert.equal(uncovered.backfillComplete, false);
});

test('a stale warehouse completion is overlaid and then dropped', () => {
  const confirmed = marketSummaryFrom(
    { running: false, progress: null },
    { sessions_ready: 84, gaps: [], last_successful_date: '20261105', coverage_complete: true },
  );
  const failed = marketSummaryFrom(
    { running: false, progress: null },
    null,
    'MARKET_COMMAND_FAILED_1_WRITER_ACTIVE_OR_RECOVERY_REQUIRED',
  );
  const once = mergeMarketRead(confirmed, failed);
  assert.equal(once.statusError, failed.statusError);
  assert.equal(once.sessionsReady, 84);
  assert.equal(once.lastSuccessfulDate, '20261105');
  assert.equal(once.backfillComplete, false);
  assert.equal(once.statusStale, false);
  assert.equal(once.statusKnown, false);

  const twice = mergeMarketRead(once, failed);
  assert.equal(twice.statusStale, true);
  assert.equal(twice.backfillComplete, false);
  assert.equal(twice.statusError, failed.statusError);
  assert.equal(twice.sessionsReady, 84);

  const recovered = mergeMarketRead(twice, confirmed);
  assert.equal(recovered.backfillComplete, true);
  assert.equal(recovered.statusError, null);
  assert.equal(recovered.statusFailures, 0);
  assert.equal(recovered.statusStale, false);
});

test('overview copy keeps the diagnostic code out of the sentence', () => {
  const failed = marketSummaryFrom(
    { running: false, progress: null },
    null,
    'MARKET_STATUS_TIMEOUT',
  );
  const once = mergeMarketRead(null, failed);
  const fresh = backfillPresentation(once, false);
  assert.equal(fresh.complete, false);
  assert.equal(fresh.diagnosticCode, 'MARKET_STATUS_TIMEOUT');
  assert.match(fresh.text, /超时/);
  assert.equal(fresh.text.includes('MARKET_STATUS_TIMEOUT'), false);

  const confirmed = marketSummaryFrom(
    { running: false, progress: null },
    { sessions_ready: 84, gaps: [], coverage_complete: true },
  );
  const stale = mergeMarketRead(mergeMarketRead(confirmed, failed), failed);
  const aged = backfillPresentation(stale, false);
  assert.equal(stale.statusStale, true);
  assert.equal(aged.complete, false);
  assert.equal(aged.text, '行情进度无法读取，请稍后重试。');
  assert.equal(aged.diagnosticCode, 'MARKET_STATUS_TIMEOUT');
  assert.equal(aged.text.includes('已就绪'), false);

  const progressDone = marketSummaryFrom(
    { running: false, progress: { sessions: 84, sessions_ready: 84, remaining: 0 } },
    null,
    'MARKET_STATUS_TIMEOUT',
  );
  const staleProgress = mergeMarketRead(mergeMarketRead(confirmed, progressDone), progressDone);
  const stillUnconfirmed = backfillPresentation(staleProgress, false);
  assert.equal(staleProgress.backfillComplete, false);
  assert.equal(staleProgress.statusStale, true);
  assert.equal(stillUnconfirmed.complete, false);
  assert.equal(stillUnconfirmed.text, '行情进度无法读取，请稍后重试。');
  assert.equal(stillUnconfirmed.downloadPercent, null);
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
