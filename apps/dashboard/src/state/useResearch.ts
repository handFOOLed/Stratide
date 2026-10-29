import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, friendlyError, loadResearch } from '../lib/api';
import type { ResearchData } from '../lib/types';

export interface ResearchState {
  data: ResearchData | null;
  error: ApiError | null;
  loading: boolean;
  loadedAt: number | null;
  refresh: () => void;
}

export function useResearch(): ResearchState {
  const [data, setData] = useState<ResearchData | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
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
    setLoading(true);
    loadResearch({ signal: controller.signal })
      .then((result) => {
        if (!mounted.current || generation.current !== current) return;
        setData(result);
        setError(null);
        setLoadedAt(Date.now());
      })
      .catch((caught: unknown) => {
        if (!mounted.current || generation.current !== current) return;
        const failure = friendlyError(caught);
        if (failure.code === 'ABORTED') return;
        setError(failure);
      })
      .finally(() => {
        if (!mounted.current || generation.current !== current) return;
        setLoading(false);
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

  return { data, error, loading, loadedAt, refresh };
}
