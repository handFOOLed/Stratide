import { useEffect, useMemo, useState } from 'react';
import type { Ref } from 'react';
import { Card, CardBody } from '../components/ui/Card';
import { Badge, StatusDot } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { EmptyState } from '../components/ui/EmptyState';
import { Pager } from '../components/ui/Pager';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Table } from '../components/ui/Table';
import { EquityChart } from '../components/ui/Chart';
import { Skeleton } from '../components/ui/Skeleton';
import { PaperPortfolioPanel } from '../components/domain/PaperPortfolioPanel';
import { FillDrawer } from '../components/domain/FillDrawer';
import { PositionDrawer } from '../components/domain/PositionDrawer';
import { PaperErrorPanel } from '../components/domain/PaperErrorPanel';
import { ModeBadge, SideBadge } from '../components/domain/Badges';
import { FreshnessNote } from '../components/layout/PageFooter';
import { useSelection } from '../lib/hooks';
import {
  formatBps,
  formatCny,
  formatDay,
  formatShares,
  parseInteger,
  signClass,
} from '../lib/format';
import { RANGE_VALUES, readPreference, writePreference } from '../lib/storage';
import type { RangeValue } from '../lib/storage';
import { rangeRows } from '../lib/format';
import type { Fill, Position } from '../lib/types';
import type { PaperDataState } from '../state/usePaperData';
import { navigate } from '../lib/route';

const PAGE_SIZE = 5;

const RANGE_OPTIONS: Array<{ value: RangeValue; label: string }> = [
  { value: '7D', label: '7D' },
  { value: '30D', label: '30D' },
  { value: '90D', label: '90D' },
  { value: '1Y', label: '1Y' },
  { value: 'ALL', label: '全部' },
];

function AlignedStatValue({ formatted, tone = '' }: { formatted: string; tone?: 'gain' | 'loss' | '' }) {
  const parts = /^([+−]?)(¥?)([\d,]+)\.(\d{2})(%?)$/.exec(formatted);
  return (
    <div className={'account-stat__value numeric ' + tone}>
      <span className="sr-only">{formatted}</span>
      {parts ? (
        <>
          <span aria-hidden="true" className="account-stat__sign">{parts[1]}</span>
          <span aria-hidden="true">{parts[2]}</span>
          <span aria-hidden="true" className="account-stat__integer">{parts[3]}</span>
          <span aria-hidden="true">.</span>
          <span aria-hidden="true">{parts[4]}</span>
          <span aria-hidden="true">{parts[5]}</span>
        </>
      ) : <span aria-hidden="true" className="account-stat__missing">{formatted}</span>}
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="overview-grid" aria-hidden="true">
      <div className="overview-top">
        <Skeleton className="skeleton-card skeleton-card--tall" />
        <Skeleton className="skeleton-card skeleton-card--tall" />
        <Skeleton className="skeleton-card skeleton-card--tall" />
      </div>
      <div className="overview-bottom">
        <Skeleton className="skeleton-card" />
        <Skeleton className="skeleton-card" />
      </div>
    </div>
  );
}

