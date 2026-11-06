/**
 * Runtime status polls and market-summary reads use separate in-flight gates.
 * A slow `/api/runtime/market` summary must not skip the next status poll,
 * or the UI keeps a light UNKNOWN / UNVERIFIED snapshot after full diagnostics.
 */

export interface MarketSummary {
  sessionsReady: number;
  targetSessions: number;
  remaining: number;
  lastSuccessfulDate: string | null;
  gaps: number;
  backfillRunning: boolean;
  backfillComplete: boolean;
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

export function marketSummaryFrom(backfill: MarketBackfillState, summary: MarketStatusSnapshot): MarketSummary {
  const progress = backfill.progress ?? null;
  const sessionsReady = progress?.sessions_ready ?? summary.sessions_ready ?? 0;
  const remaining = progress?.remaining ?? 0;
  return {
    sessionsReady,
    targetSessions: progress?.sessions ?? 84,
    remaining,
    lastSuccessfulDate: summary.last_successful_date ?? null,
    gaps: summary.gaps?.length ?? 0,
    backfillRunning: backfill.running === true,
    backfillComplete: progress !== null && progress.remaining === 0 && backfill.running !== true,
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
