import type { HTMLAttributes, ReactNode } from 'react';

export function Card({
  children,
  className = '',
  quiet = false,
  flush = false,
  as: Tag = 'section',
  ...rest
}: {
  children: ReactNode;
  className?: string;
  quiet?: boolean;
  flush?: boolean;
  as?: 'section' | 'article' | 'div';
} & Omit<HTMLAttributes<HTMLElement>, 'children'>) {
  return (
    <Tag
      {...rest}
      className={['card', quiet ? 'card--quiet' : '', flush ? 'card--flush' : '', className]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </Tag>
  );
}

export function CardHead({
  title,
  subtitle,
  actions,
  bordered = false,
  eyebrow,
  id,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  bordered?: boolean;
  eyebrow?: ReactNode;
  id?: string;
}) {
  return (
    <div className={`card__head${bordered ? ' card__head--bordered' : ''}`}>
      <div className="card__heading">
        {eyebrow ? <div className="page-eyebrow">{eyebrow}</div> : null}
        <h2 className="card__title" id={id}>{title}</h2>
        {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="card__actions">{actions}</div> : null}
    </div>
  );
}

export function CardBody({
  children,
  flush = false,
  tight = false,
  className = '',
}: {
  children: ReactNode;
  flush?: boolean;
  tight?: boolean;
  className?: string;
}) {
  return (
    <div
      className={['card__body', flush ? 'card__body--flush' : '', tight ? 'card__body--tight' : '', className]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </div>
  );
}

export function CardFoot({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={['card__foot', className].filter(Boolean).join(' ')}>{children}</div>;
}
