import { Diagnostics } from '../ui/Diagnostics';
import { Drawer } from '../ui/Overlay';
import { Kv } from '../ui/Kv';
import { StatusBadge } from '../ui/StatusBadge';
import { countText, formatBps, formatCny, formatDay } from '../../lib/format';
import { statusView } from '../../lib/status';
import type { StatusView } from '../../lib/status';
import type { Fill, Order, SnapshotMeta, StrategyRecord } from '../../lib/types';
import { DrawerSection } from './DrawerSection';
import { SideBadge } from './Badges';

const RECORD_STATUS: Record<string, StatusView> = {
  snapshot_record_only: statusView('ok', '仅记录'),
  paper_assumption_only: statusView('ok', '仅记录'),
};

function recordStatusView(status: string): StatusView {
  if (Object.hasOwn(RECORD_STATUS, status)) return RECORD_STATUS[status];
  return statusView('unset', '状态未知');
}

function moneyText(value: string | null): string {
  return value === null ? '未记录' : formatCny(value, { signed: true });
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
      eyebrow="策略版本"
      title={record.deployment.strategy_id}
      meta={
        <StatusBadge status={recordStatusView(record.status)} size="sm" />
      }
    >
      <div data-testid="strategy-drawer">
        <DrawerSection title="记录状态">
          <Kv
            items={[
              { label: '状态', value: <StatusBadge status={recordStatusView(record.status)} size="sm" /> },
              { label: '独立收益', value: moneyText(record.pnl_fen) },
              {
                label: '独立回撤',
                value: record.drawdown_bps === null ? '未记录' : formatBps(record.drawdown_bps),
              },
            ]}
          />
          {record.pnl_fen === null && record.drawdown_bps === null ? (
            <p className="drawer-note">这份记录没有可用的独立收益与回撤数据。</p>
          ) : null}
          <p className="drawer-note">仅作记录，不代表策略正在运行或未来收益。</p>
        </DrawerSection>

        <DrawerSection title="关联记录">
          <Kv
            items={[
              { label: '模拟成交', value: countText(relatedFills.length, '笔') },
              { label: '模拟订单', value: countText(relatedOrders.length, '笔') },
            ]}
          />
          {relatedFills.length === 0 ? (
            <p className="drawer-note">没有与该策略关联的模拟成交。</p>
          ) : (
            <div className="mini-table-wrap">
              <table className="mini-table">
                <caption className="sr-only">该策略的模拟成交</caption>
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
            title="策略诊断信息"
            items={[
              { label: '策略', value: record.deployment.strategy_id },
              { label: '所属组', value: record.deployment.group_id },
              { label: '冻结版本', value: record.deployment.frozen_version },
              { label: '部署标识', value: record.deployment.deployment_id },
              { label: '记录状态（原始值）', value: record.status },
              { label: '收益（原始值）', value: record.pnl_fen ?? '未记录' },
              { label: '回撤（原始值）', value: record.drawdown_bps ?? '未记录' },
              { label: '不可用原因（原始值）', value: record.unavailable_reason ?? '未记录' },
              { label: '数据模式', value: meta === null ? '未记录' : meta.mode },
              { label: '快照标识', value: meta === null ? '未记录' : meta.snapshot_id },
            ]}
            data={{ record, snapshot: meta }}
          />
        </div>
      </div>
    </Drawer>
  );
}
