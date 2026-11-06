import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checklistProgress, checklistVisible } from '../src/lib/checklist.ts';

const readyStatus = {
  setup_complete: true,
  dependencies: {
    tushare_credential: { state: 'CONFIGURED', reason: null, note: null },
    market_eod: { state: 'INITIALIZED', reason: null, note: null },
  },
};

const readyMarket = {
  sessionsReady: 84,
  targetSessions: 84,
  remaining: 0,
  lastSuccessfulDate: '20261105',
  gaps: 0,
  backfillRunning: false,
  backfillComplete: true,
  statusKnown: true,
  statusError: null,
};

const readyAgent = {
  status: { default_model: 'market-deepseek-fusion', budget: { state: 'configured' } },
};

test('a fully known checklist is hidden and stays hidden while data reloads', () => {
  const done = checklistProgress({ status: readyStatus, market: readyMarket }, readyAgent);
  assert.equal(done.knownComplete, true);
  assert.equal(done.knownIncomplete, false);
  assert.equal(checklistVisible(done, false), false);

  const reloading = checklistProgress({ status: null, market: null }, { status: null });
  assert.equal(reloading.knownComplete, false);
  assert.equal(reloading.knownIncomplete, false);
  assert.equal(checklistVisible(reloading, true), false);
});

test('a known gap shows the checklist again after it was dismissed', () => {
  const gap = checklistProgress(
    {
      status: {
        ...readyStatus,
        dependencies: {
          ...readyStatus.dependencies,
          tushare_credential: { state: 'MISSING', reason: null, note: null },
        },
      },
      market: readyMarket,
    },
    readyAgent,
  );
  assert.equal(gap.knownComplete, false);
  assert.equal(gap.knownIncomplete, true);
  assert.equal(checklistVisible(gap, true), true);
});

test('an unfinished first run still shows the checklist', () => {
  const fresh = checklistProgress({ status: null, market: null }, { status: null });
  assert.equal(checklistVisible(fresh, false), true);
});
