export function ProgressBar({
  value,
  indeterminate = false,
  tone = 'default',
  label,
}: {
  value: number | null;
  /** No numeric fill. Used when a percentage would be invented. */
  indeterminate?: boolean;
  tone?: 'default' | 'warning' | 'danger';
  label: string;
}) {
  const known = !indeterminate && typeof value === 'number' && Number.isFinite(value);
  if (!known) {
    return (
      <div className="progress progress--indeterminate" role="progressbar" aria-label={label} aria-valuetext="没有百分比">
        <div className="progress__bar progress__bar--indeterminate" />
      </div>
    );
  }
  const clamped = Math.min(100, Math.max(0, value as number));
  const toneClass = tone === 'warning' ? ' progress__bar--warning' : tone === 'danger' ? ' progress__bar--danger' : '';
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
    >
      <div className={'progress__bar' + toneClass} style={{ width: `${clamped}%` }} />
    </div>
  );
}
