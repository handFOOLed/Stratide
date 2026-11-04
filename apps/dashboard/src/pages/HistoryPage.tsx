import { useMemo, useState } from 'react';
import type { ReactNode, Ref } from 'react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { EmptyState } from '../components/ui/EmptyState';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { Select, TextInput } from '../components/ui/Field';
import { Table } from '../components/ui/Table';
import { Tabs } from '../components/ui/Tabs';
import { Skeleton, SkeletonLines } from '../components/ui/Skeleton';
import { PaperErrorPanel } from '../components/domain/PaperErrorPanel';
import { FillDrawer } from '../components/domain/FillDrawer';
import { OrderDrawer } from '../components/domain/OrderDrawer';
import { DayDrawer } from '../components/domain/DayDrawer';
import { StrategyDrawer } from '../components/domain/StrategyDrawer';
import { ModeBadge, OrderStatusBadge, SideBadge } from '../components/domain/Badges';
import { Icon } from '../icons';
import { useSelection } from '../lib/hooks';
import {
  formatBps,
  formatCny,
  formatDateTime,
  formatDay,
  formatShares,
  orderStatusLabel,
  parseInteger,
  signClass,
} from '../lib/format';
import type { Fill, Order, StrategyRecord } from '../lib/types';
import type { HistoryTab } from '../lib/route';
import type { PaperDataState } from '../state/usePaperData';
import type { ResearchState } from '../state/useResearch';
import { WorkspaceStudies } from '../components/domain/WorkspaceStudies';
import type { WorkspaceState } from '../lib/workspace';

const TAB_LABELS = {
  fills: '成交',
  orders: '订单',
  daily: '逐日核对',
  strategies: '策略档案',
  research: '研究档案',
} as const;

interface HistoryProps {
  paper: PaperDataState;
  research: ResearchState;
  workspace: WorkspaceState;
  tab: HistoryTab;
  onTab: (tab: HistoryTab) => void;
  titleRef?: Ref<HTMLHeadingElement>;
}

export function HistoryPage({ paper, research, workspace, tab, onTab, titleRef }: HistoryProps) {
  const bundle = paper.bundle;
  const meta = paper.meta;
  const counts = {
    fills: bundle?.fills.length,
    orders: bundle?.orders.length,
    strategies: bundle?.strategies.length,
    research: research.data?.results.length,
  };
  const tabs = (Object.keys(TAB_LABELS) as HistoryTab[]).map((value) => ({
    value,
    label: TAB_LABELS[value],
    count: counts[value as keyof typeof counts],
  }));

  const header = (
    <PageHeader
      title="历史报告"
      titleRef={titleRef}
      side={
        meta ? (
          <>
            <ModeBadge mode={meta.mode} />
            <Badge tone="outline">源日 {formatDay(meta.last_day)}</Badge>
          </>
        ) : null
      }
    />
  );

  const tabsBar = (
    <div className="tabs-bar">
      <Tabs tabs={tabs} value={tab} onChange={onTab} label="历史报告视图" idPrefix="history" />
    </div>
  );

  let content: ReactNode;
  if (tab === 'research') {
    content = <><WorkspaceStudies workspace={workspace}/><ResearchTab research={research} /></>;
  } else if (paper.phase === 'loading') {
    content = <HistorySkeleton />;
  } else if (!bundle || !meta) {
    content = (
      <PaperErrorPanel
        error={paper.error ?? { code: 'UNKNOWN', message: '账户数据不可用', status: 0 }}
        onRetry={paper.refresh}
      />
    );
  } else {
    content = (
      <>
        {paper.stale && paper.error ? (
          <Callout tone="warning" title="最近一次读取失败，以下为上次成功读取的快照" className="stale-banner">
            <div className="stale-banner__row">
              <span>{paper.error.message}</span>
              <Button size="sm" variant="ghost" icon="refresh" onClick={paper.refresh}>重新读取</Button>
            </div>
          </Callout>
        ) : null}
        {tab === 'fills' ? (
          <FillsTab fills={bundle.fills} orders={bundle.orders} meta={meta} />
        ) : tab === 'orders' ? (
          <OrdersTab orders={bundle.orders} fills={bundle.fills} meta={meta} />
        ) : tab === 'daily' ? (
          <DailyTab bundle={bundle} />
        ) : (
          <StrategiesTab strategies={bundle.strategies} fills={bundle.fills} orders={bundle.orders} meta={meta} />
        )}
      </>
    );
  }

  return (
    <>
      {header}
      {tabsBar}
      <div
        key={tab}
        className="tab-panel-enter"
        role="tabpanel"
        id={'history-panel-' + tab}
        aria-labelledby={'history-tab-' + tab}
        tabIndex={0}
      >
        {content}
      </div>
    </>
  );
}

