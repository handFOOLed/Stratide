import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  cancelAgentTask,
  controlAgent,
  createAgentTask,
  friendlyError,
  loadAgentStatus,
  loadAgentTask,
  loadAgentTasks,
  retryAgentTask,
} from '../lib/api';
import { useDocumentVisible, useInterval } from '../lib/hooks';
import type {
  AgentStatus,
  AgentTask,
  AgentTaskDetail,
} from '../lib/types';

export type AgentPhase = 'locked' | 'loading' | 'ready' | 'error';

export interface CreateTaskInput {
  name: string;
  goal: string;
  scope: string;
  start_day: string;
  end_day: string;
  task_budget_micro: string | null;
}

export interface AgentState {
  token: string | null;
  phase: AgentPhase;
  status: AgentStatus | null;
  tasks: AgentTask[];
  nextBefore: string | null;
  pageBefore: string | null;
  error: ApiError | null;
  busy: string | null;
  refreshing: boolean;
  lastUpdated: number | null;
  detail: AgentTaskDetail | null;
  detailOpen: boolean;
  detailLoading: boolean;
  detailError: ApiError | null;
  unlock: (token: string) => Promise<ApiError | null>;
  lock: () => void;
  refresh: (options?: { silent?: boolean; before?: string | null }) => Promise<void>;
  goPage: (before: string | null) => Promise<void>;
  createTask: (input: CreateTaskInput) => Promise<{ error: ApiError | null; id?: string }>;
  cancelTask: (id: string) => Promise<ApiError | null>;
  retryTask: (id: string) => Promise<ApiError | null>;
  control: (
    body:
      | { action: 'pause' }
      | { action: 'resume' }
      | { action: 'eod'; enabled: boolean }
      | { action: 'model'; model_id: string }
      | { action: 'backup'; model_id: string },
  ) => Promise<ApiError | null>;
  openTask: (id: string) => Promise<void>;
  closeTask: () => void;
  refreshDetail: () => Promise<void>;
}

