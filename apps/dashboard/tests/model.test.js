import { test } from 'node:test';
import assert from 'node:assert/strict';
import { money, shares, bps, sortRows, rangeRows, chartModel, esc } from '../src/model.js';

test('integer fen and shares stay exact beyond the JS safe integer boundary', () => {
  assert.equal(money('9007199254740993'), '¥90,071,992,547,409.93');
  assert.equal(money('-3349', true), '−¥33.49');
  assert.equal(money('899', true), '+¥8.99');
  assert.equal(shares('9007199254740995'), '9,007,199,254,740,995');
  assert.equal(money(null), '—');
  assert.equal(money(9007199254740993), '—');
  assert.equal(bps('-3'), '−0.03%');
  assert.equal(esc('<script>&"'), '&lt;script&gt;&amp;&quot;');
});

test('ranges end at the source date, not the wall clock, and never invent dates', () => {
  const rows = ['20260717','20260928','20261001','20261028'].map(day => ({ day }));
  assert.deepEqual(rangeRows(rows, '30D').map(r => r.day), ['20261001','20261028']);
  assert.deepEqual(rangeRows(rows, '7D').map(r => r.day), ['20261028']);
  assert.equal(rangeRows(rows, 'ALL').length, 4);
});

test('charts break at null valuations and project large amounts relatively', () => {
  const rows = [{ day:'20261026', nav_fen:'9007199254740993' },
    { day:'20261027', nav_fen:null }, { day:'20261028', nav_fen:'9007199254740994' }];
  const model = chartModel(rows, 'nav');
  assert.equal(model.paths.length, 2);
  assert.equal(model.points[1], null);
  assert.ok(model.points[0].y > model.points[2].y);
  assert.equal(chartModel([{ day:'20261028', nav_fen:null }], 'nav'), null);
});

test('numeric sorts do not round financial integers or rank null as zero', () => {
  const rows = [{value:null},{value:'9007199254740994'},{value:'9007199254740993'}];
  assert.deepEqual(sortRows(rows,'value','asc').map(r=>r.value), ['9007199254740993','9007199254740994',null]);
  assert.deepEqual(sortRows(rows,'value','desc').map(r=>r.value), ['9007199254740994','9007199254740993',null]);
});
