import { useMemo, useRef, useState } from 'react';
import type { FormEvent, Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Button, IconButton } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { Diagnostics } from '../components/ui/Diagnostics';
import { EmptyState } from '../components/ui/EmptyState';
import { InfoHint } from '../components/ui/InfoHint';
import { Field, Select, TextArea, TextInput } from '../components/ui/Field';
import { Kv } from '../components/ui/Kv';
import { Modal, Drawer } from '../components/ui/Overlay';
import { ProgressBar } from '../components/ui/ProgressBar';
import { SkeletonLines, Skeleton } from '../components/ui/Skeleton';
import { StatusBadge, StatusLine } from '../components/ui/StatusBadge';
import { Switch } from '../components/ui/Switch';
import { Table } from '../components/ui/Table';
import { useToast } from '../components/ui/Toast';
import { TaskStatusBadge } from '../components/domain/Badges';
import { BudgetEditor } from '../components/domain/BudgetEditor';
import { WorkspaceStudies } from '../components/domain/WorkspaceStudies';
import { Icon } from '../icons';
import { COMMON, EMPTY, TERMS, UNITS } from '../lib/copy';
import {
  countText,
  dateInputToDay,
  formatClock,
  formatDateFromTimestamp,
  formatDateTime,
  formatDuration,
  formatMicroMoney,
  parseInteger,
  todayShanghai,
} from '../lib/format';
import { navigate } from '../lib/route';
import {
  availabilityView,
  eodStatusView,
  failureReasonText,
  humanReasonText,
  researchStatusView,
  statusView,
  taskStatusView,
} from '../lib/status';
import type { StatusView } from '../lib/status';
import type { AgentCall, AgentModel, AgentStatus, AgentTask, AgentTaskDetail } from '../lib/types';
import type { AgentState } from '../state/useAgent';
import type { WorkspaceState } from '../lib/workspace';

function isBusy(agent: AgentState, prefix: string): boolean {
  return agent.busy !== null && agent.busy.startsWith(prefix);
}

function moneyText(value: string | null, currency: string): string {
  return value === null ? COMMON.notAvailable : formatMicroMoney(value, currency);
}

function percent(part: string | null, total: string | null): number {
  const p = parseInteger(part);
  const t = parseInteger(total);
  if (p === null || t === null || t <= 0n) return 0;
  const scaled = (p * 10_000n) / t;
  return Math.min(100, Math.max(0, Number(scaled) / 100));
}

function usedMicro(limit: string | null, remaining: string | null): string | null {
  const l = parseInteger(limit);
  const r = parseInteger(remaining);
  if (l === null || r === null) return null;
  return (l - r).toString();
}

function taskCost(calls: AgentCall[]): string | null {
  if (calls.length === 0) return null;
  let total = 0n;
  for (const call of calls) {
    const raw = call.state === 'settled' ? call.settled_micro : call.state === 'no_charge' ? '0' : call.maximum_micro;
    const value = parseInteger(raw);
    if (value !== null) total += value;
  }
  return total.toString();
}

/** 后端已给出中文原因时直接使用；否则回退集中映射，再回退“原因未记录”。 */
function reasonTextOf(code: string | null, text: string | null | undefined): string {
  return text ?? failureReasonText(code);
}

/** 已持久化原因码的一句话：有中文用中文，没有就明确“原因未记录”，不直出原始码。 */
function reasonTextOrNull(code: string | null, text: string | null | undefined): string | null {
  if (text !== null && text !== undefined && text !== '') return text;
  return humanReasonText(code);
}

function callReasonText(call: AgentCall): string {
  if (call.reason === null && call.reason_text === null) return COMMON.notAvailable;
  return call.reason_text ?? failureReasonText(call.reason);
}

function modelDisplayName(model: AgentModel): string {
  if (model.kind === 'fake') return '本地测试模型';
  return model.label;
}

function modelStatusView(model: AgentModel): StatusView {
  if (model.authorization !== 'authorized') {
    return statusView('attention', '需要处理', model.authorization_text ?? humanReasonText(model.authorization) ?? '研究模型授权配置不完整');
  }
  return availabilityView(model.availability);
}

/** 全市场研究未运行通知：不是付费研究任务，也不是失败任务。 */
const RESEARCH_STATUS_PROVIDER = 'market-research-status';

function isResearchStatusRecord(kind: string | undefined, providerId: string): boolean {
  return kind === 'research_blocked_notice' || providerId === RESEARCH_STATUS_PROVIDER;
}

function researchStatusRecordView(reason: string | null, text: string | null | undefined): StatusView {
  return statusView('attention', '需要处理', text ?? humanReasonText(reason) ?? '原因未记录');
}

function researchStatusRecordName(name: string): string {
  const match = /^全市场研究阻断\s*(\d{8})$/.exec(name.trim());
  if (match !== null && match[1] !== undefined) {
    const day = match[1];
    return '全市场研究未运行 · ' + day.slice(0, 4) + '-' + day.slice(4, 6) + '-' + day.slice(6, 8);
  }
  return name.trim();
}

function researchTaskDisplayName(task: AgentTask): string {
  if (isResearchStatusRecord(task.kind, task.provider_id)) return researchStatusRecordName(task.name);
  return displayTaskName(task.created_at, task.name);
}

function taskDetailDisplayName(detail: AgentTaskDetail): string {
  if (isResearchStatusRecord(detail.kind, detail.provider_id)) return researchStatusRecordName(detail.request.name);
  return displayTaskName(detail.created_at, detail.request.name);
}

function autoTaskName(name: string): string {
  const daily = /^EOD 日常研究\s*·\s*(\d{8})$/.exec(name.trim());
  if (daily !== null && daily[1] !== undefined) {
    const day = daily[1];
    return '收盘后自动研究 · ' + day.slice(0, 4) + '-' + day.slice(4, 6) + '-' + day.slice(6, 8);
  }
  return name.trim().replace(/EOD\s*日常研究/g, '收盘后自动研究').replace(/EOD/g, '收盘后');
}

function displayTaskName(createdAt: string | null, name: string): string {
  const trimmed = autoTaskName(name);
  const date = createdAt === null ? '' : formatDateFromTimestamp(createdAt);
  if (date === '' || date === COMMON.notAvailable) return trimmed === '' ? '研究任务' : trimmed;
  return trimmed === '' ? date + ' 研究任务' : date + ' · ' + trimmed;
}

