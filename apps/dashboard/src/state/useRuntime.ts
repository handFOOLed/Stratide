import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, friendlyError } from '../lib/api';
import { loadRuntimeStatus, runtimeAction } from '../lib/runtime';
import type { RuntimeStatus } from '../lib/runtime';
import { runtimeStatusPollIntervalMs } from '../lib/runtimePoll';
import {
  createRuntimeRefreshLocks,
  marketSummaryFrom,
  mergeMarketRead,
  refreshRuntimeSnapshot,
} from '../lib/runtimeRefresh';
import type { MarketSummary } from '../lib/runtimeRefresh';
import { useDocumentVisible, useInterval } from '../lib/hooks';

export type { MarketSummary };

export interface RuntimeState {
  status: RuntimeStatus | null;
  error: ApiError | null;
  checking: boolean;
  checkedAt: number | null;
  market: MarketSummary | null;
  refresh: () => void;
}

/**
 * 本机后台运行状态（服务 + 依赖 + 行情补录进度）。
 * 只读：所有操作仍由“系统与诊断”页显式触发。
 * 状态轮询与行情摘要分锁：慢的 market 请求不能跳过下一次 runtime status。
 */
export function useRuntime(): RuntimeState {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const [market, setMarket] = useState<MarketSummary | null>(null);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const locks = useRef(createRuntimeRefreshLocks());
  const marketRef = useRef<MarketSummary | null>(null);
  const visible = useDocumentVisible();

  const refresh = useCallback((silent = false) => {
    if (locks.current.statusBusy) return;
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    if (!silent) setChecking(true);
    void refreshRuntimeSnapshot(locks.current, {
      loadStatus: () => loadRuntimeStatus(next.signal),
      loadMarket: async () => {
        // backfill-state is a local file read. status opens the warehouse and
        // can fail or sit on the server's 60s limit while a writer holds the
        // lock. Either failure still publishes a summary so the badge cannot
        // stay on “正在读取”.
        try {
          const backfill = await runtimeAction<{
            running?: boolean;
            progress?: { sessions?: number; sessions_ready?: number; remaining?: number } | null;
          }>('market', { action: 'backfill-state' }, { timeoutMs: 8000, timeoutCode: 'MARKET_BACKFILL_STATE_TIMEOUT', signal: next.signal });
          try {
            const summary = await runtimeAction<{
              last_successful_date?: string | null;
              gaps?: unknown[];
              sessions_ready?: number;
              coverage_complete?: boolean;
            }>('market', { action: 'status' }, { timeoutMs: 8000, timeoutCode: 'MARKET_STATUS_TIMEOUT', signal: next.signal });
            return marketSummaryFrom(backfill, summary, null);
          } catch (caught) {
            if (caught instanceof ApiError && caught.code === 'ABORTED') throw caught;
            const code = caught instanceof ApiError ? caught.code : 'MARKET_STATUS_UNAVAILABLE';
            return marketSummaryFrom(backfill, null, code);
          }
        } catch (caught) {
          if (caught instanceof ApiError && caught.code === 'ABORTED') throw caught;
          const code = caught instanceof ApiError ? caught.code : 'MARKET_STATUS_UNAVAILABLE';
          return marketSummaryFrom({ running: false, progress: null }, null, code);
        }
      },
      onStatus: (value) => {
        if (!mounted.current) return;
        setStatus(value);
        setError(null);
        setCheckedAt(Date.now());
        setChecking(false);
      },
      onStatusError: (caught: unknown) => {
        if (!mounted.current) return;
        setChecking(false);
        const failure = friendlyError(caught);
        if (failure.code === 'ABORTED') return;
        setError(failure);
      },
      onMarket: (value) => {
        const merged = mergeMarketRead(marketRef.current, value);
        marketRef.current = merged;
        if (mounted.current) setMarket(merged);
      },
      onMarketMiss: () => {
        // ABORTED (unmount or a newer poll) keeps the last summary. A real
        // status failure returns a summary and is aged in mergeMarketRead.
      },
    });
  }, []);

  useEffect(() => {
    mounted.current = true;
    refresh();
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, [refresh]);

  useInterval(() => refresh(true), runtimeStatusPollIntervalMs(status, visible));

  return { status, error, checking, checkedAt, market, refresh: () => refresh() };
}
