import type {
  AgentCreateResult,
  AgentStatus,
  AgentTaskDetail,
  AgentTaskList,
  Envelope,
  HealthData,
  PaperBundle,
  ResearchData,
  SnapshotMeta,
  StrategyRecord,
} from './types.ts';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail: string | null;

  constructor(code: string, message: string, status = 0, detail: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

export interface EnvelopeResult<T> {
  envelope: Envelope<T>;
  status: number;
}
const ERROR_MESSAGES: Record<string,string> = {
  REAL_MARKET_DATA_EGRESS_DENIED:'真实行情、TimesFM 风险及派生摘要尚未获云外发许可。',
  OWNER_PAUSED:'Owner 已暂停研究。', OWNER_TOKEN_REQUIRED:'请先解锁本机研究控制。',
  APPROVAL_EXPIRED:'本次许可已过期，请重新提交并核对。',APPROVAL_STATE_CONFLICT:'审批状态已变化，请重新读取原记录。',
  DESKTOP_AGENT_AUTHORITY_MISMATCH:'研究工作区未绑定当前 Agent；已阻止执行。',
  DESKTOP_BINDING_UNAVAILABLE:'原研究实例绑定不可用，未执行研究。',
  DEEPSEEK_DISABLED_OR_ONCE_CONSUMED:'原云调用开关已关闭或本次许可已消费。',
  LOCAL_CPU_DISABLED:'本地 CPU 研究已停用。', LOCAL_NO_BILLING:'本地研究，不计费。',
};
export function humanReason(value: string | null): string {
  if (value === null || value === '') return '—';
  if (Object.hasOwn(ERROR_MESSAGES,value)) return ERROR_MESSAGES[value];
  return /^[A-Za-z][A-Za-z0-9_]*_[A-Za-z0-9_]+$/.test(value) ? '状态或原因见技术详情' : value;
}

interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

async function readEnvelope<T>(path: string, options: RequestOptions = {}): Promise<EnvelopeResult<T>> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 8000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  options.signal?.addEventListener('abort', onAbort, { once: true });
  let response: Response;
  try {
    response = await fetch(path, {
      cache: 'no-store',
      credentials: 'omit',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) {
      throw new ApiError('ABORTED', '请求已取消', 0);
    }
    if (controller.signal.aborted) {
      throw new ApiError('TIMEOUT', '本地服务响应超时。请确认 Windows 上的 stratided 进程仍在运行。', 0);
    }
    throw new ApiError(
      'OFFLINE',
      '无法连接本地服务。请确认 stratided 正在运行，然后重新读取。',
      0,
      error instanceof Error ? error.message : null,
    );
  } finally {
    window.clearTimeout(timer);
    options.signal?.removeEventListener('abort', onAbort);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      'INVALID_RESPONSE',
      '本地服务返回了无法解析的响应。',
      response.status,
      null,
    );
  }

  if (!payload || typeof payload !== 'object') {
    throw new ApiError('INVALID_RESPONSE', '本地服务返回了空的响应。', response.status);
  }

  const envelope = payload as Envelope<T>;
  if (typeof envelope.api_version !== 'number' || !('data' in envelope)) {
    throw new ApiError('INVALID_RESPONSE', '响应不符合 Stratide API 的公开格式。', response.status);
  }
  return { envelope, status: response.status };
}

function envelopeError<T>(result: EnvelopeResult<T>): ApiError | null {
  const { envelope, status } = result;
  if (envelope.error) {
    return new ApiError(envelope.error.code, humanReason(envelope.error.message), status);
  }
  if (status !== 200) {
    return new ApiError('API_ERROR', `本地服务返回 HTTP ${status}。`, status);
  }
  return null;
}

export async function loadPaperBundle(purpose:'current'|'selected_report', options: RequestOptions = {}): Promise<{
  bundle: PaperBundle;
  meta: SnapshotMeta;
}> {
  const names = ['account', 'equity', 'positions', 'strategies', 'fills', 'orders'] as const;
  const results = await Promise.all(
    names.map((name) => readEnvelope<unknown>(`/api/${purpose==='current'?'v1/':''}${name}`, options)),
  );

  for (const result of results) {
    const error = envelopeError(result);
    if (error) throw error;
  }

  const [accountResult, equityResult, positionsResult, strategiesResult, fillsResult, ordersResult] =
    results;
  const meta = accountResult?.envelope.snapshot ?? null;
  if (!meta) {
    throw new ApiError('NO_SNAPSHOT', '尚未指定 Paper 报告。', 409);
  }
  for (const result of results) {
    if (result.envelope.snapshot?.snapshot_id !== meta.snapshot_id) {
      throw new ApiError(
        'SNAPSHOT_CHANGED',
        '读取期间本地服务返回了不同快照，已停止组合显示。请重新读取。',
        0,
      );
    }
  }

  const account = accountResult?.envelope.data;
  const equity = equityResult?.envelope.data;
  const positions = positionsResult?.envelope.data;
  const fills = fillsResult?.envelope.data;
  const orders = ordersResult?.envelope.data;
  if (!account || !Array.isArray(equity) || !Array.isArray(positions) || !Array.isArray(fills) || !Array.isArray(orders)) {
    throw new ApiError('INVALID_RESPONSE', '账户数据不完整，已停止展示以避免混用。', 0);
  }

  const rawStrategies = strategiesResult?.envelope.data as unknown;
  const strategies: StrategyRecord[] = Array.isArray(rawStrategies)
    ? (rawStrategies as StrategyRecord[])
    : rawStrategies && typeof rawStrategies === 'object'
      ? [rawStrategies as StrategyRecord]
      : [];

  return {
    bundle: {
      account: account as PaperBundle['account'],
      equity: equity as PaperBundle['equity'],
      positions: positions as PaperBundle['positions'],
      strategies,
      fills: fills as PaperBundle['fills'],
      orders: orders as PaperBundle['orders'],
    },
    meta,
  };
}