const KNOWN_SCOPES: Record<string, string> = {
  '当前已发布的 Paper 摘要': '当前已发布的模拟账户摘要',
  '当前已发布 Paper 摘要': '当前已发布的模拟账户摘要',
};

function displayScope(scope: string): string {
  return KNOWN_SCOPES[scope] ?? scope;
}

function taskOutcomeText(task: AgentTask): string {
  switch (task.status) {
    case 'completed':
      return task.conclusion ?? reasonTextOrNull(task.reason, task.reason_text) ?? '已完成，结论未保存';
    case 'failed': {
      const reason = reasonTextOf(task.reason, task.reason_text);
      return reason === '原因未记录' ? '失败，原因未记录' : reason;
    }
    case 'blocked': {
      const reason = reasonTextOf(task.reason, task.reason_text);
      return reason === '原因未记录' ? '已被阻止，原因未记录' : reason;
    }
    case 'outcome_uncertain': {
      const specific = reasonTextOrNull(task.reason, task.reason_text);
      return specific === null || specific === ''
        ? '结果或费用尚未确认，请核对调用记录'
        : specific + '。结果或费用尚未确认，请核对调用记录';
    }
    case 'queued':
      return '等待开始';
    case 'running':
    case 'local_running':
      return '研究进行中';
    case 'cancel_requested':
      return '已发出取消请求，等待当前步骤结束';
    case 'cancelled':
      return '任务已取消';
    case 'skipped':
      return reasonTextOrNull(task.reason, task.reason_text) ?? '任务已跳过';
    default:
      return '状态未知';
  }
}

function eodRecordedReason(status: AgentStatus): string | null {
  const latest = status.eod.latest;
  if (latest !== null && latest.reason_text !== undefined && latest.reason_text !== null) return latest.reason_text;
  const raw = latest === null ? status.eod.reason : latest.reason ?? status.eod.reason;
  return humanReasonText(raw);
}

function runtimeSentence(status: AgentStatus, view: StatusView, runningTasks: number, queuedTasks: number): string {
  if (status.worker_error !== null) return '研究服务出错：' + reasonTextOf(status.worker_error, status.worker_error_text);
  if (status.paused) return '研究已暂停，暂停期间不会开始新的研究。';
  if (runningTasks > 0) return countText(runningTasks, UNITS.task) + '任务正在研究。';
  if (queuedTasks > 0) return countText(queuedTasks, UNITS.task) + '任务排队中，开始后会自动调用 AI 服务。';
  return view.reason ?? view.label;
}

function detailSentence(detail: AgentTaskDetail): string {
  const conclusion = detail.result?.research.hypothesis ?? null;
  switch (detail.status) {
    case 'completed':
      return conclusion ?? reasonTextOrNull(detail.reason, detail.reason_text) ?? '研究已完成，结论未保存。';
    case 'failed': {
      const reason = reasonTextOf(detail.reason, detail.reason_text);
      return reason === '原因未记录' ? '失败，原因未记录。' : '失败原因：' + reason + '。';
    }
    case 'blocked': {
      const reason = reasonTextOf(detail.reason, detail.reason_text);
      return reason === '原因未记录' ? '已被阻止，原因未记录。' : '已被阻止：' + reason + '。';
    }
    case 'outcome_uncertain':
      return '结果或费用尚未确认，请核对调用记录。';
    case 'queued':
      return '等待开始。';
    case 'running':
    case 'local_running':
      return '研究进行中。';
    case 'cancel_requested':
      return '已发出取消请求，等待当前步骤结束。';
    case 'cancelled':
      return '任务已取消。';
    case 'skipped':
      return '已跳过：' + (reasonTextOrNull(detail.reason, detail.reason_text) ?? '原因未记录') + '。';
    default:
      return '状态未知。';
  }
}

function defaultRange(sourceDay: string): { start: string; end: string } {
  const source = /^\d{4}-\d{2}-\d{2}$/.test(sourceDay) ? sourceDay : todayShanghai();
  return { start: source, end: source };
}

interface CancelTarget {
  id: string;
  title: string;
}

