import { useEffect, useState } from 'react';

export const PAGE_KEYS = ['overview', 'history', 'agents', 'notifications', 'settings'] as const;
export type PageKey = (typeof PAGE_KEYS)[number];

export const HISTORY_TABS = ['fills', 'orders', 'daily', 'strategies', 'research'] as const;
export type HistoryTab = (typeof HISTORY_TABS)[number];

export interface Route {
  page: PageKey;
  tab: HistoryTab;
}

export const PAGE_LABELS: Record<PageKey, string> = {
  overview: '总览',
  history: '历史与报告',
  agents: 'Agent 管理',
  notifications: '通知与审批',
  settings: '设置',
};

export const HISTORY_TAB_LABELS: Record<HistoryTab, string> = {
  fills: '成交',
  orders: '订单',
  daily: '逐日核对',
  strategies: '策略档案',
  research: '研究档案',
};

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, '').replace(/^\/+/, '');
  const [pagePart, tabPart] = raw.split('/');
  const page = (PAGE_KEYS as readonly string[]).includes(pagePart) ? (pagePart as PageKey) : 'overview';
  let tab: HistoryTab = 'fills';
  if (page === 'history') {
    if (tabPart === 'performance') tab = 'daily';
    else if (tabPart && (HISTORY_TABS as readonly string[]).includes(tabPart)) tab = tabPart as HistoryTab;
  }
  return { page, tab };
}

export function routeHref(route: Route): string {
  return route.page === 'history' ? `#history/${route.tab}` : `#${route.page}`;
}

export function navigate(route: Route, options: { replace?: boolean } = {}): void {
  const href = routeHref(route);
  if (window.location.hash === href) return;
  if (options.replace) {
    window.history.replaceState(null, '', href);
    window.dispatchEvent(new Event('hashchange'));
  } else {
    window.location.hash = href;
  }
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
