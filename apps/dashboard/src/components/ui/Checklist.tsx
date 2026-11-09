import type { ReactNode } from 'react';
import { Icon } from '../../icons';
import { countText } from '../../lib/format';

export interface ChecklistItem {
  id: string;
  title: string;
  description?: ReactNode;
  done: boolean;
  /** 需要处理的入口（可选）。 */
  action?: ReactNode;
}

/**
 * 上手清单：完成一项打勾。总览在每一项都已确认完成时整块隐藏。
 * 内容必须来自真实状态，不得写死进度。
 */
export function Checklist({
  items,
  title = '上手清单',
}: {
  items: ChecklistItem[];
  title?: string;
}) {
  const doneCount = items.filter((item) => item.done).length;
  const allDone = doneCount === items.length;
  return (
    <section className={'checklist card' + (allDone ? ' checklist--done' : '')}>
      <div className="checklist__head">
        <span className="checklist__title">
          <Icon name={allDone ? 'check' : 'list'} size={16} />
          {title}
        </span>
        <span className="checklist__progress">
          {allDone ? '已完成' : countText(doneCount, '项') + ' / ' + countText(items.length, '项')}
        </span>
      </div>
      <ol className="checklist__items">
          {items.map((item) => (
            <li key={item.id} className={'checklist__item' + (item.done ? ' checklist__item--done' : '')}>
              <span className="checklist__mark" aria-hidden="true">
                <Icon name={item.done ? 'check' : 'arrow-right'} size={13} />
              </span>
              <div className="checklist__body">
                <div className="checklist__item-title">
                  {item.title}
                  <span className="sr-only">{item.done ? '（已完成）' : '（待完成）'}</span>
                </div>
                {item.description ? <div className="checklist__desc">{item.description}</div> : null}
              </div>
              {item.done ? null : item.action ? <div className="checklist__action">{item.action}</div> : null}
            </li>
          ))}
      </ol>
    </section>
  );
}
