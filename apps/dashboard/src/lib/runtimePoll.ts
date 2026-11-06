/** Normal dashboard poll while runtime status is complete. */
export const RUNTIME_STATUS_POLL_MS = 30_000;
/** Poll while backend still serves a light placeholder snapshot. */
export const RUNTIME_STATUS_FAST_POLL_MS = 2_000;

export interface RuntimeStatusRefreshHint {
  status_refresh?: string;
}

export function runtimeStatusPollIntervalMs(
  status: RuntimeStatusRefreshHint | null,
  visible: boolean,
): number | null {
  if (!visible) return null;
  if (status?.status_refresh === 'light') return RUNTIME_STATUS_FAST_POLL_MS;
  return RUNTIME_STATUS_POLL_MS;
}

export function runtimeStatusAwaitingFullRefresh(status: RuntimeStatusRefreshHint | null): boolean {
  return status?.status_refresh === 'light';
}
