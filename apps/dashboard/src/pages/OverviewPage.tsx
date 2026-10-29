import { useMemo, useState } from 'react';
import type { Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { EmptyState } from '../components/ui/EmptyState';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Table } from '../components/ui/Table';
import { EquityChart } from '../components/ui/Chart';
import { Skeleton } from '../components/ui/Skeleton';
import { FillDrawer } from '../components/domain/FillDrawer';
import { PositionDrawer } from '../components/domain/PositionDrawer';
import { PaperErrorPanel } from '../components/domain/PaperErrorPanel';
import { EvidenceBadge, ModeBadge, SideBadge } from '../components/domain/Badges';
import { modeInfo } from '../lib/labels';
import { FreshnessNote } from '../components/layout/PageFooter';
import { useSelection } from '../lib/hooks';
import {
  formatBps,
  formatCny,
  formatDateTime,
  formatDay,
  formatShares,
  instrumentLabel,
  parseInteger,
  signClass,
} from '../lib/format';
import { RANGE_VALUES, METRIC_VALUES, readPreference, writePreference } from '../lib/storage';
import type { MetricValue, RangeValue } from '../lib/storage';
import { rangeRows } from '../lib/format';
import type { Fill, Position } from '../lib/types';
import type { PaperDataState } from '../state/usePaperData';

const RANGE_OPTIONS: Array<{ value: RangeValue; label: string }> = [
  { value: '7D', label: '7D' },
  { value: '30D', label: '30D' },
  { value: '90D', label: '90D' },
  { value: '1Y', label: '1Y' },
  { value: 'ALL', label: '全部' },
];

const METRIC_OPTIONS: Array<{ value: MetricValue; label: string }> = [
  { value: 'nav', label: '净值' },
  { value: 'pnl', label: '累计盈亏' },
  { value: 'return', label: '收益率' },
];

function OverviewSkeleton() {
  return (
    <div className="grid overview-grid" aria-hidden="true">
      <div className="col-8"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
      <div className="col-4"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
      <div className="col-12"><Skeleton className="skeleton-card skeleton-card--tall" /></div>
      <div className="col-7"><Skeleton className="skeleton-card" /></div>
      <div className="col-5"><Skeleton className="skeleton-card" /></div>
    </div>
  );
}

