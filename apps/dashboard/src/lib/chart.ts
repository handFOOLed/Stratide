import { formatAxisCny, formatBps, formatDay, parseDayMs, parseInteger } from './format.ts';
import type { EquityRow } from './types.ts';

export type ChartMetric = 'nav' | 'pnl' | 'return';

export interface ChartPoint {
  x: number;
  y: number;
  day: string;
  value: string;
}

export interface ChartTick {
  y: number;
  value: bigint;
  label: string;
}

export interface ChartXAxisTick {
  x: number;
  day: string;
  anchor: 'start' | 'middle' | 'end';
}

export interface ChartModel {
  width: number;
  height: number;
  plot: { left: number; right: number; top: number; bottom: number };
  points: Array<ChartPoint | null>;
  segments: string[];
  areas: string[];
  ticks: ChartTick[];
  xTicks: ChartXAxisTick[];
  zeroY: number | null;
  validCount: number;
  totalCount: number;
  firstDay: string | null;
  lastDay: string | null;
  yMin: bigint;
  yMax: bigint;
}

const METRIC_KEY: Record<ChartMetric, keyof EquityRow> = {
  nav: 'nav_fen',
  pnl: 'cumulative_pnl_fen',
  return: 'return_bps',
};

function metricLabel(metric: ChartMetric, value: bigint): string {
  return metric === 'return' ? formatBps(value.toString()) : formatAxisCny(value.toString());
}

/** Smallest power of ten that is >= value, so NAV axes read 560 -> 1000, 5600 -> 10000. */
export function decimalCeiling(value: bigint): bigint {
  if (value <= 1n) return 1n;
  let power = 1n;
  while (power < value) power *= 10n;
  return power;
}

interface ScreenPoint {
  x: number;
  y: number;
}

/**
 * Monotone cubic (Fritsch-Carlson) path: smooth, never overshoots a segment's
 * endpoints, therefore never invents a new high or low between report days.
 */
export function monotonePath(points: ScreenPoint[]): string {
  const count = points.length;
  if (count === 0) return '';
  const fmt = (value: number) => (Number.isFinite(value) ? value.toFixed(2) : '0');
  const first = points[0];
  if (!first) return '';
  if (count === 1) return `M${fmt(first.x)},${fmt(first.y)}`;
  if (count === 2) {
    const second = points[1] as ScreenPoint;
    return `M${fmt(first.x)},${fmt(first.y)} L${fmt(second.x)},${fmt(second.y)}`;
  }

  const dx: number[] = [];
  const slope: number[] = [];
  for (let index = 0; index < count - 1; index += 1) {
    const current = points[index] as ScreenPoint;
    const next = points[index + 1] as ScreenPoint;
    const run = next.x - current.x;
    dx.push(run);
    slope.push(run === 0 ? 0 : (next.y - current.y) / run);
  }

  const tangent: number[] = new Array(count);
  tangent[0] = slope[0] ?? 0;
  tangent[count - 1] = slope[count - 2] ?? 0;
  for (let index = 1; index < count - 1; index += 1) {
    const before = slope[index - 1] ?? 0;
    const after = slope[index] ?? 0;
    tangent[index] = before * after <= 0 ? 0 : (before + after) / 2;
  }

  for (let index = 0; index < count - 1; index += 1) {
    const segmentSlope = slope[index] ?? 0;
    if (segmentSlope === 0) {
      tangent[index] = 0;
      tangent[index + 1] = 0;
      continue;
    }
    const alpha = (tangent[index] ?? 0) / segmentSlope;
    const beta = (tangent[index + 1] ?? 0) / segmentSlope;
    const magnitude = alpha * alpha + beta * beta;
    if (magnitude > 9) {
      const scale = 3 / Math.sqrt(magnitude);
      tangent[index] = scale * alpha * segmentSlope;
      tangent[index + 1] = scale * beta * segmentSlope;
    }
  }

  let path = `M${fmt(first.x)},${fmt(first.y)}`;
  for (let index = 0; index < count - 1; index += 1) {
    const current = points[index] as ScreenPoint;
    const next = points[index + 1] as ScreenPoint;
    const run = (dx[index] ?? 0) / 3;
    const c1x = current.x + run;
    const c1y = current.y + (tangent[index] ?? 0) * run;
    const c2x = next.x - run;
    const c2y = next.y - (tangent[index + 1] ?? 0) * run;
    path += ` C${fmt(c1x)},${fmt(c1y)} ${fmt(c2x)},${fmt(c2y)} ${fmt(next.x)},${fmt(next.y)}`;
  }
  return path;
}

