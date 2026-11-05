import type { ReactNode } from 'react';
import { Icon } from '../../icons';
import { STATUS_KIND_ICON } from '../../lib/status';
import type { StatusView } from '../../lib/status';

/**
 * 统一状态徽标：图标 + 颜色 + 文字，不能只靠颜色表达状态。
 * 主界面只允许 5 种状态色：ok / progress / attention / error / unset。
 */
export function StatusBadge({
  status,
  size = 'md',
  className = '',
}: {
  status: StatusView;
  size?: 'sm' | 'md';
  className?: string;
}) {
  return (
    <span
      className={'status-badge status-badge--' + status.kind + (size === 'sm' ? ' status-badge--sm' : '') + (className === '' ? '' : ' ' + className)}
      data-status={status.kind}
    >
      <Icon name={STATUS_KIND_ICON[status.kind]} size={size === 'sm' ? 12 : 13} />
      <span>{status.label}</span>
    </span>
  );
}

/** 状态徽标 + 一句话原因，用于列表行与卡片头部。 */
export function StatusLine({
  status,
  showReason = true,
  children,
  className = '',
}: {
  status: StatusView;
  showReason?: boolean;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <span className={'status-line' + (className === '' ? '' : ' ' + className)}>
      <StatusBadge status={status} size="sm" />
      {showReason && status.reason ? <span className="status-line__reason">{status.reason}</span> : null}
      {children}
    </span>
  );
}

/** 健康条 / 摘要行里的状态灯 + 文字。 */
export function StatusInline({ status, label, className = '' }: { status: StatusView; label?: string; className?: string }) {
  return (
    <span className={'status-inline status-inline--' + status.kind + (className === '' ? '' : ' ' + className)}>
      <span className="status-inline__dot" aria-hidden="true" />
      <span className="status-inline__text">{label ?? status.label}</span>
    </span>
  );
}
