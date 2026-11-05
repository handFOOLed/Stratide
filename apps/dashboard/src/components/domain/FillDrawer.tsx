import { Callout } from '../ui/Callout';
import { Diagnostics } from '../ui/Diagnostics';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import { StatusBadge } from '../ui/StatusBadge';
import {
  countText,
  formatCny,
  formatDateTime,
  formatDay,
  instrumentLabel,
} from '../../lib/format';
import { humanReasonText, orderStatusView } from '../../lib/status';
import type { Fill, Order, SnapshotMeta } from '../../lib/types';
import { DrawerSection } from './DrawerSection';
import { SideBadge } from './Badges';

function notionalFen(fill: Fill): string {
  return (BigInt(fill.quantity) * BigInt(fill.price_fen)).toString();
}

function orderReasonText(order: Order): string | null {
  if (order.reason === null) return order.status === 'Rejected' ? '原因未记录' : null;
  const mapped = humanReasonText(order.reason);
  if (mapped === null || /^[\x20-\x7E]+$/.test(mapped)) return '原因未记录';
  return mapped;
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
  const amount = notionalFen(fill);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="模拟成交"
      title={fill.instrument.code}
      meta={
        <>
          <SideBadge side={fill.side} />
          <span className="drawer__meta-text">数据日期 {formatDay(fill.day)}</span>
        </>
      }
    >
      <div data-testid="fill-drawer">
        <Callout tone="info" className="drawer-callout">
          这是模拟成交，不是券商真实成交。
        </Callout>

        <div className="fill-summary">
          <div className="fill-summary__main">
            <span className="fill-summary__label">成交金额</span>
            <span className="fill-summary__value numeric">{formatCny(amount)}</span>
            <span className="fill-summary__sub numeric">
              {countText(fill.quantity, '股')} × {formatCny(fill.price_fen)}
            </span>
          </div>
          <div className="fill-summary__side">
            <span className="fill-summary__label">费用合计</span>
            <span className="fill-summary__fee numeric">{formatCny(fill.fee_fen)}</span>
            <span className="fill-summary__sub">{instrumentLabel(fill.instrument)}</span>
          </div>
        </div>

        <DrawerSection title="费用">
          {fill.fees === null ? (
            <p className="drawer-note">这笔成交只记录了费用合计。</p>
          ) : (
            <dl className="fee-table">
              <div>
                <dt>佣金</dt>
                <dd className="numeric">{formatCny(fill.fees.commission)}</dd>
              </div>
              <div>
                <dt>印花税</dt>
                <dd className="numeric">{formatCny(fill.fees.tax)}</dd>
              </div>
              <div>
                <dt>过户费</dt>
                <dd className="numeric">{formatCny(fill.fees.transfer)}</dd>
              </div>
            </dl>
          )}
        </DrawerSection>

        <DrawerSection title="关联订单">
          {order === null ? (
            <p className="drawer-note">没有找到这笔成交对应的订单。</p>
          ) : (
            <>
              <div className="drawer-order-status">
                <StatusBadge status={orderStatusView(order.status, order.reason)} size="sm" />
                <SideBadge side={order.side} />
              </div>
              <dl className="fee-table fee-table--plain">
                <div>
                  <dt>委托数量</dt>
                  <dd className="numeric">{countText(order.quantity, '股')}</dd>
                </div>
                <div>
                  <dt>成交数量</dt>
                  <dd className="numeric">{countText(order.confirmed_filled_shares, '股')}</dd>
                </div>
                <div>
                  <dt>限价</dt>
                  <dd className="numeric">{formatCny(order.limit_fen)}</dd>
                </div>
              </dl>
              {orderReasonText(order) === null ? null : (
                <p className="drawer-note">{orderReasonText(order)}</p>
              )}
            </>
          )}
        </DrawerSection>

        <DrawerSection title="时间与记录">
          <Kv
            tight
            items={[
              { label: '数据日期', value: formatDay(fill.day) },
              {
                label: '模拟成交时间',
                value: fill.simulated_at === null ? '未记录' : formatDateTime(fill.simulated_at),
              },
              {
                label: '交易保护检查时间',
                value: fill.risk_checked_at === null ? '未记录' : formatDateTime(fill.risk_checked_at),
              },
            ]}
          />
        </DrawerSection>

        <div className="drawer-diagnostics">
          <Diagnostics
            title="成交诊断信息"
            items={[
              { label: '成交编号', value: fill.fill_id },
              { label: '订单编号', value: fill.order_id },
              { label: '方向（原始值）', value: fill.side },
              { label: '执行假设', value: fill.execution_assumption ?? '未记录' },
              { label: '来源版本', value: fill.source_version ?? '未记录' },
              { label: '策略', value: fill.deployment.strategy_id },
              { label: '所属组', value: fill.deployment.group_id },
              { label: '冻结版本', value: fill.deployment.frozen_version },
              { label: '部署标识', value: fill.deployment.deployment_id },
              { label: '数据模式', value: meta === null ? '未记录' : meta.mode },
              { label: '快照标识', value: meta === null ? '未记录' : meta.snapshot_id },
            ]}
            data={{ fill, snapshot: meta }}
          />
        </div>
      </div>
    </Drawer>
  );
}
