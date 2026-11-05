import { useEffect, useMemo, useState } from 'react';
import type { ReactNode, Ref } from 'react';
import { PageHeader, PageMeta, MetaSep } from '../components/ui/PageHeader';
import { Card, CardBody, CardHead } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Callout } from '../components/ui/Callout';
import { EmptyState } from '../components/ui/EmptyState';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import type { SegmentedOption } from '../components/ui/SegmentedControl';
import { Select, TextInput } from '../components/ui/Field';
import { Table } from '../components/ui/Table';
import { Tabs } from '../components/ui/Tabs';
import { SkeletonLines } from '../components/ui/Skeleton';
import { Diagnostics } from '../components/ui/Diagnostics';
import { StatusBadge } from '../components/ui/StatusBadge';
import { InfoHint } from '../components/ui/InfoHint';
import { FillDrawer } from '../components/domain/FillDrawer';
import { OrderDrawer } from '../components/domain/OrderDrawer';
import { DayDrawer } from '../components/domain/DayDrawer';
import { StrategyDrawer } from '../components/domain/StrategyDrawer';
import { SideBadge } from '../components/domain/Badges';
import { FreshnessNote } from '../components/layout/PageFooter';
import { Icon } from '../icons';
import { useSelection } from '../lib/hooks';
import {
  countText,
  formatBps,
  formatCny,
  formatDateFromTimestamp,
  formatDateTime,
  formatDay,
  parseInteger,
  signClass,
} from '../lib/format';
import { humanReasonText, orderStatusView, statusView } from '../lib/status';
import type { StatusView } from '../lib/status';
import { EMPTY, TERMS } from '../lib/copy';
import type { EquityRow, Fill, Order, PaperBundle, SnapshotMeta, StrategyRecord } from '../lib/types';
import { navigate } from '../lib/route';
import type { HistoryTab } from '../lib/route';
import type { ApiError } from '../lib/api';
import type { PaperDataState } from '../state/usePaperData';
import type { ResearchState } from '../state/useResearch';
import type { WorkspaceState } from '../lib/workspace';

type VisibleTab = 'fills' | 'orders' | 'daily';
type SideFilter = 'all' | 'Buy' | 'Sell';
type SortOrder = 'desc' | 'asc';
type DailySelection = { row: EquityRow; previous: EquityRow | null };

const VISIBLE_TABS = ['fills', 'orders', 'daily'] as const;

const TAB_LABELS: Record<VisibleTab, string> = {
  fills: '成交',
  orders: '订单',
  daily: '每日账本',
};

const SIDE_OPTIONS: ReadonlyArray<SegmentedOption<SideFilter>> = [
  { value: 'all', label: '全部' },
  { value: 'Buy', label: '买入' },
  { value: 'Sell', label: '卖出' },
];

const SORT_OPTIONS: ReadonlyArray<SegmentedOption<SortOrder>> = [
  { value: 'desc', label: '最新在前' },
  { value: 'asc', label: '最早在前' },
];

const STRATEGY_RECORD_STATUS: Record<string, StatusView> = {
  snapshot_record_only: statusView('ok', '仅记录'),
  paper_assumption_only: statusView('ok', '仅记录'),
};

/** 旧链接里的“策略记录 / 研究报告”不再单独成页，统一回到成交。 */
function resolveTab(tab: HistoryTab): VisibleTab {
  if (tab === 'orders') return 'orders';
  if (tab === 'daily') return 'daily';
  return 'fills';
}

function strategyRecordStatus(status: string): StatusView {
  if (Object.hasOwn(STRATEGY_RECORD_STATUS, status)) return STRATEGY_RECORD_STATUS[status];
  return statusView('unset', '状态未知');
}

function loadFailureReason(error: ApiError): string {
  const mapped = humanReasonText(error.code);
  if (mapped !== null) return mapped;
  return error.message === '—' ? '原因未记录' : error.message;
}

function dayText(value: string | null): string {
  return value === null ? '未记录' : formatDay(value);
}

