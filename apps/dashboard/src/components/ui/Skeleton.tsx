export function Skeleton({ className = '', style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={['skeleton', className].filter(Boolean).join(' ')} style={style} aria-hidden="true" />;
}

export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          className={`skeleton-line${index === 0 ? ' skeleton-line--title' : index % 2 === 0 ? ' skeleton-line--short' : ''}`}
        />
      ))}
    </div>
  );
}

export function LoadingCard({ tall = false }: { tall?: boolean }) {
  return (
    <div className={`skeleton skeleton-card${tall ? ' skeleton-card--tall' : ''}`} aria-hidden="true" />
  );
}
