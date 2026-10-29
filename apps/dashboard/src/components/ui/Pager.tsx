import { Icon } from '../../icons';

/**
 * Small explicit pager: previous / page numbers / next.
 * Used where a list must keep a fixed visible height (five position rows).
 */
export function Pager({
  page,
  pageCount,
  onPage,
  label,
}: {
  page: number;
  pageCount: number;
  onPage: (page: number) => void;
  label: string;
}) {
  if (pageCount <= 1) return null;
  const current = Math.min(Math.max(1, page), pageCount);
  const pages = pageNumbers(current, pageCount);
  return (
    <div className="pager" role="group" aria-label={label}>
      <button
        type="button"
        className="pager__btn"
        aria-label="上一页"
        title="上一页"
        disabled={current <= 1}
        onClick={() => onPage(current - 1)}
      >
        <Icon name="chevron-left" size={14} />
      </button>
      {pages.map((value, index) =>
        value === null ? (
          <span key={'gap-' + String(index)} className="pager__count" aria-hidden="true">…</span>
        ) : (
          <button
            key={value}
            type="button"
            className="pager__btn"
            aria-label={'第 ' + String(value) + ' 页'}
            aria-current={value === current ? 'page' : undefined}
            onClick={() => onPage(value)}
          >
            {value}
          </button>
        ),
      )}
      <button
        type="button"
        className="pager__btn"
        aria-label="下一页"
        title="下一页"
        disabled={current >= pageCount}
        onClick={() => onPage(current + 1)}
      >
        <Icon name="chevron-right" size={14} />
      </button>
    </div>
  );
}

function pageNumbers(current: number, pageCount: number): Array<number | null> {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, index) => index + 1);
  }
  const values: Array<number | null> = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(pageCount - 1, current + 1);
  if (start > 2) values.push(null);
  for (let page = start; page <= end; page += 1) values.push(page);
  if (end < pageCount - 1) values.push(null);
  values.push(pageCount);
  return values;
}
