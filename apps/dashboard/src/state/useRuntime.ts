import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, friendlyError } from '../lib/api';
import { loadRuntimeStatus, runtimeAction } from '../lib/runtime';
import type { RuntimeStatus } from '../lib/runtime';
import { RUNTIME_STATUS_FAST_POLL_MS, RUNTIME_STATUS_POLL_MS, runtimeStatusPollIntervalMs } from '../lib/runtimePoll';
import { marketSummaryFrom, mergeMarketRead } from '../lib/runtimeRefresh';
import type { MarketBackfillState, MarketStatusSnapshot, MarketSummary } from '../lib/runtimeRefresh';
import { useDocumentVisible, useInterval } from '../lib/hooks';

export type { MarketSummary };

export interface RuntimeState {
  status: RuntimeStatus | null;
  error: ApiError | null;
  checking: boolean;
  checkedAt: number | null;
  market: MarketSummary | null;
  refresh: () => void;
  refreshAfterBackfill: () => void;
}

export function useRuntime(): RuntimeState {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const [market, setMarket] = useState<MarketSummary | null>(null);
  const statusRead = useRef<AbortController | null>(null);
  const marketRead = useRef<AbortController | null>(null);
  const visible = useDocumentVisible();

  const refreshStatus = useCallback(async (force = false) => {
    if (!force && statusRead.current !== null) return;
    statusRead.current?.abort();
    const next = new AbortController();
    statusRead.current = next;
    if (force) setChecking(true);
    try {
      const value = await loadRuntimeStatus(next.signal);
      if (next.signal.aborted) return;
      setStatus(value);
      setError(null);
      setCheckedAt(Date.now());
    } catch (caught) {
      if (!next.signal.aborted) setError(friendlyError(caught));
    } finally {
      if (statusRead.current === next) {
        statusRead.current = null;
        setChecking(false);
      }
    }
  }, []);

  const refreshMarket = useCallback(async (force = false) => {
    if (!force && marketRead.current !== null) return;
    marketRead.current?.abort();
    const next = new AbortController();
    marketRead.current = next;
    let backfill: MarketBackfillState = {};
    try {
      backfill = await runtimeAction<MarketBackfillState>('market', { action: 'backfill-state' }, {
        timeoutMs: 8000, timeoutCode: 'MARKET_BACKFILL_STATE_TIMEOUT', signal: next.signal,
      });
      if (next.signal.aborted) return;
      const progress = marketSummaryFrom(backfill, null);
      if (progress.backfillRunning || progress.backfillPhase === 'FAILED') {
        setMarket(progress);
        return;
      }
      setMarket((previous) =>
        previous === null || previous.backfillRunning || previous.backfillPhase !== progress.backfillPhase
          ? progress
          : previous,
      );
      const summary = await runtimeAction<MarketStatusSnapshot>('market', { action: 'status' }, {
        timeoutMs: 8000, timeoutCode: 'MARKET_STATUS_TIMEOUT', signal: next.signal,
      });
      if (!next.signal.aborted) setMarket(marketSummaryFrom(backfill, summary));
    } catch (caught) {
      if (next.signal.aborted) return;
      const code = caught instanceof ApiError ? caught.code : 'MARKET_STATUS_UNAVAILABLE';
      const failure = marketSummaryFrom(backfill, null, code);
      setMarket((previous) => mergeMarketRead(previous, failure));
    } finally {
      if (marketRead.current === next) marketRead.current = null;
    }
  }, []);

  const refresh = useCallback(() => {
    void refreshStatus(true);
    void refreshMarket(true);
  }, [refreshStatus, refreshMarket]);

  const refreshAfterBackfill = useCallback(() => {
    setMarket(marketSummaryFrom({ running: true, phase: 'QUEUED' }, null));
    refresh();
  }, [refresh]);

  useEffect(() => {
    refresh();
    return () => {
      statusRead.current?.abort();
      marketRead.current?.abort();
      statusRead.current = null;
      marketRead.current = null;
    };
  }, [refresh]);

  useInterval(() => void refreshStatus(), runtimeStatusPollIntervalMs(status, visible));
  const followingBackfill = market?.backfillRunning ||
    (market?.backfillPhase === 'VERIFYING' && !market.statusKnown && !market.statusStale);
  useInterval(() => void refreshMarket(), visible
    ? (followingBackfill ? RUNTIME_STATUS_FAST_POLL_MS : RUNTIME_STATUS_POLL_MS)
    : null);

  return { status, error, checking, checkedAt, market, refresh, refreshAfterBackfill };
}
