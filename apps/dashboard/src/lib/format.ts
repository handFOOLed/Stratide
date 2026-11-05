import type { RangeValue } from './storage.ts';

const MINUS = '\u2212';

export function parseInteger(value: unknown): bigint | null {
  if (typeof value === 'bigint') return value;
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) ? BigInt(value) : null;
  }
  if (typeof value !== 'string' || !/^-?\d+$/.test(value)) return null;
  try {
    return BigInt(value);
  } catch {
    return null;
  }
}

function groupDigits(value: string): string {
  return value.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function absolute(value: bigint): bigint {
  return value < 0n ? -value : value;
}

function signPrefix(value: bigint, signed: boolean): string {
  if (value < 0n) return MINUS;
  return signed && value > 0n ? '+' : '';
}

export function formatCny(value: unknown, options: { signed?: boolean } = {}): string {
  const n = parseInteger(value);
  if (n === null) return '—';
  const abs = absolute(n);
  const yuan = groupDigits((abs / 100n).toString());
  const fen = (abs % 100n).toString().padStart(2, '0');
  return `${signPrefix(n, options.signed === true)}¥${yuan}.${fen}`;
}

export const money = formatCny;

export function formatCnyUnsigned(value: unknown): string {
  return formatCny(value);
}

export function formatAxisCny(value: unknown): string {
  const n = parseInteger(value);
  if (n === null) return '—';
  const abs = absolute(n);
  return `${n < 0n ? MINUS : ''}¥${groupDigits((abs / 100n).toString())}`;
}

export function formatBps(value: unknown, options: { signed?: boolean } = {}): string {
  const n = parseInteger(value);
  if (n === null) return '—';
  const abs = absolute(n);
  const whole = (abs / 100n).toString();
  const frac = (abs % 100n).toString().padStart(2, '0');
  return `${signPrefix(n, options.signed === true)}${groupDigits(whole)}.${frac}%`;
}

export function formatShares(value: unknown): string {
  const n = parseInteger(value);
  return n === null ? '—' : groupDigits(n.toString());
}

export function formatCount(value: unknown): string {
  const n = parseInteger(value);
  return n === null ? '—' : groupDigits(n.toString());
}

/** 统一数量写法：“2 笔”“0 只”“— 条”。禁止再手写“共 0 笔 / 0 条 / 0 只”混用。 */
export function countText(value: unknown, unit: string): string {
  const n = parseInteger(value);
  return n === null ? '— ' + unit : groupDigits(n.toString()) + ' ' + unit;
}

export function currencySymbol(currency: string | null | undefined): string {
  if (currency === 'CNY' || currency === 'RMB' || currency === null || currency === undefined) return '¥';
  return currency;
}

/** 云端费用预算以 micro 货币为单位；人民币显示为 ¥ + 两位小数，其他单位保留代码。 */
export function formatMicroMoney(value: unknown, currency: string): string {
  const n = parseInteger(value);
  if (n === null) return '—';
  if (currency !== 'CNY') return formatMicro(n) + ' ' + currency;
  const negative = n < 0n;
  const abs = negative ? -n : n;
  let whole = abs / 1_000_000n;
  let fen = (abs % 1_000_000n + 5_000n) / 10_000n;
  if (fen === 100n) {
    whole += 1n;
    fen = 0n;
  }
  return (negative ? MINUS : '') + '¥' + groupDigits(whole.toString()) + '.' + fen.toString().padStart(2, '0');
}

/** 本机时间戳 → 日期（Asia/Shanghai），用于“2026-11-05”这类表头。 */
export function formatDateFromTimestamp(value: unknown): string {
  const ms = parseTimestamp(value);
  if (ms === null) return '—';
  const p = shanghaiParts(ms);
  return p.year + '-' + p.month + '-' + p.day;
}

export function formatMicro(value: unknown, options: { currency?: string; signed?: boolean } = {}): string {
  const n = parseInteger(value);
  if (n === null) return '—';
  const abs = absolute(n);
  const whole = groupDigits((abs / 1_000_000n).toString());
  const raw = (abs % 1_000_000n).toString().padStart(6, '0');
  const trimmed = raw.replace(/0+$/, '');
  const frac = trimmed.length >= 2 ? trimmed : trimmed.padEnd(2, '0');
  const result = `${signPrefix(n, options.signed === true)}${whole}.${frac}`;
  return options.currency ? `${result} ${options.currency}` : result;
}

export function formatBpsAsPercent(value: unknown): string {
  return formatBps(value);
}

export function signClass(value: unknown): 'gain' | 'loss' | '' {
  const n = parseInteger(value);
  if (n === null || n === 0n) return '';
  return n > 0n ? 'gain' : 'loss';
}

export function signSymbol(value: unknown): string {
  const n = parseInteger(value);
  if (n === null || n === 0n) return '';
  return n > 0n ? '+' : MINUS;
}

export function formatDay(value: unknown): string {
  if (typeof value !== 'string' || !/^\d{8}$/.test(value)) return '—';
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

export function formatDayShort(value: unknown): string {
  const day = formatDay(value);
  return day === '—' ? day : day.slice(5);
}

export function parseDayMs(value: unknown): number | null {
  if (typeof value !== 'string' || !/^\d{8}$/.test(value)) return null;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  const ms = Date.UTC(year, month - 1, day);
  const date = new Date(ms);
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  return ms;
}

export function dateInputToDay(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const ms = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(ms)) return null;
  const day = value.replaceAll('-', '');
  return parseDayMs(day) === null ? null : day;
}

export function dayToDateInput(value: unknown): string {
  const day = formatDay(value);
  return day === '—' ? '' : day;
}

export function todayShanghai(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const read = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${read('year')}-${read('month')}-${read('day')}`;
}

function normalizeIso(value: string): string {
  return value.replace(/(\.\d{3})\d+/, '$1');
}

export function parseTimestamp(value: unknown): number | null {
  if (typeof value !== 'string' || value.length === 0) return null;
  if (/^\d{10}$/.test(value)) {
    const seconds = Number(value);
    return Number.isFinite(seconds) ? seconds * 1000 : null;
  }
  if (/^\d{13}$/.test(value)) {
    const ms = Number(value);
    return Number.isFinite(ms) && ms >= 0 ? ms : null;
  }
  if (/^\d{16}$/.test(value)) {
    // Defensive: a microsecond epoch string is not a documented paper timestamp.
    const ms = Number(value.slice(0, 13));
    return Number.isFinite(ms) ? ms : null;
  }
  const ms = Date.parse(normalizeIso(value));
  return Number.isFinite(ms) ? ms : null;
}

function shanghaiParts(ms: number) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(ms));
  const read = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return {
    year: read('year'),
    month: read('month'),
    day: read('day'),
    hour: read('hour'),
    minute: read('minute'),
    second: read('second'),
  };
}

export function formatDateTime(value: unknown): string {
  const ms = parseTimestamp(value);
  if (ms === null) return '—';
  const p = shanghaiParts(ms);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
}

export function formatDateTimeSeconds(value: unknown): string {
  const ms = parseTimestamp(value);
  if (ms === null) return '—';
  const p = shanghaiParts(ms);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
}

export function formatClock(value: Date | number): string {
  const ms = value instanceof Date ? value.getTime() : value;
  if (!Number.isFinite(ms)) return '—';
  const p = shanghaiParts(ms);
  return `${p.hour}:${p.minute}:${p.second}`;
}

export function formatDuration(start: unknown, end: unknown): string {
  if (start === null || start === undefined) return '—';
  const startMs = parseTimestamp(start);
  if (startMs === null) return '—';
  const endMs = end === null || end === undefined ? null : parseTimestamp(end);
  if (endMs === null) return '运行中';
  const seconds = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (seconds < 1) return '<1 秒';
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    return rest === 0 ? `${minutes} 分` : `${minutes} 分 ${rest} 秒`;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return minutes === 0 ? `${hours} 小时` : `${hours} 小时 ${minutes} 分`;
}

export function instrumentLabel(instrument: { code: string; market: string } | null | undefined): string {
  if (!instrument) return '—';
  const market = instrument.market === 'Shanghai' ? '沪市' : instrument.market === 'Shenzhen' ? '深市' : instrument.market;
  return `${instrument.code} · ${market}`;
}

export function instrumentCode(instrument: { code: string } | null | undefined): string {
  return instrument?.code ?? '—';
}

export function sideLabel(side: string): string {
  if (side === 'Buy') return '买入';
  if (side === 'Sell') return '卖出';
  return side;
}

export function orderStatusLabel(status: string): string {
  switch (status) {
    case 'Open':
      return '待成交';
    case 'PartiallyFilled':
      return '部分成交';
    case 'Filled':
      return '已成交';
    case 'Rejected':
      return '已拒绝';
    case 'Expired':
      return '已过期';
    default:
      return status;
  }
}
export function rangeRows<T extends { day: string }>(rows: T[], range: RangeValue): T[] {
  if (range === 'ALL' || rows.length === 0) return rows;
  const days: Record<string, number> = { '7D': 7, '30D': 30, '90D': 90, '1Y': 365 };
  const lastMs = parseDayMs(rows[rows.length - 1]?.day);
  if (lastMs === null) return rows;
  const span = (days[range] ?? 30) - 1;
  const start = lastMs - span * 86_400_000;
  return rows.filter((row) => {
    const ms = parseDayMs(row.day);
    return ms !== null && ms >= start;
  });
}