import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { AppShell } from './layout/AppShell';
import { PageFooter } from './components/layout/PageFooter';
import { OverviewPage } from './pages/OverviewPage';
import { HistoryPage } from './pages/HistoryPage';
import { AgentPage } from './pages/AgentPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { SettingsPage } from './pages/SettingsPage';
import { navigate, useRoute, PAGE_LABELS } from './lib/route';
import type { HistoryTab } from './lib/route';
import { usePageScrollReset, usePageTitle } from './lib/hooks';
import { usePaperData } from './state/usePaperData';
import { useHealth } from './state/useHealth';
import { useResearch } from './state/useResearch';
import { useAgent } from './state/useAgent';

export function App() {
  const route = useRoute();
  const paper = usePaperData();
  const health = useHealth();
  const research = useResearch();
  const agent = useAgent(route.page === 'agents');
  const mainRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const previousPage = useRef(route.page);

  usePageTitle(PAGE_LABELS[route.page]);
  usePageScrollReset(mainRef, route.page + ':' + route.tab);

  useEffect(() => {
    if (previousPage.current === route.page) return;
    previousPage.current = route.page;
    window.requestAnimationFrame(() => {
      titleRef.current?.focus({ preventScroll: true });
    });
  }, [route.page]);

  useEffect(() => {
    if (route.page !== 'agents' && agent.detailOpen) {
      agent.closeTask();
    }
  }, [agent.detailOpen, agent.closeTask, route.page]);

  const refreshAll = () => {
    paper.refresh();
    health.refresh();
    research.refresh();
    if (route.page === 'agents' && agent.phase === 'ready') {
      void agent.refresh({ silent: true });
    }
  };

  let page: ReactNode;
  switch (route.page) {
    case 'history':
      page = (
        <HistoryPage
          paper={paper}
          research={research}
          tab={route.tab}
          onTab={(tab: HistoryTab) => navigate({ page: 'history', tab })}
          titleRef={titleRef}
        />
      );
      break;
    case 'agents':
      page = <AgentPage agent={agent} titleRef={titleRef} />;
      break;
    case 'notifications':
      page = <NotificationsPage health={health} titleRef={titleRef} />;
      break;
    case 'settings':
      page = <SettingsPage paper={paper} health={health} titleRef={titleRef} />;
      break;
    case 'overview':
    default:
      page = <OverviewPage paper={paper} titleRef={titleRef} />;
      break;
  }

  return (
    <AppShell
      route={route}
      health={health}
      meta={paper.meta}
      paperError={paper.error}
      onRefresh={refreshAll}
      refreshing={paper.refreshing || health.checking}
      mainRef={mainRef}
      footer={<PageFooter />}
    >
      <div className="page-frame" key={route.page}>
        {page}
      </div>
    </AppShell>
  );
}