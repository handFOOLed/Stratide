import { useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { Overlay } from '../components/ui/Overlay';
import type { ApiError } from '../lib/api';
import type { Route } from '../lib/route';
import type { SnapshotMeta } from '../lib/types';
import type { HealthState } from '../state/useHealth';
import { SidebarContent } from './Sidebar';
import { Topbar } from './Topbar';

export function AppShell({
  route,
  health,
  meta,
  paperError,
  onRefresh,
  refreshing,
  mainRef,
  children,
  footer,
}: {
  route: Route;
  health: HealthState;
  meta: SnapshotMeta | null;
  paperError: ApiError | null;
  onRefresh: () => void;
  refreshing: boolean;
  mainRef: RefObject<HTMLDivElement | null>;
  children: ReactNode;
  footer: ReactNode;
}) {
  const [navOpen, setNavOpen] = useState(false);
  const contentRef = useRef<HTMLElement>(null);
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          contentRef.current?.focus({ preventScroll: true });
          const scroller = mainRef.current;
          if (scroller && typeof scroller.scrollTo === 'function') {
            scroller.scrollTo({ top: 0, behavior: 'auto' });
          }
        }}
      >
        跳到主要内容
      </a>
      <SidebarContent route={route} />
      <div className="workspace" ref={mainRef}>
        <Topbar
          page={route.page}
          health={health}
          meta={meta}
          paperError={paperError}
          onRefresh={onRefresh}
          refreshing={refreshing}
          onOpenNav={() => setNavOpen(true)}
        />
        <main className="main-inner" id="main-content" tabIndex={-1} ref={contentRef}>
          {children}
          {footer}
        </main>
      </div>

      <Overlay
        open={navOpen}
        onClose={() => setNavOpen(false)}
        placement="left"
        duration={260}
        labelId="mobile-nav-title"
        className="overlay--nav"
      >
        <div className="mobile-nav-panel">
          <SidebarContent
            route={route}
            mobile
            onClose={() => setNavOpen(false)}
            onNavigate={() => setNavOpen(false)}
          />
        </div>
      </Overlay>
    </div>
  );
}