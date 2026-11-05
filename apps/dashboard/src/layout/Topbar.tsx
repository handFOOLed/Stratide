import { Icon } from '../icons';
import { useTheme } from '../state/ThemeProvider';
import { overallSystemStatus } from '../lib/status';
import { StatusInline } from '../components/ui/StatusBadge';
import type { HealthState } from '../state/useHealth';
import type { RuntimeState } from '../state/useRuntime';

function systemPill(health: HealthState, runtime: RuntimeState) {
  const overall = overallSystemStatus({
    serviceOnline: !health.error && health.data?.service === 'online',
    healthChecking: health.checking,
    healthErrorCode: health.error?.code ?? null,
    runtime: runtime.status,
    runtimeErrorCode: runtime.error?.code ?? null,
  });
  if (health.checking && !health.data && runtime.status === null) {
    return { status: { kind: 'progress' as const, label: '检查中' }, overall };
  }
  return { status: overall.status.kind === 'error' && health.error !== null ? { kind: 'error' as const, label: '服务离线' } : overall.status, overall };
}

export function Topbar({
  health,
  runtime,
  onOpenNav,
}: {
  health: HealthState;
  runtime: RuntimeState;
  onOpenNav: () => void;
}) {
  const { resolvedTheme, toggleTheme } = useTheme();
  const { status } = systemPill(health, runtime);
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="topbar-left">
          <button type="button" className="icon-btn mobile-menu" aria-label="打开导航" title="打开导航" onClick={onOpenNav}>
            <Icon name="menu" />
          </button>
        </div>
        <div className="topbar-actions">
          <a
            className={'system-pill system-pill--' + status.kind}
            href="#settings/runtime"
            title={'系统状态：' + status.label + '，点击查看系统与诊断'}
          >
            <StatusInline status={status} />
            <Icon name="chevron-right" size={13} />
          </a>
          <button
            type="button"
            className="icon-btn theme-toggle"
            aria-label={resolvedTheme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            title={resolvedTheme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            onClick={toggleTheme}
          >
            <Icon name={resolvedTheme === 'dark' ? 'sun' : 'moon'} />
          </button>
        </div>
      </div>
    </header>
  );
}
