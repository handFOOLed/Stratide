/**
 * Runtime status polls and market-summary reads use separate in-flight gates.
 * A slow `/api/runtime/market` summary must not skip the next status poll,
 * or the UI keeps a light UNKNOWN / UNVERIFIED snapshot after full diagnostics.
 */

export interface MarketSummary {
  sessionsReady: number;
  targetSessions: number;
  /** Null when the progress file has no remaining count and status has not arrived. */
  remaining: number | null;
  lastSuccessfulDate: string | null;
  gaps: number | null;
  backfillRunning: boolean;
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

export function marketSummaryFrom(
  backfill: MarketBackfillState,
  summary: MarketStatusSnapshot | null,
  statusError: string | null = null,
): MarketSummary {
  const progress = backfill.progress ?? null;
  const target = progress?.sessions ?? 84;
  const sessionsReady = progress?.sessions_ready ?? summary?.sessions_ready ?? 0;
  const gaps = summary === null ? null : summary.gaps?.length ?? 0;
  const running = backfill.running === true;
  const progressDone =
    progress !== null &&
    progress.remaining === 0 &&
    !running &&
    (progress.sessions_ready ?? 0) >= (progress.sessions ?? target);
  // Empty gaps are not completion. report() sets coverage_complete only when
  // the calendar covers the configured window and sessions_ready meets the target.
  const warehouseDone =
    summary !== null &&
    !running &&
    summary.coverage_complete === true &&
    (summary.sessions_ready ?? 0) >= target &&
    (summary.gaps?.length ?? 0) === 0;
  const remaining = progress?.remaining ?? (warehouseDone ? 0 : null);
  return {
    sessionsReady,
    targetSessions: target,
    remaining,
    lastSuccessfulDate: summary?.last_successful_date ?? null,
    gaps,
    backfillRunning: running,
    backfillComplete: progressDone || warehouseDone,
    statusKnown: summary !== null,
    statusError: summary !== null ? null : statusError,
    statusFailures: 0,
    statusStale: false,
  };
}

/**
 * Keep the last confirmed session counts across a failed status read.
 * A completion that came only from the warehouse report is dropped at once.
 * After MARKET_STATUS_STALE_POLLS the read is marked stale. A progress file
 * from this read can still prove completion when it met the target.
 */
export function mergeMarketRead(previous: MarketSummary | null, incoming: MarketSummary): MarketSummary {
  if (incoming.statusKnown && incoming.statusError === null) {
    return { ...incoming, statusFailures: 0, statusStale: false };
  }
  const statusFailures = (previous?.statusFailures ?? 0) + 1;
  const kept = previous ?? incoming;
  // A progress file from this read can still prove completion. A previous
  // warehouse report cannot: its coverage flag was not reconfirmed.
  const progressConfirmed =
    incoming.remaining === 0 && !incoming.backfillRunning && incoming.sessionsReady >= incoming.targetSessions;
  return {
    sessionsReady: incoming.remaining !== null || incoming.backfillRunning ? incoming.sessionsReady : kept.sessionsReady,
    targetSessions: incoming.targetSessions || kept.targetSessions,
    remaining: incoming.remaining !== null ? incoming.remaining : kept.remaining,
    lastSuccessfulDate: incoming.lastSuccessfulDate ?? kept.lastSuccessfulDate,
    gaps: incoming.gaps ?? kept.gaps,
    backfillRunning: incoming.backfillRunning,
    backfillComplete: progressConfirmed,
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

export interface BackfillOverviewMessage {
  text: string;
  /** Shown apart from the sentence, in the muted diagnostic style. */
  diagnosticCode: string | null;
  complete: boolean;
}

/**
 * Checklist copy for the merged market summary. A stale read is not a
 * confirmed warehouse: the sentence says it cannot be read, and the code
 * stays out of that sentence.
 */
export function backfillOverviewMessage(
  market: MarketSummary | null,
  runtimeUnreadable: boolean,
): BackfillOverviewMessage {
  if (market === null) {
    return {
      text: runtimeUnreadable ? '无法读取历史行情补录进度' : '正在读取历史行情补录进度',
      diagnosticCode: null,
      complete: false,
    };
  }
  if (market.backfillRunning) {
    return {
      text:
        market.remaining === null
          ? '历史行情补录已开始'
          : '历史行情补录中：待补齐 ' + String(market.remaining) + ' 个交易日',
      diagnosticCode: null,
      complete: false,
    };
  }
  const confirmed = market.backfillComplete && !market.statusStale;
  if (market.statusError !== null && !confirmed) {
    const failure = backfillReadFailure(market.statusError);
    return {
      text: market.statusStale ? '行情进度无法读取，请稍后重试。' : failure.hint,
      diagnosticCode: failure.diagnosticCode,
      complete: false,
    };
  }
  if (confirmed) {
    return {
      text: '历史行情已就绪（' + String(market.sessionsReady) + ' 个交易日）',
      diagnosticCode: null,
      complete: true,
    };
  }
  if (!market.statusKnown) {
    return { text: '正在读取历史行情补录进度', diagnosticCode: null, complete: false };
  }
  if (market.sessionsReady > 0) {
    return {
      text: '历史行情补录尚未完成：待补齐 ' + String(market.remaining ?? market.gaps ?? 0) + ' 个交易日',
      diagnosticCode: null,
      complete: false,
    };
  }
  return {
    text: '历史行情补录尚未开始（目标 ' + String(market.targetSessions) + ' 个交易日）',
    diagnosticCode: null,
    complete: false,
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
