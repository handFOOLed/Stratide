import type { ReactNode } from 'react';

/**
 * 核心概念的“?”悬浮说明：每条不超过 2 句。
 */
export function InfoHint({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="info-hint">
      <button type="button" className="info-hint__trigger" aria-label={label}>
        ?
      </button>
      <span className="info-hint__bubble" role="tooltip">
        {children}
      </span>
    </span>
  );
}
