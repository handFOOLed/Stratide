import { Badge } from '../ui/Badge';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import {
  formatCny,
  formatDay,
  formatShares,
  instrumentLabel,
  orderStatusLabel,
} from '../../lib/format';
import type { Fill, Order } from '../../lib/types';
import { DrawerNote, DrawerSection } from './DrawerSection';
import { ModeBadge, OrderStatusBadge, SideBadge } from './Badges';
import type { SnapshotMeta } from '../../lib/types';

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
  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="模拟订单"
      title={'订单 #' + order.order_id}
      meta={
        <>
          <SideBadge side={order.side} />
          <OrderStatusBadge status={order.status} label={orderStatusLabel(order.status)} />
          <Badge tone="outline">{formatDay(order.day)}</Badge>
          {meta ? <ModeBadge mode={meta.mode} /> : null}
        </>
      }
    >
      <DrawerSection title="委托">
        <Kv
          items={[
            { label: '证券', value: instrumentLabel(order.instrument) },
            { label: '方向', value: order.side === 'Buy' ? '买入' : '卖出' },
            { label: '委托数量', value: formatShares(order.quantity) + ' 股' },
            { label: '已确认成交', value: formatShares(order.confirmed_filled_shares) + ' 股' },
            { label: '剩余数量', value: formatShares(order.remaining) + ' 股' },
            { label: '限价', value: formatCny(order.limit_fen) },
            { label: '状态', value: orderStatusLabel(order.status) + ' / ' + order.status },
          ]}
        />
      </DrawerSection>

      <DrawerSection title="原始原因">
        <p className="prose">{order.reason || '报告未提供额外原因。'}</p>
        <DrawerNote>原始 reason 按服务端文本展示，不由前端改写或归类。</DrawerNote>
      </DrawerSection>

      <DrawerSection title="关联成交">
        {related.length === 0 ? (
          <DrawerNote>此订单没有已确认的模拟成交。</DrawerNote>
        ) : (
          <div className="mini-table-wrap">
            <table className="mini-table">
              <thead>
                <tr>
                  <th>成交</th>
                  <th className="num">数量</th>
                  <th className="num">价格</th>
                  <th className="num">费用</th>
                </tr>
              </thead>
              <tbody>
                {related.map((fill) => (
                  <tr key={fill.fill_id}>
                    <td className="cell-mono">{fill.fill_id}</td>
                    <td className="num">{formatShares(fill.quantity)}</td>
                    <td className="num">{formatCny(fill.price_fen)}</td>
                    <td className="num">{formatCny(fill.fee_fen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DrawerSection>

      <DrawerSection title="部署记录">
        <Kv
          items={[
            { label: '所属组', value: order.deployment.group_id },
            { label: '策略', value: order.deployment.strategy_id },
            { label: '冻结版本', value: order.deployment.frozen_version },
            { label: '部署标识', value: order.deployment.deployment_id },
          ]}
        />
      </DrawerSection>
    </Drawer>
  );
}
