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
}

export interface MarketBackfillState {
  running?: boolean;
  progress?: { sessions?: number; sessions_ready?: number; remaining?: number } | null;
}

export interface MarketStatusSnapshot {
  last_successful_date?: string | null;
  gaps?: unknown[];
  sessions_ready?: number;
}

export function marketSummaryFrom(
  backfill: MarketBackfillState,
  summary: MarketStatusSnapshot | null,
  statusError: string | null = null,
): MarketSummary {
  const progress = backfill.progress ?? null;
  const sessionsReady = progress?.sessions_ready ?? summary?.sessions_ready ?? 0;
  const gaps = summary === null ? null : summary.gaps?.length ?? 0;
  const running = backfill.running === true;
  const progressDone = progress !== null && progress.remaining === 0 && !running;
  // A finished warehouse can exist without a progress file (the file is removed
  // with the request). Empty gaps plus a non-zero ready count is completion.
  const warehouseDone =
    summary !== null && (summary.sessions_ready ?? 0) > 0 && (summary.gaps?.length ?? 0) === 0 && !running;
  const remaining = progress?.remaining ?? (warehouseDone ? 0 : null);
  return {
    sessionsReady,
    targetSessions: progress?.sessions ?? 84,
    remaining,
    lastSuccessfulDate: summary?.last_successful_date ?? null,
    gaps,
    backfillRunning: running,
    backfillComplete: progressDone || warehouseDone,
    statusKnown: summary !== null,
    statusError: summary !== null ? null : statusError,
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
