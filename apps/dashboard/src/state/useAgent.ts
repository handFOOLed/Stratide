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
import type { AgentBudget, AgentStatus, AgentTask, AgentTaskDetail } from '../lib/types';

export type AgentPhase = 'loading' | 'ready' | 'error';

export interface CreateTaskInput {
  request_key: string;
  name: string;
  goal: string;
  scope: string;
  start_day: string;
  end_day: string;
  task_budget_micro: string | null;
}

type ControlInput =
  | { action: 'pause' }
  | { action: 'resume' }
  | { action: 'eod'; enabled: boolean }
  | { action: 'model'; model_id: string }
  | { action: 'backup'; model_id: string };

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
  refresh: (options?: { silent?: boolean }) => Promise<void>;
  applyBudget: (budget: AgentBudget) => void;
  goPage: (before: string | null) => Promise<void>;
  createTask: (input: CreateTaskInput) => Promise<{ error: ApiError | null; id?: string }>;
  cancelTask: (id: string) => Promise<ApiError | null>;
  retryTask: (id: string) => Promise<ApiError | null>;
  control: (body: ControlInput) => Promise<ApiError | null>;
  openTask: (id: string) => Promise<void>;
  closeTask: () => void;
  refreshDetail: () => Promise<void>;
}

const LOCAL_SESSION = 'local';

export function useAgent(active: boolean): AgentState {
  const [phase, setPhase] = useState<AgentPhase>('loading');
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
  const pageBeforeRef = useRef<string | null>(null);
  const mainController = useRef<AbortController | null>(null);
  const detailController = useRef<AbortController | null>(null);
  const detailId = useRef<string | null>(null);
  const visible = useDocumentVisible();

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      mainController.current?.abort();
      detailController.current?.abort();
      mainController.current = null;
    };
  }, []);

  const loadAll = useCallback(async (before: string | null, silent = false, force = false) => {
    if (!mounted.current || (!force && mainController.current !== null)) return;
    mainController.current?.abort();
    const controller = new AbortController();
    mainController.current = controller;
    if (!silent) setRefreshing(true);
    try {
      const [nextStatus, taskList] = await Promise.all([
        loadAgentStatus(LOCAL_SESSION, controller.signal),
        loadAgentTasks(LOCAL_SESSION, before, controller.signal),
      ]);
      if (controller.signal.aborted) return;
      setStatus(nextStatus);
      setTasks(taskList.tasks);
      setNextBefore(taskList.next_before);
      setError(null);
      setLastUpdated(Date.now());
      setPhase('ready');
    } catch (caught) {
      if (controller.signal.aborted) return;
      controller.abort();
      const failure = friendlyError(caught);
      setError(failure);
      setPhase((current) => current === 'ready' && failure.status !== 401 ? 'ready' : 'error');
    } finally {
      if (mainController.current === controller) {
        mainController.current = null;
        setRefreshing(false);
      }
    }
  }, []);

  const refresh = useCallback(async ({ silent = false } = {}) => {
    await loadAll(pageBeforeRef.current, silent, !silent);
  }, [loadAll]);

  const applyBudget = useCallback((budget: AgentBudget) => {
    setStatus((current) => current === null ? null : { ...current, budget });
    void loadAll(pageBeforeRef.current, true, true);
  }, [loadAll]);

  const goPage = useCallback(async (before: string | null) => {
    pageBeforeRef.current = before;
    setPageBefore(before);
    setBusy('page');
    await loadAll(before, false, true);
    if (mounted.current) setBusy(null);
  }, [loadAll]);

  const createTask = useCallback(async (input: CreateTaskInput): Promise<{ error: ApiError | null; id?: string }> => {
    setBusy('create');
    try {
      const { request_key, ...request } = input;
      const created = await createAgentTask(LOCAL_SESSION, request, request_key);
      pageBeforeRef.current = null;
      setPageBefore(null);
      await loadAll(null, true, true);
      return { error: null, id: created.id };
    } catch (caught) {
      return { error: friendlyError(caught) };
    } finally {
      if (mounted.current) setBusy(null);
    }
  }, [loadAll]);

  const openTask = useCallback(async (id: string) => {
    detailId.current = id;
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailError(null);
    setDetail((current) => current?.id === id ? current : null);
    detailController.current?.abort();
    const controller = new AbortController();
    detailController.current = controller;
    try {
      const nextDetail = await loadAgentTask(LOCAL_SESSION, id, controller.signal);
      if (!controller.signal.aborted) setDetail(nextDetail);
    } catch (caught) {
      if (!controller.signal.aborted) setDetailError(friendlyError(caught));
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
    }
  }, []);

  const closeTask = useCallback(() => {
    detailController.current?.abort();
    detailId.current = null;
    setDetailOpen(false);
    setDetailLoading(false);
    setDetailError(null);
  }, []);

  const refreshDetail = useCallback(async () => {
    if (detailId.current !== null) await openTask(detailId.current);
  }, [openTask]);

  const runTaskAction = useCallback(async (id: string, action: 'cancel' | 'retry'): Promise<ApiError | null> => {
    setBusy(action + ':' + id);
    try {
      if (action === 'cancel') await cancelAgentTask(LOCAL_SESSION, id);
      else await retryAgentTask(LOCAL_SESSION, id);
      await loadAll(pageBeforeRef.current, true, true);
      if (detailId.current === id && mounted.current) await openTask(id);
      return null;
    } catch (caught) {
      return friendlyError(caught);
    } finally {
      if (mounted.current) setBusy(null);
    }
  }, [loadAll, openTask]);

  const cancelTask = useCallback((id: string) => runTaskAction(id, 'cancel'), [runTaskAction]);
  const retryTask = useCallback((id: string) => runTaskAction(id, 'retry'), [runTaskAction]);

  const control = useCallback(async (body: ControlInput): Promise<ApiError | null> => {
    setBusy('control:' + body.action);
    try {
      await controlAgent(LOCAL_SESSION, body);
      await loadAll(pageBeforeRef.current, true, true);
      return null;
    } catch (caught) {
      return friendlyError(caught);
    } finally {
      if (mounted.current) setBusy(null);
    }
  }, [loadAll]);

  useEffect(() => {
    if (active) void refresh();
  }, [active, refresh]);

  useInterval(() => void refresh({ silent: true }), active && phase === 'ready' && visible ? 6000 : null);

  return {
    token: phase === 'ready' ? LOCAL_SESSION : null,
    phase, status, tasks, nextBefore, pageBefore, error, busy, refreshing, lastUpdated,
    detail, detailOpen, detailLoading, detailError, refresh, applyBudget, goPage,
    createTask, cancelTask, retryTask, control, openTask, closeTask, refreshDetail,
  };
}
