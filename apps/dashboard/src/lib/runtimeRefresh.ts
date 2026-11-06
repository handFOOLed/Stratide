/**
 * Runtime status polls and market-summary reads use separate in-flight gates.
 * A slow `/api/runtime/market` summary must not skip the next status poll,
 * or the UI keeps a light UNKNOWN / UNVERIFIED snapshot after full diagnostics.
 */

/**
 * verified: the latest successful warehouse report says coverage_complete.
 * rejected: that report explicitly says coverage_complete false.
 * unknown: no fresh report, a missing flag, or a backfill still running.
 * A progress file cannot change this.
 */
export type WarehouseVerification = 'verified' | 'rejected' | 'unknown';

export interface MarketSummary {
  sessionsReady: number;
  targetSessions: number;
  /** Null when the progress file has no remaining count and status has not arrived. */
  remaining: number | null;
  /** Download counter from the progress file, when that file had a number. */
  progressSessions: number | null;
  /** Session count from the latest successful warehouse report. */
  reportSessions: number | null;
  /** Explicit flag from the latest successful report. Null when this read has none. */
  coverageComplete: boolean | null;
  verification: WarehouseVerification;
  /**
   * Download ratio as a real percentage. Null when the counts are not known.
   * This is not warehouse verification.
   */
  downloadPercent: number | null;
  lastSuccessfulDate: string | null;
  gaps: number | null;
  backfillRunning: boolean;
  /** True only when verification is verified. Progress files and cached trues cannot set this. */
  backfillComplete: boolean;
  /** True only after a successful market status read. */
  statusKnown: boolean;
  /** Set when status failed. A busy warehouse is not the same as “still reading”. */
  statusError: string | null;
  /** Consecutive status reads that did not confirm the warehouse. */
  statusFailures: number;
  /** True after repeated unconfirmed reads. A previous completion is no longer claimed. */
  statusStale: boolean;
}

export interface MarketBackfillState {
  running?: boolean;
  progress?: { sessions?: number; sessions_ready?: number; remaining?: number } | null;
}

export interface MarketStatusSnapshot {
  last_successful_date?: string | null;
  gaps?: unknown[];
  sessions_ready?: number;
  /** Backend flag: calendar covers the configured window and the target session count is ready. */
  coverage_complete?: boolean;
}

/** Failures before a previously confirmed completion is dropped. */
export const MARKET_STATUS_STALE_POLLS = 2;

function finiteCount(value: number | undefined | null): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

/** Real download ratio. Null when either count is missing. Never a stand-in for verification. */
export function downloadPercent(ready: number | null, target: number | null): number | null {
  if (ready === null || target === null || target <= 0) return null;
  return Math.round((Math.min(ready, target) / target) * 100);
}

function coverageFlag(summary: MarketStatusSnapshot | null): boolean | null {
  if (summary === null || summary.coverage_complete === undefined) return null;
  return summary.coverage_complete === true;
}

/**
 * The latest successful report decides. Explicit false wins over a full
 * progress file, a full session count, and empty gaps. A missing flag or a
 * running job is unknown, not complete.
 */
export function warehouseVerification(
  running: boolean,
  statusKnown: boolean,
  coverageComplete: boolean | null,
  reportSessions: number | null,
  targetSessions: number,
  gaps: number | null,
): WarehouseVerification {
  if (!statusKnown) return 'unknown';
  if (coverageComplete === false) return 'rejected';
  if (running) return 'unknown';
  if (
    coverageComplete === true &&
    (reportSessions ?? 0) >= targetSessions &&
    (gaps ?? 0) === 0
  ) {
    return 'verified';
  }
  return 'unknown';
}

export function marketSummaryFrom(
  backfill: MarketBackfillState,
  summary: MarketStatusSnapshot | null,
  statusError: string | null = null,
): MarketSummary {
  const progress = backfill.progress ?? null;
  const progressSessions = finiteCount(progress?.sessions_ready);
  const progressTarget = finiteCount(progress?.sessions);
  const progressRemaining = progress === null ? null : finiteCount(progress.remaining);
  const reportSessions = summary === null ? null : finiteCount(summary.sessions_ready);
  const target = progressTarget ?? 84;
  const coverageComplete = coverageFlag(summary);
  const gaps = summary === null ? null : summary.gaps?.length ?? 0;
  const running = backfill.running === true;
  const statusKnown = summary !== null;
  const verification = warehouseVerification(
    running,
    statusKnown,
    coverageComplete,
    reportSessions,
    target,
    gaps,
  );
  // A fresh report's own session count is the download figure. The progress
  // file fills in only when that report is missing.
  const measuredReady = reportSessions ?? progressSessions;
  const measuredTarget = progressSessions !== null || reportSessions !== null ? target : null;
  return {
    sessionsReady: reportSessions ?? progressSessions ?? 0,
    targetSessions: target,
    remaining: progressRemaining,
    progressSessions,
    reportSessions,
    coverageComplete,
    verification,
    downloadPercent: downloadPercent(measuredReady, measuredTarget),
    lastSuccessfulDate: summary?.last_successful_date ?? null,
    gaps,
    backfillRunning: running,
    backfillComplete: verification === 'verified',
    statusKnown,
    statusError: summary !== null ? null : statusError,
    statusFailures: 0,
    statusStale: false,
  };
}

