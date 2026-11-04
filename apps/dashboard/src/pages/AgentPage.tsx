import { useMemo, useRef, useState } from 'react';
import type { FormEvent, Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button, IconButton } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { EmptyState } from '../components/ui/EmptyState';
import { Modal, Drawer } from '../components/ui/Overlay';
import { Field, Select, TextArea, TextInput } from '../components/ui/Field';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Switch } from '../components/ui/Switch';
import { Skeleton, SkeletonLines } from '../components/ui/Skeleton';
import { Table } from '../components/ui/Table';
import { useToast } from '../components/ui/Toast';
import { TaskStatusBadge, AvailabilityBadge } from '../components/domain/Badges';
import { Icon } from '../icons';
import {
  EOD_DISPOSITION_LABELS,
  RESEARCH_QUALIFICATION_LABELS,
  TASK_STATUS_LABELS,
  VERIFICATION_LABELS,
} from '../lib/labels';
import {
  dateInputToDay,
  formatClock,
  formatDateTime,
  formatDuration,
  formatMicro,
  formatShares,
  parseInteger,
  todayShanghai,
} from '../lib/format';
import type { AgentCall, AgentModel, AgentStatus, AgentTask, AgentTaskDetail } from '../lib/types';
import type { AgentState } from '../state/useAgent';
import { formatDay } from '../lib/format';
import { ResearchOperations } from '../components/domain/ResearchOperations';
import { humanReason } from '../lib/api';
import { ModeBadge } from '../components/domain/Badges';
import { stateLabel } from '../lib/workspace';
import { WorkspaceStudies, TechnicalDetails } from '../components/domain/WorkspaceStudies';
import type { WorkspaceState } from '../lib/workspace';

function isBusy(agent: AgentState, prefix: string): boolean {
  return Boolean(agent.busy && agent.busy.startsWith(prefix));
}

function taskDuration(task: AgentTask): string {
  if (!task.started_at) return '—';
  if (task.finished_at) return formatDuration(task.started_at, task.finished_at);
  return task.status === 'running' ? '运行中' : '—';
}

