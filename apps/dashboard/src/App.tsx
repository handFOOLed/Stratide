import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { AppShell } from './layout/AppShell';
import { OverviewPage } from './pages/OverviewPage';
import { HistoryPage } from './pages/HistoryPage';
import { AgentPage } from './pages/AgentPage';
import { NotificationsPage } from './pages/NotificationsPage';
import { SettingsPage } from './pages/SettingsPage';
import { AgreementPage } from './pages/AgreementPage';
import { navigate, useRoute, PAGE_LABELS } from './lib/route';
import type { HistoryTab, SettingsSection } from './lib/route';
import { usePageScrollReset, usePageTitle } from './lib/hooks';
import { usePaperData } from './state/usePaperData';
import { useHealth } from './state/useHealth';
import { useResearch } from './state/useResearch';
import { useAgent } from './state/useAgent';
import { useWorkspace } from './lib/workspace';
import { readConsent } from './lib/consent';
import type { ConsentState } from './lib/consent';
import { useEffect as useEffectConsent, useState } from 'react';

export function App() {
  const route = useRoute();
  const [consent, setConsent] = useState<ConsentState | null>(null);
  useEffectConsent(() => {
    readConsent()
      .then(setConsent)
      .catch(() => setConsent(null));
  }, []);
  const paper = usePaperData('selected_report');
  const current = usePaperData('current');
  const health = useHealth();
  const research = useResearch();
  const agent = useAgent(route.page === 'agents' || route.page === 'notifications' || route.page === 'settings');
  const workspace = useWorkspace();
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
    current.refresh();
    health.refresh();
    research.refresh();
    workspace.refresh();
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
          workspace={workspace}
          tab={route.tab}
          onTab={(tab: HistoryTab) => navigate({ page: 'history', tab })}
          titleRef={titleRef}
        />
      );
      break;
    case 'agents':
      page = <AgentPage agent={agent} workspace={workspace} titleRef={titleRef} />;
      break;
    case 'notifications':
      page = <NotificationsPage agent={agent} titleRef={titleRef} />;
      break;
    case 'settings':
      page = (
        <SettingsPage
          paper={paper}
          health={health}
          workspace={workspace}
          agent={agent}
          section={route.section}
          onSection={(section: SettingsSection) => navigate({ page: 'settings', section })}
          titleRef={titleRef}
        />
      );
      break;
    case 'overview':
    default:
      page = <OverviewPage paper={current} titleRef={titleRef} />;
      break;
  }

  if (consent === null) {
    return <div className="agreement agreement--loading" role="status">正在读取本机设置…</div>;
  }
  if (consent.required) {
    return <AgreementPage />;
  }

  return (
    <AppShell
      route={route}
      health={health}
      meta={route.page==='history'?paper.meta:current.meta}
      paperError={route.page==='history'?paper.error:current.error}
      onRefresh={refreshAll}
      refreshing={paper.refreshing || current.refreshing || health.checking}
      mainRef={mainRef}
    >
      <div className="page-frame" key={route.page}>
        {page}
      </div>
    </AppShell>
  );
}