export function useAgent(active: boolean): AgentState {
  const [token, setToken] = useState<string | null>(null);
  const [phase, setPhase] = useState<AgentPhase>('locked');
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [pageBefore, setPageBefore] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [detail, setDetail] = useState<AgentTaskDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ApiError | null>(null);

  const mounted = useRef(true);
  const generation = useRef(0);
  const pageBeforeRef = useRef<string | null>(null);
  const mainController = useRef<AbortController | null>(null);
  const detailController = useRef<AbortController | null>(null);
  const inFlight = useRef(false);
  const visible = useDocumentVisible();

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      mainController.current?.abort();
      detailController.current?.abort();
    };
  }, []);

  const clearSession = useCallback(() => {
    generation.current += 1;
    mainController.current?.abort();
    detailController.current?.abort();
    inFlight.current = false;
    setToken(null);
    setStatus(null);
    setTasks([]);
    setNextBefore(null);
    setPageBefore(null);
    setDetail(null);
    setDetailOpen(false);
    setDetailLoading(false);
    setDetailError(null);
    setRefreshing(false);
    setBusy(null);
    setPhase('locked');
    pageBeforeRef.current = null;
  }, []);

  const lock = useCallback(() => {
    clearSession();
    setError(null);
    setLastUpdated(null);
  }, [clearSession]);

  const loadAll = useCallback(
    async (
      activeToken: string,
      before: string | null,
      options: { silent?: boolean; generationAtStart?: number } = {},
    ): Promise<boolean> => {
      if (inFlight.current) return false;
      inFlight.current = true;
      const current = options.generationAtStart ?? generation.current;
      mainController.current?.abort();
      const controller = new AbortController();
      mainController.current = controller;
      if (!options.silent) setRefreshing(true);
      try {
        const [nextStatus, taskList] = await Promise.all([
          loadAgentStatus(activeToken, controller.signal),
          loadAgentTasks(activeToken, before, controller.signal),
        ]);
        if (!mounted.current || generation.current !== current) return false;
        setStatus(nextStatus);
        setTasks(taskList.tasks);
        setNextBefore(taskList.next_before);
        setError(null);
        setLastUpdated(Date.now());
        setPhase('ready');
        return true;
      } catch (caught) {
        if (!mounted.current || generation.current !== current) return false;
        const failure = friendlyError(caught);
        if (failure.code === 'ABORTED') return false;
        if (failure.code === 'OWNER_TOKEN_REQUIRED' || failure.status === 401) {
          clearSession();
          setError(new ApiError('OWNER_TOKEN_REQUIRED', '本机会话已失效，请重新输入 Owner 令牌。', 401));
          return false;
        }
        setError(failure);
        setPhase((currentPhase) => (currentPhase === 'ready' ? 'ready' : 'error'));
        return false;
      } finally {
        inFlight.current = false;
        if (mounted.current && generation.current === current) setRefreshing(false);
      }
    },
    [clearSession],
  );

  const refresh = useCallback(
    async (options: { silent?: boolean; before?: string | null } = {}) => {
      if (!token) return;
      const before = options.before !== undefined ? options.before : pageBeforeRef.current;
      if (options.before !== undefined) {
        pageBeforeRef.current = options.before;
        setPageBefore(options.before);
      }
      await loadAll(token, before, { silent: options.silent ?? false });
    },
    [loadAll, token],
  );

  const unlock = useCallback(
    async (nextToken: string): Promise<ApiError | null> => {
      const clean = nextToken.trim();
      if (!clean) return new ApiError('OWNER_TOKEN_REQUIRED', '请输入 Owner 令牌。', 401);
      generation.current += 1;
      const current = generation.current;
      setToken(clean);
      setError(null);
      setBusy('unlock');
      try {
        const [nextStatus, taskList] = await Promise.all([
          loadAgentStatus(clean),
          loadAgentTasks(clean, null),
        ]);
        if (!mounted.current || generation.current !== current) return null;
        setStatus(nextStatus);
        setTasks(taskList.tasks);
        setNextBefore(taskList.next_before);
        setPageBefore(null);
        pageBeforeRef.current = null;
        setPhase('ready');
        setLastUpdated(Date.now());
        return null;
      } catch (caught) {
        if (!mounted.current || generation.current !== current) return null;
        const failure = friendlyError(caught);
        if (failure.code === 'OWNER_TOKEN_REQUIRED' || failure.status === 401) {
          clearSession();
          return new ApiError('OWNER_TOKEN_REQUIRED', 'Owner 令牌无效，或本机 Agent 尚未启动。', 401);
        }
        setToken(null);
        setError(failure);
        setPhase('locked');
        return failure;
      } finally {
        if (mounted.current) setBusy(null);
      }
    },
    [clearSession],
  );

  const goPage = useCallback(
    async (before: string | null) => {
      if (!token) return;
      pageBeforeRef.current = before;
      setPageBefore(before);
      setBusy('page');
      await loadAll(token, before, { silent: false });
      if (mounted.current) setBusy(null);
    },
    [loadAll, token],
  );

  const createTask = useCallback(
    async (input: CreateTaskInput): Promise<{ error: ApiError | null; id?: string }> => {
      if (!token) return { error: new ApiError('OWNER_TOKEN_REQUIRED', '请先解锁 Agent。', 401) };
      setBusy('create');
      try {
        const created = await createAgentTask(token, input);
        pageBeforeRef.current = null;
        setPageBefore(null);
        await loadAll(token, null, { silent: true });
        return { error: null, id: created.id };
      } catch (caught) {
        const failure = friendlyError(caught);
        if (failure.status === 401) {
          clearSession();
        }
        return { error: failure };
      } finally {
        if (mounted.current) setBusy(null);
      }
    },
    [clearSession, loadAll, token],
  );

  const runTaskAction = useCallback(
    async (id: string, action: 'cancel' | 'retry'): Promise<ApiError | null> => {
      if (!token) return new ApiError('OWNER_TOKEN_REQUIRED', '请先解锁 Agent。', 401);
      setBusy(action + ':' + id);
      try {
        if (action === 'cancel') await cancelAgentTask(token, id);
        else await retryAgentTask(token, id);
        await loadAll(token, pageBeforeRef.current, { silent: true });
        if (detailOpen && detail?.id === id) {
          try {
            const nextDetail = await loadAgentTask(token, id);
            if (mounted.current) setDetail(nextDetail);
          } catch {
            // The list refresh already reflects the durable state; keep the drawer as-is.
          }
        }
        return null;
      } catch (caught) {
        const failure = friendlyError(caught);
        if (failure.status === 401) {
          clearSession();
          setError(new ApiError('OWNER_TOKEN_REQUIRED', '本机会话已失效，请重新输入 Owner 令牌。', 401));
        }
        return failure;
      } finally {
        if (mounted.current) setBusy(null);
      }
    },
    [clearSession, detail, detailOpen, loadAll, token],
  );

  const cancelTask = useCallback((id: string) => runTaskAction(id, 'cancel'), [runTaskAction]);
  const retryTask = useCallback((id: string) => runTaskAction(id, 'retry'), [runTaskAction]);

  const control = useCallback(
    async (
      body:
        | { action: 'pause' }
        | { action: 'resume' }
        | { action: 'eod'; enabled: boolean }
        | { action: 'model'; model_id: string }
        | { action: 'backup'; model_id: string },
    ): Promise<ApiError | null> => {
      if (!token) return new ApiError('OWNER_TOKEN_REQUIRED', '请先解锁 Agent。', 401);
      setBusy('control:' + body.action);
      try {
        await controlAgent(token, body);
        await loadAll(token, pageBeforeRef.current, { silent: true });
        return null;
      } catch (caught) {
        const failure = friendlyError(caught);
        if (failure.status === 401) {
          clearSession();
          setError(new ApiError('OWNER_TOKEN_REQUIRED', '本机会话已失效，请重新输入 Owner 令牌。', 401));
        }
        return failure;
      } finally {
        if (mounted.current) setBusy(null);
      }
    },
    [clearSession, loadAll, token],
  );

  const openTask = useCallback(
    async (id: string) => {
      if (!token) return;
      setDetailOpen(true);
      setDetailLoading(true);
      setDetailError(null);
      setDetail((current) => (current && current.id === id ? current : null));
      detailController.current?.abort();
      const controller = new AbortController();
      detailController.current = controller;
      try {
        const nextDetail = await loadAgentTask(token, id, controller.signal);
        if (!mounted.current) return;
        setDetail(nextDetail);
      } catch (caught) {
        if (!mounted.current) return;
        const failure = friendlyError(caught);
        if (failure.code === 'ABORTED') return;
        if (failure.status === 401) {
          clearSession();
          setError(new ApiError('OWNER_TOKEN_REQUIRED', '本机会话已失效，请重新输入 Owner 令牌。', 401));
        }
        setDetailError(failure);
      } finally {
        if (mounted.current) setDetailLoading(false);
      }
    },
    [clearSession, token],
  );

  const closeTask = useCallback(() => {
    setDetailOpen(false);
    setDetailError(null);
  }, []);

  const refreshDetail = useCallback(async () => {
    if (!token || !detail) return;
    setDetailLoading(true);
    try {
      const nextDetail = await loadAgentTask(token, detail.id);
      if (mounted.current) {
        setDetail(nextDetail);
        setDetailError(null);
      }
    } catch (caught) {
      if (mounted.current) setDetailError(friendlyError(caught));
    } finally {
      if (mounted.current) setDetailLoading(false);
    }
  }, [detail, token]);

  const wasActive = useRef(false);
  useEffect(() => {
    if (active && !wasActive.current && token && phase === 'ready') {
      void refresh({ silent: true });
    }
    wasActive.current = active;
  }, [active, phase, refresh, token]);

  useInterval(
    () => {
      if (active && token && phase === 'ready' && visible) {
        void refresh({ silent: true });
      }
    },
    active && token && phase === 'ready' && visible ? 6000 : null,
  );

  return {
    token,
    phase,
    status,
    tasks,
    nextBefore,
    pageBefore,
    error,
    busy,
    refreshing,
    lastUpdated,
    detail,
    detailOpen,
    detailLoading,
    detailError,
    unlock,
    lock,
    refresh,
    goPage,
    createTask,
    cancelTask,
    retryTask,
    control,
    openTask,
    closeTask,
    refreshDetail,
  };
}