/** 最后有效估值日早于数据日期时在页头附注；相等则不重复展示。 */
function lastValidValuationDay(meta: SnapshotMeta): string | null {
  if (meta.last_valid_valuation_at === null) return null;
  const day = formatDateFromTimestamp(meta.last_valid_valuation_at);
  if (day === '—' || day === formatDay(meta.last_day)) return null;
  return day;
}

function moneyText(value: string | null): string {
  return parseInteger(value) === null ? '未记录' : formatCny(value);
}

function signedMoneyText(value: string | null): string {
  return parseInteger(value) === null ? '未记录' : formatCny(value, { signed: true });
}

function returnText(value: string | null): string {
  return parseInteger(value) === null ? '未记录' : formatBps(value, { signed: true });
}

function drawdownTone(value: string | null): string {
  const parsed = value === null ? null : parseInteger(value);
  return parsed !== null && parsed > 0n ? 'loss' : '';
}

/** 只放行已翻译的原因；形如 "SOURCE_BLOCKED:xxx" 的原始码一律折叠为“原因未记录”。 */
function reasonText(value: string | null): string | null {
  if (value === null) return null;
  const mapped = humanReasonText(value);
  if (mapped === null || /^[\x20-\x7E]+$/.test(mapped)) return null;
  return mapped;
}

function orderReasonText(order: Order): string {
  if (order.reason === null) return order.status === 'Rejected' ? '原因未记录' : '';
  return reasonText(order.reason) ?? '原因未记录';
}

function missingDataStatus(reason: string): StatusView {
  const human = humanReasonText(reason);
  return human === null ? statusView('attention', '数据缺失') : statusView('attention', '数据缺失', human);
}

function snapshotItems(meta: SnapshotMeta): Array<{ label: string; value: string }> {
  return [
    { label: '数据日期', value: dayText(meta.last_day) },
    { label: '数据开始', value: dayText(meta.first_day) },
    { label: '更新于', value: meta.as_of === null ? '未记录' : formatDateTime(meta.as_of) },
    {
      label: '最后有效估值日',
      value:
        meta.last_valid_valuation_at === null ? '未记录' : formatDateTime(meta.last_valid_valuation_at),
    },
    { label: '数据模式', value: meta.mode },
    { label: '证据等级', value: meta.evidence_class },
    { label: '数据来源', value: meta.source },
    { label: '来源版本', value: meta.source_version },
    { label: '数据缺口', value: countText(meta.gaps.length, '条') },
    { label: '快照标识', value: meta.snapshot_id },
    { label: '报告校验', value: meta.report_sha256 },
    { label: '输入校验', value: meta.input_sha256 },
    { label: '账本头', value: meta.ledger_head },
    { label: '校验状态', value: meta.validation },
  ];
}

interface HistoryProps {
  paper: PaperDataState;
  research: ResearchState;
  workspace: WorkspaceState;
  tab: HistoryTab;
  onTab: (tab: HistoryTab) => void;
  titleRef?: Ref<HTMLHeadingElement>;
}

