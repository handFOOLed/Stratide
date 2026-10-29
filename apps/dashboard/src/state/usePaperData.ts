import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, friendlyError, loadPaperBundle } from '../lib/api';
import type { PaperBundle, SnapshotMeta } from '../lib/types';

export type PaperPhase = 'loading' | 'ready' | 'error';

export interface PaperDataState {
  phase: PaperPhase;
  bundle: PaperBundle | null;
  meta: SnapshotMeta | null;
  error: ApiError | null;
  refreshing: boolean;
  loadedAt: number | null;
  stale: boolean;
  refresh: () => void;
}

const TERMINAL_CODES = new Set(['NO_SNAPSHOT', 'INVALID_SNAPSHOT', 'SNAPSHOT_CHANGED']);

export function usePaperData(): PaperDataState {
  const [bundle, setBundle] = useState<PaperBundle | null>(null);
  const [meta, setMeta] = useState<SnapshotMeta | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadedAt, setLoadedAt] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const mounted = useRef(true);

  const refresh = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    generation.current += 1;
    const current = generation.current;
    setRefreshing(true);
    setLoading(true);
    loadPaperBundle({ signal: controller.signal })
      .then((result) => {
        if (!mounted.current || generation.current !== current) return;
        setBundle(result.bundle);
        setMeta(result.meta);
        setError(null);
        setLoadedAt(Date.now());
      })
      .catch((caught: unknown) => {
        if (!mounted.current || generation.current !== current) return;
        const failure = friendlyError(caught);
        if (failure.code === 'ABORTED') return;
        setError(failure);
        if (TERMINAL_CODES.has(failure.code)) {
          setBundle(null);
          setMeta(null);
        }
      })
      .finally(() => {
        if (!mounted.current || generation.current !== current) return;
        setLoading(false);
        setRefreshing(false);
      });
  }, []);

  useEffect(() => {
    mounted.current = true;
    refresh();
    return () => {
      mounted.current = false;
      controllerRef.current?.abort();
    };
  }, [refresh]);

  const phase: PaperPhase = bundle ? 'ready' : loading ? 'loading' : 'error';
  return {
    phase,
    bundle,
    meta,
    error,
    refreshing,
    loadedAt,
    stale: Boolean(error && bundle),
    refresh,
  };
}