export async function loadHealth(options: RequestOptions = {}): Promise<{
  data: HealthData;
  meta: SnapshotMeta | null;
}> {
  const result = await readEnvelope<HealthData>('/api/health', { timeoutMs: 4000, ...options });
  const error = envelopeError(result);
  if (error) throw error;
  if (!result.envelope.data) {
    throw new ApiError('INVALID_RESPONSE', '健康检查响应缺少 data。', result.status);
  }
  return { data: result.envelope.data, meta: result.envelope.snapshot };
}

export async function loadResearch(options: RequestOptions = {}): Promise<ResearchData> {
  const result = await readEnvelope<ResearchData>('/api/research', options);
  const error = envelopeError(result);
  if (error) throw error;
  if (!result.envelope.data) {
    throw new ApiError('INVALID_RESPONSE', '研究档案响应缺少 data。', result.status);
  }
  return result.envelope.data;
}

// ---------- Agent API: owner-gated, memory-only token ----------

interface AgentRequestOptions {
  idempotencyKey?: string;
  method?: 'GET' | 'POST';
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function agentFetch<T>(token: string, path: string, options: AgentRequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 8000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  options.signal?.addEventListener('abort', onAbort, { once: true });
  const hasBody = options.body !== undefined;
  let response: Response;
  try {
    response = await fetch(`/api/agent/${path}`, {
      method: options.method ?? 'GET',
      cache: 'no-store',
      credentials: 'omit',
      headers: {
        Accept: 'application/json',
        'X-Stratide-Owner': token,
        ...(options.idempotencyKey === undefined ? {} : {'X-Stratide-Idempotency':options.idempotencyKey}),
        ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
      signal: controller.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) throw new ApiError('ABORTED', '请求已取消', 0);
    if (controller.signal.aborted) {
      throw new ApiError('TIMEOUT', '本机研究服务响应超时。', 0);
    }
    throw new ApiError(
      'OFFLINE',
      '无法连接本机研究服务。',
      0,
      error instanceof Error ? error.message : null,
    );
  } finally {
    window.clearTimeout(timer);
    options.signal?.removeEventListener('abort', onAbort);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError('INVALID_RESPONSE', '研究服务返回了无法解析的响应。', response.status);
  }
  if (!payload || typeof payload !== 'object') {
    throw new ApiError('INVALID_RESPONSE', '研究服务返回了空响应。', response.status);
  }
  const envelope = payload as Envelope<T>;
  if (!response.ok) {
    const error = envelope.error;
    throw new ApiError(
      error?.code ?? 'AGENT_API_ERROR',
      error === null ? `研究服务返回 HTTP ${response.status}。` : humanReason(error.message),
      response.status,
    );
  }
  if (!('data' in envelope) || envelope.data === null) {
    throw new ApiError('INVALID_RESPONSE', '研究服务响应缺少 data。', response.status);
  }
  return envelope.data;
}

export function loadAgentStatus(token: string, signal?: AbortSignal): Promise<AgentStatus> {
  return agentFetch<AgentStatus>(token, 'status', { signal });
}

export function loadAgentTasks(
  token: string,
  before: string | null,
  signal?: AbortSignal,
): Promise<AgentTaskList> {
  const suffix = before ? `?before=${encodeURIComponent(before)}` : '';
  return agentFetch<AgentTaskList>(token, `tasks${suffix}`, { signal });
}

export function loadAgentTask(token: string, id: string, signal?: AbortSignal): Promise<AgentTaskDetail> {
  return agentFetch<AgentTaskDetail>(token, `tasks/${encodeURIComponent(id)}`, { signal }).then(detail => {
    const r = detail.result;
    if (r !== null && (!r.research || !Array.isArray(r.research.evidence) || !Array.isArray(r.research.risks) || !Array.isArray(r.research.next_steps) || typeof r.research.hypothesis !== 'string')) {
      return {...detail, artifact:r, result:null};
    }
    return detail;
  });
}

export function createAgentTask(
  token: string,
  input: {
    name: string;
    goal: string;
    scope: string;
    start_day: string;
    end_day: string;
    task_budget_micro: string | null;
  },
  idempotencyKey: string,
): Promise<AgentCreateResult> {
  return agentFetch<AgentCreateResult>(token, 'tasks', {
    method: 'POST',
    body: input,
    idempotencyKey,
    timeoutMs: 12000,
  });
}

export function cancelAgentTask(token: string, id: string): Promise<unknown> {
  return agentFetch<unknown>(token, `tasks/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
    body: {},
  });
}

export function retryAgentTask(token: string, id: string): Promise<unknown> {
  return agentFetch<unknown>(token, `tasks/${encodeURIComponent(id)}/retry`, {
    method: 'POST',
    body: {},
  });
}

export function controlAgent(
  token: string,
  body:
    | { action: 'pause' }
    | { action: 'resume' }
    | { action: 'eod'; enabled: boolean }
    | { action: 'model'; model_id: string }
    | { action: 'backup'; model_id: string },
): Promise<unknown> {
  return agentFetch<unknown>(token, 'control', { method: 'POST', body });
}

export function friendlyError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (error instanceof Error) {
    return new ApiError('UNKNOWN', error.message || '发生未知错误。', 0);
  }
  return new ApiError('UNKNOWN', '发生未知错误。', 0);
}
