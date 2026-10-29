import type { ReactNode } from 'react';

export type BadgeTone =
  | 'neutral'
  | 'outline'
  | 'accent'
  | 'success'
  | 'gain'
  | 'loss'
  | 'warning'
  | 'danger';

export function Badge({
  tone = 'neutral',
  mono = false,
  children,
  className = '',
  title,
}: {
  tone?: BadgeTone;
  mono?: boolean;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      className={['badge', `badge--${tone}`, mono ? 'badge--mono' : '', className].filter(Boolean).join(' ')}
      title={title}
    >
      {children}
    </span>
  );
}

export function StatusDot({ tone = 'neutral' }: { tone?: 'neutral' | 'online' | 'offline' | 'warning' }) {
  return <span className={`status-dot status-dot--${tone}`} aria-hidden="true" />;
}
