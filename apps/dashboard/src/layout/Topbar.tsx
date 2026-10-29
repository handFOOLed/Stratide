import { Icon } from '../icons';
import { useTheme } from '../state/ThemeProvider';
import { HealthPopover } from './HealthPopover';
import type { HealthState } from '../state/useHealth';
import type { ApiError } from '../lib/api';
import type { SnapshotMeta } from '../lib/types';

export function Topbar({
  health,
  meta,
  paperError,
  onRefresh,
  refreshing,
  onOpenNav,
}: {
  health: HealthState;
  meta: SnapshotMeta | null;
  paperError: ApiError | null;
  onRefresh: () => void;
  refreshing: boolean;
  onOpenNav: () => void;
}) {
  const { resolvedTheme, toggleTheme } = useTheme();
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="topbar-left">
          <button type="button" className="icon-btn mobile-menu" aria-label="打开导航" title="打开导航" onClick={onOpenNav}>
            <Icon name="menu" />
          </button>
        </div>
        <div className="topbar-actions">
          <HealthPopover
            health={health}
            meta={meta}
            paperError={paperError}
            onRefresh={onRefresh}
            refreshing={refreshing}
          />
          <button
            type="button"
            className="icon-btn theme-toggle"
            aria-label={resolvedTheme === 'dark' ? '切换到浅色主题' : '切换到深色主题'}
            title={resolvedTheme === 'dark' ? '切换到浅色主题' : '切换到深色主题'}
            onClick={toggleTheme}
          >
            <Icon name={resolvedTheme === 'dark' ? 'sun' : 'moon'} />
          </button>
        </div>
      </div>
    </header>
  );
}
