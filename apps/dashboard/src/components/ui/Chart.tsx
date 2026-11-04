import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent, RefObject } from 'react';
import { buildChartModel, chartDayLabel, chartMetricValue } from '../../lib/chart';
import type { ChartMetric } from '../../lib/chart';
import { formatDay } from '../../lib/format';
import type { EquityRow } from '../../lib/types';

function useElementSize(ref: RefObject<HTMLDivElement | null>) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      const rect = element.getBoundingClientRect();
      setSize((current) =>
        Math.abs(current.width - rect.width) < 0.5 && Math.abs(current.height - rect.height) < 0.5
          ? current
          : { width: rect.width, height: rect.height },
      );
    };
    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

export function EquityChart({
  rows,
  metric,
  label,
  heightClass,
  navTopFen = null,
  baselineFen = null,
}: {
  rows: EquityRow[];
  metric: ChartMetric;
  label: string;
  heightClass?: string;
  navTopFen?: bigint | null;
  baselineFen?: bigint | null;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const measured = useElementSize(frameRef);
  const width = measured.width > 16 ? measured.width : 760;
  const height = measured.height > 16 ? measured.height : 260;
  const model = useMemo(
    () => buildChartModel(rows, metric, width, height, { navTopFen, baselineFen }),
    [height, metric, navTopFen, baselineFen, rows, width],
  );
  const [hover, setHover] = useState<number | null>(null);

  const points = useMemo(
    () => model?.points.filter((point): point is NonNullable<typeof point> => point !== null) ?? [],
    [model],
  );
  const active = hover !== null ? points[hover] ?? null : null;

  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    if (!model || points.length === 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    let best = 0;
    let distance = Number.POSITIVE_INFINITY;
    points.forEach((point, index) => {
      const d = Math.abs(point.x - x);
      if (d < distance) {
        distance = d;
        best = index;
      }
    });
    setHover(best);
  };

  const summary = useMemo(() => {
    if (!model || model.validCount === 0) return '没有有效估值';
    const first = model.points.find((point) => point !== null);
    const last = [...model.points].reverse().find((point) => point !== null);
    if (!first || !last) return '没有有效估值';
    const missing = model.totalCount - model.validCount;
    return (
      formatDay(model.firstDay ?? '') +
      ' 至 ' +
      formatDay(model.lastDay ?? '') +
      '，' +
      String(model.validCount) +
      ' 个有效估值。首个 ' +
      chartMetricValue(metric, first.value) +
      '，最后 ' +
      chartMetricValue(metric, last.value) +
      (missing > 0 ? '。缺失估值断开 ' + String(missing) + ' 日，不补点。' : '。')
    );
  }, [metric, model]);

  const frameClass = 'chart-frame' + (heightClass ? ' ' + heightClass : '');

  if (!model) {
    return (
      <div className={frameClass} ref={frameRef}>
        <div className="chart-empty">此区间没有有效估值。</div>
      </div>
    );
  }

  const tooltipLeft = active ? Math.min(Math.max(active.x, 66), Math.max(66, model.width - 66)) : 0;
  const tooltipTop = active ? active.y : 0;
  const tooltipStyle = active
    ? {
        left: tooltipLeft,
        top: tooltipTop,
        transform: tooltipTop < 72 ? 'translate(-50%, 12px)' : 'translate(-50%, calc(-100% - 12px))',
      }
    : undefined;

  return (
    <div className={frameClass} ref={frameRef}>
      <svg
        className="chart-svg"
        viewBox={'0 0 ' + String(model.width) + ' ' + String(model.height)}
        role="img"
        aria-label={label + '。' + summary}
        tabIndex={0}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHover(null)}
        onFocus={() => {
          if (hover === null && points.length > 0) setHover(points.length - 1);
        }}
        onBlur={() => setHover(null)}
        onKeyDown={(event) => {
          if (points.length === 0) return;
          if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            const current = hover === null ? points.length - 1 : hover;
            const next = event.key === 'ArrowLeft' ? Math.max(0, current - 1) : Math.min(points.length - 1, current + 1);
            setHover(next);
          } else if (event.key === 'Home') {
            event.preventDefault();
            setHover(0);
          } else if (event.key === 'End') {
            event.preventDefault();
            setHover(points.length - 1);
          } else if (event.key === 'Escape') {
            setHover(null);
          }
        }}
      >

        {/* Five equal steps: a faint dashed gridline every 20% of the axis. */}
        {model.ticks.map((tick) => (
          <g key={String(tick.y)}>
            <line
              className="chart-grid-line"
              x1={model.plot.left}
              x2={model.plot.right}
              y1={tick.y}
              y2={tick.y}
            />
            <text className="chart-axis-text" x={model.plot.left - 8} y={tick.y + 3} textAnchor="end">
              {tick.label}
            </text>
          </g>
        ))}

        {model.zeroY !== null ? (
          <line
            className="chart-zero-line"
            x1={model.plot.left}
            x2={model.plot.right}
            y1={model.zeroY}
            y2={model.zeroY}
          />
        ) : null}

        {model.baselineY !== null ? <g><line className="chart-zero" x1={model.plot.left} x2={model.plot.right} y1={model.baselineY} y2={model.baselineY}/><text className="chart-axis-text" x={model.plot.right} y={model.baselineY-5} textAnchor="end">本金</text></g> : null}
        {points.length <= 7 ? points.map(p=><circle className="chart-dot" key={p.day} cx={p.x} cy={p.y} r={3}/>) : null}
        {model.segments.map((segment, index) => (
          <path key={'line-' + String(index)} className="chart-line" d={segment} />
        ))}

        {active ? (
          <g>
            <line
              className="chart-cursor"
              x1={active.x}
              x2={active.x}
              y1={model.plot.top}
              y2={model.plot.bottom}
            />
            <circle className="chart-dot chart-dot--active" cx={active.x} cy={active.y} r={4.5} />
          </g>
        ) : null}

        {model.xTicks.map((tick, index) => (
          <text
            key={'x-' + String(index)}
            className="chart-axis-text"
            x={tick.x}
            y={model.height - 6}
            textAnchor={tick.anchor}
          >
            {chartDayLabel(tick.day)}
          </text>
        ))}
      </svg>

      {active ? (
        <div className="chart-tooltip" style={tooltipStyle} aria-hidden="true">
          <div className="chart-tooltip__day">{formatDay(active.day)}</div>
          <div className="chart-tooltip__value">{chartMetricValue(metric, active.value)}</div>
        </div>
      ) : null}
    </div>
  );
}
