import type { ReactNode } from 'react';
import { Icon } from '../../icons';
import type { IconName } from '../../icons';
import { Button } from './Button';

export function EmptyState({
  title,
  description,
  icon = 'info',
  actions,
  code,
  compact = false,
  tone = 'neutral',
}: {
  title: ReactNode;
  description?: ReactNode;
  icon?: IconName;
  actions?: ReactNode;
  code?: ReactNode;
  compact?: boolean;
  tone?: 'neutral' | 'error';
}) {
  return (
    <div className={['empty-state', compact ? 'empty-state--compact' : '', tone === 'error' ? 'empty-state--error' : ''].filter(Boolean).join(' ')}>
      <div className="empty-state__icon">
        <Icon name={icon} />
      </div>
      <h3 className="empty-state__title">{title}</h3>
      {description ? <p className="empty-state__desc">{description}</p> : null}
      {actions ? <div className="empty-state__actions">{actions}</div> : null}
      {code ? <div className="empty-state__code">{code}</div> : null}
    </div>
  );
}

export function ErrorState({
  title,
  message,
  code,
  onRetry,
  actionLabel = '重新读取',
}: {
  title: ReactNode;
  message?: ReactNode;
  code?: string;
  onRetry?: () => void;
  actionLabel?: string;
}) {
  return (
    <EmptyState
      tone="error"
      icon="alert-triangle"
      title={title}
      description={message}
      code={code}
      actions={
        onRetry ? (
          <Button variant="secondary" icon="refresh" onClick={onRetry}>
            {actionLabel}
          </Button>
        ) : undefined
      }
    />
  );
}
