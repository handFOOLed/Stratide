import { Callout } from '../ui/Callout';
import { Diagnostics } from '../ui/Diagnostics';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import { StatusBadge } from '../ui/StatusBadge';
import { countText, formatCny, formatDay, instrumentLabel } from '../../lib/format';
import { humanReasonText, orderStatusView } from '../../lib/status';
import type { Fill, Order, SnapshotMeta } from '../../lib/types';
import { DrawerSection } from './DrawerSection';
import { SideBadge } from './Badges';

function orderReasonText(order: Order): string | null {
  if (order.reason === null) return order.status === 'Rejected' ? '原因未记录' : null;
  const mapped = humanReasonText(order.reason);
  if (mapped === null || /^[\x20-\x7E]+$/.test(mapped)) return '原因未记录';
  return mapped;
}

export function OrderDrawer({
  order,
  open,
  fills,
  meta,
  onClose,
}: {
  order: Order | null;
  open: boolean;
  fills: Fill[];
  meta: SnapshotMeta | null;
  onClose: () => void;
}) {
  if (!order) return null;
  const related = fills.filter((fill) => fill.order_id === order.order_id);
  const reason = orderReasonText(order);
  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="模拟订单"
      title={order.instrument.code}
      meta={
        <>
          <SideBadge side={order.side} />
          <StatusBadge status={orderStatusView(order.status, order.reason)} size="sm" />
          <span className="drawer__meta-text">数据日期 {formatDay(order.day)}</span>
        </>
      }
    >
      <div data-testid="order-drawer">
        <Callout tone="info" className="drawer-callout">
          这是模拟订单，不是券商真实委托。
        </Callout>

        <DrawerSection title="委托">
          <Kv
            tight
            items={[
              { label: '证券', value: instrumentLabel(order.instrument) },
              {
                label: '方向',
                value: <SideBadge side={order.side} />,
              },
              { label: '委托数量', value: countText(order.quantity, '股') },
              { label: '已成交数量', value: countText(order.confirmed_filled_shares, '股') },
              { label: '剩余数量', value: countText(order.remaining, '股') },
              { label: '限价', value: formatCny(order.limit_fen) },
            ]}
          />
        </DrawerSection>

        <DrawerSection title="原因">
          {reason === null ? (
            <p className="drawer-note">这笔订单没有记录原因。</p>
          ) : (
            <p className="prose">{reason}</p>
          )}
        </DrawerSection>

        <DrawerSection title="关联成交">
          {related.length === 0 ? (
            <p className="drawer-note">这笔订单没有已确认的模拟成交。</p>
          ) : (
            <div className="mini-table-wrap">
              <table className="mini-table">
                <caption className="sr-only">该订单的模拟成交</caption>
                <thead>
                  <tr>
                    <th>日期 / 方向</th>
                    <th className="num">数量</th>
                    <th className="num">价格</th>
                    <th className="num">费用</th>
                  </tr>
                </thead>
                <tbody>
                  {related.map((fill) => (
                    <tr key={fill.fill_id}>
                      <td>
                        {formatDay(fill.day)} <SideBadge side={fill.side} />
                      </td>
                      <td className="num">{countText(fill.quantity, '股')}</td>
                      <td className="num">{formatCny(fill.price_fen)}</td>
                      <td className="num">{formatCny(fill.fee_fen)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DrawerSection>

        <div className="drawer-diagnostics">
          <Diagnostics
            title="订单诊断信息"
            items={[
              { label: '订单编号', value: order.order_id },
              { label: '方向（原始值）', value: order.side },
              { label: '状态（原始值）', value: order.status },
              { label: '原因（原始值）', value: order.reason ?? '未记录' },
              { label: '策略', value: order.deployment.strategy_id },
              { label: '所属组', value: order.deployment.group_id },
              { label: '冻结版本', value: order.deployment.frozen_version },
              { label: '部署标识', value: order.deployment.deployment_id },
              { label: '数据模式', value: meta === null ? '未记录' : meta.mode },
              { label: '快照标识', value: meta === null ? '未记录' : meta.snapshot_id },
            ]}
            data={{ order, fills: related, snapshot: meta }}
          />
        </div>
      </div>
    </Drawer>
  );
}
