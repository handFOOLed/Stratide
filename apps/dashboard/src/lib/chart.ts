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
}

const METRIC_KEY: Record<ChartMetric, keyof EquityRow> = {
  nav: 'nav_fen',
  pnl: 'cumulative_pnl_fen',
  return: 'return_bps',
};

function metricLabel(metric: ChartMetric, value: bigint): string {
  return metric === 'return' ? formatBps(value.toString()) : formatAxisCny(value.toString());
}

export function buildChartModel(
  rows: EquityRow[],
  metric: ChartMetric,
  width: number,
  height: number,
): ChartModel | null {
  if (rows.length === 0 || width <= 0 || height <= 0) return null;
  const key = METRIC_KEY[metric];
  const values = rows.map((row) => parseInteger(row[key]));
  const valid = values.filter((value): value is bigint => value !== null);
  if (valid.length === 0) return null;

  let min = valid.reduce((a, b) => (a < b ? a : b));
  let max = valid.reduce((a, b) => (a > b ? a : b));
  if (metric !== 'nav') {
    if (min > 0n) min = 0n;
    if (max < 0n) max = 0n;
  }
  const delta = max - min;

  const compact = width < 520;
  const left = compact ? 44 : 58;
  const right = Math.max(left + 20, width - 8);
  const top = 14;
  const bottom = Math.max(top + 40, height - 26);
  const plotWidth = right - left;
  const plotHeight = bottom - top;

  const firstMs = parseDayMs(rows[0]?.day);
  const lastMs = parseDayMs(rows[rows.length - 1]?.day);
  const span = firstMs !== null && lastMs !== null ? lastMs - firstMs : 0;

  const yFor = (value: bigint): number => {
    if (delta === 0n) return top + plotHeight / 2;
    const ratio = Number(((value - min) * 1_000_000n) / delta) / 1_000_000;
    return top + (1 - Math.min(1, Math.max(0, ratio))) * plotHeight;
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
  let segment: ChartPoint[] = [];
  const flush = () => {
    if (segment.length >= 2) {
      const path = segment.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ');
      segments.push(path);
      const first = segment[0];
      const last = segment[segment.length - 1];
      if (first && last) {
        areas.push(
          `${path} L${last.x.toFixed(2)},${bottom.toFixed(2)} L${first.x.toFixed(2)},${bottom.toFixed(2)} Z`,
        );
      }
    }
    segment = [];
  };
  for (const point of points) {
    if (point) {
      segment.push(point);
    } else {
      flush();
    }
  }
  flush();

  const tickIntervals = height >= 270 ? 4 : 3;
  const ticks: ChartTick[] = [];
  for (let index = 0; index <= tickIntervals; index += 1) {
    const value = delta === 0n ? min : max - (delta * BigInt(index)) / BigInt(tickIntervals);
    ticks.push({
      y: top + (plotHeight * index) / tickIntervals,
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