import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, friendlyError } from '../lib/api';
import { loadRuntimeStatus, runtimeAction } from '../lib/runtime';
import type { RuntimeStatus } from '../lib/runtime';
import { runtimeStatusPollIntervalMs } from '../lib/runtimePoll';
import {
  createRuntimeRefreshLocks,
  marketSummaryFrom,
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
        const [backfill, summary] = await Promise.all([
          runtimeAction<{ running?: boolean; progress?: { sessions?: number; sessions_ready?: number; remaining?: number } | null }>('market', { action: 'backfill-state' }),
          runtimeAction<{ last_successful_date?: string | null; gaps?: unknown[]; sessions_ready?: number }>('market', { action: 'status' }),
        ]);
        return marketSummaryFrom(backfill, summary);
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
        if (mounted.current) setMarket(value);
      },
      onMarketMiss: () => {
        if (mounted.current) setMarket(null);
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
