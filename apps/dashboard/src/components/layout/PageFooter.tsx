import { formatClock } from '../../lib/format';
import { TERMS } from '../../lib/copy';

export function FreshnessNote({ loadedAt }: { loadedAt: number | null }) {
  if (!loadedAt) return null;
  return <span>{TERMS.updatedAt} {formatClock(loadedAt)}</span>;
}
