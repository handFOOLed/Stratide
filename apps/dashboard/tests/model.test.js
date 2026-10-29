import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  dateInputToDay,
  formatBps,
  formatCny,
  formatDateTime,
  formatDay,
  formatMicro,
  formatShares,
  money,
  rangeRows,
} from '../src/lib/format.ts';
import { buildChartModel } from '../src/lib/chart.ts';

test('integer fen, shares and micro amounts stay exact beyond the JS safe integer boundary', () => {
  assert.equal(formatCny('9007199254740993'), '¥90,071,992,547,409.93');
  assert.equal(formatCny('-3349', { signed: true }), '−¥33.49');
  assert.equal(formatCny('899', { signed: true }), '+¥8.99');
  assert.equal(formatCny(null), '—');
  assert.equal(formatCny(9007199254740993), '—');
  assert.equal(formatShares('9007199254740995'), '9,007,199,254,740,995');
  assert.equal(formatBps('-3', { signed: true }), '−0.03%');
  assert.equal(formatBps('71', { signed: true }), '+0.71%');
  assert.equal(formatMicro('2731'), '0.002731');
  assert.equal(formatMicro('34816'), '0.034816');
  assert.equal(formatMicro('1000000', { currency: 'TST' }), '1.00 TST');
  assert.equal(formatMicro('-1000000', { currency: 'TST' }), '−1.00 TST');
  assert.equal(money, formatCny);
});

test('ranges end at the source date, not the wall clock, and never invent dates', () => {
  const rows = ['20260717', '20260928', '20261001', '20261028'].map((day) => ({ day }));
  assert.deepEqual(rangeRows(rows, '30D').map((row) => row.day), ['20261001', '20261028']);
  assert.deepEqual(rangeRows(rows, '7D').map((row) => row.day), ['20261028']);
  assert.equal(rangeRows(rows, 'ALL').length, 4);
});

test('day parsing and date inputs reject impossible calendar dates', () => {
  assert.equal(formatDay('20261102'), '2026-11-02');
  assert.equal(formatDay('2026-11-02'), '—');
  assert.equal(dateInputToDay('2026-11-02'), '20261102');
  assert.equal(dateInputToDay('2026-02-30'), null);
  assert.equal(dateInputToDay('not-a-date'), null);
  assert.equal(formatDateTime('2026-10-29T10:57:48.477812200+00:00'), '2026-10-29 18:57');
});

test('charts break at null valuations, use a zero baseline for P&L and do not duplicate axis ticks', () => {
  const rows = [
    { day: '20261026', nav_fen: '9007199254740993', cumulative_pnl_fen: '-200', return_bps: '-20' },
    { day: '20261027', nav_fen: null, cumulative_pnl_fen: null, return_bps: null },
    { day: '20261028', nav_fen: '9007199254740994', cumulative_pnl_fen: '100', return_bps: '10' },
    { day: '20261029', nav_fen: '9007199254740990', cumulative_pnl_fen: '0', return_bps: '0' },
  ];
  const model = buildChartModel(rows, 'nav', 940, 300);
  assert.ok(model);
  assert.equal(model.points[1], null);
  assert.equal(model.validCount, 3);
  assert.ok(model.points[0].y > model.points[2].y);

  const pnl = buildChartModel(rows, 'pnl', 940, 300);
  assert.ok(pnl);
  assert.notEqual(pnl.zeroY, null);

  const short = buildChartModel(rows.slice(-2), 'nav', 940, 300);
  assert.ok(short);
  assert.equal(short.xTicks.length, 2);
  assert.equal(short.xTicks[1].anchor, 'end');

  const single = buildChartModel(rows, 'return', 320, 220);
  assert.ok(single);
  assert.equal(new Set(single.xTicks.map((tick) => tick.x)).size, single.xTicks.length);
  assert.equal(buildChartModel([{ day: '20261028', nav_fen: null, cumulative_pnl_fen: null, return_bps: null }], 'nav', 940, 300), null);
});