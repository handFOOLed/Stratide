import type { ReactNode } from 'react';

export function Table({
  label,
  children,
  className = '',
  stack = false,
}: {
  label: string;
  children: ReactNode;
  className?: string;
  stack?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table className={['data-table', stack ? 'data-table--stack' : '', className].filter(Boolean).join(' ')}>
        <caption className="sr-only">{label}</caption>
        {children}
      </table>
    </div>
  );
}
