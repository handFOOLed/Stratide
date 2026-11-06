import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError } from '../src/lib/api.ts';
import { runtimeAction } from '../src/lib/runtime.ts';

function hangUntilAbort() {
  return (_url, init) =>
    new Promise((_resolve, reject) => {
      const signal = init?.signal;
      if (signal?.aborted) {
        reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
        return;
      }
      signal?.addEventListener('abort', () => {
        reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
      });
    });
}

test('an outer abort stays ABORTED and is not a timeout', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = hangUntilAbort();
  const outer = new AbortController();
  const task = runtimeAction('market', { action: 'status' }, {
    timeoutMs: 5000,
    timeoutCode: 'MARKET_STATUS_TIMEOUT',
    signal: outer.signal,
  });
  outer.abort();
  await assert.rejects(task, (error) => error instanceof ApiError && error.code === 'ABORTED');
  globalThis.fetch = original;
});

test('the local timer is a timeout code, distinct from ABORTED', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = hangUntilAbort();
  const outer = new AbortController();
  const task = runtimeAction('market', { action: 'status' }, {
    timeoutMs: 20,
    timeoutCode: 'MARKET_STATUS_TIMEOUT',
    signal: outer.signal,
  });
  await assert.rejects(task, (error) => error instanceof ApiError && error.code === 'MARKET_STATUS_TIMEOUT');
  assert.equal(outer.signal.aborted, false);
  globalThis.fetch = original;
});
