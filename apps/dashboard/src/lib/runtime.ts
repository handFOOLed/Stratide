import { ApiError } from './api';

export interface ChildStatus {
  pid: number;
  started_at: string;
  restarts: number;
  instance_id?: string | null;
  last_exit?: { code: number | null; at: string } | null;
}

export interface BuildInfo {
  version: string | null;
  commit: string | null;
  built_at: string | null;
}

export interface RuntimeStatus {
  managed: boolean;
  product_version: string;
  /** 安装包 BUILD_INFO.json 的投影；源码树运行且无该文件时三个字段均为 null。 */
  build: BuildInfo;
  repo_url: string | null;
  issues_url: string | null;
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
  /** Present on fast/light snapshots; absent once background full diagnostics finish. */
  status_refresh?: 'light' | string;
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
    if (init.signal?.aborted) throw new ApiError('ABORTED', 'ABORTED', 0);
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
    headers: { Accept: 'application/json' },
    signal,
  });
}

export async function runtimeAction<T>(
  path: string,
  body: Record<string, unknown> = {},
  options: { timeoutMs?: number; timeoutCode?: string } = {},
): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer =
    options.timeoutMs === undefined
      ? null
      : setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, options.timeoutMs);
  try {
    return await read<T>('/api/runtime/' + path, {
      method: 'POST',
      credentials: 'omit',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) {
      const code = options.timeoutCode ?? 'REQUEST_TIMEOUT';
      throw new ApiError(code, code, 0);
    }
    throw error;
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

export interface SetupCompleteResult {
  state: 'COMPLETE' | 'INCOMPLETE' | string;
  setup_complete: boolean;
  completed_at: string | null;
}

/** 标记或撤销“首次设置完成”；撤销只删除运行目录标记，不影响账户/研究数据。 */
export async function setSetupComplete(completed: boolean | null): Promise<SetupCompleteResult> {
  return runtimeAction<SetupCompleteResult>('setup-complete', completed === null ? {} : { completed });
}

export function shanghaiToday(): string {
  return new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10).replaceAll('-', '');
}

export interface WslProbeResult {
  state: 'READY' | 'BLOCKED';
  reason: string | null;
  probe: Record<string, unknown>;
}