function taskCost(calls: AgentCall[]): string | null {
  if (!calls || calls.length === 0) return null;
  let total = 0n;
  for (const call of calls) {
    const raw = call.state === 'settled' ? call.settled_micro : call.state === 'no_charge' ? '0' : call.maximum_micro;
    const value = parseInteger(raw);
    if (value !== null) total += value;
  }
  return total.toString();
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

function defaultRange(sourceDay: string | undefined): { start: string; end: string } {
  const today = todayShanghai();
  const source = sourceDay && /^\d{4}-\d{2}-\d{2}$/.test(sourceDay) ? sourceDay : today;
  return { start: source, end: source };
}

export function AgentPage({ agent, workspace, titleRef }: { agent: AgentState; workspace: WorkspaceState; titleRef?: Ref<HTMLHeadingElement> }) {
  const toast = useToast();
  const [unlockOpen, setUnlockOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const status = agent.status;
  const unlocked = agent.phase === 'ready' && Boolean(status);

  const header = (
    <PageHeader
      title="Agent 管理"
      titleRef={titleRef}
      side={
        unlocked ? (
          <>
            <Badge tone="success">本机会话已解锁</Badge>
            <span className="page-meta">{agent.lastUpdated ? '更新于 ' + formatClock(agent.lastUpdated) : '等待读取'}</span>
            <Button
              size="sm"
              variant="ghost"
              icon="lock"
              onClick={() => {
                agent.lock();
                toast.push({ title: '已锁定本机会话', description: 'Owner 令牌已从页面内存移除。', tone: 'info' });
              }}
            >
              锁定
            </Button>
          </>
        ) : (
          <Badge tone="outline">未解锁</Badge>
        )
      }
    />
  );

  if (agent.phase === 'locked') {
    return (
      <>
        {header}
        {agent.error ? (
          <Callout tone="warning" title="研究会话不可用" className="stale-banner">
            {agent.error.message}
          </Callout>
        ) : null}
        <div className="grid agent-gate-grid">
          <div className="col-7">
            <Card className="agent-gate">
              <div className="agent-gate__icon" aria-hidden="true"><Icon name="lock" size={22} /></div>
              <h2 className="agent-gate__title">解锁本机研究控制</h2>
              <p className="agent-gate__desc">
                使用本机 Owner 令牌查看和管理研究任务。
              </p>
              <ul className="gate-points">
                <li><Icon name="key" size={14} /><span>令牌仅保存在页面内存，刷新后需重新解锁。</span></li>
                <li><Icon name="database" size={14} /><span>刷新列表与查看详情不会调用付费模型。</span></li>
              </ul>
              <div className="agent-gate__actions">
                <Button variant="primary" icon="unlock" onClick={() => setUnlockOpen(true)}>
                  输入 Owner 令牌
                </Button>
                <span className="agent-gate__hint">从本机 Agent 目录的 owner-token 文件复制</span>
              </div>
            </Card>
          </div>
          <div className="col-5">
            <Card className="agent-boundary">
              <CardHead
                title="研究边界"
                actions={<Badge tone="outline">Paper only</Badge>}
              />
              <div className="boundary-list">
                <div className="boundary-item">
                  <span className="boundary-item__icon"><Icon name="file" /></span>
                  <div><strong>持久任务</strong><p>任务、结果与调用记录保存在本机。</p></div>
                </div>
                <div className="boundary-item">
                  <span className="boundary-item__icon"><Icon name="wallet" /></span>
                  <div><strong>硬预算</strong><p>日/月上限与调用预留由可信服务执行。</p></div>
                </div>
                <div className="boundary-item">
                  <span className="boundary-item__icon"><Icon name="shield" /></span>
                  <div><strong>无交易权限</strong><p>探索性研究不授予策略资格或实盘许可。</p></div>
                </div>
              </div>
            </Card>
          </div>
        </div>
        <UnlockModal
          open={unlockOpen}
          agent={agent}
          onClose={() => setUnlockOpen(false)}
          onSuccess={() => {
            setUnlockOpen(false);
            toast.push({ title: '已解锁本机研究控制', description: '令牌仅在当前页面内存中保留。', tone: 'success' });
          }}
        />
      </>
    );
  }

  if (agent.phase === 'loading') {
    return (
      <>
        {header}
        <div role="status" className="sr-only">正在读取本机研究服务</div>
        <div className="grid">
          <div className="col-7"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
          <div className="col-5"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
          <div className="col-12"><Skeleton className="skeleton-card" /></div>
          <div className="col-12"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
        </div>
      </>
    );
  }

  if (agent.phase === 'error' || !status) {
    return (
      <>
        {header}
        <Card>
          <EmptyState
            tone="error"
            icon="alert-triangle"
            title="研究服务不可用"
            description={agent.error?.message || '本机研究服务未返回状态。请确认 Agent 已启动并配置。'}
            code={agent.error?.code}
            actions={
              <>
                <Button variant="secondary" icon="refresh" onClick={() => void agent.refresh()}>重新读取</Button>
                <Button variant="ghost" onClick={agent.lock}>锁定会话</Button>
              </>
            }
          />
        </Card>
      </>
    );
  }

  const budget = status.budget;
  const budgetConfigured = budget.state === 'configured';
  const defaultModel = status.models.find((model) => model.id === status.default_model) ?? null;
  const canCreate = Boolean(defaultModel) && budgetConfigured && status.dashboard_mode !== 'attached_explicit_operations';
  const createDisabledReason = !defaultModel
    ? '尚未配置默认研究模型，不能创建任务。'
    : status.dashboard_mode === 'attached_explicit_operations'
      ? '请使用下方冻结研究入口，沿用原 Worker、预算与来源绑定。'
    : !budgetConfigured
      ? '日/月预算未配置，付费研究已被阻止。'
      : '';
  const runningTasks = agent.tasks.filter((task) => task.status === 'running').length;

  return (
    <>
      {header}
      {agent.error ? (
        <Callout tone="warning" title="最近一次读取失败，显示上次成功读取的状态" className="stale-banner">
          <div className="stale-banner__row">
            <span>{agent.error.message}</span>
            <Button size="sm" variant="ghost" icon="refresh" onClick={() => void agent.refresh()}>重新读取</Button>
          </div>
        </Callout>
      ) : null}

      <div className="grid agent-grid">
        <div className="col-7">
          <Card className="agent-runtime">
            <CardHead
              title="研究运行状态"
              actions={
                <Badge tone={status.paused ? 'warning' : runningTasks ? 'accent' : 'neutral'}>
                  {status.paused ? '已优雅暂停' : runningTasks ? '研究中 ' + String(runningTasks) : '等待执行'}
                </Badge>
              }
            />
            <CardBody>
              <div className="runtime-head">
                <div>
                  <h3 className="runtime-title">{status.paused ? '已暂停接收新任务' : '等待或执行已授权研究'}</h3>
                  <p className="runtime-desc">
                    {status.paused
                      ? '暂停接收新任务，已提交的调用可完成。'
                      : '任务串行执行，详情只读取已保存记录。'}
                  </p>
                </div>
                <div className="runtime-actions">
                  <Button
                    variant={status.paused ? 'primary' : 'secondary'}
                    icon={status.paused ? 'play' : 'pause'}
                    loading={isBusy(agent, 'control:pause') || isBusy(agent, 'control:resume')}
                    onClick={async () => {
                      const error = await agent.control({ action: status.paused ? 'resume' : 'pause' });
                      if (error) toast.push({ title: '操作失败', description: error.message, tone: 'danger' });
                      else toast.push({ title: status.paused ? '已恢复研究' : '已优雅暂停研究', tone: 'success' });
                    }}
                  >
                    {status.paused ? '恢复研究' : '优雅暂停'}
                  </Button>
                </div>
              </div>

              {status.worker_error ? (
                <Callout tone="warning" title="Worker 报告错误" className="runtime-warning">{humanReason(status.worker_error)}<TechnicalDetails value={{reason:status.worker_error}}/></Callout>
              ) : null}

              <div className="runtime-meta">
                <div><span>Worker 并发</span><strong>{status.worker_concurrency}</strong></div>
                <div><span>默认模型</span><strong>{defaultModel?.label ?? '未配置'}</strong></div>
                <div><span>研究资格</span><strong title={status.qualification}>{RESEARCH_QUALIFICATION_LABELS[status.qualification] ?? '资格待核对'}</strong></div>
                <div><span>自动 fallback</span><strong>关闭 · 仅 Owner 切换</strong></div>
              </div>

              <div className="eod-block" hidden={status.dashboard_mode==='attached_explicit_operations'}>
                <div className="eod-head">
                  <div>
                    <h3 className="eod-title">EOD 自动研究</h3>
                    <p className="eod-desc">默认关闭；只为最新有效源日派发，同源日不重复。最终状态以服务端持久记录为准。</p>
                  </div>
                  <div className="eod-switch">
                    <span className="eod-switch-label">{status.eod.enabled ? '已启用' : '已停用'}</span>
                    <Switch
                      checked={status.eod.enabled}
                      busy={isBusy(agent, 'control:eod')}
                      label="EOD 自动研究开关"
                      onChange={async (enabled) => {
                        const error = await agent.control({ action: 'eod', enabled });
                        if (error) toast.push({ title: 'EOD 设置失败', description: error.message, tone: 'danger' });
                        else toast.push({ title: enabled ? '已启用 EOD 自动研究' : '已关闭 EOD 自动研究', tone: 'success' });
                      }}
                    />
                  </div>
                </div>
                <div className="eod-latest">
                  <span className="eod-latest__label">最近记录</span>
                  {status.eod.latest ? (
                    <div className="eod-latest__body">
                      <span>源日 {status.eod.latest.source_day || '—'}</span>
                      <Badge tone={status.eod.latest.disposition === 'completed' ? 'success' : status.eod.latest.disposition === 'failed' || status.eod.latest.disposition === 'outcome_uncertain' ? 'warning' : 'neutral'}>
                        {EOD_DISPOSITION_LABELS[status.eod.latest.disposition ?? ''] ?? '状态待核对'}
                      </Badge>
                      <span className="muted" title={status.eod.latest.reason || status.eod.reason || ''}>{humanReason(status.eod.latest.reason || status.eod.reason || null)}</span>
                    </div>
                  ) : (
                    <span className="muted">尚无 EOD 派发记录 · 已记录跳过 {status.eod.skipped} 次</span>
                  )}
                </div>
              </div>
            </CardBody>
          </Card>
        </div>

        <div className="col-5">
          <BudgetCard status={status} agent={agent} />
        </div>

        <div className="col-12">
          <ModelsCard status={status} agent={agent} />
        </div>

        <div className="col-12">
          <TasksCard
            agent={agent}
            status={status}
            canCreate={canCreate}
            createDisabledReason={createDisabledReason}
            onCreate={() => setCreateOpen(true)}
          />
        </div>
      </div>

      {agent.token !== null ? <ResearchOperations token={agent.token}/> : null}
      <WorkspaceStudies workspace={workspace}/>
      <TaskDrawer agent={agent} status={status} />

      <Modal
        open={createOpen}
        onClose={() => {
          if (agent.busy !== 'create') setCreateOpen(false);
        }}
        title="新建研究任务"
        description="任务会进入持久队列，并受日/月硬预算与新任务配置约束。"
        wide
        footer={<CreateFooter agent={agent} canCreate={canCreate} onCancel={() => setCreateOpen(false)} />}
      >
        <CreateTaskForm
          agent={agent}
          canCreate={canCreate}
          disabledReason={createDisabledReason}
          onDone={(id) => {
            setCreateOpen(false);
            toast.push({ title: '研究任务已排队', description: '任务 ID #' + id + '。列表读取不会调用模型。', tone: 'success' });
          }}
        />
      </Modal>
    </>
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
    <Card className="agent-budget">
      <CardHead
        title="研究预算"
        actions={<Badge tone={configured ? 'success' : 'warning'}>{configured ? budget.currency : '未配置'}</Badge>}
      />
      <CardBody>
        {!configured ? (
          <>
            <Callout tone="warning" title="日 / 月预算未配置，付费研究已阻止">
              额度只由本机 Owner 可信设置维护。Web 不提供加额或清锁；预算耗尽只暂停研究，不影响风险与账本。
            </Callout>
            <div className="budget-note">预算未配置时仍可查看已保存任务，但不会发起新的付费调用。</div>
          </>
        ) : (
          <>
            <div className="budget-block">
              <div className="budget-block__head">
                <span>今日</span>
                <span className="budget-block__values numeric">
                  {formatMicro(budget.daily_remaining_micro, { currency: budget.currency })} / {formatMicro(budget.daily_limit_micro, { currency: budget.currency })}
                </span>
              </div>
              <ProgressBar value={dailyPct} tone={dailyTone} label="今日研究预算使用" />
              <div className="budget-sub">
                <span>已占用（含预留）{formatMicro(dailyUsed, { currency: budget.currency })}</span>
                <span>已核对 {formatMicro(budget.daily_settled_micro)}</span>
              </div>
            </div>
            <div className="budget-block">
              <div className="budget-block__head">
                <span>本月</span>
                <span className="budget-block__values numeric">
                  {formatMicro(budget.monthly_remaining_micro, { currency: budget.currency })} / {formatMicro(budget.monthly_limit_micro, { currency: budget.currency })}
                </span>
              </div>
              <ProgressBar value={monthlyPct} tone={monthlyTone} label="本月研究预算使用" />
              <div className="budget-sub">
                <span>已占用（含预留）{formatMicro(monthlyUsed, { currency: budget.currency })}</span>
                <span>已核对 {formatMicro(budget.monthly_settled_micro)}</span>
              </div>
            </div>
            <dl className="budget-stats">
              <div><dt>未结清预留</dt><dd className="numeric">{formatMicro(budget.reserved_micro, { currency: budget.currency })}</dd></div>
              <div><dt>调用尝试</dt><dd className="numeric">{formatShares(budget.call_count)}</dd></div>
              <div><dt>输入 / 输出 Token</dt><dd className="numeric">{formatShares(budget.input_tokens)} / {formatShares(budget.output_tokens)}</dd></div>
              <div><dt>收到用量估算</dt><dd className="numeric">{formatMicro(budget.usage_estimate_micro, { currency: budget.currency })}</dd></div>
            </dl>
            <div className="budget-note">
              {budget.currency} · {budget.timezone} · {budget.day} / {budget.month}。未核定费用按最大预留计。
            </div>
          </>
        )}
        {agent.busy === 'control:eod' ? <span className="sr-only">正在更新 EOD 设置</span> : null}
      </CardBody>
    </Card>
  );
}

function ModelsCard({ status, agent }: { status: AgentStatus; agent: AgentState }) {
  const toast = useToast();
  const selected = status.models.find((model) => model.id === status.default_model) ?? null;
  const usage = status.usage_by_model ?? [];
  return (
    <Card className="agent-models">
      <CardHead
        title="模型与自动研究"
        subtitle="模型选择仅影响新任务"
        actions={<Badge tone="outline">{status.automatic_fallback.startsWith('disabled') ? '自动 fallback 关闭' : '备用仅保存'}</Badge>}
      />
      <CardBody>
        <div className="model-config-grid">
          <Field label="默认模型" htmlFor="agent-default-model">
            <Select
              id="agent-default-model"
              value={status.default_model ?? ''}
              disabled={agent.busy?.startsWith('control:') || status.models.length === 0}
              onChange={async (event) => {
                const modelId = event.target.value;
                if (!modelId) return;
                const error = await agent.control({ action: 'model', model_id: modelId });
                if (error) toast.push({ title: '默认模型切换失败', description: error.message, tone: 'danger' });
                else toast.push({ title: '默认模型已切换', description: '仅影响之后创建的新任务。', tone: 'success' });
              }}
            >
              {status.default_model ? null : <option value="" disabled>未配置</option>}
              {status.models.map((model) => (
                <option key={model.id} value={model.id}>{model.label} · {model.id}</option>
              ))}
            </Select>
          </Field>
          <Field label="备用配置" htmlFor="agent-backup-model" hint="仅保存，不自动 fallback；不可用时明确失败。">
            <Select
              id="agent-backup-model"
              value={status.backup_model ?? ''}
              disabled={agent.busy?.startsWith('control:') || status.models.length === 0}
              onChange={async (event) => {
                const modelId = event.target.value;
                if (!modelId) return;
                const error = await agent.control({ action: 'backup', model_id: modelId });
                if (error) toast.push({ title: '备用配置保存失败', description: error.message, tone: 'danger' });
                else toast.push({ title: '备用配置已保存', description: '备用配置不会自动切换。', tone: 'success' });
              }}
            >
              {status.backup_model ? null : <option value="" disabled>未选择</option>}
              {status.models.map((model) => (
                <option key={model.id} value={model.id}>{model.label} · {model.id}</option>
              ))}
            </Select>
          </Field>
          <div className="model-selected">
            <span className="field__label">当前默认配置</span>
            {selected ? (
              <div className="model-selected__body">
                <span className="model-selected__name">{selected.label}</span>
                <div className="inline-row inline-row--tight">
                  <Badge tone={selected.verification === 'FAKE_SYNTHETIC_ONLY' ? 'warning' : 'warning'}>
                    {VERIFICATION_LABELS[selected.verification] ?? selected.verification}
                  </Badge>
                  <AvailabilityBadge availability={selected.availability} />
                </div>
                <span className="model-selected__meta" title={selected.authorization}>{selected.kind==='fake'?'本地合成':'云 API'} · {selected.model} · {selected.authorization==='authorized'?'原授权有效':'授权受阻，查看技术原因'}</span>
                {selected.last_reason ? (
                  <span className="model-selected__meta">最近 Provider 观察：{selected.last_reason}</span>
                ) : null}
              </div>
            ) : (
              <span className="muted">未配置模型</span>
            )}
          </div>
        </div>

        {status.models.length === 0 ? (
          <Callout tone="warning" title="尚未配置研究模型" className="models-warning">
            模型、授权、费率与 HTTPS 端点只由本机可信设置维护；Web 不提供配置写入。
          </Callout>
        ) : (
          <div className="model-table-wrap">
            <table className="mini-table model-table">
              <thead>
                <tr>
                  <th>配置</th>
                  <th>类型 / 模型</th>
                  <th>授权</th>
                  <th>可用性</th>
                  <th>核验</th>
                  <th>费率版本</th>
                </tr>
              </thead>
              <tbody>
                {status.models.map((model) => (
                  <tr key={model.id}>
                    <td><span className="cell-title">{model.label}</span><span className="cell-sub">{model.id}</span></td>
                    <td><span className="cell-sub">{model.kind==='fake'?'本地合成':'云 API'}</span><span className="cell-mono">{model.model}</span></td>
                    <td title={model.authorization}>{model.authorization==='authorized'?'原授权有效':'授权受阻'}</td>
                    <td>
                      <AvailabilityBadge availability={model.availability} />
                      {model.last_reason ? <span className="cell-sub" title={model.last_reason}>{humanReason(model.last_reason)}</span> : null}
                    </td>
                    <td><Badge tone="neutral" title={model.verification}>{VERIFICATION_LABELS[model.verification] ?? '待核验'}</Badge></td>
                    <td className="cell-mono">{model.price_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <details className="disclosure model-usage">
          <summary className="disclosure__summary">
            <span>调用与模型用量</span>
            <Icon name="chevron-down" />
          </summary>
          <div className="disclosure__body">
            {usage.length === 0 ? (
              <p className="muted">尚无已记录用量。</p>
            ) : (
              <table className="mini-table">
                <thead>
                  <tr>
                    <th>配置</th>
                    <th className="num">调用</th>
                    <th className="num">输入 / 输出 Token</th>
                    <th className="num">用量估算</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.map((item) => (
                    <tr key={item.provider_id}>
                      <td>{status.models.find((model) => model.id === item.provider_id)?.label ?? item.provider_id}</td>
                      <td className="num">{formatShares(item.calls)}</td>
                      <td className="num">{formatShares(item.input_tokens)} / {formatShares(item.output_tokens)}</td>
                      <td className="num">{formatMicro(item.usage_micro, { currency: status.budget.currency })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </details>
      </CardBody>
    </Card>
  );
}

function TasksCard({
  agent,
  status,
  canCreate,
  createDisabledReason,
  onCreate,
}: {
  agent: AgentState;
  status: AgentStatus;
  canCreate: boolean;
  createDisabledReason: string;
  onCreate: () => void;
}) {
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return agent.tasks.filter((task) => {
      if (filter !== 'all') {
        if (filter === 'active' && !['queued', 'running', 'cancel_requested'].includes(task.status)) return false;
        if (filter === 'failed' && !['failed', 'outcome_uncertain'].includes(task.status)) return false;
        if (filter === 'completed' && task.status !== 'completed') return false;
        if (filter === 'cancelled' && task.status !== 'cancelled') return false;
      }
      if (!term) return true;
      return [task.name, task.provider_id, task.conclusion ?? '', task.reason ?? '', task.id]
        .join(' ')
        .toLowerCase()
        .includes(term);
    });
  }, [agent.tasks, filter, query]);

  const disabled = agent.busy !== null || !canCreate;

  return (
    <Card className="agent-tasks">
      <CardHead
        title="研究任务"
        actions={
          <>
            <IconButton
              label="刷新研究任务"
              icon="refresh"
              onClick={() => void agent.refresh()}
              disabled={agent.refreshing || agent.busy !== null}
            />
            <Button variant="primary" icon="plus" onClick={onCreate} disabled={disabled} title={createDisabledReason || undefined}>
              新建任务
            </Button>
          </>
        }
      />
      {!canCreate ? (
        <div className="tasks-disabled-note"><Icon name="info" size={14} /> {createDisabledReason}</div>
      ) : null}
      <div className="toolbar">
        <div className="toolbar__search">
          <Icon name="search" />
          <TextInput
            aria-label="搜索研究任务"
            placeholder="搜索任务、模型或结论"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <Select aria-label="任务状态筛选" value={filter} onChange={(event) => setFilter(event.target.value)} className="toolbar__select">
          <option value="all">全部状态</option>
          <option value="active">进行中</option>
          <option value="completed">已完成</option>
          <option value="failed">异常 / 费用不确定</option>
          <option value="cancelled">已取消</option>
        </Select>
        <span className="toolbar__meta">{String(filtered.length)} / {String(agent.tasks.length)} 条</span>
        {agent.refreshing ? <span className="toolbar__meta">读取中…</span> : null}
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          compact
          icon="file"
          title={agent.tasks.length === 0 ? '尚无研究任务' : '没有匹配的任务'}
          description={
            agent.tasks.length === 0
              ? '从“新建任务”开始；所有任务受日/月硬预算约束。'
              : '调整搜索词或状态筛选。'
          }
          actions={
            agent.tasks.length === 0 && canCreate ? (
              <Button variant="secondary" icon="plus" onClick={onCreate}>新建研究任务</Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <Table label="研究任务" className="tasks-table">
            <thead>
              <tr>
                <th>任务 / 模型</th>
                <th>状态</th>
                <th>时间</th>
                <th className="num">费用 / 预留</th>
                <th>结论 / 原因</th>
                <th className="row-actions-head">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((task) => {
                const cost = taskCost(task.calls);
                return (
                  <tr key={task.id} onClick={() => void agent.openTask(task.id)}>
                    <td>
                      <button
                        type="button"
                        className="row-link"
                        onClick={(event) => {
                          event.stopPropagation();
                          void agent.openTask(task.id);
                        }}
                      >
                        {task.name}
                      </button>
                      <span className="cell-sub">#{task.id} · {task.provider_id}</span>
                    </td>
                    <td><TaskStatusBadge status={task.status} /></td>
                    <td>
                      <span className="cell-sub">{formatDateTime(task.started_at || task.created_at)}</span>
                      <span className="cell-sub">{taskDuration(task)}</span>
                    </td>
                    <td className="num" title={cost ? '未知费用按最大预留计' : undefined}>
                      {cost ? formatMicro(cost, { currency: status.budget.currency }) : '—'}
                    </td>
                    <td className="cell-reason" title={task.conclusion || task.reason || ''}>
                      {task.conclusion || humanReason(task.reason) || '等待执行'}
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className="row-actions">
                        {['queued', 'running'].includes(task.status) ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            icon="ban"
                            loading={agent.busy === 'cancel:' + task.id}
                            disabled={agent.busy !== null}
                            onClick={async () => {
                              const error = await agent.cancelTask(task.id);
                              if (error) toast.push({ title: '取消失败', description: error.message, tone: 'danger' });
                              else toast.push({ title: '已申请取消', description: '运行中的请求不会被撤销；请查看最终状态。', tone: 'info' });
                            }}
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
                            disabled={agent.busy !== null}
                            onClick={async () => {
                              const error = await agent.retryTask(task.id);
                              if (error) toast.push({ title: '重试失败', description: error.message, tone: 'danger' });
                              else toast.push({ title: '任务已重新排队', tone: 'success' });
                            }}
                          >
                            安全重试
                          </Button>
                        ) : null}
                        {!task.retryable && !['queued', 'running'].includes(task.status) ? (
                          <Icon name="chevron-right" size={14} className="muted" />
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
          <div className="tasks-pagination">
            <div className="tasks-pagination__meta">
              <span>每页最多 20 条 · 读取于 {agent.lastUpdated ? formatClock(agent.lastUpdated) : '—'}</span>
            </div>
            <div className="tasks-pagination__actions">
              <Button size="sm" variant="ghost" icon="chevrons-left" disabled={!agent.pageBefore || agent.busy !== null} onClick={() => void agent.goPage(null)}>
                最新
              </Button>
              <Button size="sm" variant="ghost" iconRight="chevron-right" disabled={!agent.nextBefore || agent.busy !== null} onClick={() => void agent.goPage(agent.nextBefore)}>
                更早
              </Button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}

function TaskDrawer({ agent, status }: { agent: AgentState; status: AgentStatus }) {
  const toast = useToast();
  const detail = agent.detail;
  const currency = status.budget.currency;
  const canCancel = detail ? ['queued', 'running', 'local_running'].includes(detail.status) : false;
  const canRetry = detail?.retryable === true;
  return (
    <Drawer
      open={agent.detailOpen}
      onClose={agent.closeTask}
      eyebrow={detail ? '已保存研究任务 #' + detail.id : '研究任务'}
      title={detail?.request.name ?? '读取任务详情'}
      meta={
        <>
          {detail ? <TaskStatusBadge status={detail.status} /> : null}
          {detail ? <Badge tone="outline">{detail.provider_id}</Badge> : null}
        </>
      }
      footer={
        <>
          <Button size="sm" variant="ghost" icon="refresh" loading={agent.detailLoading} onClick={() => void agent.refreshDetail()}>
            刷新详情
          </Button>
          <span className="drawer__foot-spacer" />
          {canRetry ? (
            <Button
              size="sm"
              variant="secondary"
              icon="retry"
              loading={agent.busy === 'retry:' + (detail?.id ?? '')}
              disabled={agent.busy !== null}
              onClick={async () => {
                if (!detail) return;
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
              loading={agent.busy === 'cancel:' + (detail?.id ?? '')}
              disabled={agent.busy !== null}
              onClick={async () => {
                if (!detail) return;
                const error = await agent.cancelTask(detail.id);
                if (error) toast.push({ title: '取消失败', description: error.message, tone: 'danger' });
                else toast.push({ title: '已申请取消', description: '运行中的 Provider 请求不会被撤销。', tone: 'info' });
              }}
            >
              取消任务
            </Button>
          ) : null}
        </>
      }
    >
      {agent.detailError && detail ? (
        <Callout tone="warning" title="详情刷新失败，显示上次读取记录">
          {agent.detailError.message}
        </Callout>
      ) : null}
      {agent.detailLoading && !detail ? (
        <SkeletonLines lines={6} />
      ) : agent.detailError && !detail ? (
        <EmptyState
          tone="error"
          icon="alert-triangle"
          title="任务详情不可用"
          description={agent.detailError.message}
          code={agent.detailError.code}
          actions={<Button variant="secondary" icon="refresh" onClick={() => void agent.refreshDetail()}>重新读取</Button>}
        />
      ) : detail ? (
        <TaskDetailBody detail={detail} currency={currency} />
      ) : (
        <p className="muted">任务详情尚未加载。</p>
      )}
    </Drawer>
  );
}

function TaskDetailBody({ detail, currency }: { detail: AgentTaskDetail; currency: string }) {
  const result = detail.result;
  return (
    <>
      <div className="drawer__section">
        <h3 className="drawer__section-title">请求</h3>
        <dl className="kv">
          <dt>研究目标</dt><dd>{detail.request.goal}</dd>
          <dt>研究范围</dt><dd>{detail.request.scope}</dd>
          <dt>请求区间</dt><dd>{detail.request.start_day} — {detail.request.end_day}</dd>
          <dt>单任务预算</dt><dd>{detail.request.task_budget_micro ? formatMicro(detail.request.task_budget_micro, { currency }) : '未设置，仍受日/月硬上限'}</dd>
          <dt>创建时间</dt><dd>{formatDateTime(detail.created_at)}</dd>
          <dt>开始 / 完成</dt><dd>{formatDateTime(detail.started_at)} / {formatDateTime(detail.finished_at)}</dd>
          <dt>取消申请</dt><dd>{detail.cancel_requested_at ? formatDateTime(detail.cancel_requested_at) : '—'}</dd>
          <dt>原因</dt><dd>{humanReason(detail.reason)}<TechnicalDetails value={{reason:detail.reason}}/></dd>
        </dl>
      </div>

      <div className="drawer__section">
        <h3 className="drawer__section-title">冻结输入与模型</h3>
        <dl className="kv">
          <dt>输入模式</dt><dd><ModeBadge mode={detail.input.mode}/></dd>
          <dt>实际摘要源日</dt><dd>{detail.input.source_day || '无已发布报告'}</dd>
          <dt>摘要版本</dt><dd className="code-chip">{detail.input.version}</dd>
          <dt>研究范围</dt><dd>原冻结来源范围<TechnicalDetails value={detail.input}/></dd>
          <dt>模型 / 配置</dt><dd>{detail.provider_id} <span className="code-chip">{detail.provider_hash.slice(0, 16)}…</span></dd>
        </dl>
        <p className="drawer-note">详情读取只读取本地已保存记录，不调用模型。</p>
      </div>

      {result && Array.isArray(result.research.evidence) ? (
        <div className="drawer__section">
          <h3 className="drawer__section-title">研究结果</h3>
          <div className="inline-row inline-row--tight result-badges">
            <Badge tone={result.synthetic_provider ? 'warning' : 'accent'}>
              {result.synthetic_provider ? 'FAKE / SYNTHETIC' : '云端文本研究'}
            </Badge>
            <Badge tone="outline">{result.model}</Badge>
            <Badge tone="neutral">{formatDateTime(result.generated_at)}</Badge>
            <Badge tone="outline">{RESEARCH_QUALIFICATION_LABELS[result.qualification] ?? result.qualification}</Badge>
          </div>
          <div className="result-section">
            <h4>可核查假设</h4>
            <p>{result.research.hypothesis}</p>
          </div>
          <div className="result-section">
            <h4>关键依据</h4>
            <ul>{result.research.evidence.map((item, index) => <li key={index}>{item}</li>)}</ul>
          </div>
          <div className="result-section">
            <h4>反证 / 风险</h4>
            <ul>{result.research.risks.map((item, index) => <li key={index}>{item}</li>)}</ul>
          </div>
          <div className="result-section">
            <h4>下一步</h4>
            <ul>{result.research.next_steps.map((item, index) => <li key={index}>{item}</li>)}</ul>
          </div>
          <Callout tone="warning" title="限制">{result.limitations}</Callout>
        </div>
      ) : result ? (
        <div className="drawer__section"><h3 className="drawer__section-title">已保存研究产物</h3><p>本地风险或结构化研究输出；模型自由文本仅为未核验假设。</p><TechnicalDetails value={result}/></div>
      ) : (
        <div className="drawer__section">
          <h3 className="drawer__section-title">研究结果</h3>
          <p className="muted">{detail.artifact===undefined?'尚无已保存研究输出。此详情不会发起推理。':'已保存结构化研究产物，见下方详情。'}</p>
        </div>
      )}

      <div className="drawer__section">
        <h3 className="drawer__section-title">费用与调用记录</h3>
        {detail.artifact !== undefined ? <><p>已保存本地风险或结构化研究输出；模型自由文本仅为未核验假设。</p><TechnicalDetails value={detail.artifact}/></> : null}
        <p className="drawer-note">云端收到用量仍不是最终账单；未知结果保留最大预留，不自动重发。</p>
        {detail.calls.length === 0 ? (
          <p className="muted">尚未预留或发出调用。</p>
        ) : (
          <div className="mini-table-wrap">
            <table className="mini-table call-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>状态</th>
                  <th className="num">最大 / 已核对 / 估算</th>
                  <th>费率版本</th>
                  <th>周期</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                {detail.calls.map((call) => (
                  <tr key={call.id}>
                    <td className="cell-mono">{call.id}</td>
                    <td title={call.state}>{stateLabel(call.state)}</td>
                    <td className="num">
                      {formatMicro(call.maximum_micro)} / {formatMicro(call.settled_micro)} / {formatMicro(call.usage_micro)}
                    </td>
                    <td className="cell-mono">{call.price_version}</td>
                    <td className="cell-mono">{call.day} / {call.month}</td>
                    <td className="cell-reason" title={call.reason || ''}>{humanReason(call.reason)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function UnlockModal({
  open,
  agent,
  onClose,
  onSuccess,
}: {
  open: boolean;
  agent: AgentState;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const loading = agent.busy === 'unlock';

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setErrorCode(null);
    if (!token.trim()) {
      setError('请输入本机 Owner 令牌。');
      return;
    }
    const failure = await agent.unlock(token);
    if (failure) {
      setError(failure.message);
      setErrorCode(failure.code);
      return;
    }
    setToken('');
    onSuccess();
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!loading) onClose();
      }}
      title="解锁本机研究控制"
      description="令牌只保存在当前页面内存，不写入浏览器存储或 URL。"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>取消</Button>
          <Button variant="primary" type="submit" form="agent-unlock-form" loading={loading}>解锁</Button>
        </>
      }
    >
      <form id="agent-unlock-form" onSubmit={submit}>
        <Field
          label="本机 Owner 令牌"
          htmlFor="agent-owner-token"
          hint="从本机 Agent 目录的 owner-token 文件复制。刷新页面后需要重新解锁。"
          error={error}
        >
          <TextInput
            id="agent-owner-token"
            type="password"
            autoComplete="off"
            spellCheck={false}
            minLength={32}
            maxLength={128}
            value={token}
            onChange={(event) => setToken(event.target.value)}
            required
            data-autofocus
          />
        </Field>
        {errorCode ? <p className="field__error">错误代码：{errorCode}</p> : null}
        {error ? <Callout tone="danger" className="form-error" role="alert">{error}</Callout> : null}
      </form>
    </Modal>
  );
}

function CreateFooter({
  agent,
  canCreate,
  onCancel,
}: {
  agent: AgentState;
  canCreate: boolean;
  onCancel: () => void;
}) {
  return (
    <>
      <span className="modal__foot-note">提交只入队；取消不撤销已提交的计费请求。</span>
      <Button variant="ghost" type="button" onClick={onCancel} disabled={agent.busy === 'create'}>
        取消
      </Button>
      <Button
        variant="primary"
        type="submit"
        form="agent-task-form"
        loading={agent.busy === 'create'}
        disabled={!canCreate}
      >
        提交研究任务
      </Button>
    </>
  );
}

function CreateTaskForm({
  agent,
  canCreate,
  disabledReason,
  onDone,
}: {
  agent: AgentState;
  canCreate: boolean;
  disabledReason: string;
  onDone: (id: string) => void;
}) {
  const defaults = defaultRange(agent.status?.input.source_day);
  const [name, setName] = useState('');
  const [goal, setGoal] = useState('');
  const [scope, setScope] = useState('当前已发布的 Paper 摘要');
  const [startDay, setStartDay] = useState(defaults.start);
  const [endDay, setEndDay] = useState(defaults.end);
  const [budget, setBudget] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [formCode, setFormCode] = useState<string | null>(null);
  const requestKey=useRef(crypto.randomUUID().replaceAll('-',''));
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
    if (budget.trim() && !/^[0-9]+$/.test(budget.trim())) next.budget = '单任务预算必须为正整数字符串。';
    else if (budget.trim() && BigInt(budget.trim()) <= 0n) next.budget = '单任务预算必须大于 0。';
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setFormError(null);
    setFormCode(null);
    const result = await agent.createTask({
      request_key:requestKey.current,
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
    if (result.id) {requestKey.current=crypto.randomUUID().replaceAll('-','');onDone(result.id);}
  };

  return (
    <form id="agent-task-form" className="agent-task-form" onSubmit={submit}>
      {!canCreate ? (
        <Callout tone="warning" title="当前不能创建任务">{disabledReason}</Callout>
      ) : null}
      <div className="form-grid">
        <Field label="任务名称" htmlFor="task-name" hint="最多 40 个字符。" error={errors.name} className="form-grid__full">
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
        <Field label="证券 / 研究范围" htmlFor="task-scope" hint="只允许提交到已发布的摘要与本次课题。" error={errors.scope}>
          <TextInput
            id="task-scope"
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            maxLength={100}
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.scope)}
          />
        </Field>
        <Field label="单任务预算 micro（可选）" htmlFor="task-budget" hint="留空仍受日/月硬上限。" error={errors.budget}>
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
        <Field label="开始日期" htmlFor="task-start" hint="研究请求区间，不保证已有该区间完整数据。" error={errors.start}>
          <TextInput
            id="task-start"
            type="date"
            value={startDay}
            onChange={(event) => setStartDay(event.target.value)}
            disabled={!canCreate || loading}
            aria-invalid={Boolean(errors.start)}
          />
        </Field>
        <Field label="结束日期" htmlFor="task-end" hint="当前摘要源日只作为默认值。" error={errors.end}>
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
        创建任务可能产生费用；取消运行中的任务不会撤销已提交的 Provider 请求。未知费用会保留最大预留，系统不会自动重发。
      </Callout>
      {formError ? (
        <Callout tone="danger" title="提交失败" className="form-error" role="alert">
          {formError}
          {formCode ? <span className="field__error"> · {formCode}</span> : null}
        </Callout>
      ) : null}
    </form>
  );
}
