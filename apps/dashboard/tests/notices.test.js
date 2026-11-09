import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleNotices } from '../src/lib/notices.ts';

test('read notices are removed before any row is rendered', () => {
  const rows = [
    { id: 'a', read: true, name: '已读甲' },
    { id: 'b', read: false, name: '未读乙' },
    { id: 'c', read: true, name: '已读丙' },
  ];
  const visible = visibleNotices(rows);
  assert.deepEqual(visible.map((row) => row.id), ['b']);
  assert.equal(visible.some((row) => row.read), false);
});

test('an empty unread list stays empty when every stored row is read', () => {
  assert.deepEqual(visibleNotices([{ id: 'a', read: true }]), []);
  assert.deepEqual(visibleNotices([]), []);
});
