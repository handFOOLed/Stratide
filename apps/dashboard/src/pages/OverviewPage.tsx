import { useEffect, useMemo, useState } from 'react';
import type { ReactNode, Ref } from 'react';
import { PageHeader, PageMeta, MetaSep } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { EmptyState } from '../components/ui/EmptyState';
import { Pager } from '../components/ui/Pager';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Table } from '../components/ui/Table';
import { EquityChart } from '../components/ui/Chart';
import { Skeleton } from '../components/ui/Skeleton';
import { StatusInline, StatusLine } from '../components/ui/StatusBadge';
import { Checklist } from '../components/ui/Checklist';
import type { ChecklistItem } from '../components/ui/Checklist';
import { HealthBar } from '../components/ui/HealthBar';
import type { HealthBarItem } from '../components/ui/HealthBar';
import { Diagnostics } from '../components/ui/Diagnostics';
import { InfoHint } from '../components/ui/InfoHint';
import { PaperPortfolioPanel } from '../components/domain/PaperPortfolioPanel';
import { FillDrawer } from '../components/domain/FillDrawer';
import { PositionDrawer } from '../components/domain/PositionDrawer';
import { PaperErrorPanel } from '../components/domain/PaperErrorPanel';
import { SideBadge } from '../components/domain/Badges';
import { useSelection } from '../lib/hooks';
import {
  countText,
  formatBps,
  formatCny,
  formatDateTime,
  formatDay,
  parseInteger,
  rangeRows,
  signClass,
} from '../lib/format';
import { RANGE_VALUES, readPreference, writePreference } from '../lib/storage';
import type { RangeValue } from '../lib/storage';
import { checklistProgress, checklistVisible } from '../lib/checklist';
import { backfillReadFailure } from '../lib/runtimeRefresh';
import { navigate } from '../lib/route';
import {
  dataStatusView,
  dependencyStatusView,
  EVIDENCE_DIAGNOSTIC_LABEL,
  humanReasonText,
  MODE_DIAGNOSTIC_LABEL,
  overallSystemStatus,
  protectionStatusView,
  researchStatusView,
} from '../lib/status';
import type { StatusView } from '../lib/status';
import { EMPTY, HEALTH_BAR } from '../lib/copy';
import type { ApiError } from '../lib/api';
import type { Fill, Position } from '../lib/types';
import type { PaperDataState } from '../state/usePaperData';
import type { HealthState } from '../state/useHealth';
import type { RuntimeState } from '../state/useRuntime';
import type { AgentState } from '../state/useAgent';

const PAGE_SIZE = 5;

const RANGE_OPTIONS: Array<{ value: RangeValue; label: string }> = [
  { value: '7D', label: '7D' },
  { value: '30D', label: '30D' },
  { value: '90D', label: '90D' },
  { value: '1Y', label: '1Y' },
  { value: 'ALL', label: '全部' },
];

function failureText(error: ApiError): string {
  const mapped = humanReasonText(error.code);
  if (mapped !== null) return mapped;
  return error.message === '—' ? '原因未记录' : error.message;
}

function errorDiagnostic(error: ApiError | null): string {
  return error === null ? '无' : error.code + ' · ' + error.message;
}

