const PREFIX = 'stratide.';

export function readPreference<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const value = window.localStorage.getItem(`${PREFIX}${key}`);
    return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writePreference(key: string, value: string): void {
  try {
    window.localStorage.setItem(`${PREFIX}${key}`, value);
  } catch {
    // Preferences are optional. Never break the dashboard when storage is unavailable.
  }
}

export const THEME_VALUES = ['system', 'light', 'dark'] as const;
export type ThemePreference = (typeof THEME_VALUES)[number];

export const MOTION_VALUES = ['system', 'reduce'] as const;
export type MotionPreference = (typeof MOTION_VALUES)[number];

export const RANGE_VALUES = ['7D', '30D', '90D', '1Y', 'ALL'] as const;
export type RangeValue = (typeof RANGE_VALUES)[number];

export const METRIC_VALUES = ['nav', 'pnl', 'return'] as const;
export type MetricValue = (typeof METRIC_VALUES)[number];
