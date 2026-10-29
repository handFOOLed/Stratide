import { Badge } from '../ui/Badge';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import {
  formatCny,
  formatDateTime,
  formatDay,
  formatShares,
  instrumentLabel,
  orderStatusLabel,
  sideLabel,
} from '../../lib/format';
import type { Fill, Order, SnapshotMeta } from '../../lib/types';
import { DrawerSection } from './DrawerSection';
import { ModeBadge, SideBadge } from './Badges';

function notional(fill: Fill): string | null {
  if (!/^\d+$/.test(fill.quantity) || !/^\d+$/.test(fill.price_fen)) return null;
  try {
    return (BigInt(fill.quantity) * BigInt(fill.price_fen)).toString();
  } catch {
    return null;
  }
}

export function FillDrawer({
  fill,
  open,
  orders,
  meta,
  onClose,
}: {
  fill: Fill | null;
  open: boolean;
  orders: Order[];
  meta: SnapshotMeta | null;
  onClose: () => void;
}) {
  if (!fill) return null;
  const order = orders.find((item) => item.order_id === fill.order_id) ?? null;
  const amount = notional(fill);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="模拟成交"
      title={fill.instrument.code}
      meta={
        <>
          <SideBadge side={fill.side} />
          <span className="drawer__meta-text">{formatDay(fill.day)}</span>
          {meta ? <ModeBadge mode={meta.mode} /> : null}
        </>
      }
    >
      <div className="fill-summary">
        <div className="fill-summary__main">
          <span className="fill-summary__label">成交金额</span>
          <span className="fill-summary__value numeric">{amount ? formatCny(amount) : '—'}</span>
          <span className="fill-summary__sub numeric">
            {formatShares(fill.quantity)} 股 × {formatCny(fill.price_fen)}
          </span>
        </div>
        <div className="fill-summary__side">
          <span className="fill-summary__label">费用合计</span>
          <span className="fill-summary__fee numeric">{formatCny(fill.fee_fen)}</span>
          <span className="fill-summary__sub">{instrumentLabel(fill.instrument)}</span>
        </div>
      </div>

      <DrawerSection title="费用">
        {fill.fees ? (
          <dl className="fee-table">
            <div><dt>佣金</dt><dd className="numeric">{formatCny(fill.fees.commission)}</dd></div>
            <div><dt>印花税</dt><dd className="numeric">{formatCny(fill.fees.tax)}</dd></div>
            <div><dt>过户费</dt><dd className="numeric">{formatCny(fill.fees.transfer)}</dd></div>
          </dl>
        ) : (
          <p className="drawer-note">报告只提供费用合计 {formatCny(fill.fee_fen)}，没有拆分。</p>
        )}
      </DrawerSection>

      <DrawerSection title="关联订单">
        {order ? (
          <>
            <div className="order-link">
              <span className="order-link__id mono">#{order.order_id}</span>
              <Badge tone={order.status === 'Rejected' ? 'danger' : order.status === 'Filled' ? 'success' : 'neutral'}>
                {orderStatusLabel(order.status)}
              </Badge>
            </div>
            <dl className="fee-table fee-table--plain">
              <div><dt>方向</dt><dd>{sideLabel(order.side)}</dd></div>
              <div><dt>委托数量</dt><dd className="numeric">{formatShares(order.quantity)} 股</dd></div>
              <div><dt>成交数量</dt><dd className="numeric">{formatShares(order.confirmed_filled_shares)} 股</dd></div>
              <div><dt>限价</dt><dd className="numeric">{formatCny(order.limit_fen)}</dd></div>
            </dl>
            {order.reason ? <p className="drawer-note">{order.reason}</p> : null}
          </>
        ) : (
          <p className="drawer-note">当前快照中没有关联订单。</p>
        )}
      </DrawerSection>

      <details className="drawer-more">
        <summary className="drawer-more__summary">
          <span>时间与来源</span>
          <span className="drawer-more__hint">模拟记账，非券商成交</span>
        </summary>
        <div className="drawer-more__body">
          <Kv
            tight
            items={[
              { label: '模拟记账时间', value: formatDateTime(fill.simulated_at) },
              { label: '开盘审查时间', value: formatDateTime(fill.risk_checked_at) },
              { label: '源日期', value: formatDay(fill.day) },
              { label: '成交编号', value: <span className="mono">{fill.fill_id}</span> },
              { label: '执行假设', value: fill.execution_assumption || '报告未提供' },
              { label: '来源版本', value: fill.source_version || '报告未提供' },
              { label: '组 / 策略', value: fill.deployment.group_id + ' · ' + fill.deployment.strategy_id },
              { label: '冻结版本', value: fill.deployment.frozen_version },
              { label: '部署标识', value: fill.deployment.deployment_id },
            ]}
          />
        </div>
      </details>
    </Drawer>
  );
}