function buildHealthItems(input: {
  health: HealthState;
  runtime: RuntimeState;
  agent: AgentState;
  accountValue: ReactNode;
  dataStatus: StatusView;
  dataDate: string | null;
}): HealthBarItem[] {
  const runningTasks = input.agent.tasks.filter(
    (task) => task.status === 'running' || task.status === 'local_running',
  ).length;
  const overall = overallSystemStatus({
    serviceOnline: input.health.error === null && input.health.data !== null && input.health.data.service === 'online',
    healthChecking: input.health.checking,
    healthErrorCode: input.health.error === null ? null : input.health.error.code,
    runtime: input.runtime.status,
    runtimeErrorCode: input.runtime.error === null ? null : input.runtime.error.code,
  });
  const latestTask = input.agent.tasks.length === 0 ? null : input.agent.tasks[0];
  const research = researchStatusView({
    ready: input.agent.phase === 'ready' && input.agent.status !== null,
    paused: input.agent.status !== null && input.agent.status.paused,
    status: input.agent.status,
    errorCode: input.agent.error === null ? null : input.agent.error.code,
    runningTasks,
    latestTaskStatus: latestTask === null ? null : latestTask.status,
    latestTaskReason: latestTask === null ? null : latestTask.reason,
  });
  return [
    { id: 'account', label: HEALTH_BAR.account, value: input.accountValue },
    {
      id: 'data',
      label: (
        <>
          {HEALTH_BAR.dataDate}
          <InfoHint label="数据日期说明">数据日期是最近一个已有行情的交易日；每个交易日收盘后更新，不是实时行情。</InfoHint>
        </>
      ),
      value: input.dataDate,
      status: input.dataStatus,
    },
    { id: 'system', label: HEALTH_BAR.system, value: null, status: overall.status, href: '#settings/runtime' },
    { id: 'research', label: HEALTH_BAR.research, value: null, status: research, href: '#agents' },
  ];
}

function ChecklistAction({
  testId,
  label,
  onClick,
}: {
  testId: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <Button size="sm" variant="ghost" iconRight="arrow-right" data-testid={testId} onClick={onClick}>
      {label}
    </Button>
  );
}

function OverviewSkeleton() {
  return (
    <div className="overview-skeleton" aria-hidden="true">
      <Skeleton className="overview-skeleton__bar" />
      <Skeleton className="overview-skeleton__checklist" />
      <div className="overview-skeleton__row">
        <Skeleton className="skeleton-card skeleton-card--tall" />
        <Skeleton className="skeleton-card skeleton-card--tall" />
      </div>
      <div className="overview-skeleton__row">
        <Skeleton className="skeleton-card" />
        <Skeleton className="skeleton-card" />
      </div>
    </div>
  );
}