/**
 * A fresh report replaces the previous decision, including an explicit false.
 * A failed read does not keep a cached complete, and a progress file on that
 * read cannot create one. Download counts may still be shown.
 */
export function mergeMarketRead(previous: MarketSummary | null, incoming: MarketSummary): MarketSummary {
  if (incoming.statusKnown && incoming.statusError === null) {
    return { ...incoming, statusFailures: 0, statusStale: false };
  }
  const statusFailures = (previous?.statusFailures ?? 0) + 1;
  const kept = previous ?? incoming;
  const progressSessions = incoming.progressSessions ?? kept.progressSessions;
  const targetSessions = incoming.targetSessions || kept.targetSessions;
  return {
    sessionsReady: incoming.reportSessions ?? progressSessions ?? kept.sessionsReady,
    targetSessions,
    remaining: incoming.remaining !== null ? incoming.remaining : kept.remaining,
    progressSessions,
    // A failed read has no report. Do not keep the previous report count, or
    // the meter can pair a stale session total with a newer progress-file percent.
    reportSessions: null,
    coverageComplete: null,
    verification: 'unknown',
    downloadPercent: incoming.progressSessions !== null ? incoming.downloadPercent : null,
    lastSuccessfulDate: incoming.lastSuccessfulDate ?? kept.lastSuccessfulDate,
    gaps: incoming.gaps ?? kept.gaps,
    backfillRunning: incoming.backfillRunning,
    backfillComplete: false,
    statusKnown: false,
    statusError: incoming.statusError,
    statusFailures,
    statusStale: statusFailures >= MARKET_STATUS_STALE_POLLS,
  };
}

/** Chinese hint plus the stable API/client code. The code stays visible after a failed idle read. */
export function backfillReadFailure(code: string): { hint: string; diagnosticCode: string } {
  let hint = '行情进度暂时读不到，可稍后重试。';
  if (code.includes('WAREHOUSE_WRITER_BUSY') || code.includes('WRITER_ACTIVE')) {
    hint = '行情库正在写入，进度会在写入结束后更新。';
  } else if (code.includes('TIMEOUT')) {
    hint = '行情库空闲检查超时，进度还没有读到。';
  }
  return { hint, diagnosticCode: code };
}

export interface BackfillPresentation {
  /** Same bit as MarketSummary.backfillComplete. Views must not add another. */
  complete: boolean;
  verification: WarehouseVerification;
  /** Null means the bar is indeterminate. A number is the download ratio only. */
  downloadPercent: number | null;
  title: string;
  text: string;
  /** Secondary count. Null when we would be inventing one. */
  countText: string | null;
  diagnosticCode: string | null;
  tone: 'ok' | 'progress' | 'attention' | 'unset';
}

function countLine(market: MarketSummary, percent: number | null): string | null {
  if (percent === null) return null;
  const downloaded = market.reportSessions ?? market.progressSessions;
  if (downloaded === null) return null;
  let line = '已下载 ' + String(downloaded) + '/' + String(market.targetSessions) + '（' + String(percent) + '%）';
  if (
    market.reportSessions !== null &&
    market.progressSessions !== null &&
    market.reportSessions !== market.progressSessions
  ) {
    line += '，进度文件 ' + String(market.progressSessions) + '/' + String(market.targetSessions);
  }
  return line;
}

/**
 * One presentation for settings, overview, and the checklist.
 * complete is copied from the summary; it is not recomputed here.
 */