export function AgentPage({ agent, workspace, titleRef }: { agent: AgentState; workspace: WorkspaceState; titleRef?: Ref<HTMLHeadingElement> }) {
  const toast = useToast();
  const [createOpen, setCreateOpen] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<CancelTarget | null>(null);

  const status = agent.status;
  const header = (
    <PageHeader
      title={TERMS.aiResearch}
      titleRef={titleRef}
      side={
        <span className="page-meta">
          {TERMS.updatedAt} {agent.lastUpdated === null ? COMMON.notAvailable : formatClock(agent.lastUpdated)}
        </span>
      }
    />
  );

  if (agent.phase === 'locked' || agent.phase === 'loading') {
    return (
      <>
        {header}
        <div role="status" className="sr-only">正在读取 AI 研究状态</div>
        <div className="grid">
          <div className="col-12"><Skeleton className="skeleton-card" /></div>
          <div className="col-12"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
          <div className="col-5"><Skeleton className="skeleton-card" /></div>
          <div className="col-7"><Skeleton className="skeleton-card" /></div>
          <div className="col-12"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
        </div>
      </>
    );
  }

  if (agent.phase === 'error' || status === null) {
    return (
      <>
        {header}
        <Card>
          <CardBody>
            <EmptyState
              tone="error"
              icon="alert-octagon"
              title="AI 研究服务不可用"
              description={agent.error?.message ?? '研究服务没有返回状态。'}
              actions={<Button variant="secondary" icon="refresh" onClick={() => void agent.refresh()}>重新读取</Button>}
            />
            <Diagnostics items={[{ label: '原始错误码', value: agent.error?.code ?? COMMON.notAvailable }]} />
          </CardBody>
        </Card>
      </>
    );
  }

  const budget = status.budget;
  const budgetConfigured = budget.state === 'configured';
  const defaultModel = status.models.find((model) => model.id === status.default_model) ?? null;
  const manualResearchAvailable = status.manual_research_available !== false;
  const attachedMode = status.dashboard_mode === 'attached_explicit_operations';
  const createDisabledReason = !manualResearchAvailable
    ? '安装版由后台自动研究执行任务，手动新建研究暂不可用。'
    : attachedMode
      ? '当前以只读方式启动，不能新建研究任务。'
      : defaultModel === null
        ? '尚未选择默认研究模型。'
        : !budgetConfigured
          ? '尚未设置研究预算。'
          : '';
  const canCreate = createDisabledReason === '';
  const runningTasks = agent.tasks.filter((task) => task.status === 'running' || task.status === 'local_running').length;
  const queuedTasks = agent.tasks.filter((task) => task.status === 'queued').length;
  const latestFinishedTask = agent.tasks.find((task) => ['completed', 'failed', 'blocked', 'outcome_uncertain', 'cancelled'].includes(task.status)) ?? null;
  const researchView = researchStatusView({
    ready: true,
    paused: status.paused,
    status,
    errorCode: null,
    runningTasks,
    latestTaskStatus: latestFinishedTask === null ? null : latestFinishedTask.status,
    latestTaskReason: latestFinishedTask === null ? null : latestFinishedTask.reason,
  });

  const requestCancel = (id: string, title: string) => setCancelTarget({ id, title });
  const confirmCancel = async () => {
    if (cancelTarget === null) return;
    const error = await agent.cancelTask(cancelTarget.id);
    if (error) toast.push({ title: '取消失败', description: error.message, tone: 'danger' });
    else toast.push({ title: '已申请取消', description: '已经发出的计费请求不会撤销，可能仍会产生费用。', tone: 'info' });
    setCancelTarget(null);
  };

  return (
    <>
      {header}
      {agent.error === null ? null : (
        <Callout tone="warning" title="最近一次读取失败，显示上次成功读取的状态" className="stale-banner">
          <div className="stale-banner__row">
            <span>{agent.error.message}</span>
            <Button size="sm" variant="ghost" icon="refresh" onClick={() => void agent.refresh()}>重新读取</Button>
          </div>
        </Callout>
      )}

      <div className="grid agent-grid">
        <div className="col-12">
          <RuntimeCard
            agent={agent}
            status={status}
            view={researchView}
            runningTasks={runningTasks}
            queuedTasks={queuedTasks}
            canCreate={canCreate}
            manualResearchAvailable={manualResearchAvailable}
            createDisabledReason={createDisabledReason}
            onCreate={() => setCreateOpen(true)}
          />
        </div>
        <div className="col-12">
          <TasksCard agent={agent} onRequestCancel={requestCancel} />
        </div>
        <div className="col-5">
          <BudgetCard status={status} agent={agent} />
        </div>
        <div className="col-7">
          <ModelsCard status={status} agent={agent} />
        </div>
        <div className="col-12">
          <WorkspaceStudies workspace={workspace} />
        </div>
      </div>

      <TaskDrawer agent={agent} status={status} onRequestCancel={requestCancel} />

      <Modal
        open={cancelTarget !== null}
        onClose={() => setCancelTarget(null)}
        title="取消研究任务？"
        description={cancelTarget === null ? undefined : cancelTarget.title}
        footer={
          <>
            <Button variant="ghost" type="button" onClick={() => setCancelTarget(null)}>不取消</Button>
            <Button
              variant="danger"
              type="button"
              loading={cancelTarget !== null && agent.busy === 'cancel:' + cancelTarget.id}
              disabled={agent.busy !== null}
              onClick={() => void confirmCancel()}
              data-testid="task-cancel-confirm"
            >
              确认取消
            </Button>
          </>
        }
      >
        <p className="muted">取消后任务会尽快停止，但不会撤销已经发出的计费请求，可能仍会产生费用。</p>
      </Modal>

      <Modal
        open={createOpen}
        onClose={() => {
          if (agent.busy !== 'create') setCreateOpen(false);
        }}
        title="新建研究"
        description="研究任务会进入队列，并受每日与每月研究预算上限约束。"
        wide
        footer={<CreateFooter agent={agent} canCreate={canCreate} onCancel={() => setCreateOpen(false)} />}
      >
        <CreateTaskForm
          agent={agent}
          canCreate={canCreate}
          disabledReason={createDisabledReason}
          sourceDay={status.input.source_day}
          currency={budget.currency}
          onDone={() => {
            setCreateOpen(false);
            toast.push({ title: '研究任务已排队', description: '进度与结论会显示在下面的任务列表中。', tone: 'success' });
          }}
        />
      </Modal>
    </>
  );
}

