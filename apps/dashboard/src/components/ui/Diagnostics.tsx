import type { MouseEvent, ReactNode } from 'react';
import { Icon } from '../../icons';
import { Kv } from './Kv';
import { useToast } from './Toast';
import { DIAGNOSTICS } from '../../lib/copy';

export interface DiagnosticItem {
  label: ReactNode;
  value: ReactNode;
}

async function writeClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

export function CopyButton({
  text,
  label = DIAGNOSTICS.copy,
  className = '',
  stopDetailsToggle = false,
}: {
  text: string;
  label?: string;
  className?: string;
  stopDetailsToggle?: boolean;
}) {
  const toast = useToast();
  const onClick = (event: MouseEvent<HTMLButtonElement>) => {
    if (stopDetailsToggle) {
      event.preventDefault();
      event.stopPropagation();
    }
    void writeClipboard(text).then(() => toast.push({ title: DIAGNOSTICS.copied, tone: 'success' }));
  };
  return (
    <button type="button" className={'diagnostics__copy' + (className === '' ? '' : ' ' + className)} onClick={onClick}>
      <Icon name="file" size={13} />
      {label}
    </button>
  );
}

/**
 * 诊断信息折叠区：默认收起，包含内部 ID / 原始状态 / 技术字段，并提供复制按钮。
 * 主界面不得展示这些内容，只允许出现在这里。
 */
export function Diagnostics({
  title = DIAGNOSTICS.title,
  items,
  data,
  hint = DIAGNOSTICS.hint,
  copyText,
}: {
  title?: string;
  items?: DiagnosticItem[];
  data?: unknown;
  hint?: string;
  copyText?: string;
}) {
  const payload = copyText ?? (data === undefined ? JSON.stringify(items ?? [], null, 2) : JSON.stringify(data, null, 2));
  return (
    <details className="diagnostics">
      <summary className="diagnostics__summary">
        <span className="diagnostics__title">
          <Icon name="info" size={14} />
          {title}
          <span className="diagnostics__hint">{hint}</span>
        </span>
        <CopyButton text={payload} stopDetailsToggle />
        <Icon name="chevron-down" size={14} className="diagnostics__chevron" />
      </summary>
      <div className="diagnostics__body">
        {items === undefined || items.length === 0 ? null : <Kv tight items={items} />}
        {data === undefined ? null : <pre className="diagnostics__raw">{JSON.stringify(data, null, 2)}</pre>}
      </div>
    </details>
  );
}
