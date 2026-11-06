import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  createRuntimeRefreshLocks,
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