export function OverviewPage({
  paper,
  health,
  runtime,
  agent,
  titleRef,
}: {
  paper: PaperDataState;
  health: HealthState;
  runtime: RuntimeState;
  agent: AgentState;
  titleRef?: Ref<HTMLHeadingElement>;
}) {
  const [range, setRange] = useState<RangeValue>(() => readPreference('range', '30D', RANGE_VALUES));
  const [positionPage, setPositionPage] = useState(0);
  const [fillPage, setFillPage] = useState(0);
  const checklist = checklistProgress(runtime, agent);
  useEffect(() => {
    if (checklist.knownComplete) writePreference('checklist-dismissed', '1');
    else if (checklist.knownIncomplete) writePreference('checklist-dismissed', '0');
  }, [checklist.knownComplete, checklist.knownIncomplete]);
  const positions = useSelection<Position>();
  const fills = useSelection<Fill>();

  const bundle = paper.bundle;
  const meta = paper.meta;

  const chartRows = useMemo(
    () => (bundle === null ? [] : rangeRows(bundle.equity, range)),
    [bundle, range],
  );
  const sortedPositions = useMemo(
    () => (bundle === null ? [] : [...bundle.positions].sort((a, b) => a.instrument.code.localeCompare(b.instrument.code))),
    [bundle],
  );
  const recentFills = useMemo(() => {
    if (bundle === null) return [];
    const pageCount = Math.max(1, Math.ceil(bundle.fills.length / PAGE_SIZE));
    const currentPage = Math.min(fillPage, pageCount - 1);
    return [...bundle.fills].reverse().slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);
  }, [bundle, fillPage]);
  const totalValuedDays = useMemo(
    () => (bundle === null ? 0 : bundle.equity.filter((row) => parseInteger(row.nav_fen) !== null).length),
    [bundle],
  );
  const navTopFen = useMemo(() => {
    let top = bundle === null ? null : parseInteger(bundle.account.nav_fen);
    for (const row of chartRows) {
      const value = parseInteger(row.nav_fen);
      if (value !== null && (top === null || value > top)) top = value;
    }
    return top;
  }, [bundle, chartRows]);

  const dataDate = meta === null || meta.last_day === null ? null : formatDay(meta.last_day);
  const earlierValuationDay =
    meta !== null && meta.as_of !== null && meta.last_day !== null && meta.as_of < meta.last_day
      ? formatDay(meta.as_of)
      : null;
  const updatedAt = paper.loadedAt === null ? null : formatDateTime(new Date(paper.loadedAt).toISOString());

  const header = (
    <PageHeader
      title="总览"
      titleRef={titleRef}
      side={
        meta === null ? null : (
          <PageMeta>
            <span data-testid="overview-data-date">数据日期 {dataDate ?? '未记录'}</span>
            {earlierValuationDay === null ? null : (
              <>
                <MetaSep />
                <span data-testid="overview-as-of">最后有效估值日 {earlierValuationDay}</span>
              </>
            )}
            {updatedAt === null ? null : (
              <>
                <MetaSep />
                <span data-testid="overview-updated-at">更新于 {updatedAt}</span>
              </>
            )}
          </PageMeta>
        )
      }
    />
  );

  if (paper.phase === 'loading') {
    return (
      <div className="overview-page" data-testid="overview-page">
        {header}
        <div role="status" className="sr-only">正在读取模拟账户数据</div>
        <OverviewSkeleton />
      </div>
    );
  }

  if (paper.phase === 'error' && paper.error !== null) {
    const failure = paper.error;
    const failedDataStatus = dataStatusView({
      meta: null,
      errorCode: failure.code,
      errorMessage: failure.message,
      gaps: 0,
    });
    const unconfigured = failure.code === 'NO_SNAPSHOT' || failure.code === 'CURRENT_PAPER_ACCOUNT_UNCONFIGURED';
    return (
      <div className="overview-page" data-testid="overview-page">
        {header}
        <HealthBar
          items={buildHealthItems({
            health,
            runtime,
            agent,
            accountValue: unconfigured ? '未设置' : '—',
            dataStatus: failedDataStatus,
            dataDate: null,
          })}
        />
        <PaperErrorPanel error={failure} onRetry={paper.refresh} />
      </div>
    );
  }

  if (bundle === null || meta === null) return null;

  const account = bundle.account;
  const risk = account.risk;
  // risk 为 null 表示这份数据没有附带交易保护记录，不能当成“未触发”。
  const accountFreezes = risk === null || risk.account_freezes === null ? 0 : risk.account_freezes.length;
  const strategyFreezes = risk === null || risk.strategy_freezes === null ? 0 : risk.strategy_freezes.length;
  const totalFreezes = accountFreezes + strategyFreezes;
  const dataMissing = account.valuation_error !== null;
  const protection = protectionStatusView({ risk, dataMissing });
  const protectionExpanded = totalFreezes > 0 || dataMissing;

  const dataStatus = dataStatusView({
    meta,
    errorCode: paper.error === null ? null : paper.error.code,
    errorMessage: paper.error === null ? null : paper.error.message,
    gaps: meta.gaps.length,
  });

  const portfolio = account.portfolio === undefined ? null : account.portfolio;
  const setupDone = runtime.status !== null && runtime.status.setup_complete;
  const dependencies = runtime.status === null ? null : runtime.status.dependencies;
  const tushareDependency = dependencies === null ? null : dependencies.tushare_credential;
  const marketEodDependency = dependencies === null ? null : dependencies.market_eod;
  const tushareView =
    tushareDependency === null
      ? null
      : dependencyStatusView('tushare_credential', tushareDependency.state, tushareDependency.reason ?? null, tushareDependency.note ?? null);
  const marketEodView =
    marketEodDependency === null
      ? null
      : dependencyStatusView('market_eod', marketEodDependency.state, marketEodDependency.reason ?? null, marketEodDependency.note ?? null);
  const tushareDone = tushareView !== null && tushareView.kind === 'ok';
  const marketEodDone = marketEodView !== null && marketEodView.kind === 'ok';
  const market = runtime.market;
  const backfillDone = market !== null && market.backfillComplete;
  const backfillDescription =
    market === null
      ? runtime.error === null
        ? '正在读取历史行情补录进度'
        : '无法读取历史行情补录进度'
      : market.backfillComplete
        ? '历史行情已就绪（' + String(market.sessionsReady) + ' 个交易日）'
        : market.backfillRunning
          ? market.remaining === null
            ? '历史行情补录已开始'
            : '历史行情补录中：待补齐 ' + String(market.remaining) + ' 个交易日'
          : market.statusError !== null
            ? backfillReadFailure(market.statusError).hint + ' 诊断码 ' + market.statusError
            : !market.statusKnown
              ? '正在读取历史行情补录进度'
              : market.sessionsReady > 0
                ? '历史行情补录尚未完成：待补齐 ' + String(market.remaining ?? market.gaps ?? 0) + ' 个交易日'
                : '历史行情补录尚未开始（目标 ' + String(market.targetSessions) + ' 个交易日）';
  const researchConfigured =
    agent.status !== null && agent.status.default_model !== null && agent.status.budget.state === 'configured';

  const runtimeAction = (testId: string) => (
    <ChecklistAction
      testId={testId}
      label="去设置"
      onClick={() => navigate({ page: 'settings', section: 'runtime' })}
    />
  );

  const checklistItems: ChecklistItem[] = [
    {
      id: 'setup',
      title: '完成首次设置',
      description:
        runtime.status === null
          ? runtime.error === null
            ? '正在读取本机设置'
            : '无法读取本机设置：' + failureText(runtime.error)
          : setupDone
            ? '首次设置已经完成'
            : '在“设置 → 系统与诊断”中完成首次设置后会标记为已完成',
      done: setupDone,
      action: runtimeAction('checklist-action-setup'),
    },
    {
      id: 'tushare',
      title: '配置行情数据源',
      description:
        tushareView === null
          ? '正在读取数据源配置'
          : tushareDone
            ? 'Tushare 数据源已经配置'
            : (tushareView.reason ?? '填写 Tushare 访问令牌后即可获取行情'),
      done: tushareDone,
      action: runtimeAction('checklist-action-tushare'),
    },
    {
      id: 'market-eod',
      title: '启用行情自动采集',
      description:
        marketEodView === null
          ? '正在读取行情采集状态'
          : marketEodDone
            ? '每个交易日收盘后会自动采集行情'
            : (marketEodView.reason ?? '在“设置 → 系统与诊断”中初始化行情自动采集'),
      done: marketEodDone,
      action: runtimeAction('checklist-action-market'),
    },
    {
      id: 'history-backfill',
      title: '完成历史行情补录',
      description: backfillDescription,
      done: backfillDone,
      action: runtimeAction('checklist-action-backfill'),
    },
    {
      id: 'research',
      title: '设置 AI 研究',
      description:
        agent.status === null
          ? agent.error === null
            ? '正在读取 AI 研究设置'
            : '无法读取 AI 研究设置：' + failureText(agent.error)
          : researchConfigured
            ? '已经选择默认研究模型并设置研究预算'
            : agent.status.default_model === null
              ? '还没有选择默认研究模型'
              : '还没有设置研究预算',
      done: researchConfigured,
      action: (
        <ChecklistAction
          testId="checklist-action-research"
          label="前往 AI 研究"
          onClick={() => navigate({ page: 'agents' })}
        />
      ),
    },
  ];
  const checklistDismissed = readPreference('checklist-dismissed', '0', ['0', '1'] as const) === '1';
  const showChecklist = checklistVisible(checklist, checklistDismissed);

  const positionPageCount = Math.max(1, Math.ceil(sortedPositions.length / PAGE_SIZE));
  const currentPositionPage = Math.min(positionPage, positionPageCount - 1);
  const visiblePositions = sortedPositions.slice(
    currentPositionPage * PAGE_SIZE,
    currentPositionPage * PAGE_SIZE + PAGE_SIZE,
  );
  const fillPageCount = Math.max(1, Math.ceil(bundle.fills.length / PAGE_SIZE));
  const currentFillPage = Math.min(fillPage, fillPageCount - 1);
  const listsEmpty = sortedPositions.length === 0 && bundle.fills.length === 0;
  const chartMissingDays = chartRows.filter((row) => parseInteger(row.nav_fen) === null).length;

  const onRange = (next: RangeValue) => {
    setRange(next);
    writePreference('range', next);
  };

  const diagnosticsItems = [
    { label: '账户标识', value: account.account_id },
    { label: '数据模式', value: MODE_DIAGNOSTIC_LABEL[meta.mode] ?? meta.mode },
    { label: '证据等级', value: EVIDENCE_DIAGNOSTIC_LABEL[meta.evidence_class] ?? meta.evidence_class },
    { label: '数据来源', value: meta.source },
    { label: '来源版本', value: meta.source_version },
    { label: '数据日期', value: formatDay(meta.last_day) },
    { label: '数据开始', value: formatDay(meta.first_day) },
    { label: '最后有效数据', value: formatDateTime(meta.last_valid_valuation_at) },
    { label: '快照标识', value: meta.snapshot_id },
    { label: '账本头', value: meta.ledger_head },
    { label: '报告摘要', value: meta.report_sha256 },
    { label: '输入摘要', value: meta.input_sha256 },
    { label: '数据缺口', value: countText(meta.gaps.length, '条') },
    { label: '校验状态', value: meta.validation },
    { label: '估值错误', value: account.valuation_error ?? '无' },
    { label: '交易保护原始记录', value: risk === null ? '无' : JSON.stringify(risk) },
    {
      label: '模拟交易规则原始记录',
      value: portfolio === null ? '无' : JSON.stringify(portfolio),
    },
    { label: '原始读取错误', value: errorDiagnostic(paper.error) },
    { label: '健康检查错误', value: errorDiagnostic(health.error) },
    { label: '后台状态错误', value: errorDiagnostic(runtime.error) },
    { label: 'AI 研究状态错误', value: errorDiagnostic(agent.error) },
  ];

  return (
    <div className="overview-page" data-testid="overview-page">
      {header}

      <HealthBar
        items={buildHealthItems({
          health,
          runtime,
          agent,
          accountValue: dataMissing ? '数据缺失' : formatCny(account.nav_fen),
          dataStatus,
          dataDate,
        })}
      />

      {paper.stale && paper.error !== null ? (
        <Callout tone="warning" title="最近一次更新没有成功，以下是上次成功读取的数据" className="overview-stale" role="alert">
          <div className="overview-stale__row">
            <span>{failureText(paper.error)}</span>
            <Button size="sm" variant="ghost" icon="refresh" data-testid="stale-retry" onClick={paper.refresh}>
              重新读取
            </Button>
          </div>
        </Callout>
      ) : null}

      {showChecklist ? (
        <Checklist items={checklistItems} open onToggle={() => undefined} />
      ) : null}

      {protectionExpanded ? (
        <Card className="overview-protection-card" data-testid="protection-alert">
          <CardBody>
            <div className="overview-protection-card__head">
              <StatusLine status={protection} />
              <Button
                size="sm"
                variant="ghost"
                iconRight="arrow-right"
                data-testid="risk-diagnostics-link"
                onClick={() => navigate({ page: 'settings', section: 'runtime' })}
              >
                查看诊断
              </Button>
            </div>
            {totalFreezes > 0 ? (
              <div className="overview-protection-card__counts">
                <span>
                  账户限制 <strong>{countText(accountFreezes, '项')}</strong>
                </span>
                <span>
                  策略限制 <strong>{countText(strategyFreezes, '项')}</strong>
                </span>
              </div>
            ) : null}
            {totalFreezes > 0 ? (
              <p className="overview-protection-card__hint">触发后需要人工处理，不会自动恢复。</p>
            ) : null}
            {dataMissing ? (
              <p className="overview-protection-card__data">数据缺失，暂无法可靠估值；数据恢复前不展示资产与盈亏。</p>
            ) : null}
          </CardBody>
        </Card>
      ) : (
        <div className="overview-protection-line" data-testid="protection-normal">
          <StatusInline status={protection} />
          <InfoHint label="交易保护说明">触发限制时只阻止新的模拟下单，不会自动平仓，也不会自动恢复。</InfoHint>
          {protection.kind === 'ok' || protection.reason === undefined ? null : (
            <span className="overview-protection-line__reason">{protection.reason}</span>
          )}
        </div>
      )}

      <div className="overview-main">
        <Card className="overview-asset-card">
          <CardBody>
            <div className="overview-asset-main">
              <div className="overview-asset-total">
                <h2 className="card__title">
                  总资产
                  <InfoHint label="总资产说明">现金与持仓市值的合计，每个交易日收盘后更新。</InfoHint>
                </h2>
                <div className="overview-asset-value numeric" data-testid="nav-value">
                  {formatCny(account.nav_fen)}
                </div>
              </div>
              <div className="overview-asset-deltas">
                <div className="overview-asset-delta">
                  <span className="overview-asset-delta__label">今日盈亏</span>
                  <span
                    className={'overview-asset-delta__value numeric ' + signClass(account.session_pnl_fen)}
                    data-testid="session-pnl"
                  >
                    {formatCny(account.session_pnl_fen, { signed: true })}
                  </span>
                </div>
                <div className="overview-asset-delta">
                  <span className="overview-asset-delta__label">累计收益</span>
                  <span
                    className={'overview-asset-delta__value numeric ' + signClass(account.cumulative_pnl_fen)}
                    data-testid="cumulative-pnl"
                  >
                    {formatCny(account.cumulative_pnl_fen, { signed: true })}
                  </span>
                  <span className={'overview-asset-delta__sub numeric ' + signClass(account.total_return_bps)}>
                    {formatBps(account.total_return_bps, { signed: true })}
                  </span>
                </div>
              </div>
            </div>
            <dl className="overview-asset-secondary">
              <div>
                <dt>可用资金</dt>
                <dd>{formatCny(account.available_cash_fen)}</dd>
              </div>
              <div>
                <dt>挂单冻结资金</dt>
                <dd>{formatCny(account.reserved_cash_fen)}</dd>
              </div>
              <div>
                <dt>累计费用</dt>
                <dd>{formatCny(account.total_fee_fen)}</dd>
              </div>
              <div>
                <dt>最大日回撤</dt>
                <dd>{formatBps(account.max_daily_observation_drawdown_bps)}</dd>
              </div>
            </dl>
          </CardBody>
        </Card>

        <Card className="overview-chart-card">
          <CardHead
            title="资产曲线"
            subtitle={
              totalValuedDays >= 2 && chartMissingDays > 0
                ? '有 ' + String(chartMissingDays) + ' 天没有可用数据，曲线会在缺口处断开'
                : undefined
            }
            actions={
              totalValuedDays >= 2 ? (
                <SegmentedControl
                  label="图表时间范围"
                  options={RANGE_OPTIONS}
                  value={range}
                  onChange={onRange}
                  compact
                />
              ) : undefined
            }
          />
          <div className="overview-chart-body" data-testid="equity-chart">
            {totalValuedDays >= 2 ? (
              <EquityChart
                rows={chartRows}
                metric="nav"
                label="模拟账户资产曲线"
                navTopFen={navTopFen}
                baselineFen={parseInteger(account.initial_nav_fen)}
              />
            ) : (
              <div className="overview-chart-empty">
                <EmptyState compact icon="chart" title={EMPTY.chartTitle} description={EMPTY.chartBody} />
              </div>
            )}
          </div>
        </Card>
      </div>

      {listsEmpty ? (
        <Card className="overview-combined-empty" data-testid="overview-combined-empty">
          <EmptyState
            compact
            icon="wallet"
            title="还没有持仓和成交"
            description="通过交易保护后，系统会按次日开盘价模拟成交；结果会显示在这里。"
          />
        </Card>
      ) : (
        <div className="overview-lists">
          <Card className="overview-list-card" data-testid="positions-card">
            <CardHead title="当前持仓" subtitle={countText(sortedPositions.length, '只')} />
            {sortedPositions.length === 0 ? (
              <CardBody>
                <EmptyState compact icon="wallet" title={EMPTY.positionsTitle} description={EMPTY.positionsBody} />
              </CardBody>
            ) : (
              <>
                <Table label="当前持仓">
                  <thead>
                    <tr>
                      <th>证券</th>
                      <th className="num">持有</th>
                      <th className="num">市值</th>
                      <th className="num">浮动盈亏</th>
                      <th className="num">可卖</th>
                      <th aria-label="详情" />
                    </tr>
                  </thead>
                  <tbody>
                    {visiblePositions.map((position) => (
                      <tr
                        key={position.instrument.code}
                        data-testid="position-row"
                        onClick={() => positions.select(position)}
                      >
                        <td>
                          <button
                            type="button"
                            className="row-link"
                            onClick={(event) => {
                              event.stopPropagation();
                              positions.select(position);
                            }}
                          >
                            {position.instrument.code}
                          </button>
                        </td>
                        <td className="num">{countText(position.quantity, '股')}</td>
                        <td className="num">{formatCny(position.market_value_fen)}</td>
                        <td className={'num ' + signClass(position.unrealized_pnl_fen)}>
                          {formatCny(position.unrealized_pnl_fen, { signed: true })}
                        </td>
                        <td className="num">{countText(position.sellable_shares, '股')}</td>
                        <td className="row-action-cell" aria-hidden="true">
                          <span className="row-chevron">›</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                {positionPageCount > 1 ? (
                  <div className="card__foot overview-list-foot">
                    <span className="pager__count">{countText(sortedPositions.length, '只')}</span>
                    <Pager
                      page={currentPositionPage + 1}
                      pageCount={positionPageCount}
                      onPage={(next) => setPositionPage(next - 1)}
                      label="持仓分页"
                    />
                  </div>
                ) : null}
              </>
            )}
          </Card>

          <Card className="overview-list-card" data-testid="fills-card">
            <CardHead title="最近成交" subtitle={countText(bundle.fills.length, '笔')} />
            {bundle.fills.length === 0 ? (
              <CardBody>
                <EmptyState compact icon="history" title={EMPTY.fillsTitle} description={EMPTY.fillsBody} />
              </CardBody>
            ) : (
              <>
                <Table label="最近模拟成交" className="overview-fills-table">
                  <thead>
                    <tr>
                      <th>日期</th>
                      <th>证券</th>
                      <th>方向</th>
                      <th className="num">数量</th>
                      <th className="num">价格</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentFills.map((fill) => (
                      <tr key={fill.fill_id} data-testid="fill-row" onClick={() => fills.select(fill)}>
                        <td>
                          <button
                            type="button"
                            className="row-link"
                            onClick={(event) => {
                              event.stopPropagation();
                              fills.select(fill);
                            }}
                          >
                            {formatDay(fill.day)}
                          </button>
                        </td>
                        <td>{fill.instrument.code}</td>
                        <td>
                          <SideBadge side={fill.side} />
                        </td>
                        <td className="num">{countText(fill.quantity, '股')}</td>
                        <td className="num">{formatCny(fill.price_fen)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
                {fillPageCount > 1 ? (
                  <div className="card__foot overview-list-foot">
                    <span className="pager__count">{countText(bundle.fills.length, '笔')}</span>
                    <Pager
                      page={currentFillPage + 1}
                      pageCount={fillPageCount}
                      onPage={(next) => setFillPage(next - 1)}
                      label="成交分页"
                    />
                  </div>
                ) : null}
              </>
            )}
          </Card>
        </div>
      )}

      <PaperPortfolioPanel portfolio={portfolio} orders={bundle.orders} />

      <div className="overview-diagnostics" data-testid="overview-diagnostics">
        <Diagnostics
          items={diagnosticsItems}
          data={{
            meta,
            account: {
              account_id: account.account_id,
              day: account.day,
              nav_fen: account.nav_fen,
              valuation_error: account.valuation_error,
              initial_nav_fen: account.initial_nav_fen,
            },
            risk,
            deployment: account.deployment,
            portfolio: account.portfolio,
            errors: {
              paper: paper.error,
              health: health.error,
              runtime: runtime.error,
              research: agent.error,
            },
          }}
        />
      </div>

      <PositionDrawer
        position={positions.item}
        open={positions.open}
        fills={bundle.fills}
        meta={meta}
        onClose={positions.close}
      />
      <FillDrawer fill={fills.item} open={fills.open} orders={bundle.orders} meta={meta} onClose={fills.close} />
    </div>
  );
}
