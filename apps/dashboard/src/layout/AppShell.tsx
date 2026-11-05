import { useRef, useState } from 'react';
import type { ReactNode, RefObject } from 'react';
import { Overlay } from '../components/ui/Overlay';
import type { Route } from '../lib/route';
import type { HealthState } from '../state/useHealth';
import type { RuntimeState } from '../state/useRuntime';
import { SidebarContent } from './Sidebar';
import { Topbar } from './Topbar';

export function AppShell({
  route,
  health,
  runtime,
  mainRef,
  children,
}: {
  route: Route;
  health: HealthState;
  runtime: RuntimeState;
  mainRef: RefObject<HTMLDivElement | null>;
  children: ReactNode;
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
        <Topbar health={health} runtime={runtime} onOpenNav={() => setNavOpen(true)} />
        <main className="main-inner" id="main-content" tabIndex={-1} ref={contentRef}>
          {children}
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
