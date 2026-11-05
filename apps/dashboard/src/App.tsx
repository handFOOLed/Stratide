import { useEffect, useRef, useState } from 'react';
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
import { useRuntime } from './state/useRuntime';
import { useWorkspace } from './lib/workspace';
import { readConsent } from './lib/consent';
import type { ConsentState } from './lib/consent';

export function App() {
  const route = useRoute();
  const [consent, setConsent] = useState<ConsentState | null>(null);
  useEffect(() => {
    readConsent()
      .then(setConsent)
      .catch(() => setConsent(null));
  }, []);
  const paper = usePaperData('selected_report');
  const current = usePaperData('current');
  const health = useHealth();
  const runtime = useRuntime();
  const research = useResearch();
  // 研究状态需要在总览健康条与通知页展示，因此始终轻量轮询本机状态。
  const agent = useAgent(true);
  const workspace = useWorkspace();
  const mainRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const previousPage = useRef(route.page);

  usePageTitle(PAGE_LABELS[route.page]);
  usePageScrollReset(mainRef, route.page + ':' + route.tab + ':' + route.section);

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
          runtime={runtime}
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
      page = <OverviewPage paper={current} health={health} runtime={runtime} agent={agent} titleRef={titleRef} />;
      break;
  }

  if (consent === null) {
    return <div className="agreement agreement--loading" role="status">正在读取本机设置…</div>;
  }
  if (consent.required) {
    return <AgreementPage />;
  }

  return (
    <AppShell route={route} health={health} runtime={runtime} mainRef={mainRef}>
      <div className="page-frame" key={route.page}>
        {page}
      </div>
    </AppShell>
  );
}
