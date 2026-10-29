import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia(query);
    const onChange = () => setMatches(media.matches);
    onChange();
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

export function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden');
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);
  return visible;
}

export function useInterval(callback: () => void, delay: number | null): void {
  const saved = useRef(callback);
  useLayoutEffect(() => {
    saved.current = callback;
  }, [callback]);
  useEffect(() => {
    if (delay === null) return;
    const id = window.setInterval(() => saved.current(), delay);
    return () => window.clearInterval(id);
  }, [delay]);
}

export function useOnClickOutside(
  refs: Array<RefObject<HTMLElement | null>>,
  handler: () => void,
  active: boolean,
): void {
  useEffect(() => {
    if (!active) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (refs.some((ref) => ref.current?.contains(target))) return;
      handler();
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, [active, handler, refs]);
}

export interface Presence {
  mounted: boolean;
  state: 'open' | 'closing';
}

export function usePresence(open: boolean, duration: number): Presence {
  const [mounted, setMounted] = useState(open);
  const [state, setState] = useState<'open' | 'closing'>(open ? 'open' : 'closing');
  const timer = useRef<number | null>(null);
  useEffect(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    if (open) {
      setMounted(true);
      setState('open');
      return;
    }
    setState('closing');
    timer.current = window.setTimeout(() => {
      setMounted(false);
      timer.current = null;
    }, duration);
    return () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
        timer.current = null;
      }
    };
  }, [duration, open]);
  return { mounted, state };
}

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(',');

export function useFocusTrap(
  panelRef: RefObject<HTMLElement | null>,
  active: boolean,
  onClose: () => void,
): void {
  const previous = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  useLayoutEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    if (!active) return;
    const panel = panelRef.current;
    if (!panel) return;
    previous.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusables = () =>
      Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => !element.hasAttribute('disabled') && element.offsetParent !== null,
      );
    const focusTarget = panel.querySelector<HTMLElement>('[data-autofocus]') ?? focusables()[0] ?? panel;
    window.requestAnimationFrame(() => focusTarget.focus({ preventScroll: true }));

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        panel.focus({ preventScroll: true });
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      const current = document.activeElement;
      if (event.shiftKey && (current === first || current === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && current === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      const previousElement = previous.current;
      if (previousElement && previousElement.isConnected) {
        window.requestAnimationFrame(() => previousElement.focus({ preventScroll: true }));
      }
    };
  }, [active, panelRef]);
}

export function usePageScrollReset(ref: RefObject<HTMLElement | null>, key: string): void {
  const previous = useRef<string | null>(null);
  useEffect(() => {
    if (previous.current === null) {
      previous.current = key;
      return;
    }
    if (previous.current === key) return;
    previous.current = key;
    const node = ref.current;
    if (node && typeof node.scrollTo === 'function') {
      node.scrollTo({ top: 0, behavior: 'auto' });
    } else if (node) {
      node.scrollTop = 0;
    }
  }, [key, ref]);
}

export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · Stratide`;
    return () => {
      document.title = 'Stratide · Paper 工作空间';
    };
  }, [title]);
}

export function useIdSafe(prefix: string): string {
  const raw = useRef(`${prefix}-${Math.random().toString(36).slice(2, 9)}`);
  return raw.current;
}
export interface Selection<T> {
  item: T | null;
  open: boolean;
  select: (item: T) => void;
  close: () => void;
}

export function useSelection<T>(): Selection<T> {
  const [item, setItem] = useState<T | null>(null);
  const [open, setOpen] = useState(false);
  const select = useCallback((next: T) => {
    setItem(next);
    setOpen(true);
  }, []);
  const close = useCallback(() => setOpen(false), []);
  return { item, open, select, close };
}