export function OverviewPage({ paper, titleRef }: { paper: PaperDataState; titleRef?: Ref<HTMLHeadingElement> }) {
  const [range, setRange] = useState<RangeValue>(() => readPreference('range', '30D', RANGE_VALUES));
  const [page, setPage] = useState(0);
  const [fillPage, setFillPage] = useState(0);
  const positions = useSelection<Position>();
  const fills = useSelection<Fill>();

  const bundle = paper.bundle;
  const meta = paper.meta;

  const chartRows = useMemo(
    () => (bundle ? rangeRows(bundle.equity, range) : []),
    [bundle, range],
  );
  const recentFills = useMemo(
    () => (bundle ? [...bundle.fills].reverse().slice(fillPage * PAGE_SIZE, (fillPage + 1) * PAGE_SIZE) : []),
    [bundle, fillPage],
  );
  const sortedPositions = useMemo(
    () => (bundle ? [...bundle.positions].sort((a, b) => a.instrument.code.localeCompare(b.instrument.code)) : []),
    [bundle],
  );

  const pageCount = Math.max(1, Math.ceil(sortedPositions.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visiblePositions = sortedPositions.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  useEffect(() => {
    if (page >= pageCount) setPage(Math.max(0, pageCount - 1));
  }, [page, pageCount]);

  // The NAV axis tops out at the next power of ten of the larger of the current
  // account NAV and the displayed window, so a historical peak is never clipped.
  const navTopFen = useMemo(() => {
    let top = bundle ? parseInteger(bundle.account.nav_fen) : null;
    for (const row of chartRows) {
      const value = parseInteger(row.nav_fen);
      if (value !== null && (top === null || value > top)) top = value;
    }
    return top;
  }, [bundle, chartRows]);

  const onRange = (next: RangeValue) => {
    setRange(next);
    writePreference('range', next);
  };
  const header = (
    <header className="page-header page-header--compact">
      <div className="page-header__main">
        <h1 className="page-title" ref={titleRef} tabIndex={-1}>
          总览
        </h1>
      </div>
      <div className="page-header__side">
        {meta ? (
          <>
            <ModeBadge mode={meta.mode} />
            <Badge tone="outline">只读快照</Badge>
            <span className="page-meta"><FreshnessNote loadedAt={paper.loadedAt} /></span>
          </>
        ) : null}
      </div>
    </header>
  );

  if (paper.phase === 'loading') {
    return (
      <div className="overview-page">
        {header}
        <div role="status" className="sr-only">正在加载账户数据</div>
        <OverviewSkeleton />
      </div>
    );
  }

  if (paper.phase === 'error' && !bundle) {
    return (
      <div className="overview-page">
        {header}
        <PaperErrorPanel
          error={paper.error ?? { code: 'UNKNOWN', message: '未知错误', status: 0 }}
          onRetry={paper.refresh}
        />
      </div>
    );
  }

  if (!bundle || !meta) return null;
  if (meta.mode === 'historical_replay') {
    return <div className="overview-page">{header}<Card><CardBody><h2 className="card__title">当前 Paper 账户尚未配置</h2><p>已选择的是事后历史报告。报告的净值、持仓与交易保留在历史页，不作为当前 Paper 账户。</p><Button variant="secondary" onClick={() => navigate({page:'history',tab:'daily'})}>查看历史报告</Button></CardBody></Card></div>;
  }

  const account = bundle.account;
  const risk = account.risk;
  const accountFreezes = risk?.account_freezes?.length ?? 0;
  const strategyFreezes = risk?.strategy_freezes?.length ?? 0;
  const totalFreezes = accountFreezes + strategyFreezes;
  const missingValuations = chartRows.filter((row) => parseInteger(row.nav_fen) === null).length;
  const valuedDays = chartRows.length - missingValuations;
  const hasValuationError = Boolean(account.valuation_error);
  const pnlClass = signClass(account.session_pnl_fen);
  const drawdownClass = '';
  const firstVisible = sortedPositions.length === 0 ? 0 : currentPage * PAGE_SIZE + 1;
  const lastVisible = currentPage * PAGE_SIZE + visiblePositions.length;

  return (
    <div className="overview-page">
      {header}

      {paper.stale && paper.error ? (
        <Callout tone="warning" title="最近一次读取失败，以下为上次成功的快照" className="stale-banner">
          <div className="stale-banner__row">
            <span>{paper.error.message}</span>
            <Button size="sm" variant="ghost" icon="refresh" onClick={paper.refresh}>重新读取</Button>
          </div>
        </Callout>
      ) : null}

      <div className="overview-grid">
        <div className="overview-top">
          <Card className="risk-card">
            <CardBody>
              <h2 className="card__title">风险提示</h2>

              {hasValuationError ? (
                <Callout tone="warning" title="最后估值缺失" className="account-alert">
                  净值与盈亏暂不可用。服务端原因：{account.valuation_error}。
                </Callout>
              ) : null}

              <div className={'risk-strip' + (totalFreezes > 0 ? ' risk-strip--alert' : '')}>
                <div className="risk-strip__main">
                  <StatusDot tone={totalFreezes > 0 ? 'warning' : 'online'} />
                  <strong>
                    {totalFreezes > 0
                      ? '此快照记录 ' + String(totalFreezes) + ' 项风控锁'
                      : '此快照未记录风控锁'}
                  </strong>
                </div>
                <div className="risk-strip__meta">
                  <span>账户锁 {String(accountFreezes)}</span>
                  <span>策略锁 {String(strategyFreezes)}</span>
                  <span>估值 {hasValuationError ? '缺失' : '有效'}</span>
                </div>
              </div>
              <p className="risk-card__note">
                {totalFreezes > 0
                  ? '存在风控锁时，新的模拟下单会被阻止；解除需要你确认。'
                  : '当前没有风控锁。触线会自动阻止新的模拟下单。'}
              </p>

            </CardBody>
          </Card>

          <Card className="account-card">
            <CardBody>
              <div className="account-main">
                <h2 className="card__title">账户资产</h2>
                <div className="account-value" data-testid="nav-value">
                  {formatCny(account.nav_fen)}
                </div>
              </div>
              <div className="account-delta">
                <h3 className="account-delta__title">今日盈亏</h3>
                <div className={'account-delta__value numeric ' + pnlClass}>
                  {formatCny(account.session_pnl_fen, { signed: true })}
                </div>
              </div>
              <div className="account-details">
                <div className="account-stats">
                  <div className="account-stat-group">
                    <div className="account-stat">
                      <div className="account-stat__label">累计盈亏</div>
                      <AlignedStatValue
                        formatted={formatCny(account.cumulative_pnl_fen, { signed: true })}
                        tone={signClass(account.cumulative_pnl_fen)}
                      />
                    </div>
                    <div className="account-stat">
                      <div className="account-stat__label">累计费用</div>
                      <AlignedStatValue formatted={formatCny(account.total_fee_fen)} />
                    </div>
                  </div>
                  <div className="account-stat-group">
                    <div className="account-stat">
                      <div className="account-stat__label">累计收益率</div>
                      <AlignedStatValue
                        formatted={formatBps(account.total_return_bps, { signed: true })}
                        tone={signClass(account.total_return_bps)}
                      />
                    </div>
                    <div className="account-stat">
                      <div className="account-stat__label">最大日回撤</div>
                      <AlignedStatValue
                        formatted={formatBps(account.max_daily_observation_drawdown_bps)}
                        tone={drawdownClass}
                      />
                    </div>
                  </div>
                </div>
                <dl className="account-reserved">
                  <dt>交易预留</dt>
                  <dd>{formatCny(account.reserved_cash_fen)}</dd>
                </dl>
              </div>
            </CardBody>
          </Card>

          <Card className="chart-card">
            <div className="card__head card__head--compact">
              <div className="card__heading">
                <h2 className="card__title">资产曲线</h2>
                <p className="card__subtitle">
                  {String(chartRows.length)} 个报告日
                  {missingValuations > 0 ? ' · 缺 ' + String(missingValuations) + ' 日' : ''}
                </p>
              </div>
              <div className="card__actions">
                <SegmentedControl
                  label="图表时间范围"
                  options={RANGE_OPTIONS}
                  value={range}
                  onChange={onRange}
                  compact
                />
              </div>
            </div>
            <div className="chart-body">
              {valuedDays >= 2 ? (
                <>
                  <EquityChart
                    rows={chartRows}
                    metric="nav"
                    label="当前 Paper 账户资产曲线"
                    navTopFen={navTopFen}
                    baselineFen={parseInteger(account.initial_nav_fen)}
                  />
                  <p className="chart-axis-note">纵轴自适应 · 每格为显示范围的 20%</p>
                </>
              ) : (
                <div className="overview-empty overview-empty--chart">
                  <EmptyState
                    compact
                    icon="activity"
                    title="净值曲线将在第二个交易日出现"
                    description="当前只有 1 个报告日；每天盘后采集完成后会自动延长这条曲线。"
                  />
                </div>
              )}
            </div>
          </Card>
        </div>
        <div className="overview-bottom">
          <Card className="positions-card">
            <div className="card__head card__head--compact">
              <div className="card__heading">
                <h2 className="card__title">当前持仓</h2>
                <p className="card__subtitle">{String(sortedPositions.length)} 只</p>
              </div>
            </div>
            {sortedPositions.length === 0 ? (
              <div className="overview-empty">
                <EmptyState compact icon="wallet" title="当前空仓" description="此报告没有持仓记录。" />
              </div>
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
                  {visiblePositions.map((position) => (
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
            <div className="card__foot card__foot--end">
              <span className="pager__count">
                {sortedPositions.length === 0
                  ? '0 条'
                  : String(firstVisible) + '–' + String(lastVisible) + ' / 共 ' + String(sortedPositions.length) + ' 条'}
              </span>
              <Pager page={currentPage + 1} pageCount={pageCount} onPage={(next) => setPage(next - 1)} label="持仓分页" />
            </div>
          </Card>

          <Card className="recent-fills-card">
            <div className="card__head card__head--compact">
              <div className="card__heading">
                <h2 className="card__title">最近成交</h2>
                <p className="card__subtitle">已确认模拟成交 · 每页 5 笔</p>
              </div>
            </div>
            {recentFills.length === 0 ? (
              <div className="overview-empty">
                <EmptyState compact icon="list" title="尚无已确认模拟成交" description="未成交与拒绝的订单可在历史中查看。" />
              </div>
            ) : (
              <Table label="最近模拟成交" className="recent-fills-table">
                <colgroup>
                  <col /><col /><col /><col /><col />
                </colgroup>
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
            <div className="card__foot card__foot--end">
              <span className="pager__count">共 {bundle.fills.length} 笔</span>
              <Pager page={fillPage + 1} pageCount={Math.max(1, Math.ceil(bundle.fills.length / PAGE_SIZE))} onPage={next=>setFillPage(next-1)} label="成交分页"/>
            </div>
          </Card>
        </div>
      </div>

      {bundle.fills.length === 0 && valuedDays < 2 ? (
        <Card className="overview-guide">
          <CardBody>
            <h2 className="card__title">接下来会发生什么</h2>
            <ol className="guide-steps">
              <li><strong>每天盘后</strong>自动采集全市场行情，时间约 16:10–18:00。</li>
              <li><strong>数据满 84 个交易日后</strong>，本机模型与已授权的云研究才会生成候选。</li>
              <li><strong>通过风控后</strong>，才会在你的 {formatCny(account.initial_nav_fen)} 模拟账户里产生模拟成交。</li>
            </ol>
          </CardBody>
        </Card>
      ) : null}

      <PaperPortfolioPanel portfolio={account.portfolio === undefined ? null : account.portfolio} orders={bundle.orders}/>
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
    </div>
  );
}
