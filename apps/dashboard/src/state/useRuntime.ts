import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, friendlyError } from '../lib/api';
import { loadRuntimeStatus, runtimeAction } from '../lib/runtime';
import type { RuntimeStatus } from '../lib/runtime';
import { useDocumentVisible, useInterval } from '../lib/hooks';

export interface MarketSummary {
  /** 仓库中已就绪的交易日总数（可能大于目标 84）。 */
  sessionsReady: number;
  /** 补录目标（通常 84 个交易日）。 */
  targetSessions: number;
  /** 还差多少个交易日才补完；0 表示完成。 */
  remaining: number;
  lastSuccessfulDate: string | null;
  gaps: number;
  backfillRunning: boolean;
  /** 补录是否已完成：以 remaining==0 为准，而不是 sessionsReady/84。 */
  backfillComplete: boolean;
}

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
 */
export function useRuntime(): RuntimeState {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const [market, setMarket] = useState<MarketSummary | null>(null);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const inFlight = useRef(false);
  const visible = useDocumentVisible();

  const refresh = useCallback((silent = false) => {
    if (inFlight.current) return;
    inFlight.current = true;
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;
    if (!silent) setChecking(true);
    loadRuntimeStatus(next.signal)
      .then(async (value) => {
        if (!mounted.current) return;
        setStatus(value);
        setError(null);
        setCheckedAt(Date.now());
        // 行情仓库可能尚未初始化，读不到补录进度是诚实的“未配置”状态，
        // 不应把整块系统状态标成读取失败。
        try {
          const [backfill, summary] = await Promise.all([
            runtimeAction<{ running?: boolean; progress?: { sessions?: number; sessions_ready?: number; remaining?: number } | null }>('market', { action: 'backfill-state' }),
            runtimeAction<{ last_successful_date?: string | null; gaps?: unknown[]; sessions_ready?: number }>('market', { action: 'status' }),
          ]);
          if (!mounted.current) return;
          const progress = backfill.progress ?? null;
          const sessionsReady = progress?.sessions_ready ?? summary.sessions_ready ?? 0;
          const remaining = progress?.remaining ?? 0;
          setMarket({
            sessionsReady,
            targetSessions: progress?.sessions ?? 84,
            remaining,
            lastSuccessfulDate: summary.last_successful_date ?? null,
            gaps: summary.gaps?.length ?? 0,
            backfillRunning: backfill.running === true,
            // 没有进度记录时不能当作“补录完成”。
            backfillComplete: progress !== null && progress.remaining === 0 && backfill.running !== true,
          });
        } catch {
          if (mounted.current) setMarket(null);
        }
      })
      .catch((caught: unknown) => {
        if (!mounted.current) return;
        const failure = friendlyError(caught);
        if (failure.code === 'ABORTED') return;
        setError(failure);
      })
      .finally(() => {
        inFlight.current = false;
        if (mounted.current) setChecking(false);
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

  useInterval(() => refresh(true), visible ? 30_000 : null);

  return { status, error, checking, checkedAt, market, refresh: () => refresh() };
}
