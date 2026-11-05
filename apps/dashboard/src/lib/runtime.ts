import { ApiError } from './api';

/** The desktop launcher passes this per-install token in the URL fragment.
 *  It is kept in memory only, never in storage, and stripped from the URL. */
let token = '';

export function captureRuntimeToken(): void {
  const hash = window.location.hash;
  const query = hash.indexOf('?');
  if (query < 0) return;
  const params = new URLSearchParams(hash.slice(query + 1));
  const value = params.get('rt');
  if (value) token = value;
  window.history.replaceState(null, '', hash.slice(0, query));
}

export function runtimeToken(): string {
  return token;
}

export interface ChildStatus {
  pid: number;
  started_at: string;
  restarts: number;
  instance_id?: string | null;
  last_exit?: { code: number | null; at: string } | null;
}

export interface RuntimeStatus {
  managed: boolean;
  product_version: string;
  home: string;
  app_dir: string;
  data_root: string;
  logs_dir: string;
  port: number;
  config_error: string | null;
  setup_complete: boolean;
  autostart: { task_name: string; exists: boolean; enabled: boolean; mechanism: string; detail: string };
  supervisor: {
    running: boolean;
    status: string;
    reason: string;
    pid: number;
    instance_id: string;
    started_at: string;
    updated_at: string;
    dashboard: ChildStatus | null;
    watch: ChildStatus | null;
  };
  service: {
    healthy: boolean;
    code?: string;
    instance_id?: string;
    pid?: string;
    agent?: string | null;
  };
  dependencies: {
    python: DependencyStatus;
    wsl: DependencyStatus;
    timesfm: DependencyStatus;
    tushare_credential: DependencyStatus;
    market_eod: DependencyStatus;
    paper_account: DependencyStatus;
    agent: DependencyStatus;
  };
  log_tail: string[];
}

export interface DependencyStatus {
  state: string;
  reason?: string;
  detail?: string;
  note?: string;
  version?: string;
  configured?: boolean;
  path?: string;
  distributions?: string[];
  database?: string;
  modified_at?: string | null;
  distribution?: string | null;
  workspace?: string | null;
  python?: string | null;
  model?: string | null;
}

interface EnvelopeShape<T> {
  api_version?: number;
  data?: T;
  error?: { code?: string } | null;
}

async function read<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError('OFFLINE', '无法连接本地服务；后台可能已停止。', 0);
  }
  let payload: EnvelopeShape<T>;
  try {
    payload = (await response.json()) as EnvelopeShape<T>;
  } catch {
    throw new ApiError('INVALID_RESPONSE', '本地服务返回了无法解析的响应。', response.status);
  }
  if (!response.ok || !payload.data) {
    const code = payload.error?.code ?? 'RUNTIME_REQUEST_FAILED';
    throw new ApiError(code, code, response.status);
  }
  if (response.ok && 'error' in payload && payload.error) {
    throw new ApiError(payload.error.code ?? 'RUNTIME_REQUEST_FAILED', payload.error.code ?? 'RUNTIME_REQUEST_FAILED', response.status);
  }
  return payload.data;
}

export async function loadRuntimeStatus(signal?: AbortSignal): Promise<RuntimeStatus> {
  return read<RuntimeStatus>('/api/runtime/status', {
    cache: 'no-store',
    credentials: 'omit',
    headers: { Accept: 'application/json', 'X-Stratide-Runtime': token },
    signal,
  });
}

export async function runtimeAction<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  return read<T>('/api/runtime/' + path, {
    method: 'POST',
    credentials: 'omit',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Stratide-Runtime': token,
    },
    body: JSON.stringify(body),
  });
}

export function shanghaiToday(): string {
  return new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10).replaceAll('-', '');
}

export interface WslProbeResult {
  state: 'READY' | 'BLOCKED';
  reason: string | null;
  probe: Record<string, unknown>;
}