export function OverviewPage({ paper, titleRef }: { paper: PaperDataState; titleRef?: Ref<HTMLHeadingElement> }) {
  const [range, setRange] = useState<RangeValue>(() => readPreference('range', '30D', RANGE_VALUES));
  const [metric, setMetric] = useState<MetricValue>(() => readPreference('metric', 'nav', METRIC_VALUES));
  const positions = useSelection<Position>();
  const fills = useSelection<Fill>();

  const bundle = paper.bundle;
  const meta = paper.meta;

  const chartRows = useMemo(
    () => (bundle ? rangeRows(bundle.equity, range) : []),
    [bundle, range],
  );
  const recentFills = useMemo(
    () => (bundle ? [...bundle.fills].reverse().slice(0, 5) : []),
    [bundle],
  );
  const sortedPositions = useMemo(
    () => (bundle ? [...bundle.positions].sort((a, b) => a.instrument.code.localeCompare(b.instrument.code)) : []),
    [bundle],
  );

  const onRange = (next: RangeValue) => {
    setRange(next);
    writePreference('range', next);
  };
  const onMetric = (next: MetricValue) => {
    setMetric(next);
    writePreference('metric', next);
  };

  const header = (
    <PageHeader
      eyebrow="Paper account"
      title="账户总览"
      description="一处查看账户净值、现金、持仓与风险状态。数据来自启动时固定的已发布快照，不是实时行情。"
      titleRef={titleRef}
      side={
        meta ? (
          <>
            <ModeBadge mode={meta.mode} />
            <Badge tone="outline">只读快照</Badge>
            <span className="page-meta"><FreshnessNote loadedAt={paper.loadedAt} /></span>
          </>
        ) : null
      }
    />
  );

  if (paper.phase === 'loading') {
    return (
      <>
        {header}
        <div role="status" className="sr-only">正在加载账户数据</div>
        <OverviewSkeleton />
      </>
    );
  }

  if (paper.phase === 'error' && !bundle) {
    return (
      <>
        {header}
        <PaperErrorPanel
          error={paper.error ?? { code: 'UNKNOWN', message: '未知错误', status: 0 }}
          onRetry={paper.refresh}
        />
      </>
    );
  }

  if (!bundle || !meta) return null;

  const account = bundle.account;
  const risk = account.risk;
  const accountFreezes = risk?.account_freezes?.length ?? 0;
  const strategyFreezes = risk?.strategy_freezes?.length ?? 0;
  const totalFreezes = accountFreezes + strategyFreezes;
  const missingValuations = bundle.equity.filter((row) => parseInteger(row.nav_fen) === null).length;
  const validValuations = bundle.equity.length - missingValuations;
  const hasValuationError = Boolean(account.valuation_error);
  const navClass = signClass(account.session_pnl_fen);

  const content = (
    <>
      {paper.stale && paper.error ? (
        <Callout
          tone="warning"
          title="最近一次读取失败，以下为上次成功读取的快照"
          className="stale-banner"
        >
          <div className="stale-banner__row">
            <span>{paper.error.message}</span>
            <Button size="sm" variant="ghost" icon="refresh" onClick={paper.refresh}>重新读取</Button>
          </div>
        </Callout>
      ) : null}

      {totalFreezes > 0 ? (
        <Callout tone="danger" title={'此快照记录了 ' + String(totalFreezes) + ' 项风控锁'} className="risk-banner">
          账户锁 {accountFreezes} 项、策略锁 {strategyFreezes} 项。本页只展示原报告状态；服务可达不代表风控已恢复，也不代表锁已解除。
        </Callout>
      ) : null}

      <div className="grid overview-grid">
        <div className="col-8">
          <Card className="hero-card">
            <div className="hero-top">
              <div className="hero-main">
                <div className="hero-label">
                  账户净值 <span className="hero-currency">CNY</span>
                </div>
                <div className="hero-value numeric" data-testid="nav-value">
                  {formatCny(account.nav_fen)}
                </div>
                <div className="hero-delta">
                  <span className={'numeric ' + navClass}>{formatCny(account.session_pnl_fen, { signed: true })}</span>
                  <span className="hero-delta-label">当日盈亏 · 源日</span>
                </div>
                <div className="hero-account">
                  <span className="code-chip">{account.account_id}</span>
                  <span className="page-meta__sep" aria-hidden="true">·</span>
                  <span>最后估值 {meta.last_valid_valuation_at ? formatDateTime(meta.last_valid_valuation_at) : formatDay(meta.as_of)}</span>
                </div>
              </div>
              <div className="hero-side">
                <div className="hero-side-item">
                  <span>账号现金</span>
                  <strong className="numeric">{formatCny(account.cash_fen)}</strong>
                </div>
                <div className="hero-side-item">
                  <span>可用现金</span>
                  <strong className="numeric">{formatCny(account.available_cash_fen)}</strong>
                </div>
                <div className="hero-side-item">
                  <span>订单预留</span>
                  <strong className="numeric">{formatCny(account.reserved_cash_fen)}</strong>
                </div>
              </div>
            </div>

            {hasValuationError ? (
              <Callout tone="warning" title="最后估值缺失" className="hero-warning">
                净值、当日与累计盈亏在本快照中不可用。缺失估值不会被零值或前一日价格替代。服务端原因：{account.valuation_error}。
              </Callout>
            ) : null}

            <div className="stat-row hero-stats">
              <div className="stat">
                <div className="stat__label">累计盈亏</div>
                <div className={'stat__value numeric ' + signClass(account.cumulative_pnl_fen)}>
                  {formatCny(account.cumulative_pnl_fen, { signed: true })}
                </div>
                <div className="stat__hint">NAV − 初始 NAV − 外部净流入</div>
              </div>
              <div className="stat">
                <div className="stat__label">累计收益率</div>
                <div className={'stat__value numeric ' + signClass(account.total_return_bps)}>
                  {formatBps(account.total_return_bps, { signed: true })}
                </div>
                <div className="stat__hint">报告整数基点口径</div>
              </div>
              <div className="stat">
                <div className="stat__label">最大日观察回撤</div>
                <div className="stat__value numeric">{formatBps(account.max_daily_observation_drawdown_bps)}</div>
                <div className="stat__hint">按相邻报告日观察，非盘中回撤</div>
              </div>
            </div>
          </Card>
        </div>

        <div className="col-4">
          <Card className="risk-card">
            <CardHead
              title="账户风险"
              subtitle="只展示原报告记录的锁与估值状态"
              actions={<Badge tone={totalFreezes > 0 ? 'danger' : 'neutral'}>{totalFreezes > 0 ? '有记录' : '未记录锁'}</Badge>}
            />
            <CardBody>
              <div className={'risk-status ' + (totalFreezes > 0 ? 'risk-status--danger' : 'risk-status--calm')}>
                <span className={'status-dot ' + (totalFreezes > 0 ? 'status-dot--warning' : '')} aria-hidden="true" />
                <div>
                  <strong>{totalFreezes > 0 ? String(totalFreezes) + ' 项风控锁' : '此快照未记录风控锁'}</strong>
                  <p>服务可达不等于风控运行正常；本页不读取实时风控状态。</p>
                </div>
              </div>
              <dl className="risk-rows">
                <div><dt>账户锁</dt><dd className="numeric">{String(accountFreezes)}</dd></div>
                <div><dt>策略锁</dt><dd className="numeric">{String(strategyFreezes)}</dd></div>
                <div><dt>有效估值日</dt><dd className="numeric">{String(validValuations)} / {String(bundle.equity.length)}</dd></div>
                <div><dt>缺失估值日</dt><dd className={'numeric ' + (missingValuations ? 'warning-text' : '')}>{String(missingValuations)}</dd></div>
                <div><dt>估值状态</dt><dd>{hasValuationError ? '最后估值缺失' : '有效'}</dd></div>
              </dl>
              <div className="risk-caveat">
                <p>风控阈值、实时连接与前向账户未在本快照中提供。Paper only。</p>
              </div>
            </CardBody>
          </Card>
        </div>

        <div className="col-12">
          <Card className="chart-card">
            <CardHead
              title="资产曲线"
              subtitle={meta.mode === 'historical_replay' ? '历史回放，仅用于核对已发布报告' : '按报告日期绘制，缺失估值不补点'}
              actions={
                <SegmentedControl
                  label="图表指标"
                  options={METRIC_OPTIONS}
                  value={metric}
                  onChange={onMetric}
                  compact
                />
              }
            />
            <CardBody>
              <div className="chart-toolbar">
                <div className="chart-legend">
                  <span className="chart-legend__item"><span className="chart-legend__line" /> 当前 Paper 账户</span>
                  <span className="chart-legend__item"><span className="chart-legend__dash" /> 缺失估值断开</span>
                </div>
                <SegmentedControl
                  label="图表时间范围"
                  options={RANGE_OPTIONS}
                  value={range}
                  onChange={onRange}
                  compact
                />
              </div>
              <EquityChart rows={chartRows} metric={metric} label="当前 Paper 账户资产曲线" />
              <div className="chart-caption">
                <div className="chart-caption__left">
                  <span>{String(chartRows.length)} 个报告日</span>
                  <span aria-hidden="true">·</span>
                  <span>{String(chartRows.filter((row) => parseInteger(row.nav_fen) !== null).length)} 个有效 NAV 点</span>
                  {chartRows.some((row) => parseInteger(row.nav_fen) === null) ? (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>缺估值 {String(chartRows.filter((row) => parseInteger(row.nav_fen) === null).length)} 日</span>
                    </>
                  ) : null}
                </div>
                <span>仅按真实日期绘制 · 不补齐区间</span>
              </div>
            </CardBody>
          </Card>
        </div>

        <div className="col-7">
          <Card className="positions-card">
            <CardHead
              title={'当前持仓' + (sortedPositions.length ? ' · ' + String(sortedPositions.length) : '')}
              subtitle="源日持仓、可卖数量与报告估值"
            />
            {sortedPositions.length === 0 ? (
              <EmptyState
                compact
                icon="wallet"
                title="当前空仓"
                description="此报告没有持仓记录。页面不会生成占位证券或虚构市值。"
              />
            ) : (
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
                  {sortedPositions.map((position) => (
                    <tr key={position.instrument.code} onClick={() => positions.select(position)}>
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
                        <span className="cell-sub">{instrumentLabel(position.instrument)}</span>
                      </td>
                      <td className="num">{formatShares(position.quantity)}</td>
                      <td className="num">{formatCny(position.market_value_fen)}</td>
                      <td className={'num ' + signClass(position.unrealized_pnl_fen)}>
                        {formatCny(position.unrealized_pnl_fen, { signed: true })}
                      </td>
                      <td className="num">{formatShares(position.sellable_shares)}</td>
                      <td className="row-action-cell" aria-hidden="true"><span className="row-chevron">›</span></td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
            {sortedPositions.length > 0 ? (
              <div className="card__foot">
                <span>持仓市值只从有效 NAV 与现金导出。</span>
                <span>点击一行查看批次与关联记录</span>
              </div>
            ) : null}
          </Card>
        </div>

        <div className="col-5">
          <Card className="recent-fills-card">
            <CardHead
              title="最近模拟成交"
              subtitle="最多五笔已确认 fills，不代表券商成交"
              actions={<Badge tone="outline">最近 5 笔</Badge>}
            />
            {recentFills.length === 0 ? (
              <EmptyState
                compact
                icon="list"
                title="尚无已确认模拟成交"
                description="未成交、拒绝和过期订单可在历史与报告的订单状态中查看。"
              />
            ) : (
              <Table label="最近模拟成交">
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
                    <tr key={fill.fill_id} onClick={() => fills.select(fill)}>
                      <td>
                        <button
                          type="button"
                          className="row-link"
                          onClick={(event) => {
                            event.stopPropagation();
                            fills.select(fill);
                          }}
                        >
                          {formatDay(fill.day).slice(5)}
                        </button>
                      </td>
                      <td>{fill.instrument.code}</td>
                      <td><SideBadge side={fill.side} /></td>
                      <td className="num">{formatShares(fill.quantity)}</td>
                      <td className="num">{formatCny(fill.price_fen)}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
            <div className="card__foot">
              <span>模拟记账不是券商成交时间。</span>
            </div>
          </Card>
        </div>
      </div>

      <div className="data-note">
        <Badge tone="outline">数据说明</Badge>
        <p>
          当前为 <strong>{modeInfo(meta.mode).label}</strong>（{meta.mode}）已发布快照 · {meta.source_version}。证据等级：<strong>{meta.evidence_class}</strong>。
          本页不连接持续运行的前向账户，也不把历史或合成结果冒充连续前向收益。
        </p>
        <EvidenceBadge evidence={meta.evidence_class} />
      </div>

      <PositionDrawer
        position={positions.item}
        open={positions.open}
        fills={bundle.fills}
        meta={meta}
        onClose={positions.close}
      />
      <FillDrawer
        fill={fills.item}
        open={fills.open}
        orders={bundle.orders}
        meta={meta}
        onClose={fills.close}
      />
    </>
  );

  return (
    <>
      {header}
      {content}
    </>
  );
}