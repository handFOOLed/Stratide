import type { ReactNode } from 'react';
import { StatusInline } from './StatusBadge';
import type { StatusView } from '../../lib/status';

export interface HealthBarItem {
  id: string;
  label: ReactNode;
  value: ReactNode;
  status?: StatusView;
  href?: string;
}

/**
 * 总览顶部健康条：模拟账户 | 数据更新至 | 系统状态 | AI 研究状态。
 * 每项都必须来自真实状态；可点击项跳转到对应页面。
 */
export function HealthBar({ items }: { items: HealthBarItem[] }) {
  return (
    <div className="health-bar" role="list" aria-label="账户与系统状态">
      {items.map((item) => {
        const content = (
          <>
            <span className="health-bar__label">{item.label}</span>
            <span className="health-bar__value">
              {item.status ? <StatusInline status={item.status} /> : null}
              {item.value === null || item.value === undefined ? null : <span className="health-bar__text">{item.value}</span>}
            </span>
          </>
        );
        return item.href ? (
          <a key={item.id} className="health-bar__item" href={item.href} role="listitem">
            {content}
          </a>
        ) : (
          <div key={item.id} className="health-bar__item" role="listitem">
            {content}
          </div>
        );
      })}
    </div>
  );
}
