import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  RUNTIME_STATUS_FAST_POLL_MS,
  RUNTIME_STATUS_POLL_MS,
  runtimeStatusAwaitingFullRefresh,
  runtimeStatusPollIntervalMs,
} from '../src/lib/runtimePoll.ts';

test('runtime status poll stays slow until light snapshot is replaced', () => {
  assert.equal(runtimeStatusPollIntervalMs(null, true), RUNTIME_STATUS_POLL_MS);
  assert.equal(runtimeStatusPollIntervalMs({}, true), RUNTIME_STATUS_POLL_MS);
  assert.equal(runtimeStatusPollIntervalMs({ status_refresh: 'light' }, true), RUNTIME_STATUS_FAST_POLL_MS);
  assert.equal(runtimeStatusPollIntervalMs({ status_refresh: 'light' }, false), null);
  assert.equal(runtimeStatusAwaitingFullRefresh({ status_refresh: 'light' }), true);
  assert.equal(runtimeStatusAwaitingFullRefresh({}), false);
});
