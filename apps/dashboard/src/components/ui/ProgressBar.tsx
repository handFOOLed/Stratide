export function ProgressBar({
  value,
  tone = 'default',
  label,
}: {
  value: number;
  tone?: 'default' | 'warning' | 'danger';
  label: string;
}) {
  const clamped = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
    >
      <div
        className={`progress__bar${tone === 'warning' ? ' progress__bar--warning' : tone === 'danger' ? ' progress__bar--danger' : ''}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
