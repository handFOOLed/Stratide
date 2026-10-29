import { BrandMark, Icon } from '../icons';
import type { IconName } from '../icons';
import { PAGE_LABELS, routeHref } from '../lib/route';
import type { PageKey, Route } from '../lib/route';

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
    <aside className={'sidebar' + (mobile ? ' sidebar--mobile' : '')} aria-label="工作空间侧边栏">
      {mobile ? <h2 className="sr-only" id="mobile-nav-title">主导航</h2> : null}
      <div className="sidebar-brand">
        <a href="#overview" className="brand-link" onClick={onNavigate} aria-label="Stratide 总览">
          <BrandMark />
        </a>
        <div className="brand-copy">
          <span className="brand-name">Stratide</span>
          <span className="brand-sub">Paper workspace</span>
        </div>
        {mobile && onClose ? (
          <button type="button" className="icon-btn mobile-nav-close" aria-label="关闭导航" onClick={onClose}>
            <Icon name="close" />
          </button>
        ) : null}
      </div>
      <div className="sidebar-scroll">
        <div className="nav-group">
          <p className="nav-label">工作空间</p>
          <nav className="nav-list" aria-label="主导航">
            {NAV.map((item) => (
              <a
                key={item.page}
                href={routeHref({ page: item.page, tab: route.tab })}
                className="nav-item"
                aria-current={route.page === item.page ? 'page' : undefined}
                title={PAGE_LABELS[item.page]}
                onClick={onNavigate}
              >
                <span className="nav-icon" aria-hidden="true">
                  <Icon name={item.icon} />
                </span>
                <span className="nav-text">{PAGE_LABELS[item.page]}</span>
              </a>
            ))}
          </nav>
        </div>
        <div className="sidebar-status" title="本机只读工作空间">
          <span className="status-dot status-dot--online" aria-hidden="true" />
          <span className="sidebar-status-copy">
            <span className="sidebar-status-title">本机 Paper 工作空间</span>
            <span className="sidebar-status-detail">只读账户 · 研究受控</span>
          </span>
        </div>
      </div>
      <div className="sidebar-footer">
        <span className="sidebar-footer-host">127.0.0.1 · local</span>
        <span className="sidebar-footer-version">v{__UI_VERSION__}</span>
      </div>
    </aside>
  );
}