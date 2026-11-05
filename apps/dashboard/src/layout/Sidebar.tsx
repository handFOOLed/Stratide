import { BrandMark, Icon } from '../icons';
import type { IconName } from '../icons';
import { PAGE_LABELS, routeHref } from '../lib/route';
import type { PageKey, Route } from '../lib/route';
import { SidebarUser } from './UserMenu';
import { APP } from '../lib/copy';

const NAV: Array<{ page: PageKey; icon: IconName }> = [
  { page: 'overview', icon: 'overview' },
  { page: 'history', icon: 'history' },
  { page: 'agents', icon: 'agent' },
  { page: 'notifications', icon: 'notifications' },
  { page: 'settings', icon: 'settings' },
];

export function SidebarContent({
  route,
  onNavigate,
  mobile = false,
  onClose,
}: {
  route: Route;
  onNavigate?: () => void;
  mobile?: boolean;
  onClose?: () => void;
}) {
  return (
    <aside className={'sidebar' + (mobile ? ' sidebar--mobile' : '')} aria-label="主导航">
      {mobile ? <h2 className="sr-only" id="mobile-nav-title">主导航</h2> : null}
      <div className="sidebar-brand">
        <a href="#overview" className="brand-link" onClick={onNavigate} aria-label="Stratide 总览">
          <BrandMark />
          <span className="brand-copy">
            <span className="brand-name">{APP.name}</span>
            <span className="brand-sub">模拟盘 · AI 研究</span>
          </span>
        </a>
        {mobile && onClose ? (
          <button type="button" className="icon-btn mobile-nav-close" aria-label="关闭导航" onClick={onClose}>
            <Icon name="close" />
          </button>
        ) : null}
      </div>
      <div className="sidebar-scroll">
        <nav className="nav-group" aria-label="主导航">
          <div className="nav-list">
            {NAV.map((item) => (
              <a
                key={item.page}
                href={routeHref({ page: item.page, tab: route.tab, section: route.section })}
                className="nav-item"
                aria-current={route.page === item.page ? 'page' : undefined}
                onClick={onNavigate}
              >
                <span className="nav-icon" aria-hidden="true">
                  <Icon name={item.icon} />
                </span>
                <span className="nav-text">{PAGE_LABELS[item.page]}</span>
              </a>
            ))}
          </div>
        </nav>
      </div>
      <SidebarUser />
    </aside>
  );
}