export function buildChartModel(
  rows: EquityRow[],
  metric: ChartMetric,
  width: number,
  height: number,
  options: { navTopFen?: bigint | null } = {},
): ChartModel | null {
  if (rows.length === 0 || width <= 0 || height <= 0) return null;
  const key = METRIC_KEY[metric];
  const values = rows.map((row) => parseInteger(row[key]));
  const valid = values.filter((value): value is bigint => value !== null);
  if (valid.length === 0) return null;

  const rawMax = valid.reduce((a, b) => (a > b ? a : b));
  const rawMin = valid.reduce((a, b) => (a < b ? a : b));

  let min: bigint;
  let max: bigint;
  if (metric === 'nav') {
    // NAV is a positive quantity: 0 -> 10^ceil(log10(max(current NAV, window max))).
    const current = options.navTopFen ?? null;
    const top = decimalCeiling(current !== null && current > rawMax ? current : rawMax);
    min = 0n;
    max = top;
  } else {
    min = rawMin > 0n ? 0n : rawMin;
    max = rawMax < 0n ? 0n : rawMax;
    if (max === min) max = min + (min < 0n ? -min / 20n : 0n) + 1n;
  }
  const delta = max - min;

  const compact = width < 520;
  const left = compact ? 48 : 60;
  const right = Math.max(left + 20, width - 10);
  const top = 10;
  const bottom = Math.max(top + 40, height - 24);
  const plotWidth = right - left;
  const plotHeight = bottom - top;

  const firstMs = parseDayMs(rows[0]?.day);
  const lastMs = parseDayMs(rows[rows.length - 1]?.day);
  const span = firstMs !== null && lastMs !== null ? lastMs - firstMs : 0;

  // Money stays integer; only the final SVG projection uses floating point.
  const valueSpan = Number(delta);
  const yFor = (value: bigint): number => {
    if (valueSpan === 0) return top + plotHeight / 2;
    const ratio = Math.min(1, Math.max(0, Number(value - min) / valueSpan));
    return top + (1 - ratio) * plotHeight;
  };

  const xFor = (day: string): number => {
    const ms = parseDayMs(day);
    if (firstMs === null || lastMs === null || ms === null || span <= 0) {
      return left + plotWidth / 2;
    }
    const ratio = Math.min(1, Math.max(0, (ms - firstMs) / span));
    return left + ratio * plotWidth;
  };

  const points: Array<ChartPoint | null> = rows.map((row, index) => {
    const value = values[index];
    if (value === null || value === undefined) return null;
    return {
      x: xFor(row.day),
      y: yFor(value),
      day: row.day,
      value: value.toString(),
    };
  });

  const segments: string[] = [];
  const areas: string[] = [];
  let run: ChartPoint[] = [];
  const flush = () => {
    if (run.length >= 2) {
      const path = monotonePath(run.map((point) => ({ x: point.x, y: point.y })));
      segments.push(path);
      const first = run[0];
      const last = run[run.length - 1];
      if (first && last) {
        areas.push(
          `${path} L${last.x.toFixed(2)},${bottom.toFixed(2)} L${first.x.toFixed(2)},${bottom.toFixed(2)} Z`,
        );
      }
    }
    run = [];
  };
  for (const point of points) {
    if (point) run.push(point);
    else flush();
  }
  flush();

  // Five equal intervals => a faint dashed gridline every 20% of the domain.
  const ticks: ChartTick[] = [];
  for (let index = 0; index <= 5; index += 1) {
    const value = delta === 0n ? min : max - (delta * BigInt(index)) / 5n;
    ticks.push({
      y: top + (plotHeight * index) / 5,
      value,
      label: metricLabel(metric, value),
    });
  }

  const xCount = width < 420 ? 2 : width < 680 ? 3 : width < 920 ? 4 : 5;
  const xTicks: ChartXAxisTick[] = [];
  const seen = new Set<number>();
  const lastIndex = rows.length - 1;
  const tickCount = Math.min(xCount, rows.length);
  for (let index = 0; index < tickCount; index += 1) {
    const rowIndex = tickCount <= 1 ? 0 : Math.round((lastIndex * index) / (tickCount - 1));
    if (seen.has(rowIndex)) continue;
    seen.add(rowIndex);
    const row = rows[rowIndex];
    if (!row) continue;
    const anchor: ChartXAxisTick['anchor'] =
      rowIndex === 0 ? 'start' : rowIndex === lastIndex ? 'end' : 'middle';
    xTicks.push({ x: xFor(row.day), day: row.day, anchor });
  }

  const zeroY = metric !== 'nav' && min < 0n && max > 0n ? yFor(0n) : null;

  return {
    width,
    height,
    plot: { left, right, top, bottom },
    points,
    segments,
    areas,
    ticks,
    xTicks,
    zeroY,
    validCount: valid.length,
    totalCount: rows.length,
    firstDay: rows[0]?.day ?? null,
    lastDay: rows[rows.length - 1]?.day ?? null,
    yMin: min,
    yMax: max,
  };
}

export function chartMetricValue(metric: ChartMetric, value: string): string {
  return metric === 'return' ? formatBps(value) : formatCnyTooltip(value);
}

function formatCnyTooltip(value: string): string {
  const n = parseInteger(value);
  if (n === null) return '—';
  const abs = n < 0n ? -n : n;
  const yuan = (abs / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const fen = (abs % 100n).toString().padStart(2, '0');
  return `${n < 0n ? '\u2212' : ''}¥${yuan}.${fen}`;
}

export function chartDayLabel(day: string): string {
  const full = formatDay(day);
  return full === '—' ? '—' : full.slice(5);
}
