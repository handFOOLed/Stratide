import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { MOTION_VALUES, THEME_VALUES, readPreference, writePreference } from '../lib/storage';
import type { MotionPreference, ThemePreference } from '../lib/storage';

interface ThemeApi {
  theme: ThemePreference;
  motion: MotionPreference;
  resolvedTheme: 'light' | 'dark';
  reducedMotion: boolean;
  setTheme: (theme: ThemePreference) => void;
  setMotion: (motion: MotionPreference) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeApi | null>(null);

function prefersDark(): boolean {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false;
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;
}

export function applyStoredAppearance(): void {
  if (typeof window === 'undefined') return;
  const theme = readPreference('theme', 'system', THEME_VALUES);
  const motion = readPreference('motion', 'system', MOTION_VALUES);
  const dark = affectsDark(theme);
  const reduced = motion === 'reduce' || (motion === 'system' && prefersReducedMotion());
  const root = document.documentElement;
  root.dataset.theme = dark ? 'dark' : 'light';
  root.dataset.themePreference = theme;
  root.dataset.motion = reduced ? 'reduce' : 'full';
  root.style.colorScheme = dark ? 'dark' : 'light';
}

function affectsDark(theme: ThemePreference): boolean {
  return theme === 'dark' || (theme === 'system' && prefersDark());
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(() =>
    readPreference('theme', 'system', THEME_VALUES),
  );
  const [motion, setMotionState] = useState<MotionPreference>(() =>
    readPreference('motion', 'system', MOTION_VALUES),
  );
  const [systemDark, setSystemDark] = useState(prefersDark);
  const [systemReduced, setSystemReduced] = useState(prefersReducedMotion);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const dark = window.matchMedia('(prefers-color-scheme: dark)');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onDark = () => setSystemDark(dark.matches);
    const onReduced = () => setSystemReduced(reduced.matches);
    dark.addEventListener('change', onDark);
    reduced.addEventListener('change', onReduced);
    return () => {
      dark.removeEventListener('change', onDark);
      reduced.removeEventListener('change', onReduced);
    };
  }, []);

  const resolvedTheme: 'light' | 'dark' = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;
  const reducedMotion = motion === 'reduce' || (motion === 'system' && systemReduced);

  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = resolvedTheme;
    root.dataset.themePreference = theme;
    root.dataset.motion = reducedMotion ? 'reduce' : 'full';
    root.style.colorScheme = resolvedTheme;
  }, [reducedMotion, resolvedTheme, theme]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    writePreference('theme', next);
  }, []);

  const setMotion = useCallback((next: MotionPreference) => {
    setMotionState(next);
    writePreference('motion', next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  }, [resolvedTheme, setTheme]);

  const api = useMemo(
    () => ({ theme, motion, resolvedTheme, reducedMotion, setTheme, setMotion, toggleTheme }),
    [motion, reducedMotion, resolvedTheme, setMotion, setTheme, theme, toggleTheme],
  );

  return <ThemeContext.Provider value={api}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeApi {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme must be used inside ThemeProvider');
  return value;
}