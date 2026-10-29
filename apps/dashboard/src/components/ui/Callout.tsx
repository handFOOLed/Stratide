import type { ReactNode } from 'react';
import { Icon } from '../../icons';
import type { IconName } from '../../icons';

const ICONS: Record<string, IconName> = {
  info: 'info',
  warning: 'alert-triangle',
  danger: 'alert-octagon',
  success: 'check',
};

export function Callout({
  tone = 'info',
  title,
  children,
  icon,
  className = '',
  role,
}: {
  tone?: 'info' | 'warning' | 'danger' | 'success';
  title?: ReactNode;
  children?: ReactNode;
  icon?: IconName;
  className?: string;
  role?: 'alert' | 'status';
}) {
  return (
    <div className={[`callout callout--${tone}`, className].filter(Boolean).join(' ')} role={role}>
      <span className="callout__icon">
        <Icon name={icon ?? ICONS[tone] ?? 'info'} />
      </span>
      <div className="callout__content">
        {title ? <div className="callout__title">{title}</div> : null}
        {children}
      </div>
    </div>
  );
}