export function HistoryPage({ paper, tab, onTab, titleRef }: HistoryProps) {
  const active = resolveTab(tab);
  const bundle = paper.bundle;

  // 旧链接（策略档案 / 研究档案）已经并入“成交”，把地址也收敛到成交视图。
  useEffect(() => {
    if (active === tab) return;
    navigate({ page: 'history', tab: 'fills' }, { replace: true });
  }, [active, tab]);
  const meta = paper.meta;
  const lastValidDay = meta === null ? null : lastValidValuationDay(meta);
  const tabs = VISIBLE_TABS.map((value) => ({
    value,
    label: TAB_LABELS[value],
    count:
      bundle === null
        ? undefined
        : value === 'fills'
          ? bundle.fills.length
          : value === 'orders'
            ? bundle.orders.length
            : bundle.equity.length,
  }));

  let content: ReactNode;
  if (bundle === null || meta === null) {
    content = paper.error === null ? <HistorySkeleton /> : <HistoryLoadError error={paper.error} onRetry={paper.refresh} />;
  } else if (active === 'fills') {
    content = <FillsTab fills={bundle.fills} orders={bundle.orders} meta={meta} />;
  } else if (active === 'orders') {
    content = <OrdersTab orders={bundle.orders} fills={bundle.fills} meta={meta} />;
  } else {
    content = <DailyTab bundle={bundle} />;
  }

  return (
    <>
      <PageHeader
        title="交易记录"
        titleRef={titleRef}
        side={
          meta === null ? null : (
            <PageMeta>
              <span data-testid="history-data-date">
                {TERMS.dataDate} {dayText(meta.last_day)}
              </span>
              {lastValidDay === null ? null : (
                <>
                  <MetaSep />
                  <span data-testid="history-last-valuation-day">最后有效估值日 {lastValidDay}</span>
                </>
              )}
              {paper.loadedAt === null ? null : (
                <>
                  <MetaSep />
                  <FreshnessNote loadedAt={paper.loadedAt} />
                </>
              )}
            </PageMeta>
          )
        }
      />
      <div className="tabs-bar" data-testid="history-tabs">
        <Tabs tabs={tabs} value={active} onChange={onTab} label="交易记录视图" idPrefix="history" />
      </div>
      {bundle !== null && meta !== null && paper.error !== null ? (
        <StaleBanner reason={loadFailureReason(paper.error)} onRetry={paper.refresh} />
      ) : null}
      <div
        key={active}
        className="tab-panel-enter"
        role="tabpanel"
        id={'history-panel-' + active}
        aria-labelledby={'history-tab-' + active}
        tabIndex={0}
      >
        {content}
      </div>
      {bundle !== null && meta !== null ? (
        <AdvancedRecords strategies={bundle.strategies} fills={bundle.fills} orders={bundle.orders} meta={meta} />
      ) : null}
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

function HistoryLoadError({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return (
    <div data-testid="history-load-error">
      <Card className="history-error-card">
        <EmptyState
          tone="error"
          icon="alert-triangle"
          title="读取失败"
          description={loadFailureReason(error)}
          actions={
            <Button variant="secondary" icon="refresh" onClick={onRetry}>
              重新读取
            </Button>
          }
        />
        <div className="history-error-card__diagnostics">
          <Diagnostics
            title="读取诊断信息"
            items={[
              { label: '错误代码', value: error.code },
              { label: '提示', value: error.message === '—' ? '原因未记录' : error.message },
              { label: 'HTTP 状态', value: String(error.status) },
            ]}
            data={{ code: error.code, status: error.status, detail: error.detail }}
          />
        </div>
      </Card>
    </div>
  );
}

function StaleBanner({ reason, onRetry }: { reason: string; onRetry: () => void }) {
  return (
    <Callout tone="warning" title="更新失败，以下为上次成功读取的数据" className="stale-banner" role="alert">
      <div className="stale-banner__row">
        <span>{reason}</span>
        <Button size="sm" variant="ghost" icon="refresh" onClick={onRetry}>
          重新读取
        </Button>
      </div>
    </Callout>
  );
}

function FillsTab({ fills, orders, meta }: { fills: Fill[]; orders: Order[]; meta: SnapshotMeta }) {
  const selection = useSelection<Fill>();
  const [query, setQuery] = useState('');
  const [side, setSide] = useState<SideFilter>('all');
  const [order, setOrder] = useState<SortOrder>('desc');

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const rows = fills.filter((fill) => {
      if (side !== 'all' && fill.side !== side) return false;
      if (!term) return true;
      return [fill.instrument.code, fill.instrument.market, fill.deployment.strategy_id]
        .join(' ')
        .toLowerCase()
        .includes(term);
    });
    return [...rows].sort((a, b) => {
      const left = (a.day + a.fill_id).localeCompare(b.day + b.fill_id);
      return order === 'desc' ? -left : left;
    });
  }, [fills, order, query, side]);

  const clearFilters = () => {
    setQuery('');
    setSide('all');
  };

  return (
    <Card className="history-card">
      <div className="toolbar">
        <div className="toolbar__search" data-testid="fills-search">
          <Icon name="search" />
          <TextInput
            aria-label="搜索成交"
            placeholder="搜索证券或策略"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <SegmentedControl label="成交方向" options={SIDE_OPTIONS} value={side} onChange={setSide} compact />
        <SegmentedControl label="时间顺序" options={SORT_OPTIONS} value={order} onChange={setOrder} compact />
        <span className="toolbar__meta">
          {filtered.length === fills.length
            ? '共 ' + countText(fills.length, '笔')
            : '显示 ' + countText(filtered.length, '笔') + ' · 共 ' + countText(fills.length, '笔')}
        </span>
      </div>
      {filtered.length === 0 ? (
        <div data-testid="fills-empty">
          <EmptyState
            compact
            icon={fills.length === 0 ? 'history' : 'search'}
            title={fills.length === 0 ? EMPTY.fillsTitle : '没有匹配的成交'}
            description={fills.length === 0 ? EMPTY.fillsBody : '调整搜索、方向或排序条件后再看。'}
            actions={
              fills.length === 0 ? undefined : (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  清除筛选
                </Button>
              )
            }
          />
        </div>
      ) : (
        <>
          <div data-testid="fills-table">
            <Table label="成交记录" className="fills-table history-table--fills">
              <thead>
                <tr>
                  <th>日期 / 时间</th>
                  <th>证券</th>
                  <th>方向</th>
                  <th className="num">价格</th>
                  <th className="num">数量</th>
                  <th className="num">费用</th>
                  <th aria-label="详情" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((fill) => (
                  <tr key={fill.fill_id} data-testid="fill-row" onClick={() => selection.select(fill)}>
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
                      {fill.simulated_at === null ? null : (
                        <span className="cell-sub">{formatDateTime(fill.simulated_at)}</span>
                      )}
                    </td>
                    <td>
                      <span className="cell-title">{fill.instrument.code}</span>
                    </td>
                    <td>
                      <SideBadge side={fill.side} />
                    </td>
                    <td className="num">{formatCny(fill.price_fen)}</td>
                    <td className="num">{countText(fill.quantity, '股')}</td>
                    <td className="num">{formatCny(fill.fee_fen)}</td>
                    <td className="row-action-cell" aria-hidden="true">
                      <span className="row-chevron">›</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
          <div className="card__foot">
            <span>
              模拟成交，不是券商真实成交。
              <InfoHint label="模拟成交说明">通过交易保护后，按次日开盘价模拟成交；用于验证策略流程，不代表真实可成交价格。</InfoHint>
            </span>
            <span>点击一行查看费用与订单详情。</span>
          </div>
        </>
      )}
      <FillDrawer fill={selection.item} open={selection.open} orders={orders} meta={meta} onClose={selection.close} />
    </Card>
  );
}

function OrdersTab({ orders, fills, meta }: { orders: Order[]; fills: Fill[]; meta: SnapshotMeta }) {
  const selection = useSelection<Order>();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');

  const statuses = useMemo(() => {
    const values = Array.from(new Set(orders.map((order) => order.status)));
    return values.sort();
  }, [orders]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return orders
      .filter((order) => {
        if (status !== 'all' && order.status !== status) return false;
        if (!term) return true;
        return [order.instrument.code, order.instrument.market, order.deployment.strategy_id]
          .join(' ')
          .toLowerCase()
          .includes(term);
      })
      .reverse();
  }, [orders, query, status]);

  const clearFilters = () => {
    setQuery('');
    setStatus('all');
  };

  return (
    <Card className="history-card">
      <div className="toolbar">
        <div className="toolbar__search" data-testid="orders-search">
          <Icon name="search" />
          <TextInput
            aria-label="搜索订单"
            placeholder="搜索证券或策略"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <Select
          aria-label="订单状态筛选"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="history-status-filter"
        >
          <option value="all">全部状态</option>
          {statuses.map((value) => (
            <option key={value} value={value}>
              {orderStatusView(value, null).label}
            </option>
          ))}
        </Select>
        <span className="toolbar__meta">
          {filtered.length === orders.length
            ? '共 ' + countText(orders.length, '笔')
            : '显示 ' + countText(filtered.length, '笔') + ' · 共 ' + countText(orders.length, '笔')}
        </span>
      </div>
      {filtered.length === 0 ? (
        <div data-testid="orders-empty">
          <EmptyState
            compact
            icon={orders.length === 0 ? 'list' : 'search'}
            title={orders.length === 0 ? EMPTY.ordersTitle : '没有匹配的订单'}
            description={orders.length === 0 ? EMPTY.ordersBody : '调整搜索或状态筛选后再看。'}
            actions={
              orders.length === 0 ? undefined : (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  清除筛选
                </Button>
              )
            }
          />
        </div>
      ) : (
        <>
          <div data-testid="orders-table">
            <Table label="模拟订单" className="orders-table history-table--orders">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>证券 / 方向</th>
                  <th className="num">委托数量</th>
                  <th className="num">成交 / 剩余</th>
                  <th className="num">限价</th>
                  <th>状态</th>
                  <th>原因</th>
                  <th aria-label="详情" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((order) => {
                  const reason = orderReasonText(order);
                  return (
                    <tr key={order.order_id} data-testid="order-row" onClick={() => selection.select(order)}>
                      <td>
                        <button
                          type="button"
                          className="row-link"
                          onClick={(event) => {
                            event.stopPropagation();
                            selection.select(order);
                          }}
                        >
                          {formatDay(order.day)}
                        </button>
                      </td>
                      <td>
                        <span className="cell-title">{order.instrument.code}</span>
                        <span className="cell-sub">
                          <SideBadge side={order.side} />
                        </span>
                      </td>
                      <td className="num">{countText(order.quantity, '股')}</td>
                      <td className="num">
                        {countText(order.confirmed_filled_shares, '股')} / {countText(order.remaining, '股')}
                      </td>
                      <td className="num">{formatCny(order.limit_fen)}</td>
                      <td>
                        <StatusBadge status={orderStatusView(order.status, order.reason)} size="sm" />
                      </td>
                      <td className="cell-reason">{reason === '' ? null : reason}</td>
                      <td className="row-action-cell" aria-hidden="true">
                        <span className="row-chevron">›</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </div>
          <div className="card__foot">
            <span>委托记录不等于实际成交。</span>
            <span>点击一行查看委托与关联成交。</span>
          </div>
        </>
      )}
      <OrderDrawer order={selection.item} open={selection.open} fills={fills} meta={meta} onClose={selection.close} />
    </Card>
  );
}

function DailyTab({ bundle }: { bundle: PaperBundle }) {
  const rows = bundle.equity;
  const account = bundle.account;
  const selection = useSelection<DailySelection>();
  const previousRows = useMemo(() => {
    const map = new Map<string, EquityRow | null>();
    rows.forEach((row, index) => map.set(row.day, rows[index - 1] ?? null));
    return map;
  }, [rows]);

  if (rows.length === 0) {
    return (
      <Card className="history-card">
        <EmptyState icon="calendar" title={EMPTY.dailyTitle} description={EMPTY.dailyBody} />
      </Card>
    );
  }

  const first = rows[0];
  const latest = rows[rows.length - 1];

  return (
    <div className="history-daily">
      <Card className="history-summary-card">
        <CardHead title="账户摘要" />
        <CardBody>
          <dl className="history-summary">
            <div>
              <dt>报告区间</dt>
              <dd>
                {dayText(first.day)} — {dayText(latest.day)}
              </dd>
            </div>
            <div>
              <dt>交易日数</dt>
              <dd className="numeric">{countText(rows.length, '个交易日')}</dd>
            </div>
            <div>
              <dt>初始资金</dt>
              <dd className="numeric">{moneyText(account.initial_nav_fen)}</dd>
            </div>
            <div>
              <dt>资金转入转出</dt>
              <dd className="numeric">{signedMoneyText(account.external_flow_total_fen)}</dd>
            </div>
          </dl>
        </CardBody>
      </Card>

      <Card className="history-card">
        <div data-testid="daily-table">
          <Table label="账户每日账本" className="daily-table history-table--daily">
            <thead>
              <tr>
                <th>日期</th>
                <th className="num">账户资产</th>
                <th className="num">现金</th>
                <th className="num">持仓市值</th>
                <th className="num">累计盈亏</th>
                <th className="num">累计收益率</th>
                <th>状态</th>
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
                    data-testid="daily-row"
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
                    <td className="num">{moneyText(row.nav_fen)}</td>
                    <td className="num">{moneyText(row.cash_fen)}</td>
                    <td className="num">{holdings === null ? '未记录' : formatCny(holdings)}</td>
                    <td className={'num ' + signClass(row.cumulative_pnl_fen)}>{signedMoneyText(row.cumulative_pnl_fen)}</td>
                    <td className={'num ' + signClass(row.return_bps)}>{returnText(row.return_bps)}</td>
                    <td>
                      {row.valuation_error === null ? null : (
                        <StatusBadge status={missingDataStatus(row.valuation_error)} size="sm" />
                      )}
                    </td>
                    <td className="row-action-cell" aria-hidden="true">
                      <span className="row-chevron">›</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </div>
        <div className="card__foot">
          <span>持仓市值 = 账户资产 − 现金</span>
          <span>
            {TERMS.dataDate} {dayText(latest.day)}
          </span>
        </div>
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

function AdvancedRecords({
  strategies,
  fills,
  orders,
  meta,
}: {
  strategies: StrategyRecord[];
  fills: Fill[];
  orders: Order[];
  meta: SnapshotMeta;
}) {
  const selection = useSelection<StrategyRecord>();
  return (
    <details className="advanced-records" data-testid="advanced-records">
      <summary className="advanced-records__summary" data-testid="advanced-records-toggle">
        <span className="advanced-records__title">
          <Icon name="layers" size={15} />
          高级记录
        </span>
        <span className="advanced-records__hint">策略版本记录与原始数据信息</span>
        <Icon name="chevron-down" size={14} className="advanced-records__chevron" />
      </summary>
      <div className="advanced-records__body">
        <Card>
          <CardHead title="策略版本记录" subtitle="仅作留档，不代表策略正在运行或未来收益。" />
          {strategies.length === 0 ? (
            <EmptyState
              compact
              icon="layers"
              title="还没有策略版本记录"
              description="有可用记录后，这里会显示策略名、所属组和独立收益/回撤。"
            />
          ) : (
            <>
              <Table label="策略版本记录" className="history-strategies-table">
                <thead>
                  <tr>
                    <th>策略</th>
                    <th>状态</th>
                    <th className="num">独立收益</th>
                    <th className="num">独立回撤</th>
                    <th aria-label="详情" />
                  </tr>
                </thead>
                <tbody>
                  {strategies.map((record) => (
                    <tr
                      key={record.deployment.deployment_id}
                      data-testid="strategy-row"
                      onClick={() => selection.select(record)}
                    >
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
                      </td>
                      <td>
                        <StatusBadge status={strategyRecordStatus(record.status)} size="sm" />
                      </td>
                      <td className={'num ' + signClass(record.pnl_fen)}>{signedMoneyText(record.pnl_fen)}</td>
                      <td className={'num ' + drawdownTone(record.drawdown_bps)}>
                        {record.drawdown_bps === null ? '未记录' : formatBps(record.drawdown_bps)}
                      </td>
                      <td className="row-action-cell" aria-hidden="true">
                        <span className="row-chevron">›</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              <div className="card__foot">
                <span>策略版本按报告留档，用于回看。</span>
                <span>{countText(strategies.length, '个')}</span>
              </div>
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
        <Card>
          <CardHead title="数据与快照" subtitle="当前页面读取的数据来源与校验信息。" />
          <CardBody>
            <Diagnostics title="数据诊断信息" items={snapshotItems(meta)} data={meta} />
          </CardBody>
        </Card>
      </div>
    </details>
  );
}