function RuntimeCard({
  agent,
  status,
  view,
  runningTasks,
  queuedTasks,
  canCreate,
  manualResearchAvailable,
  createDisabledReason,
  onCreate,
}: {
  agent: AgentState;
  status: AgentStatus;
  view: StatusView;
  runningTasks: number;
  queuedTasks: number;
  canCreate: boolean;
  manualResearchAvailable: boolean;
  createDisabledReason: string;
  onCreate: () => void;
}) {
  const toast = useToast();
  const defaultModel = status.models.find((model) => model.id === status.default_model) ?? null;
  const latest = status.eod.latest;
  const latestView = latest === null ? null : eodStatusView(latest.disposition ?? null, eodRecordedReason(status));

  const pauseOrResume = async (action: 'pause' | 'resume') => {
    const error = await agent.control({ action });
    if (error) toast.push({ title: action === 'pause' ? '暂停失败' : '恢复失败', description: error.message, tone: 'danger' });
    else toast.push({ title: action === 'pause' ? '已暂停 AI 研究' : '已恢复 AI 研究', tone: 'success' });
  };

  return (
    <Card className="agent-runtime" data-testid="agent-status-card">
      <CardHead title="运行状态" actions={<StatusBadge status={view} />} />
      <CardBody>
        <div className="runtime-head">
          <div className="runtime-summary">
            <p className="runtime-lead">{runtimeSentence(status, view, runningTasks, queuedTasks)}</p>
            {view.reason === undefined || view.reason === runtimeSentence(status, view, runningTasks, queuedTasks) ? null : (
              <p className="runtime-lead runtime-lead--note">{view.reason}</p>
            )}
          </div>
          <div className="runtime-actions">
            <Button
              variant="primary"
              icon="plus"
              onClick={onCreate}
              disabled={!canCreate}
              title={canCreate ? undefined : createDisabledReason}
              data-testid="agent-create"
            >
              新建研究
            </Button>
            {status.paused ? (
              <Button variant="secondary" icon="play" loading={isBusy(agent, 'control:resume')} disabled={agent.busy !== null} onClick={() => void pauseOrResume('resume')} data-testid="agent-resume">
                恢复研究
              </Button>
            ) : runningTasks > 0 ? (
              <Button variant="secondary" icon="pause" loading={isBusy(agent, 'control:pause')} disabled={agent.busy !== null} onClick={() => void pauseOrResume('pause')} data-testid="agent-pause">
                暂停研究
              </Button>
            ) : null}
          </div>
        </div>

        {manualResearchAvailable ? null : (
          <p className="runtime-lead runtime-lead--note" data-testid="agent-manual-unavailable">
            安装版由后台自动研究执行任务，手动新建研究暂不可用。
          </p>
        )}

        {canCreate || !manualResearchAvailable ? null : (
          <Callout tone="warning" title="当前不能新建研究" className="runtime-warning">
            {createDisabledReason}
          </Callout>
        )}

        {status.worker_error === null ? null : (
          <Callout tone="danger" title="研究服务出错" className="runtime-warning" role="alert">
            {reasonTextOf(status.worker_error, status.worker_error_text)}
            <Diagnostics items={[{ label: '原始错误', value: status.worker_error }]} />
          </Callout>
        )}

        <div className="runtime-meta">
          <div>
            <span>当前研究模型</span>
            <strong>{defaultModel === null ? '未设置' : modelDisplayName(defaultModel)}</strong>
          </div>
          <div>
            <span>进行中</span>
            <strong>{countText(runningTasks, UNITS.task)}</strong>
          </div>
          <div>
            <span>排队中</span>
            <strong>{countText(queuedTasks, UNITS.task)}</strong>
          </div>
        </div>

        <div className="eod-block">
          <div className="eod-head">
            <div>
              <h3 className="eod-title">{TERMS.closeAutoResearch}</h3>
              <p className="eod-desc">每个交易日收盘后，自动用最新行情生成一份研究任务。</p>
            </div>
            <div className="eod-switch">
              <span className="eod-switch-label">{status.eod.enabled ? '已启用' : '已停用'}</span>
              <Switch
                checked={status.eod.enabled}
                busy={isBusy(agent, 'control:eod')}
                disabled={status.dashboard_mode === 'attached_explicit_operations'}
                label={TERMS.closeAutoResearch + '开关'}
                onChange={async (enabled) => {
                  const error = await agent.control({ action: 'eod', enabled });
                  if (error) toast.push({ title: '自动研究设置失败', description: error.message, tone: 'danger' });
                  else toast.push({ title: enabled ? '已启用收盘后自动研究' : '已关闭收盘后自动研究', tone: 'success' });
                }}
              />
            </div>
          </div>
          {status.dashboard_mode === 'attached_explicit_operations' ? (
            <p className="eod-desc">当前以只读方式启动，不能修改收盘后自动研究设置。</p>
          ) : null}
          <div className="eod-latest">
            <span className="eod-latest__label">最近一次</span>
            {latest === null || latestView === null ? (
              <span className="muted">还没有自动研究记录</span>
            ) : (
              <div className="eod-latest__body">
                <StatusBadge status={latestView} size="sm" />
                <span>数据日期 {latest.source_day ?? COMMON.notAvailable}</span>
                {latestView.reason === undefined ? null : <span className="muted">{latestView.reason}</span>}
              </div>
            )}
          </div>
          <Diagnostics
            items={[
              { label: '开关原始值', value: status.eod.enabled ? 'true' : 'false' },
              { label: '最近结果原始值', value: latest === null ? COMMON.notAvailable : latest.disposition ?? COMMON.notAvailable },
              { label: '最近调度原因', value: status.eod.reason ?? COMMON.notAvailable },
              { label: '跳过记录', value: countText(status.eod.skipped, '次') },
            ]}
          />
        </div>
      </CardBody>
    </Card>
  );
}