function HistorySkeleton() {
  return (
    <Card aria-hidden="true">
      <CardBody>
        <SkeletonLines lines={2} />
        <div className="skeleton-gap" />
        <SkeletonLines lines={6} />
      </CardBody>
    </Card>
  );
}

function FillsTab({
  fills,
  orders,
  meta,
}: {
  fills: Fill[];
  orders: Order[];
  meta: NonNullable<PaperDataState['meta']>;
}) {
  const selection = useSelection<Fill>();
  const [query, setQuery] = useState('');
  const [side, setSide] = useState<'all' | 'Buy' | 'Sell'>('all');
  const [order, setOrder] = useState<'desc' | 'asc'>('desc');

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const rows = fills.filter((fill) => {
      if (side !== 'all' && fill.side !== side) return false;
      if (!term) return true;
      return [fill.instrument.code, fill.instrument.market, fill.deployment.strategy_id, fill.order_id, fill.fill_id]
        .join(' ')
        .toLowerCase()
        .includes(term);
    });
    return [...rows].sort((a, b) => {
      const left = (a.day + a.fill_id).localeCompare(b.day + b.fill_id);
      return order === 'desc' ? -left : left;
    });
  }, [fills, order, query, side]);

  return (
    <Card className="history-card">
      <div className="toolbar">
        <div className="toolbar__search">
          <Icon name="search" />
          <TextInput
            aria-label="搜索成交"
            placeholder="搜索证券、策略或订单号"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <SegmentedControl
          label="成交方向"
          options={[
            { value: 'all', label: '全部' },
            { value: 'Buy', label: '买入' },
            { value: 'Sell', label: '卖出' },
          ]}
          value={side}
          onChange={setSide}
          compact
        />
        <SegmentedControl
          label="时间顺序"
          options={[
            { value: 'desc', label: '最新优先' },
            { value: 'asc', label: '最早优先' },
          ]}
          value={order}
          onChange={setOrder}
          compact
        />
        <span className="toolbar__meta">{String(filtered.length)} / {String(fills.length)} 笔</span>
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          compact
          icon="search"
          title={fills.length === 0 ? '尚无已确认模拟成交' : '没有匹配的成交'}
          description={
            fills.length === 0
              ? '此报告没有已确认的模拟成交。未成交、拒绝和过期订单可在订单状态中查看。'
              : '调整搜索词、方向或时间顺序。'
          }
        />
      ) : (
        <>
          <Table label="完整模拟成交" className="fills-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>证券</th>
                <th>方向</th>
                <th className="num">价格</th>
                <th className="num">数量</th>
                <th className="num">费用</th>
                <th>策略</th>
                <th aria-label="详情" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((fill) => (
                <tr key={fill.fill_id} onClick={() => selection.select(fill)}>
                  <td>
                    <button
                      type="button"
                      className="row-link"
                      onClick={(event) => {
                        event.stopPropagation();
                        selection.select(fill);
                      }}
                    >
                      {formatDay(fill.day)}
                    </button>
                    <span className="cell-sub">{formatDateTime(fill.simulated_at)}</span>
                  </td>
                  <td>
                    <span className="cell-title">{fill.instrument.code}</span>
                  </td>
                  <td><SideBadge side={fill.side} /></td>
                  <td className="num">{formatCny(fill.price_fen)}</td>
                  <td className="num">{formatShares(fill.quantity)}</td>
                  <td className="num">{formatCny(fill.fee_fen)}</td>
                  <td><span className="cell-sub">{fill.deployment.strategy_id}</span></td>
                  <td className="row-action-cell" aria-hidden="true"><span className="row-chevron">›</span></td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="card__foot">
            <span>模拟记账时间不是券商真实成交时间。</span>
            <span>点击一行查看费用拆分、订单与执行假设。</span>
          </div>
        </>
      )}
      <FillDrawer fill={selection.item} open={selection.open} orders={orders} meta={meta} onClose={selection.close} />
    </Card>
  );
}

