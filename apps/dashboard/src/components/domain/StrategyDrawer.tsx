import { Badge } from '../ui/Badge';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import { formatBps, formatCny, formatDay, formatShares } from '../../lib/format';
import type { Fill, Order, StrategyRecord } from '../../lib/types';
import { DrawerNote, DrawerSection } from './DrawerSection';
import { ModeBadge, SideBadge } from './Badges';
import type { SnapshotMeta } from '../../lib/types';

function statusLabel(status: string): string {
  return status === 'snapshot_record_only' ? '快照记录' : status;
}

export function StrategyDrawer({
  record,
  open,
  fills,
  orders,
  meta,
  onClose,
}: {
  record: StrategyRecord | null;
  open: boolean;
  fills: Fill[];
  orders: Order[];
  meta: SnapshotMeta | null;
  onClose: () => void;
}) {
  if (!record) return null;
  const relatedFills = fills.filter(
    (fill) => fill.deployment.strategy_id === record.deployment.strategy_id,
  );
  const relatedOrders = orders.filter(
    (order) => order.deployment.strategy_id === record.deployment.strategy_id,
  );
  return (
    <Drawer
      open={open}
      onClose={onClose}
      eyebrow="策略档案"
      title={record.deployment.strategy_id}
      meta={
        <>
          <Badge tone="neutral">{record.deployment.group_id}</Badge>
          {meta ? <ModeBadge mode={meta.mode} /> : null}
        </>
      }
    >
      <DrawerSection title="记录状态">
        <Kv
          items={[
            { label: '状态', value: statusLabel(record.status) },
            { label: '独立收益', value: record.pnl_fen === null ? '不可用' : formatCny(record.pnl_fen) },
            { label: '独立回撤', value: record.drawdown_bps === null ? '不可用' : formatBps(record.drawdown_bps) },
            { label: '不可用原因', value: record.unavailable_reason || '报告未说明' },
          ]}
        />
        <DrawerNote>
          这是已发布报告中的冻结部署记录，不代表策略进程正在运行，也不构成独立策略绩效或策略资格。
        </DrawerNote>
      </DrawerSection>

      <DrawerSection title="部署">
        <Kv
          items={[
            { label: '所属组', value: record.deployment.group_id },
            { label: '策略', value: record.deployment.strategy_id },
            { label: '冻结版本', value: record.deployment.frozen_version },
            { label: '部署标识', value: record.deployment.deployment_id },
          ]}
        />
      </DrawerSection>

      <DrawerSection title="关联记录">
        <Kv
          items={[
            { label: '模拟成交', value: formatShares(relatedFills.length) + ' 笔' },
            { label: '模拟订单', value: formatShares(relatedOrders.length) + ' 笔' },
          ]}
        />
        {relatedFills.length > 0 ? (
          <div className="mini-table-wrap">
            <table className="mini-table">
              <thead>
                <tr>
                  <th>日期 / 方向</th>
                  <th className="num">数量</th>
                  <th className="num">价格</th>
                  <th className="num">费用</th>
                </tr>
              </thead>
              <tbody>
                {relatedFills.slice(-5).reverse().map((fill) => (
                  <tr key={fill.fill_id}>
                    <td>
                      {formatDay(fill.day)} <SideBadge side={fill.side} />
                    </td>
                    <td className="num">{formatShares(fill.quantity)}</td>
                    <td className="num">{formatCny(fill.price_fen)}</td>
                    <td className="num">{formatCny(fill.fee_fen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <DrawerNote>没有与该策略关联的已确认模拟成交。</DrawerNote>
        )}
      </DrawerSection>
    </Drawer>
  );
}
