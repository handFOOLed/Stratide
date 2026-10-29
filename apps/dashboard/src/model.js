export const RANGES = ['7D', '30D', '90D', '1Y', 'ALL'];
export const METRICS = { nav: '总资产', return: '累计收益率', pnl: '累计盈亏' };
export const STATUS = { Open: '待成交', PartiallyFilled: '部分成交', Filled: '已成交', Rejected: '已拒绝', Expired: '已过期' };
export const MODES = { synthetic_test: '合成测试', historical_replay: '历史模拟', forward_paper: '前向模拟' };

export function integer(value) {
  if (typeof value !== 'string' || !/^-?\d+$/.test(value)) return null;
  return BigInt(value);
}

export function money(value, signed = false) {
  const n = integer(value);
  if (n === null) return '—';
  const abs = n < 0n ? -n : n;
  const sign = n < 0n ? '−' : signed && n > 0n ? '+' : '';
  return `${sign}¥${(abs / 100n).toLocaleString('en-US')}.${(abs % 100n).toString().padStart(2, '0')}`;
}

export function bps(value) {
  return integer(value) === null ? '—' : `${money(value, true).replace('¥', '')}%`;
}

export function shares(value) { return integer(value)?.toLocaleString('en-US') ?? '—'; }
export function signClass(value) { const n = integer(value); return n === null || n === 0n ? '' : n > 0n ? 'profit' : 'loss'; }
export function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }
export function day(value) { return /^\d{8}$/.test(value ?? '') ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}` : '—'; }
export function timestamp(value) {
  const n = integer(value);
  if (n === null || n > 8_640_000_000_000_000n || n < 0n) return '—';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short', hour12: false }).format(new Date(Number(n)));
}
export function instrument(value) { return value ? `${value.code} · ${value.market === 'Shanghai' ? '沪市' : value.market}` : '—'; }

export function preference(key, fallback, allowed) {
  try { const value = localStorage.getItem(`stratide.${key}`); return (!allowed || allowed.includes(value)) && value !== null ? value : fallback; }
  catch { return fallback; }
}
export function remember(key, value) { try { localStorage.setItem(`stratide.${key}`, value); } catch { /* Session-only preferences when storage is disabled. */ } }

function dayTime(value) { return Date.parse(`${day(value)}T00:00:00Z`); }
export function rangeRows(rows, range) {
  if (range === 'ALL' || !rows.length) return rows;
  const days = { '7D': 7, '30D': 30, '90D': 90, '1Y': 365 }[range] ?? 30;
  const start = dayTime(rows.at(-1).day) - (days - 1) * 86_400_000;
  return rows.filter(row => dayTime(row.day) >= start);
}

export function sortRows(rows, key, direction = 'asc') {
  return [...rows].sort((a, b) => {
    const x = a[key]; const y = b[key];
    // Unavailable values stay last in either direction, never becoming zero.
    if (x === null || x === undefined) return y === null || y === undefined ? 0 : 1;
    if (y === null || y === undefined) return -1;
    const ix = integer(x); const iy = integer(y);
    const compared = ix !== null && iy !== null ? (ix < iy ? -1 : ix > iy ? 1 : 0) : String(x).localeCompare(String(y), 'zh-CN');
    return direction === 'desc' ? -compared : compared;
  });
}

// Money remains BigInt until this final, relative projection into SVG pixels.
// No rounding through Number can change the displayed financial amount.
export function chartModel(rows, metric, width = 940) {
  const key = { nav: 'nav_fen', pnl: 'cumulative_pnl_fen', return: 'return_bps' }[metric];
  const valid = rows.map(r => integer(r[key])).filter(v => v !== null);
  if (!valid.length) return null;
  const min = valid.reduce((a, b) => a < b ? a : b);
  const max = valid.reduce((a, b) => a > b ? a : b);
  const delta = max - min;
  const first = dayTime(rows[0].day); const last = dayTime(rows.at(-1).day);
  const points = rows.map(r => {
    const value = integer(r[key]);
    if (value === null) return null;
    const left = 100; const right = width - 16;
    return { x: last === first ? (left + right) / 2 : left + (dayTime(r.day) - first) / (last - first) * (right - left),
      y: delta === 0n ? 126 : 26 + (1 - Number(value - min) / Number(delta)) * 200,
      day: r.day, value: r[key] };
  });
  const paths = []; let segment = [];
  for (const point of [...points, null]) {
    if (point) segment.push(`${segment.length ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)}`);
    else if (segment.length) { paths.push(segment.join(' ')); segment = []; }
  }
  const ticks = [0n, 1n, 2n, 3n, 4n].map(i => ({ y: 26 + Number(i) * 50,
    value: (delta === 0n ? min : max - delta * i / 4n).toString() }));
  return { points, paths, ticks };
}
