import { ProgressBar } from '../ui/ProgressBar';
import { backfillPresentation } from '../../lib/runtimeRefresh';
import type { MarketSummary } from '../../lib/runtimeRefresh';

/** Shared backfill meter. Completion text comes only from backfillPresentation. */
export function BackfillMeter({
  market,
  runtimeUnreadable = false,
}: {
  market: MarketSummary | null;
  runtimeUnreadable?: boolean;
}) {
  const view = backfillPresentation(market, runtimeUnreadable);
  return (
    <div className="backfill-meter" data-verification={view.verification} data-complete={view.complete ? 'true' : 'false'}>
      <p className="backfill-meter__text">{view.text}</p>
      {view.downloadPercent === null ? (
        <p className="backfill-meter__percent">—</p>
      ) : (
        <p className="backfill-meter__percent">{view.downloadPercent}%</p>
      )}
      {view.countText ? <p className="backfill-meter__count">{view.countText}</p> : null}
      <ProgressBar
        value={view.downloadPercent}
        indeterminate={view.downloadPercent === null}
        tone={view.complete ? 'default' : 'warning'}
        label={view.complete ? '历史补录已校验' : '历史补录下载进度'}
      />
      {view.diagnosticCode ? <code className="backfill-diagnostic__code">{view.diagnosticCode}</code> : null}
    </div>
  );
}