function OrdersTab({
  orders,
  fills,
  meta,
}: {
  orders: Order[];
  fills: Fill[];
  meta: NonNullable<PaperDataState['meta']>;
}) {
  const selection = useSelection<Order>();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');

  const statuses = useMemo(() => {
    const values = Array.from(new Set(orders.map((order) => order.status)));
    return values.sort();
  }, [orders]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return [...orders]
      .filter((order) => {
        if (status !== 'all' && order.status !== status) return false;
        if (!term) return true;
        return [order.instrument.code, order.deployment.strategy_id, order.order_id, order.reason ?? '']
          .join(' ')
          .toLowerCase()
          .includes(term);
      })
      .reverse();
  }, [orders, query, status]);

  return (
    <Card className="history-card">
      <div className="toolbar">
        <div className="toolbar__search">
          <Icon name="search" />
          <TextInput
            aria-label="搜索订单"
            placeholder="搜索证券、策略、订单号或原因"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <Select
          aria-label="订单状态筛选"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="toolbar__select"
        >
          <option value="all">全部状态</option>
          {statuses.map((value) => (
            <option key={value} value={value}>{orderStatusLabel(value)}</option>
          ))}
        </Select>
        <span className="toolbar__meta">{String(filtered.length)} / {String(orders.length)} 笔</span>
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          compact
          icon="list"
          title={orders.length === 0 ? '尚无模拟订单' : '没有匹配的订单'}
          description={
            orders.length === 0
              ? '此报告没有提交过订单。页面不会生成占位委托。'
              : '调整搜索词或状态筛选。'
          }
        />
      ) : (
        <>
          <Table label="完整模拟订单" className="orders-table">
            <thead>
              <tr>
                <th>订单 / 源日</th>
                <th>证券 / 方向</th>
                <th className="num">委托</th>
                <th className="num">已确认 / 剩余</th>
                <th className="num">限价</th>
                <th>状态</th>
                <th>原始原因</th>
                <th aria-label="详情" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((order) => (
                <tr key={order.order_id} onClick={() => selection.select(order)}>
                  <td>
                    <button
                      type="button"
                      className="row-link cell-mono"
                      onClick={(event) => {
                        event.stopPropagation();
                        selection.select(order);
                      }}
                    >
                      #{order.order_id}
                    </button>
                    <span className="cell-sub">{formatDay(order.day)}</span>
                  </td>
                  <td>
                    <span className="cell-title">{order.instrument.code}</span>
                    <span className="cell-sub">{order.side === 'Buy' ? '买入' : '卖出'}</span>
                  </td>
                  <td className="num">{formatShares(order.quantity)}</td>
                  <td className="num">
                    {formatShares(order.confirmed_filled_shares)} / {formatShares(order.remaining)}
                  </td>
                  <td className="num">{formatCny(order.limit_fen)}</td>
                  <td><OrderStatusBadge status={order.status} label={orderStatusLabel(order.status)} /></td>
                  <td className="cell-reason" title={order.reason ?? ''}>{order.reason || '无额外原因'}</td>
                  <td className="row-action-cell" aria-hidden="true"><span className="row-chevron">›</span></td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="card__foot">
            <span>委托意图不等于实际成交；原始 reason 不做前端改写。</span>
          </div>
        </>
      )}
      <OrderDrawer order={selection.item} open={selection.open} fills={fills} meta={meta} onClose={selection.close} />
    </Card>
  );
}

