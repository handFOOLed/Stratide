import type { ReactNode } from 'react';

export function Kv({ items, tight = false }: { items: Array<{ label: ReactNode; value: ReactNode }>; tight?: boolean }) {
  return (
    <dl className={`kv${tight ? ' kv--tight' : ''}`}>
      {items.map((item, index) => (
        <div key={index} className="kv__row">
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
