import { useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
}: {
  rows: EquityRow[];
  metric: ChartMetric;
  label: string;
  heightClass?: string;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const measured = useElementSize(frameRef);
  const width = measured.width > 16 ? measured.width : 760;
  const height = measured.height > 16 ? measured.height : 300;
  const model = useMemo(() => buildChartModel(rows, metric, width, height), [height, metric, rows, width]);
  const [hover, setHover] = useState<number | null>(null);
  const gradientId = 'chart-area-' + useId().replace(/[^a-zA-Z0-9_-]/g, '');

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
    return (
      formatDay(model.firstDay ?? '') +
      ' 至 ' +
      formatDay(model.lastDay ?? '') +
      '，' +
      String(model.validCount) +
      ' 个有效估值点。首个 ' +
      chartMetricValue(metric, first.value) +
      '，最后 ' +
      chartMetricValue(metric, last.value) +
      '。缺失估值保持断开，不补点。'
    );
  }, [metric, model]);

  const frameClass = 'chart-frame' + (heightClass ? ' ' + heightClass : '');

  if (!model) {
    return (
      <div className={frameClass} ref={frameRef}>
        <div className="chart-empty">此区间没有有效估值。缺失值保留为空，不生成收益点或填充日期。</div>
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
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" className="chart-stop-top" />
            <stop offset="100%" className="chart-stop-bottom" />
          </linearGradient>
        </defs>

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

        {model.areas.map((area, index) => (
          <path
            key={'area-' + String(index)}
            className="chart-area"
            d={area}
            style={{ fill: 'url(#' + gradientId + ')' }}
          />
        ))}
        {model.segments.map((segment, index) => (
          <path key={'line-' + String(index)} className="chart-line" d={segment} />
        ))}

        {model.totalCount <= 31
          ? model.points.map((point, index) =>
              point ? (
                <circle
                  key={'dot-' + String(index)}
                  className={'chart-dot' + (active === point ? ' chart-dot--active' : '')}
                  cx={point.x}
                  cy={point.y}
                  r={3}
                >
                  <title>{formatDay(point.day) + ' · ' + chartMetricValue(metric, point.value)}</title>
                </circle>
              ) : null,
            )
          : null}

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
            y={model.height - 8}
            textAnchor={tick.anchor}
          >
            {chartDayLabel(tick.day)}
          </text>
        ))}
      </svg>

      {active ? (
        <div
          className="chart-tooltip"
          style={tooltipStyle}
          aria-hidden="true"
        >
          <div className="chart-tooltip__day">{formatDay(active.day)}</div>
          <div className="chart-tooltip__value">
            {chartMetricValue(metric, active.value)}
            <span className="chart-tooltip__metric">
              {metric === 'return' ? '累计收益率' : metric === 'pnl' ? '累计盈亏' : '账户净值'}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}