import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, friendlyError, loadHealth } from '../lib/api';
import { useDocumentVisible, useInterval } from '../lib/hooks';
import type { HealthData } from '../lib/types';

export interface HealthState {
  data: HealthData | null;
  error: ApiError | null;
  checking: boolean;
  checkedAt: number | null;
  refresh: () => void;
}

const HEALTH_TIMEOUT_MS = 12_000;
/** Ignore a single slow response while the service was recently healthy. */
const STALE_OK_MS = 90_000;
const FAILURE_THRESHOLD = 2;

export function useHealth(): HealthState {
  const [data, setData] = useState<HealthData | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const visible = useDocumentVisible();
  const consecutiveFailures = useRef(0);
  const lastSuccessAt = useRef<number | null>(null);

  const refresh = useCallback((silent = false) => {
    if (inFlight.current) return;
    inFlight.current = true;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    if (!silent) setChecking(true);
    loadHealth({ signal: controller.signal, timeoutMs: HEALTH_TIMEOUT_MS })
      .then((result) => {
        if (!mounted.current) return;
        consecutiveFailures.current = 0;
        lastSuccessAt.current = Date.now();
        setData(result.data);
        setError(null);
        setCheckedAt(Date.now());
      })
      .catch((caught: unknown) => {
        if (!mounted.current) return;
        const failure = friendlyError(caught);
        if (failure.code === 'ABORTED') return;
        consecutiveFailures.current += 1;
        const recentlyHealthy =
          lastSuccessAt.current !== null && Date.now() - lastSuccessAt.current < STALE_OK_MS;
        const transient =
          (failure.code === 'TIMEOUT' || failure.code === 'OFFLINE') &&
          recentlyHealthy &&
          consecutiveFailures.current < FAILURE_THRESHOLD;
        if (transient) {
          setCheckedAt(Date.now());
          return;
        }
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
      controllerRef.current?.abort();
    };
  }, [refresh]);

  useInterval(() => refresh(true), visible ? 30_000 : null);

  return { data, error, checking, checkedAt, refresh: () => refresh() };
}