export function backfillPresentation(market: MarketSummary | null, runtimeUnreadable: boolean): BackfillPresentation {
  if (market === null) {
    return {
      complete: false,
      verification: 'unknown',
      downloadPercent: null,
      title: runtimeUnreadable ? '无法读取' : '正在读取',
      text: runtimeUnreadable ? '无法读取历史行情补录进度' : '正在读取历史行情补录进度',
      countText: null,
      diagnosticCode: null,
      tone: runtimeUnreadable ? 'attention' : 'progress',
    };
  }
  const complete = market.backfillComplete;
  const percent = market.statusStale ? null : market.downloadPercent;
  const countText = market.statusStale ? null : countLine(market, percent);
  if (market.backfillRunning) {
    const rejected = market.verification === 'rejected' ? '仓库校验未通过。' : '';
    return {
      complete,
      verification: market.verification,
      downloadPercent: percent,
      title: '进行中',
      text:
        (market.remaining === null ? '历史行情补录已开始。' : '待补齐 ' + String(market.remaining) + ' 个交易日。') +
        rejected,
      countText,
      diagnosticCode: null,
      tone: 'progress',
    };
  }
  if (complete) {
    return {
      complete,
      verification: 'verified',
      downloadPercent: percent,
      title: '已完成',
      text: '历史行情已就绪（' + String(market.sessionsReady) + ' 个交易日）',
      countText,
      diagnosticCode: null,
      tone: 'ok',
    };
  }
  if (market.verification === 'rejected') {
    return {
      complete,
      verification: 'rejected',
      downloadPercent: percent,
      title: '待校验',
      text: '仓库校验未通过，下载数量不能当成已完成。',
      countText,
      diagnosticCode: null,
      tone: 'attention',
    };
  }
  if (market.statusError !== null) {
    const failure = backfillReadFailure(market.statusError);
    return {
      complete,
      verification: 'unknown',
      downloadPercent: percent,
      title: '无法读取',
      text: market.statusStale ? '行情进度无法读取，请稍后重试。' : failure.hint,
      countText,
      diagnosticCode: failure.diagnosticCode,
      tone: 'attention',
    };
  }
  if (!market.statusKnown) {
    return {
      complete,
      verification: 'unknown',
      downloadPercent: percent,
      title: percent === null ? '正在读取' : '尚未确认',
      text: percent === null ? '正在读取历史行情补录进度' : '已有下载计数，仓库校验还没有读到。',
      countText,
      diagnosticCode: null,
      tone: 'progress',
    };
  }
  return {
    complete,
    verification: 'unknown',
    downloadPercent: percent,
    title: market.sessionsReady > 0 ? '尚未完成' : '尚未开始',
    text:
      market.sessionsReady > 0
        ? '仓库还没有确认校验完成。'
        : '历史行情补录尚未开始（目标 ' + String(market.targetSessions) + ' 个交易日）',
    countText: market.sessionsReady > 0 ? countText : null,
    diagnosticCode: null,
    tone: 'unset',
  };
}

export interface RuntimeRefreshLocks {
  statusBusy: boolean;
  marketBusy: boolean;
  marketPending: boolean;
  loadMarket: (() => Promise<unknown>) | null;
  publishMarket: ((market: unknown) => void) | null;
  publishMarketMiss: (() => void) | null;
}

export function createRuntimeRefreshLocks(): RuntimeRefreshLocks {
  return {
    statusBusy: false,
    marketBusy: false,
    marketPending: false,
    loadMarket: null,
    publishMarket: null,
    publishMarketMiss: null,
  };
}

export interface RuntimeRefreshJob<Status, Market> {
  loadStatus: () => Promise<Status>;
  loadMarket: () => Promise<Market>;
  onStatus: (status: Status) => void;
  onStatusError: (error: unknown) => void;
  onMarket: (market: Market) => void;
  onMarketMiss: () => void;
}

export type RuntimeRefreshResult = 'skipped' | 'ok' | 'error';

export async function refreshRuntimeSnapshot<Status, Market>(
  locks: RuntimeRefreshLocks,
  job: RuntimeRefreshJob<Status, Market>,
): Promise<RuntimeRefreshResult> {
  if (locks.statusBusy) return 'skipped';
  locks.statusBusy = true;
  let failed = false;
  try {
    const status = await job.loadStatus();
    job.onStatus(status);
  } catch (error) {
    failed = true;
    job.onStatusError(error);
  } finally {
    locks.statusBusy = false;
  }
  if (failed) return 'error';
  locks.loadMarket = () => job.loadMarket();
  locks.publishMarket = (market) => {
    job.onMarket(market as Market);
  };
  locks.publishMarketMiss = () => {
    job.onMarketMiss();
  };
  locks.marketPending = true;
  drainMarket(locks);
  return 'ok';
}

function drainMarket(locks: RuntimeRefreshLocks): void {
  if (locks.marketBusy) return;
  locks.marketBusy = true;
  void (async () => {
    try {
      while (locks.marketPending) {
        locks.marketPending = false;
        const loadMarket = locks.loadMarket;
        const publishMarket = locks.publishMarket;
        const publishMarketMiss = locks.publishMarketMiss;
        if (loadMarket === null || publishMarket === null || publishMarketMiss === null) break;
        try {
          const market = await loadMarket();
          publishMarket(market);
        } catch {
          publishMarketMiss();
        }
      }
    } finally {
      locks.marketBusy = false;
      if (locks.marketPending) drainMarket(locks);
    }
  })();
}
