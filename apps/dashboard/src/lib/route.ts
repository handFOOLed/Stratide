import { useEffect, useState } from 'react';

export const PAGE_KEYS = ['overview', 'history', 'agents', 'notifications', 'settings'] as const;
export type PageKey = (typeof PAGE_KEYS)[number];

export const HISTORY_TABS = ['fills', 'orders', 'daily', 'strategies', 'research'] as const;
export type HistoryTab = (typeof HISTORY_TABS)[number];

export const SETTINGS_SECTIONS = ['appearance', 'ai', 'runtime', 'data', 'about'] as const;
export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

export interface Route {
  page: PageKey;
  tab: HistoryTab;
  section: SettingsSection;
}

export interface RouteTarget {
  page: PageKey;
  tab?: HistoryTab;
  section?: SettingsSection;
}

export const PAGE_LABELS: Record<PageKey, string> = {
  overview: '总览',
  history: '历史报告',
  agents: 'Agent 管理',
  notifications: '通知',
  settings: '设置',
};

export const HISTORY_TAB_LABELS: Record<HistoryTab, string> = {
  fills: '成交',
  orders: '订单',
  daily: '逐日核对',
  strategies: '策略档案',
  research: '研究档案',
};

export const SETTINGS_SECTION_LABELS: Record<SettingsSection, string> = {
  appearance: '外观',
  ai: 'AI 服务',
  runtime: '运行与安装',
  data: '数据连接',
  about: '关于',
};

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, '').split('?')[0].replace(/^\/+/, '');
  const [pagePart, tabPart] = raw.split('/');
  const page = (PAGE_KEYS as readonly string[]).includes(pagePart) ? (pagePart as PageKey) : 'overview';
  let tab: HistoryTab = 'fills';
  let section: SettingsSection = 'appearance';
  if (page === 'history') {
    if (tabPart === 'performance') tab = 'daily';
    else if (tabPart && (HISTORY_TABS as readonly string[]).includes(tabPart)) tab = tabPart as HistoryTab;
  }
  if (page === 'settings' && tabPart && (SETTINGS_SECTIONS as readonly string[]).includes(tabPart)) {
    section = tabPart as SettingsSection;
  }
  return { page, tab, section };
}

export function routeHref(route: RouteTarget): string {
  if (route.page === 'history') return `#history/${route.tab ?? 'fills'}`;
  if (route.page === 'settings') {
    const section = route.section ?? 'appearance';
    return section === 'appearance' ? '#settings' : `#settings/${section}`;
  }
  return `#${route.page}`;
}

export function navigate(route: RouteTarget, options: { replace?: boolean } = {}): void {
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