function DailyTab({ bundle }: { bundle: NonNullable<PaperDataState['bundle']> }) {
  const selection = useSelection<{ row: NonNullable<PaperDataState['bundle']>['equity'][number]; previous: NonNullable<PaperDataState['bundle']>['equity'][number] | null }>();
  const account = bundle.account;
  const rows = bundle.equity;
  const missing = rows.filter((row) => parseInteger(row.nav_fen) === null).length;
  const latest = rows[rows.length - 1] ?? null;
  const previousRows = useMemo(() => {
    const map = new Map<string, typeof rows[number] | null>();
    rows.forEach((row, index) => map.set(row.day, rows[index - 1] ?? null));
    return map;
  }, [rows]);

  return (
    <div className="daily-layout">
      <Card className="daily-summary">
        <CardHead
          title="报告摘要"
          actions={<Badge tone={missing ? 'warning' : 'neutral'}>{missing ? '有缺失估值' : '逐日完整'}</Badge>}
        />
        <CardBody>
          <dl className="reconciliation-strip">
            <div>
              <dt>报告区间</dt>
              <dd>{formatDay(rows[0]?.day ?? null)} — {formatDay(rows[rows.length - 1]?.day ?? null)}</dd>
            </div>
            <div>
              <dt>报告日</dt>
              <dd className="numeric">{String(rows.length)}</dd>
            </div>
            <div>
              <dt>有效 / 缺失估值</dt>
              <dd className="numeric">{String(rows.length - missing)} / {String(missing)}</dd>
            </div>
            <div>
              <dt>外部净流入</dt>
              <dd className="numeric">{formatCny(account.external_flow_total_fen, { signed: true })}</dd>
            </div>
            <div>
              <dt>初始净值</dt>
              <dd className="numeric">{formatCny(account.initial_nav_fen)}</dd>
            </div>
            <div>
              <dt>累计模拟费用</dt>
              <dd className="numeric">{formatCny(account.total_fee_fen)}</dd>
            </div>
          </dl>
        </CardBody>
      </Card>

      <Card className="history-card">
        {rows.length === 0 ? (
          <EmptyState compact icon="calendar" title="没有逐日记录" description="报告没有可展示的逐日字段。" />
        ) : (
          <>
            <Table label="账户逐日核对" className="daily-table">
              <thead>
                <tr>
                  <th>源日期</th>
                  <th className="num">账户资产</th>
                  <th className="num">现金</th>
                  <th className="num">隐含持仓</th>
                  <th className="num">累计盈亏</th>
                  <th className="num">累计收益率</th>
                  <th>估值状态</th>
                  <th aria-label="详情" />
                </tr>
              </thead>
              <tbody>
                {[...rows].reverse().map((row) => {
                  const nav = parseInteger(row.nav_fen);
                  const cash = parseInteger(row.cash_fen);
                  const holdings = nav !== null && cash !== null ? (nav - cash).toString() : null;
                  return (
                    <tr
                      key={row.day}
                      onClick={() => selection.select({ row, previous: previousRows.get(row.day) ?? null })}
                    >
                      <td>
                        <button
                          type="button"
                          className="row-link"
                          onClick={(event) => {
                            event.stopPropagation();
                            selection.select({ row, previous: previousRows.get(row.day) ?? null });
                          }}
                        >
                          {formatDay(row.day)}
                        </button>
                      </td>
                      <td className="num">{formatCny(row.nav_fen)}</td>
                      <td className="num">{formatCny(row.cash_fen)}</td>
                      <td className="num">{formatCny(holdings)}</td>
                      <td className={'num ' + signClass(row.cumulative_pnl_fen)}>
                        {formatCny(row.cumulative_pnl_fen, { signed: true })}
                      </td>
                      <td className={'num ' + signClass(row.return_bps)}>
                        {formatBps(row.return_bps, { signed: true })}
                      </td>
                      <td>
                        {row.valuation_error ? <Badge tone="warning">估值缺失</Badge> : '—'}
                      </td>
                      <td className="row-action-cell" aria-hidden="true"><span className="row-chevron">›</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
            <div className="card__foot">
              <span>隐含持仓 = 账户资产 − 现金</span>
              <span>最新源日 {formatDay(latest?.day ?? null)}</span>
            </div>
          </>
        )}
      </Card>

      <DayDrawer
        row={selection.item?.row ?? null}
        previous={selection.item?.previous ?? null}
        open={selection.open}
        onClose={selection.close}
      />
    </div>
  );
}

function StrategiesTab({
  strategies,
  fills,
  orders,
  meta,
}: {
  strategies: StrategyRecord[];
  fills: Fill[];
  orders: Order[];
  meta: NonNullable<PaperDataState['meta']>;
}) {
  const selection = useSelection<StrategyRecord>();
  return (
    <Card className="history-card">
      <CardHead
        title="冻结部署"
        actions={<Badge tone="outline">{String(strategies.length)} 条</Badge>}
      />
      {strategies.length === 0 ? (
        <EmptyState
          compact
          icon="layers"
          title="没有策略记录"
        />
      ) : (
        <>
          <Table label="策略档案">
            <thead>
              <tr>
                <th>策略</th>
                <th>所属组</th>
                <th>冻结版本</th>
                <th>状态</th>
                <th className="num">独立收益</th>
                <th className="num">独立回撤</th>
                <th>不可用原因</th>
                <th aria-label="详情" />
              </tr>
            </thead>
            <tbody>
              {strategies.map((record) => (
                <tr key={record.deployment.deployment_id} onClick={() => selection.select(record)}>
                  <td>
                    <button
                      type="button"
                      className="row-link"
                      onClick={(event) => {
                        event.stopPropagation();
                        selection.select(record);
                      }}
                    >
                      {record.deployment.strategy_id}
                    </button>
                    <span className="cell-sub">{record.deployment.deployment_id}</span>
                  </td>
                  <td>{record.deployment.group_id}</td>
                  <td className="cell-mono">{record.deployment.frozen_version}</td>
                  <td><Badge tone="neutral">{record.status === 'snapshot_record_only' ? '快照记录' : 'Paper 假设记录'}</Badge></td>
                  <td className={'num ' + signClass(record.pnl_fen)}>{formatCny(record.pnl_fen, { signed: true })}</td>
                  <td className={'num ' + ((parseInteger(record.drawdown_bps) ?? 0n) > 0n ? 'loss' : '')}>{formatBps(record.drawdown_bps)}</td>
                  <td className="cell-reason" title={record.unavailable_reason ?? ''}>{record.unavailable_reason || '—'}</td>
                  <td className="row-action-cell" aria-hidden="true"><span className="row-chevron">›</span></td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
      <StrategyDrawer
        record={selection.item}
        open={selection.open}
        fills={fills}
        orders={orders}
        meta={meta}
        onClose={selection.close}
      />
    </Card>
  );
}

function ResearchTab({ research }: { research: ResearchState }) {
  if (research.loading && !research.data) {
    return (
      <Card aria-hidden="true">
        <CardBody><SkeletonLines lines={5} /></CardBody>
      </Card>
    );
  }
  if (research.error) {
    return (
      <Card>
        <EmptyState
          tone="error"
          icon="alert-triangle"
          title="独立研究结果不可用"
          description={research.error.message}
          code={research.error.code}
          actions={<Button variant="secondary" icon="refresh" onClick={research.refresh}>重新读取</Button>}
        />
      </Card>
    );
  }
  const results = research.data?.results ?? [];
  if (results.length === 0) {
    return (
      <Card>
        <EmptyState
          icon="file"
          title="尚未配置独立研究结果"
          description="仅展示独立评估报告，不计入账户资产。"
        />
        <div className="card__foot">
          <span>当前状态：{research.data?.status ?? 'not_configured'}</span>
        </div>
      </Card>
    );
  }
  return (
    <div className="section-stack">
      {results.map((result, index) => (
        <Card key={index} className="research-card">
          <CardHead
            title="独立研究结果"
            subtitle={result.strategy_version || '已保存研究档案'}
            actions={<Badge tone="accent">不计入账户 NAV</Badge>}
          />
          <CardBody>
            <div className="research-labels">
              <Badge tone="outline">研究证据：{result.research_evidence || '未提供'}</Badge>
              <Badge tone="outline">工程：{result.engineering || '未提供'}</Badge>
              <Badge tone="neutral">
                独立验收：
                {typeof result.independent_acceptance === 'string'
                  ? result.independent_acceptance
                  : result.independent_acceptance
                    ? '见原报告'
                    : '未提供'}
              </Badge>
            </div>
            <p className="research-coverage">
              {result.data_coverage?.target || '历史研究范围未提供'} ·{' '}
              {result.data_coverage?.target_blockers?.length
                ? '目标长窗口存在数据阻断'
                : '区段状态见原研究报告'}
            </p>
            {Array.isArray(result.windows) && result.windows.length > 0 ? (
              <Table label="独立研究区段" className="research-table">
                <thead>
                  <tr>
                    <th>区段</th>
                    <th>日期</th>
                    <th className="num">交易日</th>
                    <th className="num">净变化</th>
                    <th className="num">模拟成交</th>
                    <th className="num">缺估值日</th>
                  </tr>
                </thead>
                <tbody>
                  {result.windows.map((window, windowIndex) => (
                    <tr key={windowIndex}>
                      <td>{window.name || '—'}</td>
                      <td>{formatDay(window.first_day ?? null)} — {formatDay(window.last_day ?? null)}</td>
                      <td className="num">{formatShares(window.days)}</td>
                      <td className={'num ' + signClass(window.net_pnl_fen)}>
                        {formatCny(window.net_pnl_fen, { signed: true })}
                      </td>
                      <td className="num">{formatShares(window.fills)}</td>
                      <td className="num">{formatShares(window.missing_nav_days)}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : null}
            <p className="panel-footnote">
              这是独立研究档案，不能作为当前账户资金、持续前向表现或已获准入的证明。
            </p>
          </CardBody>
        </Card>
      ))}
      <div className="section-note">读取已保存研究结论，不重新评价策略，也不发起模型调用。</div>
    </div>
  );
}
