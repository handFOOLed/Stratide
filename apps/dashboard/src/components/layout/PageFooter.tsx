import { formatClock } from '../../lib/format';

export function FreshnessNote({ loadedAt }: { loadedAt: number | null }) {
  if (!loadedAt) return null;
  return <span>读取于 {formatClock(loadedAt)}</span>;
}
