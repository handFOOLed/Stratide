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
import type { Fill, Order } from '../../lib/types';
import { DrawerNote, DrawerSection } from './DrawerSection';
import { ModeBadge, SideBadge } from './Badges';
import type { SnapshotMeta } from '../../lib/types';

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
  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="模拟成交"
      title={fill.fill_id}
      meta={
        <>
          <SideBadge side={fill.side} />
          <Badge tone="outline">{formatDay(fill.day)}</Badge>
          {meta ? <ModeBadge mode={meta.mode} /> : null}
        </>
      }
    >
      <DrawerSection title="成交">
        <Kv
          items={[
            { label: '证券', value: instrumentLabel(fill.instrument) },
            { label: '方向', value: sideLabel(fill.side) },
            { label: '成交数量', value: formatShares(fill.quantity) + ' 股' },
            { label: '成交价格', value: formatCny(fill.price_fen) },
            { label: '费用合计', value: formatCny(fill.fee_fen) },
          ]}
        />
        {fill.fees ? (
          <div className="fee-breakdown">
            <div><span>佣金</span><strong className="numeric">{formatCny(fill.fees.commission)}</strong></div>
            <div><span>印花税</span><strong className="numeric">{formatCny(fill.fees.tax)}</strong></div>
            <div><span>过户费</span><strong className="numeric">{formatCny(fill.fees.transfer)}</strong></div>
          </div>
        ) : (
          <DrawerNote>报告未提供费用拆分，仅保留费用合计。</DrawerNote>
        )}
      </DrawerSection>

      <DrawerSection title="时间口径">
        <Kv
          items={[
            { label: '模拟记账时间', value: formatDateTime(fill.simulated_at) },
            { label: '开盘审查时间', value: formatDateTime(fill.risk_checked_at) },
            { label: '源日期', value: formatDay(fill.day) },
          ]}
        />
        <DrawerNote>
          这两个时间都不是券商真实成交时间。模拟记账时间来自本地 Paper 账本，开盘审查时间来自风控检查或历史模型。
        </DrawerNote>
      </DrawerSection>

      <DrawerSection title="关联订单">
        {order ? (
          <Kv
            items={[
              { label: '订单号', value: '#' + order.order_id },
              { label: '状态', value: orderStatusLabel(order.status) + ' / ' + order.status },
              { label: '原始原因', value: order.reason || '无额外原因' },
            ]}
          />
        ) : (
          <DrawerNote>订单记录不可用或不在当前快照中。</DrawerNote>
        )}
        <DrawerNote>委托意图不等于实际成交；关联订单只用于核对。</DrawerNote>
      </DrawerSection>

      <DrawerSection title="执行与来源">
        <Kv
          items={[
            { label: '执行假设', value: fill.execution_assumption || '报告未提供执行假设' },
            { label: '来源版本', value: fill.source_version || '报告未提供' },
            { label: '所属组', value: fill.deployment.group_id },
            { label: '策略', value: fill.deployment.strategy_id },
            { label: '冻结版本', value: fill.deployment.frozen_version },
            { label: '部署标识', value: fill.deployment.deployment_id },
          ]}
        />
      </DrawerSection>
    </Drawer>
  );
}