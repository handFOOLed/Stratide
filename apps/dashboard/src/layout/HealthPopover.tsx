import { useEffect, useRef, useState } from 'react';
import { formatClock } from '../lib/format';
import { useOnClickOutside } from '../lib/hooks';
import { Icon } from '../icons';
import { StatusDot } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import type { HealthState } from '../state/useHealth';
import type { ApiError as ApiErrorType } from '../lib/api';
import type { SnapshotMeta } from '../lib/types';

const AGENT_LABEL: Record<string, string> = {
  not_implemented: '未接入',
  local_research_available: '本机可用',
};

const NOTIFICATION_LABEL: Record<string, string> = {
  not_implemented: '未接入',
};

export function HealthPopover({
  health,
  meta,
  paperError,
  onRefresh,
  refreshing,
}: {
  health: HealthState;
  meta: SnapshotMeta | null;
  paperError: ApiErrorType | null;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useOnClickOutside([wrapRef], () => setOpen(false), open);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  const online = !health.error && health.data?.service === 'online';
  const dotTone = health.checking && !health.data ? 'warning' : online ? 'online' : 'offline';
  const snapshotReady = Boolean(meta);
  const snapshotLabel = paperError
    ? paperError.code === 'NO_SNAPSHOT'
      ? '未选择报告'
      : paperError.code === 'INVALID_SNAPSHOT'
        ? '报告不可用'
        : '读取失败'
    : snapshotReady
      ? '已加载只读快照'
      : '尚未加载';

  return (
    <div className="popover-wrap" ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className="health-pill"
        data-tone={online ? 'online' : 'offline'}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="health-popover"
        onClick={() => setOpen((current) => !current)}
        title="本机服务状态"
      >
        <StatusDot tone={dotTone} />
        <span className="health-pill-label">
          {health.checking && !health.data ? '检查中' : online ? '服务在线' : '服务离线'}
        </span>
      </button>

      {open ? (
        <div className="popover" id="health-popover" role="dialog" aria-label="本机服务状态">
          <div className="popover__head">
            <div>
              <div className="popover__title">本机服务状态</div>
              <div className="popover__sub">只读 Paper · 127.0.0.1</div>
            </div>
            <span className="badge badge--outline">local</span>
          </div>
          <div className="popover__body">
            <div className="popover__row">
              <span className="popover__key">Web 服务</span>
              <span className="popover__value">
                <StatusDot tone={online ? 'online' : 'offline'} />
                {online ? '在线' : health.error ? '无法连接' : '检查中'}
              </span>
            </div>
            <div className="popover__row">
              <span className="popover__key">Paper 快照</span>
              <span className="popover__value">{snapshotLabel}</span>
            </div>
            <div className="popover__row">
              <span className="popover__key">行情时效</span>
              <span className="popover__value">
                {health.data?.market_data === 'last_published_snapshot_not_live'
                  ? '最后发布快照 · 非实时'
                  : health.data?.market_data ?? '未知'}
              </span>
            </div>
            <div className="popover__row">
              <span className="popover__key">前向账户</span>
              <span className="popover__value">
                {health.data?.forward_account === 'not_available' ? '尚未接入' : health.data?.forward_account ?? '未知'}
              </span>
            </div>
            <div className="popover__row">
              <span className="popover__key">研究 Agent</span>
              <span className="popover__value">
                {AGENT_LABEL[health.data?.agent ?? ''] ?? health.data?.agent ?? '未知'}
              </span>
            </div>
            <div className="popover__row">
              <span className="popover__key">通知服务</span>
              <span className="popover__value">
                {NOTIFICATION_LABEL[health.data?.notifications ?? ''] ?? health.data?.notifications ?? '未知'}
              </span>
            </div>
          </div>
          <div className="popover__foot">
            <span className="popover__time">
              {health.checkedAt ? '检查于 ' + formatClock(health.checkedAt) : '尚未检查'}
            </span>
            <Button size="sm" variant="ghost" icon="refresh" loading={refreshing || health.checking} onClick={onRefresh}>
              重新读取
            </Button>
          </div>
          <div className="popover__note">
            服务可达不等于风控运行正常或行情新鲜。更新 Paper 快照需显式重启服务。
          </div>
        </div>
      ) : null}
    </div>
  );
}