function TasksCard({ agent, onRequestCancel }: { agent: AgentState; onRequestCancel: (id: string, title: string) => void }) {
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return agent.tasks.filter((task) => {
      if (filter === 'active' && !['queued', 'running', 'local_running', 'cancel_requested'].includes(task.status)) return false;
      if (filter === 'completed' && task.status !== 'completed') return false;
      if (filter === 'failed' && (!['failed', 'blocked', 'outcome_uncertain'].includes(task.status) || isResearchStatusRecord(task.kind, task.provider_id))) return false;
      if (filter === 'cancelled' && task.status !== 'cancelled') return false;
      if (filter === 'not_run' && !isResearchStatusRecord(task.kind, task.provider_id)) return false;
      if (term === '') return true;
      return [
        researchTaskDisplayName(task),
        task.conclusion ?? '',
        task.reason_text ?? humanReasonText(task.reason) ?? '',
        taskOutcomeText(task),
      ]
        .join(' ')
        .toLowerCase()
        .includes(term);
    });
  }, [agent.tasks, filter, query]);

  const busy = agent.busy !== null;

  return (
    <Card className="agent-tasks" data-testid="agent-tasks">
      <CardHead
        title="研究任务"
        actions={
          <IconButton
            label="刷新研究任务"
            icon="refresh"
            onClick={() => void agent.refresh()}
            disabled={agent.refreshing || busy}
          />
        }
      />
      <div className="toolbar">
        <div className="toolbar__search">
          <Icon name="search" />
          <TextInput
            aria-label="搜索研究任务"
            placeholder="搜索任务名称、结论或原因"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            data-testid="task-search"
          />
        </div>
        <Select aria-label="任务状态筛选" value={filter} onChange={(event) => setFilter(event.target.value)} data-testid="task-filter">
          <option value="all">全部状态</option>
          <option value="active">进行中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败或阻止</option>
          <option value="not_run">研究未运行</option>
          <option value="cancelled">已取消</option>
        </Select>
        <span className="toolbar__meta">{countText(filtered.length, UNITS.task)}</span>
        {agent.refreshing ? <span className="toolbar__meta">读取中…</span> : null}
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          compact
          icon="file"
          title={agent.tasks.length === 0 ? EMPTY.tasksTitle : '没有匹配的任务'}
          description={agent.tasks.length === 0 ? EMPTY.tasksBody : '调整搜索词或状态筛选。'}
        />
      ) : (
        <>
          <Table label="研究任务" className="tasks-table">
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>时间</th>
                <th>结论 / 原因</th>
                <th className="row-actions-head">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((task) => {
                const display = researchTaskDisplayName(task);
                const notRunRecord = isResearchStatusRecord(task.kind, task.provider_id);
                const outcome = notRunRecord ? researchStatusRecordView(task.reason, task.reason_text).reason ?? '原因未记录' : taskOutcomeText(task);
                const canCancel = ['queued', 'running', 'local_running'].includes(task.status);
                return (
                  <tr key={task.id} data-testid="task-row" onClick={() => void agent.openTask(task.id)}>
                    <td>
                      <button
                        type="button"
                        className="row-link"
                        onClick={(event) => {
                          event.stopPropagation();
                          void agent.openTask(task.id);
                        }}
                      >
                        {display}
                      </button>
                      {notRunRecord ? <span className="cell-sub" data-testid="task-not-run">研究未运行</span> : null}
                    </td>
                    <td>
                      {notRunRecord ? (
                        <StatusBadge status={researchStatusRecordView(task.reason, task.reason_text)} size="sm" />
                      ) : (
                        <TaskStatusBadge status={task.status} reason={task.reason} conclusion={task.conclusion} />
                      )}
                    </td>
                    <td>
                      <span className="cell-sub">{formatDateTime(task.created_at)}</span>
                      <span className="cell-sub">
                        {notRunRecord ? '未执行' : task.started_at === null ? '尚未开始' : '耗时 ' + formatDuration(task.started_at, task.finished_at)}
                      </span>
                    </td>
                    <td className="cell-reason" title={outcome}>
                      {outcome}
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className="row-actions">
                        {canCancel ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            icon="ban"
                            loading={agent.busy === 'cancel:' + task.id}
                            disabled={busy}
                            onClick={() => onRequestCancel(task.id, display)}
                            data-testid="task-cancel"
                          >
                            取消
                          </Button>
                        ) : null}
                        {task.retryable ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            icon="retry"
                            loading={agent.busy === 'retry:' + task.id}
                            disabled={busy}
                            onClick={async () => {
                              const error = await agent.retryTask(task.id);
                              if (error) toast.push({ title: '重试失败', description: error.message, tone: 'danger' });
                              else toast.push({ title: '任务已重新排队', tone: 'success' });
                            }}
                            data-testid="task-retry"
                          >
                            安全重试
                          </Button>
                        ) : null}
                        {canCancel || task.retryable ? null : <Icon name="chevron-right" size={14} className="muted" />}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
          <div className="tasks-pagination">
            <div className="tasks-pagination__meta">显示最近 {countText(agent.tasks.length, UNITS.task)}任务</div>
            <div className="tasks-pagination__actions">
              <Button
                size="sm"
                variant="ghost"
                icon="chevrons-left"
                disabled={agent.pageBefore === null || busy}
                onClick={() => void agent.goPage(null)}
              >
                最新
              </Button>
              <Button
                size="sm"
                variant="ghost"
                iconRight="chevron-right"
                disabled={agent.nextBefore === null || busy}
                onClick={() => {
                  if (agent.nextBefore !== null) void agent.goPage(agent.nextBefore);
                }}
              >
                更早
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}

function BudgetCard({ status, agent }: { status: AgentStatus; agent: AgentState }) {
  const budget = status.budget;
  const configured = budget.state === 'configured';
  const dailyUsed = usedMicro(budget.daily_limit_micro, budget.daily_remaining_micro);
  const monthlyUsed = usedMicro(budget.monthly_limit_micro, budget.monthly_remaining_micro);
  const dailyPct = percent(dailyUsed, budget.daily_limit_micro);
  const monthlyPct = percent(monthlyUsed, budget.monthly_limit_micro);
  const dailyTone = dailyPct >= 100 ? 'danger' : dailyPct >= 80 ? 'warning' : 'default';
  const monthlyTone = monthlyPct >= 100 ? 'danger' : monthlyPct >= 80 ? 'warning' : 'default';

  return (
    <Card className="agent-budget" data-testid="agent-budget">
      <CardHead
        title={
          <span className="card__title-with-hint">
            研究预算
            <InfoHint label="研究预算说明">达到日或月上限后只暂停付费研究，不影响行情采集与交易保护。</InfoHint>
          </span>
        }
        actions={
          <>
            <StatusBadge status={configured ? statusView('ok', '正常') : statusView('attention', '需要处理')} />
            <BudgetEditor agent={agent} budget={budget} />
          </>
        }
      />
      <CardBody>
        {configured ? (
          <>
            <div className="budget-block">
              <div className="budget-block__head">
                <span>今日已用</span>
                <span className="budget-block__values numeric">
                  {moneyText(dailyUsed, budget.currency)} / {moneyText(budget.daily_limit_micro, budget.currency)}
                </span>
              </div>
              <ProgressBar value={dailyPct} tone={dailyTone} label="今日研究预算使用" />
            </div>
            <div className="budget-block">
              <div className="budget-block__head">
                <span>本月已用</span>
                <span className="budget-block__values numeric">
                  {moneyText(monthlyUsed, budget.currency)} / {moneyText(budget.monthly_limit_micro, budget.currency)}
                </span>
              </div>
              <ProgressBar value={monthlyPct} tone={monthlyTone} label="本月研究预算使用" />
            </div>
            <details className="disclosure budget-usage">
              <summary className="disclosure__summary">
                <span>用量明细</span>
                <Icon name="chevron-down" />
              </summary>
              <div className="disclosure__body">
                <Kv
                  tight
                  items={[
                    { label: '未结清预留', value: moneyText(budget.reserved_micro, budget.currency) },
                    { label: '调用尝试（累计）', value: countText(budget.call_count, '次') },
                    {
                      label: '输入 / 输出 Token',
                      value: countText(budget.input_tokens, '个') + ' / ' + countText(budget.output_tokens, '个'),
                    },
                    { label: '收到用量估算', value: moneyText(budget.usage_estimate_micro, budget.currency) },
                  ]}
                />
                <p className="budget-note">调用次数与用量是本地累计记录；云端返回的用量不是最终账单，未核对前按最大预留占用。</p>
              </div>
            </details>
          </>
        ) : (
          <>
            <Callout tone="warning" title="需要处理：尚未设置研究预算">
              未设置预算时不会开始新的研究；点右上角「编辑预算」设置每日与每月上限。
            </Callout>
            <p className="budget-note">已有的研究任务、研究报告仍可查看。</p>
          </>
        )}
      </CardBody>
    </Card>
  );
}

function ModelsCard({ status, agent }: { status: AgentStatus; agent: AgentState }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const selected = status.models.find((model) => model.id === status.default_model) ?? null;
  const modelStatus = selected === null
    ? statusView('attention', '需要处理', '尚未选择默认研究模型')
    : modelStatusView(selected);

  return (
    <Card className="agent-models" data-testid="agent-models">
      <CardHead
        title="模型设置"
        actions={
          <Button
            variant="ghost"
            size="sm"
            icon={open ? 'chevron-down' : 'settings'}
            onClick={() => setOpen((value) => !value)}
            data-testid="agent-models-toggle"
          >
            {open ? '收起设置' : '展开设置'}
          </Button>
        }
      />
      <CardBody>
        <div className="model-summary">
          <div className="model-summary__main">
            <span className="model-summary__label">当前研究模型</span>
            <span className="model-summary__name">{selected === null ? '未设置' : modelDisplayName(selected)}</span>
          </div>
          <StatusBadge status={modelStatus} />
        </div>
        {modelStatus.reason === undefined ? null : <p className="model-footnote">{modelStatus.reason}</p>}

        {open ? (
          <div className="model-settings">
            {status.models.length === 0 ? (
              <Callout tone="warning" title="需要处理：尚未配置研究模型">
                请先在设置中配置 AI 服务与 API Key，并保存研究模型。
                <div className="inline-row inline-row--tight">
                  <Button variant="secondary" size="sm" onClick={() => navigate({ page: 'settings', section: 'ai' })}>去设置</Button>
                </div>
              </Callout>
            ) : (
              <>
                <div className="model-config-grid">
                  <Field label="默认研究模型" htmlFor="agent-default-model" hint="切换后只影响之后新建的研究任务。">
                    <Select
                      id="agent-default-model"
                      data-testid="agent-default-model"
                      value={status.default_model ?? ''}
                      disabled={isBusy(agent, 'control:')}
                      onChange={async (event) => {
                        const modelId = event.target.value;
                        if (modelId === '') return;
                        const error = await agent.control({ action: 'model', model_id: modelId });
                        if (error) toast.push({ title: '默认模型切换失败', description: error.message, tone: 'danger' });
                        else toast.push({ title: '默认模型已切换', description: '只影响之后新建的研究任务。', tone: 'success' });
                      }}
                    >
                      {status.default_model === null ? <option value="" disabled>请选择</option> : null}
                      {status.models.map((model) => (
                        <option key={model.id} value={model.id}>{modelDisplayName(model)}</option>
                      ))}
                    </Select>
                  </Field>
                  {status.models.length >= 2 ? (
                    <Field label="备用模型" htmlFor="agent-backup-model" hint="备用模型仅保存，不会自动切换。">
                      <Select
                        id="agent-backup-model"
                        data-testid="agent-backup-model"
                        value={status.backup_model ?? ''}
                        disabled={isBusy(agent, 'control:')}
                        onChange={async (event) => {
                          const modelId = event.target.value;
                          if (modelId === '') return;
                          const error = await agent.control({ action: 'backup', model_id: modelId });
                          if (error) toast.push({ title: '备用模型保存失败', description: error.message, tone: 'danger' });
                          else toast.push({ title: '备用模型已保存', description: '不会自动切换模型。', tone: 'success' });
                        }}
                      >
                        <option value="" disabled>未选择</option>
                        {status.models.map((model) => (
                          <option key={model.id} value={model.id}>{modelDisplayName(model)}</option>
                        ))}
                      </Select>
                    </Field>
                  ) : null}
                </div>
                <p className="model-footnote">研究模型只在本机研究服务中调用；切换不会改写历史任务。</p>
              </>
            )}
            <Diagnostics
              items={[
                { label: '默认模型配置', value: status.default_model ?? COMMON.notAvailable },
                { label: '备用模型配置', value: status.backup_model ?? COMMON.notAvailable },
                {
                  label: '模型定义',
                  value: status.models.map((model) => model.id + ' · ' + model.model + ' · ' + model.price_version + ' · ' + model.availability).join('；') || COMMON.notAvailable,
                },
                { label: '自动切换', value: status.automatic_fallback },
              ]}
              data={{ models: status.models, usage_by_model: status.usage_by_model }}
            />
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function TaskDrawer({
  agent,
  status,
  onRequestCancel,
}: {
  agent: AgentState;
  status: AgentStatus;
  onRequestCancel: (id: string, title: string) => void;
}) {
  const toast = useToast();
  const detail = agent.detail;
  const title = detail === null ? '研究任务' : taskDetailDisplayName(detail);
  const view = detail === null
    ? null
    : isResearchStatusRecord(detail.kind, detail.provider_id)
      ? researchStatusRecordView(detail.reason, detail.reason_text)
      : taskStatusView(detail.status, detail.reason_text ?? detail.reason, detail.result?.research.hypothesis ?? null);
  const canCancel = detail !== null && ['queued', 'running', 'local_running'].includes(detail.status);
  const canRetry = detail !== null && detail.retryable;

  return (
    <Drawer
      open={agent.detailOpen}
      onClose={agent.closeTask}
      eyebrow="研究任务"
      title={title}
      meta={view === null ? null : <StatusBadge status={view} />}
      footer={
        <>
          <Button size="sm" variant="ghost" icon="refresh" loading={agent.detailLoading} onClick={() => void agent.refreshDetail()}>
            刷新
          </Button>
          <span className="drawer__foot-spacer" />
          {canRetry ? (
            <Button
              size="sm"
              variant="secondary"
              icon="retry"
              loading={detail !== null && agent.busy === 'retry:' + detail.id}
              disabled={agent.busy !== null}
              onClick={async () => {
                if (detail === null) return;
                const error = await agent.retryTask(detail.id);
                if (error) toast.push({ title: '重试失败', description: error.message, tone: 'danger' });
                else toast.push({ title: '任务已重新排队', tone: 'success' });
              }}
            >
              安全重试
            </Button>
          ) : null}
          {canCancel ? (
            <Button
              size="sm"
              variant="danger"
              icon="ban"
              loading={detail !== null && agent.busy === 'cancel:' + detail.id}
              disabled={agent.busy !== null}
              onClick={() => {
                if (detail === null) return;
                onRequestCancel(detail.id, title);
              }}
            >
              取消任务
            </Button>
          ) : null}
        </>
      }
    >
      {agent.detailError !== null && detail !== null ? (
        <Callout tone="warning" title="详情刷新失败，显示上次读取记录">
          {agent.detailError.message}
        </Callout>
      ) : null}
      {agent.detailLoading && detail === null ? (
        <SkeletonLines lines={6} />
      ) : agent.detailError !== null && detail === null ? (
        <EmptyState
          tone="error"
          icon="alert-triangle"
          title="任务详情不可用"
          description={agent.detailError.message}
          actions={<Button variant="secondary" icon="refresh" onClick={() => void agent.refreshDetail()}>重新读取</Button>}
        />
      ) : detail !== null ? (
        <div className="task-detail" data-testid="task-detail">
          <TaskDetailBody detail={detail} currency={status.budget.currency} />
        </div>
      ) : (
        <p className="muted">任务详情尚未加载。</p>
      )}
    </Drawer>
  );
}

function ResearchStatusRecordDetail({ detail }: { detail: AgentTaskDetail }) {
  return (
    <>
      <div className="drawer__section">
        <h3 className="drawer__section-title">结论与原因</h3>
        <StatusLine status={researchStatusRecordView(detail.reason, detail.reason_text)} />
        <p className="detail-sentence">这条记录只说明研究未能运行，没有执行详情。</p>
      </div>

      <div className="drawer__section">
        <p className="drawer-note">
          这不是付费研究任务，不会产生费用；上面显示的是系统在自动研究前检查行情与授权时留下的原因。原因消除后，下一次收盘后自动研究可以继续运行。
        </p>
      </div>

      <div className="drawer__section">
        <Diagnostics
          items={[
            { label: '记录 ID', value: detail.id },
            { label: '记录类型', value: detail.provider_id },
            { label: '状态原始值', value: detail.status },
            { label: '原因原始值', value: detail.reason ?? COMMON.notAvailable },
            { label: '创建时间', value: formatDateTime(detail.created_at) },
            { label: '调用记录', value: countText(detail.calls.length, '次') },
          ]}
          data={{ request: detail.request, input: detail.input, calls: detail.calls }}
        />
      </div>
    </>
  );
}

function TaskDetailBody({ detail, currency }: { detail: AgentTaskDetail; currency: string }) {
  if (isResearchStatusRecord(detail.kind, detail.provider_id)) return <ResearchStatusRecordDetail detail={detail} />;
  const result = detail.result;
  const view = taskStatusView(detail.status, detail.reason_text ?? detail.reason, result?.research.hypothesis ?? null);
  const cost = taskCost(detail.calls);

  return (
    <>
      <div className="drawer__section">
        <h3 className="drawer__section-title">结论与原因</h3>
        <StatusLine status={view} showReason={false} />
        <p className="detail-sentence">{detailSentence(detail)}</p>
        {result === null ? (
          detail.artifact === undefined ? (
            <p className="drawer-note">还没有保存的研究结论。</p>
          ) : (
            <p className="drawer-note">已保存结构化研究产物；研究结论未能识别，原始内容见下方诊断信息。</p>
          )
        ) : result.synthetic_provider ? (
          <Callout tone="info" title="本地测试结果">
            这次研究由本地测试数据生成，仅用于验证软件流程，不能作为研究结论；完整内容见下方诊断信息。
          </Callout>
        ) : (
          <>
            <div className="result-section">
              <h4>关键依据</h4>
              <ul>{result.research.evidence.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </div>
            <div className="result-section">
              <h4>反证与风险</h4>
              <ul>{result.research.risks.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </div>
            <div className="result-section">
              <h4>下一步</h4>
              <ul>{result.research.next_steps.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </div>
            <Callout tone="warning" title="使用限制">{result.limitations}</Callout>
          </>
        )}
      </div>

      <div className="drawer__section">
        <h3 className="drawer__section-title">做了什么</h3>
        <Kv
          tight
          items={[
            { label: '研究目标', value: detail.request.goal },
            { label: '研究范围', value: displayScope(detail.request.scope) },
            { label: '请求区间', value: detail.request.start_day + ' — ' + detail.request.end_day },
            { label: '耗时', value: formatDuration(detail.started_at, detail.finished_at) },
            { label: '创建时间', value: formatDateTime(detail.created_at) },
          ]}
        />
      </div>

      <div className="drawer__section">
        <h3 className="drawer__section-title">花费</h3>
        <Kv
          tight
          items={[
            { label: '本次费用', value: cost === null ? '尚未产生费用' : formatMicroMoney(cost, currency) },
            { label: '调用记录', value: countText(detail.calls.length, '次') },
          ]}
        />
        <p className="drawer-note">费用按已保存的调用记录汇总：已核对账单按实际金额，未核对或结果未知的调用按最大预留计；取消任务不会撤销已经发出的计费请求。</p>
      </div>

      <div className="drawer__section">
        <Diagnostics
          items={[
            { label: '任务 ID', value: detail.id },
            { label: '研究服务配置', value: detail.provider_id },
            { label: '配置哈希', value: detail.provider_hash },
            { label: '状态原始值', value: detail.status },
            { label: '原因原始值', value: detail.reason ?? COMMON.notAvailable },
            { label: '冻结输入版本', value: detail.input.version },
            { label: '输入模式', value: detail.input.mode },
            { label: '输入数据日期', value: detail.input.source_day },
            { label: '输入范围', value: detail.input.scopes.join('、') },
            { label: '请求预算', value: detail.request.task_budget_micro ?? '未设置' },
            { label: '结果服务类型', value: result?.provider_kind ?? COMMON.notAvailable },
            { label: '结果模型', value: result?.model ?? COMMON.notAvailable },
            { label: '结果生成时间', value: result === null ? COMMON.notAvailable : formatDateTime(result.generated_at) },
            { label: '结果计费说明', value: result?.billing ?? COMMON.notAvailable },
            { label: '结果来源（合成）', value: result === null ? COMMON.notAvailable : result.synthetic_provider ? 'true' : 'false' },
            {
              label: '创建 / 开始 / 完成',
              value: formatDateTime(detail.created_at) + ' / ' + formatDateTime(detail.started_at) + ' / ' + formatDateTime(detail.finished_at),
            },
            { label: '取消申请时间', value: formatDateTime(detail.cancel_requested_at) },
            { label: '调用记录', value: <CallRecords calls={detail.calls} currency={currency} /> },
          ]}
          data={{ input: detail.input, calls: detail.calls, artifact: detail.artifact, result: detail.result }}
        />
      </div>
    </>
  );
}

function CallRecords({ calls, currency }: { calls: AgentCall[]; currency: string }) {
  if (calls.length === 0) return <span>尚无调用记录</span>;
  return (
    <div className="mini-table-wrap">
      <table className="mini-table call-table">
        <thead>
          <tr>
            <th>序号</th>
            <th>状态</th>
            <th className="num">最大 / 已核对 / 估算</th>
            <th>周期</th>
            <th>费率版本</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call, index) => (
            <tr key={call.id}>
              <td>{index + 1}</td>
              <td>{call.state}</td>
              <td className="num">
                {formatMicroMoney(call.maximum_micro, currency)} / {formatMicroMoney(call.settled_micro, currency)} /{' '}
                {formatMicroMoney(call.usage_micro, currency)}
              </td>
              <td>{call.day} / {call.month}</td>
              <td>{call.price_version}</td>
              <td>{callReasonText(call)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreateFooter({ agent, canCreate, onCancel }: { agent: AgentState; canCreate: boolean; onCancel: () => void }) {
  return (
    <>
      <span className="modal__foot-note">提交后进入队列，完成后结论会保存在研究报告里。</span>
      <Button variant="ghost" type="button" onClick={onCancel} disabled={agent.busy === 'create'}>
        取消
      </Button>
      <Button variant="primary" type="submit" form="agent-task-form" loading={agent.busy === 'create'} disabled={!canCreate}>
        提交研究
      </Button>
    </>
  );
}

function CreateTaskForm({
  agent,
  canCreate,
  disabledReason,
  sourceDay,
  currency,
  onDone,
}: {
  agent: AgentState;
  canCreate: boolean;
  disabledReason: string;
  sourceDay: string;
  currency: string;
  onDone: () => void;
}) {
  const defaults = defaultRange(sourceDay);
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [scope, setScope] = useState('当前已发布的模拟账户摘要');
  const [startDay, setStartDay] = useState(defaults.start);
  const [endDay, setEndDay] = useState(defaults.end);
  const [budget, setBudget] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [formCode, setFormCode] = useState<string | null>(null);
  const requestKey = useRef(crypto.randomUUID().replaceAll('-', ''));
  const loading = agent.busy === 'create';

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canCreate || loading) return;
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = '请输入任务名称。';
    else if (name.trim().length > 40) next.name = '任务名称不能超过 40 个字符。';
    if (!goal.trim()) next.goal = '请写明研究目标与反证条件。';
    else if (goal.trim().length > 650) next.goal = '研究目标不能超过 650 个字符。';
    if (!scope.trim()) next.scope = '请输入研究范围。';
    else if (scope.trim().length > 100) next.scope = '研究范围不能超过 100 个字符。';
    const start = dateInputToDay(startDay);
    const end = dateInputToDay(endDay);
    if (!start) next.start = '开始日期格式无效。';
    if (!end) next.end = '结束日期格式无效。';
    if (start && end && start > end) next.end = '结束日期不能早于开始日期。';
    if (budget.trim() && !/^[0-9]+$/.test(budget.trim())) next.budget = '任务预算必须是大于 0 的整数。';
    else if (budget.trim() && BigInt(budget.trim()) <= 0n) next.budget = '任务预算必须大于 0。';
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setFormError(null);
    setFormCode(null);
    const result = await agent.createTask({
      request_key: requestKey.current,
      name: name.trim(),
      goal: goal.trim(),
      scope: scope.trim(),
      start_day: startDay,
      end_day: endDay,
      task_budget_micro: budget.trim() || null,
    });
    if (result.error) {
      setFormError(result.error.message);
      setFormCode(result.error.code);
      return;
    }
    if (result.id) {
      requestKey.current = crypto.randomUUID().replaceAll('-', '');
      onDone();
    }
  };

  return (
    <form id="agent-task-form" className="agent-task-form" onSubmit={(event) => void submit(event)}>
      {canCreate ? null : (
        <Callout tone="warning" title="当前不能新建研究">
          {disabledReason}
        </Callout>
      )}
      <div className="form-grid">
        <Field label="任务名称" htmlFor="task-name" hint="最多 40 个字符，列表里会显示成「日期 · 任务名称」。" error={errors.name} className="form-grid__full">
          <TextInput
            id="task-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={40}
            placeholder="例如：成本假设复核"
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.name)}
            data-autofocus
          />
        </Field>
        <Field label="研究目标" htmlFor="task-goal" hint="写明希望验证的问题、依据与反证条件。" error={errors.goal} className="form-grid__full">
          <TextArea
            id="task-goal"
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            maxLength={650}
            rows={4}
            placeholder="例如：核查成本与缺估值约束会如何改变表面收益，并说明在什么证据下应放弃该假设。"
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.goal)}
          />
        </Field>
        <Field label="研究范围" htmlFor="task-scope" hint="描述本次研究覆盖的账户、数据与课题范围。" error={errors.scope}>
          <TextInput
            id="task-scope"
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            maxLength={100}
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.scope)}
          />
        </Field>
        <Field
          label="任务预算（可选）"
          htmlFor="task-budget"
          hint={'留空表示只受每日与每月上限约束；如需填写，数值为货币的百万分之一（50000 相当于 ' + formatMicroMoney('50000', currency) + '）。'}
          error={errors.budget}
        >
          <TextInput
            id="task-budget"
            value={budget}
            onChange={(event) => setBudget(event.target.value)}
            inputMode="numeric"
            pattern="[0-9]*"
            placeholder="例如 50000"
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.budget)}
          />
        </Field>
        <Field label="开始日期" htmlFor="task-start" hint="研究请求的数据区间，不保证区间内已有完整数据。" error={errors.start}>
          <TextInput
            id="task-start"
            type="date"
            value={startDay}
            onChange={(event) => setStartDay(event.target.value)}
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.start)}
          />
        </Field>
        <Field label="结束日期" htmlFor="task-end" hint="默认取最近一次已发布的数据日期。" error={errors.end}>
          <TextInput
            id="task-end"
            type="date"
            value={endDay}
            onChange={(event) => setEndDay(event.target.value)}
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.end)}
          />
        </Field>
      </div>
      <Callout tone="warning" title="费用与取消">
        创建研究可能产生费用；取消运行中的任务不会撤销已经发出的计费请求。费用以最终账单为准，系统不会自动重发。
      </Callout>
      {formError === null ? null : (
        <Callout tone="danger" title="提交失败" className="form-error" role="alert">
          {formError}
          {formCode === null ? null : <Diagnostics items={[{ label: '原始错误码', value: formCode }]} />}
        </Callout>
      )}
    </form>
  );
}
